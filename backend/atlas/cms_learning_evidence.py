"""Private claim-level source locators for four learning authoring families.

This is append-only editorial provenance: it never changes canonical learning,
learner history, source rights, scientific review or public publication.
"""
import hashlib

from django.db import connection
from rest_framework.response import Response

from .cms_content import digest
from .cms_learning_evidence_models import LearningEvidenceRevision, LearningEvidenceSource
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_public_rights import registered_scopes, scope_visible
from .cms_sessions import current_session
from .cms_sources import require_impact_scope, source_impact, source_snapshot
from .cms_source_models import SourceState
from .cms_views import AdminAPIView, expected_version, payload
from .models import (
    CognitiveDistortionPracticeItem, DailyChallenge, Flashcard, QuizAttempt,
    QuizQuestion, SourceReference, StudyActivity, UserFlashcardProgress,
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


def _digest_text(item, field):
    value = getattr(item, field)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _latest(kind, pk):
    return (LearningEvidenceRevision.objects.filter(kind=kind, target_pk=pk)
            .order_by("-sequence").prefetch_related("links__source").first())


def _state(kind, item, field, revision):
    current_digest = _digest_text(item, field)
    seq = revision.sequence if revision else 0
    links = list(revision.links.all()) if revision else []
    rows = []
    parts = [kind, str(item.pk), current_digest, str(seq)]
    rights_scopes = registered_scopes()
    for link in links:
        source = link.source
        source_state = source_snapshot(source)
        source_digest = digest(source_state)
        rights_restricted = any(
            kind == "source_reference" and pk == source.pk
            and not scope_visible("source_reference", source.pk, material, intended_use)
            for kind, pk, material, intended_use in rights_scopes
        )
        stale = (link.source_digest != source_digest or
                 revision.content_digest != current_digest)
        reason = ("SOURCE_ARCHIVED" if source_state["archived"] or source_state["deleted"]
                  else "RIGHTS_RESTRICTED" if rights_restricted
                  else "SOURCE_OR_EXPLANATION_CHANGED" if stale else None)
        rows.append({
            "source_id": source.pk,
            "source_title": source.title if not reason else None,
            "locator": None if reason in ("SOURCE_ARCHIVED", "RIGHTS_RESTRICTED") else link.locator,
            "source_verification_status": (source.verification_status or "unknown") if not reason else "restricted",
            "status": ("restricted" if reason in ("SOURCE_ARCHIVED", "RIGHTS_RESTRICTED")
                       else "stale" if stale else "linked"),
            "reason": reason,
        })
        parts.extend((str(source.pk), source_digest, link.locator))
    token = int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:13], 16)
    return {"kind": kind, "item_id": item.pk, "revision": seq,
            "status": ("unlinked" if not rows else
                       "requires_review" if any(row["status"] != "linked" for row in rows)
                       else "source_attached_unreviewed"),
            "links": rows, "scientific_review": "unreviewed",
            "publication_available": False, "canonical_write": 0,
            "learner_write": 0, "content_digest": current_digest}, token


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
        data = payload(request, {"sources"})
        sources = data.get("sources")
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
            next_sequence = old.sequence + 1 if old else 1
            revision = LearningEvidenceRevision.objects.create(
                kind=kind, target_pk=item_id, sequence=next_sequence,
                content_digest=_digest_text(item, field), actor=request.user,
            )
            locators = {row["source_id"]: row["locator"].strip() for row in sources}
            for source in selected:
                LearningEvidenceSource.objects.create(
                    revision=revision, source=source, locator=locators[source.pk],
                    source_digest=digest(source_snapshot(source)),
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
