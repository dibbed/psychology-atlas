from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Bookmark, CaseChoice, CaseQuestion, CaseStep, Category, ClinicalCase,
    Concept, ConceptAlias, ConceptBookmark, ConceptNote, ConceptRelationship, ConceptRelationshipSource,
    ConceptSymptom, CognitiveDistortionPracticeAttempt, CognitiveDistortionPracticeChoice,
    CognitiveDistortionPracticeItem, DailyChallenge, DailyChallengeAttempt, DailyChallengeChoice, Disorder, DisorderConcept,
    DisorderSymptom, DSMCorpus, DSMRecord, DSMRecordRelation, Flashcard, Quiz, QuizChoice, QuizQuestion, SourceReference, StudyActivity, Symptom, UserConceptProgress,
    UserFlashcardProgress, UserNote, UserProgress,
    ScientificReviewStatus, Technique, TechniqueConcept, TechniqueConceptSource, TechniqueSource,
    Therapy, TherapyAlias, TherapyClassification, TherapyClassificationLink, TherapyConcept,
    TherapyConceptSource, TherapyDisorder, TherapyDisorderSource, TherapyFamily, TherapySource,
    TherapyTechnique, TherapyTechniqueSource,
)


class AtlasApiTests(APITestCase):
    def setUp(self):
        cache.clear()
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

    def test_concept_detail_search_and_disorder_link(self):
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

    def test_concept_bookmark_and_note_are_user_scoped(self):
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

    def test_flashcard_review_queue_and_srs_progress(self):
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

    def test_review_queue_rejects_invalid_limit_without_500(self):
        self.auth(self.user_a)
        for raw_limit in ("abc", "0", "-1", "1.5"):
            with self.subTest(limit=raw_limit):
                response = self.client.get(f"/api/flashcards/review-queue/?limit={raw_limit}")
                self.assertEqual(response.status_code, 400)

    def test_flashcard_review_rejects_inactive_linked_content(self):
        concept = Concept.objects.create(
            slug="inactive-review-concept",
            name_en="Inactive Review Concept",
            simple_definition="definition",
            is_active=False,
        )
        card = Flashcard.objects.create(
            slug="inactive-review-card",
            front="Front",
            back="Back",
            concept=concept,
            is_active=True,
        )
        self.auth(self.user_a)
        response = self.client.post(
            f"/api/flashcards/{card.slug}/review/",
            {"rating": "good"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(UserFlashcardProgress.objects.filter(user=self.user_a, flashcard=card).exists())

    def test_flashcard_review_rejects_invalid_rating(self):
        card = Flashcard.objects.create(slug="bad-rating-card", front="Front", back="Back", is_active=True)
        self.auth(self.user_a)
        response = self.client.post(
            f"/api/flashcards/{card.slug}/review/",
            {"rating": "perfect"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_daily_challenge_is_single_attempt_per_day(self):
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

    def test_study_overview_and_dashboard_expose_learning_metrics(self):
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

    def test_concept_map_returns_concept_and_disorder_edges(self):
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

    def test_heatmap_does_not_double_count_new_disorder_view(self):
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

    def test_concept_detail_hides_inactive_related_concepts(self):
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

    def test_global_search_hides_orphan_symptoms(self):
        Symptom.objects.create(
            slug="orphan-search-symptom",
            name_en="Orphan Search Symptom",
            name_fa="نشانه یتیم جستجو",
            domain="cognitive",
        )
        response = self.client.get("/api/search/?q=یتیم")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["symptoms"], [])

    def test_daily_challenge_attempt_survives_when_all_challenges_are_deactivated(self):
        challenge = DailyChallenge.objects.create(
            prompt="Historical daily prompt",
            explanation="Historical explanation",
            is_active=True,
        )
        choice = DailyChallengeChoice.objects.create(
            challenge=challenge,
            text="Correct",
            is_correct=True,
            sort_order=0,
        )
        self.auth(self.user_a)
        submitted = self.client.post("/api/daily-challenge/", {"choice_id": choice.id}, format="json")
        self.assertEqual(submitted.status_code, 200)

        challenge.is_active = False
        challenge.save(update_fields=("is_active", "updated_at"))
        response = self.client.get("/api/daily-challenge/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], challenge.id)
        self.assertEqual(response.json()["attempt"]["selected_choice_id"], choice.id)

    def test_global_search_matches_disorder_and_concept_slugs(self):
        slug_disorder = Disorder.objects.create(
            category=self.category,
            slug="opaque-disorder-code",
            name_en="Unrelated Disorder Name",
            is_active=True,
        )
        concept = Concept.objects.create(
            slug="opaque-concept-code",
            name_en="Unrelated Concept Name",
            simple_definition="unrelated definition",
            is_active=True,
        )
        disorder_response = self.client.get("/api/search/?q=opaque-disorder-code")
        concept_response = self.client.get("/api/search/?q=opaque-concept-code")
        self.assertEqual(disorder_response.status_code, 200)
        self.assertEqual(concept_response.status_code, 200)
        self.assertEqual(disorder_response.json()["disorders"][0]["slug"], slug_disorder.slug)
        self.assertEqual(concept_response.json()["concepts"][0]["slug"], concept.slug)

    def test_disorder_detail_hides_inactive_related_disorders(self):
        inactive = Disorder.objects.create(
            category=self.category,
            slug="inactive-related-disorder",
            name_en="Inactive Related Disorder",
            is_active=False,
        )
        from .models import DifferentialRelationship
        DifferentialRelationship.objects.create(
            disorder=self.disorder,
            related_disorder=inactive,
            relationship_type=DifferentialRelationship.Kind.RELATED,
        )
        response = self.client.get(f"/api/disorders/{self.disorder.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["related"], [])

    def test_review_and_study_metrics_hide_cards_and_progress_for_inactive_concepts(self):
        inactive = Concept.objects.create(
            slug="inactive-study-concept",
            name_en="Inactive Study Concept",
            simple_definition="inactive",
            is_active=False,
        )
        card = Flashcard.objects.create(
            slug="inactive-study-card",
            front="Front",
            back="Back",
            concept=inactive,
            is_active=True,
        )
        UserConceptProgress.objects.create(
            user=self.user_a,
            concept=inactive,
            progress_percent=90,
            status=UserConceptProgress.Status.COMPLETED,
        )
        UserFlashcardProgress.objects.create(user=self.user_a, flashcard=card)
        self.auth(self.user_a)

        queue = self.client.get("/api/flashcards/review-queue/")
        overview = self.client.get("/api/study/overview/")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.json()["count"], 0)
        self.assertEqual(overview.json()["review"]["due"], 0)
        self.assertEqual(overview.json()["review"]["reviewed"], 0)
        self.assertEqual(overview.json()["concepts"]["studied"], 0)
        self.assertEqual(overview.json()["concepts"]["mastered"], 0)
        self.assertEqual(dashboard.json()["review_due"], 0)
        self.assertEqual(dashboard.json()["concepts_studied"], 0)

    def test_concept_map_query_count_does_not_scale_per_concept(self):
        concepts = [
            Concept.objects.create(
                slug=f"query-concept-{index}",
                name_en=f"Query Concept {index}",
                simple_definition="definition",
                is_active=True,
            )
            for index in range(12)
        ]
        for index in range(len(concepts) - 1):
            ConceptRelationship.objects.create(
                source_concept=concepts[index],
                target_concept=concepts[index + 1],
                relationship_type=ConceptRelationship.Kind.RELATED,
            )
            DisorderConcept.objects.create(
                disorder=self.disorder,
                concept=concepts[index],
                role=DisorderConcept.Role.ASSOCIATED,
            )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get("/api/concept-map/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 8)

    def test_daily_challenge_rolls_back_attempt_if_side_effect_fails(self):
        challenge = DailyChallenge.objects.create(
            prompt="Atomic daily prompt",
            explanation="Atomic explanation",
            is_active=True,
        )
        choice = DailyChallengeChoice.objects.create(
            challenge=challenge,
            text="Correct",
            is_correct=True,
            sort_order=0,
        )
        self.auth(self.user_a)
        with patch("atlas.views.record_activity", side_effect=RuntimeError("activity failed")):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/daily-challenge/", {"choice_id": choice.id}, format="json")
        self.assertFalse(DailyChallengeAttempt.objects.filter(user=self.user_a).exists())

    def test_notes_reject_missing_or_null_body_without_deleting_existing_data(self):
        concept = Concept.objects.create(
            slug="note-validation-concept",
            name_en="Note Validation Concept",
            simple_definition="definition",
            is_active=True,
        )
        self.auth(self.user_a)

        for payload in ({}, {"body": None}):
            with self.subTest(kind="disorder", payload=payload):
                UserNote.objects.update_or_create(
                    user=self.user_a,
                    disorder=self.disorder,
                    defaults={"body": "keep disorder note"},
                )
                response = self.client.put(f"/api/notes/{self.disorder.slug}/", payload, format="json")
                self.assertEqual(response.status_code, 400)
                note = UserNote.objects.get(user=self.user_a, disorder=self.disorder)
                self.assertEqual(note.body, "keep disorder note")

            with self.subTest(kind="concept", payload=payload):
                ConceptNote.objects.update_or_create(
                    user=self.user_a,
                    concept=concept,
                    defaults={"body": "keep concept note"},
                )
                response = self.client.put(f"/api/concept-notes/{concept.slug}/", payload, format="json")
                self.assertEqual(response.status_code, 400)
                note = ConceptNote.objects.get(user=self.user_a, concept=concept)
                self.assertEqual(note.body, "keep concept note")

    def test_daily_challenge_handles_oversized_integer_choice_id_without_500(self):
        challenge = DailyChallenge.objects.create(
            prompt="Large id prompt",
            explanation="Large id explanation",
            is_active=True,
        )
        DailyChallengeChoice.objects.create(
            challenge=challenge,
            text="Correct",
            is_correct=True,
            sort_order=0,
        )
        self.auth(self.user_a)
        response = self.client.post(
            "/api/daily-challenge/",
            {"choice_id": "999999999999999999999999999999999999999999999999"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DailyChallengeAttempt.objects.filter(user=self.user_a).exists())

    def test_search_normalizes_common_arabic_and_persian_letter_variants(self):
        concept = Concept.objects.create(
            slug="persian-search-concept",
            name_en="Persian Search Concept",
            name_fa="نگرانی",
            simple_definition="تعریف",
            is_active=True,
        )
        disorder = Disorder.objects.create(
            category=self.category,
            slug="persian-search-disorder",
            name_en="Persian Search Disorder",
            name_fa="اختلال شناختی",
            is_active=True,
        )
        global_concept = self.client.get("/api/search/?q=نگراني")
        disorder_list = self.client.get("/api/disorders/?q=شناختي&page_size=100")
        concept_list = self.client.get("/api/concepts/?q=نگراني&page_size=100")
        self.assertEqual(global_concept.status_code, 200)
        self.assertIn(concept.slug, [row["slug"] for row in global_concept.json()["concepts"]])
        self.assertEqual(disorder_list.status_code, 200)
        self.assertIn(disorder.slug, [row["slug"] for row in disorder_list.json()["results"]])
        self.assertEqual(concept_list.status_code, 200)
        self.assertIn(concept.slug, [row["slug"] for row in concept_list.json()["results"]])

    def test_daily_challenge_skips_inactive_linked_content(self):
        inactive = Concept.objects.create(
            slug="inactive-challenge-concept",
            name_en="Inactive Challenge Concept",
            simple_definition="inactive",
            is_active=False,
        )
        challenge = DailyChallenge.objects.create(
            prompt="Inactive linked prompt",
            explanation="Inactive linked explanation",
            concept=inactive,
            is_active=True,
        )
        DailyChallengeChoice.objects.create(
            challenge=challenge,
            text="Correct",
            is_correct=True,
            sort_order=0,
        )
        response = self.client.get("/api/daily-challenge/")
        self.assertEqual(response.status_code, 404)

    def test_historical_daily_challenge_hides_deactivated_links_but_preserves_attempt(self):
        concept = Concept.objects.create(
            slug="historical-challenge-concept",
            name_en="Historical Challenge Concept",
            simple_definition="definition",
            is_active=True,
        )
        challenge = DailyChallenge.objects.create(
            prompt="Historical linked prompt",
            explanation="Historical linked explanation",
            concept=concept,
            is_active=True,
        )
        choice = DailyChallengeChoice.objects.create(
            challenge=challenge,
            text="Correct",
            is_correct=True,
            sort_order=0,
        )
        self.auth(self.user_a)
        submitted = self.client.post("/api/daily-challenge/", {"choice_id": choice.id}, format="json")
        self.assertEqual(submitted.status_code, 200)
        concept.is_active = False
        concept.save(update_fields=("is_active", "updated_at"))
        challenge.is_active = False
        challenge.save(update_fields=("is_active", "updated_at"))

        response = self.client.get("/api/daily-challenge/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], challenge.id)
        self.assertIsNone(response.json()["concept"])
        self.assertEqual(response.json()["attempt"]["selected_choice_id"], choice.id)

    def test_quiz_and_case_linked_to_inactive_disorder_are_not_available(self):
        inactive = Disorder.objects.create(
            category=self.category,
            slug="inactive-learning-disorder",
            name_en="Inactive Learning Disorder",
            is_active=False,
        )
        quiz = Quiz.objects.create(
            slug="inactive-linked-quiz",
            title="Inactive Linked Quiz",
            disorder=inactive,
            is_active=True,
        )
        quiz_question = QuizQuestion.objects.create(quiz=quiz, prompt="Q", sort_order=1)
        quiz_choice = QuizChoice.objects.create(
            question=quiz_question,
            text="A",
            is_correct=True,
            sort_order=1,
        )
        clinical_case = ClinicalCase.objects.create(
            slug="inactive-linked-case",
            title="Inactive Linked Case",
            patient_summary="summary",
            primary_disorder=inactive,
            is_active=True,
        )
        step = CaseStep.objects.create(case=clinical_case, title="step", narrative="n", sort_order=1)
        case_question = CaseQuestion.objects.create(step=step, prompt="Q", sort_order=1)
        case_choice = CaseChoice.objects.create(
            question=case_question,
            text="A",
            score_value=1,
            sort_order=1,
        )

        quiz_list = self.client.get("/api/quizzes/?page_size=100")
        case_list = self.client.get("/api/cases/?page_size=100")
        self.assertNotIn(quiz.slug, [row["slug"] for row in quiz_list.json()["results"]])
        self.assertNotIn(clinical_case.slug, [row["slug"] for row in case_list.json()["results"]])
        self.assertEqual(self.client.get(f"/api/quizzes/{quiz.slug}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/cases/{clinical_case.slug}/").status_code, 404)

        self.auth(self.user_a)
        quiz_submit = self.client.post(
            f"/api/quizzes/{quiz.slug}/submit/",
            {"answers": [{"question_id": quiz_question.id, "choice_id": quiz_choice.id}]},
            format="json",
        )
        case_submit = self.client.post(
            f"/api/cases/{clinical_case.slug}/submit/",
            {"answers": [{"question_id": case_question.id, "choice_id": case_choice.id}]},
            format="json",
        )
        self.assertEqual(quiz_submit.status_code, 404)
        self.assertEqual(case_submit.status_code, 404)
        self.assertFalse(UserProgress.objects.filter(user=self.user_a, disorder=inactive).exists())

    def test_learning_metrics_are_isolated_between_users(self):
        concept = Concept.objects.create(
            slug="isolation-concept",
            name_en="Isolation Concept",
            simple_definition="definition",
            is_active=True,
        )
        card = Flashcard.objects.create(
            slug="isolation-card",
            front="Front",
            back="Back",
            concept=concept,
            is_active=True,
        )
        UserProgress.objects.create(user=self.user_a, disorder=self.disorder, progress_percent=80)
        UserConceptProgress.objects.create(user=self.user_a, concept=concept, progress_percent=90)
        UserFlashcardProgress.objects.create(user=self.user_a, flashcard=card)

        self.auth(self.user_b)
        study = self.client.get("/api/study/overview/")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(study.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(study.json()["review"]["due"], 0)
        self.assertEqual(study.json()["concepts"]["studied"], 0)
        self.assertEqual(dashboard.json()["disorders_studied"], 0)
        self.assertEqual(dashboard.json()["concepts_studied"], 0)

    def test_atlas_overview_uses_live_database_counts(self):
        concept = Concept.objects.create(
            slug="overview-concept",
            name_en="Overview Concept",
            simple_definition="definition",
            is_active=True,
        )
        Flashcard.objects.create(
            slug="overview-card",
            front="Front",
            back="Back",
            concept=concept,
            is_active=True,
        )
        response = self.client.get("/api/atlas-overview/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["counts"]["disorders"], 1)
        self.assertEqual(data["counts"]["concepts"], 1)
        self.assertEqual(data["counts"]["flashcards"], 1)
        self.assertEqual(data["graph"]["nodes"], 2)
        self.assertEqual(data["categories"][0]["count"], 1)

    def test_concept_catalog_exposes_real_connection_counts(self):
        concept = Concept.objects.create(
            slug="catalog-metrics",
            name_en="Catalog Metrics",
            simple_definition="definition",
            is_active=True,
        )
        other = Concept.objects.create(
            slug="catalog-other",
            name_en="Catalog Other",
            simple_definition="definition",
            is_active=True,
        )
        DisorderConcept.objects.create(disorder=self.disorder, concept=concept, role="associated")
        ConceptRelationship.objects.create(
            source_concept=concept,
            target_concept=other,
            relationship_type="related",
            explanation="structured relation",
        )
        Flashcard.objects.create(slug="catalog-card", front="Front", back="Back", concept=concept, is_active=True)
        response = self.client.get("/api/concepts/?q=Catalog Metrics&page_size=100")
        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertEqual(row["disorder_count"], 1)
        self.assertEqual(row["flashcard_count"], 1)
        self.assertEqual(row["relationship_count"], 1)

    def test_graph_exposes_node_metadata_degree_and_edge_explanation(self):
        concept = Concept.objects.create(
            slug="metadata-concept",
            name_en="Metadata Concept",
            name_fa="مفهوم متادیتا",
            simple_definition="structured definition",
            is_active=True,
        )
        DisorderConcept.objects.create(
            disorder=self.disorder,
            concept=concept,
            role="core",
            explanation="why these nodes are linked",
        )
        response = self.client.get("/api/concept-map/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["meta"]["node_count"], 2)
        concept_node = next(node for node in data["nodes"] if node["id"] == f"concept:{concept.slug}")
        self.assertEqual(concept_node["summary"], "structured definition")
        self.assertEqual(concept_node["degree"], 1)
        edge = next(edge for edge in data["edges"] if edge["target"] == f"concept:{concept.slug}")
        self.assertEqual(edge["explanation"], "why these nodes are linked")

    def test_symptom_search_returns_active_related_disorders(self):
        symptom = Symptom.objects.create(
            slug="linked-search-symptom",
            name_en="Linked Search Symptom",
            name_fa="نشانه متصل",
            domain="cognitive",
        )
        DisorderSymptom.objects.create(disorder=self.disorder, symptom=symptom)
        response = self.client.get("/api/search/?q=نشانه متصل")
        self.assertEqual(response.status_code, 200)
        row = response.json()["symptoms"][0]
        self.assertEqual(row["disorders"][0]["slug"], self.disorder.slug)

    def test_concept_catalog_filters_domain_subtype_and_searches_aliases(self):
        concept = Concept.objects.create(
            slug="v4-distortion",
            name_en="V4 Distortion",
            name_fa="تحریف نسخه چهار",
            simple_definition="definition",
            kind="cognitive",
            domain="cbt",
            subtype="cognitive_distortion",
            is_active=True,
        )
        ConceptAlias.objects.create(concept=concept, text="نام جایگزین ویژه", language="fa")

        response = self.client.get("/api/concepts/?domain=cbt&subtype=cognitive_distortion&q=نام جایگزین&page_size=100")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], concept.slug)
        self.assertEqual(rows[0]["domain"], "cbt")
        self.assertEqual(rows[0]["subtype"], "cognitive_distortion")
        self.assertEqual(rows[0]["aliases"][0]["text"], "نام جایگزین ویژه")

    def test_concept_detail_exposes_distortion_fields_and_relation_provenance(self):
        root = Concept.objects.create(
            slug="v4-root",
            name_en="V4 Root",
            simple_definition="root",
            domain="cbt",
            is_active=True,
        )
        distortion = Concept.objects.create(
            slug="v4-child",
            name_en="V4 Child",
            simple_definition="child",
            kind="cognitive",
            domain="cbt",
            subtype="cognitive_distortion",
            recognition_cues="cue",
            counterexample="counter",
            common_confusions="confusion",
            is_active=True,
        )
        relation = ConceptRelationship.objects.create(
            source_concept=distortion,
            target_concept=root,
            relationship_type="part_of",
            explanation="structured membership",
        )
        source = SourceReference.objects.create(
            title="Evidence Source",
            organization="Evidence Org",
            url="https://example.com/source",
        )
        ConceptRelationshipSource.objects.create(relationship=relation, source=source)

        response = self.client.get(f"/api/concepts/{distortion.slug}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["recognition_cues"], "cue")
        self.assertEqual(data["counterexample"], "counter")
        self.assertEqual(data["common_confusions"], "confusion")
        self.assertEqual(data["relationships"][0]["sources"][0]["title"], "Evidence Source")

    def test_concept_symptom_is_exposed_in_detail_and_graph(self):
        concept = Concept.objects.create(
            slug="v4-symptom-concept",
            name_en="V4 Symptom Concept",
            simple_definition="definition",
            domain="psychopathology",
            is_active=True,
        )
        symptom = Symptom.objects.create(
            slug="v4-linked-symptom",
            name_en="V4 Linked Symptom",
            name_fa="نشانه نسخه چهار",
            domain="cognitive",
        )
        ConceptSymptom.objects.create(
            concept=concept,
            symptom=symptom,
            relationship_type="manifestation",
            explanation="explicit concept symptom link",
        )

        detail = self.client.get(f"/api/concepts/{concept.slug}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["symptoms"][0]["slug"], symptom.slug)

        graph = self.client.get("/api/concept-map/")
        self.assertEqual(graph.status_code, 200)
        edge = next(
            row for row in graph.json()["edges"]
            if row["source"] == f"concept:{concept.slug}" and row["target"] == f"symptom:{symptom.slug}"
        )
        self.assertEqual(edge["kind"], "concept_symptom_manifestation")
        self.assertEqual(edge["explanation"], "explicit concept symptom link")

    def test_atlas_overview_exposes_concept_taxonomy(self):
        Concept.objects.create(
            slug="v4-taxonomy",
            name_en="V4 Taxonomy",
            simple_definition="definition",
            kind="cognitive",
            domain="cbt",
            subtype="cognitive_distortion",
            is_active=True,
        )
        response = self.client.get("/api/atlas-overview/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(row["domain"] == "cbt" for row in data["concept_domains"]))
        self.assertTrue(any(row["subtype"] == "cognitive_distortion" for row in data["concept_subtypes"]))

    def test_seed_preserves_dsm_category_for_linked_curated_disorder(self):
        dsm_category = Category.objects.create(
            slug="dsm-chapter-04",
            name_en="DSM Anxiety",
            name_fa="فصل اضطراب DSM",
            is_active=True,
        )
        disorder = Disorder.objects.create(
            category=dsm_category,
            slug="panic-disorder",
            name_en="Panic Disorder",
            name_fa="اختلال پانیک",
            data_origin="curated",
            is_active=True,
        )
        corpus = DSMCorpus.objects.create(
            key="test-dsm-corpus",
            title="Test DSM Corpus",
            source_filename="test.json",
            source_sha256="a" * 64,
            is_active=True,
        )
        DSMRecord.objects.create(
            corpus=corpus,
            master_id="DSM-TEST-1",
            linked_disorder=disorder,
            display_type="diagnosis",
            chapter_number=4,
            chapter_name_en="Anxiety Disorders",
            name_en="Panic Disorder",
            is_active=True,
        )

        call_command("seed_mvp", stdout=StringIO())
        disorder.refresh_from_db()
        legacy_category = Category.objects.get(slug="anxiety")
        self.assertEqual(disorder.category_id, dsm_category.id)
        self.assertEqual(
            legacy_category.is_active,
            legacy_category.disorders.filter(is_active=True).exists(),
        )
        for slug in ("anxiety", "ocd-related", "mood", "trauma", "personality-a", "personality-b", "personality-c"):
            category = Category.objects.get(slug=slug)
            self.assertEqual(
                category.is_active,
                category.disorders.filter(is_active=True).exists(),
            )

    def test_graph_filters_by_domain_and_relation(self):
        root = Concept.objects.create(
            slug="graph-root-v4",
            name_en="Graph Root V4",
            simple_definition="root",
            kind="cognitive",
            domain="cbt",
            subtype="cognitive_distortion",
            is_active=True,
        )
        child = Concept.objects.create(
            slug="graph-child-v4",
            name_en="Graph Child V4",
            simple_definition="child",
            kind="cognitive",
            domain="cbt",
            subtype="cognitive_distortion",
            is_active=True,
        )
        ConceptRelationship.objects.create(
            source_concept=child,
            target_concept=root,
            relationship_type="part_of",
            explanation="membership",
        )
        response = self.client.get("/api/concept-map/?domain=cbt&relation=part_of")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual({node["id"] for node in data["nodes"]}, {f"concept:{root.slug}", f"concept:{child.slug}"})
        self.assertEqual(data["meta"]["edge_count"], 1)

    def test_neighborhood_supports_depth_two(self):
        a = Concept.objects.create(slug="neighbor-a", name_en="A", simple_definition="a", is_active=True)
        b = Concept.objects.create(slug="neighbor-b", name_en="B", simple_definition="b", is_active=True)
        c = Concept.objects.create(slug="neighbor-c", name_en="C", simple_definition="c", is_active=True)
        ConceptRelationship.objects.create(source_concept=a, target_concept=b, relationship_type="related")
        ConceptRelationship.objects.create(source_concept=b, target_concept=c, relationship_type="related")
        response = self.client.get(f"/api/concepts/{a.slug}/neighborhood/?depth=2")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual({node["id"] for node in data["nodes"]}, {"concept:neighbor-a", "concept:neighbor-b", "concept:neighbor-c"})
        self.assertEqual(data["depth"], 2)

    def test_graph_path_finds_shortest_structured_route(self):
        a = Concept.objects.create(slug="path-a", name_en="Path A", simple_definition="a", is_active=True)
        b = Concept.objects.create(slug="path-b", name_en="Path B", simple_definition="b", is_active=True)
        c = Concept.objects.create(slug="path-c", name_en="Path C", simple_definition="c", is_active=True)
        ConceptRelationship.objects.create(source_concept=a, target_concept=b, relationship_type="related")
        ConceptRelationship.objects.create(source_concept=b, target_concept=c, relationship_type="influences")
        response = self.client.get("/api/concept-map/path/?from=concept:path-a&to=concept:path-c")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["hops"], 2)
        self.assertEqual([node["id"] for node in data["nodes"]], ["concept:path-a", "concept:path-b", "concept:path-c"])

    def test_practice_queue_hides_correct_answer(self):
        correct = Concept.objects.create(
            slug="practice-correct",
            name_en="Practice Correct",
            simple_definition="correct",
            subtype="cognitive_distortion",
            is_active=True,
        )
        wrong = Concept.objects.create(
            slug="practice-wrong",
            name_en="Practice Wrong",
            simple_definition="wrong",
            subtype="cognitive_distortion",
            is_active=True,
        )
        item = CognitiveDistortionPracticeItem.objects.create(
            slug="practice-item",
            prompt="Which one?",
            explanation="Because structured evidence.",
            target_concept=correct,
            is_active=True,
        )
        CognitiveDistortionPracticeChoice.objects.create(item=item, concept=correct, text="Correct", is_correct=True)
        CognitiveDistortionPracticeChoice.objects.create(item=item, concept=wrong, text="Wrong", is_correct=False)
        response = self.client.get("/api/cognitive-distortions/practice/")
        self.assertEqual(response.status_code, 200)
        choice = response.json()["items"][0]["choices"][0]
        self.assertNotIn("is_correct", choice)
        self.assertNotIn("explanation", response.json()["items"][0])

    def test_practice_submit_records_activity_and_progress(self):
        correct = Concept.objects.create(
            slug="practice-submit-correct",
            name_en="Practice Submit Correct",
            simple_definition="correct",
            subtype="cognitive_distortion",
            is_active=True,
        )
        wrong = Concept.objects.create(
            slug="practice-submit-wrong",
            name_en="Practice Submit Wrong",
            simple_definition="wrong",
            subtype="cognitive_distortion",
            is_active=True,
        )
        item = CognitiveDistortionPracticeItem.objects.create(
            slug="practice-submit-item",
            prompt="Which one?",
            explanation="Correct explanation",
            target_concept=correct,
            is_active=True,
        )
        correct_choice = CognitiveDistortionPracticeChoice.objects.create(item=item, concept=correct, text="Correct", is_correct=True)
        CognitiveDistortionPracticeChoice.objects.create(item=item, concept=wrong, text="Wrong", is_correct=False)
        self.auth(self.user_a)
        response = self.client.post(
            f"/api/cognitive-distortions/practice/{item.slug}/submit/",
            {"choice_id": correct_choice.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["correct"])
        self.assertEqual(response.json()["progress_percent"], 75)
        self.assertTrue(CognitiveDistortionPracticeAttempt.objects.filter(user=self.user_a, item=item, is_correct=True).exists())
        self.assertTrue(StudyActivity.objects.filter(user=self.user_a, activity_type="distortion_practice", concept=correct).exists())

    def test_practice_submit_rejects_choice_from_other_item(self):
        correct = Concept.objects.create(
            slug="practice-cross-correct",
            name_en="Practice Cross Correct",
            simple_definition="correct",
            subtype="cognitive_distortion",
            is_active=True,
        )
        wrong = Concept.objects.create(
            slug="practice-cross-wrong",
            name_en="Practice Cross Wrong",
            simple_definition="wrong",
            subtype="cognitive_distortion",
            is_active=True,
        )
        item_a = CognitiveDistortionPracticeItem.objects.create(slug="practice-a", prompt="A", explanation="A", target_concept=correct)
        item_b = CognitiveDistortionPracticeItem.objects.create(slug="practice-b", prompt="B", explanation="B", target_concept=wrong)
        CognitiveDistortionPracticeChoice.objects.create(item=item_a, concept=correct, text="Correct", is_correct=True)
        foreign_choice = CognitiveDistortionPracticeChoice.objects.create(item=item_b, concept=wrong, text="Wrong", is_correct=True)
        self.auth(self.user_a)
        response = self.client.post(
            f"/api/cognitive-distortions/practice/{item_a.slug}/submit/",
            {"choice_id": foreign_choice.id},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_practice_invalid_content_has_no_side_effects(self):
        target = Concept.objects.create(slug="v041-practice-target", name_en="V041 Practice Target", simple_definition="target", subtype="cognitive_distortion", is_active=True)
        other = Concept.objects.create(slug="v041-practice-other", name_en="V041 Practice Other", simple_definition="other", subtype="cognitive_distortion", is_active=True)
        item = CognitiveDistortionPracticeItem.objects.create(slug="v041-invalid-practice", prompt="Invalid content", explanation="Invalid", target_concept=target, is_active=True)
        selected = CognitiveDistortionPracticeChoice.objects.create(item=item, concept=target, text="Target", is_correct=True, sort_order=0)
        CognitiveDistortionPracticeChoice.objects.create(item=item, concept=other, text="Other", is_correct=True, sort_order=1)
        self.auth(self.user_a)
        response = self.client.post(f"/api/cognitive-distortions/practice/{item.slug}/submit/", {"choice_id": selected.id}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(CognitiveDistortionPracticeAttempt.objects.filter(user=self.user_a, item=item).exists())
        self.assertFalse(UserConceptProgress.objects.filter(user=self.user_a, concept=target).exists())
        self.assertFalse(StudyActivity.objects.filter(user=self.user_a, activity_type=StudyActivity.Kind.DISTORTION_PRACTICE, concept=target).exists())

    def test_practice_queue_hides_inactive_choice_concepts(self):
        target = Concept.objects.create(slug="v041-queue-target", name_en="V041 Queue Target", simple_definition="target", subtype="cognitive_distortion", is_active=True)
        active_wrong = Concept.objects.create(slug="v041-queue-active-wrong", name_en="V041 Queue Active Wrong", simple_definition="wrong", subtype="cognitive_distortion", is_active=True)
        inactive_wrong = Concept.objects.create(slug="v041-queue-inactive-wrong", name_en="V041 Queue Inactive Wrong", simple_definition="inactive", subtype="cognitive_distortion", is_active=False)
        item = CognitiveDistortionPracticeItem.objects.create(slug="v041-queue-item", prompt="Queue lifecycle", explanation="Queue lifecycle", target_concept=target, is_active=True)
        CognitiveDistortionPracticeChoice.objects.create(item=item, concept=target, text="Target", is_correct=True, sort_order=0)
        CognitiveDistortionPracticeChoice.objects.create(item=item, concept=active_wrong, text="Active", is_correct=False, sort_order=1)
        CognitiveDistortionPracticeChoice.objects.create(item=item, concept=inactive_wrong, text="Inactive", is_correct=False, sort_order=2)
        response = self.client.get("/api/cognitive-distortions/practice/?limit=20")
        self.assertEqual(response.status_code, 200)
        row = next(row for row in response.json()["items"] if row["slug"] == "v041-queue-item")
        self.assertEqual({choice["concept"]["slug"] for choice in row["choices"]}, {target.slug, active_wrong.slug})

    def test_neighborhood_node_type_never_returns_disconnected_second_level_node(self):
        center = Concept.objects.create(slug="v041-neighbor-center", name_en="Center", simple_definition="center", is_active=True)
        second = Concept.objects.create(slug="v041-neighbor-second", name_en="Second", simple_definition="second", is_active=True)
        bridge_disorder = Disorder.objects.create(category=self.category, slug="v041-neighbor-bridge", name_en="Bridge Disorder", is_active=True)
        DisorderConcept.objects.create(disorder=bridge_disorder, concept=center, role="associated")
        DisorderConcept.objects.create(disorder=bridge_disorder, concept=second, role="associated")
        response = self.client.get(f"/api/concepts/{center.slug}/neighborhood/?depth=2&node_type=concept")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual({node["id"] for node in data["nodes"]}, {f"concept:{center.slug}"})
        self.assertEqual(data["edges"], [])

    def test_graph_min_degree_is_applied_after_relation_filter(self):
        a = Concept.objects.create(slug="v041-degree-a", name_en="Degree A", simple_definition="a", is_active=True)
        b = Concept.objects.create(slug="v041-degree-b", name_en="Degree B", simple_definition="b", is_active=True)
        c = Concept.objects.create(slug="v041-degree-c", name_en="Degree C", simple_definition="c", is_active=True)
        d = Concept.objects.create(slug="v041-degree-d", name_en="Degree D", simple_definition="d", is_active=True)
        ConceptRelationship.objects.create(source_concept=a, target_concept=b, relationship_type="part_of")
        ConceptRelationship.objects.create(source_concept=a, target_concept=c, relationship_type="related")
        ConceptRelationship.objects.create(source_concept=b, target_concept=d, relationship_type="related")
        response = self.client.get("/api/concept-map/?relation=part_of&min_degree=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nodes"], [])
        self.assertEqual(response.json()["edges"], [])

    def test_graph_path_marks_reverse_traversal(self):
        child = Concept.objects.create(slug="v041-path-child", name_en="Child", simple_definition="child", is_active=True)
        parent = Concept.objects.create(slug="v041-path-parent", name_en="Parent", simple_definition="parent", is_active=True)
        ConceptRelationship.objects.create(source_concept=child, target_concept=parent, relationship_type="part_of")
        response = self.client.get(f"/api/concept-map/path/?from=concept:{parent.slug}&to=concept:{child.slug}&relation=part_of")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["found"])
        self.assertEqual(response.json()["edges"][0]["traversal_direction"], "reverse")

    def test_graph_path_excludes_dsm_nearby_shortcuts_by_default(self):
        second_disorder = Disorder.objects.create(category=self.category, slug="v041-path-disorder-two", name_en="Path Disorder Two", is_active=True)
        left = Concept.objects.create(slug="v041-path-left", name_en="Left", simple_definition="left", is_active=True)
        right = Concept.objects.create(slug="v041-path-right", name_en="Right", simple_definition="right", is_active=True)
        DisorderConcept.objects.create(disorder=self.disorder, concept=left, role="associated")
        DisorderConcept.objects.create(disorder=second_disorder, concept=right, role="associated")
        corpus = DSMCorpus.objects.create(key="v041-path-corpus", title="V041 Path Corpus", source_filename="v041.json", source_sha256="b" * 64, is_active=True)
        first_record = DSMRecord.objects.create(corpus=corpus, master_id="V041-PATH-1", linked_disorder=self.disorder, display_type="diagnosis", name_en="First", is_active=True, sort_index=1)
        second_record = DSMRecord.objects.create(corpus=corpus, master_id="V041-PATH-2", linked_disorder=second_disorder, display_type="diagnosis", name_en="Second", is_active=True, sort_index=2)
        DSMRecordRelation.objects.create(source=first_record, target=second_record, relationship_type=DSMRecordRelation.Kind.NEARBY, explanation="structural nearby only")
        default = self.client.get(f"/api/concept-map/path/?from=concept:{left.slug}&to=concept:{right.slug}")
        structural = self.client.get(f"/api/concept-map/path/?from=concept:{left.slug}&to=concept:{right.slug}&include_structural=1")
        self.assertEqual(default.status_code, 200)
        self.assertFalse(default.json()["found"])
        self.assertEqual(structural.status_code, 200)
        self.assertTrue(structural.json()["found"])
        self.assertTrue(any(edge["kind"] == "dsm_nearby" for edge in structural.json()["edges"]))

    def test_disorder_get_is_read_only_for_progress(self):
        self.auth(self.user_a)
        response = self.client.get(f"/api/disorders/{self.disorder.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserProgress.objects.filter(user=self.user_a, disorder=self.disorder).exists())
        self.assertFalse(StudyActivity.objects.filter(user=self.user_a, activity_type=StudyActivity.Kind.DISORDER_VIEW, disorder=self.disorder).exists())

    def test_failed_quiz_and_case_do_not_grant_mastery_progress(self):
        quiz = Quiz.objects.create(slug="v041-zero-quiz", title="Zero Quiz", disorder=self.disorder, is_active=True)
        question = QuizQuestion.objects.create(quiz=quiz, prompt="Q", sort_order=1)
        QuizChoice.objects.create(question=question, text="Correct", is_correct=True, sort_order=1)
        wrong = QuizChoice.objects.create(question=question, text="Wrong", is_correct=False, sort_order=2)
        case = ClinicalCase.objects.create(slug="v041-zero-case", title="Zero Case", patient_summary="summary", primary_disorder=self.disorder, is_active=True)
        step = CaseStep.objects.create(case=case, title="Step", narrative="N", sort_order=1)
        case_question = CaseQuestion.objects.create(step=step, prompt="CQ", sort_order=1)
        CaseChoice.objects.create(question=case_question, text="Best", score_value=3, sort_order=1)
        case_wrong = CaseChoice.objects.create(question=case_question, text="Wrong", score_value=0, sort_order=2)
        self.auth(self.user_a)
        quiz_response = self.client.post(f"/api/quizzes/{quiz.slug}/submit/", {"answers": [{"question_id": question.id, "choice_id": wrong.id}]}, format="json")
        self.assertEqual(quiz_response.status_code, 200)
        progress = UserProgress.objects.get(user=self.user_a, disorder=self.disorder)
        self.assertEqual(progress.progress_percent, 25)
        case_response = self.client.post(f"/api/cases/{case.slug}/submit/", {"answers": [{"question_id": case_question.id, "choice_id": case_wrong.id}]}, format="json")
        self.assertEqual(case_response.status_code, 200)
        progress.refresh_from_db()
        self.assertEqual(progress.progress_percent, 25)
        self.assertNotEqual(progress.status, UserProgress.Status.COMPLETED)

    def test_graph_cache_invalidates_after_model_change(self):
        first = Concept.objects.create(slug="v041-cache-first", name_en="First", simple_definition="first", is_active=True)
        initial = self.client.get("/api/concept-map/")
        self.assertIn(f"concept:{first.slug}", {node["id"] for node in initial.json()["nodes"]})
        second = Concept.objects.create(slug="v041-cache-second", name_en="Second", simple_definition="second", is_active=True)
        refreshed = self.client.get("/api/concept-map/")
        self.assertIn(f"concept:{second.slug}", {node["id"] for node in refreshed.json()["nodes"]})

    def test_seed_soft_deactivates_stale_protected_practice_choice_and_quiz_choice(self):
        call_command("seed_mvp", stdout=StringIO())
        item = CognitiveDistortionPracticeItem.objects.get(slug="dp-all-or-nothing-1")
        stale_concept = Concept.objects.get(slug="mind-reading")
        stale_choice, _ = CognitiveDistortionPracticeChoice.objects.update_or_create(item=item, concept=stale_concept, defaults={"text": "Historical stale choice", "is_correct": False, "sort_order": 99, "is_active": True})
        CognitiveDistortionPracticeAttempt.objects.create(user=self.user_a, item=item, selected_choice=stale_choice, is_correct=False)
        quiz = Quiz.objects.filter(seed_managed=True, is_active=True).order_by("id").first()
        quiz_question = quiz.questions.filter(is_active=True).order_by("sort_order", "id").first()
        stale_quiz_choice = QuizChoice.objects.create(question=quiz_question, text="Historical stale quiz choice", is_correct=True, sort_order=99, is_active=True)
        call_command("seed_mvp", stdout=StringIO())
        stale_choice.refresh_from_db()
        stale_quiz_choice.refresh_from_db()
        self.assertFalse(stale_choice.is_active)
        self.assertFalse(stale_choice.is_correct)
        self.assertTrue(CognitiveDistortionPracticeAttempt.objects.filter(selected_choice=stale_choice).exists())
        self.assertFalse(stale_quiz_choice.is_active)
        self.assertFalse(stale_quiz_choice.is_correct)
        self.assertEqual(quiz_question.choices.filter(is_active=True, is_correct=True).count(), 1)

    def test_oversized_numeric_inputs_return_400_instead_of_500(self):
        concept = Concept.objects.create(slug="v041-large-input", name_en="Large", simple_definition="large", is_active=True)
        huge = "9" * 5000
        responses = [
            self.client.get(f"/api/concept-map/?min_degree={huge}"),
            self.client.get(f"/api/concepts/{concept.slug}/neighborhood/?depth={huge}"),
            self.client.get(f"/api/cognitive-distortions/practice/?limit={huge}"),
        ]
        for response in responses:
            self.assertEqual(response.status_code, 400)

    def test_logout_blacklists_refresh_token(self):
        refresh = RefreshToken.for_user(self.user_a)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = self.client.post("/api/auth/logout/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(response.status_code, 204)
        self.client.credentials()
        replay = self.client.post("/api/auth/refresh/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(replay.status_code, 401)


class TherapyFoundationTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(slug="therapy-test", name_en="Therapy Test")
        self.disorder = Disorder.objects.create(
            category=self.category,
            slug="therapy-test-disorder",
            name_en="Therapy Test Disorder",
            is_active=True,
        )
        self.concept = Concept.objects.create(
            slug="therapy-test-concept",
            name_en="Therapy Test Concept",
            simple_definition="Test concept",
            is_active=True,
        )
        self.family = TherapyFamily.objects.create(
            slug="cognitive-behavioral",
            name_en="Cognitive and Behavioral",
            name_fa="شناختی و رفتاری",
        )
        self.therapy = Therapy.objects.create(
            family=self.family,
            slug="test-therapy",
            name_en="Test Therapy",
        )
        self.technique = Technique.objects.create(
            slug="test-technique",
            name_en="Test Technique",
        )
        self.source = SourceReference.objects.create(
            title="Test guideline",
            organization="Test Organization",
            source_type="guideline",
        )

    def test_therapy_family_is_primary_while_classifications_can_overlap(self):
        trauma_focused = TherapyClassification.objects.create(
            slug="trauma-focused",
            name_en="Trauma-focused",
            kind=TherapyClassification.Kind.FOCUS,
        )
        exposure_based = TherapyClassification.objects.create(
            slug="exposure-based",
            name_en="Exposure-based",
            kind=TherapyClassification.Kind.METHOD,
        )
        TherapyClassificationLink.objects.create(therapy=self.therapy, classification=trauma_focused)
        TherapyClassificationLink.objects.create(therapy=self.therapy, classification=exposure_based)

        self.assertEqual(self.therapy.family, self.family)
        self.assertEqual(self.therapy.classification_links.filter(is_active=True).count(), 2)
        self.assertEqual(self.therapy.review_status, ScientificReviewStatus.UNREVIEWED)

    def test_therapy_relationships_keep_clinical_role_separate_from_evidence_basis(self):
        link = TherapyDisorder.objects.create(
            therapy=self.therapy,
            disorder=self.disorder,
            clinical_role=TherapyDisorder.ClinicalRole.CONTEXT_DEPENDENT,
            evidence_basis=TherapyDisorder.EvidenceBasis.GUIDELINE,
        )
        TherapyDisorderSource.objects.create(relationship=link, source=self.source)

        self.assertEqual(link.clinical_role, TherapyDisorder.ClinicalRole.CONTEXT_DEPENDENT)
        self.assertEqual(link.evidence_basis, TherapyDisorder.EvidenceBasis.GUIDELINE)
        self.assertEqual(link.source_links.count(), 1)

    def test_therapy_and_technique_relations_reuse_shared_source_registry(self):
        TherapySource.objects.create(therapy=self.therapy, source=self.source)
        TechniqueSource.objects.create(technique=self.technique, source=self.source)
        therapy_technique = TherapyTechnique.objects.create(
            therapy=self.therapy,
            technique=self.technique,
            role=TherapyTechnique.Role.CORE,
        )
        TherapyTechniqueSource.objects.create(relationship=therapy_technique, source=self.source)
        therapy_concept = TherapyConcept.objects.create(
            therapy=self.therapy,
            concept=self.concept,
            relationship_type=TherapyConcept.Kind.TARGETS,
        )
        TherapyConceptSource.objects.create(relationship=therapy_concept, source=self.source)
        technique_concept = TechniqueConcept.objects.create(
            technique=self.technique,
            concept=self.concept,
            relationship_type=TechniqueConcept.Kind.ADDRESSES,
        )
        TechniqueConceptSource.objects.create(relationship=technique_concept, source=self.source)

        self.assertEqual(self.therapy.source_links.get().source_id, self.source.id)
        self.assertEqual(self.technique.source_links.get().source_id, self.source.id)
        self.assertEqual(therapy_technique.source_links.get().source_id, self.source.id)
        self.assertEqual(therapy_concept.source_links.get().source_id, self.source.id)
        self.assertEqual(technique_concept.source_links.get().source_id, self.source.id)
