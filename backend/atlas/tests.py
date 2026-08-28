from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Bookmark, CaseChoice, CaseQuestion, CaseStep, Category, ClinicalCase,
    Disorder, DisorderSymptom, Quiz, QuizChoice, QuizQuestion, Symptom,
    UserNote, UserProgress,
)


class AtlasApiTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(slug="test", name_en="Test")
        self.disorder = Disorder.objects.create(
            category=self.category,
            slug="test-disorder",
            name_en="Test Disorder",
            is_active=True,
        )
        self.user_a = User.objects.create_user(username="a@example.com", email="a@example.com", password="ComplexPass123!")
        self.user_b = User.objects.create_user(username="b@example.com", email="b@example.com", password="ComplexPass123!")

    def auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_public_disorder_list(self):
        response = self.client.get("/api/disorders/")
        self.assertEqual(response.status_code, 200)

    def test_register_rejects_email_already_used_on_another_user(self):
        User.objects.create_user(username="legacy-user", email="legacy@example.com", password="ComplexPass123!")
        response = self.client.post(
            "/api/auth/register/",
            {"email": "LEGACY@example.com", "password": "AnotherComplexPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_register_password_validation_uses_email_context(self):
        response = self.client.post(
            "/api/auth/register/",
            {"email": "freshperson@example.com", "password": "freshperson@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_bookmark_is_scoped_to_authenticated_user(self):
        Bookmark.objects.create(user=self.user_a, disorder=self.disorder)
        self.auth(self.user_b)
        response = self.client.get("/api/bookmarks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_user_cannot_delete_another_users_bookmark(self):
        Bookmark.objects.create(user=self.user_a, disorder=self.disorder)
        self.auth(self.user_b)
        response = self.client.delete(f"/api/bookmarks/{self.disorder.slug}/")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(Bookmark.objects.filter(user=self.user_a, disorder=self.disorder).exists())

    def test_compare_requires_multiple_disorders(self):
        response = self.client.get(f"/api/disorders/compare/?slugs={self.disorder.slug}")
        self.assertEqual(response.status_code, 400)

    def test_note_is_private_and_updateable(self):
        self.auth(self.user_a)
        response = self.client.put(
            f"/api/notes/{self.disorder.slug}/",
            {"body": "یادداشت تست"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserNote.objects.filter(user=self.user_a, disorder=self.disorder).exists())

        self.auth(self.user_b)
        response = self.client.get("/api/notes/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_view_progress_is_scoped_and_increases(self):
        self.auth(self.user_a)
        response = self.client.post(f"/api/progress/{self.disorder.slug}/view/")
        self.assertEqual(response.status_code, 200)
        progress = UserProgress.objects.get(user=self.user_a, disorder=self.disorder)
        self.assertGreaterEqual(progress.progress_percent, 25)
        self.assertFalse(UserProgress.objects.filter(user=self.user_b, disorder=self.disorder).exists())

    def test_authenticated_disorder_detail_never_regresses_progress(self):
        UserProgress.objects.create(
            user=self.user_a,
            disorder=self.disorder,
            progress_percent=85,
            status=UserProgress.Status.COMPLETED,
        )
        self.auth(self.user_a)
        response = self.client.get(f"/api/disorders/{self.disorder.slug}/")
        self.assertEqual(response.status_code, 200)
        progress = UserProgress.objects.get(user=self.user_a, disorder=self.disorder)
        self.assertEqual(progress.progress_percent, 85)
        self.assertEqual(progress.status, UserProgress.Status.COMPLETED)

    def test_dashboard_includes_v2_metrics(self):
        self.auth(self.user_a)
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for key in ("case_accuracy", "notes_count", "study_days", "weak_topics", "recent_notes"):
            self.assertIn(key, data)

    def test_case_submit_returns_detailed_feedback_and_progress(self):
        case = ClinicalCase.objects.create(
            slug="test-case",
            title="Test Case",
            patient_summary="summary",
            primary_disorder=self.disorder,
            is_active=True,
        )
        step = CaseStep.objects.create(case=case, title="step", narrative="narrative", sort_order=1)
        question = CaseQuestion.objects.create(step=step, prompt="question", explanation="explanation", sort_order=1)
        choice = CaseChoice.objects.create(question=question, text="best", score_value=3, feedback="good", sort_order=1)

        self.auth(self.user_a)
        response = self.client.post(
            "/api/cases/test-case/submit/",
            {"answers": [{"question_id": question.id, "choice_id": choice.id}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        feedback = response.json()["feedback"][0]
        self.assertEqual(feedback["max_score"], 3)
        self.assertTrue(feedback["full_credit"])
        progress = UserProgress.objects.get(user=self.user_a, disorder=self.disorder)
        self.assertGreaterEqual(progress.progress_percent, 85)
        self.assertEqual(progress.status, UserProgress.Status.COMPLETED)

    def test_disorder_search_matches_symptom_name(self):
        symptom = Symptom.objects.create(slug="special-symptom", name_en="Special Symptom", name_fa="نشانه ویژه")
        DisorderSymptom.objects.create(disorder=self.disorder, symptom=symptom)
        response = self.client.get("/api/disorders/?q=نشانه ویژه&page_size=100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["slug"], self.disorder.slug)

    def test_compare_rejects_unknown_disorder(self):
        response = self.client.get(f"/api/disorders/compare/?slugs={self.disorder.slug},missing-disorder")
        self.assertEqual(response.status_code, 404)

    def test_compare_rejects_duplicate_disorder(self):
        response = self.client.get(f"/api/disorders/compare/?slugs={self.disorder.slug},{self.disorder.slug}")
        self.assertEqual(response.status_code, 400)

    def test_blank_note_removes_existing_note(self):
        UserNote.objects.create(user=self.user_a, disorder=self.disorder, body="old")
        self.auth(self.user_a)
        response = self.client.put(
            f"/api/notes/{self.disorder.slug}/",
            {"body": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserNote.objects.filter(user=self.user_a, disorder=self.disorder).exists())
        self.assertFalse(response.json()["exists"])

    def test_quiz_submit_rejects_malformed_answers_with_400(self):
        quiz = Quiz.objects.create(slug="validation-quiz", title="Validation", disorder=self.disorder, is_active=True)
        question = QuizQuestion.objects.create(quiz=quiz, prompt="Q", sort_order=1)
        choice = QuizChoice.objects.create(question=question, text="A", is_correct=True, sort_order=1)
        self.auth(self.user_a)

        invalid_payloads = [
            [],
            {"answers": None},
            {"answers": [{"question_id": "abc", "choice_id": choice.id}]},
            {"answers": [{"question_id": True, "choice_id": choice.id}]},
            {"answers": [{"question_id": float(question.id), "choice_id": choice.id}]},
            {"answers": [{"question_id": question.id, "choice_id": choice.id}, {"question_id": question.id, "choice_id": choice.id}]},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post("/api/quizzes/validation-quiz/submit/", payload, format="json")
                self.assertEqual(response.status_code, 400)

    def test_case_submit_rejects_null_answers_with_400(self):
        case = ClinicalCase.objects.create(
            slug="validation-case",
            title="Validation Case",
            patient_summary="summary",
            primary_disorder=self.disorder,
            is_active=True,
        )
        step = CaseStep.objects.create(case=case, title="step", narrative="narrative", sort_order=1)
        question = CaseQuestion.objects.create(step=step, prompt="question", sort_order=1)
        CaseChoice.objects.create(question=question, text="choice", score_value=1, sort_order=1)
        self.auth(self.user_a)
        for payload in ({"answers": None}, []):
            with self.subTest(payload=payload):
                response = self.client.post("/api/cases/validation-case/submit/", payload, format="json")
                self.assertEqual(response.status_code, 400)

    def test_object_payload_endpoints_reject_malformed_data(self):
        self.auth(self.user_a)
        responses = [
            self.client.post("/api/bookmarks/", [], format="json"),
            self.client.post("/api/bookmarks/", {}, format="json"),
            self.client.put(f"/api/notes/{self.disorder.slug}/", [], format="json"),
            self.client.put(f"/api/notes/{self.disorder.slug}/", {"body": {"unexpected": True}}, format="json"),
        ]
        for response in responses:
            self.assertEqual(response.status_code, 400)

    def test_disorder_pagination_can_return_full_v02_catalog(self):
        for index in range(29):
            Disorder.objects.create(
                category=self.category,
                slug=f"extra-{index}",
                name_en=f"Extra {index}",
                is_active=True,
            )
        response = self.client.get("/api/disorders/?page_size=100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 30)
        self.assertEqual(len(response.json()["results"]), 30)
