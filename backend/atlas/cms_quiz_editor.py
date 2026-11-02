"""P13 private, inactive quiz drafts. Historical answers are immutable.

Only inactive, unseeded quizzes without attempts may replace question/choice rows.
Activation requires later source/scientific/rights-controlled P16 publication.
"""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.response import Response

from .cms_case_editor import revision_etag
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sessions import current_session
from .cms_views import AdminAPIView, expected_version, page, payload
from .models import Disorder, Quiz, QuizAttempt, QuizChoice, QuizQuestion, StudyActivity

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _require_private_edit(actor, quiz):
    require(actor, "cms_learning_edit")
    require(actor, "cms_learning_view")
    if (quiz.seed_managed or quiz.is_active or QuizAttempt.objects.filter(quiz=quiz).exists()
            or StudyActivity.objects.filter(quiz=quiz).exists()):
        raise CMSFailure("QUIZ_HAS_HISTORY_OR_IS_PUBLIC", 409)


def _questions(data):
    if type(data) is not dict or set(data) != {"questions"}:
        raise CMSFailure("INVALID_FIELDS", 400)
    questions = data["questions"]
    if type(questions) is not list or len(questions) > 100:
        raise CMSFailure("INVALID_QUIZ", 400)
    for q in questions:
        if type(q) is not dict or set(q) != {"prompt", "explanation", "choices"}:
            raise CMSFailure("INVALID_QUIZ", 400)
        if (type(q["prompt"]) is not str or not q["prompt"].strip() or len(q["prompt"]) > 20000
                or type(q["explanation"]) is not str or len(q["explanation"]) > 20000):
            raise CMSFailure("INVALID_QUIZ", 400)
        choices = q["choices"]
        if type(choices) is not list or not 2 <= len(choices) <= 10:
            raise CMSFailure("INVALID_QUIZ", 400)
        correct = 0
        for choice in choices:
            if type(choice) is not dict or set(choice) != {"text", "is_correct"}:
                raise CMSFailure("INVALID_QUIZ", 400)
            if (type(choice["text"]) is not str or not choice["text"].strip()
                    or len(choice["text"]) > 20000 or type(choice["is_correct"]) is not bool):
                raise CMSFailure("INVALID_QUIZ", 400)
            correct += choice["is_correct"]
        if correct != 1:
            raise CMSFailure("QUIZ_ANSWER_KEY_INVALID", 400)
    return questions


def _quiz(actor, quiz_id):
    require(actor, "cms_learning_view")
    quiz = Quiz.objects.select_for_update().filter(pk=quiz_id).first()
    if quiz is None:
        raise CMSFailure("NOT_FOUND", 404)
    return quiz


def _snapshot(quiz):
    questions = list(quiz.questions.order_by("sort_order", "pk").prefetch_related("choices"))
    if len(questions) > 100 or any(q.choices.count() > 10 for q in questions):
        raise CMSFailure("PREVIEW_LIMIT", 400)
    result = [{
        "id": q.pk, "prompt": q.prompt, "explanation": q.explanation,
        "is_active": q.is_active,
        "choices": [{
            "id": c.pk, "text": c.text, "is_correct": c.is_correct,
            "is_active": c.is_active,
        } for c in q.choices.all()]
    } for q in questions]
    issues = []
    if not quiz.title.strip():
        issues.append("TITLE_MISSING")
    if not result:
        issues.append("NO_QUESTIONS")
    for q in result:
        if not q["is_active"]:
            continue
        choices = [c for c in q["choices"] if c["is_active"]]
        if not q["prompt"].strip() or len(choices) < 2 or sum(c["is_correct"] for c in choices) != 1:
            issues.append("QUESTION_INVALID:" + str(q["id"]))
    if result and not any(q["is_active"] for q in result):
        issues.append("NO_ACTIVE_QUESTIONS")
    return result, issues


def _metadata_values(data):
    title, description, disorder_id = data["title"], data["description"], data["disorder_id"]
    if (type(title) is not str or not title.strip() or len(title) > 255
            or type(description) is not str or len(description) > 20000):
        raise CMSFailure("INVALID_FIELDS", 400)
    if disorder_id is not None and (type(disorder_id) is not int or not 1 <= disorder_id <= 2**63 - 1):
        raise CMSFailure("INVALID_FIELDS", 400)
    return {"title": title.strip(), "description": description, "disorder_id": disorder_id}


def create_quiz(actor_id, session_id, data, request_id):
    if type(data) is not dict or set(data) != {"slug", "title", "description", "disorder_id"}:
        raise CMSFailure("INVALID_FIELDS", 400)
    slug = data["slug"]
    if type(slug) is not str or len(slug) > 160 or not _SLUG.fullmatch(slug):
        raise CMSFailure("INVALID_FIELDS", 400)
    metadata = _metadata_values(data)
    disorder_id = metadata["disorder_id"]
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_learning_create")
        require(actor, "cms_learning_view")
        if Quiz.objects.filter(slug=slug).exists():
            raise CMSFailure("QUIZ_SLUG_EXISTS", 409)
        if disorder_id is not None and not Disorder.objects.filter(pk=disorder_id, is_active=True).exists():
            raise CMSFailure("INVALID_REFERENCE", 400)
        quiz = Quiz.objects.create(
            slug=slug, **metadata, is_active=False, seed_managed=False,
        )
        AdminAuditEvent.objects.create(
            actor=actor, outcome="success", action="quiz.draft_created",
            target_kind="quiz", target_id=quiz.pk, request_id=request_id,
            reason="DRAFT_CREATION", diff=[],
        )
        return quiz


def update_metadata(actor_id, session_id, quiz_id, expected, data, request_id):
    if type(data) is not dict or set(data) != {"title", "description", "disorder_id"}:
        raise CMSFailure("INVALID_FIELDS", 400)
    metadata = _metadata_values(data)
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        quiz = _quiz(actor, quiz_id)
        _require_private_edit(actor, quiz)
        if revision_etag(quiz) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if metadata["disorder_id"] is not None and not Disorder.objects.filter(
                pk=metadata["disorder_id"], is_active=True).exists():
            raise CMSFailure("INVALID_REFERENCE", 400)
        changed = [field for field, value in metadata.items() if getattr(quiz, field) != value]
        if changed:
            for field in changed:
                setattr(quiz, field, metadata[field])
            quiz.updated_at = max(timezone.now(), quiz.updated_at + timedelta(microseconds=1))
            quiz.save(update_fields=[*changed, "updated_at"])
            AdminAuditEvent.objects.create(actor=actor, outcome="success", action="quiz.draft_updated",
                target_kind="quiz", target_id=quiz.pk, request_id=request_id, reason="CONTENT_UPDATE",
                diff=["disorder" if field == "disorder_id" else field for field in changed])
        return quiz


def replace_questions(actor_id, session_id, quiz_id, expected, data, request_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        quiz = _quiz(actor, quiz_id)
        _require_private_edit(actor, quiz)
        if revision_etag(quiz) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        questions = _questions(data)
        QuizChoice.objects.filter(question__quiz=quiz).delete()
        QuizQuestion.objects.filter(quiz=quiz).delete()
        for index, q in enumerate(questions):
            question = QuizQuestion.objects.create(
                quiz=quiz, prompt=q["prompt"], explanation=q["explanation"],
                sort_order=index, is_active=True,
            )
            for position, choice in enumerate(q["choices"]):
                QuizChoice.objects.create(
                    question=question, text=choice["text"], is_correct=choice["is_correct"],
                    sort_order=position, is_active=True,
                )
        quiz.updated_at = max(timezone.now(), quiz.updated_at + timedelta(microseconds=1))
        quiz.save(update_fields=["updated_at"])
        AdminAuditEvent.objects.create(
            actor=actor, outcome="success", action="quiz.draft_updated",
            target_kind="quiz", target_id=quiz.pk, request_id=request_id,
            reason="CONTENT_UPDATE", diff=["questions"],
        )
        return quiz


class QuizCatalogView(AdminAPIView):
    capability = "cms_learning_view"

    def get(self, request):
        with policy_lock():
            require(request.user, "cms_learning_view")
            meta, rows = page(request, Quiz.objects.order_by("-pk"))
            return Response({**meta, "results": [{
                "quiz_id": q.pk, "title": q.title, "slug": q.slug,
                "is_active": q.is_active, "seed_managed": q.seed_managed,
            } for q in rows]})

    def post(self, request):
        data = payload(request, {"slug", "title", "description", "disorder_id"})
        quiz = create_quiz(request.user.pk, request.cms_session.pk, data, self.request_id)
        response = Response({
            "quiz_id": quiz.pk, "is_active": False, "publication_available": False,
        }, status=201)
        response["ETag"] = f'"{revision_etag(quiz)}"'
        return response


class QuizDetailView(AdminAPIView):
    capability = "cms_learning_view"

    def get(self, request, quiz_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            quiz = _quiz(request.user, quiz_id)
            questions, issues = _snapshot(quiz)
            response = Response({
                "quiz_id": quiz.pk, "title": quiz.title, "slug": quiz.slug,
                "description": quiz.description, "disorder_id": quiz.disorder_id,
                "is_active": quiz.is_active, "seed_managed": quiz.seed_managed,
                "history_protected": (quiz.attempts.exists() or
                                      StudyActivity.objects.filter(quiz=quiz).exists()),
                "questions": questions, "valid": not issues, "issues": issues,
                "publication_available": False,
            })
            response["ETag"] = f'"{revision_etag(quiz)}"'
            return response


class QuizMetadataView(AdminAPIView):
    capability = "cms_learning_edit"

    def post(self, request, quiz_id):
        data = payload(request, {"title", "description", "disorder_id"})
        quiz = update_metadata(request.user.pk, request.cms_session.pk, quiz_id,
                               expected_version(request), data, self.request_id)
        response = Response({"quiz_id": quiz.pk, "publication_available": False})
        response["ETag"] = f'"{revision_etag(quiz)}"'
        return response


class QuizReplaceView(AdminAPIView):
    capability = "cms_learning_edit"

    def post(self, request, quiz_id):
        data = payload(request, {"questions"})
        quiz = replace_questions(
            request.user.pk, request.cms_session.pk, quiz_id,
            expected_version(request), data, self.request_id,
        )
        _questions_list, issues = _snapshot(quiz)
        response = Response({
            "quiz_id": quiz.pk, "valid": not issues,
            "issues": issues, "publication_available": False,
        })
        response["ETag"] = f'"{revision_etag(quiz)}"'
        return response


class QuizSimulationView(AdminAPIView):
    capability = "cms_learning_preview"

    def post(self, request, quiz_id):
        data = payload(request, {"answers"})
        answers = data.get("answers")
        if type(answers) is not list or len(answers) > 100:
            raise CMSFailure("INVALID_ANSWERS", 400)
        if any(type(row) is not dict or set(row) != {"question_id", "choice_id"}
               or type(row["question_id"]) is not int or type(row["choice_id"]) is not int
               or row["question_id"] < 1 or row["choice_id"] < 1 for row in answers):
            raise CMSFailure("INVALID_ANSWERS", 400)
        with policy_lock():
            quiz = _quiz(request.user, quiz_id)
            questions, issues = _snapshot(quiz)
            if issues:
                raise CMSFailure("INVALID_QUIZ", 409)
            expected = {q["id"] for q in questions if q["is_active"]}
            if len(answers) != len(expected) or set(row["question_id"] for row in answers) != expected:
                raise CMSFailure("INVALID_ANSWERS", 400)
            choices = {q["id"]: {c["id"]: c for c in q["choices"] if c["is_active"]}
                       for q in questions if q["is_active"]}
            correct = 0
            feedback = []
            for answer in answers:
                choice = choices[answer["question_id"]].get(answer["choice_id"])
                if choice is None:
                    raise CMSFailure("INVALID_ANSWERS", 400)
                match = bool(choice["is_correct"])
                correct += int(match)
                feedback.append({
                    "question_id": answer["question_id"],
                    "correct": match, "explanation": next(q["explanation"] for q in questions
                                                           if q["id"] == answer["question_id"]),
                })
            return Response({
                "quiz_id": quiz_id, "preview_only": True,
                "score_percent": round(correct * 100 / len(expected)),
                "correct_count": correct, "total_questions": len(expected),
                "feedback": feedback, "learner_activity_created": False,
                "publication_available": False,
            })
