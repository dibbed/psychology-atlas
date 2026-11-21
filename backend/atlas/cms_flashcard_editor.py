"""P13 Flashcard CMS: private inactive card authoring, preserve SRS state.

Existing active/seed-managed/in-use cards are immutable from this editor.
No user progress, schedule, activity or published content is modified.
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
from .models import Concept, Disorder, Flashcard, StudyActivity, UserFlashcardProgress

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _check_fields(data, creating):
    allowed = {"slug", "front", "back", "hint", "difficulty", "concept_id", "disorder_id"}
    if type(data) is not dict or not data or set(data) - allowed or (creating and set(data) != allowed) or (
        not creating and "slug" in data
    ):
        raise CMSFailure("INVALID_FIELDS", 400)
    if "slug" in data and (type(data["slug"]) is not str or len(data["slug"]) > 180 or not _SLUG.fullmatch(data["slug"])):
        raise CMSFailure("INVALID_FIELDS", 400)
    for name in ("front", "back", "hint"):
        if name in data and (type(data[name]) is not str or len(data[name]) > 20000 or (
            name != "hint" and not data[name].strip()
        )):
            raise CMSFailure("INVALID_FIELDS", 400)
    if "difficulty" in data and data["difficulty"] not in Flashcard.Difficulty.values:
        raise CMSFailure("INVALID_FIELDS", 400)
    for field in ("concept_id", "disorder_id"):
        if field in data and data[field] is not None and (
            type(data[field]) is not int or data[field] < 1
        ):
            raise CMSFailure("INVALID_FIELDS", 400)


def _check_references(data):
    if data.get("concept_id") is not None and not Concept.objects.filter(pk=data["concept_id"], is_active=True).exists():
        raise CMSFailure("INVALID_REFERENCE", 400)
    if data.get("disorder_id") is not None and not Disorder.objects.filter(pk=data["disorder_id"], is_active=True).exists():
        raise CMSFailure("INVALID_REFERENCE", 400)


def _view(user, card_id):
    require(user, "cms_learning_view")
    card = Flashcard.objects.select_for_update().filter(pk=card_id).first()
    if card is None:
        raise CMSFailure("NOT_FOUND", 404)
    return card


def _history_locked(card):
    return (UserFlashcardProgress.objects.filter(flashcard=card).exists()
            or StudyActivity.objects.filter(flashcard=card).exists())


def create_card(actor_id, session_id, data, request_id):
    _check_fields(data, creating=True)
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_learning_create")
        require(actor, "cms_learning_view")
        _check_references(data)
        if Flashcard.objects.filter(slug=data["slug"]).exists():
            raise CMSFailure("FLASHCARD_SLUG_EXISTS", 409)
        card = Flashcard.objects.create(
            **data, is_active=False, seed_managed=False,
        )
        AdminAuditEvent.objects.create(
            actor=actor, outcome="success", action="flashcard.draft_created",
            target_kind="flashcard", target_id=card.pk, request_id=request_id,
            reason="DRAFT_CREATION", diff=[],
        )
        return card


def update_card(actor_id, session_id, card_id, expected, data, request_id):
    _check_fields(data, creating=False)
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_learning_edit")
        card = _view(actor, card_id)
        if card.archived_at is not None or card.is_active or card.seed_managed or _history_locked(card):
            raise CMSFailure("FLASHCARD_IN_USE_OR_PUBLIC", 409)
        if revision_etag(card) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        _check_references(data)
        changed = []
        for field, value in data.items():
            if getattr(card, field) != value:
                setattr(card, field, value)
                changed.append(field)
        if changed:
            card.updated_at = max(timezone.now(), card.updated_at + timedelta(microseconds=1))
            card.save(update_fields=[*changed, "updated_at"])
            AdminAuditEvent.objects.create(
                actor=actor, outcome="success", action="flashcard.draft_updated",
                target_kind="flashcard", target_id=card.pk, request_id=request_id,
                reason="CONTENT_UPDATE", diff=[field.removesuffix("_id") for field in changed
                    if field in {"difficulty", "concept_id", "disorder_id"}],
            )
        return card


def _result(card):
    return {
        "flashcard_id": card.pk, "slug": card.slug, "front": card.front,
        "back": card.back, "hint": card.hint, "difficulty": card.difficulty,
        "concept_id": card.concept_id, "disorder_id": card.disorder_id,
        "archived_at": card.archived_at, "is_active": card.is_active, "seed_managed": card.seed_managed,
        "history_protected": _history_locked(card),
        "publication_available": False,
    }


class FlashcardCatalogView(AdminAPIView):
    capability = "cms_learning_view"

    def get(self, request):
        with policy_lock():
            require(request.user, "cms_learning_view")
            meta, rows = page(request, Flashcard.objects.order_by("-pk"))
            return Response({**meta, "results": [{
                "flashcard_id": card.pk, "slug": card.slug,
                "archived_at": card.archived_at, "is_active": card.is_active, "seed_managed": card.seed_managed,
            } for card in rows]})

    def post(self, request):
        data = payload(request, {"slug", "front", "back", "hint", "difficulty", "concept_id", "disorder_id"})
        card = create_card(request.user.pk, request.cms_session.pk, data, self.request_id)
        response = Response({
            "flashcard_id": card.pk, "is_active": False, "publication_available": False,
        }, status=201)
        response["ETag"] = f'"{revision_etag(card)}"'
        return response


class FlashcardDetailView(AdminAPIView):
    capability = "cms_learning_view"

    def get(self, request, card_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            card = _view(request.user, card_id)
            response = Response(_result(card))
            response["ETag"] = f'"{revision_etag(card)}"'
            return response


class FlashcardMetadataView(AdminAPIView):
    capability = "cms_learning_edit"

    def post(self, request, card_id):
        data = payload(request, {"front", "back", "hint", "difficulty", "concept_id", "disorder_id"})
        card = update_card(request.user.pk, request.cms_session.pk, card_id,
                           expected_version(request), data, self.request_id)
        response = Response(_result(card))
        response["ETag"] = f'"{revision_etag(card)}"'
        return response
