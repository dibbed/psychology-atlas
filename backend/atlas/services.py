from django.db import transaction
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
    for step in revision.steps.filter(is_active=True).prefetch_related("questions__choices").all():
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
        })

    attempt.score = score
    attempt.status = CaseAttempt.Status.COMPLETED
    attempt.current_step = None
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=("score", "status", "current_step", "completed_at", "updated_at"))

    if clinical_case.primary_disorder_id:
        progress, _ = UserProgress.objects.get_or_create(user=user, disorder=clinical_case.primary_disorder)
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
        disorder=clinical_case.primary_disorder,
        metadata={
            "score": attempt.score,
            "max_score": attempt.max_score,
            "case_revision": revision.version,
        },
    )
    return attempt, feedback


def _apply_stateful_case_completion_side_effects(attempt):
    disorder = attempt.revision.primary_disorder
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
            "stateful_engine": True,
        },
    )


@transaction.atomic
def start_or_resume_case_attempt(*, user, clinical_case):
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
        existing = existing_attempts[0]
        if (
            existing.current_step_id is None
            or existing.current_step.revision_id != existing.revision_id
            or not existing.current_step.is_active
        ):
            raise ValidationError("attempt در حال اجرا state معتبر برای resume ندارد.")
        return existing, False

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


def _event_snapshot(*, step, question=None, choice=None, transition=None):
    snapshot = {
        "step_key": step.stable_key,
        "step_title": step.title,
        "node_kind": step.node_kind,
    }
    if question is not None:
        snapshot["question_prompt"] = question.prompt
        snapshot["question_explanation"] = question.explanation
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


@transaction.atomic
def advance_case_attempt(*, user, attempt, step_id, choice_id, state_version):
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
        .prefetch_related("questions__choices")
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
