"""Read-only, owner-scoped orchestration for the Study Today screen."""

from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db.models import Case, F, IntegerField, OuterRef, Q, Subquery, Sum, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from . import models
from .learning import (
    available_flashcards, challenge_attempt_for_today, due_flashcard_progress,
    new_flashcards, today_challenge,
)
from .recommendation_views import assemble_recommendations
from .recommendations_v2 import _summary_current, resumable_case_attempts
from .study_scheduler import CANONICAL_EVIDENCE_KINDS, _block_queryset
from .study_sessions import block_action_href, get_current_session, serialize_session


DISPLAY_LIMIT = 20


def _schedule_stale(plan):
    return bool(plan.generation_version and not _summary_current(plan))


def _study_clock(user, now):
    saved = models.UserStudySettings.objects.filter(user=user).values(
        "study_timezone", "default_daily_minutes",
    ).first()
    name = saved["study_timezone"] if saved else settings.TIME_ZONE
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        name = settings.TIME_ZONE
        zone = ZoneInfo(name)
    daily_limit = (
        saved["default_daily_minutes"] if saved else
        models.UserStudySettings._meta.get_field("default_daily_minutes").get_default()
    )
    return name, zone, now.astimezone(zone).date(), daily_limit


def _actionable_target_filter(local_date, challenge_available):
    """SQL counterpart of the established target-runnable checks for exact counts."""
    kind = models.StudyBlock.Kind
    no_target = Q(block_kind__in=[kind.FLASHCARD_REVIEW, kind.NOTES_REVIEW])
    optional_challenge = (
        Q(block_kind=kind.DAILY_CHALLENGE_OPTIONAL, scheduled_date=local_date)
        if challenge_available else Q(pk__in=[])
    )
    simple = (
        Q(block_kind__in=[kind.CONCEPT_REVIEW, kind.DISTORTION_PRACTICE], concept__is_active=True)
        | Q(block_kind=kind.DISORDER_REVIEW, disorder__is_active=True)
        | Q(block_kind=kind.THEORY_READING, theory__is_active=True)
        | Q(block_kind=kind.PSYCHOLOGIST_READING, psychologist__is_active=True)
        | Q(block_kind=kind.TIMELINE_REVIEW, timeline_event__is_active=True)
        | Q(block_kind=kind.THERAPY_READING, therapy__is_active=True, therapy__family__is_active=True)
        | (Q(block_kind=kind.QUIZ_PRACTICE, quiz__is_active=True)
           & (Q(quiz__disorder__isnull=True) | Q(quiz__disorder__is_active=True)))
    )
    runnable_case = (
        Q(block_kind=kind.CASE_PRACTICE, clinical_case__is_active=True,
          clinical_case__current_revision__status=models.CaseRevision.Status.PUBLISHED,
          clinical_case__current_revision__case_id=F("clinical_case_id"),
          clinical_case__current_revision__entry_step__is_active=True,
          clinical_case__current_revision__entry_step__case_id=F("clinical_case_id"),
          clinical_case__current_revision__entry_step__revision_id=F("clinical_case__current_revision_id"))
        & (Q(clinical_case__current_revision__primary_disorder__isnull=True)
           | Q(clinical_case__current_revision__primary_disorder__is_active=True))
    )
    return no_target | optional_challenge | simple | runnable_case


def _block_rows(user, local_date, challenge_available):
    return (
        _block_queryset().filter(
            plan__user=user, plan__status=models.StudyPlan.Status.ACTIVE,
            status__in=[models.StudyBlock.Status.PENDING, models.StudyBlock.Status.IN_PROGRESS],
        ).filter(_actionable_target_filter(local_date, challenge_available))
        .annotate(scope_priority=Case(
            When(scope__plan_id=F("plan_id"), then=F("scope__priority")),
            output_field=IntegerField(),
        ))
        .order_by(F("scope_priority").desc(nulls_last=True), "scheduled_date", "sequence", "plan_id", "id")
    )


def _block_item(block):
    return {
        "id": block.id,
        "plan_id": block.plan_id,
        "block_kind": block.block_kind,
        "status": block.status,
        "scheduled_date": block.scheduled_date.isoformat(),
        "sequence": block.sequence,
        "estimated_minutes": block.estimated_minutes,
        "snapshot_title": block.snapshot_title,
        "scope_priority": block.scope_priority,
        "action_href": block_action_href(block),
        "target_active": True,
        "evidence_required": block.block_kind in CANONICAL_EVIDENCE_KINDS,
        "can_start_session": True,
    }


def _limited_block_list(queryset):
    total = queryset.count()
    items = [_block_item(block) for block in queryset[:DISPLAY_LIMIT]]
    return {"total": total, "items": items, "truncated": total > len(items)}


def _plan_list(user, local_date):
    active = models.StudyPlan.objects.filter(user=user, status=models.StudyPlan.Status.ACTIVE)
    availability = models.StudyPlanAvailability.objects.filter(
        plan_id=OuterRef("pk"), weekday=local_date.weekday(),
    ).order_by().values("available_minutes")[:1]
    total = active.count()
    rows = active.annotate(
        today_available=Coalesce(Subquery(availability), 0),
    ).order_by("id")[:DISPLAY_LIMIT]
    items = [{
        "id": plan.id,
        "name": plan.name,
        "plan_kind": plan.plan_kind,
        "target_date": plan.target_date.isoformat() if plan.target_date else None,
        "days_remaining": (plan.target_date - local_date).days if plan.target_date else None,
        "generation_version": plan.generation_version,
        "schedule_stale": _schedule_stale(plan),
        "today_available_minutes": plan.today_available,
    } for plan in rows]
    return {"total": total, "items": items, "truncated": total > len(items)}


def _capacity(user, local_date, daily_limit):
    configured = models.StudyPlanAvailability.objects.filter(
        plan__user=user, plan__status=models.StudyPlan.Status.ACTIVE,
        weekday=local_date.weekday(),
    ).aggregate(total=Sum("available_minutes"))["total"] or 0
    available = min(daily_limit, configured)
    block_minutes = models.StudyBlock.objects.filter(
        plan__user=user, plan__status=models.StudyPlan.Status.ACTIVE,
        scheduled_date=local_date,
        status__in=[
            models.StudyBlock.Status.PENDING, models.StudyBlock.Status.IN_PROGRESS,
            models.StudyBlock.Status.COMPLETED,
        ],
    ).aggregate(
        scheduled=Sum("estimated_minutes"),
        completed=Sum("estimated_minutes", filter=Q(status=models.StudyBlock.Status.COMPLETED)),
    )
    scheduled = block_minutes["scheduled"] or 0
    completed = block_minutes["completed"] or 0
    return {
        "available_minutes": available,
        "scheduled_minutes": scheduled,
        "completed_minutes": completed,
        "remaining_minutes": max(available - completed, 0),
        "over_capacity_minutes": max(scheduled - available, 0),
    }


def _review(user, now, local_date, zone):
    visible = available_flashcards()
    due = due_flashcard_progress(user, now, visible)
    midnight = datetime.combine(local_date, time.min, tzinfo=zone)
    return {
        "due": due.count(),
        "overdue": due.filter(due_at__lt=midnight).count(),
        "new": new_flashcards(user, visible).count(),
    }


def _action(kind, reason_code, target_type, target_id, href, label, *,
            plan_id=None, block_id=None, recommendation_key=None, can_start_session=False):
    return {
        "kind": kind,
        "reason_code": reason_code,
        "target": {"type": target_type, "id": target_id},
        "plan_id": plan_id,
        "block_id": block_id,
        "recommendation_key": recommendation_key,
        "can_start_session": can_start_session,
        "action": {"href": href, "label": label},
    }


def _next_action(user, session, session_payload, case_attempt, overdue, today,
                 review, challenge, capacity, recommendations, plans):
    if session is not None:
        block = session_payload["primary_block"]
        reason = "session_in_progress" if block and block["action_href"] else "session_focus_unavailable"
        return _action("resume_session", reason, "study_session", session.id,
                       f"/study/session/{session.id}", "ادامه جلسه مطالعه",
                       plan_id=session.plan_id, block_id=session.primary_block_id)
    if case_attempt is not None:
        return _action("resume_case", "case_in_progress", "clinical_case", case_attempt.case_id,
                       f"/cases/{case_attempt.case.slug}", "ادامه تمرین مورد")
    for kind, reason, listing in (
        ("overdue_block", "block_overdue", overdue),
        ("today_block", "block_due_today", today),
    ):
        if listing["items"]:
            block = listing["items"][0]
            return _action(kind, reason, "study_block", block["id"],
                           block["action_href"], "شروع فعالیت",
                           plan_id=block["plan_id"], block_id=block["id"],
                           can_start_session=True)
    if review["due"]:
        return _action("srs_review", "srs_overdue" if review["overdue"] else "srs_due",
                       "review_queue", None, "/flashcards", "مرور فلش‌کارت‌ها")
    if (challenge["available"] and not challenge["completed"]
            and capacity["remaining_minutes"] > 0
            and capacity["available_minutes"] > capacity["scheduled_minutes"]):
        return _action("daily_challenge", "challenge_available", "daily_challenge", None,
                       "/study#daily-challenge", "چالش روزانه")
    if recommendations["items"]:
        rec = recommendations["items"][0]
        return _action("recommendation", "recommendation_v2", rec["target"]["type"],
                       rec["target"]["id"], rec["action"]["href"], rec["action"]["label"],
                       recommendation_key=rec["key"])
    if not models.StudyPlan.objects.filter(user=user).exists():
        return _action("onboarding", "create_plan", "none", None,
                       "/study/plans/new", "ساخت برنامه مطالعه")
    if plans["total"] == 0:
        return _action("onboarding", "review_plans", "none", None,
                       "/study/plans", "بازبینی برنامه‌ها")
    pending = next((plan for plan in models.StudyPlan.objects.filter(
        user=user, status=models.StudyPlan.Status.ACTIVE,
    ).only(
        "id", "generation_version", "generation_fingerprint", "last_generated_at",
        "last_generation_summary",
    ).order_by("id").iterator(chunk_size=200)
        if plan.generation_version == 0 or _schedule_stale(plan)), None)
    if pending is not None:
        return _action("onboarding", "prepare_schedule", "study_plan", pending.id,
                       f"/study/plans/{pending.id}", "آماده‌سازی زمان‌بندی", plan_id=pending.id)
    if review["new"]:
        return _action("onboarding", "srs_new", "review_queue", None,
                       "/flashcards", "شروع فلش‌کارت‌های جدید")
    return _action("onboarding", "review_plans", "none", None,
                   "/study/plans", "بازبینی برنامه‌ها")


def build_today(user, now):
    """Assemble factual state without creating or updating any row."""
    name, zone, local_date, daily_limit = _study_clock(user, now)
    app_date = timezone.localtime(now).date()
    challenge_attempt = challenge_attempt_for_today(user, app_date)
    challenge_available = today_challenge(app_date) is not None
    challenge = {
        "challenge_date": app_date.isoformat(),
        "available": challenge_available,
        "completed": challenge_attempt is not None,
        "action": (
            {"href": "/study#daily-challenge", "label": "چالش روزانه"}
            if challenge_available and challenge_attempt is None else None
        ),
    }
    plans = _plan_list(user, local_date)
    capacity = _capacity(user, local_date, daily_limit)
    actionable = _block_rows(user, local_date, challenge_available and challenge_attempt is None)
    overdue = _limited_block_list(actionable.filter(scheduled_date__lt=local_date))
    today = _limited_block_list(actionable.filter(scheduled_date=local_date))
    review = _review(user, now, local_date, zone)
    session = get_current_session(user)
    session_payload = serialize_session(user, session, as_of=now) if session is not None else None
    case_attempt = resumable_case_attempts(user, now).first() if session is None else None
    recommendations = assemble_recommendations(user, now, local_date=local_date)
    return {
        "version": "v1",
        "as_of": now.isoformat(),
        "local_date": local_date.isoformat(),
        "timezone": name,
        "capacity": capacity,
        "active_session": session_payload,
        "review": review,
        "active_plans": plans,
        "today_blocks": today,
        "overdue_blocks": overdue,
        "daily_challenge": challenge,
        "next_action": _next_action(user, session, session_payload, case_attempt, overdue, today,
                                    review, challenge, capacity, recommendations, plans),
        "recommendations": recommendations,
    }
