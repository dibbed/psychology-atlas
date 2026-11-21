"""P13 test-first: inactive quiz editorial workflow without learner history rewrites."""
from unittest.mock import patch
from django.db import DatabaseError
from django.test import TestCase, override_settings

from .cms_models import AdminAuditEvent
from .models import (
    Quiz, QuizQuestion, QuizChoice, QuizAttempt, QuizAttemptAnswer,
    StudyActivity, Category, Disorder,
)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class QuizEditorialTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client_owner = self.sign_in(self.owner)
        self.quiz = Quiz.objects.create(
            slug="p13-fictional-quiz", title="Synthetic educational quiz",
            description="Fictional scenario", is_active=False, seed_managed=False,
        )

    def url(self, quiz=None):
        return f"learning/quizzes/{quiz or self.quiz.pk}/"

    def sample(self):
        return {"questions": [
            {"prompt": "Synthetic question one?", "explanation": "Fictional explanation",
             "choices": [
                 {"text": "First illustrative answer", "is_correct": True},
                 {"text": "Second illustrative answer", "is_correct": False},
             ]}
        ]}

    def test_private_metadata_edit_preserves_question_identity_and_advances_etag(self):
        q = QuizQuestion.objects.create(quiz=self.quiz, prompt="Immutable question identity")
        c = QuizChoice.objects.create(question=q, text="Original key", is_correct=True)
        tag = self.client_owner.get(BASE + self.url())["ETag"]
        body = {"title": "Updated private title", "description": "Updated private description", "disorder_id": None}
        response = self.post(self.client_owner, self.url() + "metadata/", body, etag=tag)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertNotEqual(response["ETag"], tag)
        self.quiz.refresh_from_db()
        self.assertEqual((self.quiz.title, self.quiz.description, self.quiz.is_active),
                         (body["title"], body["description"], False))
        self.assertEqual(list(self.quiz.questions.values_list("pk", flat=True)), [q.pk])
        self.assertEqual(list(q.choices.values_list("pk", "is_correct")), [(c.pk, True)])
        event = AdminAuditEvent.objects.get(action="quiz.draft_updated", target_id=self.quiz.pk)
        self.assertCountEqual(event.diff, ["title", "description"])
        repeat = self.post(self.client_owner, self.url() + "metadata/", body, etag=response["ETag"])
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat["ETag"], response["ETag"])
        self.assertEqual(AdminAuditEvent.objects.filter(action="quiz.draft_updated", target_id=self.quiz.pk).count(), 1)
        self.assertEqual(self.post(self.client_owner, self.url() + "metadata/", body, etag=tag).status_code, 412)
        self.assertFalse(QuizAttempt.objects.exists())
        self.assertFalse(StudyActivity.objects.exists())

    def test_metadata_audit_failure_rolls_back_the_entire_change(self):
        tag = self.client_owner.get(BASE + self.url())["ETag"]
        with patch("atlas.cms_quiz_editor.AdminAuditEvent.objects.create", side_effect=DatabaseError("Synthetic audit failure")):
            response = self.post(self.client_owner, self.url() + "metadata/", {
                "title": "Must roll back", "description": "", "disorder_id": None}, etag=tag)
        self.assertEqual(response.status_code, 503)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, "Synthetic educational quiz")
        self.assertEqual(self.client_owner.get(BASE + self.url())["ETag"], tag)
        self.assertFalse(AdminAuditEvent.objects.filter(action="quiz.draft_updated").exists())

    def test_metadata_rejects_public_seeded_or_historical_quizzes(self):
        body = {"title": "Attempted rewrite", "description": "", "disorder_id": None}
        for field in ("is_active", "seed_managed"):
            setattr(self.quiz, field, True)
            self.quiz.save(update_fields=[field])
            tag = self.client_owner.get(BASE + self.url())["ETag"]
            self.assertEqual(self.post(self.client_owner, self.url() + "metadata/", body, etag=tag).status_code, 409)
            setattr(self.quiz, field, False)
            self.quiz.save(update_fields=[field])
        activity = StudyActivity.objects.create(user=self.normal, quiz=self.quiz,
            activity_type=StudyActivity.Kind.QUIZ_COMPLETED)
        tag = self.client_owner.get(BASE + self.url())["ETag"]
        self.assertEqual(self.post(self.client_owner, self.url() + "metadata/", body, etag=tag).status_code, 409)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, "Synthetic educational quiz")
        self.assertTrue(StudyActivity.objects.filter(pk=activity.pk, quiz=self.quiz).exists())

    def test_metadata_requires_both_permissions_and_valid_active_reference(self):
        body = {"title": "Private title", "description": "", "disorder_id": None}
        tag = self.client_owner.get(BASE + self.url())["ETag"]
        for cap in ("cms_learning_view", "cms_learning_edit"):
            client = self.sign_in(self.user("metadata-" + cap, staff=True, caps=("cms_enter", cap)))
            self.assertEqual(self.post(client, self.url() + "metadata/", body, etag=tag).status_code, 403)
        for bad in ({**body, "is_active": True}, {**body, "title": " "},
                    {**body, "disorder_id": True}, {**body, "disorder_id": 2**70},
                    {**body, "disorder_id": 999999}):
            self.assertEqual(self.post(self.client_owner, self.url() + "metadata/", bad, etag=tag).status_code, 400)
        category = Category.objects.create(slug="p13-metadata-category", name_en="Synthetic category")
        disorder = Disorder.objects.create(category=category, slug="p13-metadata-disorder", name_en="Synthetic disorder", is_active=False)
        body["disorder_id"] = disorder.pk
        self.assertEqual(self.post(self.client_owner, self.url() + "metadata/", body, etag=tag).status_code, 400)
        disorder.is_active = True
        disorder.save(update_fields=["is_active"])
        self.assertEqual(self.post(self.client_owner, self.url() + "metadata/", body, etag=tag).status_code, 200)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.disorder_id, disorder.pk)

    def test_create_private_quiz_and_list_without_public_activation(self):
        result = self.post(self.client_owner, "learning/quizzes/", {
            "slug": "p13-new-example", "title": "Another educational quiz",
            "description": "Synthetic", "disorder_id": None,
        })
        self.assertEqual(result.status_code, 201, result.content[:350])
        created = Quiz.objects.get(pk=result.json()["quiz_id"])
        self.assertFalse(created.is_active)
        self.assertFalse(created.seed_managed)
        self.assertEqual(result.json()["publication_available"], False)
        rows = self.client_owner.get(BASE + "learning/quizzes/")
        self.assertEqual(rows.status_code, 200, rows.content[:350])
        self.assertTrue(any(x["quiz_id"] == created.pk for x in rows.json()["results"]))
        self.assertEqual(self.post(self.client_owner, "learning/quizzes/", {
            "slug": "p13-new-example", "title": "Duplicate", "description": "", "disorder_id": None,
        }).status_code, 409)

    def test_build_validate_and_preview_quiz_without_attempt_or_activity(self):
        detail = self.client_owner.get(BASE + self.url())
        self.assertEqual(detail.status_code, 200, detail.content[:300])
        tag = detail["ETag"]
        changed = self.post(self.client_owner, self.url() + "questions/replace/",
            self.sample(), etag=tag)
        self.assertEqual(changed.status_code, 200, changed.content[:350])
        self.assertEqual(changed.json()["valid"], True)
        detail = self.client_owner.get(BASE + self.url())
        question_id = detail.json()["questions"][0]["id"]
        correct = detail.json()["questions"][0]["choices"][0]["id"]
        counts = (QuizAttempt.objects.count(), QuizAttemptAnswer.objects.count(), StudyActivity.objects.count())
        result = self.post(self.client_owner, self.url() + "simulate/", {
            "answers": [{"question_id": question_id, "choice_id": correct}],
        })
        self.assertEqual(result.status_code, 200, result.content[:350])
        self.assertEqual(result.json()["score_percent"], 100)
        self.assertTrue(result.json()["preview_only"])
        self.assertEqual(counts, (QuizAttempt.objects.count(), QuizAttemptAnswer.objects.count(),
                                  StudyActivity.objects.count()))
        self.assertEqual(self.post(self.client_owner, self.url() + "questions/replace/",
            self.sample(), etag=tag).status_code, 412)

    def test_reject_invalid_quiz_and_no_partial_write(self):
        tag = self.client_owner.get(BASE + self.url())["ETag"]
        bad = {"questions": [{"prompt": "Two answers marked right", "explanation": "",
            "choices": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": True}]}]}
        result = self.post(self.client_owner, self.url() + "questions/replace/", bad, etag=tag)
        self.assertEqual(result.status_code, 400, result.content[:350])
        self.assertEqual(self.quiz.questions.count(), 0)
        self.assertEqual(self.post(self.client_owner, self.url() + "questions/replace/",
            {"questions": [{"question_id": 9999}]}, etag=tag).status_code, 400)

    def test_existing_study_activity_alone_blocks_answer_key_rewrite(self):
        StudyActivity.objects.create(
            user=self.normal, quiz=self.quiz, activity_type=StudyActivity.Kind.QUIZ_COMPLETED,
        )
        detail = self.client_owner.get(BASE + self.url())
        self.assertTrue(detail.json()["history_protected"])
        tag = detail["ETag"]
        response = self.post(self.client_owner, self.url()+"questions/replace/",
            self.sample(), etag=tag)
        self.assertEqual(response.status_code, 409, response.content[:250])
        self.assertEqual(self.quiz.questions.count(), 0)

    def test_protect_existing_quiz_attempts_and_permission_boundaries(self):
        q = QuizQuestion.objects.create(quiz=self.quiz, prompt="Prior immutable question")
        c = QuizChoice.objects.create(question=q, text="A", is_correct=True)
        attempt = QuizAttempt.objects.create(user=self.normal, quiz=self.quiz,
            status=QuizAttempt.Status.COMPLETED, score=100, correct_count=1, total_questions=1)
        answer = QuizAttemptAnswer.objects.create(attempt=attempt, question=q,
            selected_choice=c, is_correct=True)
        tag = self.client_owner.get(BASE + self.url())["ETag"]
        result = self.post(self.client_owner, self.url() + "questions/replace/",
            self.sample(), etag=tag)
        self.assertEqual(result.status_code, 409, result.content[:350])
        self.assertEqual(self.post(self.client_owner, self.url() + "metadata/", {
            "title": "Cannot rewrite historical title", "description": "", "disorder_id": None}, etag=tag).status_code, 409)
        answer.refresh_from_db()
        self.assertEqual((answer.question_id, answer.selected_choice_id, answer.is_correct),
                         (q.pk, c.pk, True))
        self.assertEqual(self.quiz.questions.count(), 1)
        viewer = self.user("p13-learning-viewer", staff=True,
            caps=("cms_enter", "cms_learning_view"))
        viewer_client = self.sign_in(viewer)
        self.assertEqual(viewer_client.get(BASE + self.url()).status_code, 200)
        self.assertEqual(self.post(viewer_client, self.url()+"questions/replace/",
            self.sample(), etag=tag).status_code, 403)
        no_view = self.user("p13-learning-editor-no-view", staff=True,
            caps=("cms_enter", "cms_learning_edit"))
        client = self.sign_in(no_view)
        self.assertEqual(self.post(client, self.url()+"questions/replace/",
            self.sample(), etag=tag).status_code, 403)
