"""P13 bounded private Daily Challenge and Distortion Practice editors.

Answer keys and old attempts remain immutable. No public activation before P16.
"""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.response import Response

from .cms_case_editor import revision_etag
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sessions import current_session
from .cms_views import AdminAPIView, expected_version, page, payload
from .models import (
    Concept, Disorder, DailyChallenge, DailyChallengeChoice,
    CognitiveDistortionPracticeItem, CognitiveDistortionPracticeChoice,
)

KINDS = {
    "daily": (DailyChallenge, DailyChallengeChoice),
    "distortions": (CognitiveDistortionPracticeItem, CognitiveDistortionPracticeChoice),
}
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _types(kind):
    if kind not in KINDS:
        raise CMSFailure("NOT_FOUND", 404)
    return KINDS[kind]


def _validate_creation(kind, data):
    fields = ({"prompt", "explanation", "concept_id", "disorder_id"} if kind == "daily" else
              {"slug", "prompt", "explanation", "difficulty", "target_concept_id"})
    if type(data) is not dict or set(data) != fields:
        raise CMSFailure("INVALID_FIELDS", 400)
    for field in ("prompt", "explanation"):
        if type(data[field]) is not str or len(data[field]) > 20000 or (
            field == "prompt" and not data[field].strip()
        ):
            raise CMSFailure("INVALID_FIELDS", 400)
    if kind == "daily":
        for field, model in (("concept_id", Concept), ("disorder_id", Disorder)):
            identifier = data[field]
            if identifier is not None and (type(identifier) is not int or identifier < 1
                or not model.objects.filter(pk=identifier, is_active=True).exists()):
                raise CMSFailure("INVALID_REFERENCE", 400)
    else:
        if (type(data["slug"]) is not str or not _SLUG.fullmatch(data["slug"]) or
                len(data["slug"]) > 180 or data["difficulty"] not in
                CognitiveDistortionPracticeItem.Difficulty.values):
            raise CMSFailure("INVALID_FIELDS", 400)
        if (type(data["target_concept_id"]) is not int or
                not Concept.objects.filter(pk=data["target_concept_id"], is_active=True,
                    subtype=Concept.Subtype.COGNITIVE_DISTORTION).exists()):
            raise CMSFailure("INVALID_REFERENCE", 400)


def _validate_edit(kind, data, item):
    if type(data) is not dict or set(data) != {"prompt", "explanation", "choices"}:
        raise CMSFailure("INVALID_FIELDS", 400)
    for field in ("prompt", "explanation"):
        if type(data[field]) is not str or len(data[field]) > 20000 or (
            field == "prompt" and not data[field].strip()
        ):
            raise CMSFailure("INVALID_FIELDS", 400)
    choices = data["choices"]
    if type(choices) is not list or not 2 <= len(choices) <= 10:
        raise CMSFailure("INVALID_CHOICES", 400)
    ids = set()
    correct_count = 0
    for row in choices:
        fields = {"text", "is_correct"} if kind == "daily" else {"concept_id", "text", "is_correct"}
        if type(row) is not dict or set(row) != fields:
            raise CMSFailure("INVALID_CHOICES", 400)
        if (type(row["text"]) is not str or not row["text"].strip() or
                len(row["text"]) > (20000 if kind == "daily" else 300) or
                type(row["is_correct"]) is not bool):
            raise CMSFailure("INVALID_CHOICES", 400)
        correct_count += row["is_correct"]
        if kind == "distortions":
            ident = row["concept_id"]
            if (type(ident) is not int or ident < 1 or ident in ids or
                    not Concept.objects.filter(pk=ident, is_active=True,
                        subtype=Concept.Subtype.COGNITIVE_DISTORTION).exists()):
                raise CMSFailure("INVALID_REFERENCE", 400)
            ids.add(ident)
            if row["is_correct"] and ident != item.target_concept_id:
                raise CMSFailure("CORRECT_CONCEPT_MISMATCH", 400)
    if correct_count != 1:
        raise CMSFailure("ANSWER_KEY_INVALID", 400)
    if kind == "distortions" and item.target_concept_id not in ids:
        raise CMSFailure("TARGET_CONCEPT_MISSING", 400)
    return choices


def _read(actor, kind, identifier):
    require(actor, "cms_learning_view")
    model, _ = _types(kind)
    item = model.objects.select_for_update().filter(pk=identifier).first()
    if item is None:
        raise CMSFailure("NOT_FOUND", 404)
    return item


def _snapshot(kind, item):
    rows = list(item.choices.order_by("sort_order", "pk"))
    if len(rows) > 10:
        raise CMSFailure("PREVIEW_LIMIT", 400)
    choices = [{
        "id": row.pk, "text": row.text, "is_correct": row.is_correct,
        "is_active": row.is_active,
        **({"concept_id": row.concept_id} if kind == "distortions" else {}),
    } for row in rows]
    active = [c for c in choices if c["is_active"]]
    issues = []
    if not item.prompt.strip():
        issues.append("PROMPT_MISSING")
    if len(active) < 2 or sum(c["is_correct"] for c in active) != 1:
        issues.append("ANSWER_KEY_INVALID")
    if kind == "distortions" and (not any(c["is_correct"] and
        c["concept_id"] == item.target_concept_id for c in active)):
        issues.append("CORRECT_CONCEPT_MISMATCH")
    return choices, issues


def create_item(actor_id, session_id, kind, data, request_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_learning_create")
        require(actor, "cms_learning_view")
        model, _ = _types(kind)
        _validate_creation(kind, data)
        if kind == "distortions" and model.objects.filter(slug=data["slug"]).exists():
            raise CMSFailure("PRACTICE_SLUG_EXISTS", 409)
        item = model.objects.create(**data, is_active=False, seed_managed=False)
        AdminAuditEvent.objects.create(actor=actor, outcome="success",
            action="practice.draft_created", target_kind="learning-practice",
            target_id=item.pk, request_id=request_id, reason="DRAFT_CREATION",
            diff=[],
        )
        return item


def update_item(actor_id, session_id, kind, identifier, expected, data, request_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_learning_edit")
        item = _read(actor, kind, identifier)
        if item.archived_at is not None or item.is_active or item.seed_managed or item.attempts.exists():
            raise CMSFailure("PRACTICE_HISTORY_OR_PUBLIC", 409)
        if revision_etag(item) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        choices = _validate_edit(kind, data, item)
        item.choices.all().delete()
        choice_model = _types(kind)[1]
        for index, choice in enumerate(choices):
            kw = ({"challenge": item} if kind == "daily" else {"item": item})
            choice_model.objects.create(**kw, **choice, sort_order=index, is_active=True)
        item.prompt = data["prompt"]
        item.explanation = data["explanation"]
        item.updated_at = max(timezone.now(), item.updated_at + timedelta(microseconds=1))
        item.save(update_fields=["prompt", "explanation", "updated_at"])
        AdminAuditEvent.objects.create(actor=actor, outcome="success",
            action="practice.draft_updated", target_kind="learning-practice",
            target_id=item.pk, request_id=request_id, reason="CONTENT_UPDATE",
            diff=[],
        )
        return item


def _result(kind, item):
    choices, issues = _snapshot(kind, item)
    return {
        "kind": kind, "item_id": item.pk, "prompt": item.prompt,
        "explanation": item.explanation, "choices": choices,
        "valid": not issues, "issues": issues, "archived_at": item.archived_at, "is_active": item.is_active,
        "seed_managed": item.seed_managed, "history_protected": item.attempts.exists(),
        "publication_available": False,
        **({"target_concept_id": item.target_concept_id, "slug": item.slug,
             "difficulty": item.difficulty} if kind == "distortions" else
            {"concept_id": item.concept_id, "disorder_id": item.disorder_id}),
    }


class PracticeCatalogView(AdminAPIView):
    capability = "cms_learning_view"

    def get(self, request, kind):
        with policy_lock():
            require(request.user, "cms_learning_view")
            model, _ = _types(kind)
            meta, rows = page(request, model.objects.order_by("-pk"))
            return Response({**meta, "kind": kind, "results": [{
                "item_id": row.pk, "prompt": row.prompt[:180],
                "archived_at": row.archived_at, "is_active": row.is_active, "seed_managed": row.seed_managed,
            } for row in rows]})

    def post(self, request, kind):
        model, _ = _types(kind)
        fields = ({"prompt", "explanation", "concept_id", "disorder_id"} if kind == "daily"
                  else {"slug", "prompt", "explanation", "difficulty", "target_concept_id"})
        data = payload(request, fields)
        item = create_item(request.user.pk, request.cms_session.pk, kind, data, self.request_id)
        response = Response({
            "kind": kind, "item_id": item.pk,
            "is_active": False, "publication_available": False,
        }, status=201)
        response["ETag"] = f'"{revision_etag(item)}"'
        return response


class PracticeDetailView(AdminAPIView):
    capability = "cms_learning_view"

    def get(self, request, kind, item_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            item = _read(request.user, kind, item_id)
            response = Response(_result(kind, item))
            response["ETag"] = f'"{revision_etag(item)}"'
            return response


class PracticeEditView(AdminAPIView):
    capability = "cms_learning_edit"

    def post(self, request, kind, item_id):
        data = payload(request, {"prompt", "explanation", "choices"})
        item = update_item(request.user.pk, request.cms_session.pk, kind, item_id,
                           expected_version(request), data, self.request_id)
        response = Response(_result(kind, item))
        response["ETag"] = f'"{revision_etag(item)}"'
        return response


class PracticeSimulationView(AdminAPIView):
    capability = "cms_learning_preview"

    def post(self, request, kind, item_id):
        data = payload(request, {"choice_id"})
        choice_id = data.get("choice_id")
        if type(choice_id) is not int or choice_id < 1:
            raise CMSFailure("INVALID_CHOICE", 400)
        with policy_lock():
            item = _read(request.user, kind, item_id)
            rows, issues = _snapshot(kind, item)
            if issues:
                raise CMSFailure("INVALID_PRACTICE", 409)
            choice = next((row for row in rows if row["id"] == choice_id and row["is_active"]), None)
            if choice is None:
                raise CMSFailure("INVALID_CHOICE", 400)
            return Response({
                "kind": kind, "item_id": item_id,
                "correct": bool(choice["is_correct"]), "explanation": item.explanation,
                "preview_only": True, "learner_activity_created": False,
                "publication_available": False,
            })
