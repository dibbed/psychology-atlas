import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
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
    Therapy, TherapyAlias, TherapyBookmark, TherapyClassification, TherapyClassificationLink, TherapyConcept,
    TherapyConceptSource, TherapyDisorder, TherapyDisorderSource, TherapyFamily, TherapyNote, TherapySource,
    TherapyTechnique, TherapyTechniqueSource, ResearchDataset, ResearchRecord,
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
        self.assertLessEqual(len(captured), 10)

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


class TherapySeedApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mvp", stdout=StringIO())

    def test_therapy_seed_inventory_is_source_backed_and_source_checked(self):
        self.assertEqual(Therapy.objects.filter(is_active=True, seed_managed=True).count(), 6)
        self.assertEqual(Technique.objects.filter(is_active=True, seed_managed=True).count(), 9)
        self.assertEqual(TherapyDisorder.objects.filter(is_active=True).count(), 9)
        self.assertEqual(TherapyTechnique.objects.filter(is_active=True).count(), 10)
        self.assertEqual(TherapyConcept.objects.filter(is_active=True).count(), 7)
        self.assertEqual(TechniqueConcept.objects.filter(is_active=True).count(), 8)
        self.assertFalse(
            Therapy.objects.filter(is_active=True, seed_managed=True).exclude(
                review_status=ScientificReviewStatus.SOURCE_CHECKED
            ).exists()
        )
        self.assertFalse(
            Therapy.objects.filter(is_active=True, seed_managed=True, source_links__isnull=True).exists()
        )

    def test_therapy_list_search_and_filters_use_structured_relations(self):
        alias_response = self.client.get("/api/therapies/?q=CBT")
        self.assertEqual(alias_response.status_code, 200)
        alias_slugs = {row["slug"] for row in alias_response.json()["results"]}
        self.assertIn("cognitive-behavioral-therapy", alias_slugs)

        disorder_response = self.client.get("/api/therapies/?disorder=post-traumatic-stress-disorder")
        self.assertEqual(disorder_response.status_code, 200)
        disorder_slugs = {row["slug"] for row in disorder_response.json()["results"]}
        self.assertEqual(disorder_slugs, {"cognitive-processing-therapy", "prolonged-exposure-therapy"})

        classification_response = self.client.get("/api/therapies/?classification=trauma-focused")
        self.assertEqual(classification_response.status_code, 200)
        classification_slugs = {row["slug"] for row in classification_response.json()["results"]}
        self.assertEqual(classification_slugs, {"cognitive-processing-therapy", "prolonged-exposure-therapy"})

    def test_therapy_detail_exposes_provenance_and_separates_evidence_from_role(self):
        response = self.client.get("/api/therapies/dialectical-behavior-therapy/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data["sources"]), 2)
        self.assertTrue(data["techniques"])
        bpd = next(row for row in data["disorders"] if row["disorder"]["slug"] == "borderline-personality-disorder")
        self.assertEqual(bpd["clinical_role"], TherapyDisorder.ClinicalRole.CONTEXT_DEPENDENT)
        self.assertEqual(bpd["evidence_basis"], TherapyDisorder.EvidenceBasis.GUIDELINE)
        self.assertTrue(bpd["sources"])
        self.assertIn("خودآسیبی", bpd["explanation"])

    def test_therapy_taxonomy_rejects_invalid_evidence_filter(self):
        taxonomy = self.client.get("/api/therapies/taxonomy/")
        self.assertEqual(taxonomy.status_code, 200)
        self.assertTrue(taxonomy.json()["families"])
        self.assertTrue(taxonomy.json()["classifications"])
        self.assertIn("guideline", {row["value"] for row in taxonomy.json()["evidence_bases"]})

        invalid = self.client.get("/api/therapies/?evidence_basis=best-treatment")
        self.assertEqual(invalid.status_code, 400)

    def test_technique_api_filters_by_therapy_and_concept_and_hides_inactive(self):
        therapy_response = self.client.get("/api/techniques/?therapy=prolonged-exposure-therapy")
        self.assertEqual(therapy_response.status_code, 200)
        self.assertEqual(
            {row["slug"] for row in therapy_response.json()["results"]},
            {"in-vivo-exposure", "imaginal-exposure"},
        )

        concept_response = self.client.get("/api/techniques/?concept=avoidance")
        self.assertEqual(concept_response.status_code, 200)
        concept_slugs = {row["slug"] for row in concept_response.json()["results"]}
        self.assertTrue({"exposure", "activity-planning", "in-vivo-exposure"}.issubset(concept_slugs))

        alias_response = self.client.get("/api/techniques/?q=ERP")
        self.assertEqual(alias_response.status_code, 200)
        self.assertEqual(alias_response.json()["count"], 1)
        self.assertEqual(
            {row["slug"] for row in alias_response.json()["results"]},
            {"exposure-response-prevention"},
        )

        Technique.objects.filter(slug="in-vivo-exposure").update(is_active=False)
        detail = self.client.get("/api/techniques/in-vivo-exposure/")
        self.assertEqual(detail.status_code, 404)

    def test_therapy_seed_is_idempotent(self):
        before = {
            "families": TherapyFamily.objects.count(),
            "classifications": TherapyClassification.objects.count(),
            "therapies": Therapy.objects.count(),
            "techniques": Technique.objects.count(),
            "therapy_disorders": TherapyDisorder.objects.count(),
            "therapy_techniques": TherapyTechnique.objects.count(),
            "therapy_concepts": TherapyConcept.objects.count(),
            "technique_concepts": TechniqueConcept.objects.count(),
        }
        call_command("seed_mvp", stdout=StringIO())
        after = {
            "families": TherapyFamily.objects.count(),
            "classifications": TherapyClassification.objects.count(),
            "therapies": Therapy.objects.count(),
            "techniques": Technique.objects.count(),
            "therapy_disorders": TherapyDisorder.objects.count(),
            "therapy_techniques": TherapyTechnique.objects.count(),
            "therapy_concepts": TherapyConcept.objects.count(),
            "technique_concepts": TechniqueConcept.objects.count(),
        }
        self.assertEqual(after, before)


class TherapyCrossDomainGraphTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mvp", stdout=StringIO())

    def test_global_search_includes_therapy_and_technique_exact_aliases(self):
        therapy_response = self.client.get("/api/search/?q=CBT")
        self.assertEqual(therapy_response.status_code, 200)
        self.assertEqual(
            [row["slug"] for row in therapy_response.json()["therapies"]],
            ["cognitive-behavioral-therapy"],
        )

        technique_response = self.client.get("/api/search/?q=ERP")
        self.assertEqual(technique_response.status_code, 200)
        self.assertEqual(
            [row["slug"] for row in technique_response.json()["techniques"]],
            ["exposure-response-prevention"],
        )

    def test_disorder_and_concept_details_expose_cross_domain_relations_with_sources(self):
        disorder_response = self.client.get("/api/disorders/panic-disorder/")
        self.assertEqual(disorder_response.status_code, 200)
        therapies = disorder_response.json()["therapies"]
        self.assertEqual([row["slug"] for row in therapies], ["cognitive-behavioral-therapy"])
        self.assertEqual(therapies[0]["evidence_basis"], "guideline")
        self.assertTrue(therapies[0]["sources"])

        concept_response = self.client.get("/api/concepts/avoidance/")
        self.assertEqual(concept_response.status_code, 200)
        payload = concept_response.json()
        self.assertIn("behavioral-activation", {row["therapy"]["slug"] for row in payload["therapies"]})
        self.assertIn("exposure", {row["technique"]["slug"] for row in payload["techniques"]})
        self.assertTrue(all(row["sources"] for row in payload["therapies"]))
        self.assertTrue(all(row["sources"] for row in payload["techniques"]))

    def test_graph_contains_therapy_and_technique_nodes_and_real_path(self):
        response = self.client.get("/api/concept-map/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["node_types"]["therapy"], 6)
        self.assertEqual(payload["meta"]["node_types"]["technique"], 9)
        self.assertIn("therapy:cognitive-behavioral-therapy", {row["id"] for row in payload["nodes"]})
        self.assertIn("technique:exposure", {row["id"] for row in payload["nodes"]})

        path_response = self.client.get(
            "/api/concept-map/path/?from=disorder:panic-disorder&to=technique:cognitive-restructuring"
        )
        self.assertEqual(path_response.status_code, 200)
        path_payload = path_response.json()
        self.assertTrue(path_payload["found"])
        self.assertEqual(path_payload["hops"], 2)
        self.assertEqual(
            [row["id"] for row in path_payload["nodes"]],
            [
                "disorder:panic-disorder",
                "therapy:cognitive-behavioral-therapy",
                "technique:cognitive-restructuring",
            ],
        )
        self.assertTrue(all(edge.get("sources") for edge in path_payload["edges"]))

    def test_graph_filters_and_cache_invalidation_cover_therapy_models(self):
        therapy_only = self.client.get("/api/concept-map/?node_type=therapy")
        self.assertEqual(therapy_only.status_code, 200)
        self.assertEqual(therapy_only.json()["meta"]["node_count"], 6)
        self.assertTrue(all(row["type"] == "therapy" for row in therapy_only.json()["nodes"]))

        self.client.get("/api/concept-map/")
        therapy = Therapy.objects.get(slug="cognitive-behavioral-therapy")
        therapy.summary = "Cache invalidation sentinel"
        therapy.save(update_fields=("summary", "updated_at"))
        refreshed = self.client.get("/api/concept-map/").json()
        node = next(row for row in refreshed["nodes"] if row["id"] == "therapy:cognitive-behavioral-therapy")
        self.assertEqual(node["summary"], "Cache invalidation sentinel")

        relation = TherapyDisorder.objects.get(
            therapy__slug="cognitive-behavioral-therapy",
            disorder__slug="panic-disorder",
        )
        source = relation.source_links.select_related("source").first().source
        source.organization = "Graph source sentinel"
        source.save(update_fields=("organization",))
        source_refreshed = self.client.get("/api/concept-map/").json()
        edge = next(
            row for row in source_refreshed["edges"]
            if row["source"] == "therapy:cognitive-behavioral-therapy"
            and row["target"] == "disorder:panic-disorder"
        )
        self.assertEqual(edge["sources"][0]["organization"], "Graph source sentinel")


class TherapyPersonalCompareTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mvp", stdout=StringIO())
        cls.user_a = User.objects.create_user(username="therapy-a@example.com", email="therapy-a@example.com", password="ComplexPass123!")
        cls.user_b = User.objects.create_user(username="therapy-b@example.com", email="therapy-b@example.com", password="ComplexPass123!")

    def auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_therapy_compare_preserves_order_and_structured_provenance(self):
        response = self.client.get(
            "/api/therapies/compare/?slugs=behavioral-activation,cognitive-behavioral-therapy"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [row["slug"] for row in payload["items"]],
            ["behavioral-activation", "cognitive-behavioral-therapy"],
        )
        self.assertIn("رتبه‌بندی", payload["note"])
        self.assertTrue(payload["items"][0]["sources"])
        self.assertTrue(payload["items"][0]["disorders"])
        self.assertTrue(all(row["sources"] for row in payload["items"][0]["disorders"]))

    def test_therapy_compare_query_budget_is_constant_for_bounded_comparison(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                "/api/therapies/compare/?slugs=cognitive-behavioral-therapy,behavioral-activation"
            )
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 14)

    def test_therapy_compare_rejects_invalid_sets_and_inactive_rows(self):
        one = self.client.get("/api/therapies/compare/?slugs=cognitive-behavioral-therapy")
        self.assertEqual(one.status_code, 400)
        duplicate = self.client.get(
            "/api/therapies/compare/?slugs=cognitive-behavioral-therapy,cognitive-behavioral-therapy"
        )
        self.assertEqual(duplicate.status_code, 400)
        Therapy.objects.filter(slug="interpersonal-psychotherapy").update(is_active=False)
        inactive = self.client.get(
            "/api/therapies/compare/?slugs=cognitive-behavioral-therapy,interpersonal-psychotherapy"
        )
        self.assertEqual(inactive.status_code, 404)

    def test_therapy_bookmarks_are_idempotent_scoped_and_record_activity(self):
        self.auth(self.user_a)
        created = self.client.post(
            "/api/therapy-bookmarks/", {"slug": "cognitive-behavioral-therapy"}, format="json"
        )
        self.assertEqual(created.status_code, 201)
        repeated = self.client.post(
            "/api/therapy-bookmarks/", {"slug": "cognitive-behavioral-therapy"}, format="json"
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(TherapyBookmark.objects.filter(user=self.user_a).count(), 1)
        self.assertEqual(
            StudyActivity.objects.filter(
                user=self.user_a,
                activity_type=StudyActivity.Kind.BOOKMARK_SAVED,
                therapy__slug="cognitive-behavioral-therapy",
            ).count(),
            1,
        )

        self.auth(self.user_b)
        self.assertEqual(self.client.get("/api/therapy-bookmarks/").json(), [])
        deleted = self.client.delete("/api/therapy-bookmarks/cognitive-behavioral-therapy/")
        self.assertEqual(deleted.status_code, 204)
        self.assertTrue(
            TherapyBookmark.objects.filter(
                user=self.user_a, therapy__slug="cognitive-behavioral-therapy"
            ).exists()
        )

    def test_therapy_notes_are_private_trimmed_bounded_and_deletable(self):
        self.auth(self.user_a)
        saved = self.client.put(
            "/api/therapy-notes/cognitive-behavioral-therapy/",
            {"body": "  نکته شخصی درمان  "},
            format="json",
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["body"], "نکته شخصی درمان")
        self.assertTrue(
            StudyActivity.objects.filter(
                user=self.user_a,
                activity_type=StudyActivity.Kind.NOTE_SAVED,
                therapy__slug="cognitive-behavioral-therapy",
            ).exists()
        )

        bad_type = self.client.put(
            "/api/therapy-notes/cognitive-behavioral-therapy/", {"body": 123}, format="json"
        )
        self.assertEqual(bad_type.status_code, 400)
        too_long = self.client.put(
            "/api/therapy-notes/cognitive-behavioral-therapy/",
            {"body": "x" * 12001},
            format="json",
        )
        self.assertEqual(too_long.status_code, 400)

        self.auth(self.user_b)
        private = self.client.get("/api/therapy-notes/cognitive-behavioral-therapy/")
        self.assertEqual(private.status_code, 200)
        self.assertFalse(private.json()["exists"])
        self.client.delete("/api/therapy-notes/cognitive-behavioral-therapy/")
        self.assertTrue(
            TherapyNote.objects.filter(
                user=self.user_a, therapy__slug="cognitive-behavioral-therapy"
            ).exists()
        )

        self.auth(self.user_a)
        emptied = self.client.put(
            "/api/therapy-notes/cognitive-behavioral-therapy/", {"body": "   "}, format="json"
        )
        self.assertEqual(emptied.status_code, 200)
        self.assertFalse(emptied.json()["exists"])
        self.assertFalse(TherapyNote.objects.filter(user=self.user_a).exists())

    def test_dashboard_and_personal_lists_include_only_active_therapy_content(self):
        cbt = Therapy.objects.get(slug="cognitive-behavioral-therapy")
        ba = Therapy.objects.get(slug="behavioral-activation")
        TherapyBookmark.objects.create(user=self.user_a, therapy=cbt)
        TherapyBookmark.objects.create(user=self.user_a, therapy=ba)
        TherapyNote.objects.create(user=self.user_a, therapy=cbt, body="CBT note")
        TherapyNote.objects.create(user=self.user_a, therapy=ba, body="BA note")
        ba.is_active = False
        ba.save(update_fields=("is_active", "updated_at"))

        self.auth(self.user_a)
        bookmarks = self.client.get("/api/therapy-bookmarks/")
        notes = self.client.get("/api/therapy-notes/")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(bookmarks.status_code, 200)
        self.assertEqual(notes.status_code, 200)
        self.assertEqual([row["therapy"]["slug"] for row in bookmarks.json()], ["cognitive-behavioral-therapy"])
        self.assertEqual([row["therapy"]["slug"] for row in notes.json()], ["cognitive-behavioral-therapy"])
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["saved_topics"], 1)
        self.assertEqual(dashboard.json()["notes_count"], 1)
        self.assertEqual(
            [row["slug"] for row in dashboard.json()["recent_therapy_saved"]],
            ["cognitive-behavioral-therapy"],
        )
        self.assertEqual(
            [row["slug"] for row in dashboard.json()["recent_therapy_notes"]],
            ["cognitive-behavioral-therapy"],
        )

    def test_seed_preserves_therapy_personal_data_and_activity_links(self):
        cbt = Therapy.objects.get(slug="cognitive-behavioral-therapy")
        bookmark = TherapyBookmark.objects.create(user=self.user_a, therapy=cbt)
        note = TherapyNote.objects.create(user=self.user_a, therapy=cbt, body="seed preservation note")
        activity = StudyActivity.objects.create(
            user=self.user_a,
            activity_type=StudyActivity.Kind.NOTE_SAVED,
            therapy=cbt,
        )

        call_command("seed_mvp", stdout=StringIO())

        self.assertTrue(TherapyBookmark.objects.filter(pk=bookmark.pk, user=self.user_a).exists())
        self.assertEqual(TherapyNote.objects.get(pk=note.pk).body, "seed preservation note")
        activity.refresh_from_db()
        self.assertEqual(activity.therapy_id, cbt.id)
        cbt.refresh_from_db()
        self.assertTrue(cbt.is_active)

    def test_therapy_personal_endpoints_require_authentication(self):
        for method, path in (
            ("get", "/api/therapy-bookmarks/"),
            ("post", "/api/therapy-bookmarks/"),
            ("get", "/api/therapy-notes/"),
            ("get", "/api/therapy-notes/cognitive-behavioral-therapy/"),
        ):
            response = getattr(self.client, method)(path, {}, format="json")
            self.assertEqual(response.status_code, 401)


class ResearchDatasetImportTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mvp", stdout=StringIO())

    def _write_dataset(self, path, *, complete):
        source_id = "source:test-shared-complete" if complete else "src_test_shared_legacy"
        metadata = {
            "dataset_name": "Psychology Atlas Import Test",
            "dataset_version": "research-1-complete" if complete else "1.0.0",
            "generated_at": "2026-09-03",
        }
        document = {
            "dataset_metadata": metadata,
            "sources": [
                {
                    "id" if complete else "source_id": source_id,
                    "title": "Shared Import Test Source",
                    "authors": ["Example, A."],
                    "publication_year": 2024,
                    "doi": "10.1234/import-test",
                    "url": "https://example.test/import-source",
                    "source_type": "review_article",
                    "verification_status" if complete else "verification": "verified" if complete else "citation_from_model_knowledge",
                }
            ],
            "concepts": [],
            "cognitive_distortions": [],
            "symptoms": [],
            "disorders": [],
            "therapy_families": [],
            "therapy_classifications": [],
            "therapies": [],
            "techniques": [],
            "psychologists": [],
            "theories": [],
            "timeline_events": [],
            "relationships": [],
            "claims": [],
            "research_gaps": [],
            "potential_duplicates": [],
            "terminology_notes": [],
            "corrections": [],
            "quality_control": {},
        }
        if complete:
            document["concepts"] = [
                {
                    "id": "concept:test-import-process",
                    "slug": "test-import-process",
                    "name_en": "Test Import Process",
                    "name_fa": "فرایند آزمایشی ورود",
                    "simple_definition_fa": "تعریف فارسی آزمون ورود داده.",
                    "academic_definition_fa": "تعریف دانشگاهی فارسی برای آزمون ورود داده.",
                    "domain": "cognitive_psychology",
                    "source_ids": [source_id],
                    "review": {"status": "source_checked"},
                }
            ]
            document["therapy_families"] = [
                {
                    "id": "therapy-family:test-import-family",
                    "slug": "test-import-family",
                    "name_en": "Test Import Family",
                    "name_fa": "خانواده آزمایشی ورود",
                    "description_fa": "خانواده درمانی برای تست import.",
                    "source_ids": [source_id],
                    "review": {"status": "source_checked"},
                }
            ]
            document["therapy_classifications"] = [
                {
                    "id": "therapy-classification:test-import-structured",
                    "slug": "test-import-structured",
                    "name_en": "Test Import Structured",
                    "name_fa": "ساختاریافته آزمایشی",
                    "source_ids": [source_id],
                    "review": {"status": "source_checked"},
                }
            ]
            document["therapies"] = [
                {
                    "id": "therapy:test-import-therapy",
                    "slug": "test-import-therapy",
                    "name_en": "Test Import Therapy",
                    "name_fa": "درمان آزمایشی ورود",
                    "primary_family_id": "therapy-family:test-import-family",
                    "classification_ids": ["therapy-classification:test-import-structured"],
                    "academic_definition_fa": "تعریف درمان آزمایشی.",
                    "source_ids": [source_id],
                    "review": {"status": "source_checked"},
                },
                {
                    "id": "therapy:cognitive-behavioral-therapy",
                    "slug": "cognitive-behavioral-therapy",
                    "name_en": "Cognitive Behavioral Therapy",
                    "name_fa": "درمان شناختی رفتاری",
                    "primary_family_id": "therapy-family:test-import-family",
                    "academic_definition_fa": "این متن نباید محتوای curated موجود را overwrite کند.",
                    "source_ids": [source_id],
                    "review": {"status": "source_checked"},
                },
            ]
            document["techniques"] = [
                {
                    "id": "technique:test-import-technique",
                    "slug": "test-import-technique",
                    "name_en": "Test Import Technique",
                    "name_fa": "تکنیک آزمایشی ورود",
                    "academic_definition_fa": "تعریف تکنیک آزمایشی.",
                    "source_ids": [source_id],
                    "review": {"status": "source_checked"},
                }
            ]
            document["relationships"] = [
                {
                    "id": "relation:test-import-therapy-uses-technique",
                    "source_id": "therapy:test-import-therapy",
                    "target_id": "technique:test-import-technique",
                    "relation_type": "uses",
                    "directionality": "directed",
                    "explanation_fa": "درمان آزمایشی از تکنیک آزمایشی استفاده می‌کند.",
                    "evidence_status": "source_supported_summary",
                    "confidence": "high",
                    "source_ids": [source_id],
                },
                {
                    "id": "relation:test-import-therapy-targets-concept",
                    "source_id": "therapy:test-import-therapy",
                    "target_id": "concept:test-import-process",
                    "relation_type": "targets_or_organizes_around",
                    "directionality": "directed",
                    "explanation_fa": "درمان آزمایشی پیرامون مفهوم آزمایشی سازمان می‌یابد.",
                    "evidence_status": "source_supported_summary",
                    "confidence": "high",
                    "source_ids": [source_id],
                },
            ]
            document["psychologists"] = [
                {
                    "id": "psychologist:test-import-person",
                    "full_name": "Import Test Researcher",
                    "canonical_name": "Import Test Researcher",
                    "name_fa": "پژوهشگر آزمایشی ورود",
                    "source_ids": [source_id],
                }
            ]
        else:
            document["therapy_families"] = [
                {
                    "family_id": "tf_legacy_only",
                    "name_en": "Legacy Only Therapy Family",
                    "name_fa": "خانواده فقط داده قدیمی",
                    "sources": [source_id],
                    "verification": "citation_from_model_knowledge",
                }
            ]
            document["therapies"] = [
                {
                    "therapy_id": "therapy_legacy_only",
                    "slug": "legacy-only-therapy",
                    "name_en": "Legacy Only Therapy",
                    "name_fa": "درمان فقط داده قدیمی",
                    "family_id": "tf_legacy_only",
                    "description_fa": "این رکورد باید فقط staging شود.",
                    "sources": [source_id],
                    "verification": "citation_from_model_knowledge",
                }
            ]
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return document

    def test_research_import_is_lossless_deduplicated_conservative_and_idempotent(self):
        cbt = Therapy.objects.get(slug="cognitive-behavioral-therapy")
        original_cbt_summary = cbt.summary

        with TemporaryDirectory() as directory:
            directory = Path(directory)
            legacy_path = directory / "legacy-research.json"
            complete_path = directory / "complete-research.json"
            legacy_doc = self._write_dataset(legacy_path, complete=False)
            complete_doc = self._write_dataset(complete_path, complete=True)

            call_command(
                "import_research_datasets",
                str(legacy_path),
                str(complete_path),
                stdout=StringIO(),
            )

            self.assertEqual(ResearchDataset.objects.count(), 2)
            expected_records = sum(
                len(value)
                for document in (legacy_doc, complete_doc)
                for value in document.values()
                if isinstance(value, list)
            )
            self.assertEqual(ResearchRecord.objects.count(), expected_records)
            self.assertEqual(SourceReference.objects.filter(doi="10.1234/import-test").count(), 1)

            imported_therapy = Therapy.objects.get(slug="test-import-therapy")
            imported_technique = Technique.objects.get(slug="test-import-technique")
            imported_concept = Concept.objects.get(slug="test-import-process")
            self.assertEqual(imported_therapy.review_status, ScientificReviewStatus.SOURCE_CHECKED)
            self.assertFalse(imported_therapy.seed_managed)
            self.assertTrue(imported_therapy.source_links.exists())
            self.assertTrue(imported_technique.source_links.exists())
            self.assertTrue(imported_concept.source_links.exists())
            self.assertFalse(Therapy.objects.filter(slug="legacy-only-therapy").exists())
            self.assertTrue(
                ResearchRecord.objects.filter(
                    section="therapies",
                    external_id="therapy_legacy_only",
                    promoted_pk__isnull=True,
                ).exists()
            )

            cbt.refresh_from_db()
            self.assertEqual(cbt.summary, original_cbt_summary)

            therapy_technique = TherapyTechnique.objects.get(
                therapy=imported_therapy,
                technique=imported_technique,
            )
            self.assertTrue(therapy_technique.source_links.exists())
            relationship_record = ResearchRecord.objects.get(
                section="relationships",
                external_id="relation:test-import-therapy-uses-technique",
            )
            self.assertEqual(relationship_record.promoted_model, "atlas.therapytechnique")
            self.assertEqual(relationship_record.promoted_pk, therapy_technique.pk)
            self.assertEqual(
                ResearchRecord.objects.filter(section="psychologists", promoted_pk__isnull=True).count(),
                1,
            )

            stable_counts = {
                "datasets": ResearchDataset.objects.count(),
                "records": ResearchRecord.objects.count(),
                "sources": SourceReference.objects.count(),
                "therapies": Therapy.objects.count(),
                "techniques": Technique.objects.count(),
                "concepts": Concept.objects.count(),
                "relations": TherapyTechnique.objects.count(),
            }
            call_command(
                "import_research_datasets",
                str(legacy_path),
                str(complete_path),
                stdout=StringIO(),
            )
            self.assertEqual(stable_counts["datasets"], ResearchDataset.objects.count())
            self.assertEqual(stable_counts["records"], ResearchRecord.objects.count())
            self.assertEqual(stable_counts["sources"], SourceReference.objects.count())
            self.assertEqual(stable_counts["therapies"], Therapy.objects.count())
            self.assertEqual(stable_counts["techniques"], Technique.objects.count())
            self.assertEqual(stable_counts["concepts"], Concept.objects.count())
            self.assertEqual(stable_counts["relations"], TherapyTechnique.objects.count())

            call_command("seed_mvp", stdout=StringIO())
            self.assertTrue(Therapy.objects.filter(pk=imported_therapy.pk, is_active=True).exists())
            self.assertTrue(Technique.objects.filter(pk=imported_technique.pk, is_active=True).exists())
            self.assertTrue(Concept.objects.filter(pk=imported_concept.pk, is_active=True).exists())
            therapy_technique.refresh_from_db()
            self.assertTrue(therapy_technique.is_active)
            self.assertFalse(therapy_technique.seed_managed)
            therapy_concept = TherapyConcept.objects.get(
                therapy=imported_therapy,
                concept=imported_concept,
                relationship_type=TherapyConcept.Kind.TARGETS,
            )
            self.assertTrue(therapy_concept.is_active)
            self.assertFalse(therapy_concept.seed_managed)
            self.assertTrue(
                TherapyClassificationLink.objects.filter(
                    therapy=imported_therapy,
                    classification__slug="test-import-structured",
                    is_active=True,
                    seed_managed=False,
                ).exists()
            )
            self.assertEqual(ResearchDataset.objects.count(), 2)
