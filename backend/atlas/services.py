import time
from collections import defaultdict

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .learning import record_activity
from .validation import positive_int
from .models import (
    CaseAttempt,
    CaseAttemptAnswer,
    CaseAttemptEvent,
    CaseStep,
    CaseTransition,
    ClinicalCase,
    QuizAttempt,
    QuizAttemptAnswer,
    StudyActivity,
    UserProgress,
)


def _normalize_answers(answers, expected_question_ids, *, label):
    if not isinstance(answers, list):
        raise ValidationError(f"پاسخ‌های {label} باید به‌صورت یک فهرست ارسال شوند.")
    if len(answers) != len(expected_question_ids):
        raise ValidationError(f"به همه سؤال‌های {label} باید دقیقاً یک بار پاسخ داده شود.")

    normalized = []
    submitted_ids = set()
    for item in answers:
        if not isinstance(item, dict):
            raise ValidationError(f"ساختار یکی از پاسخ‌های {label} معتبر نیست.")
        question_raw = item.get("question_id")
        choice_raw = item.get("choice_id")
        try:
            question_id = positive_int(question_raw, field="question_id")
            choice_id = positive_int(choice_raw, field="choice_id")
        except ValidationError:
            raise ValidationError(f"شناسه سؤال یا گزینه در {label} معتبر نیست.")

        if question_id in submitted_ids:
            raise ValidationError(f"هر سؤال {label} فقط یک بار باید پاسخ داده شود.")
        submitted_ids.add(question_id)
        normalized.append((question_id, choice_id))

    if submitted_ids != expected_question_ids:
        raise ValidationError(f"به همه سؤال‌های {label} باید دقیقاً یک بار پاسخ داده شود.")
    return normalized


@transaction.atomic
def submit_quiz(*, user, quiz, answers):
    question_ids = set(quiz.questions.filter(is_active=True).values_list("id", flat=True))
    if not question_ids:
        raise ValidationError("این آزمون هنوز سؤال قابل پاسخ ندارد.")
    normalized_answers = _normalize_answers(answers, question_ids, label="آزمون")

    attempt = QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        total_questions=len(question_ids),
    )

    correct = 0
    feedback = []
    questions = {q.id: q for q in quiz.questions.filter(is_active=True).prefetch_related("choices").all()}

    for qid, cid in normalized_answers:
        question = questions[qid]
        try:
            choice = next(c for c in question.choices.all() if c.id == cid and c.is_active)
        except StopIteration:
            raise ValidationError(f"گزینه {cid} متعلق به سؤال {qid} نیست.")

        is_correct = bool(choice.is_correct)
        correct += int(is_correct)
        QuizAttemptAnswer.objects.create(
            attempt=attempt,
            question=question,
            selected_choice=choice,
            is_correct=is_correct,
        )
        feedback.append({
            "question_id": qid,
            "correct": is_correct,
            "explanation": question.explanation,
        })

    attempt.correct_count = correct
    attempt.score = round(correct * 100 / len(question_ids)) if question_ids else 0
    attempt.status = QuizAttempt.Status.COMPLETED
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=("correct_count", "score", "status", "completed_at", "updated_at"))

    if quiz.disorder_id:
        progress, _ = UserProgress.objects.get_or_create(user=user, disorder=quiz.disorder)
        earned_progress = 25 + round(attempt.score * 0.60)
        progress.progress_percent = max(progress.progress_percent, earned_progress)
        progress.last_viewed_at = timezone.now()
        if progress.progress_percent >= 85:
            progress.status = UserProgress.Status.COMPLETED
            progress.completed_at = progress.completed_at or timezone.now()
        progress.save(update_fields=("progress_percent", "last_viewed_at", "status", "completed_at", "updated_at"))

    record_activity(
        user,
        StudyActivity.Kind.QUIZ_COMPLETED,
        quiz=quiz,
        disorder=quiz.disorder,
        metadata={"score": attempt.score, "correct_count": correct, "total_questions": len(question_ids)},
    )
    return attempt, feedback


@transaction.atomic
def submit_case(*, user, clinical_case, answers):
    revision = clinical_case.current_revision
    if revision is None:
        raise ValidationError("این کیس بالینی revision فعال ندارد.")
    if clinical_case.structure_mode != "linear":
        raise ValidationError("این endpoint فقط برای کیس‌های خطی سازگار با نسخه قبلی است.")

    questions = {}
    for step in revision.steps.filter(is_active=True).prefetch_related("questions__choices", "questions__scoring_dimension").all():
        for q in step.questions.all():
            if q.is_active:
                questions[q.id] = q

    if not questions:
        raise ValidationError("این کیس بالینی هنوز سؤال قابل پاسخ ندارد.")
    normalized_answers = _normalize_answers(answers, set(questions), label="کیس بالینی")

    max_score = sum(
        max([c.score_value for c in q.choices.all() if c.is_active] or [0])
        for q in questions.values()
    )
    attempt = CaseAttempt.objects.create(
        user=user,
        case=clinical_case,
        revision=revision,
        current_step=revision.entry_step,
        max_score=max_score,
    )

    score = 0
    feedback = []
    for qid, cid in normalized_answers:
        question = questions[qid]
        try:
            choice = next(c for c in question.choices.all() if c.id == cid and c.is_active)
        except StopIteration:
            raise ValidationError(f"گزینه {cid} متعلق به سؤال {qid} نیست.")

        awarded = choice.score_value
        score += awarded
        CaseAttemptAnswer.objects.create(
            attempt=attempt,
            question=question,
            scoring_dimension=question.scoring_dimension,
            selected_choice=choice,
            awarded_score=awarded,
        )
        max_for_question = max([c.score_value for c in question.choices.all() if c.is_active] or [0])
        feedback.append({
            "question_id": qid,
            "awarded_score": awarded,
            "max_score": max_for_question,
            "full_credit": awarded == max_for_question,
            "feedback": choice.feedback,
            "explanation": question.explanation,
            "scoring_dimension": (
                {
                    "key": question.scoring_dimension.stable_key,
                    "label": question.scoring_dimension.label,
                }
                if question.scoring_dimension_id
                else None
            ),
        })

    attempt.score = score
    attempt.status = CaseAttempt.Status.COMPLETED
    attempt.current_step = None
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=("score", "status", "current_step", "completed_at", "updated_at"))

    disorder = revision.primary_disorder
    if disorder_id := getattr(disorder, "id", None):
        progress, _ = UserProgress.objects.get_or_create(user=user, disorder_id=disorder_id)
        performance = round(score * 100 / max_score) if max_score else 0
        earned_progress = 25 + round(performance * 0.60)
        progress.progress_percent = max(progress.progress_percent, earned_progress)
        progress.last_viewed_at = timezone.now()
        if progress.progress_percent >= 85:
            progress.status = UserProgress.Status.COMPLETED
            progress.completed_at = progress.completed_at or timezone.now()
        progress.save(update_fields=("progress_percent", "last_viewed_at", "status", "completed_at", "updated_at"))

    record_activity(
        user,
        StudyActivity.Kind.CASE_COMPLETED,
        clinical_case=clinical_case,
        disorder=disorder,
        metadata={
            "score": attempt.score,
            "max_score": attempt.max_score,
            "case_revision": revision.version,
            "rubric_version": revision.rubric_version,
        },
    )
    return attempt, feedback


def _apply_stateful_case_completion_side_effects(attempt):
    disorder = attempt.revision.primary_disorder
    dimension_feedback = build_case_attempt_dimension_feedback(attempt)
    if disorder_id := getattr(disorder, "id", None):
        progress, _ = UserProgress.objects.get_or_create(user=attempt.user, disorder_id=disorder_id)
        performance = round(attempt.score * 100 / attempt.max_score) if attempt.max_score else 0
        earned_progress = 25 + round(performance * 0.60)
        progress.progress_percent = max(progress.progress_percent, earned_progress)
        progress.last_viewed_at = timezone.now()
        if progress.progress_percent >= 85:
            progress.status = UserProgress.Status.COMPLETED
            progress.completed_at = progress.completed_at or timezone.now()
        progress.save(update_fields=("progress_percent", "last_viewed_at", "status", "completed_at", "updated_at"))

    record_activity(
        attempt.user,
        StudyActivity.Kind.CASE_COMPLETED,
        clinical_case=attempt.case,
        disorder=disorder,
        metadata={
            "attempt_id": attempt.id,
            "score": attempt.score,
            "max_score": attempt.max_score,
            "case_revision": attempt.revision.version,
            "rubric_version": attempt.revision.rubric_version,
            "dimension_scores": [
                {
                    "key": item["key"],
                    "score": item["score"],
                    "max_score": item["max_score"],
                }
                for item in dimension_feedback["dimensions"]
            ],
            "stateful_engine": True,
        },
    )


_SQLITE_LOCK_RETRY_DELAYS = (0.02, 0.05, 0.10, 0.20, 0.40)


def _validate_resumable_case_attempt(attempt):
    if (
        attempt.current_step_id is None
        or attempt.current_step.revision_id != attempt.revision_id
        or not attempt.current_step.is_active
    ):
        raise ValidationError("attempt در حال اجرا state معتبر برای resume ندارد.")
    return attempt


@transaction.atomic
def _start_or_resume_case_attempt_once(*, user, clinical_case):
    locked_case = (
        ClinicalCase.objects.select_for_update()
        .select_related("current_revision__entry_step")
        .get(pk=clinical_case.pk)
    )
    existing_attempts = list(
        CaseAttempt.objects.select_for_update()
        .filter(user=user, case=locked_case, status=CaseAttempt.Status.IN_PROGRESS)
        .select_related("revision", "current_step")
        .order_by("-created_at", "-id")[:2]
    )
    if len(existing_attempts) > 1:
        raise ValidationError("برای این کاربر و کیس بیش از یک attempt در حال اجرا وجود دارد؛ audit لازم است.")
    if existing_attempts:
        return _validate_resumable_case_attempt(existing_attempts[0]), False

    revision = locked_case.current_revision
    if revision is None or revision.status != revision.Status.PUBLISHED:
        raise ValidationError("این کیس revision منتشرشده و قابل شروع ندارد.")
    entry_step = revision.entry_step
    if entry_step is None or not entry_step.is_active or entry_step.revision_id != revision.id:
        raise ValidationError("نقطه شروع معتبر برای این کیس تعریف نشده است.")

    attempt = CaseAttempt.objects.create(
        user=user,
        case=locked_case,
        revision=revision,
        current_step=entry_step,
        status=CaseAttempt.Status.IN_PROGRESS,
        state_version=0,
    )
    return attempt, True


def start_or_resume_case_attempt(*, user, clinical_case):
    """Start exactly one active attempt, retrying only transient SQLite writer-lock races."""
    for retry_index in range(len(_SQLITE_LOCK_RETRY_DELAYS) + 1):
        try:
            return _start_or_resume_case_attempt_once(user=user, clinical_case=clinical_case)
        except IntegrityError:
            existing = (
                CaseAttempt.objects.filter(
                    user=user,
                    case=clinical_case,
                    status=CaseAttempt.Status.IN_PROGRESS,
                )
                .select_related("revision", "current_step")
                .order_by("-created_at", "-id")
                .first()
            )
            if existing is not None:
                return _validate_resumable_case_attempt(existing), False
            raise
        except OperationalError as exc:
            is_transient_sqlite_lock = connection.vendor == "sqlite" and "locked" in str(exc).lower()
            if not is_transient_sqlite_lock or retry_index >= len(_SQLITE_LOCK_RETRY_DELAYS):
                raise
            time.sleep(_SQLITE_LOCK_RETRY_DELAYS[retry_index])


def _event_snapshot(*, step, question=None, choice=None, transition=None):
    snapshot = {
        "step_key": step.stable_key,
        "step_title": step.title,
        "node_kind": step.node_kind,
    }
    if question is not None:
        snapshot["question_prompt"] = question.prompt
        snapshot["question_explanation"] = question.explanation
        if question.scoring_dimension_id:
            snapshot["scoring_dimension"] = {
                "key": question.scoring_dimension.stable_key,
                "label": question.scoring_dimension.label,
                "description": question.scoring_dimension.description,
                "sort_order": question.scoring_dimension.sort_order,
            }
    if choice is not None:
        snapshot["choice_text"] = choice.text
        snapshot["choice_feedback"] = choice.feedback
    if transition is not None:
        snapshot["outcome"] = transition.outcome
        snapshot["target_step_key"] = transition.target_step.stable_key if transition.target_step_id else None
    else:
        snapshot["outcome"] = CaseTransition.Outcome.COMPLETE
        snapshot["target_step_key"] = None
    return snapshot


def build_case_attempt_dimension_feedback(attempt):
    dimensions = {}
    decision_count = 0
    unscored_decisions = 0

    for event in attempt.events.all():
        if event.event_type != CaseAttemptEvent.EventType.DECISION:
            continue
        decision_count += 1
        if attempt.revision.rubric_version == 0:
            unscored_decisions += 1
            continue
        dimension_snapshot = event.snapshot.get("scoring_dimension") if isinstance(event.snapshot, dict) else None
        if not isinstance(dimension_snapshot, dict):
            unscored_decisions += 1
            continue
        key = dimension_snapshot.get("key")
        label = dimension_snapshot.get("label")
        if not isinstance(key, str) or not key or not isinstance(label, str) or not label:
            unscored_decisions += 1
            continue
        raw_description = dimension_snapshot.get("description")
        raw_sort_order = dimension_snapshot.get("sort_order")
        description = raw_description if isinstance(raw_description, str) else ""
        sort_order = raw_sort_order if isinstance(raw_sort_order, int) and not isinstance(raw_sort_order, bool) else 0
        row = dimensions.setdefault(key, {
            "key": key,
            "label": label,
            "description": description,
            "sort_order": max(sort_order, 0),
            "score": 0,
            "max_score": 0,
            "decision_count": 0,
        })
        row["score"] += event.awarded_score
        row["max_score"] += event.max_score
        row["decision_count"] += 1

    ordered = sorted(dimensions.values(), key=lambda item: (item["sort_order"], item["label"], item["key"]))
    review_dimensions = []
    for row in ordered:
        row["percent"] = round(row["score"] * 100 / row["max_score"]) if row["max_score"] else None
        row["needs_review"] = row["max_score"] > row["score"]
        if row["needs_review"]:
            row["feedback"] = "در این بُعد بخشی از امتیاز مسیر از دست رفته است؛ بازخورد و توضیح تصمیم‌های مربوط را مرور کن."
            review_dimensions.append(row["key"])
        else:
            row["feedback"] = "در تصمیم‌های طی‌شده این بُعد، امتیاز کامل ثبت شده است؛ توضیح تصمیم‌ها را برای تثبیت مرور کن."

    if ordered:
        message = "این breakdown فقط از تصمیم‌های واقعاً طی‌شده در همین revision ساخته شده است."
    elif attempt.revision.rubric_version == 0:
        message = "این تلاش پیش از rubric چندبعدی v0.7.3 ثبت شده و breakdown چندبعدی ندارد."
    else:
        message = "هنوز تصمیم امتیازدهی‌شده‌ای برای ساخت breakdown چندبعدی ثبت نشده است."

    return {
        "rubric_version": attempt.revision.rubric_version,
        "available": bool(ordered),
        "decision_count": decision_count,
        "unscored_decisions": unscored_decisions,
        "dimensions": ordered,
        "review_dimensions": review_dimensions,
        "message": message,
        "disclaimer": (
            "این breakdown فقط عملکرد در تصمیم‌های همین سناریوی آموزشی را توصیف می‌کند و "
            "معیار صلاحیت بالینی، تشخیص، درمان یا ارزیابی حرفه‌ای نیست."
        ),
    }


@transaction.atomic
def _advance_case_attempt_once(*, user, attempt, step_id, choice_id, state_version):
    locked = (
        CaseAttempt.objects.select_for_update()
        .select_related("case", "revision__primary_disorder", "current_step")
        .get(pk=attempt.pk, user=user)
    )

    prior_event = (
        locked.events.filter(step_id=step_id)
        .select_related("selected_choice", "next_step", "transition")
        .first()
    )
    if prior_event is not None:
        if prior_event.state_version_before == state_version and prior_event.selected_choice_id == choice_id:
            return locked, prior_event, True
        raise ValidationError("این مرحله قبلاً با یک state یا انتخاب دیگر ثبت شده است.")

    if locked.status != CaseAttempt.Status.IN_PROGRESS:
        raise ValidationError("این attempt قبلاً تکمیل شده و قابل ویرایش نیست.")
    if locked.state_version != state_version:
        raise ValidationError({"state_version": "وضعیت attempt تغییر کرده است؛ state جدید را دوباره دریافت کن."})
    if locked.current_step_id != step_id:
        raise ValidationError({"step_id": "فقط مرحله جاری attempt قابل ثبت است."})

    step = (
        CaseStep.objects.filter(pk=locked.current_step_id, is_active=True, revision=locked.revision)
        .prefetch_related("questions__choices", "questions__scoring_dimension")
        .first()
    )
    if step is None:
        raise ValidationError("مرحله جاری attempt دیگر معتبر نیست.")

    question = None
    choice = None
    transition = None
    next_step = None
    awarded_score = 0
    max_score = 0

    if step.node_kind == CaseStep.NodeKind.DECISION:
        active_questions = [q for q in step.questions.all() if q.is_active]
        if len(active_questions) != 1:
            raise ValidationError("ساختار مرحله تصمیم این کیس معتبر نیست.")
        question = active_questions[0]
        if choice_id is None:
            raise ValidationError({"choice_id": "برای مرحله تصمیم باید یک گزینه انتخاب شود."})
        choice = next((item for item in question.choices.all() if item.id == choice_id and item.is_active), None)
        if choice is None:
            raise ValidationError({"choice_id": "گزینه انتخاب‌شده متعلق به سؤال جاری و فعال نیست."})
        transition = (
            CaseTransition.objects.filter(
                revision=locked.revision,
                source_step=step,
                choice=choice,
                is_active=True,
            )
            .select_related("target_step")
            .first()
        )
        if transition is None:
            raise ValidationError("برای این انتخاب transition معتبر تعریف نشده است.")
        awarded_score = choice.score_value
        max_score = max([item.score_value for item in question.choices.all() if item.is_active] or [0])
    elif step.node_kind == CaseStep.NodeKind.INFORMATION:
        if choice_id is not None:
            raise ValidationError({"choice_id": "مرحله اطلاعاتی انتخاب گزینه ندارد."})
        transition = (
            CaseTransition.objects.filter(
                revision=locked.revision,
                source_step=step,
                choice__isnull=True,
                is_active=True,
            )
            .select_related("target_step")
            .first()
        )
        if transition is None:
            raise ValidationError("برای مرحله اطلاعاتی transition خودکار معتبر تعریف نشده است.")
    elif step.node_kind == CaseStep.NodeKind.TERMINAL:
        if choice_id is not None:
            raise ValidationError({"choice_id": "مرحله پایانی انتخاب گزینه ندارد."})
    else:
        raise ValidationError("نوع مرحله جاری پشتیبانی نمی‌شود.")

    if transition is not None:
        if transition.outcome == CaseTransition.Outcome.CONTINUE:
            next_step = transition.target_step
            if next_step is None or not next_step.is_active or next_step.revision_id != locked.revision_id:
                raise ValidationError("هدف transition جاری معتبر نیست.")
        elif transition.outcome != CaseTransition.Outcome.COMPLETE:
            raise ValidationError("نتیجه transition جاری معتبر نیست.")

    event_type = CaseAttemptEvent.EventType.DECISION
    if step.node_kind == CaseStep.NodeKind.INFORMATION:
        event_type = CaseAttemptEvent.EventType.ADVANCE
    elif step.node_kind == CaseStep.NodeKind.TERMINAL:
        event_type = CaseAttemptEvent.EventType.TERMINAL_COMPLETE

    before = locked.state_version
    after = before + 1
    outcome = transition.outcome if transition is not None else CaseTransition.Outcome.COMPLETE
    event = CaseAttemptEvent(
        attempt=locked,
        step=step,
        event_type=event_type,
        question=question,
        scoring_dimension=question.scoring_dimension if question is not None else None,
        selected_choice=choice,
        transition=transition,
        next_step=next_step,
        outcome=outcome,
        awarded_score=awarded_score,
        max_score=max_score,
        state_version_before=before,
        state_version_after=after,
        snapshot=_event_snapshot(step=step, question=question, choice=choice, transition=transition),
    )
    event.full_clean()
    event.save()

    if question is not None and choice is not None:
        answer = CaseAttemptAnswer(
            attempt=locked,
            question=question,
            scoring_dimension=question.scoring_dimension,
            selected_choice=choice,
            awarded_score=awarded_score,
        )
        answer.full_clean()
        answer.save()

    locked.score += awarded_score
    locked.max_score += max_score
    locked.state_version = after
    completed = step.node_kind == CaseStep.NodeKind.TERMINAL or outcome == CaseTransition.Outcome.COMPLETE
    if completed:
        locked.status = CaseAttempt.Status.COMPLETED
        locked.current_step = None
        locked.completed_at = timezone.now()
        locked.save(update_fields=(
            "score",
            "max_score",
            "state_version",
            "status",
            "current_step",
            "completed_at",
            "updated_at",
        ))
        _apply_stateful_case_completion_side_effects(locked)
    else:
        locked.current_step = next_step
        locked.save(update_fields=("score", "max_score", "state_version", "current_step", "updated_at"))

    return locked, event, False


def _recover_case_attempt_event_race(*, user, attempt, step_id, choice_id, state_version):
    refreshed = (
        CaseAttempt.objects.select_related("case", "revision__primary_disorder", "current_step")
        .get(pk=attempt.pk, user=user)
    )
    prior_event = (
        refreshed.events.filter(step_id=step_id)
        .select_related("selected_choice", "next_step", "transition")
        .first()
    )
    if prior_event is None:
        return None
    if prior_event.state_version_before == state_version and prior_event.selected_choice_id == choice_id:
        return refreshed, prior_event, True
    raise ValidationError("این مرحله قبلاً با یک state یا انتخاب دیگر ثبت شده است.")


def advance_case_attempt(*, user, attempt, step_id, choice_id, state_version):
    """Advance one immutable Case event, retrying transient SQLite writer-lock races."""
    for retry_index in range(len(_SQLITE_LOCK_RETRY_DELAYS) + 1):
        try:
            return _advance_case_attempt_once(
                user=user,
                attempt=attempt,
                step_id=step_id,
                choice_id=choice_id,
                state_version=state_version,
            )
        except IntegrityError:
            recovered = _recover_case_attempt_event_race(
                user=user,
                attempt=attempt,
                step_id=step_id,
                choice_id=choice_id,
                state_version=state_version,
            )
            if recovered is not None:
                return recovered
            raise
        except OperationalError as exc:
            is_transient_sqlite_lock = connection.vendor == "sqlite" and "locked" in str(exc).lower()
            if not is_transient_sqlite_lock or retry_index >= len(_SQLITE_LOCK_RETRY_DELAYS):
                raise
            time.sleep(_SQLITE_LOCK_RETRY_DELAYS[retry_index])


CASE_ANALYTICS_VERSION = 1
CASE_ANALYTICS_RECENT_ATTEMPT_LIMIT = 20
CASE_ANALYTICS_PATH_LIMIT = 20
CASE_ANALYTICS_DISCLAIMER = (
    "این آمار فقط الگوهای ثبت‌شده در سناریوهای آموزشی همین کاربر را خلاصه می‌کند و "
    "معیار صلاحیت بالینی، تشخیص، درمان یا مقایسه هنجاری با دیگران نیست."
)


def _analytics_percent(score, max_score):
    if max_score is None or max_score <= 0:
        return None
    return round(score * 100 / max_score)


def _analytics_completion_rate(completed, total):
    if not total:
        return None
    return round(completed * 100 / total)


def _average_scored_attempt_percent(rows):
    percents = [
        percent
        for row in rows
        if row["status"] == CaseAttempt.Status.COMPLETED
        for percent in [_analytics_percent(row["score"], row["max_score"])]
        if percent is not None
    ]
    if not percents:
        return None, 0
    return round(sum(percents) / len(percents)), len(percents)


def _reconstruct_completed_attempt_path(attempt, events):
    """Return a historical path only when the immutable event stream is internally complete."""
    if not events:
        return None

    event_node_kinds = {
        CaseAttemptEvent.EventType.DECISION: CaseStep.NodeKind.DECISION,
        CaseAttemptEvent.EventType.ADVANCE: CaseStep.NodeKind.INFORMATION,
        CaseAttemptEvent.EventType.TERMINAL_COMPLETE: CaseStep.NodeKind.TERMINAL,
    }
    entry_step_key = events[0].get("attempt__revision__entry_step__stable_key")
    if not isinstance(entry_step_key, str) or not entry_step_key:
        return None

    expected_state_version = 0
    expected_step_key = entry_step_key
    signature_parts = []
    path_steps = []

    for index, event in enumerate(events):
        if (
            event["state_version_before"] != expected_state_version
            or event["state_version_after"] != expected_state_version + 1
            or event["event_type"] not in event_node_kinds
        ):
            return None

        snapshot = event["snapshot"] if isinstance(event["snapshot"], dict) else {}
        step_key = snapshot.get("step_key")
        node_kind = snapshot.get("node_kind")
        snapshot_outcome = snapshot.get("outcome")
        expected_node_kind = event_node_kinds[event["event_type"]]
        if (
            not isinstance(step_key, str)
            or not step_key
            or step_key != event["step__stable_key"]
            or node_kind != expected_node_kind
            or event["step__node_kind"] != expected_node_kind
            or snapshot_outcome != event["outcome"]
            or step_key != expected_step_key
        ):
            return None

        raw_step_title = snapshot.get("step_title")
        step_title = raw_step_title if isinstance(raw_step_title, str) else ""
        raw_target_step_key = snapshot.get("target_step_key")
        if raw_target_step_key is not None and (
            not isinstance(raw_target_step_key, str) or not raw_target_step_key
        ):
            return None
        target_step_key = raw_target_step_key
        actual_target_step_key = event["next_step__stable_key"]

        raw_choice_text = snapshot.get("choice_text")
        if event["event_type"] == CaseAttemptEvent.EventType.DECISION:
            if (
                event["selected_choice_id"] is None
                or not isinstance(raw_choice_text, str)
                or not raw_choice_text
            ):
                return None
            choice_text = raw_choice_text
        else:
            if event["selected_choice_id"] is not None or raw_choice_text is not None:
                return None
            choice_text = None

        if event["outcome"] == CaseTransition.Outcome.CONTINUE:
            if (
                target_step_key is None
                or target_step_key != actual_target_step_key
                or index == len(events) - 1
            ):
                return None
            expected_step_key = target_step_key
        elif event["outcome"] == CaseTransition.Outcome.COMPLETE:
            if (
                target_step_key is not None
                or actual_target_step_key is not None
                or index != len(events) - 1
            ):
                return None
            expected_step_key = None
        else:
            return None

        signature_parts.append((
            event["event_type"],
            step_key,
            event["selected_choice_id"],
            choice_text,
            target_step_key,
        ))
        path_steps.append({
            "event_type": event["event_type"],
            "step_key": step_key,
            "step_title": step_title,
            "node_kind": node_kind,
            "choice_id": event["selected_choice_id"],
            "choice_text": choice_text,
        })
        expected_state_version += 1

    if attempt["state_version"] != expected_state_version:
        return None
    return tuple(signature_parts), path_steps


def build_personal_case_analytics_overview(*, user):
    """Return bounded-query, personal-only Case analytics derived from immutable attempt history."""
    attempt_rows = list(
        CaseAttempt.objects.filter(user=user)
        .values(
            "id",
            "case_id",
            "case__slug",
            "case__title",
            "case__current_revision__title",
            "case__structure_mode",
            "revision__version",
            "revision__title",
            "revision__rubric_version",
            "status",
            "score",
            "max_score",
            "created_at",
            "updated_at",
            "completed_at",
        )
        .order_by("case_id", "created_at", "id")
    )
    decision_counts = {
        row["attempt__case_id"]: row["decision_count"]
        for row in (
            CaseAttemptEvent.objects.filter(
                attempt__user=user,
                event_type=CaseAttemptEvent.EventType.DECISION,
            )
            .values("attempt__case_id")
            .annotate(decision_count=Count("id"))
        )
    }

    by_case = defaultdict(list)
    for row in attempt_rows:
        by_case[row["case_id"]].append(row)

    case_summaries = []
    for case_id, rows in by_case.items():
        total = len(rows)
        completed = sum(row["status"] == CaseAttempt.Status.COMPLETED for row in rows)
        in_progress = total - completed
        average_percent, scored_completed = _average_scored_attempt_percent(rows)
        latest = max(rows, key=lambda row: (row["updated_at"], row["id"]))
        case_summaries.append({
            "case_id": case_id,
            "slug": latest["case__slug"],
            "current_title": latest["case__current_revision__title"] or latest["case__title"],
            "latest_attempt_revision_title": latest["revision__title"] or latest["case__title"],
            "structure_mode": latest["case__structure_mode"],
            "latest_attempt_revision_number": latest["revision__version"],
            "latest_attempt_rubric_version": latest["revision__rubric_version"],
            "attempts": total,
            "completed_attempts": completed,
            "in_progress_attempts": in_progress,
            "completion_rate": _analytics_completion_rate(completed, total),
            "average_completed_score_percent": average_percent,
            "scored_completed_attempts": scored_completed,
            "decision_count": decision_counts.get(case_id, 0),
            "last_activity_at": latest["updated_at"],
        })

    case_summaries.sort(key=lambda row: (row["last_activity_at"], row["case_id"]), reverse=True)
    total = len(attempt_rows)
    completed = sum(row["status"] == CaseAttempt.Status.COMPLETED for row in attempt_rows)
    average_percent, scored_completed = _average_scored_attempt_percent(attempt_rows)

    return {
        "analytics_version": CASE_ANALYTICS_VERSION,
        "scope": "personal",
        "generated_at": timezone.now(),
        "attempts": {
            "total": total,
            "completed": completed,
            "in_progress": total - completed,
            "completion_rate": _analytics_completion_rate(completed, total),
            "average_completed_score_percent": average_percent,
            "scored_completed_attempts": scored_completed,
        },
        "cases_started": len(case_summaries),
        "decision_count": sum(decision_counts.values()),
        "cases": case_summaries,
        "disclaimer": CASE_ANALYTICS_DISCLAIMER,
    }


def build_personal_case_analytics_detail(*, user, clinical_case):
    """Return personal analytics for one Case without consulting mutable future graph state."""
    attempt_rows = list(
        CaseAttempt.objects.filter(user=user, case=clinical_case)
        .values(
            "id",
            "revision__version",
            "revision__title",
            "revision__rubric_version",
            "status",
            "score",
            "max_score",
            "state_version",
            "created_at",
            "updated_at",
            "completed_at",
        )
        .order_by("-updated_at", "-id")
    )
    if not attempt_rows:
        return None

    event_rows = list(
        CaseAttemptEvent.objects.filter(attempt__user=user, attempt__case=clinical_case)
        .values(
            "attempt_id",
            "attempt__revision__version",
            "attempt__revision__rubric_version",
            "attempt__revision__entry_step__stable_key",
            "event_type",
            "step__stable_key",
            "step__node_kind",
            "selected_choice_id",
            "next_step__stable_key",
            "awarded_score",
            "max_score",
            "state_version_before",
            "state_version_after",
            "outcome",
            "snapshot",
        )
        .order_by("attempt_id", "state_version_before", "id")
    )

    events_by_attempt = defaultdict(list)
    for event in event_rows:
        events_by_attempt[event["attempt_id"]].append(event)

    dimension_groups = {}
    branch_groups = {}
    rubric_zero_decisions = 0
    unscored_dimension_decisions = 0

    for event in event_rows:
        if event["event_type"] != CaseAttemptEvent.EventType.DECISION:
            continue
        snapshot = event["snapshot"] if isinstance(event["snapshot"], dict) else {}
        revision_number = event["attempt__revision__version"]
        rubric_version = event["attempt__revision__rubric_version"]

        step_key = snapshot.get("step_key")
        raw_step_title = snapshot.get("step_title")
        step_title = raw_step_title if isinstance(raw_step_title, str) else ""
        choice_text = snapshot.get("choice_text")
        if isinstance(step_key, str) and step_key and isinstance(choice_text, str) and choice_text:
            branch_key = (revision_number, step_key, step_title)
            branch = branch_groups.setdefault(branch_key, {
                "revision_number": revision_number,
                "step_key": step_key,
                "step_title": step_title,
                "decision_count": 0,
                "choices": {},
            })
            branch["decision_count"] += 1
            choice_identity = (event["selected_choice_id"], choice_text)
            choice = branch["choices"].setdefault(choice_identity, {
                "choice_id": event["selected_choice_id"],
                "choice_text": choice_text,
                "count": 0,
                "score": 0,
                "max_score": 0,
            })
            choice["count"] += 1
            choice["score"] += event["awarded_score"]
            choice["max_score"] += event["max_score"]

        if rubric_version < 1:
            rubric_zero_decisions += 1
            continue

        dimension_snapshot = snapshot.get("scoring_dimension")
        if not isinstance(dimension_snapshot, dict):
            unscored_dimension_decisions += 1
            continue
        key = dimension_snapshot.get("key")
        label = dimension_snapshot.get("label")
        if not isinstance(key, str) or not key or not isinstance(label, str) or not label:
            unscored_dimension_decisions += 1
            continue
        description = dimension_snapshot.get("description")
        if not isinstance(description, str):
            description = ""
        raw_sort_order = dimension_snapshot.get("sort_order")
        sort_order = raw_sort_order if isinstance(raw_sort_order, int) and not isinstance(raw_sort_order, bool) else 0
        dimension_key = (revision_number, key, label, description)
        dimension = dimension_groups.setdefault(dimension_key, {
            "revision_number": revision_number,
            "key": key,
            "label": label,
            "description": description,
            "sort_order": max(sort_order, 0),
            "score": 0,
            "max_score": 0,
            "decision_count": 0,
            "attempt_ids": set(),
        })
        dimension["score"] += event["awarded_score"]
        dimension["max_score"] += event["max_score"]
        dimension["decision_count"] += 1
        dimension["attempt_ids"].add(event["attempt_id"])

    dimensions = []
    for dimension in dimension_groups.values():
        percent = _analytics_percent(dimension["score"], dimension["max_score"])
        dimensions.append({
            "revision_number": dimension["revision_number"],
            "key": dimension["key"],
            "label": dimension["label"],
            "description": dimension["description"],
            "sort_order": dimension["sort_order"],
            "score": dimension["score"],
            "max_score": dimension["max_score"],
            "percent": percent,
            "decision_count": dimension["decision_count"],
            "attempt_count": len(dimension["attempt_ids"]),
            "needs_review": percent is not None and dimension["score"] < dimension["max_score"],
        })
    dimensions.sort(key=lambda row: (-row["revision_number"], row["sort_order"], row["label"], row["key"]))

    branches = []
    for branch in branch_groups.values():
        choices = []
        for choice in branch["choices"].values():
            choices.append({
                "choice_id": choice["choice_id"],
                "choice_text": choice["choice_text"],
                "count": choice["count"],
                "selection_percent": round(choice["count"] * 100 / branch["decision_count"]),
                "score": choice["score"],
                "max_score": choice["max_score"],
                "score_percent": _analytics_percent(choice["score"], choice["max_score"]),
            })
        choices.sort(key=lambda row: (-row["count"], row["choice_text"], row["choice_id"] or 0))
        branches.append({
            "revision_number": branch["revision_number"],
            "step_key": branch["step_key"],
            "step_title": branch["step_title"],
            "decision_count": branch["decision_count"],
            "choices": choices,
        })
    branches.sort(key=lambda row: (-row["revision_number"], row["step_key"], row["step_title"]))

    path_groups = {}
    completed_attempts_without_reconstructible_path = 0
    for attempt in attempt_rows:
        if attempt["status"] != CaseAttempt.Status.COMPLETED:
            continue
        events = events_by_attempt.get(attempt["id"], [])
        reconstructed = _reconstruct_completed_attempt_path(attempt, events)
        if reconstructed is None:
            completed_attempts_without_reconstructible_path += 1
            continue
        signature_parts, path_steps = reconstructed
        path_key = (attempt["revision__version"], signature_parts)
        path = path_groups.setdefault(path_key, {
            "revision_number": attempt["revision__version"],
            "steps": path_steps,
            "attempt_count": 0,
            "last_used_at": attempt["completed_at"] or attempt["updated_at"],
        })
        path["attempt_count"] += 1
        used_at = attempt["completed_at"] or attempt["updated_at"]
        if used_at and (not path["last_used_at"] or used_at > path["last_used_at"]):
            path["last_used_at"] = used_at

    paths = list(path_groups.values())
    paths.sort(key=lambda row: (row["attempt_count"], row["last_used_at"]), reverse=True)
    paths = paths[:CASE_ANALYTICS_PATH_LIMIT]

    recent_attempts = []
    for attempt in attempt_rows[:CASE_ANALYTICS_RECENT_ATTEMPT_LIMIT]:
        events = events_by_attempt.get(attempt["id"], [])
        recent_attempts.append({
            "id": attempt["id"],
            "revision_number": attempt["revision__version"],
            "revision_title": attempt["revision__title"] or clinical_case.title,
            "rubric_version": attempt["revision__rubric_version"],
            "status": attempt["status"],
            "state_version": attempt["state_version"],
            "score": attempt["score"],
            "max_score": attempt["max_score"],
            "score_percent": _analytics_percent(attempt["score"], attempt["max_score"]),
            "event_count": len(events),
            "decision_count": sum(event["event_type"] == CaseAttemptEvent.EventType.DECISION for event in events),
            "started_at": attempt["created_at"],
            "updated_at": attempt["updated_at"],
            "completed_at": attempt["completed_at"],
        })

    total = len(attempt_rows)
    completed = sum(row["status"] == CaseAttempt.Status.COMPLETED for row in attempt_rows)
    average_percent, scored_completed = _average_scored_attempt_percent(attempt_rows)
    rubric_zero_attempts = sum(row["revision__rubric_version"] == 0 for row in attempt_rows)

    return {
        "analytics_version": CASE_ANALYTICS_VERSION,
        "scope": "personal",
        "generated_at": timezone.now(),
        "case": {
            "id": clinical_case.id,
            "slug": clinical_case.slug,
            "current_title": (
                clinical_case.current_revision.title
                if clinical_case.current_revision_id and clinical_case.current_revision.title
                else clinical_case.title
            ),
            "structure_mode": clinical_case.structure_mode,
        },
        "attempts": {
            "total": total,
            "completed": completed,
            "in_progress": total - completed,
            "completion_rate": _analytics_completion_rate(completed, total),
            "average_completed_score_percent": average_percent,
            "scored_completed_attempts": scored_completed,
        },
        "decision_count": sum(
            event["event_type"] == CaseAttemptEvent.EventType.DECISION
            for event in event_rows
        ),
        "dimensions": dimensions,
        "branches": branches,
        "completed_paths": paths,
        "recent_attempts": recent_attempts,
        "legacy": {
            "rubric_zero_attempts": rubric_zero_attempts,
            "rubric_zero_decisions": rubric_zero_decisions,
            "unscored_dimension_decisions": unscored_dimension_decisions,
            "completed_attempts_without_reconstructible_path": completed_attempts_without_reconstructible_path,
        },
        "disclaimer": CASE_ANALYTICS_DISCLAIMER,
    }
