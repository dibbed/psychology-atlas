"""Private claim-level source locators for four learning authoring families.

This is append-only editorial provenance: it never changes canonical learning,
learner history, source rights, scientific review or public publication.
"""
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from rest_framework.response import Response

from .cms_content import digest
from .cms_governance_models import GovernanceRecord
from .cms_learning_evidence_models import LearningEvidenceRevision, LearningEvidenceSource
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_public_rights import registered_scopes, scope_visible
from .cms_sessions import current_session
from .cms_sources import require_impact_scope, source_impact, source_snapshot
from .cms_source_models import SourceState
from .cms_views import AdminAPIView, expected_version, payload
from .models import (
    CognitiveDistortionPracticeItem, Concept, DailyChallenge, Disorder, Flashcard,
    QuizAttempt, QuizQuestion, SourceReference, StudyActivity, UserFlashcardProgress,
    lock_brain_curation,
)

KIND_MODELS = {
    "quiz-question": (QuizQuestion, "explanation"),
    "flashcard": (Flashcard, "back"),
    "daily": (DailyChallenge, "explanation"),
    "distortions": (CognitiveDistortionPracticeItem, "explanation"),
}
MAX_SOURCES = 10


def _target(kind, pk, *, write=False):
    if kind not in KIND_MODELS:
        raise CMSFailure("NOT_FOUND", 404)
    model, field = KIND_MODELS[kind]
    queryset = model.objects.select_for_update() if write else model.objects
    item = queryset.filter(pk=pk).first()
    if item is None:
        raise CMSFailure("NOT_FOUND", 404)
    return item, field


def _editable(kind, item):
    owner = item.quiz if kind == "quiz-question" else item
    if (owner.archived_at is not None or owner.is_active or owner.seed_managed):
        raise CMSFailure("LEARNING_EVIDENCE_LOCKED", 409)
    if kind == "quiz-question":
        if (QuizAttempt.objects.filter(quiz=owner).exists()
                or StudyActivity.objects.filter(quiz=owner).exists()):
            raise CMSFailure("LEARNING_EVIDENCE_LOCKED", 409)
    elif kind == "flashcard":
        if (UserFlashcardProgress.objects.filter(flashcard=owner).exists()
                or StudyActivity.objects.filter(flashcard=owner).exists()):
            raise CMSFailure("LEARNING_EVIDENCE_LOCKED", 409)
    elif owner.attempts.exists():
        raise CMSFailure("LEARNING_EVIDENCE_LOCKED", 409)


CLAIM_CONTEXT_VERSION = "claim-context-v2"


def _claim_context(kind, item):
    """Fingerprint the claim, answer key, and live dependency semantics."""
    if kind == "quiz-question":
        parent = item.quiz
        content = {
            "prompt": item.prompt, "explanation": item.explanation,
            "is_active": item.is_active, "quiz_id": item.quiz_id,
            "quiz_disorder_id": parent.disorder_id, "quiz_title": parent.title,
        }
        concept_ids = set()
        disorder_ids = {parent.disorder_id} if parent.disorder_id else set()
    elif kind == "flashcard":
        content = {key: getattr(item, key) for key in (
            "front", "back", "hint", "difficulty", "concept_id", "disorder_id")}
        concept_ids = {item.concept_id} if item.concept_id else set()
        disorder_ids = {item.disorder_id} if item.disorder_id else set()
    elif kind == "daily":
        content = {key: getattr(item, key) for key in (
            "prompt", "explanation", "concept_id", "disorder_id")}
        concept_ids = {item.concept_id} if item.concept_id else set()
        disorder_ids = {item.disorder_id} if item.disorder_id else set()
    else:
        content = {key: getattr(item, key) for key in (
            "prompt", "explanation", "target_concept_id", "difficulty")}
        concept_ids = {item.target_concept_id}
        disorder_ids = set()

    if kind in {"quiz-question", "daily", "distortions"}:
        fields = ("id", "text", "is_correct", "is_active", "sort_order")
        if kind == "distortions":
            fields += ("concept_id",)
        content["choices"] = list(item.choices.order_by("sort_order", "pk").values(*fields))
        if kind == "distortions":
            concept_ids.update(choice["concept_id"] for choice in content["choices"])

    def dependencies(model, ids, fields, resource_type):
        rows = list(model.objects.filter(pk__in=ids).order_by("pk").values(*fields))
        for row in rows:
            row["public_metadata_visible"] = scope_visible(resource_type, row["id"])
        return rows

    document = {
        "schema": CLAIM_CONTEXT_VERSION, "kind": kind, "id": item.pk,
        "content": content,
        "dependencies": {
            "concept": dependencies(Concept, {pk for pk in concept_ids if pk},
                                    ("id", "is_active", "subtype"), "concept"),
            "disorder": dependencies(Disorder, {pk for pk in disorder_ids if pk},
                                     ("id", "is_active"), "disorder"),
        },
    }
    return hashlib.sha256(json.dumps(
        document, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), cls=DjangoJSONEncoder,
    ).encode("utf-8")).hexdigest()


def _source_context_digest(source):
    rights = list(GovernanceRecord.objects.filter(
        kind="rights", resource_type="source_reference", resource_id=source.pk,
    ).order_by("pk").values(
        "id", "status", "version", "material", "intended_use",
        "resource_version", "current_revision_id",
    ))
    return digest({"source": source_snapshot(source), "rights": rights})


def _restricted_rights(source):
    return any(
        kind == "source_reference" and pk == source.pk
        and not scope_visible("source_reference", source.pk, material, intended_use)
        for kind, pk, material, intended_use in registered_scopes()
    )


def _latest(kind, pk):
    return (LearningEvidenceRevision.objects.filter(kind=kind, target_pk=pk)
            .order_by("-sequence").prefetch_related("links__source").first())


def _state(kind, item, field, revision, *, context_digest=None, source_cache=None):
    current_digest = context_digest if context_digest is not None else _claim_context(kind, item)
    seq = revision.sequence if revision else 0
    links = list(revision.links.all()) if revision else []
    rows = []
    parts = [kind, str(item.pk), current_digest, str(seq),
             revision.fingerprint_version if revision else CLAIM_CONTEXT_VERSION]
    for link in links:
        source = link.source
        if source_cache is not None and source.pk in source_cache:
            source_state, source_digest, rights_restricted = source_cache[source.pk]
        else:
            source_state = source_snapshot(source)
            source_digest = _source_context_digest(source)
            rights_restricted = _restricted_rights(source)
            if source_cache is not None:
                source_cache[source.pk] = (source_state, source_digest, rights_restricted)
        stale = (revision.fingerprint_version != CLAIM_CONTEXT_VERSION or
                 link.source_digest != source_digest or
                 revision.content_digest != current_digest)
        reason = ("SOURCE_ARCHIVED" if source_state["archived"] or source_state["deleted"]
                  else "RIGHTS_RESTRICTED" if rights_restricted
                  else "SOURCE_OR_CONTEXT_CHANGED" if stale else None)
        rows.append({
            "source_id": source.pk,
            "source_title": source.title if not reason else None,
            "locator": None if reason in ("SOURCE_ARCHIVED", "RIGHTS_RESTRICTED") else link.locator,
            "source_verification_status": (source.verification_status or "unknown") if not reason else "restricted",
            "status": ("restricted" if reason in ("SOURCE_ARCHIVED", "RIGHTS_RESTRICTED")
                       else "stale" if stale else "linked"),
            "reason": reason,
        })
        parts.extend((str(source.pk), source_digest, link.locator, str(rights_restricted)))
    token = int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:13], 16)
    return {"kind": kind, "item_id": item.pk, "revision": seq,
            "status": ("unlinked" if not rows else
                       "requires_review" if any(row["status"] != "linked" for row in rows)
                       else "source_attached_unreviewed"),
            "links": rows, "scientific_review": "unreviewed",
            "publication_available": False, "canonical_write": 0,
            "learner_write": 0, "content_digest": current_digest,
            "fingerprint_version": CLAIM_CONTEXT_VERSION}, token


class LearningEvidenceView(AdminAPIView):
    capability = "cms_learning_view"

    def get(self, request, kind, item_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_learning_view")
            require(request.user, "cms_source_view")
            item, field = _target(kind, item_id)
            revision = _latest(kind, item_id)
            if revision is not None:
                for link in revision.links.select_related("source"):
                    require_impact_scope(request.user, source_impact(link.source))
            result, etag = _state(kind, item, field, revision)
            response = Response(result)
            response["ETag"] = f'"{etag}"'
            return response

    def post(self, request, kind, item_id):
        data = payload(request, {"sources", "change_reason"})
        sources = data.get("sources")
        change_reason = data.get("change_reason", "")
        if type(change_reason) is not str or len(change_reason) > 500:
            raise CMSFailure("INVALID_FIELDS", 400)
        if type(sources) is not list or len(sources) > MAX_SOURCES:
            raise CMSFailure("INVALID_SOURCES", 400)
        unique = set()
        for source in sources:
            if (type(source) is not dict or set(source) != {"source_id", "locator"}
                    or type(source["source_id"]) is not int or source["source_id"] < 1
                    or source["source_id"] in unique
                    or type(source["locator"]) is not str
                    or not 1 <= len(source["locator"].strip()) <= 500):
                raise CMSFailure("INVALID_SOURCES", 400)
            unique.add(source["source_id"])
        with policy_lock():
            current_session(request.cms_session.pk, request.user)
            for cap in ("cms_learning_view", "cms_learning_edit", "cms_source_view"):
                require(request.user, cap)
            item, field = _target(kind, item_id, write=True)
            _editable(kind, item)
            if sources and not getattr(item, field).strip():
                raise CMSFailure("EXPLANATION_REQUIRED", 409)
            lock_brain_curation(connection.alias)
            old = _latest(kind, item_id)
            _, etag = _state(kind, item, field, old)
            if expected_version(request) != etag:
                raise CMSFailure("STALE_REVISION", 412)
            selected = list(SourceReference.objects.select_for_update()
                            .filter(pk__in=unique).order_by("pk"))
            for source in selected:
                require_impact_scope(request.user, source_impact(source))
            if len(selected) != len(unique) or SourceState.objects.filter(
                    source_pk__in=unique, archived=True).exists() or SourceState.objects.filter(
                    source_pk__in=unique, deleted=True).exists():
                raise CMSFailure("INVALID_SOURCE", 409)
            if any(_restricted_rights(source) for source in selected):
                raise CMSFailure("RIGHTS_RESTRICTED", 409)
            context_digest = _claim_context(kind, item)
            locators = {row["source_id"]: row["locator"].strip() for row in sources}
            source_digests = {source.pk: _source_context_digest(source) for source in selected}
            old_links = {link.source_id: link for link in old.links.all()} if old else {}
            if (old and old.fingerprint_version == CLAIM_CONTEXT_VERSION
                    and old.content_digest == context_digest
                    and set(old_links) == set(locators)
                    and all(old_links[pk].locator == locator and
                            old_links[pk].source_digest == source_digests[pk]
                            for pk, locator in locators.items())):
                result, fresh = _state(kind, item, field, old)
                response = Response(result)
                response["ETag"] = f'"{fresh}"'
                return response
            removed = set(old_links) - set(locators)
            if removed and not change_reason.strip():
                raise CMSFailure("CHANGE_REASON_REQUIRED", 400)
            next_sequence = old.sequence + 1 if old else 1
            revision = LearningEvidenceRevision.objects.create(
                kind=kind, target_pk=item_id, sequence=next_sequence,
                content_digest=context_digest, fingerprint_version=CLAIM_CONTEXT_VERSION,
                change_reason=change_reason.strip() or "EVIDENCE_RECHECK",
                actor=request.user,
            )
            for source in selected:
                LearningEvidenceSource.objects.create(
                    revision=revision, source=source, locator=locators[source.pk],
                    source_digest=source_digests[source.pk],
                )
            AdminAuditEvent.objects.create(
                actor=request.user, outcome="success", action="learning.evidence_revised",
                target_kind="learning-evidence", target_id=item_id,
                request_id=self.request_id, reason="CONTENT_UPDATE",
                diff=["source"],
            )
            result, fresh = _state(kind, item, field, revision)
            response = Response(result)
            response["ETag"] = f'"{fresh}"'
            return response
