from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Bookmark, CaseChoice, CaseQuestion, CaseStep, Category, ClinicalCase,
    Concept, ConceptBookmark, ConceptNote, ConceptRelationship, DailyChallenge, DailyChallengeAttempt,
    DailyChallengeChoice, Disorder, DisorderConcept, DisorderSymptom, Flashcard,
    Quiz, QuizChoice, QuizQuestion, StudyActivity, Symptom, UserConceptProgress,
    UserFlashcardProgress, UserNote, UserProgress,
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

    def test_v3_concept_detail_search_and_disorder_link(self):
        concept = Concept.objects.create(
            slug="test-concept",
            name_en="Test Concept",
            name_fa="مفهوم تست",
            simple_definition="تعریف ویژه برای جست‌وجو",
            academic_definition="academic",
            is_active=True,
        )
        DisorderConcept.objects.create(disorder=self.disorder, concept=concept, role="core")
        detail = self.client.get("/api/concepts/test-concept/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["disorders"][0]["disorder"]["slug"], self.disorder.slug)
        search = self.client.get("/api/search/?q=ویژه")
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["concepts"][0]["slug"], concept.slug)
        disorder_detail = self.client.get(f"/api/disorders/{self.disorder.slug}/")
        self.assertEqual(disorder_detail.json()["concepts"][0]["slug"], concept.slug)

    def test_v3_concept_bookmark_and_note_are_user_scoped(self):
        concept = Concept.objects.create(
            slug="private-concept",
            name_en="Private Concept",
            simple_definition="definition",
            is_active=True,
        )
        self.auth(self.user_a)
        bookmark = self.client.post("/api/concept-bookmarks/", {"slug": concept.slug}, format="json")
        note = self.client.put(
            f"/api/concept-notes/{concept.slug}/",
            {"body": "یادداشت مفهوم"},
            format="json",
        )
        self.assertEqual(bookmark.status_code, 201)
        self.assertEqual(note.status_code, 200)
        self.assertTrue(ConceptBookmark.objects.filter(user=self.user_a, concept=concept).exists())
        self.assertTrue(ConceptNote.objects.filter(user=self.user_a, concept=concept).exists())

        self.auth(self.user_b)
        self.assertEqual(self.client.get("/api/concept-bookmarks/").json(), [])
        self.assertEqual(self.client.get("/api/concept-notes/").json(), [])

    def test_v3_flashcard_review_queue_and_srs_progress(self):
        concept = Concept.objects.create(
            slug="review-concept",
            name_en="Review Concept",
            simple_definition="definition",
            is_active=True,
        )
        card = Flashcard.objects.create(
            slug="review-card",
            front="Front",
            back="Back",
            concept=concept,
            is_active=True,
        )
        self.auth(self.user_a)
        queue = self.client.get("/api/flashcards/review-queue/")
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.json()["new_count"], 1)
        response = self.client.post(
            f"/api/flashcards/{card.slug}/review/",
            {"rating": "good"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        progress = UserFlashcardProgress.objects.get(user=self.user_a, flashcard=card)
        self.assertEqual(progress.repetitions, 1)
        self.assertEqual(progress.interval_days, 1)
        self.assertEqual(progress.last_rating, "good")
        concept_progress = UserConceptProgress.objects.get(user=self.user_a, concept=concept)
        self.assertGreaterEqual(concept_progress.progress_percent, 70)
        self.assertTrue(
            StudyActivity.objects.filter(
                user=self.user_a,
                activity_type=StudyActivity.Kind.FLASHCARD_REVIEW,
                flashcard=card,
            ).exists()
        )

    def test_v3_flashcard_review_rejects_invalid_rating(self):
        card = Flashcard.objects.create(slug="bad-rating-card", front="Front", back="Back", is_active=True)
        self.auth(self.user_a)
        response = self.client.post(
            f"/api/flashcards/{card.slug}/review/",
            {"rating": "perfect"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_v3_daily_challenge_is_single_attempt_per_day(self):
        concept = Concept.objects.create(
            slug="daily-concept",
            name_en="Daily Concept",
            simple_definition="definition",
            is_active=True,
        )
        challenge = DailyChallenge.objects.create(
            prompt="Daily prompt",
            explanation="Daily explanation",
            concept=concept,
            is_active=True,
        )
        correct = DailyChallengeChoice.objects.create(
            challenge=challenge,
            text="Correct",
            is_correct=True,
            sort_order=0,
        )
        DailyChallengeChoice.objects.create(
            challenge=challenge,
            text="Wrong",
            is_correct=False,
            sort_order=1,
        )
        self.auth(self.user_a)
        before = self.client.get("/api/daily-challenge/")
        self.assertEqual(before.status_code, 200)
        self.assertNotIn("is_correct", before.json()["choices"][0])
        first = self.client.post("/api/daily-challenge/", {"choice_id": correct.id}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["correct"])
        second = self.client.post("/api/daily-challenge/", {"choice_id": correct.id}, format="json")
        self.assertEqual(second.status_code, 409)
        self.assertEqual(DailyChallengeAttempt.objects.filter(user=self.user_a).count(), 1)

        challenge.is_active = False
        challenge.save(update_fields=("is_active", "updated_at"))
        replacement = DailyChallenge.objects.create(prompt="Replacement", explanation="Replacement explanation", is_active=True)
        DailyChallengeChoice.objects.create(challenge=replacement, text="Replacement choice", is_correct=True, sort_order=0)
        after_change = self.client.get("/api/daily-challenge/")
        self.assertEqual(after_change.status_code, 200)
        self.assertEqual(after_change.json()["id"], challenge.id)
        self.assertEqual(after_change.json()["attempt"]["selected_choice_id"], correct.id)

    def test_v3_study_overview_and_dashboard_expose_learning_metrics(self):
        concept = Concept.objects.create(
            slug="metric-concept",
            name_en="Metric Concept",
            simple_definition="definition",
            is_active=True,
        )
        self.auth(self.user_a)
        self.client.post(f"/api/concepts/{concept.slug}/view/")
        overview = self.client.get("/api/study/overview/")
        self.assertEqual(overview.status_code, 200)
        for key in ("streak", "heatmap", "recommendations", "review", "concepts"):
            self.assertIn(key, overview.json())
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        for key in ("streak", "heatmap", "recommendations", "review_due", "continue_concepts"):
            self.assertIn(key, dashboard.json())

    def test_v3_concept_map_returns_concept_and_disorder_edges(self):
        concept = Concept.objects.create(
            slug="map-concept",
            name_en="Map Concept",
            simple_definition="definition",
            is_active=True,
        )
        symptom = Symptom.objects.create(
            slug="map-symptom",
            name_en="Map Symptom",
            name_fa="نشانه نقشه",
            domain="cognitive",
        )
        DisorderConcept.objects.create(disorder=self.disorder, concept=concept, role="associated")
        DisorderSymptom.objects.create(disorder=self.disorder, symptom=symptom, prominence="core")
        response = self.client.get("/api/concept-map/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        node_ids = {node["id"] for node in data["nodes"]}
        self.assertIn(f"concept:{concept.slug}", node_ids)
        self.assertIn(f"disorder:{self.disorder.slug}", node_ids)
        self.assertIn(f"symptom:{symptom.slug}", node_ids)
        self.assertTrue(any(edge["target"] == f"concept:{concept.slug}" for edge in data["edges"]))
        self.assertTrue(any(
            edge["source"] == f"disorder:{self.disorder.slug}"
            and edge["target"] == f"symptom:{symptom.slug}"
            and edge["kind"] == "symptom_core"
            for edge in data["edges"]
        ))

    def test_v3_heatmap_does_not_double_count_new_disorder_view(self):
        self.auth(self.user_a)
        response = self.client.post(f"/api/progress/{self.disorder.slug}/view/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/progress/{self.disorder.slug}/view/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            StudyActivity.objects.filter(
                user=self.user_a,
                activity_type=StudyActivity.Kind.DISORDER_VIEW,
                disorder=self.disorder,
            ).count(),
            1,
        )
        overview = self.client.get("/api/study/overview/")
        self.assertEqual(overview.status_code, 200)
        today = overview.json()["heatmap"][-1]
        self.assertEqual(today["count"], 1)

    def test_v3_concept_detail_hides_inactive_related_concepts(self):
        active = Concept.objects.create(
            slug="active-concept",
            name_en="Active Concept",
            simple_definition="active",
            is_active=True,
        )
        inactive = Concept.objects.create(
            slug="inactive-concept",
            name_en="Inactive Concept",
            simple_definition="inactive",
            is_active=False,
        )
        ConceptRelationship.objects.create(
            source_concept=active,
            target_concept=inactive,
            relationship_type="related",
        )
        response = self.client.get(f"/api/concepts/{active.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["relationships"], [])

    def test_v3_global_search_hides_orphan_symptoms(self):
        Symptom.objects.create(
            slug="orphan-search-symptom",
            name_en="Orphan Search Symptom",
            name_fa="نشانه یتیم جستجو",
            domain="cognitive",
        )
        response = self.client.get("/api/search/?q=یتیم")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["symptoms"], [])
