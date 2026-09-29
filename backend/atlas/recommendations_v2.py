"""Deterministic, read-only Recommendation V2 candidates.

The caller owns feedback lookup and response limiting. ``context_ref`` is an
internal identity component and must be removed from public item payloads.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, Subquery

from . import models
from .learning import available_flashcards, due_flashcard_progress, new_flashcards
from .study_planning import _scope_target, _target_active
from .study_scheduler import _block_queryset, study_block_payload


PRIORITIES = {
    "overdue_block": (120, 1),
    "plan_schedule_stale": (110, 2),
    "plan_generate": (105, 3),
    "srs_review": (100, 4),
    "plan_capacity": (90, 5),
    "case_resume": (80, 6),
    "quiz_retry": (70, 7),
    "distortion_practice": (60, 8),
    "concept_review": (50, 9),
    "disorder_review": (50, 9),
    "graph_explore": (40, 10),
    "srs_start": (30, 11),
}


def fingerprint(rec_type, target_type, target_id, reason_code, context_ref):
    identity = ["rec-v2", rec_type, target_type, target_id, reason_code, context_ref]
    encoded = json.dumps(identity, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return "r2_" + hashlib.sha256(encoded).hexdigest()


def _candidate(rec_type, target_type, target_id, slug, reason_code, context_ref,
               title, description, reasons, signals, href, label, *,
               scheduled_date=None, reason_codes=None):
    priority, rank = PRIORITIES[rec_type]
    return {
        "key": fingerprint(rec_type, target_type, target_id, reason_code, context_ref),
        "type": rec_type,
        "target": {"type": target_type, "id": target_id, "slug": slug},
        "priority": priority,
        "title": title[:160],
        "description": description[:400],
        "reason_codes": (reason_codes or [reason_code])[:4],
        "reasons": reasons[:4],
        "signals": signals[:4],
        "action": {"href": href, "label": label},
        "context_ref": context_ref,
        "_sort": (rank, scheduled_date or "9999-12-31"),
    }


def _owner_date(user, now):
    timezone_name = (
        models.UserStudySettings.objects.filter(user=user)
        .values_list("study_timezone", flat=True).first()
        or settings.TIME_ZONE
    )
    try:
        return now.astimezone(ZoneInfo(timezone_name)).date()
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return now.astimezone(ZoneInfo(settings.TIME_ZONE)).date()


def _capped(queryset, cap):
    rows = list(queryset[: cap + 1])
    return rows[:cap], len(rows) > cap


def _summary_current(plan):
    summary = plan.last_generation_summary
    if not plan.generation_fingerprint or not plan.last_generated_at or not isinstance(summary, dict):
        return False
    required = ("generation_version", "unscheduled_candidates", "capacity_shortfall_minutes", "available_minutes")
    return (
        all(type(summary.get(field)) is int and summary[field] >= 0 for field in required)
        and summary["generation_version"] == plan.generation_version
    )


def _block_suppression(kind, suppressed, *, quiz_id=None, clinical_case_id=None,
                       concept_id=None, disorder_id=None):
    if kind == models.StudyBlock.Kind.FLASHCARD_REVIEW:
        suppressed.add(("review_queue", None, "flashcard_review"))
    elif kind == models.StudyBlock.Kind.QUIZ_PRACTICE and quiz_id:
        suppressed.add(("quiz", quiz_id, "quiz_practice"))
    elif kind == models.StudyBlock.Kind.CASE_PRACTICE and clinical_case_id:
        suppressed.add(("clinical_case", clinical_case_id, "case_practice"))
    elif kind == models.StudyBlock.Kind.CONCEPT_REVIEW and concept_id:
        suppressed.add(("concept", concept_id, "concept_reading"))
    elif kind == models.StudyBlock.Kind.DISORDER_REVIEW and disorder_id:
        suppressed.add(("disorder", disorder_id, "disorder_reading"))
    elif kind == models.StudyBlock.Kind.DISTORTION_PRACTICE and concept_id:
        suppressed.add(("concept", concept_id, "distortion_practice"))


def _queue_candidates(user, now, today, suppressed):
    if ("review_queue", None, "flashcard_review") in suppressed:
        return []
    visible = available_flashcards()
    due_count = due_flashcard_progress(user, now, visible).count()
    if due_count:
        return [_candidate(
            "srs_review", "review_queue", None, None, "srs_due",
            f"due_day:{today.isoformat()}", "مرور فلش‌کارت‌ها",
            f"{due_count} فلش‌کارت فعال موعد مرور دارد.",
            ["موعد مرور این فلش‌کارت‌ها طبق برنامه مرور ثبت‌شده رسیده است."],
            [{"kind": "srs_due", "count": due_count}], "/flashcards", "مرور فلش‌کارت‌ها",
        )]
    new_count = new_flashcards(user, visible).count()
    if new_count:
        return [_candidate(
            "srs_start", "review_queue", None, None, "srs_new",
            f"new_day:{today.isoformat()}", "شروع فلش‌کارت‌های جدید",
            f"{new_count} فلش‌کارت فعال هنوز مرور نشده است.",
            ["برای این فلش‌کارت‌ها سابقه مرور ثبت نشده است."],
            [{"kind": "srs_new", "count": new_count}], "/flashcards", "شروع مرور",
        )]
    return []


def resumable_case_attempts(user, now):
    """Owner-scoped recent attempts whose case and pinned step can be resumed."""
    return models.CaseAttempt.objects.filter(
        user=user, status=models.CaseAttempt.Status.IN_PROGRESS,
        updated_at__gte=now - timedelta(days=30),
        case__is_active=True,
        case__current_revision__status=models.CaseRevision.Status.PUBLISHED,
        case__current_revision__entry_step__is_active=True,
        case__current_revision__case_id=F("case_id"),
        case__current_revision__entry_step__case_id=F("case_id"),
        case__current_revision__entry_step__revision_id=F("case__current_revision_id"),
        revision__case_id=F("case_id"),
        revision__status=models.CaseRevision.Status.PUBLISHED,
        current_step__is_active=True,
        current_step__case_id=F("case_id"),
        current_step__revision_id=F("revision_id"),
    ).filter(
        Q(case__current_revision__primary_disorder__isnull=True)
        | Q(case__current_revision__primary_disorder__is_active=True),
    ).select_related(
        "case", "case__current_revision", "case__current_revision__entry_step",
        "case__current_revision__primary_disorder", "revision", "current_step",
    ).order_by("-updated_at", "-id")


def build_candidates(user, now, *, today=None):
    """Return ordered, deduplicated pre-dismissal candidates and cap indicator.

    No write occurs here, including implicit settings creation. The API applies
    owner-key feedback and a response limit after this function returns.
    """
    today = today if today is not None else _owner_date(user, now)
    cutoff = now - timedelta(days=30)
    candidates = []
    truncated = False
    suppressed_actions = set()

    plans, hit = _capped(
        models.StudyPlan.objects.filter(user=user, status=models.StudyPlan.Status.ACTIVE)
        .prefetch_related(
            Prefetch("scopes", queryset=models.StudyPlanScope.objects.filter(priority__gte=4).select_related(
                "concept", "theory", "disorder", "therapy", "therapy__family",
                "psychologist", "timeline_event", "quiz", "quiz__disorder",
                "clinical_case", "clinical_case__current_revision",
                "clinical_case__current_revision__entry_step",
                "clinical_case__current_revision__primary_disorder",
            ).order_by("id")),
            Prefetch("availability", queryset=models.StudyPlanAvailability.objects.order_by("weekday", "id")),
        ).order_by("-updated_at", "-id"), 20,
    )
    truncated |= hit
    plan_ids = [plan.id for plan in plans]

    # The 50-item overdue cap limits advice, not deduplication. Stream compact
    # target identifiers for all actionable blocks through today so a capped
    # overdue block or today's block still wins over matching generic advice.
    block_base = _block_queryset().filter(
        plan__user=user, plan__status=models.StudyPlan.Status.ACTIVE,
        status__in=[models.StudyBlock.Status.PENDING, models.StudyBlock.Status.IN_PROGRESS],
    )
    overdue, hit = _capped(block_base.filter(scheduled_date__lt=today).order_by("scheduled_date", "id"), 50)
    truncated |= hit
    for block in overdue:
        payload = study_block_payload(block)
        if not payload["target_active"]:
            continue
        candidates.append(_candidate(
            "overdue_block", "study_block", block.id, str(block.id), "block_overdue",
            f"scheduled:{block.scheduled_date.isoformat()}", "بلوک مطالعه عقب‌افتاده",
            f"بلوک {block.get_block_kind_display()} برای {block.scheduled_date.isoformat()} برنامه‌ریزی شده است.",
            [f"این بلوک در تاریخ {block.scheduled_date.isoformat()} برنامه‌ریزی شده و هنوز تکمیل نشده است."],
            [{"kind": "study_block", "id": block.id, "plan_id": block.plan_id,
              "block_kind": block.block_kind, "scheduled_date": block.scheduled_date.isoformat()}],
            payload["action_href"], "ادامه بلوک مطالعه",
            scheduled_date=block.scheduled_date.isoformat(),
        ))
    actionable_through_today = block_base.filter(scheduled_date__lte=today).filter(
        Q(block_kind=models.StudyBlock.Kind.FLASHCARD_REVIEW)
        | (Q(block_kind=models.StudyBlock.Kind.QUIZ_PRACTICE, quiz__is_active=True)
           & (Q(quiz__disorder__isnull=True) | Q(quiz__disorder__is_active=True)))
        | (Q(block_kind=models.StudyBlock.Kind.CASE_PRACTICE, clinical_case__is_active=True,
             clinical_case__current_revision__status=models.CaseRevision.Status.PUBLISHED,
             clinical_case__current_revision__entry_step__is_active=True,
             clinical_case__current_revision__case_id=F("clinical_case_id"),
             clinical_case__current_revision__entry_step__case_id=F("clinical_case_id"),
             clinical_case__current_revision__entry_step__revision_id=F("clinical_case__current_revision_id"))
           & (Q(clinical_case__current_revision__primary_disorder__isnull=True)
              | Q(clinical_case__current_revision__primary_disorder__is_active=True)))
        | Q(block_kind__in=[models.StudyBlock.Kind.CONCEPT_REVIEW,
                            models.StudyBlock.Kind.DISTORTION_PRACTICE], concept__is_active=True)
        | Q(block_kind=models.StudyBlock.Kind.DISORDER_REVIEW, disorder__is_active=True)
    ).order_by().values_list("block_kind", "quiz_id", "clinical_case_id", "concept_id", "disorder_id")
    for kind, quiz_id, case_id, concept_id, disorder_id in actionable_through_today.iterator(chunk_size=200):
        _block_suppression(kind, suppressed_actions, quiz_id=quiz_id,
                           clinical_case_id=case_id, concept_id=concept_id,
                           disorder_id=disorder_id)

    current_block_scopes = set(models.StudyBlock.objects.filter(
        plan__user=user, plan_id__in=plan_ids, plan__status=models.StudyPlan.Status.ACTIVE,
        generation_version=F("plan__generation_version"), scope_id__isnull=False,
    ).exclude(status__in=[models.StudyBlock.Status.SUPERSEDED, models.StudyBlock.Status.SKIPPED])
        .values_list("plan_id", "generation_version", "scope_id").distinct())
    for plan in plans:
        ref = f"generation:{plan.generation_version}"
        href = f"/study/plans/{plan.id}"
        if plan.generation_version == 0:
            candidates.append(_candidate(
                "plan_generate", "study_plan", plan.id, str(plan.id), "schedule_missing", ref,
                "ساخت برنامه زمانی مطالعه", "برای این برنامه هنوز زمان‌بندی ساخته نشده است.",
                ["نسخه زمان‌بندی این برنامه هنوز صفر است."],
                [{"kind": "study_plan", "id": plan.id, "generation_version": 0}], href, "ساخت زمان‌بندی",
            ))
            continue
        if not _summary_current(plan):
            candidates.append(_candidate(
                "plan_schedule_stale", "study_plan", plan.id, str(plan.id), "schedule_stale", ref,
                "بازبینی زمان‌بندی برنامه", "زمان‌بندی این برنامه نیاز به بازبینی دارد.",
                ["خلاصه معتبر و جاری برای آخرین نسخه زمان‌بندی در دسترس نیست."],
                [{"kind": "study_plan", "id": plan.id, "generation_version": plan.generation_version}],
                href, "بازبینی برنامه",
            ))
            continue
        summary = plan.last_generation_summary
        codes = []
        reasons = []
        signals = []
        backlog = summary["unscheduled_candidates"]
        shortfall = summary["capacity_shortfall_minutes"]
        if backlog:
            codes.append("unscheduled_backlog")
            reasons.append(f"{backlog} مورد از زمان‌بندی این برنامه جا مانده است.")
            signals.append({"kind": "unscheduled_backlog", "count": backlog})
        if shortfall:
            codes.append("capacity_shortfall")
            reasons.append(f"کمبود ظرفیت گزارش‌شده {shortfall} دقیقه است.")
            signals.append({"kind": "capacity_shortfall", "minutes": shortfall})
        uncovered = []
        for scope in plan.scopes.all():
            if scope.priority < 4 or (plan.id, plan.generation_version, scope.id) in current_block_scopes:
                continue
            target_type, target = _scope_target(scope)
            if target is not None and _target_active(target_type, target):
                uncovered.append(scope)
        if uncovered:
            codes.append("scope_without_coverage")
            reasons.append(f"{len(uncovered)} حوزه دارای اولویت بالا بلوک زمان‌بندی جاری ندارد.")
            signals.append({"kind": "scope_without_coverage", "scope_ids": [scope.id for scope in uncovered[:10]]})
        if summary["available_minutes"] == 0:
            codes.append("zero_usable_capacity")
            reasons.append("ظرفیت قابل استفاده در زمان‌بندی اخیر صفر دقیقه گزارش شده است.")
            signals.append({"kind": "zero_usable_capacity", "available_minutes": 0,
                            "configured_weekly_minutes": sum(a.available_minutes for a in plan.availability.all())})
        if codes:
            if plan.plan_kind == models.StudyPlan.Kind.EXAM and plan.target_date is not None:
                signals.append({"kind": "exam_target_date", "days_remaining": max(0, (plan.target_date - today).days),
                                "target_date": plan.target_date.isoformat()})
            candidates.append(_candidate(
                "plan_capacity", "study_plan", plan.id, str(plan.id), "plan_capacity_gap", ref,
                "بازبینی ظرفیت برنامه", "بخشی از برنامه با ظرفیت زمان‌بندی فعلی پوشش داده نشده است.",
                reasons, signals, href, "بازبینی برنامه", reason_codes=["plan_capacity_gap", *codes],
            ))

    candidates.extend(_queue_candidates(user, now, today, suppressed_actions))

    cases, hit = _capped(resumable_case_attempts(user, now), 20)
    truncated |= hit
    seen_cases = set()
    for attempt in cases:
        case = attempt.case
        if case.id in seen_cases or not _target_active("clinical_case", case):
            continue
        seen_cases.add(case.id)
        if ("clinical_case", case.id, "case_practice") in suppressed_actions:
            continue
        candidates.append(_candidate(
            "case_resume", "clinical_case", case.id, case.slug, "case_in_progress",
            f"attempt:{attempt.id}", "ادامه تمرین مورد", "یک تلاش ناتمام برای این مورد ثبت شده است.",
            ["این تلاش در ۳۰ روز اخیر فعال بوده است."],
            [{"kind": "case_attempt", "id": attempt.id, "revision_id": attempt.revision_id}],
            f"/cases/{case.slug}", "ادامه تمرین",
        ))

    quizzes, hit = _capped(models.QuizAttempt.objects.filter(
        user=user, status=models.QuizAttempt.Status.COMPLETED, completed_at__gte=cutoff,
        quiz__is_active=True,
    ).filter(
        Q(quiz__disorder__isnull=True) | Q(quiz__disorder__is_active=True),
    ).select_related("quiz", "quiz__disorder").order_by("-completed_at", "-id"), 20)
    truncated |= hit
    wrong_by_attempt = dict(models.QuizAttemptAnswer.objects.filter(
        attempt_id__in=[a.id for a in quizzes], is_correct=False,
    ).values("attempt_id").annotate(total=Count("id")).values_list("attempt_id", "total"))
    seen_quizzes = set()
    for attempt in quizzes:
        quiz = attempt.quiz
        if quiz.id in seen_quizzes or not _target_active("quiz", quiz):
            continue
        seen_quizzes.add(quiz.id)
        wrong = wrong_by_attempt.get(attempt.id, 0)
        if not wrong or ("quiz", quiz.id, "quiz_practice") in suppressed_actions:
            continue
        candidates.append(_candidate(
            "quiz_retry", "quiz", quiz.id, quiz.slug, "recent_incorrect_quiz_answers",
            f"attempt:{attempt.id}", "مرور پاسخ‌های این آزمون",
            f"در آخرین تلاش، {wrong} پاسخ نادرست ثبت شده است؛ می‌توانی دوباره تمرین کنی.",
            ["آخرین تلاش این آزمون در ۳۰ روز اخیر ثبت شده است."],
            [{"kind": "quiz_attempt", "id": attempt.id, "incorrect_answers": wrong}],
            f"/quizzes/{quiz.slug}", "تمرین دوباره",
        ))

    distortion_scopes, hit = _capped(models.StudyPlanScope.objects.filter(
        plan__user=user, plan__status=models.StudyPlan.Status.ACTIVE,
        concept__is_active=True, concept__subtype=models.Concept.Subtype.COGNITIVE_DISTORTION,
        include_practice=True,
    ).select_related("concept", "plan").order_by("plan_id", "id"), 20)
    truncated |= hit
    valid_practice = set(models.CognitiveDistortionPracticeItem.objects.filter(
        is_active=True, target_concept__is_active=True,
        target_concept_id__in=[scope.concept_id for scope in distortion_scopes],
    ).values_list("target_concept_id", flat=True).distinct())
    for scope in distortion_scopes:
        concept = scope.concept
        if (concept.id not in valid_practice
                or ("concept", concept.id, "distortion_practice") in suppressed_actions):
            continue
        candidates.append(_candidate(
            "distortion_practice", "concept", concept.id, concept.slug, "explicit_distortion_scope",
            f"plan:{scope.plan_id}:scope:{scope.id}", "تمرین تشخیص نمونه‌ها",
            "این مفهوم در حوزه مطالعه انتخابی توست و تمرین فعالی برای آن وجود دارد.",
            ["تمرین نمونه‌های این مفهوم در برنامه مطالعه صریحاً فعال شده است."],
            [{"kind": "study_scope", "id": scope.id, "plan_id": scope.plan_id,
              "practice_item_available": True}],
            "/cognitive-distortions#practice", "تمرین تشخیص",
        ))

    concepts, hit = _capped(models.UserConceptProgress.objects.filter(
        user=user, progress_percent__lt=70, concept__is_active=True,
    ).select_related("concept").order_by("progress_percent", "concept_id"), 10)
    truncated |= hit
    for progress in concepts:
        concept = progress.concept
        if ("concept", concept.id, "concept_reading") in suppressed_actions:
            continue
        candidates.append(_candidate(
            "concept_review", "concept", concept.id, concept.slug, "concept_progress_low",
            "current_progress", "مرور مفهوم", "پیشرفت ثبت‌شده این مفهوم کمتر از ۷۰٪ است.",
            [f"پیشرفت ثبت‌شده برای این مفهوم {progress.progress_percent}٪ است."],
            [{"kind": "concept_progress", "percent": progress.progress_percent}],
            f"/concepts/{concept.slug}", "مرور مفهوم",
        ))

    disorders, hit = _capped(models.UserProgress.objects.filter(
        user=user, progress_percent__lt=70, disorder__is_active=True,
    ).select_related("disorder").order_by("progress_percent", "disorder_id"), 10)
    truncated |= hit
    for progress in disorders:
        disorder = progress.disorder
        if ("disorder", disorder.id, "disorder_reading") in suppressed_actions:
            continue
        candidates.append(_candidate(
            "disorder_review", "disorder", disorder.id, disorder.slug, "disorder_progress_low",
            "current_progress", "مرور اختلال", "پیشرفت ثبت‌شده این مدخل کمتر از ۷۰٪ است.",
            [f"پیشرفت ثبت‌شده برای این مدخل {progress.progress_percent}٪ است."],
            [{"kind": "disorder_progress", "percent": progress.progress_percent}],
            f"/disorders/{disorder.slug}", "مرور مدخل",
        ))

    checked_source = models.TheoryConceptSource.objects.filter(
        relationship_id=OuterRef("pk"), source__verification_status__regex=r"\S",
    ).exclude(source__verification_status="citation_from_model_knowledge")
    first_scope = models.StudyPlanScope.objects.filter(
        theory_id=OuterRef("theory_id"), plan__user=user,
        plan__status=models.StudyPlan.Status.ACTIVE,
        theory__is_active=True, theory__review_status=models.ScientificReviewStatus.REVIEWED,
    ).order_by("id").values("id")[:1]
    relations, hit = _capped(models.TheoryConcept.objects.filter(
        theory__is_active=True,
        theory__review_status=models.ScientificReviewStatus.REVIEWED,
        concept__is_active=True, is_active=True,
        review_status=models.ScientificReviewStatus.REVIEWED,
    ).annotate(has_checked_source=Exists(checked_source), first_scope_id=Subquery(first_scope))
        .filter(has_checked_source=True, first_scope_id__isnull=False)
        .select_related("theory", "concept")
        .prefetch_related(Prefetch("source_links", queryset=models.TheoryConceptSource.objects.select_related("source").order_by("source_id")))
        .order_by("first_scope_id", "id"), 20)
    truncated |= hit
    graph_scopes = models.StudyPlanScope.objects.in_bulk([relation.first_scope_id for relation in relations])
    graph_low_progress = set(models.UserConceptProgress.objects.filter(
        user=user, concept_id__in=[relation.concept_id for relation in relations],
        progress_percent__lt=70,
    ).values_list("concept_id", flat=True))
    graph_by_concept = {}
    for relation in relations:
        if (relation.concept_id in graph_low_progress
                or ("concept", relation.concept_id, "concept_reading") in suppressed_actions):
            continue
        sources = [link.source for link in relation.source_links.all()
                   if link.source.verification_status.strip()
                   and link.source.verification_status != "citation_from_model_knowledge"]
        if not sources:
            continue
        scope = graph_scopes[relation.first_scope_id]
        current = graph_by_concept.get(relation.concept_id)
        if current is None or (scope.id, relation.id) < (current[0].id, current[1].id):
            graph_by_concept[relation.concept_id] = (scope, relation, sources[:2])
    for scope, relation, sources in graph_by_concept.values():
        concept = relation.concept
        theory = relation.theory
        theory_name = theory.name_fa or theory.name_en
        source_signals = [{"id": source.id, "title": source.title[:160], "url": source.url,
                           "citation": source.citation[:240], "organization": source.organization[:160],
                           "publication_year": source.publication_year,
                           "verification_status": source.verification_status}
                          for source in sources]
        candidates.append(_candidate(
            "graph_explore", "concept", concept.id, concept.slug, "reviewed_explicit_relation",
            f"theoryconcept:{relation.id}:{relation.relationship_type}:scope:{scope.id}",
            "مطالعه رابطه ثبت‌شده در اطلس",
            f"این مفهوم در اطلس با نظریه {theory_name} با رابطه {relation.get_relationship_type_display()} ثبت شده است.",
            ["این رابطه مستقیم و بازبینی‌شده با منبع بررسی‌شده ثبت شده است."],
            [{"kind": "theory_concept_relation", "id": relation.id, "relation_type": relation.relationship_type,
              "review_status": relation.review_status, "sources": source_signals}],
            f"/concepts/{concept.slug}", "مطالعه مفهوم",
        ))

    candidates.sort(key=lambda item: (
        -item["priority"], item["_sort"][0], item["_sort"][1],
        item["target"]["type"], item["target"]["slug"] or "", item["key"],
    ))
    deduped = []
    seen_keys = set()
    seen_actions = set()
    for item in candidates:
        target = item["target"]
        action_kind = item["action"]["href"]
        action = (action_kind, target["type"], target["id"], item["context_ref"])
        if item["key"] in seen_keys or action in seen_actions:
            continue
        seen_keys.add(item["key"])
        seen_actions.add(action)
        item.pop("_sort")
        deduped.append(item)
        if len(deduped) == 200:
            truncated = True
            break
    return deduped, truncated
