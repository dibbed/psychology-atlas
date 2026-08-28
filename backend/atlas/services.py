from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import (
    CaseAttempt,
    CaseAttemptAnswer,
    CaseChoice,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizChoice,
    UserProgress,
)


@transaction.atomic
def submit_quiz(*, user, quiz, answers):
    question_ids = set(quiz.questions.values_list("id", flat=True))
    submitted_ids = {int(a["question_id"]) for a in answers}
    if submitted_ids != question_ids:
        raise ValidationError("به همه سؤال‌های آزمون باید دقیقاً یک بار پاسخ داده شود.")

    attempt = QuizAttempt.objects.create(
        user=user,
        quiz=quiz,
        total_questions=len(question_ids),
    )

    correct = 0
    feedback = []
    questions = {q.id: q for q in quiz.questions.prefetch_related("choices").all()}

    for item in answers:
        qid = int(item["question_id"])
        cid = int(item["choice_id"])
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
    return attempt, feedback


@transaction.atomic
def submit_case(*, user, clinical_case, answers):
    questions = {}
    for step in clinical_case.steps.prefetch_related("questions__choices").all():
        for q in step.questions.all():
            questions[q.id] = q

    submitted_ids = {int(a["question_id"]) for a in answers}
    if submitted_ids != set(questions):
        raise ValidationError("به همه سؤال‌های کیس بالینی باید دقیقاً یک بار پاسخ داده شود.")

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
    for item in answers:
        qid = int(item["question_id"])
        cid = int(item["choice_id"])
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
    return attempt, feedback
