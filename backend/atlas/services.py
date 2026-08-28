from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .learning import record_activity
from .models import (
    CaseAttempt,
    CaseAttemptAnswer,
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
        if isinstance(question_raw, bool) or isinstance(choice_raw, bool):
            raise ValidationError(f"شناسه سؤال یا گزینه در {label} معتبر نیست.")
        if not isinstance(question_raw, (int, str)) or not isinstance(choice_raw, (int, str)):
            raise ValidationError(f"شناسه سؤال یا گزینه در {label} معتبر نیست.")
        if isinstance(question_raw, str) and not question_raw.isdigit():
            raise ValidationError(f"شناسه سؤال یا گزینه در {label} معتبر نیست.")
        if isinstance(choice_raw, str) and not choice_raw.isdigit():
            raise ValidationError(f"شناسه سؤال یا گزینه در {label} معتبر نیست.")
        question_id = int(question_raw)
        choice_id = int(choice_raw)
        if question_id <= 0 or choice_id <= 0:
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
    question_ids = set(quiz.questions.values_list("id", flat=True))
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
    questions = {q.id: q for q in quiz.questions.prefetch_related("choices").all()}

    for qid, cid in normalized_answers:
        question = questions[qid]
        try:
            choice = next(c for c in question.choices.all() if c.id == cid)
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
        progress.progress_percent = max(progress.progress_percent, 65)
        progress.last_viewed_at = timezone.now()
        progress.save(update_fields=("progress_percent", "last_viewed_at", "updated_at"))

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
    questions = {}
    for step in clinical_case.steps.prefetch_related("questions__choices").all():
        for q in step.questions.all():
            questions[q.id] = q

    if not questions:
        raise ValidationError("این کیس بالینی هنوز سؤال قابل پاسخ ندارد.")
    normalized_answers = _normalize_answers(answers, set(questions), label="کیس بالینی")

    max_score = sum(
        max([c.score_value for c in q.choices.all()] or [0])
        for q in questions.values()
    )
    attempt = CaseAttempt.objects.create(
        user=user,
        case=clinical_case,
        max_score=max_score,
    )

    score = 0
    feedback = []
    for qid, cid in normalized_answers:
        question = questions[qid]
        try:
            choice = next(c for c in question.choices.all() if c.id == cid)
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
        max_for_question = max([c.score_value for c in question.choices.all()] or [0])
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
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=("score", "status", "completed_at", "updated_at"))

    if clinical_case.primary_disorder_id:
        progress, _ = UserProgress.objects.get_or_create(user=user, disorder=clinical_case.primary_disorder)
        next_percent = max(progress.progress_percent, 85 if score == max_score else 75)
        progress.progress_percent = next_percent
        progress.last_viewed_at = timezone.now()
        if next_percent >= 85:
            progress.status = UserProgress.Status.COMPLETED
            progress.completed_at = timezone.now()
        progress.save(update_fields=("progress_percent", "last_viewed_at", "status", "completed_at", "updated_at"))

    record_activity(
        user,
        StudyActivity.Kind.CASE_COMPLETED,
        clinical_case=clinical_case,
        disorder=clinical_case.primary_disorder,
        metadata={"score": attempt.score, "max_score": attempt.max_score},
    )
    return attempt, feedback
