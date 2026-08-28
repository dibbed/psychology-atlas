from __future__ import annotations

import math
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    Concept,
    DailyChallenge,
    DailyChallengeAttempt,
    Flashcard,
    StudyActivity,
    UserConceptProgress,
    UserFlashcardProgress,
    UserProgress,
)


def available_flashcards():
    return Flashcard.objects.filter(is_active=True).filter(
        Q(concept__isnull=True) | Q(concept__is_active=True),
        Q(disorder__isnull=True) | Q(disorder__is_active=True),
    )


def record_activity(user, activity_type, **links):
    allowed = {"disorder", "concept", "quiz", "clinical_case", "flashcard", "metadata", "occurred_at"}
    payload = {key: value for key, value in links.items() if key in allowed and value is not None}

    if activity_type in {StudyActivity.Kind.DISORDER_VIEW, StudyActivity.Kind.CONCEPT_VIEW}:
        since = timezone.now() - timedelta(minutes=5)
        qs = StudyActivity.objects.filter(user=user, activity_type=activity_type, occurred_at__gte=since)
        for key in ("disorder", "concept"):
            if key in payload:
                qs = qs.filter(**{key: payload[key]})
        existing = qs.order_by("-occurred_at", "-id").first()
        if existing:
            return existing

    return StudyActivity.objects.create(user=user, activity_type=activity_type, **payload)


def mark_concept_viewed(user, concept: Concept):
    now = timezone.now()
    progress, _ = UserConceptProgress.objects.get_or_create(user=user, concept=concept)
    progress.progress_percent = max(progress.progress_percent, 20)
    progress.last_viewed_at = now
    progress.save(update_fields=("progress_percent", "last_viewed_at", "updated_at"))
    record_activity(user, StudyActivity.Kind.CONCEPT_VIEW, concept=concept)
    return progress


def _update_concept_from_review(user, flashcard: Flashcard, rating: str):
    if not flashcard.concept_id:
        return
    now = timezone.now()
    progress, _ = UserConceptProgress.objects.get_or_create(user=user, concept=flashcard.concept)
    minimum = {
        UserFlashcardProgress.Rating.AGAIN: 30,
        UserFlashcardProgress.Rating.HARD: 45,
        UserFlashcardProgress.Rating.GOOD: 70,
        UserFlashcardProgress.Rating.EASY: 85,
    }[rating]
    progress.progress_percent = max(progress.progress_percent, minimum)
    progress.last_reviewed_at = now
    progress.last_viewed_at = progress.last_viewed_at or now
    if progress.progress_percent >= 85:
        progress.status = UserConceptProgress.Status.COMPLETED
        progress.completed_at = progress.completed_at or now
    progress.save(
        update_fields=(
            "progress_percent",
            "last_reviewed_at",
            "last_viewed_at",
            "status",
            "completed_at",
            "updated_at",
        )
    )


@transaction.atomic
def review_flashcard(*, user, flashcard: Flashcard, rating: str):
    valid = {choice for choice, _ in UserFlashcardProgress.Rating.choices}
    if rating not in valid:
        raise ValueError("invalid_rating")

    now = timezone.now()
    progress, _ = UserFlashcardProgress.objects.select_for_update().get_or_create(
        user=user,
        flashcard=flashcard,
    )

    ease = progress.ease_factor
    interval = progress.interval_days
    repetitions = progress.repetitions
    lapses = progress.lapses

    if rating == UserFlashcardProgress.Rating.AGAIN:
        repetitions = 0
        interval = 0
        lapses += 1
        ease = max(1.3, ease - 0.20)
        due_at = now + timedelta(minutes=10)
        state = UserFlashcardProgress.State.LEARNING
    elif rating == UserFlashcardProgress.Rating.HARD:
        repetitions += 1
        interval = 1 if interval <= 0 else max(1, math.ceil(interval * 1.2))
        ease = max(1.3, ease - 0.15)
        due_at = now + timedelta(days=interval)
        state = UserFlashcardProgress.State.REVIEW
    elif rating == UserFlashcardProgress.Rating.GOOD:
        repetitions += 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 3
        else:
            interval = max(1, round(max(interval, 1) * ease))
        due_at = now + timedelta(days=interval)
        state = UserFlashcardProgress.State.REVIEW
    else:
        repetitions += 1
        ease = min(4.0, ease + 0.15)
        if repetitions == 1:
            interval = 4
        else:
            interval = max(4, round(max(interval, 1) * ease * 1.3))
        due_at = now + timedelta(days=interval)
        state = UserFlashcardProgress.State.REVIEW

    progress.state = state
    progress.due_at = due_at
    progress.interval_days = interval
    progress.ease_factor = round(ease, 2)
    progress.repetitions = repetitions
    progress.lapses = lapses
    progress.last_rating = rating
    progress.last_reviewed_at = now
    progress.save(
        update_fields=(
            "state",
            "due_at",
            "interval_days",
            "ease_factor",
            "repetitions",
            "lapses",
            "last_rating",
            "last_reviewed_at",
            "updated_at",
        )
    )

    record_activity(
        user,
        StudyActivity.Kind.FLASHCARD_REVIEW,
        flashcard=flashcard,
        concept=flashcard.concept,
        disorder=flashcard.disorder,
        metadata={"rating": rating, "interval_days": interval},
    )
    _update_concept_from_review(user, flashcard, rating)
    return progress


def get_review_queue(user, *, limit=20, concept_slug=None, disorder_slug=None):
    now = timezone.now()
    visible_ids = available_flashcards().values_list("id", flat=True)
    due_qs = UserFlashcardProgress.objects.filter(user=user, flashcard_id__in=visible_ids, due_at__lte=now)
    new_qs = available_flashcards()
    if concept_slug:
        due_qs = due_qs.filter(flashcard__concept__slug=concept_slug)
        new_qs = new_qs.filter(concept__slug=concept_slug)
    if disorder_slug:
        due_qs = due_qs.filter(flashcard__disorder__slug=disorder_slug)
        new_qs = new_qs.filter(disorder__slug=disorder_slug)
    due_rows = list(
        due_qs.select_related("flashcard", "flashcard__concept", "flashcard__disorder", "flashcard__disorder__category")
        .order_by("due_at", "id")[:limit]
    )
    remaining = max(0, limit - len(due_rows))
    if remaining:
        reviewed_ids = UserFlashcardProgress.objects.filter(user=user).values_list("flashcard_id", flat=True)
        new_cards = list(
            new_qs.exclude(id__in=reviewed_ids)
            .select_related("concept", "disorder", "disorder__category")
            .order_by("sort_order", "id")[:remaining]
        )
        return due_rows, new_cards
    return due_rows, []


def current_streak(user):
    today = timezone.localdate()
    dates = set(
        StudyActivity.objects.filter(user=user, occurred_at__date__lte=today)
        .values_list("occurred_at__date", flat=True)
        .distinct()
    )
    for value in user.quiz_attempts.filter(completed_at__isnull=False).values_list("completed_at", flat=True):
        dates.add(timezone.localtime(value).date())
    for value in user.case_attempts.filter(completed_at__isnull=False).values_list("completed_at", flat=True):
        dates.add(timezone.localtime(value).date())
    for value in user.learning_progress.filter(last_viewed_at__isnull=False).values_list("last_viewed_at", flat=True):
        dates.add(timezone.localtime(value).date())
    if not dates:
        return 0
    cursor = today
    if cursor not in dates:
        cursor = today - timedelta(days=1)
        if cursor not in dates:
            return 0
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def activity_heatmap(user, *, days=42):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    counts = {}
    activity_kinds_by_day = {}

    for day, kind in StudyActivity.objects.filter(
        user=user,
        occurred_at__date__gte=start,
    ).values_list("occurred_at__date", "activity_type"):
        counts[day] = counts.get(day, 0) + 1
        activity_kinds_by_day.setdefault(day, set()).add(kind)

    for value in user.quiz_attempts.filter(completed_at__date__gte=start).values_list("completed_at", flat=True):
        day = timezone.localtime(value).date()
        if StudyActivity.Kind.QUIZ_COMPLETED not in activity_kinds_by_day.get(day, set()):
            counts[day] = counts.get(day, 0) + 1

    for value in user.case_attempts.filter(completed_at__date__gte=start).values_list("completed_at", flat=True):
        day = timezone.localtime(value).date()
        if StudyActivity.Kind.CASE_COMPLETED not in activity_kinds_by_day.get(day, set()):
            counts[day] = counts.get(day, 0) + 1

    for value in user.learning_progress.filter(last_viewed_at__date__gte=start).values_list("last_viewed_at", flat=True):
        day = timezone.localtime(value).date()
        if StudyActivity.Kind.DISORDER_VIEW not in activity_kinds_by_day.get(day, set()):
            counts[day] = counts.get(day, 0) + 1

    return [
        {"date": (start + timedelta(days=offset)).isoformat(), "count": counts.get(start + timedelta(days=offset), 0)}
        for offset in range(days)
    ]


def get_recommendations(user, *, limit=6):
    recommendations = []
    visible_cards = available_flashcards()
    due_count = UserFlashcardProgress.objects.filter(
        user=user,
        flashcard_id__in=visible_cards.values_list("id", flat=True),
        due_at__lte=timezone.now(),
    ).count()
    unseen_count = visible_cards.exclude(
        id__in=UserFlashcardProgress.objects.filter(user=user).values_list("flashcard_id", flat=True)
    ).count()
    review_count = due_count or min(unseen_count, 10)
    if review_count:
        recommendations.append({
            "type": "flashcards",
            "title": "مرور فلش‌کارت‌ها",
            "reason": f"{review_count} کارت برای مرور یا شروع آماده است.",
            "href": "/flashcards",
            "priority": 100,
        })

    for progress in (
        UserProgress.objects.filter(user=user, disorder__is_active=True, progress_percent__lt=70)
        .select_related("disorder")
        .order_by("progress_percent", "-last_viewed_at")[:3]
    ):
        recommendations.append({
            "type": "disorder",
            "title": progress.disorder.name_fa or progress.disorder.name_en,
            "reason": f"پیشرفت این موضوع {progress.progress_percent}٪ است و ارزش مرور دوباره دارد.",
            "href": f"/disorders/{progress.disorder.slug}",
            "priority": 80 - progress.progress_percent,
        })

    for progress in (
        UserConceptProgress.objects.filter(user=user, concept__is_active=True, progress_percent__lt=70)
        .select_related("concept")
        .order_by("progress_percent", "-last_reviewed_at", "-last_viewed_at")[:3]
    ):
        recommendations.append({
            "type": "concept",
            "title": progress.concept.name_fa or progress.concept.name_en,
            "reason": f"تسلط فعلی این مفهوم {progress.progress_percent}٪ ثبت شده است.",
            "href": f"/concepts/{progress.concept.slug}",
            "priority": 75 - progress.progress_percent,
        })

    return sorted(recommendations, key=lambda item: item["priority"], reverse=True)[:limit]


def today_challenge():
    challenges = list(
        DailyChallenge.objects.filter(is_active=True)
        .filter(
            Q(concept__isnull=True) | Q(concept__is_active=True),
            Q(disorder__isnull=True) | Q(disorder__is_active=True),
        )
        .select_related("concept", "disorder")
        .prefetch_related("choices")
        .order_by("sort_order", "id")
    )
    if not challenges:
        return None
    index = timezone.localdate().toordinal() % len(challenges)
    return challenges[index]


def challenge_attempt_for_today(user):
    return (
        DailyChallengeAttempt.objects.filter(user=user, activity_date=timezone.localdate())
        .select_related("challenge", "challenge__concept", "challenge__disorder", "selected_choice")
        .first()
    )
