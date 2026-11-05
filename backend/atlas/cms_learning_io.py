"""Closed private authoring bundles; existing leased jobs own every durable effect."""
import hashlib
import json
import re
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.db.models import BinaryField, Prefetch, Sum, Value, prefetch_related_objects
from django.db.models.functions import Cast, Coalesce, Length
from django.utils import timezone

from .cms_artifacts import artifact_bytes, bounded_json, store_generated as _store
from .cms_audit import attribution
from .cms_case_editor import revision_etag
from .cms_job_models import AdminArtifact, AdminJob
from .cms_jobs import checkpoint_job, enqueue_job, job_scope
from .cms_learning_lifecycle import KINDS
from .cms_models import AdminAuditEvent, RolePolicy
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sessions import current_session
from .models import (Concept, Disorder, Quiz, QuizQuestion, QuizChoice, QuizAttempt,
    Flashcard, UserFlashcardProgress, DailyChallengeChoice, DailyChallengeAttempt,
    CognitiveDistortionPracticeChoice, CognitiveDistortionPracticeAttempt, StudyActivity)

SCHEMA = "psychology-atlas-learning-authoring-v1"
MANIFEST_SCHEMA = "psychology-atlas-learning-selection-v1"
JOB_KINDS = {"learning_import", "learning_export"}
MAX_BYTES, MAX_ITEMS, MAX_QUESTIONS, MAX_CHOICES = 1024 * 1024, 20, 200, 2000
FIELDS = {
    "quiz": {"slug", "title", "description", "disorder_slug", "questions"},
    "flashcard": {"slug", "front", "back", "hint", "difficulty", "concept_slug", "disorder_slug"},
    "daily": {"prompt", "explanation", "concept_slug", "disorder_slug", "choices"},
    "distortions": {"slug", "prompt", "explanation", "difficulty", "target_concept_slug", "choices"},
}


def require_transfer(actor, kind):
    for cap in ("cms_enter", "cms_learning_view"):
        require(actor, cap)
    caps = ("cms_learning_create", "cms_learning_edit", "cms_artifact_upload") if kind == "learning_import" else ("cms_learning_export",)
    for cap in caps:
        require(actor, cap)


def _json(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise CMSFailure("JSON_LIMIT", 400)
    _, document = bounded_json(raw, protect_assessment=False)
    stack, nodes = [(document, 0)], 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > 8 or nodes > 10000:
            raise CMSFailure("JSON_LIMIT", 400)
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
    return document


def _reference(model, slug, *, nullable=True, lock=False):
    if slug is None and nullable:
        return None
    if type(slug) is not str or not 0 < len(slug) <= 200:
        raise CMSFailure("INVALID_REFERENCE", 400)
    rows = model.objects.select_for_update() if lock else model.objects
    row = rows.filter(slug=slug, is_active=True).only("pk").first()
    if row is None:
        raise CMSFailure("INVALID_REFERENCE", 400)
    return row.pk


def parse_bundle(raw, *, lock_references=False):
    from .cms_quiz_editor import _SLUG, _metadata_values, _questions
    from .cms_flashcard_editor import _check_fields, _check_references
    from .cms_practice_editor import _validate_creation, _validate_edit
    document = _json(raw)
    if (set(document) != {"schema_version", "items"} or document["schema_version"] != SCHEMA
            or type(document["items"]) is not list or not 1 <= len(document["items"]) <= MAX_ITEMS):
        raise CMSFailure("UNSUPPORTED_SCHEMA", 400)
    keys, identities, entries = set(), set(), []
    question_total = choice_total = 0
    for row in document["items"]:
        if (type(row) is not dict or set(row) != {"kind", "key", "fields"}
                or type(row["kind"]) is not str or row["kind"] not in KINDS
                or type(row["key"]) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,199}", row["key"])
                or row["key"] in keys or type(row["fields"]) is not dict
                or set(row["fields"]) != FIELDS[row["kind"]]):
            raise CMSFailure("INVALID_LEARNING_BUNDLE", 400)
        keys.add(row["key"])
        kind, fields = row["kind"], dict(row["fields"])
        if "slug" in fields:
            if type(fields["slug"]) is not str:
                raise CMSFailure("INVALID_FIELDS", 400)
            identity = (kind, fields["slug"])
            if identity in identities:
                raise CMSFailure("INVALID_LEARNING_BUNDLE", 400)
            identities.add(identity)
        for name, model in (("concept", Concept), ("disorder", Disorder), ("target_concept", Concept)):
            slug_key = name + "_slug"
            if slug_key in fields:
                fields[name + "_id"] = _reference(model, fields.pop(slug_key),
                    nullable=name != "target_concept", lock=lock_references)
        entry = {"kind": kind}
        if kind == "quiz":
            questions = _questions({"questions": fields.pop("questions")})
            slug = fields["slug"]
            if len(slug) > 160 or not _SLUG.fullmatch(slug):
                raise CMSFailure("INVALID_FIELDS", 400)
            _metadata_values({key: value for key, value in fields.items() if key != "slug"})
            entry["questions"] = questions
            question_total += len(questions)
            choice_total += sum(len(question["choices"]) for question in questions)
        elif kind == "flashcard":
            _check_fields(fields, creating=True)
            _check_references(fields)
        else:
            choices = fields.pop("choices")
            if type(choices) is not list or not 2 <= len(choices) <= 10:
                raise CMSFailure("INVALID_CHOICES", 400)
            normalized = []
            for choice in choices:
                allowed = {"text", "is_correct"} | ({"concept_slug"} if kind == "distortions" else set())
                if type(choice) is not dict or set(choice) != allowed:
                    raise CMSFailure("INVALID_CHOICES", 400)
                choice = dict(choice)
                if kind == "distortions":
                    choice["concept_id"] = _reference(Concept, choice.pop("concept_slug"),
                                                       nullable=False, lock=lock_references)
                normalized.append(choice)
            _validate_creation(kind, fields)
            _validate_edit(kind, {"prompt": fields["prompt"], "explanation": fields["explanation"],
                                 "choices": normalized}, KINDS[kind](**fields))
            entry["choices"] = normalized
            choice_total += len(normalized)
        if question_total > MAX_QUESTIONS or choice_total > MAX_CHOICES:
            raise CMSFailure("JSON_LIMIT", 400)
        entry["creation"] = fields
        entries.append(entry)
    return document, entries


def candidates(kind):
    if kind not in KINDS:
        raise CMSFailure("NOT_FOUND", 404)
    rows = KINDS[kind].objects.filter(is_active=False, seed_managed=False, archived_at__isnull=True)
    if kind == "quiz":
        return rows.exclude(pk__in=QuizAttempt.objects.values("quiz_id")).exclude(
            pk__in=StudyActivity.objects.filter(quiz_id__isnull=False).values("quiz_id"))
    if kind == "flashcard":
        return rows.exclude(pk__in=UserFlashcardProgress.objects.values("flashcard_id")).exclude(
            pk__in=StudyActivity.objects.filter(flashcard_id__isnull=False).values("flashcard_id"))
    if kind == "daily":
        return rows.exclude(pk__in=DailyChallengeAttempt.objects.values("challenge_id"))
    return rows.exclude(pk__in=CognitiveDistortionPracticeAttempt.objects.values("item_id"))


def selection_items(value):
    if type(value) is not list or not 1 <= len(value) <= MAX_ITEMS:
        raise CMSFailure("JSON_LIMIT", 400)
    result, seen = [], set()
    for row in value:
        if (type(row) is not dict or set(row) != {"kind", "resource_id", "etag"}
                or type(row["kind"]) is not str or row["kind"] not in KINDS
                or type(row["resource_id"]) is not int or not 0 < row["resource_id"] < 2**63
                or type(row["etag"]) is not str or not re.fullmatch(r'"[0-9]{1,20}"', row["etag"])):
            raise CMSFailure("INVALID_FIELDS", 400)
        identity = (row["kind"], row["resource_id"])
        if identity in seen:
            raise CMSFailure("INVALID_FIELDS", 400)
        seen.add(identity)
        result.append({**row, "etag": str(int(row["etag"].strip('"')))})
    return sorted(result, key=lambda row: (row["kind"], row["resource_id"]))


def _selected_rows(items):
    rows = []
    for entry in items:
        kind, identifier = entry["kind"], entry["resource_id"]
        item = KINDS[kind].objects.select_for_update().only(
            "pk", "updated_at", "is_active", "seed_managed", "archived_at").filter(pk=identifier).first()
        if item is None or not candidates(kind).filter(pk=identifier).exists():
            raise CMSFailure("LEARNING_EXPORT_PROTECTED", 409)
        if revision_etag(item) != int(entry["etag"]):
            raise CMSFailure("STALE_REVISION", 412)
        rows.append((kind, item))
    return rows


def _guard_export(rows):
    identifiers = {kind: [item.pk for item_kind, item in rows if item_kind == kind] for kind in KINDS}
    questions = QuizQuestion.objects.filter(quiz_id__in=identifiers["quiz"])
    choices = [QuizChoice.objects.filter(question__quiz_id__in=identifiers["quiz"]),
        DailyChallengeChoice.objects.filter(challenge_id__in=identifiers["daily"]),
        CognitiveDistortionPracticeChoice.objects.filter(item_id__in=identifiers["distortions"])]
    if questions.count() > MAX_QUESTIONS or sum(query.count() for query in choices) > MAX_CHOICES:
        raise CMSFailure("JSON_LIMIT", 400)
    fields = {
        "quiz": ("slug", "title", "description", "disorder__slug"),
        "flashcard": ("slug", "front", "back", "hint", "difficulty", "concept__slug", "disorder__slug"),
        "daily": ("prompt", "explanation", "concept__slug", "disorder__slug"),
        "distortions": ("slug", "prompt", "explanation", "difficulty", "target_concept__slug"),
    }
    sources = [(KINDS[kind].objects.filter(pk__in=identifiers[kind]), names) for kind, names in fields.items()]
    sources += [(questions, ("prompt", "explanation")), (choices[0], ("text",)),
                (choices[1], ("text",)), (choices[2], ("text", "concept__slug"))]
    total = 0
    for query, names in sources:
        expression = Value(0)
        for name in names:
            # SQLite TEXT length stops at NUL; BLOB length counts all stored bytes.
            length = Length(Cast(name, BinaryField())) if connection.vendor == "sqlite" else Length(name)
            expression += Coalesce(length, Value(0))
        total += query.aggregate(total=Sum(expression))["total"] or 0
        if total > MAX_BYTES:
            raise CMSFailure("JSON_LIMIT", 400)


def _export_document(rows):
    _guard_export(rows)
    loaded = {}
    for kind in KINDS:
        identifiers = [item.pk for item_kind, item in rows if item_kind == kind]
        if not identifiers:
            continue
        items = list(KINDS[kind].objects.filter(pk__in=identifiers))
        relations = {
            "quiz": ("disorder", Prefetch("questions", queryset=QuizQuestion.objects.order_by("sort_order", "pk")
                .prefetch_related(Prefetch("choices", queryset=QuizChoice.objects.order_by("sort_order", "pk"))))),
            "flashcard": ("concept", "disorder"),
            "daily": ("concept", "disorder", Prefetch("choices", queryset=DailyChallengeChoice.objects.order_by("sort_order", "pk"))),
            "distortions": ("target_concept", Prefetch("choices", queryset=CognitiveDistortionPracticeChoice.objects
                .select_related("concept").order_by("sort_order", "pk"))),
        }
        prefetch_related_objects(items, *relations[kind])
        loaded.update({(kind, item.pk): item for item in items})
    document = {"schema_version": SCHEMA, "items": []}
    for index, (kind, selected) in enumerate(rows):
        item = loaded[(kind, selected.pk)]
        if kind == "quiz":
            fields = {"slug": item.slug, "title": item.title, "description": item.description,
                      "disorder_slug": item.disorder.slug if item.disorder_id else None, "questions": []}
            for question in item.questions.all():
                choices = list(question.choices.all())
                if not question.is_active or any(not choice.is_active for choice in choices):
                    raise CMSFailure("LEARNING_EXPORT_PROTECTED", 409)
                fields["questions"].append({"prompt": question.prompt, "explanation": question.explanation,
                    "choices": [{"text": choice.text, "is_correct": choice.is_correct} for choice in choices]})
        elif kind == "flashcard":
            fields = {"slug": item.slug, "front": item.front, "back": item.back, "hint": item.hint,
                "difficulty": item.difficulty, "concept_slug": item.concept.slug if item.concept_id else None,
                "disorder_slug": item.disorder.slug if item.disorder_id else None}
        else:
            choices = list(item.choices.all())
            if any(not choice.is_active for choice in choices):
                raise CMSFailure("LEARNING_EXPORT_PROTECTED", 409)
            fields = {"prompt": item.prompt, "explanation": item.explanation,
                "choices": [{"text": choice.text, "is_correct": choice.is_correct,
                    **({"concept_slug": choice.concept.slug} if kind == "distortions" else {})} for choice in choices]}
            if kind == "daily":
                fields.update(concept_slug=item.concept.slug if item.concept_id else None,
                              disorder_slug=item.disorder.slug if item.disorder_id else None)
            else:
                fields.update(slug=item.slug, difficulty=item.difficulty, target_concept_slug=item.target_concept.slug)
        document["items"].append({"kind": kind, "key": f"{kind}-{index + 1}", "fields": fields})
    raw = _encoded(document)
    parse_bundle(raw, lock_references=True)
    return raw


def _encoded(document):
    chunks, size = [], 0
    for chunk in json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":")).iterencode(document):
        encoded = chunk.encode("utf-8")
        size += len(encoded)
        if size > MAX_BYTES:
            raise CMSFailure("JSON_LIMIT", 400)
        chunks.append(encoded)
    return b"".join(chunks)


def _artifact(actor, identifier, raw, resource_type, version):
    return AdminArtifact(id=identifier, kind="learning_json" if resource_type == "learning_export_manifest" else "learning_export_json",
        domain="learning", owner=actor, owner_ref=attribution(actor.pk), resource_type=resource_type,
        resource_version=str(version), filename="learning-selection.json" if resource_type == "learning_export_manifest" else "learning-export.json",
        storage_key=identifier.hex + ".json", size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
        expires_at=timezone.now() + timedelta(days=7))



def enqueue_export(actor_id, session_id, data, request_id):
    if type(data) is not dict or set(data) != {"items", "request_key"} or type(data["request_key"]) is not str:
        raise CMSFailure("INVALID_FIELDS", 400)
    try:
        key = uuid.UUID(data["request_key"])
    except ValueError:
        raise CMSFailure("INVALID_FIELDS", 400)
    items = selection_items(data["items"])
    raw = _encoded({"schema_version": MANIFEST_SCHEMA, "items": items})
    checksum = hashlib.sha256(raw).hexdigest()

    def previous(actor):
        old = AdminJob.objects.filter(actor_ref=attribution(actor.pk), request_key=key).first()
        if old:
            job_scope(actor, old)
            if old.kind != "learning_export" or old.artifact.sha256 != checksum:
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
        return old

    with policy_lock():
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require_transfer(actor, "learning_export")
        actor_ref = attribution(actor.pk)
        old = previous(actor)
        if old:
            return old
        _selected_rows(items)
        identifier = uuid.uuid5(key, actor_ref + ":learning-export-manifest")
        artifact = AdminArtifact.objects.select_for_update().filter(pk=identifier).first()
        if artifact is None:
            artifact = _artifact(actor, identifier, raw, "learning_export_manifest", key)
            artifact.save(force_insert=True)
            AdminAuditEvent.objects.create(actor=actor, action="learning.transfer_prepared", outcome="success",
                target_key=str(artifact.pk), reason="LEARNING_TRANSFER", request_id=request_id)
        elif (artifact.owner_id != actor.pk or artifact.kind != "learning_json" or artifact.domain != "learning"
                or artifact.resource_type != "learning_export_manifest" or artifact.sha256 != checksum):
            raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
    # The quarantine intent survives a file-write or enqueue failure.
    with policy_lock():
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require_transfer(actor, "learning_export")
        old = previous(actor)
        if old:
            return old
        artifact = AdminArtifact.objects.select_for_update().get(pk=identifier)
        if artifact.state not in {"quarantine", "ready"} or artifact.expires_at <= timezone.now():
            raise CMSFailure("ARTIFACT_NOT_READY", 409)
        _selected_rows(items)
        _store(artifact, raw)
        current_session(session_id, actor)
        require_transfer(actor, "learning_export")
        artifact.state, artifact.validation_code = "ready", "LEARNING_SELECTION"
        artifact.save(update_fields=["state", "validation_code"])
        return enqueue_job(actor.pk, session_id, artifact.pk, key, request_id, kind="learning_export")


def _effect_authority(job):
    from .cms_jobs import _authority
    _authority(job, RolePolicy.objects.get(pk=1))
    if job.lease_expires_at is None or job.lease_expires_at <= timezone.now():
        raise CMSFailure("LEASE_LOST", 409)


def _complete(job, result):
    job.checkpoint = {**job.checkpoint, "complete": True, "input_sha256": job.artifact.sha256, "result": result}
    job.progress_done = job.progress_total = result["items"]
    AdminAuditEvent.objects.create(actor_id=job.actor_id, action="learning.imported" if job.kind == "learning_import" else "learning.exported",
        outcome="success", target_key=str(job.pk), reason="LEARNING_TRANSFER", request_id=uuid.uuid4())
    _effect_authority(job)


def process_learning(job_id, token):
    from .cms_quiz_editor import create_quiz, replace_questions
    from .cms_flashcard_editor import create_card
    from .cms_practice_editor import create_item, update_item
    result = {}

    def apply(job):
        if job.checkpoint.get("complete"):
            result.update(reconcile_learning(job))
            return
        raw = artifact_bytes(job.artifact)
        if job.kind == "learning_import":
            _, entries = parse_bundle(raw, lock_references=True)
            created = []
            for entry in entries:
                kind, data = entry["kind"], entry["creation"]
                args = (job.actor_id, job.session_id)
                if kind == "quiz":
                    item = create_quiz(*args, data, uuid.uuid4())
                    replace_questions(*args, item.pk, revision_etag(item), {"questions": entry["questions"]}, uuid.uuid4())
                elif kind == "flashcard":
                    item = create_card(*args, data, uuid.uuid4())
                else:
                    item = create_item(*args, kind, data, uuid.uuid4())
                    update_item(*args, kind, item.pk, revision_etag(item), {"prompt": data["prompt"],
                        "explanation": data["explanation"], "choices": entry["choices"]}, uuid.uuid4())
                created.append({"kind": kind, "resource_id": item.pk})
            result.update(items=len(created), created=created)
            _complete(job, dict(result))
            return
        manifest = _json(raw)
        if set(manifest) != {"schema_version", "items"} or manifest["schema_version"] != MANIFEST_SCHEMA:
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        items = [{**row, "etag": '"' + row["etag"] + '"'} for row in manifest["items"]]
        items = selection_items(items)
        exported = _export_document(_selected_rows(items))
        actor = User.objects.get(pk=job.actor_id)
        if job.output_artifact_id:
            output = AdminArtifact.objects.select_for_update().get(pk=job.output_artifact_id)
            if (output.kind != "learning_export_json" or output.domain != "learning" or output.owner_id != actor.pk
                    or output.resource_version != str(job.pk) or output.sha256 != hashlib.sha256(exported).hexdigest()
                    or output.state != "quarantine" or output.expires_at <= timezone.now()):
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        else:
            output = _artifact(actor, uuid.uuid5(job.pk, "learning-output"), exported, "learning_export", job.pk)
            output.save(force_insert=True)
            job.output_artifact = output
            AdminAuditEvent.objects.create(actor=actor, action="learning.transfer_prepared", outcome="success",
                target_key=str(output.pk), reason="LEARNING_TRANSFER", request_id=uuid.uuid4())
        _effect_authority(job)
        job.checkpoint = {"output_prepared": True, "sha256": output.sha256, "size": output.size}
        result.update(items=len(items), artifact_id=str(output.pk))

    checkpoint_job(job_id, token, apply)
    job = AdminJob.objects.get(pk=job_id)
    if job.checkpoint.get("complete"):
        return dict(result)

    def publish_output(current):
        manifest = _json(artifact_bytes(current.artifact))
        items = selection_items([{**row, "etag": '"' + row["etag"] + '"'} for row in manifest["items"]])
        raw = _export_document(_selected_rows(items))
        output = AdminArtifact.objects.select_for_update().get(pk=current.output_artifact_id)
        if (output.state != "quarantine" or output.sha256 != hashlib.sha256(raw).hexdigest()
                or output.size != len(raw) or output.expires_at <= timezone.now()):
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        _store(output, raw)
        _effect_authority(current)
        output.state, output.validation_code = "ready", "LEARNING_AUTHORING"
        output.version += 1
        output.save(update_fields=["state", "validation_code", "version"])
        _complete(current, dict(result))

    checkpoint_job(job_id, token, publish_output)
    return result


def reconcile_learning(job):
    checkpoint = job.checkpoint
    result = checkpoint.get("result")
    if (checkpoint.get("complete") is not True or type(result) is not dict
            or checkpoint.get("input_sha256") != job.artifact.sha256
            or type(result.get("items")) is not int or not 1 <= result["items"] <= MAX_ITEMS):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    if job.kind == "learning_import":
        created = result.get("created")
        if type(created) is not list or len(created) != result["items"]:
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        for row in created:
            if (type(row) is not dict or set(row) != {"kind", "resource_id"} or type(row["kind"]) is not str or row["kind"] not in KINDS
                    or type(row["resource_id"]) is not int or not KINDS[row["kind"]].objects.filter(pk=row["resource_id"]).exists()):
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    else:
        output = job.output_artifact
        if (output is None or str(output.pk) != result.get("artifact_id")
                or output.kind != "learning_export_json" or output.resource_version != str(job.pk)
                or output.sha256 != checkpoint.get("sha256") or output.size != checkpoint.get("size")
                or output.state not in {"ready", "revoked", "expired"}):
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        artifact_bytes(output)
    return result
