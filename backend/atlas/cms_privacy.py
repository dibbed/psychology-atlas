"""Closed, purpose-bound personal reads. No credentials or administrative impersonation."""
import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import BigIntegerField, BinaryField, CharField, Sum, TextField, Value
from django.db.models.functions import Cast, Coalesce, Length
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.parsers import BaseParser
from rest_framework.response import Response

from . import models
from .cms_artifacts import bounded_json
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sessions import consume_step_up, current_session
from .cms_views import AdminAPIView, payload


PAGE_SIZE = 20
MAX_TEXT_UNITS = 65536
SCOPES = {
    "disorder_notes": (models.UserNote, "user_id", ("id", "disorder_id", "body", "created_at", "updated_at")),
    "concept_notes": (models.ConceptNote, "user_id", ("id", "concept_id", "body", "created_at", "updated_at")),
    "therapy_notes": (models.TherapyNote, "user_id", ("id", "therapy_id", "body", "created_at", "updated_at")),
    "disorder_progress": (models.UserProgress, "user_id", ("id", "disorder_id", "status", "progress_percent", "last_viewed_at", "completed_at")),
    "concept_progress": (models.UserConceptProgress, "user_id", ("id", "concept_id", "status", "progress_percent", "last_viewed_at", "last_reviewed_at", "completed_at")),
    "flashcard_srs": (models.UserFlashcardProgress, "user_id", ("id", "flashcard_id", "state", "due_at", "interval_days", "ease_factor", "repetitions", "lapses", "last_rating", "last_reviewed_at")),
    "quiz_attempts": (models.QuizAttempt, "user_id", ("id", "quiz_id", "status", "score", "correct_count", "total_questions", "created_at", "completed_at")),
    "quiz_answers": (models.QuizAttemptAnswer, "attempt__user_id", ("id", "attempt_id", "question_id", "selected_choice_id", "is_correct", "answered_at")),
    "case_attempts": (models.CaseAttempt, "user_id", ("id", "case_id", "revision_id", "current_step_id", "status", "state_version", "score", "max_score", "created_at", "completed_at")),
    "case_events": (models.CaseAttemptEvent, "attempt__user_id", ("id", "attempt_id", "step_id", "event_type", "selected_choice_id", "awarded_score", "max_score", "created_at")),
    "daily_attempts": (models.DailyChallengeAttempt, "user_id", ("id", "challenge_id", "activity_date", "selected_choice_id", "is_correct", "created_at")),
    "distortion_attempts": (models.CognitiveDistortionPracticeAttempt, "user_id", ("id", "item_id", "selected_choice_id", "is_correct", "created_at")),
    "study_plans": (models.StudyPlan, "user_id", ("id", "name", "plan_kind", "status", "start_date", "target_date", "notes", "generation_version", "created_at", "updated_at")),
    "study_scopes": (models.StudyPlanScope, "plan__user_id", ("id", "plan_id", "priority", "include_practice", "disorder_id", "concept_id", "therapy_id", "theory_id", "psychologist_id", "timeline_event_id", "quiz_id", "clinical_case_id")),
    "study_blocks": (models.StudyBlock, "plan__user_id", ("id", "plan_id", "scope_id", "block_kind", "status", "scheduled_date", "estimated_minutes", "locked_by_user", "started_at", "completed_at", "skipped_at")),
    "study_sessions": (models.StudySession, "user_id", ("id", "plan_id", "primary_block_id", "status", "planned_minutes", "started_at", "completed_at", "abandoned_at", "actual_seconds")),
    "activities": (models.StudyActivity, "user_id", ("id", "activity_type", "disorder_id", "concept_id", "quiz_id", "clinical_case_id", "flashcard_id", "therapy_id", "occurred_at")),
    "recommendation_feedback": (models.RecommendationFeedback, "user_id", ("id", "recommendation_type", "target_type", "target_id", "value", "created_at", "suppressed_until")),
    "disorder_bookmarks": (models.Bookmark, "user_id", ("id", "disorder_id", "created_at")),
    "concept_bookmarks": (models.ConceptBookmark, "user_id", ("id", "concept_id", "created_at")),
    "therapy_bookmarks": (models.TherapyBookmark, "user_id", ("id", "therapy_id", "created_at")),
    "study_settings": (models.UserStudySettings, "user_id", ("id", "study_timezone", "default_daily_minutes", "default_session_minutes", "week_starts_on", "updated_at")),
}
SCOPE_LABELS = {
    "disorder_notes": "یادداشت‌های اختلال", "concept_notes": "یادداشت‌های مفهوم", "therapy_notes": "یادداشت‌های رویکرد درمانی",
    "disorder_progress": "پیشرفت اختلال", "concept_progress": "پیشرفت مفهوم", "flashcard_srs": "مرور فاصله‌دار کارت‌ها",
    "quiz_attempts": "تلاش‌های آزمون آموزشی", "quiz_answers": "پاسخ‌های ثبت‌شدهٔ آزمون", "case_attempts": "تلاش‌های پروندهٔ آموزشی",
    "case_events": "رویدادهای تلاش پرونده", "daily_attempts": "تلاش‌های چالش روزانه", "distortion_attempts": "تلاش‌های تمرین شناختی",
    "study_plans": "برنامه‌های مطالعه", "study_scopes": "حوزه‌های برنامهٔ مطالعه", "study_blocks": "بلوک‌های مطالعه",
    "study_sessions": "نشست‌های مطالعه", "activities": "فعالیت‌های آموزشی", "recommendation_feedback": "بازخورد پیشنهادها",
    "disorder_bookmarks": "نشانک‌های اختلال", "concept_bookmarks": "نشانک‌های مفهوم", "therapy_bookmarks": "نشانک‌های رویکرد درمانی",
    "study_settings": "تنظیمات شخصی مطالعه",
}


class PrivacyParser(BaseParser):
    media_type = "application/json"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read(8193)
        if len(raw) > 8192:
            raise CMSFailure("INVALID_INPUT", 400)
        return bounded_json(raw)[1]


def read_request(data):
    if (type(data) is not dict or set(data) != {"purpose", "case_ref", "scope", "page"}
            or data["purpose"] != "SUPPORT_REQUEST" or type(data["scope"]) is not str or data["scope"] not in SCOPES
            or type(data["page"]) is not int or not 1 <= data["page"] <= 10000 or type(data["case_ref"]) is not str):
        raise CMSFailure("INVALID_INPUT", 400)
    try:
        reference = uuid.UUID(data["case_ref"])
    except ValueError:
        raise CMSFailure("INVALID_INPUT", 400)
    if str(reference) != data["case_ref"] or not reference.int:
        raise CMSFailure("INVALID_INPUT", 400)
    return data


def require_privacy(actor, capability):
    require(actor, "cms_user_view")
    require(actor, "cms_privacy_" + capability)


def text_units(rows, fields):
    expression = None
    for field in fields:
        if isinstance(rows.model._meta.get_field(field), (CharField, TextField)):
            source = Cast(field, BinaryField()) if connection.vendor == "sqlite" else field
            size = Coalesce(Cast(Length(source), BigIntegerField()), Value(0), output_field=BigIntegerField())
            expression = size if expression is None else expression + size
    if expression is None:
        return 0
    return rows.aggregate(total=Sum(expression))["total"] or 0


def read_private(actor, session_id, subject_id, data, request_id):
    data = read_request(data)
    with policy_lock() as policy:
        current_session(session_id, actor)
        require_privacy(actor, "sensitive_read")
        if not get_user_model().objects.filter(pk=subject_id).exists():
            raise CMSFailure("NOT_FOUND", 404)
        consume_step_up(session_id, actor, "privacy_read", subject_id, data)
        AdminAuditEvent.objects.create(actor=actor, action="privacy.read." + data["scope"], outcome="success", target_kind="user",
            target_id=subject_id, target_key=salted_hmac("cms-privacy-case-v1", data["case_ref"], algorithm="sha256").hexdigest(),
            reason="PRIVACY_SUPPORT", request_id=request_id, policy_version=policy.version)
        model, owner, fields = SCOPES[data["scope"]]
        rows = model.objects.filter(**{owner: subject_id}).order_by("pk")
        start = (data["page"] - 1) * PAGE_SIZE
        identifiers = list(rows.select_for_update(of=("self",)).values_list("pk", flat=True)[start:start + PAGE_SIZE])
        selected = rows.filter(pk__in=identifiers)
        if text_units(selected, fields) > MAX_TEXT_UNITS:
            raise CMSFailure("PRIVACY_LIMIT", 400)
        results = list(selected.values(*fields))
        from .cms_study_actions import add_operations
        add_operations(actor, data["scope"], selected, results)
        return {"subject_id": subject_id, "scope": data["scope"], "purpose": data["purpose"],
            "page": data["page"], "page_size": PAGE_SIZE, "count": rows.count(),
            "results": results, "as_of": timezone.now().isoformat()}


class PrivacyReadView(AdminAPIView):
    capability = "cms_privacy_sensitive_read"
    parser_classes = (PrivacyParser,)

    def post(self, request, user_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(read_private(request.user, request.cms_session.pk, user_id,
            payload(request, {"purpose", "case_ref", "scope", "page"}), self.request_id))


class PrivacySchemaView(AdminAPIView):
    capability = "cms_privacy_sensitive_read"

    def get(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require_privacy(request.user, "sensitive_read")
            return Response({"scopes": [{"key": key, "label": SCOPE_LABELS[key]} for key in SCOPES],
                "page_size": PAGE_SIZE, "max_page": 10000})
