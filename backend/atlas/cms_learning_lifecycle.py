"""Controlled archival without deleting content or rewriting learner history."""
import hashlib
import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.response import Response

from .cms_audit import attribution
from .cms_case_editor import revision_etag
from .cms_learning_lifecycle_models import LearningArchiveReceipt
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sessions import consume_step_up, current_session
from .cms_views import AdminAPIView, expected_version, payload
from .models import Quiz, Flashcard, DailyChallenge, CognitiveDistortionPracticeItem

KINDS = {"quiz": Quiz, "flashcard": Flashcard, "daily": DailyChallenge,
         "distortions": CognitiveDistortionPracticeItem}


def archive_learning(actor_id, session_id, kind, item_id, expected, data, request_id):
    if kind not in KINDS:
        raise CMSFailure("NOT_FOUND", 404)
    if (type(data) is not dict or set(data) != {"reason", "idempotency_key"}
            or data["reason"] != "CONTENT_ARCHIVE" or type(data["idempotency_key"]) is not str):
        raise CMSFailure("INVALID_FIELDS", 400)
    try:
        key = uuid.UUID(data["idempotency_key"])
    except ValueError:
        raise CMSFailure("INVALID_FIELDS", 400)
    bound = {"kind": kind, "etag": expected, **data}
    digest = hashlib.sha256(json.dumps({"target": item_id, **bound}, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_learning_view")
        require(actor, "cms_learning_archive")
        item = KINDS[kind].objects.select_for_update().filter(pk=item_id).first()
        if item is None:
            raise CMSFailure("NOT_FOUND", 404)
        # Row waits can outlive authentication or a permission grant.
        current_session(session_id, actor)
        require(actor, "cms_learning_view")
        require(actor, "cms_learning_archive")
        receipt = LearningArchiveReceipt.objects.filter(idempotency_key=key).first()
        if receipt:
            if receipt.request_digest != digest:
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            return item, receipt, False
        if revision_etag(item) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if item.archived_at is not None:
            raise CMSFailure("ALREADY_ARCHIVED", 409)
        consume_step_up(session_id, actor, "learning_archive", item_id, bound)
        now = timezone.now()
        item.archived_at, item.is_active = now, False
        item.updated_at = max(now, item.updated_at + timedelta(microseconds=1))
        item.save(update_fields=["archived_at", "is_active", "updated_at"])
        receipt = LearningArchiveReceipt.objects.create(
            kind=kind, resource_id=item_id, original_etag=expected, request_digest=digest,
            idempotency_key=key, archived_at=now, actor=actor, actor_ref=attribution(actor.pk),
        )
        AdminAuditEvent.objects.create(actor=actor, outcome="success", action="learning.archived",
            target_kind=kind, target_id=item_id, reason="CONTENT_ARCHIVE",
            request_id=request_id, diff=["is_active", "archived_at"])
        return item, receipt, True


class LearningArchiveView(AdminAPIView):
    capability = "cms_learning_archive"

    def post(self, request, kind, item_id):
        item, receipt, newly = archive_learning(request.user.pk, request.cms_session.pk,
            kind, item_id, expected_version(request),
            payload(request, {"reason", "idempotency_key"}), self.request_id)
        response = Response({"kind": kind, "resource_id": item.pk, "archived": True,
            "archived_at": receipt.archived_at, "receipt_id": receipt.pk,
            "newly_archived": newly, "publication_available": False})
        response["ETag"] = f'"{revision_etag(item)}"'
        return response
