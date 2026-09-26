from __future__ import annotations

import hashlib
import json
import time
import threading
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta
from zoneinfo import ZoneInfo

from django.db import OperationalError, connection, transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import models
from .learning import available_flashcards
from .study_planning import (
    SCOPE_TARGETS,
    StudyPlanningError,
    _active_scope_queryset,
    _locked_user_plan,
    _scope_target,
    _study_scope_queryset,
    _target_active,
    _target_title,
    get_user_plan,
    local_date_for_user,
    study_settings_for_user,
)


SCHEDULER_VERSION = "v082.1"
_GENERATION_MUTEX = threading.Lock()
GENERAL_PLAN_HORIZON_DAYS = 28
MAX_GENERATION_DAYS = 730
MAX_SCHEDULE_RANGE_DAYS = 366

DEFAULT_MINUTES = {
    models.StudyBlock.Kind.FLASHCARD_REVIEW: 20,
    models.StudyBlock.Kind.CONCEPT_REVIEW: 20,
    models.StudyBlock.Kind.DISORDER_REVIEW: 25,
    models.StudyBlock.Kind.THERAPY_READING: 20,
    models.StudyBlock.Kind.THEORY_READING: 25,
    models.StudyBlock.Kind.PSYCHOLOGIST_READING: 20,
    models.StudyBlock.Kind.TIMELINE_REVIEW: 15,
    models.StudyBlock.Kind.QUIZ_PRACTICE: 20,
    models.StudyBlock.Kind.CASE_PRACTICE: 30,
    models.StudyBlock.Kind.DISTORTION_PRACTICE: 12,
    models.StudyBlock.Kind.NOTES_REVIEW: 10,
    models.StudyBlock.Kind.DAILY_CHALLENGE_OPTIONAL: 10,
}

KIND_ORDER = {
    kind: index
    for index, kind in enumerate(
        [
            models.StudyBlock.Kind.FLASHCARD_REVIEW,
            models.StudyBlock.Kind.DISORDER_REVIEW,
            models.StudyBlock.Kind.CONCEPT_REVIEW,
            models.StudyBlock.Kind.THERAPY_READING,
            models.StudyBlock.Kind.THEORY_READING,
            models.StudyBlock.Kind.PSYCHOLOGIST_READING,
            models.StudyBlock.Kind.TIMELINE_REVIEW,
            models.StudyBlock.Kind.QUIZ_PRACTICE,
            models.StudyBlock.Kind.CASE_PRACTICE,
            models.StudyBlock.Kind.DISTORTION_PRACTICE,
            models.StudyBlock.Kind.NOTES_REVIEW,
            models.StudyBlock.Kind.DAILY_CHALLENGE_OPTIONAL,
        ]
    )
}

TARGET_FIELD_BY_SCOPE = {
    "disorder": ("disorder", models.StudyBlock.Kind.DISORDER_REVIEW),
    "concept": ("concept", models.StudyBlock.Kind.CONCEPT_REVIEW),
    "therapy": ("therapy", models.StudyBlock.Kind.THERAPY_READING),
    "theory": ("theory", models.StudyBlock.Kind.THEORY_READING),
    "psychologist": ("psychologist", models.StudyBlock.Kind.PSYCHOLOGIST_READING),
    "timeline_event": ("timeline_event", models.StudyBlock.Kind.TIMELINE_REVIEW),
    "quiz": ("quiz", models.StudyBlock.Kind.QUIZ_PRACTICE),
    "clinical_case": ("clinical_case", models.StudyBlock.Kind.CASE_PRACTICE),
}

READING_KINDS = {
    models.StudyBlock.Kind.CONCEPT_REVIEW,
    models.StudyBlock.Kind.DISORDER_REVIEW,
    models.StudyBlock.Kind.THERAPY_READING,
    models.StudyBlock.Kind.THEORY_READING,
    models.StudyBlock.Kind.PSYCHOLOGIST_READING,
    models.StudyBlock.Kind.TIMELINE_REVIEW,
    models.StudyBlock.Kind.NOTES_REVIEW,
}

CANONICAL_EVIDENCE_KINDS = {
    models.StudyBlock.Kind.FLASHCARD_REVIEW,
    models.StudyBlock.Kind.QUIZ_PRACTICE,
    models.StudyBlock.Kind.CASE_PRACTICE,
    models.StudyBlock.Kind.DISTORTION_PRACTICE,
}

_SQLITE_LOCK_RETRY_DELAYS = (0.02, 0.05, 0.10, 0.20, 0.40, 0.80, 1.60)


@dataclass(frozen=True)
class Candidate:
    key: str
    block_kind: str
    estimated_minutes: int
    priority: int
    urgency: int
    earliest_date: date
    scope_id: int | None
    target_field: str | None
    target_id: int | None
    title: str
    subtitle: str
    metadata: dict

    def sort_key(self):
        return (
            self.urgency,
            -self.priority,
            self.earliest_date.isoformat(),
            KIND_ORDER.get(self.block_kind, 999),
            self.key,
        )


def _date_value(value, *, field):
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "تاریخ نامعتبر است.",
            errors={field: "invalid_date"},
        )
    parsed = parse_date(value)
    if parsed is None:
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "تاریخ باید با قالب YYYY-MM-DD ارسال شود.",
            errors={field: "invalid_date"},
        )
    return parsed


def _generation_window(plan, today):
    start = max(plan.start_date, today)
    if plan.plan_kind == models.StudyPlan.Kind.EXAM:
        if plan.target_date is None:
            raise StudyPlanningError(
                "study_plan_invalid_date_range",
                "برنامه امتحان تاریخ هدف ندارد.",
                status_code=409,
            )
        if plan.target_date < today:
            raise StudyPlanningError(
                "study_plan_invalid_date_range",
                "تاریخ هدف این برنامه گذشته است و زمان‌بندی جدید ساخته نمی‌شود.",
                status_code=409,
            )
        end = plan.target_date
    else:
        end = start + timedelta(days=GENERAL_PLAN_HORIZON_DAYS - 1)

    span = (end - start).days + 1
    if span > MAX_GENERATION_DAYS:
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            f"بازه زمان‌بندی در این نسخه حداکثر {MAX_GENERATION_DAYS} روز است.",
            status_code=409,
            errors={"schedule_days": "too_large"},
        )
    return start, end


def _block_queryset():
    return models.StudyBlock.objects.select_related(
        "plan",
        "scope",
        "disorder",
        "concept",
        "therapy",
        "therapy__family",
        "theory",
        "psychologist",
        "timeline_event",
        "quiz",
        "quiz__disorder",
        "clinical_case",
        "clinical_case__current_revision",
        "clinical_case__current_revision__primary_disorder",
        "clinical_case__current_revision__entry_step",
    )


def _block_target(block):
    for field in (
        "disorder",
        "concept",
        "therapy",
        "theory",
        "psychologist",
        "timeline_event",
        "quiz",
        "clinical_case",
    ):
        target = getattr(block, field, None)
        if target is not None:
            target_type = "clinical_case" if field == "clinical_case" else field
            return target_type, target
    return None, None


def _block_target_active(block):
    target_type, target = _block_target(block)
    if target is None:
        return True
    return _target_active(target_type, target)


def _block_href(block):
    target_type, target = _block_target(block)
    if block.block_kind == models.StudyBlock.Kind.FLASHCARD_REVIEW:
        return "/flashcards"
    if block.block_kind == models.StudyBlock.Kind.DISTORTION_PRACTICE:
        return "/cognitive-distortions"
    if target is None:
        return "/study"
    routes = {
        "disorder": "disorders",
        "concept": "concepts",
        "therapy": "therapies",
        "theory": "theories",
        "psychologist": "psychologists",
        "timeline_event": "timeline",
        "quiz": "quizzes",
        "clinical_case": "cases",
    }
    return f"/{routes[target_type]}/{target.slug}"


def study_block_payload(block):
    target_type, target = _block_target(block)
    return {
        "id": block.id,
        "plan_id": block.plan_id,
        "scope_id": block.scope_id,
        "block_kind": block.block_kind,
        "status": block.status,
        "origin": block.origin,
        "scheduled_date": block.scheduled_date.isoformat(),
        "sequence": block.sequence,
        "estimated_minutes": block.estimated_minutes,
        "generation_version": block.generation_version,
        "locked_by_user": block.locked_by_user,
        "snapshot_title": block.snapshot_title,
        "snapshot_subtitle": block.snapshot_subtitle,
        "metadata": block.metadata,
        "target_type": target_type,
        "target_slug": target.slug if target is not None else None,
        "target_active": _block_target_active(block),
        "action_href": _block_href(block),
        "evidence_required": block.block_kind in CANONICAL_EVIDENCE_KINDS,
        "started_at": block.started_at.isoformat() if block.started_at else None,
        "completed_at": block.completed_at.isoformat() if block.completed_at else None,
        "skipped_at": block.skipped_at.isoformat() if block.skipped_at else None,
        "created_at": block.created_at.isoformat(),
        "updated_at": block.updated_at.isoformat(),
    }


def get_user_block(user, block_id):
    if not isinstance(block_id, int) or isinstance(block_id, bool) or block_id <= 0:
        raise StudyPlanningError("study_block_not_found", "بلوک مطالعه پیدا نشد.", status_code=404)
    block = _block_queryset().filter(plan__user=user, pk=block_id).first()
    if block is None:
        raise StudyPlanningError("study_block_not_found", "بلوک مطالعه پیدا نشد.", status_code=404)
    return block


def _lock_user_block_and_plan(user, block_id):
    if not isinstance(block_id, int) or isinstance(block_id, bool) or block_id <= 0:
        raise StudyPlanningError("study_block_not_found", "بلوک مطالعه پیدا نشد.", status_code=404)
    locator = (
        models.StudyBlock.objects.filter(plan__user=user, pk=block_id)
        .values("id", "plan_id")
        .first()
    )
    if locator is None:
        raise StudyPlanningError("study_block_not_found", "بلوک مطالعه پیدا نشد.", status_code=404)

    plan = (
        models.StudyPlan.objects.select_for_update()
        .filter(user=user, pk=locator["plan_id"])
        .first()
    )
    if plan is None:
        raise StudyPlanningError("study_block_not_found", "بلوک مطالعه پیدا نشد.", status_code=404)
    block = (
        _block_queryset()
        .select_for_update()
        .filter(plan=plan, pk=locator["id"])
        .first()
    )
    if block is None:
        raise StudyPlanningError("study_block_not_found", "بلوک مطالعه پیدا نشد.", status_code=404)
    return block, plan


def _candidate(
    *,
    block_kind,
    priority,
    urgency,
    earliest_date,
    scope,
    target_field=None,
    target=None,
    title,
    subtitle,
    metadata=None,
    pass_key="coverage",
):
    target_key = f"{target_field}:{target.pk}" if target is not None else "none"
    key = f"{block_kind}:{target_key}:{pass_key}"
    payload = dict(metadata or {})
    payload["scheduler_version"] = SCHEDULER_VERSION
    payload["pass"] = pass_key
    payload["candidate_key"] = key
    return Candidate(
        key=key,
        block_kind=block_kind,
        estimated_minutes=DEFAULT_MINUTES[block_kind],
        priority=priority,
        urgency=urgency,
        earliest_date=earliest_date,
        scope_id=scope.id if scope is not None else None,
        target_field=target_field,
        target_id=target.pk if target is not None else None,
        title=title,
        subtitle=subtitle,
        metadata=payload,
    )


def _build_candidates(plan, scopes, start, end):
    candidates = {}
    unavailable_scopes = []
    concept_ids = set()
    disorder_ids = set()
    practice_disorder_scopes = {}
    distortion_scopes = {}

    span_days = (end - start).days + 1
    midpoint = start + timedelta(days=max(1, (span_days - 1) // 2))
    final_third = start + timedelta(days=max(1, ((span_days - 1) * 2) // 3))

    def add(item, *, prefer=False):
        existing = candidates.get(item.key)
        if existing is None or prefer:
            candidates[item.key] = item

    for scope in scopes:
        target_type, target = _scope_target(scope)
        if target is None or not _target_active(target_type, target):
            unavailable_scopes.append(
                {
                    "scope_id": scope.id,
                    "target_type": target_type,
                    "target_slug": getattr(target, "slug", None),
                    "title": _target_title(target_type, target) if target is not None else "",
                }
            )
            continue

        field, kind = TARGET_FIELD_BY_SCOPE[target_type]
        title = _target_title(target_type, target)
        add(
            _candidate(
                block_kind=kind,
                priority=scope.priority,
                urgency=10,
                earliest_date=start,
                scope=scope,
                target_field=field,
                target=target,
                title=title,
                subtitle="پوشش اصلی محدوده برنامه",
                pass_key="coverage",
            ),
            prefer=True,
        )

        if scope.priority >= 3 and span_days >= 7:
            add(
                _candidate(
                    block_kind=kind,
                    priority=scope.priority,
                    urgency=20,
                    earliest_date=midpoint,
                    scope=scope,
                    target_field=field,
                    target=target,
                    title=title,
                    subtitle="مرور دوباره در همین برنامه",
                    pass_key="review",
                )
            )
        if scope.priority == 5 and span_days >= 14:
            add(
                _candidate(
                    block_kind=kind,
                    priority=scope.priority,
                    urgency=25,
                    earliest_date=final_third,
                    scope=scope,
                    target_field=field,
                    target=target,
                    title=title,
                    subtitle="مرور تقویتی با اولویت بالا",
                    pass_key="reinforcement",
                )
            )

        if target_type == "concept":
            concept_ids.add(target.id)
            if (
                scope.include_practice
                and target.subtype == models.Concept.Subtype.COGNITIVE_DISTORTION
            ):
                distortion_scopes[target.id] = scope
        elif target_type == "disorder":
            disorder_ids.add(target.id)
            if scope.include_practice:
                practice_disorder_scopes[target.id] = scope

    if practice_disorder_scopes:
        quizzes = (
            models.Quiz.objects.filter(
                is_active=True,
                disorder_id__in=practice_disorder_scopes,
                disorder__is_active=True,
            )
            .select_related("disorder")
            .order_by("slug", "id")
        )
        for quiz in quizzes:
            scope = practice_disorder_scopes[quiz.disorder_id]
            add(
                _candidate(
                    block_kind=models.StudyBlock.Kind.QUIZ_PRACTICE,
                    priority=scope.priority,
                    urgency=15,
                    earliest_date=final_third if span_days >= 3 else start,
                    scope=scope,
                    target_field="quiz",
                    target=quiz,
                    title=quiz.title,
                    subtitle="تمرین صریح مرتبط با اختلال انتخاب‌شده",
                    metadata={"expanded_from": "disorder"},
                    pass_key="coverage",
                )
            )

        cases = (
            _active_scope_queryset("clinical_case")
            .filter(current_revision__primary_disorder_id__in=practice_disorder_scopes)
            .order_by("slug", "id")
        )
        for clinical_case in cases:
            disorder_id = clinical_case.current_revision.primary_disorder_id
            scope = practice_disorder_scopes[disorder_id]
            add(
                _candidate(
                    block_kind=models.StudyBlock.Kind.CASE_PRACTICE,
                    priority=scope.priority,
                    urgency=16,
                    earliest_date=final_third if span_days >= 3 else start,
                    scope=scope,
                    target_field="clinical_case",
                    target=clinical_case,
                    title=_target_title("clinical_case", clinical_case),
                    subtitle="کیس آموزشی صریح مرتبط با اختلال انتخاب‌شده",
                    metadata={"expanded_from": "disorder"},
                    pass_key="coverage",
                )
            )

    if distortion_scopes:
        active_distortion_concepts = set(
            models.CognitiveDistortionPracticeItem.objects.filter(
                is_active=True,
                target_concept_id__in=distortion_scopes,
                target_concept__is_active=True,
            ).values_list("target_concept_id", flat=True)
        )
        concept_map = {
            concept.id: concept
            for concept in models.Concept.objects.filter(id__in=active_distortion_concepts)
        }
        for concept_id in sorted(active_distortion_concepts):
            scope = distortion_scopes[concept_id]
            concept = concept_map[concept_id]
            add(
                _candidate(
                    block_kind=models.StudyBlock.Kind.DISTORTION_PRACTICE,
                    priority=scope.priority,
                    urgency=17,
                    earliest_date=midpoint if span_days >= 3 else start,
                    scope=scope,
                    target_field="concept",
                    target=concept,
                    title=concept.name_fa or concept.name_en,
                    subtitle="تمرین آموزشی تحریف شناختی",
                    pass_key="practice",
                )
            )

    if concept_ids or disorder_ids:
        relevant_cards = available_flashcards().filter(
            Q(concept_id__in=concept_ids) | Q(disorder_id__in=disorder_ids)
        )
        relevant_ids = relevant_cards.values_list("id", flat=True)
        has_cards = relevant_cards.exists()
        due_pressure = False
        if has_cards:
            due_pressure = models.UserFlashcardProgress.objects.filter(
                user=plan.user,
                flashcard_id__in=relevant_ids,
                due_at__lte=timezone.now(),
            ).exists()

        if has_cards:
            scope_priorities = [
                scope.priority
                for scope in scopes
                if (
                    (scope.concept_id and scope.concept_id in concept_ids)
                    or (scope.disorder_id and scope.disorder_id in disorder_ids)
                )
            ]
            priority = max(scope_priorities or [3])
            concept_slugs = sorted(
                scope.concept.slug
                for scope in scopes
                if scope.concept_id and scope.concept_id in concept_ids
            )
            disorder_slugs = sorted(
                scope.disorder.slug
                for scope in scopes
                if scope.disorder_id and scope.disorder_id in disorder_ids
            )
            week_start = start
            week_index = 0
            while week_start <= end:
                add(
                    _candidate(
                        block_kind=models.StudyBlock.Kind.FLASHCARD_REVIEW,
                        priority=priority,
                        urgency=0 if due_pressure and week_index == 0 else 30,
                        earliest_date=week_start,
                        scope=None,
                        title="مرور فلش‌کارت‌های محدوده برنامه",
                        subtitle="ظرفیت مرور؛ کارت‌های واقعی هنگام اجرا از SRS دریافت می‌شوند",
                        metadata={
                            "concept_slugs": concept_slugs,
                            "disorder_slugs": disorder_slugs,
                            "concept_ids": sorted(concept_ids),
                            "disorder_ids": sorted(disorder_ids),
                            "due_pressure_at_generation": bool(due_pressure and week_index == 0),
                        },
                        pass_key=f"week-{week_index}",
                    )
                )
                week_index += 1
                week_start += timedelta(days=7)

    return sorted(candidates.values(), key=lambda item: item.sort_key()), unavailable_scopes


def _candidate_fingerprint_payload(candidate):
    return {
        "key": candidate.key,
        "kind": candidate.block_kind,
        "minutes": candidate.estimated_minutes,
        "priority": candidate.priority,
        "urgency": candidate.urgency,
        "earliest_date": candidate.earliest_date.isoformat(),
        "scope_id": candidate.scope_id,
        "target_field": candidate.target_field,
        "target_id": candidate.target_id,
        "metadata": candidate.metadata,
    }


def _preserved_future_blocks(plan, today, end):
    return list(
        _block_queryset()
        .filter(plan=plan, scheduled_date__gte=today, scheduled_date__lte=end)
        .exclude(
            origin=models.StudyBlock.Origin.GENERATED,
            status=models.StudyBlock.Status.PENDING,
            locked_by_user=False,
        )
        .exclude(
            status__in=[
                models.StudyBlock.Status.SUPERSEDED,
                models.StudyBlock.Status.SKIPPED,
            ]
        )
        .order_by("scheduled_date", "sequence", "id")
    )


def _preserved_candidate_keys(plan, today):
    rows = (
        models.StudyBlock.objects.filter(
            plan=plan,
            origin=models.StudyBlock.Origin.GENERATED,
        )
        .exclude(status=models.StudyBlock.Status.SUPERSEDED)
        .exclude(
            status=models.StudyBlock.Status.PENDING,
            scheduled_date__gte=today,
            locked_by_user=False,
        )
        .values_list("metadata", flat=True)
    )
    keys = set()
    for metadata in rows:
        if not isinstance(metadata, dict):
            continue
        key = metadata.get("candidate_key")
        if isinstance(key, str) and key:
            keys.add(key)
    return keys


def _generation_fingerprint(plan, start, end, availability, candidates, preserved_blocks):
    payload = {
        "scheduler_version": SCHEDULER_VERSION,
        "local_date": start.isoformat(),
        "plan": {
            "kind": plan.plan_kind,
            "start_date": plan.start_date.isoformat(),
            "target_date": plan.target_date.isoformat() if plan.target_date else None,
        },
        "availability": [
            [row.weekday, row.available_minutes]
            for row in sorted(availability, key=lambda item: item.weekday)
        ],
        "candidates": [_candidate_fingerprint_payload(item) for item in candidates],
        "preserved": [
            [
                block.id,
                block.scheduled_date.isoformat(),
                block.sequence,
                block.estimated_minutes,
                block.status,
                block.origin,
                block.locked_by_user,
                block.updated_at.isoformat(),
            ]
            for block in preserved_blocks
            if block.origin != models.StudyBlock.Origin.GENERATED
        ],
        "window": [start.isoformat(), end.isoformat()],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _capacity_by_date(start, end, availability):
    minutes_by_weekday = {row.weekday: row.available_minutes for row in availability}
    capacity = {}
    cursor = start
    while cursor <= end:
        capacity[cursor] = minutes_by_weekday.get(cursor.weekday(), 0)
        cursor += timedelta(days=1)
    return capacity


def _allocate_candidates(candidates, *, start, end, capacity, preserved_blocks):
    used = {day: 0 for day in capacity}
    max_sequence = {day: -1 for day in capacity}
    for block in preserved_blocks:
        if block.status in {
            models.StudyBlock.Status.SKIPPED,
            models.StudyBlock.Status.SUPERSEDED,
        }:
            continue
        if block.scheduled_date in used:
            used[block.scheduled_date] += block.estimated_minutes
            max_sequence[block.scheduled_date] = max(
                max_sequence[block.scheduled_date],
                block.sequence,
            )

    remaining = list(candidates)
    scheduled = []
    cursor = start
    last_kind = None

    while cursor <= end and remaining:
        day_capacity = capacity.get(cursor, 0)
        remaining_minutes = max(0, day_capacity - used.get(cursor, 0))
        if remaining_minutes <= 0:
            cursor += timedelta(days=1)
            last_kind = None
            continue

        made_progress = True
        while remaining_minutes > 0 and made_progress:
            made_progress = False
            eligible_indexes = [
                index
                for index, item in enumerate(remaining)
                if item.earliest_date <= cursor and item.estimated_minutes <= remaining_minutes
            ]
            if not eligible_indexes:
                break

            chosen_index = eligible_indexes[0]
            if last_kind is not None:
                for index in eligible_indexes:
                    if remaining[index].block_kind != last_kind:
                        chosen_index = index
                        break

            item = remaining.pop(chosen_index)
            max_sequence[cursor] += 1
            scheduled.append((cursor, max_sequence[cursor], item))
            used[cursor] = used.get(cursor, 0) + item.estimated_minutes
            remaining_minutes -= item.estimated_minutes
            last_kind = item.block_kind
            made_progress = True

        cursor += timedelta(days=1)
        last_kind = None

    return scheduled, remaining, used


def _target_kwargs(candidate):
    if candidate.target_field is None or candidate.target_id is None:
        return {}
    return {f"{candidate.target_field}_id": candidate.target_id}


def _summary(
    *,
    plan,
    start,
    end,
    capacity,
    preserved_blocks,
    scheduled,
    backlog,
    unavailable_scopes,
    superseded_count,
    generation_version,
    no_op,
):
    total_capacity = sum(capacity.values())
    preserved_minutes = sum(
        block.estimated_minutes
        for block in preserved_blocks
        if block.scheduled_date in capacity
        and block.status not in {
            models.StudyBlock.Status.SKIPPED,
            models.StudyBlock.Status.SUPERSEDED,
        }
    )
    scheduled_minutes = sum(item.estimated_minutes for _, _, item in scheduled)
    backlog_minutes = sum(item.estimated_minutes for item in backlog)
    candidate_minutes = scheduled_minutes + backlog_minutes
    return {
        "scheduler_version": SCHEDULER_VERSION,
        "generation_version": generation_version,
        "no_op": no_op,
        "schedule_start": start.isoformat(),
        "schedule_end": end.isoformat(),
        "plan_target_date": plan.target_date.isoformat() if plan.target_date else None,
        "available_minutes": total_capacity,
        "preserved_minutes": preserved_minutes,
        "candidate_minutes": candidate_minutes,
        "scheduled_minutes": scheduled_minutes,
        "scheduled_blocks": len(scheduled),
        "preserved_blocks": len(preserved_blocks),
        "unscheduled_candidates": len(backlog),
        "capacity_shortfall_minutes": backlog_minutes,
        "superseded_blocks": superseded_count,
        "unavailable_scopes": unavailable_scopes,
        "backlog": [
            {
                "key": item.key,
                "block_kind": item.block_kind,
                "title": item.title,
                "estimated_minutes": item.estimated_minutes,
                "priority": item.priority,
                "earliest_date": item.earliest_date.isoformat(),
            }
            for item in backlog[:100]
        ],
    }


@transaction.atomic
def _generate_study_plan_once(user, plan_id):
    plan = _locked_user_plan(user, plan_id)
    if plan.status in {
        models.StudyPlan.Status.ARCHIVED,
        models.StudyPlan.Status.COMPLETED,
    }:
        raise StudyPlanningError(
            "study_plan_not_actionable",
            "این برنامه در وضعیت قابل زمان‌بندی نیست.",
            status_code=409,
        )

    today = local_date_for_user(user)
    start, end = _generation_window(plan, today)

    availability = list(
        plan.availability.select_for_update().order_by("weekday", "id")
    )
    if len(availability) != 7 or {row.weekday for row in availability} != set(range(7)):
        raise StudyPlanningError(
            "study_plan_no_availability",
            "ظرفیت هفت روز هفته کامل نیست.",
            status_code=409,
        )
    if not any(row.available_minutes > 0 for row in availability):
        raise StudyPlanningError(
            "study_plan_no_availability",
            "برای زمان‌بندی حداقل یک روز با ظرفیت مثبت لازم است.",
            status_code=409,
        )

    scopes = list(_study_scope_queryset().filter(plan=plan))
    if not scopes:
        raise StudyPlanningError(
            "study_plan_scope_invalid",
            "برای زمان‌بندی حداقل یک موضوع به برنامه اضافه کن.",
            status_code=409,
        )

    built_candidates, unavailable_scopes = _build_candidates(plan, scopes, start, end)
    preserved_keys = _preserved_candidate_keys(plan, today)
    candidates = [
        item for item in built_candidates
        if item.key not in preserved_keys
    ]
    preserved_blocks = _preserved_future_blocks(plan, today, end)
    fingerprint = _generation_fingerprint(
        plan,
        start,
        end,
        availability,
        candidates,
        preserved_blocks,
    )

    if plan.generation_version > 0 and plan.generation_fingerprint == fingerprint:
        summary = dict(plan.last_generation_summary or {})
        summary["no_op"] = True
        summary["generation_version"] = plan.generation_version
        return get_user_plan(user, plan.id), summary

    regenerable = models.StudyBlock.objects.filter(
        plan=plan,
        origin=models.StudyBlock.Origin.GENERATED,
        status=models.StudyBlock.Status.PENDING,
        scheduled_date__gte=today,
        locked_by_user=False,
    )
    superseded_count = regenerable.count()
    regenerable.update(status=models.StudyBlock.Status.SUPERSEDED)

    capacity = _capacity_by_date(start, end, availability)
    scheduled, backlog, _ = _allocate_candidates(
        candidates,
        start=start,
        end=end,
        capacity=capacity,
        preserved_blocks=preserved_blocks,
    )

    next_version = plan.generation_version + 1
    scope_by_id = {scope.id: scope for scope in scopes}
    blocks = [
        models.StudyBlock(
            plan=plan,
            scope=scope_by_id.get(item.scope_id),
            block_kind=item.block_kind,
            status=models.StudyBlock.Status.PENDING,
            origin=models.StudyBlock.Origin.GENERATED,
            scheduled_date=scheduled_date,
            sequence=sequence,
            estimated_minutes=item.estimated_minutes,
            generation_version=next_version,
            locked_by_user=False,
            snapshot_title=item.title,
            snapshot_subtitle=item.subtitle,
            metadata=item.metadata,
            **_target_kwargs(item),
        )
        for scheduled_date, sequence, item in scheduled
    ]
    for block in blocks:
        block.clean()
    if blocks:
        models.StudyBlock.objects.bulk_create(blocks)

    summary = _summary(
        plan=plan,
        start=start,
        end=end,
        capacity=capacity,
        preserved_blocks=preserved_blocks,
        scheduled=scheduled,
        backlog=backlog,
        unavailable_scopes=unavailable_scopes,
        superseded_count=superseded_count,
        generation_version=next_version,
        no_op=False,
    )

    plan.generation_version = next_version
    plan.generation_fingerprint = fingerprint
    plan.last_generation_summary = summary
    plan.last_generated_at = timezone.now()
    plan.save(
        update_fields=(
            "generation_version",
            "generation_fingerprint",
            "last_generation_summary",
            "last_generated_at",
            "updated_at",
        )
    )
    return get_user_plan(user, plan.id), summary


def generate_study_plan(user, plan_id):
    with _GENERATION_MUTEX:
        for retry_index in range(len(_SQLITE_LOCK_RETRY_DELAYS) + 1):
            try:
                return _generate_study_plan_once(user, plan_id)
            except OperationalError as exc:
                is_transient_sqlite_lock = (
                    connection.vendor == "sqlite" and "locked" in str(exc).lower()
                )
                if (
                    not is_transient_sqlite_lock
                    or retry_index >= len(_SQLITE_LOCK_RETRY_DELAYS)
                ):
                    raise
                time.sleep(_SQLITE_LOCK_RETRY_DELAYS[retry_index])


def _plan_schedule_range(plan, user, start_value=None, end_value=None):
    today = local_date_for_user(user)
    start = (
        _date_value(start_value, field="start")
        if start_value
        else max(plan.start_date, today - timedelta(days=7))
    )
    default_end = (
        plan.target_date
        if plan.plan_kind == models.StudyPlan.Kind.EXAM and plan.target_date
        else today + timedelta(days=GENERAL_PLAN_HORIZON_DAYS - 1)
    )
    end = _date_value(end_value, field="end") if end_value else default_end
    if end < start:
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "پایان بازه نمی‌تواند قبل از شروع باشد.",
            errors={"end": "before_start"},
        )
    truncated = False
    if (end - start).days + 1 > MAX_SCHEDULE_RANGE_DAYS:
        end = start + timedelta(days=MAX_SCHEDULE_RANGE_DAYS - 1)
        truncated = True
    return start, end, truncated


def get_study_plan_schedule(user, plan_id, *, start=None, end=None):
    plan = get_user_plan(user, plan_id)
    range_start, range_end, truncated = _plan_schedule_range(
        plan,
        user,
        start_value=start,
        end_value=end,
    )
    blocks = list(
        _block_queryset()
        .filter(
            plan=plan,
            scheduled_date__gte=range_start,
            scheduled_date__lte=range_end,
        )
        .exclude(status=models.StudyBlock.Status.SUPERSEDED)
        .order_by("scheduled_date", "sequence", "id")
    )

    today = local_date_for_user(user)
    active_statuses = {
        models.StudyBlock.Status.PENDING,
        models.StudyBlock.Status.IN_PROGRESS,
        models.StudyBlock.Status.COMPLETED,
    }
    scheduled_minutes = sum(
        block.estimated_minutes for block in blocks if block.status in active_statuses
    )
    completed_minutes = sum(
        block.estimated_minutes
        for block in blocks
        if block.status == models.StudyBlock.Status.COMPLETED
    )
    overdue_blocks = sum(
        1
        for block in blocks
        if block.status in {
            models.StudyBlock.Status.PENDING,
            models.StudyBlock.Status.IN_PROGRESS,
        }
        and block.scheduled_date < today
    )

    global_daily_minutes = study_settings_for_user(user).default_daily_minutes
    cross_plan_rows = (
        models.StudyBlock.objects.filter(
            plan__user=user,
            plan__status=models.StudyPlan.Status.ACTIVE,
            scheduled_date__gte=range_start,
            scheduled_date__lte=range_end,
        )
        .exclude(
            status__in=[
                models.StudyBlock.Status.SKIPPED,
                models.StudyBlock.Status.SUPERSEDED,
            ]
        )
        .values("scheduled_date")
        .annotate(total_minutes=Sum("estimated_minutes"))
        .order_by("scheduled_date")
    )
    overcapacity = [
        {
            "date": row["scheduled_date"].isoformat(),
            "scheduled_minutes": row["total_minutes"],
            "default_daily_minutes": global_daily_minutes,
        }
        for row in cross_plan_rows
        if row["total_minutes"] > global_daily_minutes
    ]

    by_date = {}
    for block in blocks:
        key = block.scheduled_date.isoformat()
        by_date.setdefault(key, []).append(study_block_payload(block))

    return {
        "plan_id": plan.id,
        "generation_version": plan.generation_version,
        "last_generated_at": plan.last_generated_at.isoformat()
        if plan.last_generated_at
        else None,
        "last_generation_summary": plan.last_generation_summary or {},
        "range": {
            "start": range_start.isoformat(),
            "end": range_end.isoformat(),
            "truncated": truncated,
        },
        "summary": {
            "block_count": len(blocks),
            "scheduled_minutes": scheduled_minutes,
            "completed_minutes": completed_minutes,
            "overdue_blocks": overdue_blocks,
            "cross_plan_overcapacity": overcapacity,
        },
        "days": [
            {"date": day, "blocks": day_blocks}
            for day, day_blocks in sorted(by_date.items())
        ],
    }


def _invalidate_generation(plan):
    if plan.generation_fingerprint:
        plan.generation_fingerprint = ""
        plan.save(update_fields=("generation_fingerprint", "updated_at"))


def _validate_actionable_plan(plan):
    if plan.status in {
        models.StudyPlan.Status.ARCHIVED,
        models.StudyPlan.Status.COMPLETED,
    }:
        raise StudyPlanningError(
            "study_block_not_actionable",
            "برنامه این بلوک در وضعیت قابل تغییر نیست.",
            status_code=409,
        )


def _validate_block_target(block):
    if not _block_target_active(block):
        raise StudyPlanningError(
            "study_block_target_inactive",
            "محتوای این بلوک دیگر فعال یا قابل اجرا نیست.",
            status_code=409,
        )


@transaction.atomic
def reschedule_study_block(user, block_id, payload):
    if not isinstance(payload, dict):
        raise StudyPlanningError(
            "study_block_not_actionable",
            "بدنه درخواست باید یک شیء JSON باشد.",
        )
    if set(payload) != {"scheduled_date"}:
        raise StudyPlanningError(
            "study_block_not_actionable",
            "برای جابه‌جایی فقط scheduled_date را ارسال کن.",
            errors={"fields": "invalid"},
        )

    block, plan = _lock_user_block_and_plan(user, block_id)
    _validate_actionable_plan(plan)
    if block.status != models.StudyBlock.Status.PENDING:
        raise StudyPlanningError(
            "study_block_not_actionable",
            "فقط بلوک pending قابل جابه‌جایی است.",
            status_code=409,
        )
    _validate_block_target(block)

    new_date = _date_value(payload["scheduled_date"], field="scheduled_date")
    today = local_date_for_user(user)
    if new_date < max(plan.start_date, today):
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "بلوک را نمی‌توان به قبل از امروز یا شروع برنامه منتقل کرد.",
            errors={"scheduled_date": "before_allowed_range"},
        )
    if plan.target_date is not None and new_date > plan.target_date:
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "بلوک را نمی‌توان بعد از تاریخ هدف برنامه منتقل کرد.",
            errors={"scheduled_date": "after_target_date"},
        )

    max_sequence = (
        models.StudyBlock.objects.filter(plan=plan, scheduled_date=new_date)
        .aggregate(value=Max("sequence"))
        .get("value")
    )
    block.scheduled_date = new_date
    block.sequence = (max_sequence if max_sequence is not None else -1) + 1
    block.locked_by_user = True
    block.save(
        update_fields=(
            "scheduled_date",
            "sequence",
            "locked_by_user",
            "updated_at",
        )
    )
    _invalidate_generation(plan)
    return _block_queryset().get(pk=block.pk)


@transaction.atomic
def unlock_study_block(user, block_id):
    block, plan = _lock_user_block_and_plan(user, block_id)
    _validate_actionable_plan(plan)
    if (
        block.status != models.StudyBlock.Status.PENDING
        or block.origin != models.StudyBlock.Origin.GENERATED
    ):
        raise StudyPlanningError(
            "study_block_not_actionable",
            "فقط بلوک generated و pending قابل آزاد کردن است.",
            status_code=409,
        )
    if not block.locked_by_user:
        return _block_queryset().get(pk=block.pk)
    block.locked_by_user = False
    block.save(update_fields=("locked_by_user", "updated_at"))
    _invalidate_generation(plan)
    return _block_queryset().get(pk=block.pk)


@transaction.atomic
def skip_study_block(user, block_id):
    block, plan = _lock_user_block_and_plan(user, block_id)
    _validate_actionable_plan(plan)
    if block.status == models.StudyBlock.Status.SKIPPED:
        return _block_queryset().get(pk=block.pk)
    if block.status != models.StudyBlock.Status.PENDING:
        raise StudyPlanningError(
            "study_block_not_actionable",
            "فقط بلوک pending قابل رد کردن است.",
            status_code=409,
        )
    block.status = models.StudyBlock.Status.SKIPPED
    block.skipped_at = timezone.now()
    block.save(update_fields=("status", "skipped_at", "updated_at"))
    _invalidate_generation(plan)
    return _block_queryset().get(pk=block.pk)


def _canonical_completion_evidence(block, user):
    settings_obj = study_settings_for_user(user)
    scheduled_midnight = datetime.combine(
        block.scheduled_date,
        datetime_time.min,
        tzinfo=ZoneInfo(settings_obj.study_timezone),
    )
    current_local_date = local_date_for_user(user)
    evidence_floor = (
        scheduled_midnight
        if block.scheduled_date <= current_local_date
        else block.created_at
    )
    since = max(block.started_at or block.created_at, evidence_floor)

    if block.block_kind == models.StudyBlock.Kind.QUIZ_PRACTICE:
        attempt = (
            models.QuizAttempt.objects.filter(
                user=user,
                quiz_id=block.quiz_id,
                status=models.QuizAttempt.Status.COMPLETED,
                completed_at__gte=since,
            )
            .order_by("-completed_at", "-id")
            .first()
        )
        return (
            {"kind": "quiz_attempt", "attempt_id": attempt.id}
            if attempt is not None
            else None
        )

    if block.block_kind == models.StudyBlock.Kind.CASE_PRACTICE:
        attempt = (
            models.CaseAttempt.objects.filter(
                user=user,
                case_id=block.clinical_case_id,
                status=models.CaseAttempt.Status.COMPLETED,
                completed_at__gte=since,
            )
            .order_by("-completed_at", "-id")
            .first()
        )
        return (
            {
                "kind": "case_attempt",
                "attempt_id": attempt.id,
                "revision_id": attempt.revision_id,
            }
            if attempt is not None
            else None
        )

    if block.block_kind == models.StudyBlock.Kind.DISTORTION_PRACTICE:
        attempt = (
            models.CognitiveDistortionPracticeAttempt.objects.filter(
                user=user,
                item__target_concept_id=block.concept_id,
                created_at__gte=since,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        return (
            {"kind": "distortion_practice_attempt", "attempt_id": attempt.id}
            if attempt is not None
            else None
        )

    if block.block_kind == models.StudyBlock.Kind.FLASHCARD_REVIEW:
        metadata = block.metadata if isinstance(block.metadata, dict) else {}
        concept_ids = [
            value
            for value in metadata.get("concept_ids", [])
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        disorder_ids = [
            value
            for value in metadata.get("disorder_ids", [])
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        activity = models.StudyActivity.objects.filter(
            user=user,
            activity_type=models.StudyActivity.Kind.FLASHCARD_REVIEW,
            occurred_at__gte=since,
        )
        if concept_ids or disorder_ids:
            activity = activity.filter(
                Q(flashcard__concept_id__in=concept_ids)
                | Q(flashcard__disorder_id__in=disorder_ids)
            )
        row = activity.order_by("-occurred_at", "-id").first()
        return (
            {"kind": "flashcard_review", "activity_id": row.id}
            if row is not None
            else None
        )

    return {"kind": "user_confirmation"}


@transaction.atomic
def complete_study_block(user, block_id):
    block, plan = _lock_user_block_and_plan(user, block_id)
    _validate_actionable_plan(plan)

    if block.status == models.StudyBlock.Status.COMPLETED:
        return _block_queryset().get(pk=block.pk)
    if block.status not in {
        models.StudyBlock.Status.PENDING,
        models.StudyBlock.Status.IN_PROGRESS,
    }:
        raise StudyPlanningError(
            "study_block_not_actionable",
            "این بلوک قابل تکمیل نیست.",
            status_code=409,
        )
    _validate_block_target(block)

    evidence = _canonical_completion_evidence(block, user)
    if block.block_kind in CANONICAL_EVIDENCE_KINDS and evidence is None:
        raise StudyPlanningError(
            "study_block_evidence_missing",
            "برای تکمیل این بلوک باید فعالیت واقعی مرتبط در موتور اصلی ثبت شده باشد.",
            status_code=409,
        )

    block.status = models.StudyBlock.Status.COMPLETED
    block.completed_at = timezone.now()
    metadata = dict(block.metadata or {})
    metadata["completion_evidence"] = evidence
    block.metadata = metadata
    block.save(
        update_fields=("status", "completed_at", "metadata", "updated_at")
    )
    _invalidate_generation(plan)
    return _block_queryset().get(pk=block.pk)
