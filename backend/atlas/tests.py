import hashlib
import json
from copy import deepcopy
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from . import models as atlas_models
from .case_graph import validate_case_revision_graph
from .models import (
    Bookmark, CaseAttempt, CaseAttemptAnswer, CaseChoice, CaseQuestion, CaseRevision, CaseStep, CaseTransition, Category, ClinicalCase,
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

    def create_case_revision(self, case):
        revision = CaseRevision.objects.create(
            case=case,
            version=1,
            title=case.title,
            patient_summary=case.patient_summary,
            educational_objective=case.educational_objective,
            difficulty=case.difficulty,
            primary_disorder=case.primary_disorder,
            status=CaseRevision.Status.PUBLISHED,
        )
        case.current_revision = revision
        case.save(update_fields=("current_revision", "updated_at"))
        return revision

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
        revision = self.create_case_revision(case)
        step = CaseStep.objects.create(
            case=case,
            revision=revision,
            stable_key="step-1",
            title="step",
            narrative="narrative",
            sort_order=1,
        )
        revision.entry_step = step
        revision.save(update_fields=("entry_step", "updated_at"))
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
        attempt = CaseAttempt.objects.get(id=response.json()["attempt_id"])
        self.assertEqual(attempt.revision_id, revision.id)

    def test_case_detail_reads_only_current_revision_steps(self):
        case = ClinicalCase.objects.create(
            slug="revision-detail-case",
            title="Revision Detail",
            patient_summary="summary",
            primary_disorder=self.disorder,
            is_active=True,
        )
        revision_one = self.create_case_revision(case)
        CaseStep.objects.create(
            case=case,
            revision=revision_one,
            stable_key="old-step",
            title="Old step",
            narrative="old",
            sort_order=1,
        )
        revision_two = CaseRevision.objects.create(
            case=case,
            version=2,
            title=case.title,
            patient_summary=case.patient_summary,
            primary_disorder=self.disorder,
            status=CaseRevision.Status.PUBLISHED,
        )
        new_step = CaseStep.objects.create(
            case=case,
            revision=revision_two,
            stable_key="new-step",
            title="New step",
            narrative="new",
            sort_order=1,
        )
        revision_two.entry_step = new_step
        revision_two.save(update_fields=("entry_step", "updated_at"))
        case.current_revision = revision_two
        case.save(update_fields=("current_revision", "updated_at"))

        response = self.client.get(f"/api/cases/{case.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["revision_number"], 2)
        self.assertEqual([row["title"] for row in response.json()["steps"]], ["New step"])

    def test_case_graph_validator_rejects_cycle(self):
        case = ClinicalCase.objects.create(
            slug="cycle-case",
            title="Cycle Case",
            patient_summary="summary",
            primary_disorder=self.disorder,
            structure_mode=ClinicalCase.StructureMode.BRANCHING,
        )
        revision = self.create_case_revision(case)
        first = CaseStep.objects.create(
            case=case,
            revision=revision,
            stable_key="first",
            title="First",
            narrative="first",
            sort_order=1,
            node_kind=CaseStep.NodeKind.INFORMATION,
        )
        second = CaseStep.objects.create(
            case=case,
            revision=revision,
            stable_key="second",
            title="Second",
            narrative="second",
            sort_order=2,
            node_kind=CaseStep.NodeKind.INFORMATION,
        )
        revision.entry_step = first
        revision.save(update_fields=("entry_step", "updated_at"))
        CaseTransition.objects.create(
            revision=revision,
            source_step=first,
            target_step=second,
            outcome=CaseTransition.Outcome.CONTINUE,
        )
        CaseTransition.objects.create(
            revision=revision,
            source_step=second,
            target_step=first,
            outcome=CaseTransition.Outcome.CONTINUE,
        )

        issues = validate_case_revision_graph(revision)
        self.assertIn("cycle_detected", issues)
        self.assertIn("entry_has_no_completion_path", issues)

    def test_active_case_without_published_revision_is_not_public(self):
        case = ClinicalCase.objects.create(
            slug="case-without-revision",
            title="Case Without Revision",
            patient_summary="summary",
            primary_disorder=self.disorder,
            is_active=True,
        )
        self.assertEqual(self.client.get(f"/api/cases/{case.slug}/").status_code, 404)
        listing = self.client.get("/api/cases/?page_size=100")
        self.assertNotIn(case.slug, [row["slug"] for row in listing.json()["results"]])

    def test_case_current_revision_must_belong_to_same_case_and_be_published(self):
        first = ClinicalCase.objects.create(
            slug="current-revision-first",
            title="First",
            patient_summary="summary",
            primary_disorder=self.disorder,
            is_active=True,
        )
        second = ClinicalCase.objects.create(
            slug="current-revision-second",
            title="Second",
            patient_summary="summary",
            primary_disorder=self.disorder,
            is_active=True,
        )
        second_revision = self.create_case_revision(second)
        second_step = CaseStep.objects.create(
            case=second,
            revision=second_revision,
            stable_key="step-1",
            title="Step",
            narrative="narrative",
            sort_order=1,
        )
        second_revision.entry_step = second_step
        second_revision.save(update_fields=("entry_step", "updated_at"))

        first.current_revision = second_revision
        with self.assertRaises(ValidationError):
            first.full_clean()

        second_revision.status = CaseRevision.Status.RETIRED
        second_revision.save(update_fields=("status", "updated_at"))
        second.current_revision = second_revision
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_branching_case_rejects_legacy_submit_endpoint(self):
        case = ClinicalCase.objects.create(
            slug="branching-submit-boundary",
            title="Branching Submit Boundary",
            patient_summary="summary",
            primary_disorder=self.disorder,
            structure_mode=ClinicalCase.StructureMode.BRANCHING,
            is_active=True,
        )
        revision = self.create_case_revision(case)
        step = CaseStep.objects.create(
            case=case,
            revision=revision,
            stable_key="entry",
            title="Entry",
            narrative="narrative",
            sort_order=1,
        )
        revision.entry_step = step
        revision.save(update_fields=("entry_step", "updated_at"))
        question = CaseQuestion.objects.create(step=step, prompt="Question", sort_order=1)
        choice = CaseChoice.objects.create(question=question, text="Choice", score_value=1, sort_order=1)
        self.auth(self.user_a)
        response = self.client.post(
            f"/api/cases/{case.slug}/submit/",
            {"answers": [{"question_id": question.id, "choice_id": choice.id}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CaseAttempt.objects.filter(user=self.user_a, case=case).exists())

    def test_case_attempt_answer_rejects_cross_revision_question(self):
        case = ClinicalCase.objects.create(
            slug="answer-revision-integrity",
            title="Answer Revision Integrity",
            patient_summary="summary",
            primary_disorder=self.disorder,
            is_active=True,
        )
        revision_one = self.create_case_revision(case)
        step_one = CaseStep.objects.create(
            case=case,
            revision=revision_one,
            stable_key="step-1",
            title="Step 1",
            narrative="one",
            sort_order=1,
        )
        revision_one.entry_step = step_one
        revision_one.save(update_fields=("entry_step", "updated_at"))
        question_one = CaseQuestion.objects.create(step=step_one, prompt="Q1", sort_order=1)
        CaseChoice.objects.create(question=question_one, text="A1", score_value=1, sort_order=1)

        revision_two = CaseRevision.objects.create(
            case=case,
            version=2,
            title=case.title,
            patient_summary=case.patient_summary,
            primary_disorder=self.disorder,
            status=CaseRevision.Status.PUBLISHED,
        )
        step_two = CaseStep.objects.create(
            case=case,
            revision=revision_two,
            stable_key="step-2",
            title="Step 2",
            narrative="two",
            sort_order=1,
        )
        revision_two.entry_step = step_two
        revision_two.save(update_fields=("entry_step", "updated_at"))
        question_two = CaseQuestion.objects.create(step=step_two, prompt="Q2", sort_order=1)
        choice_two = CaseChoice.objects.create(question=question_two, text="A2", score_value=1, sort_order=1)
        attempt = CaseAttempt.objects.create(user=self.user_a, case=case, revision=revision_one)
        answer = CaseAttemptAnswer(
            attempt=attempt,
            question=question_two,
            selected_choice=choice_two,
            awarded_score=1,
        )
        with self.assertRaises(ValidationError):
            answer.full_clean()

    def test_case_public_query_budget_remains_bounded(self):
        call_command("seed_mvp", verbosity=0)
        case = ClinicalCase.objects.get(slug="case-sudden-fear-01")
        with CaptureQueriesContext(connection) as list_queries:
            list_response = self.client.get("/api/cases/?page_size=100")
        self.assertEqual(list_response.status_code, 200)
        self.assertLessEqual(len(list_queries), 3)
        with CaptureQueriesContext(connection) as detail_queries:
            detail_response = self.client.get(f"/api/cases/{case.slug}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertLessEqual(len(detail_queries), 4)

    def test_seed_creates_new_case_revision_without_mutating_attempt_history(self):
        from atlas.management.commands import seed_mvp as seed_module

        call_command("seed_mvp", verbosity=0)
        case = ClinicalCase.objects.get(slug="case-sudden-fear-01")
        old_revision = case.current_revision
        old_first_step = old_revision.steps.get(stable_key="step-1")
        old_narrative = old_first_step.narrative
        attempt = CaseAttempt.objects.create(
            user=self.user_a,
            case=case,
            revision=old_revision,
            status=CaseAttempt.Status.COMPLETED,
            score=3,
            max_score=3,
        )

        modified_cases = deepcopy(seed_module.CASES)
        target = next(row for row in modified_cases if row["slug"] == case.slug)
        changed_step = list(target["steps"][0])
        changed_step[1] = changed_step[1] + " نسخه آزمایشی جدید"
        target["steps"][0] = tuple(changed_step)

        with patch.object(seed_module, "CASES", modified_cases):
            call_command("seed_mvp", verbosity=0)

        case.refresh_from_db()
        old_revision.refresh_from_db()
        attempt.refresh_from_db()
        self.assertNotEqual(case.current_revision_id, old_revision.id)
        self.assertEqual(case.current_revision.version, 2)
        self.assertEqual(old_revision.status, CaseRevision.Status.RETIRED)
        self.assertEqual(old_revision.steps.get(stable_key="step-1").narrative, old_narrative)
        self.assertEqual(attempt.revision_id, old_revision.id)
        self.assertIn("نسخه آزمایشی جدید", case.current_revision.steps.get(stable_key="step-1").narrative)
        audit_output = StringIO()
        call_command("audit_case_graphs", stdout=audit_output)
        self.assertIn("Clinical case graph audit PASS", audit_output.getvalue())

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
        revision = self.create_case_revision(case)
        step = CaseStep.objects.create(
            case=case,
            revision=revision,
            stable_key="step-1",
            title="step",
            narrative="narrative",
            sort_order=1,
        )
        revision.entry_step = step
        revision.save(update_fields=("entry_step", "updated_at"))
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
        # v0.6.5 adds three constant node-table reads (Psychologist/Theory/Timeline)
        # while preserving the original non-scaling guarantee for Concept count.
        self.assertLessEqual(len(captured), 13)

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
        revision = self.create_case_revision(clinical_case)
        step = CaseStep.objects.create(
            case=clinical_case,
            revision=revision,
            stable_key="step-1",
            title="step",
            narrative="n",
            sort_order=1,
        )
        revision.entry_step = step
        revision.save(update_fields=("entry_step", "updated_at"))
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
        revision = self.create_case_revision(case)
        step = CaseStep.objects.create(
            case=case,
            revision=revision,
            stable_key="step-1",
            title="Step",
            narrative="N",
            sort_order=1,
        )
        revision.entry_step = step
        revision.save(update_fields=("entry_step", "updated_at"))
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
                    "simple_definition_en": "English definition for the research import test.",
                    "simple_definition_fa": "تعریف فارسی آزمون ورود داده.",
                    "academic_definition_en": "Academic English definition for the research import test.",
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
                    "description_en": "Therapy family used to test research ingestion.",
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
                    "description_en": "Structured classification used by the import test.",
                    "description_fa": "طبقه‌بندی ساختاریافته برای آزمون ورود داده.",
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
                    "academic_definition_en": "Academic definition of the test import therapy.",
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
                    "academic_definition_en": "This incoming text must not overwrite existing curated content.",
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
                    "academic_definition_en": "Academic definition of the test import technique.",
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
                    "definition_en": "Legacy family definition for the research ingestion test.",
                    "definition_fa": "تعریف خانواده قدیمی برای آزمون ورود داده پژوهشی.",
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
                    "description_en": "This record must remain staging-only.",
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
            for source_path in (legacy_path, complete_path):
                dataset = ResearchDataset.objects.get(source_filename=source_path.name)
                self.assertEqual(dataset.raw_text, source_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    hashlib.sha256(dataset.raw_text.encode("utf-8")).hexdigest(),
                    dataset.source_sha256,
                )
                self.assertEqual(
                    dataset.ingestion_audit["list_record_total"],
                    dataset.records.count(),
                )

            complete_dataset = ResearchDataset.objects.get(source_filename=complete_path.name)
            psychologist_audit = complete_dataset.ingestion_audit["bilingual_educational_sections"]["psychologists"]
            self.assertEqual(psychologist_audit["records"], 1)
            self.assertEqual(psychologist_audit["bilingual_name_records"], 1)
            psychologist_record = ResearchRecord.objects.get(
                dataset=complete_dataset,
                section="psychologists",
                external_id="psychologist:test-import-person",
            )
            self.assertEqual(psychologist_record.name_en, "Import Test Researcher")
            self.assertEqual(psychologist_record.name_fa, "پژوهشگر آزمایشی ورود")

            export_dir = directory / "exported"
            call_command("export_research_datasets", str(export_dir), stdout=StringIO())
            for source_path in (legacy_path, complete_path):
                exported_path = export_dir / source_path.name
                self.assertEqual(exported_path.read_bytes(), source_path.read_bytes())
            call_command("verify_research_datasets", stdout=StringIO(), stderr=StringIO())

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
                0,
            )
            imported_psychologist = atlas_models.Psychologist.objects.get(slug="test-import-person")
            self.assertEqual(imported_psychologist.name_en, "Import Test Researcher")
            self.assertTrue(imported_psychologist.source_links.exists())
            self.assertEqual(imported_psychologist.review_status, ScientificReviewStatus.UNREVIEWED)

            stable_counts = {
                "datasets": ResearchDataset.objects.count(),
                "records": ResearchRecord.objects.count(),
                "sources": SourceReference.objects.count(),
                "therapies": Therapy.objects.count(),
                "techniques": Technique.objects.count(),
                "concepts": Concept.objects.count(),
                "relations": TherapyTechnique.objects.count(),
                "psychologists": atlas_models.Psychologist.objects.count(),
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
            self.assertEqual(stable_counts["psychologists"], atlas_models.Psychologist.objects.count())

            call_command("seed_mvp", stdout=StringIO())
            self.assertTrue(atlas_models.Psychologist.objects.filter(pk=imported_psychologist.pk, is_active=True).exists())
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


class V061ArchitectureFoundationTests(APITestCase):
    def setUp(self):
        self.source = SourceReference.objects.create(
            title="v0.6.1 architecture test source",
            organization="Psychology Atlas Test",
            verification_status="verified",
        )
        self.category = Category.objects.create(slug="v061-category", name_en="v0.6.1 Category")
        self.concept = Concept.objects.create(
            slug="v061-concept",
            name_en="v0.6.1 Concept",
            name_fa="مفهوم نسخه ۰.۶.۱",
        )
        self.family = TherapyFamily.objects.create(
            slug="v061-family",
            name_en="v0.6.1 Family",
            name_fa="خانواده نسخه ۰.۶.۱",
        )
        self.therapy = Therapy.objects.create(
            family=self.family,
            slug="v061-therapy",
            name_en="v0.6.1 Therapy",
            name_fa="درمان نسخه ۰.۶.۱",
        )
        self.technique = Technique.objects.create(
            slug="v061-technique",
            name_en="v0.6.1 Technique",
            name_fa="تکنیک نسخه ۰.۶.۱",
        )
        self.psychologist = atlas_models.Psychologist.objects.create(
            slug="test-researcher",
            name_en="Test Researcher",
            name_fa="پژوهشگر آزمایشی",
            birth_year=1900,
            death_year=1980,
        )
        self.theory = atlas_models.Theory.objects.create(
            slug="test-theory",
            name_en="Test Theory",
            name_fa="نظریه آزمایشی",
            domain="cognitive_psychology",
        )
        self.event = atlas_models.TimelineEvent.objects.create(
            slug="test-event-1960",
            title_en="Test event",
            title_fa="رویداد آزمایشی",
            date_precision=atlas_models.TimelineEvent.DatePrecision.YEAR,
            year_start=1960,
            date_text="1960",
        )

    def test_canonical_entities_are_bilingual_review_safe_and_not_seed_owned(self):
        self.assertEqual(self.psychologist.name_fa, "پژوهشگر آزمایشی")
        self.assertEqual(self.theory.name_fa, "نظریه آزمایشی")
        self.assertEqual(self.event.title_fa, "رویداد آزمایشی")
        self.assertEqual(self.psychologist.review_status, ScientificReviewStatus.UNREVIEWED)
        self.assertEqual(self.theory.review_status, ScientificReviewStatus.UNREVIEWED)
        self.assertEqual(self.event.review_status, ScientificReviewStatus.UNREVIEWED)
        self.assertFalse(self.psychologist.seed_managed)
        self.assertFalse(self.theory.seed_managed)
        self.assertFalse(self.event.seed_managed)

    def test_aliases_are_explicit_and_deduplicated_per_language(self):
        atlas_models.PsychologistAlias.objects.create(
            psychologist=self.psychologist,
            text="T. Researcher",
            language=atlas_models.PsychologistAlias.Language.EN,
            alias_type=atlas_models.PsychologistAlias.AliasType.INITIALS,
        )
        duplicate = atlas_models.PsychologistAlias(
            psychologist=self.psychologist,
            text="T. Researcher",
            language=atlas_models.PsychologistAlias.Language.EN,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

        atlas_models.TheoryAlias.objects.create(
            theory=self.theory,
            text="TT",
            language=atlas_models.TheoryAlias.Language.EN,
            alias_type=atlas_models.TheoryAlias.AliasType.ABBREVIATION,
        )
        self.assertEqual(self.theory.aliases.count(), 1)

    def test_psychologist_life_year_order_is_validated(self):
        invalid = atlas_models.Psychologist(
            slug="invalid-life-years",
            name_en="Invalid Life Years",
            birth_year=2000,
            death_year=1900,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_timeline_year_only_does_not_allow_fabricated_exact_date(self):
        year_only = atlas_models.TimelineEvent(
            slug="year-only-event",
            title_en="Year only",
            date_precision=atlas_models.TimelineEvent.DatePrecision.YEAR,
            year_start=1879,
            date_text="1879",
        )
        year_only.full_clean()

        fabricated_precision = atlas_models.TimelineEvent(
            slug="fabricated-exact-event",
            title_en="Fabricated exact date",
            date_precision=atlas_models.TimelineEvent.DatePrecision.YEAR,
            year_start=1879,
            exact_date=date(1879, 1, 1),
        )
        with self.assertRaises(ValidationError):
            fabricated_precision.full_clean()

    def test_timeline_range_and_exact_date_precision_are_explicit(self):
        valid_range = atlas_models.TimelineEvent(
            slug="valid-range",
            title_en="Valid range",
            date_precision=atlas_models.TimelineEvent.DatePrecision.YEAR_RANGE,
            year_start=1963,
            year_end=1979,
            date_text="1963-1979",
        )
        valid_range.full_clean()

        missing_range_end = atlas_models.TimelineEvent(
            slug="missing-range-end",
            title_en="Missing end",
            date_precision=atlas_models.TimelineEvent.DatePrecision.YEAR_RANGE,
            year_start=1963,
        )
        with self.assertRaises(ValidationError):
            missing_range_end.full_clean()

        exact = atlas_models.TimelineEvent(
            slug="exact-event",
            title_en="Exact event",
            date_precision=atlas_models.TimelineEvent.DatePrecision.EXACT_DATE,
            exact_date=date(2000, 1, 2),
            date_text="2000-01-02",
        )
        exact.full_clean()

    def test_entity_provenance_reuses_shared_source_reference_registry(self):
        psychologist_source = atlas_models.PsychologistSource.objects.create(
            psychologist=self.psychologist,
            source=self.source,
            role=atlas_models.PsychologistSource.Role.BIOGRAPHY,
        )
        theory_source = atlas_models.TheorySource.objects.create(
            theory=self.theory,
            source=self.source,
            role=atlas_models.TheorySource.Role.PRIMARY_PUBLICATION,
        )
        event_source = atlas_models.TimelineEventSource.objects.create(
            event=self.event,
            source=self.source,
            role=atlas_models.TimelineEventSource.Role.HISTORICAL_REVIEW,
        )
        self.assertEqual(psychologist_source.source_id, self.source.id)
        self.assertEqual(theory_source.source_id, self.source.id)
        self.assertEqual(event_source.source_id, self.source.id)
        self.assertEqual(SourceReference.objects.count(), 1)

    def test_psychologist_theory_attribution_is_explicit_and_source_aware(self):
        relationship = atlas_models.PsychologistTheory.objects.create(
            psychologist=self.psychologist,
            theory=self.theory,
            relationship_type=atlas_models.PsychologistAttributionType.PROPOSED,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.PsychologistTheorySource.objects.create(
            relationship=relationship,
            source=self.source,
        )
        self.assertEqual(relationship.relationship_type, "proposed")
        self.assertEqual(relationship.source_links.count(), 1)
        self.assertNotEqual(relationship.review_status, ScientificReviewStatus.REVIEWED)

    def test_real_staging_theory_to_technique_semantic_has_canonical_model(self):
        relationship = atlas_models.TheoryTechnique.objects.create(
            theory=self.theory,
            technique=self.technique,
            relationship_type=atlas_models.TheoryRelationType.GROUNDS,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TheoryTechniqueSource.objects.create(
            relationship=relationship,
            source=self.source,
        )
        self.assertEqual(relationship.relationship_type, "grounds")
        self.assertTrue(relationship.source_links.filter(source=self.source).exists())

    def test_self_relations_are_rejected(self):
        self_person_relation = atlas_models.PsychologistPsychologist(
            psychologist=self.psychologist,
            related_psychologist=self.psychologist,
            relationship_type=atlas_models.PsychologistRelationshipType.ASSOCIATED_WITH,
        )
        with self.assertRaises(ValidationError):
            self_person_relation.full_clean()

        self_theory_relation = atlas_models.TheoryTheory(
            theory=self.theory,
            related_theory=self.theory,
            relationship_type=atlas_models.TheoryRelationType.ASSOCIATED_WITH,
        )
        with self.assertRaises(ValidationError):
            self_theory_relation.full_clean()

    def test_timeline_cross_domain_links_are_explicit(self):
        psychologist_link = atlas_models.TimelinePsychologist.objects.create(
            event=self.event,
            psychologist=self.psychologist,
            role=atlas_models.TimelineLinkRole.SUBJECT,
        )
        theory_link = atlas_models.TimelineTheory.objects.create(
            event=self.event,
            theory=self.theory,
            role=atlas_models.TimelineLinkRole.RELATED,
        )
        therapy_link = atlas_models.TimelineTherapy.objects.create(
            event=self.event,
            therapy=self.therapy,
            role=atlas_models.TimelineLinkRole.RELATED,
        )
        concept_link = atlas_models.TimelineConcept.objects.create(
            event=self.event,
            concept=self.concept,
            role=atlas_models.TimelineLinkRole.RELATED,
        )
        for relationship, source_model in (
            (psychologist_link, atlas_models.TimelinePsychologistSource),
            (theory_link, atlas_models.TimelineTheorySource),
            (therapy_link, atlas_models.TimelineTherapySource),
            (concept_link, atlas_models.TimelineConceptSource),
        ):
            source_model.objects.create(relationship=relationship, source=self.source)
            self.assertEqual(relationship.source_links.count(), 1)

    def test_research_record_creation_does_not_blindly_promote_v061_entities(self):
        dataset = ResearchDataset.objects.create(
            key="v061-staging-only",
            source_filename="v061-staging-only.json",
            source_sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            dataset_name="v0.6.1 Staging Only",
        )
        initial_count = atlas_models.Psychologist.objects.count()
        ResearchRecord.objects.create(
            dataset=dataset,
            section="psychologists",
            external_id="psychologist:staging-only",
            canonical_key="psychologist:staging-only",
            slug="staging-only",
            name_en="Staging Only",
            name_fa="فقط مرحله پژوهش",
            payload={"id": "psychologist:staging-only", "name_en": "Staging Only"},
        )
        self.assertEqual(atlas_models.Psychologist.objects.count(), initial_count)
        record = ResearchRecord.objects.get(dataset=dataset, external_id="psychologist:staging-only")
        self.assertEqual(record.promoted_model, "")
        self.assertIsNone(record.promoted_pk)


class V062ResearchPromotionTests(APITestCase):
    def setUp(self):
        self.dataset = ResearchDataset.objects.create(
            key="v062-promotion-fixture",
            source_filename="v062-promotion-fixture.json",
            source_sha256="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            dataset_name="v0.6.2 Promotion Fixture",
            dataset_version="v0.6.2-test",
        )
        self.source = SourceReference.objects.create(
            title="v0.6.2 promotion source",
            verification_status="verified",
        )
        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="sources",
            external_id="source:v062-primary",
            canonical_key="source:v062-primary",
            name_en="v0.6.2 promotion source",
            payload={"id": "source:v062-primary", "title": "v0.6.2 promotion source"},
            promoted_model="atlas.sourcereference",
            promoted_pk=self.source.pk,
        )

        self.concept = Concept.objects.create(
            slug="v062-construct",
            name_en="v0.6.2 Construct",
            name_fa="سازه نسخه ۰.۶.۲",
        )
        self.family = TherapyFamily.objects.create(
            slug="v062-family",
            name_en="v0.6.2 Family",
            name_fa="خانواده نسخه ۰.۶.۲",
        )
        self.therapy = Therapy.objects.create(
            family=self.family,
            slug="v062-therapy",
            name_en="v0.6.2 Therapy",
            name_fa="درمان نسخه ۰.۶.۲",
        )
        self.technique = Technique.objects.create(
            slug="v062-technique",
            name_en="v0.6.2 Technique",
            name_fa="تکنیک نسخه ۰.۶.۲",
        )
        for section, external_id, obj in (
            ("concepts", "concept:v062-construct", self.concept),
            ("therapies", "therapy:v062-therapy", self.therapy),
            ("techniques", "technique:v062-technique", self.technique),
        ):
            ResearchRecord.objects.create(
                dataset=self.dataset,
                section=section,
                external_id=external_id,
                canonical_key=external_id,
                slug=obj.slug,
                name_en=obj.name_en,
                name_fa=obj.name_fa,
                payload={"id": external_id, "slug": obj.slug, "name_en": obj.name_en},
                promoted_model=obj._meta.label_lower,
                promoted_pk=obj.pk,
            )

        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="psychologists",
            external_id="psychologist:ivan-pavlov",
            canonical_key="psychologist:name:ivan p pavlov",
            name_en="Ivan P. Pavlov",
            name_fa="ایوان پاولف",
            source_ids=["source:v062-primary"],
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
            payload={
                "id": "psychologist:ivan-pavlov",
                "full_name": "Ivan P. Pavlov",
                "name_fa": "ایوان پاولف",
                "birth_year": None,
                "death_year": None,
                "nationality_background": "Russian",
                "academic_disciplines": ["physiology"],
                "major_contributions": ["Source-checked contribution"],
                "historical_context": "Source-checked historical context.",
                "source_ids": ["source:v062-primary"],
                "review": {"status": "source_checked"},
            },
        )
        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="psychologists",
            external_id="ps_pavlov_ivan",
            canonical_key="psychologist:ivan-pavlov",
            slug="ivan-pavlov",
            name_en="Ivan Pavlov",
            name_fa="ایوان پ. پاولف",
            payload={
                "psychologist_id": "ps_pavlov_ivan",
                "slug": "ivan-pavlov",
                "name_en": "Ivan Pavlov",
                "name_fa": "ایوان پ. پاولف",
                "born": 1849,
                "died": 1936,
                "key_works": ["source:v062-primary"],
                "key_contributions": ["Legacy contribution must not create field-level reviewed biography."],
            },
        )
        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="psychologists",
            external_id="psychologist:unsourced-person",
            canonical_key="psychologist:unsourced-person",
            name_en="Unsourced Person",
            name_fa="فرد بدون منبع",
            payload={"id": "psychologist:unsourced-person", "full_name": "Unsourced Person"},
        )

        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="theories",
            external_id="theory:beck-cognitive-model",
            canonical_key="theorie:beck-cognitive-model",
            name_en="Beck Cognitive Model",
            name_fa="مدل شناختی بک",
            source_ids=["source:v062-primary"],
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
            payload={
                "id": "theory:beck-cognitive-model",
                "slug": "beck-cognitive-model",
                "name_en": "Beck Cognitive Model",
                "name_fa": "مدل شناختی بک",
                "summary_en": "Source-checked model summary.",
                "summary_fa": "خلاصه فارسی مدل.",
                "theory_family_domain": "cognitive_psychology",
                "source_ids": ["source:v062-primary"],
                "review": {"status": "source_checked"},
            },
        )
        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="theories",
            external_id="the_beck_cognitive_model",
            canonical_key="theorie:beck-cognitive-model",
            slug="beck-cognitive-model",
            name_en="Beck's cognitive model",
            name_fa="الگوی شناختی بک",
            source_ids=["source:v062-primary"],
            payload={
                "theory_id": "the_beck_cognitive_model",
                "slug": "beck-cognitive-model",
                "name_en": "Beck's cognitive model",
                "name_fa": "الگوی شناختی بک",
                "domain": "cognitive_psychology",
                "core_proposition_en": "Legacy source-linked proposition.",
                "core_proposition_fa": "گزاره فارسی منبع‌دار.",
                "sources": ["source:v062-primary"],
            },
        )
        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="theories",
            external_id="theory:unsourced-theory",
            canonical_key="theorie:unsourced-theory",
            name_en="Unsourced Theory",
            name_fa="نظریه بدون منبع",
            payload={"id": "theory:unsourced-theory", "name_en": "Unsourced Theory"},
        )

        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="timeline_events",
            external_id="event:1879-v062-event",
            canonical_key="timeline_event:name:v062 event",
            name_en="v0.6.2 Event",
            name_fa="رویداد نسخه ۰.۶.۲",
            source_ids=["source:v062-primary"],
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
            payload={
                "id": "event:1879-v062-event",
                "date": "1879",
                "year": 1879,
                "date_precision": "year",
                "title_en": "v0.6.2 Event",
                "title_fa": "رویداد نسخه ۰.۶.۲",
                "description_en": "Source-backed historical event.",
                "description_fa": "رویداد تاریخی منبع‌دار.",
                "people_ids": ["psychologist:ivan-pavlov"],
                "theory_ids": ["theory:beck-cognitive-model"],
                "concept_ids": ["concept:v062-construct"],
                "therapy_ids": ["therapy:v062-therapy"],
                "source_ids": ["source:v062-primary"],
                "review": {"status": "source_checked"},
            },
        )
        ResearchRecord.objects.create(
            dataset=self.dataset,
            section="timeline_events",
            external_id="event:unsourced-v062-event",
            canonical_key="timeline_event:name:unsourced event",
            name_en="Unsourced v0.6.2 Event",
            name_fa="رویداد بدون منبع",
            payload={
                "id": "event:unsourced-v062-event",
                "year": 1900,
                "title_en": "Unsourced v0.6.2 Event",
            },
        )

        relation_payloads = [
            ("relation:v062-person-concept", "psychologist:ivan-pavlov", "concept:v062-construct", "researched_or_developed", ["source:v062-primary"]),
            ("relation:v062-person-theory", "psychologist:ivan-pavlov", "theory:beck-cognitive-model", "developed_or_majorly_associated_with", ["source:v062-primary"]),
            ("relation:v062-theory-concept", "theory:beck-cognitive-model", "concept:v062-construct", "includes_construct", ["source:v062-primary"]),
            ("relation:v062-event-person", "event:1879-v062-event", "psychologist:ivan-pavlov", "involves_person", ["source:v062-primary"]),
            ("relation:v062-event-theory", "event:1879-v062-event", "theory:beck-cognitive-model", "marks_theory_milestone", ["source:v062-primary"]),
            ("relation:v062-event-therapy", "event:1879-v062-event", "therapy:v062-therapy", "marks_therapy_milestone", ["source:v062-primary"]),
            ("relation:v062-event-technique", "event:1879-v062-event", "technique:v062-technique", "marks_technique_evidence_milestone", ["source:v062-primary"]),
            ("relation:v062-unsourced", "psychologist:ivan-pavlov", "therapy:v062-therapy", "developed", []),
        ]
        for external_id, source_id, target_id, relation_type, source_ids in relation_payloads:
            ResearchRecord.objects.create(
                dataset=self.dataset,
                section="relationships",
                external_id=external_id,
                canonical_key=external_id,
                source_ids=source_ids,
                payload={
                    "id": external_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": relation_type,
                    "source_ids": source_ids,
                },
            )

    def test_source_backed_promotion_dedupes_aliases_and_preserves_uncertainty(self):
        call_command("promote_research_staging", stdout=StringIO())
        self.assertEqual(atlas_models.Psychologist.objects.count(), 1)
        psychologist = atlas_models.Psychologist.objects.get(slug="ivan-pavlov")
        self.assertEqual(psychologist.name_en, "Ivan P. Pavlov")
        self.assertEqual(psychologist.nationality_en, "Russian")
        self.assertIsNone(psychologist.birth_year)
        self.assertIsNone(psychologist.death_year)
        self.assertTrue(psychologist.source_links.exists())
        self.assertTrue(psychologist.aliases.filter(text="Ivan Pavlov", language="en").exists())
        self.assertTrue(psychologist.aliases.filter(text="ایوان پ. پاولف", language="fa").exists())
        self.assertFalse(atlas_models.Psychologist.objects.filter(name_en="Unsourced Person").exists())

        self.assertEqual(atlas_models.Theory.objects.count(), 1)
        theory = atlas_models.Theory.objects.get(slug="beck-cognitive-model")
        self.assertEqual(theory.name_en, "Beck Cognitive Model")
        self.assertTrue(theory.aliases.filter(text="Beck's cognitive model", language="en").exists())
        self.assertTrue(theory.source_links.exists())
        self.assertFalse(atlas_models.Theory.objects.filter(name_en="Unsourced Theory").exists())

        theory_records = ResearchRecord.objects.filter(section="theories", name_en__icontains="Beck")
        self.assertEqual(set(theory_records.values_list("promoted_pk", flat=True)), {theory.pk})
        self.assertTrue(all(key.startswith("theory:") for key in theory_records.values_list("canonical_key", flat=True)))
        self.assertFalse(ResearchRecord.objects.filter(section="theories", canonical_key__startswith="theorie:").exists())

        self.assertEqual(atlas_models.TimelineEvent.objects.count(), 1)
        event = atlas_models.TimelineEvent.objects.get(slug="1879-v062-event")
        self.assertEqual(event.date_precision, atlas_models.TimelineEvent.DatePrecision.YEAR)
        self.assertEqual(event.year_start, 1879)
        self.assertIsNone(event.exact_date)
        self.assertFalse(atlas_models.TimelineEvent.objects.filter(title_en="Unsourced v0.6.2 Event").exists())
        self.assertFalse(ResearchRecord.objects.filter(section="timeline_events", canonical_key__startswith="timeline_event:").exists())

    def test_only_explicit_source_backed_relationships_are_promoted(self):
        call_command("promote_research_staging", stdout=StringIO())
        psychologist = atlas_models.Psychologist.objects.get(slug="ivan-pavlov")
        theory = atlas_models.Theory.objects.get(slug="beck-cognitive-model")
        person_concept = atlas_models.PsychologistConcept.objects.get(
            psychologist=psychologist,
            concept=self.concept,
            relationship_type=atlas_models.PsychologistAttributionType.RESEARCHED_OR_DEVELOPED,
        )
        person_theory = atlas_models.PsychologistTheory.objects.get(
            psychologist=psychologist,
            theory=theory,
            relationship_type=atlas_models.PsychologistAttributionType.DEVELOPED_OR_MAJORLY_ASSOCIATED_WITH,
        )
        theory_concept = atlas_models.TheoryConcept.objects.get(
            theory=theory,
            concept=self.concept,
            relationship_type=atlas_models.TheoryRelationType.INCLUDES_CONSTRUCT,
        )
        for relationship in (person_concept, person_theory, theory_concept):
            self.assertEqual(relationship.review_status, ScientificReviewStatus.SOURCE_CHECKED)
            self.assertTrue(relationship.source_links.filter(source=self.source).exists())
            self.assertFalse(relationship.seed_managed)
        unsourced = ResearchRecord.objects.get(external_id="relation:v062-unsourced")
        self.assertEqual(unsourced.promoted_model, "")
        self.assertIsNone(unsourced.promoted_pk)
        self.assertFalse(atlas_models.PsychologistTherapy.objects.filter(psychologist=psychologist, therapy=self.therapy).exists())

    def test_timeline_links_are_cross_domain_and_source_backed(self):
        call_command("promote_research_staging", stdout=StringIO())
        event = atlas_models.TimelineEvent.objects.get(slug="1879-v062-event")
        person_link = atlas_models.TimelinePsychologist.objects.get(event=event)
        theory_link = atlas_models.TimelineTheory.objects.get(event=event)
        therapy_link = atlas_models.TimelineTherapy.objects.get(event=event)
        technique_link = atlas_models.TimelineTechnique.objects.get(event=event)
        self.assertEqual(person_link.role, atlas_models.TimelineLinkRole.INVOLVES_PERSON)
        self.assertEqual(theory_link.role, atlas_models.TimelineLinkRole.MARKS_THEORY_MILESTONE)
        self.assertEqual(therapy_link.role, atlas_models.TimelineLinkRole.MARKS_THERAPY_MILESTONE)
        self.assertEqual(
            technique_link.role,
            atlas_models.TimelineLinkRole.MARKS_TECHNIQUE_EVIDENCE_MILESTONE,
        )
        self.assertEqual(atlas_models.TimelinePsychologist.objects.filter(event=event).count(), 1)
        self.assertEqual(atlas_models.TimelineTheory.objects.filter(event=event).count(), 1)
        self.assertEqual(atlas_models.TimelineTherapy.objects.filter(event=event).count(), 1)
        self.assertEqual(atlas_models.TimelineTechnique.objects.filter(event=event).count(), 1)
        links = [
            person_link,
            theory_link,
            therapy_link,
            technique_link,
            atlas_models.TimelineConcept.objects.get(event=event),
        ]
        for link in links:
            self.assertEqual(link.review_status, ScientificReviewStatus.SOURCE_CHECKED)
            self.assertTrue(link.source_links.filter(source=self.source).exists())
            self.assertFalse(link.seed_managed)

    def test_promotion_is_idempotent(self):
        call_command("promote_research_staging", stdout=StringIO())
        stable_counts = {
            "psychologists": atlas_models.Psychologist.objects.count(),
            "psychologist_aliases": atlas_models.PsychologistAlias.objects.count(),
            "theories": atlas_models.Theory.objects.count(),
            "theory_aliases": atlas_models.TheoryAlias.objects.count(),
            "timeline": atlas_models.TimelineEvent.objects.count(),
            "person_concepts": atlas_models.PsychologistConcept.objects.count(),
            "person_theories": atlas_models.PsychologistTheory.objects.count(),
            "theory_concepts": atlas_models.TheoryConcept.objects.count(),
            "timeline_people": atlas_models.TimelinePsychologist.objects.count(),
            "timeline_theories": atlas_models.TimelineTheory.objects.count(),
            "timeline_concepts": atlas_models.TimelineConcept.objects.count(),
            "timeline_therapies": atlas_models.TimelineTherapy.objects.count(),
            "timeline_techniques": atlas_models.TimelineTechnique.objects.count(),
        }
        call_command("promote_research_staging", stdout=StringIO())
        self.assertEqual(stable_counts["psychologists"], atlas_models.Psychologist.objects.count())
        self.assertEqual(stable_counts["psychologist_aliases"], atlas_models.PsychologistAlias.objects.count())
        self.assertEqual(stable_counts["theories"], atlas_models.Theory.objects.count())
        self.assertEqual(stable_counts["theory_aliases"], atlas_models.TheoryAlias.objects.count())
        self.assertEqual(stable_counts["timeline"], atlas_models.TimelineEvent.objects.count())
        self.assertEqual(stable_counts["person_concepts"], atlas_models.PsychologistConcept.objects.count())
        self.assertEqual(stable_counts["person_theories"], atlas_models.PsychologistTheory.objects.count())
        self.assertEqual(stable_counts["theory_concepts"], atlas_models.TheoryConcept.objects.count())
        self.assertEqual(stable_counts["timeline_people"], atlas_models.TimelinePsychologist.objects.count())
        self.assertEqual(stable_counts["timeline_theories"], atlas_models.TimelineTheory.objects.count())
        self.assertEqual(stable_counts["timeline_concepts"], atlas_models.TimelineConcept.objects.count())
        self.assertEqual(stable_counts["timeline_therapies"], atlas_models.TimelineTherapy.objects.count())
        self.assertEqual(stable_counts["timeline_techniques"], atlas_models.TimelineTechnique.objects.count())

    def test_dry_run_rolls_back_every_runtime_and_staging_index_change(self):
        before_theory_key = ResearchRecord.objects.get(external_id="theory:beck-cognitive-model").canonical_key
        call_command("promote_research_staging", "--dry-run", stdout=StringIO())
        self.assertEqual(atlas_models.Psychologist.objects.count(), 0)
        self.assertEqual(atlas_models.Theory.objects.count(), 0)
        self.assertEqual(atlas_models.TimelineEvent.objects.count(), 0)
        self.assertEqual(
            ResearchRecord.objects.get(external_id="theory:beck-cognitive-model").canonical_key,
            before_theory_key,
        )


class V063KnowledgeApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = SourceReference.objects.create(
            title="v0.6.3 canonical source",
            organization="Psychology Atlas Tests",
            citation="Test citation",
            url="https://example.org/v063-source",
            publication_year=1980,
            source_type="journal_article",
            authors=["A. Researcher", "B. Researcher"],
            doi="10.1234/v063",
            pmid="12345678",
            verification_status="verified",
        )
        cls.concept = Concept.objects.create(
            slug="v063-learning-process",
            name_en="v0.6.3 Learning Process",
            name_fa="فرایند یادگیری نسخه ۰.۶.۳",
            simple_definition="A test learning construct.",
            kind=Concept.Kind.COGNITIVE,
            domain=Concept.Domain.COGNITIVE_PSYCHOLOGY,
        )
        cls.family = TherapyFamily.objects.create(
            slug="v063-family",
            name_en="v0.6.3 Family",
            name_fa="خانواده نسخه ۰.۶.۳",
        )
        cls.therapy = Therapy.objects.create(
            family=cls.family,
            slug="v063-therapy",
            name_en="v0.6.3 Therapy",
            name_fa="درمان نسخه ۰.۶.۳",
            summary="Educational test therapy.",
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        cls.technique = Technique.objects.create(
            slug="v063-technique",
            name_en="v0.6.3 Technique",
            name_fa="تکنیک نسخه ۰.۶.۳",
            summary="Educational test technique.",
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        cls.psychologist = atlas_models.Psychologist.objects.create(
            slug="jane-researcher",
            name_en="Jane Q. Researcher",
            name_fa="جین پژوهشگر",
            summary_en="A source-checked test psychologist.",
            summary_fa="روان‌شناس آزمایشی منبع‌دار.",
            role_en="Research psychologist",
            nationality_en="Testland",
            birth_year=1940,
            academic_disciplines=["cognitive psychology"],
            contributions_en=["A test contribution"],
            affiliations=["Test University"],
            historical_context_en="Test historical context.",
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        cls.other_psychologist = atlas_models.Psychologist.objects.create(
            slug="alex-researcher",
            name_en="Alex Researcher",
            name_fa="الکس پژوهشگر",
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        cls.inactive_psychologist = atlas_models.Psychologist.objects.create(
            slug="inactive-researcher",
            name_en="Inactive Researcher",
            is_active=False,
        )
        atlas_models.PsychologistAlias.objects.create(
            psychologist=cls.psychologist,
            text="J. Researcher",
            language=atlas_models.PsychologistAlias.Language.EN,
            alias_type=atlas_models.PsychologistAlias.AliasType.INITIALS,
        )
        atlas_models.PsychologistSource.objects.create(
            psychologist=cls.psychologist,
            source=cls.source,
            role=atlas_models.PsychologistSource.Role.BIOGRAPHY,
            note="Biography source",
        )

        cls.theory = atlas_models.Theory.objects.create(
            slug="v063-model",
            name_en="v0.6.3 Model",
            name_fa="مدل نسخه ۰.۶.۳",
            domain="cognitive_psychology",
            period_text="late_20th_century",
            summary_en="A test theory summary.",
            summary_fa="خلاصه نظریه آزمایشی.",
            core_proposition_en="A source-backed test proposition.",
            key_propositions_en=["Test proposition one"],
            applications_en=["Education"],
            criticisms_en=["Test criticism"],
            limitations_en=["Test limitation"],
            modern_status="active_empirical_framework",
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        cls.related_theory = atlas_models.Theory.objects.create(
            slug="v063-related-model",
            name_en="v0.6.3 Related Model",
            name_fa="مدل مرتبط نسخه ۰.۶.۳",
            domain="cognitive_psychology",
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        cls.inactive_theory = atlas_models.Theory.objects.create(
            slug="inactive-theory-v063",
            name_en="Inactive Theory v0.6.3",
            is_active=False,
        )
        atlas_models.TheoryAlias.objects.create(
            theory=cls.theory,
            text="V63M",
            language=atlas_models.TheoryAlias.Language.EN,
            alias_type=atlas_models.TheoryAlias.AliasType.ABBREVIATION,
        )
        atlas_models.TheorySource.objects.create(
            theory=cls.theory,
            source=cls.source,
            role=atlas_models.TheorySource.Role.PRIMARY_PUBLICATION,
            note="Primary publication",
        )

        cls.event = atlas_models.TimelineEvent.objects.create(
            slug="v063-event-1980",
            title_en="v0.6.3 Event",
            title_fa="رویداد نسخه ۰.۶.۳",
            description_en="A source-backed event in 1980.",
            description_fa="رویداد منبع‌دار در سال ۱۹۸۰.",
            historical_importance_en="Test historical importance.",
            event_type=atlas_models.TimelineEvent.EventType.THEORY_DEVELOPMENT,
            category="theory_history",
            date_precision=atlas_models.TimelineEvent.DatePrecision.YEAR,
            date_text="1980",
            year_start=1980,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        cls.later_event = atlas_models.TimelineEvent.objects.create(
            slug="v063-event-1995",
            title_en="Later v0.6.3 Event",
            title_fa="رویداد بعدی نسخه ۰.۶.۳",
            event_type=atlas_models.TimelineEvent.EventType.RESEARCH_FINDING,
            category="research_history",
            date_precision=atlas_models.TimelineEvent.DatePrecision.YEAR,
            date_text="1995",
            year_start=1995,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        cls.inactive_event = atlas_models.TimelineEvent.objects.create(
            slug="inactive-event-v063",
            title_en="Inactive Event v0.6.3",
            date_precision=atlas_models.TimelineEvent.DatePrecision.YEAR,
            date_text="1970",
            year_start=1970,
            is_active=False,
        )
        atlas_models.TimelineEventSource.objects.create(
            event=cls.event,
            source=cls.source,
            role=atlas_models.TimelineEventSource.Role.HISTORICAL_REVIEW,
        )

        cls.person_theory = atlas_models.PsychologistTheory.objects.create(
            psychologist=cls.psychologist,
            theory=cls.theory,
            relationship_type=atlas_models.PsychologistAttributionType.PROPOSED,
            explanation_en="Proposed the test model.",
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.PsychologistTheorySource.objects.create(
            relationship=cls.person_theory,
            source=cls.source,
        )
        cls.person_concept = atlas_models.PsychologistConcept.objects.create(
            psychologist=cls.psychologist,
            concept=cls.concept,
            relationship_type=atlas_models.PsychologistAttributionType.RESEARCHED,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.PsychologistConceptSource.objects.create(
            relationship=cls.person_concept,
            source=cls.source,
        )
        cls.person_therapy = atlas_models.PsychologistTherapy.objects.create(
            psychologist=cls.psychologist,
            therapy=cls.therapy,
            relationship_type=atlas_models.PsychologistAttributionType.DEVELOPED,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.PsychologistTherapySource.objects.create(
            relationship=cls.person_therapy,
            source=cls.source,
        )
        cls.person_person = atlas_models.PsychologistPsychologist.objects.create(
            psychologist=cls.psychologist,
            related_psychologist=cls.other_psychologist,
            relationship_type=atlas_models.PsychologistRelationshipType.INFLUENCED,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.PsychologistPsychologistSource.objects.create(
            relationship=cls.person_person,
            source=cls.source,
        )

        cls.theory_concept = atlas_models.TheoryConcept.objects.create(
            theory=cls.theory,
            concept=cls.concept,
            relationship_type=atlas_models.TheoryRelationType.INCLUDES_CONSTRUCT,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TheoryConceptSource.objects.create(
            relationship=cls.theory_concept,
            source=cls.source,
        )
        cls.theory_therapy = atlas_models.TheoryTherapy.objects.create(
            theory=cls.theory,
            therapy=cls.therapy,
            relationship_type=atlas_models.TheoryRelationType.GROUNDS,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TheoryTherapySource.objects.create(
            relationship=cls.theory_therapy,
            source=cls.source,
        )
        cls.theory_technique = atlas_models.TheoryTechnique.objects.create(
            theory=cls.theory,
            technique=cls.technique,
            relationship_type=atlas_models.TheoryRelationType.GROUNDS,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TheoryTechniqueSource.objects.create(
            relationship=cls.theory_technique,
            source=cls.source,
        )
        cls.theory_theory = atlas_models.TheoryTheory.objects.create(
            theory=cls.theory,
            related_theory=cls.related_theory,
            relationship_type=atlas_models.TheoryRelationType.EXTENDS,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TheoryTheorySource.objects.create(
            relationship=cls.theory_theory,
            source=cls.source,
        )

        cls.timeline_person = atlas_models.TimelinePsychologist.objects.create(
            event=cls.event,
            psychologist=cls.psychologist,
            role=atlas_models.TimelineLinkRole.INVOLVES_PERSON,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TimelinePsychologistSource.objects.create(
            relationship=cls.timeline_person,
            source=cls.source,
        )
        cls.timeline_theory = atlas_models.TimelineTheory.objects.create(
            event=cls.event,
            theory=cls.theory,
            role=atlas_models.TimelineLinkRole.MARKS_THEORY_MILESTONE,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TimelineTheorySource.objects.create(
            relationship=cls.timeline_theory,
            source=cls.source,
        )
        cls.timeline_therapy = atlas_models.TimelineTherapy.objects.create(
            event=cls.event,
            therapy=cls.therapy,
            role=atlas_models.TimelineLinkRole.MARKS_THERAPY_MILESTONE,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TimelineTherapySource.objects.create(
            relationship=cls.timeline_therapy,
            source=cls.source,
        )
        cls.timeline_technique = atlas_models.TimelineTechnique.objects.create(
            event=cls.event,
            technique=cls.technique,
            role=atlas_models.TimelineLinkRole.MARKS_TECHNIQUE_EVIDENCE_MILESTONE,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TimelineTechniqueSource.objects.create(
            relationship=cls.timeline_technique,
            source=cls.source,
        )
        cls.timeline_concept = atlas_models.TimelineConcept.objects.create(
            event=cls.event,
            concept=cls.concept,
            role=atlas_models.TimelineLinkRole.RELATED,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.TimelineConceptSource.objects.create(
            relationship=cls.timeline_concept,
            source=cls.source,
        )

    def test_psychologist_catalog_search_filters_counts_and_inactive_boundary(self):
        alias_search = self.client.get("/api/psychologists/?q=J.%20Researcher")
        self.assertEqual(alias_search.status_code, 200)
        payload = alias_search.json()
        self.assertEqual(payload["count"], 1)
        row = payload["results"][0]
        self.assertEqual(row["slug"], "jane-researcher")
        self.assertEqual(row["theory_count"], 1)
        self.assertEqual(row["concept_count"], 1)
        self.assertEqual(row["therapy_count"], 1)
        self.assertEqual(row["timeline_event_count"], 1)
        self.assertEqual(row["aliases"][0]["text"], "J. Researcher")

        by_theory = self.client.get("/api/psychologists/?theory=v063-model")
        self.assertEqual(by_theory.status_code, 200)
        self.assertEqual([item["slug"] for item in by_theory.json()["results"]], ["jane-researcher"])
        by_birth = self.client.get("/api/psychologists/?birth_from=1930&birth_to=1950")
        self.assertEqual(by_birth.status_code, 200)
        self.assertEqual([item["slug"] for item in by_birth.json()["results"]], ["jane-researcher"])
        all_slugs = [item["slug"] for item in self.client.get("/api/psychologists/").json()["results"]]
        self.assertNotIn("inactive-researcher", all_slugs)
        self.assertEqual(self.client.get("/api/psychologists/?review_status=invalid").status_code, 400)
        self.assertEqual(self.client.get("/api/psychologists/?birth_from=2000&birth_to=1900").status_code, 400)

    def test_psychologist_detail_exposes_aliases_relations_and_rich_provenance(self):
        response = self.client.get("/api/psychologists/jane-researcher/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["academic_disciplines"], ["cognitive psychology"])
        self.assertEqual(payload["sources"][0]["role"], "biography")
        source = payload["sources"][0]["source"]
        self.assertEqual(source["doi"], "10.1234/v063")
        self.assertEqual(source["pmid"], "12345678")
        self.assertEqual(source["verification_status"], "verified")
        self.assertEqual(source["authors"], ["A. Researcher", "B. Researcher"])
        self.assertEqual(payload["theories"][0]["relationship_type"], "proposed")
        self.assertTrue(payload["theories"][0]["sources"])
        self.assertEqual(payload["therapies"][0]["therapy"]["slug"], "v063-therapy")
        self.assertEqual(payload["concepts"][0]["concept"]["slug"], "v063-learning-process")
        self.assertEqual(payload["related_psychologists"][0]["psychologist"]["slug"], "alex-researcher")
        self.assertEqual(payload["timeline_events"][0]["role"], "involves_person")
        self.assertEqual(self.client.get("/api/psychologists/inactive-researcher/").status_code, 404)

    def test_theory_catalog_filters_alias_search_and_detail_relations(self):
        alias_search = self.client.get("/api/theories/?q=V63M")
        self.assertEqual(alias_search.status_code, 200)
        self.assertEqual(alias_search.json()["count"], 1)
        row = alias_search.json()["results"][0]
        self.assertEqual(row["slug"], "v063-model")
        self.assertEqual(row["psychologist_count"], 1)
        self.assertEqual(row["concept_count"], 1)
        self.assertEqual(row["therapy_count"], 1)
        self.assertEqual(row["technique_count"], 1)
        self.assertEqual(row["timeline_event_count"], 1)
        by_person = self.client.get("/api/theories/?psychologist=jane-researcher")
        self.assertEqual([item["slug"] for item in by_person.json()["results"]], ["v063-model"])
        by_domain = self.client.get("/api/theories/?domain=cognitive_psychology")
        self.assertIn("v063-model", [item["slug"] for item in by_domain.json()["results"]])

        detail = self.client.get("/api/theories/v063-model/")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["sources"][0]["role"], "primary_publication")
        self.assertEqual(payload["psychologists"][0]["psychologist"]["slug"], "jane-researcher")
        self.assertEqual(payload["concepts"][0]["relationship_type"], "includes_construct")
        self.assertEqual(payload["therapies"][0]["relationship_type"], "grounds")
        self.assertEqual(payload["techniques"][0]["technique"]["slug"], "v063-technique")
        self.assertEqual(payload["related_theories"][0]["relationship_type"], "extends")
        self.assertEqual(payload["timeline_events"][0]["role"], "marks_theory_milestone")
        self.assertEqual(self.client.get("/api/theories/inactive-theory-v063/").status_code, 404)

    def test_timeline_catalog_preserves_precision_and_supports_cross_domain_filters(self):
        response = self.client.get("/api/timeline/?year_from=1979&year_to=1981")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        row = payload["results"][0]
        self.assertEqual(row["slug"], "v063-event-1980")
        self.assertEqual(row["date_precision"], "year")
        self.assertEqual(row["date_text"], "1980")
        self.assertEqual(row["year_start"], 1980)
        self.assertIsNone(row["exact_date"])
        self.assertEqual(row["psychologist_count"], 1)
        self.assertEqual(row["theory_count"], 1)
        self.assertEqual(row["therapy_count"], 1)
        self.assertEqual(row["technique_count"], 1)
        self.assertEqual(row["concept_count"], 1)

        by_technique = self.client.get("/api/timeline/?technique=v063-technique")
        self.assertEqual([item["slug"] for item in by_technique.json()["results"]], ["v063-event-1980"])
        by_type = self.client.get("/api/timeline/?event_type=theory_development")
        self.assertEqual([item["slug"] for item in by_type.json()["results"]], ["v063-event-1980"])
        self.assertEqual(self.client.get("/api/timeline/?event_type=invalid").status_code, 400)
        self.assertEqual(self.client.get("/api/timeline/?year_from=2000&year_to=1900").status_code, 400)
        self.assertEqual(self.client.get("/api/timeline/?year_from=not-a-year").status_code, 400)
        all_slugs = [item["slug"] for item in self.client.get("/api/timeline/").json()["results"]]
        self.assertNotIn("inactive-event-v063", all_slugs)

    def test_timeline_detail_preserves_relation_semantics_and_provenance(self):
        response = self.client.get("/api/timeline/v063-event-1980/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["sources"][0]["source"]["doi"], "10.1234/v063")
        self.assertEqual(payload["psychologists"][0]["role"], "involves_person")
        self.assertEqual(payload["theories"][0]["role"], "marks_theory_milestone")
        self.assertEqual(payload["therapies"][0]["role"], "marks_therapy_milestone")
        self.assertEqual(payload["techniques"][0]["role"], "marks_technique_evidence_milestone")
        self.assertEqual(payload["concepts"][0]["role"], "related")
        for key in ("psychologists", "theories", "therapies", "techniques", "concepts"):
            self.assertTrue(payload[key][0]["sources"])
        self.assertEqual(self.client.get("/api/timeline/inactive-event-v063/").status_code, 404)

    def test_v063_api_query_budgets_are_bounded(self):
        checks = (
            ("/api/psychologists/", 5),
            ("/api/theories/", 5),
            ("/api/timeline/", 4),
            ("/api/psychologists/jane-researcher/", 18),
            ("/api/theories/v063-model/", 20),
            ("/api/timeline/v063-event-1980/", 14),
        )
        for url, budget in checks:
            with self.subTest(url=url), CaptureQueriesContext(connection) as captured:
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertLessEqual(len(captured), budget, f"{url} used {len(captured)} queries")
    def test_v065_global_search_integrates_people_theories_and_timeline(self):
        with CaptureQueriesContext(connection) as captured:
            person = self.client.get("/api/search/?q=J.%20Researcher")
        self.assertEqual(person.status_code, 200)
        self.assertLessEqual(len(captured), 13, f"v0.6.6 optimized global search used {len(captured)} queries")
        payload = person.json()
        self.assertEqual([row["slug"] for row in payload["psychologists"]], ["jane-researcher"])
        self.assertIn("psychologists", payload)
        self.assertIn("theories", payload)
        self.assertIn("timeline_events", payload)

        theory = self.client.get("/api/search/?q=V63M")
        self.assertEqual([row["slug"] for row in theory.json()["theories"]], ["v063-model"])

        timeline = self.client.get("/api/search/?q=v0.6.3%20Event")
        self.assertEqual([row["slug"] for row in timeline.json()["timeline_events"]], ["v063-event-1980"])
        self.assertNotIn("inactive-researcher", {row["slug"] for row in payload["psychologists"]})

        short = self.client.get("/api/search/?q=x").json()
        self.assertEqual(short["psychologists"], [])
        self.assertEqual(short["theories"], [])
        self.assertEqual(short["timeline_events"], [])

    def test_v065_graph_contains_v06_nodes_explicit_edges_and_provenance(self):
        cache.clear()
        response = self.client.get("/api/concept-map/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["node_types"]["psychologist"], 2)
        self.assertEqual(payload["meta"]["node_types"]["theory"], 2)
        self.assertEqual(payload["meta"]["node_types"]["timeline"], 2)
        node_ids = {row["id"] for row in payload["nodes"]}
        self.assertIn("psychologist:jane-researcher", node_ids)
        self.assertIn("theory:v063-model", node_ids)
        self.assertIn("timeline:v063-event-1980", node_ids)
        self.assertNotIn("psychologist:inactive-researcher", node_ids)
        self.assertNotIn("theory:inactive-theory-v063", node_ids)
        self.assertNotIn("timeline:inactive-event-v063", node_ids)

        edge_by_kind = {row["kind"]: row for row in payload["edges"]}
        expected = {
            "psychologist_theory_proposed",
            "psychologist_concept_researched",
            "psychologist_therapy_developed",
            "psychologist_psychologist_influenced",
            "theory_concept_includes_construct",
            "theory_therapy_grounds",
            "theory_technique_grounds",
            "theory_theory_extends",
            "timeline_psychologist_involves_person",
            "timeline_theory_marks_theory_milestone",
            "timeline_therapy_marks_therapy_milestone",
            "timeline_technique_marks_technique_evidence_milestone",
            "timeline_concept_related",
        }
        self.assertTrue(expected.issubset(edge_by_kind))
        for kind in expected:
            self.assertTrue(edge_by_kind[kind]["sources"], kind)
            self.assertEqual(edge_by_kind[kind]["review_status"], "source_checked")
            self.assertEqual(edge_by_kind[kind]["sources"][0]["verification_status"], "verified")
            self.assertEqual(edge_by_kind[kind]["sources"][0]["doi"], "10.1234/v063")

    def test_v065_graph_filters_and_pathfinding_cross_new_domains(self):
        cache.clear()
        psychologist_only = self.client.get("/api/concept-map/?node_type=psychologist")
        self.assertEqual(psychologist_only.status_code, 200)
        self.assertEqual(psychologist_only.json()["meta"]["node_count"], 2)
        self.assertTrue(all(row["type"] == "psychologist" for row in psychologist_only.json()["nodes"]))

        theory_filter = self.client.get("/api/concept-map/?node_type=theory&theory_domain=cognitive_psychology")
        self.assertEqual(theory_filter.status_code, 200)
        self.assertEqual(theory_filter.json()["meta"]["node_count"], 2)

        timeline_filter = self.client.get("/api/concept-map/?node_type=timeline&event_type=theory_development")
        self.assertEqual(timeline_filter.status_code, 200)
        self.assertEqual([row["id"] for row in timeline_filter.json()["nodes"]], ["timeline:v063-event-1980"])
        self.assertEqual(self.client.get("/api/concept-map/?node_type=person").status_code, 400)
        self.assertEqual(self.client.get("/api/concept-map/?event_type=bad").status_code, 400)
        self.assertEqual(self.client.get("/api/concept-map/?review_status=bad").status_code, 400)

        path = self.client.get(
            "/api/concept-map/path/?from=psychologist:jane-researcher&to=technique:v063-technique"
        )
        self.assertEqual(path.status_code, 200)
        path_payload = path.json()
        self.assertTrue(path_payload["found"])
        self.assertEqual(path_payload["hops"], 2)
        self.assertEqual(
            [row["id"] for row in path_payload["nodes"]],
            ["psychologist:jane-researcher", "theory:v063-model", "technique:v063-technique"],
        )
        self.assertTrue(all(row.get("sources") for row in path_payload["edges"]))

    def test_v065_graph_cache_invalidates_on_v06_relation_source_changes(self):
        cache.clear()
        first = self.client.get("/api/concept-map/").json()
        edge = next(row for row in first["edges"] if row["kind"] == "psychologist_theory_proposed")
        self.assertEqual(len(edge["sources"]), 1)

        second_source = SourceReference.objects.create(
            title="Second graph provenance source",
            organization="v0.6.5 cache test",
            url="https://example.org/v065-cache-source",
            verification_status="verified",
        )
        atlas_models.PsychologistTheorySource.objects.create(
            relationship=self.person_theory,
            source=second_source,
        )
        refreshed = self.client.get("/api/concept-map/").json()
        edge = next(row for row in refreshed["edges"] if row["kind"] == "psychologist_theory_proposed")
        self.assertEqual(len(edge["sources"]), 2)
        self.assertIn("v0.6.5 cache test", {source["organization"] for source in edge["sources"]})

        self.psychologist.summary_fa = "خلاصه تازه برای invalidation گراف"
        self.psychologist.save(update_fields=("summary_fa", "updated_at"))
        refreshed_node = next(
            row for row in self.client.get("/api/concept-map/").json()["nodes"]
            if row["id"] == "psychologist:jane-researcher"
        )
        self.assertEqual(refreshed_node["summary"], "خلاصه تازه برای invalidation گراف")

    def test_v065_atlas_overview_and_graph_build_query_budget(self):
        cache.clear()
        overview = self.client.get("/api/atlas-overview/")
        self.assertEqual(overview.status_code, 200)
        payload = overview.json()
        self.assertEqual(payload["counts"]["psychologists"], 2)
        self.assertEqual(payload["counts"]["theories"], 2)
        self.assertEqual(payload["counts"]["timeline_events"], 2)
        self.assertGreaterEqual(payload["graph"]["nodes"], 9)
        self.assertGreaterEqual(payload["graph"]["edges"], 13)

        from atlas.views import _build_atlas_graph
        with CaptureQueriesContext(connection) as captured:
            nodes, edges, edge_kinds = _build_atlas_graph()
        self.assertLessEqual(len(captured), 45, f"v0.6.5 graph build used {len(captured)} queries")
        self.assertEqual(sum(1 for row in nodes if row["type"] == "psychologist"), 2)
        self.assertEqual(sum(1 for row in nodes if row["type"] == "theory"), 2)
        self.assertEqual(sum(1 for row in nodes if row["type"] == "timeline"), 2)
        self.assertIn("psychologist_theory_proposed", edge_kinds)
        self.assertTrue(all(
            row.get("sources")
            for row in edges
            if row["kind"].startswith(("psychologist_", "theory_", "timeline_"))
        ))

    def test_v065_concept_neighborhood_can_traverse_theory_and_timeline_edges(self):
        cache.clear()
        theory = self.client.get(
            "/api/concepts/v063-learning-process/neighborhood/?depth=1&node_type=theory"
        )
        self.assertEqual(theory.status_code, 200)
        self.assertIn("theory:v063-model", {row["id"] for row in theory.json()["nodes"]})

        timeline = self.client.get(
            "/api/concepts/v063-learning-process/neighborhood/?depth=1&node_type=timeline"
        )
        self.assertEqual(timeline.status_code, 200)
        self.assertIn("timeline:v063-event-1980", {row["id"] for row in timeline.json()["nodes"]})


class V066ReleaseAuditTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.weak_source = SourceReference.objects.create(
            title="Archival model-knowledge citation",
            verification_status="citation_from_model_knowledge",
        )
        self.psychologist = atlas_models.Psychologist.objects.create(
            slug="v066-person",
            name_en="v0.6.6 Person",
            name_fa="شخص v0.6.6",
        )
        self.theory = atlas_models.Theory.objects.create(
            slug="v066-theory",
            name_en="v0.6.6 Theory",
            name_fa="نظریه v0.6.6",
        )
        atlas_models.PsychologistSource.objects.create(
            psychologist=self.psychologist,
            source=self.weak_source,
        )
        atlas_models.TheorySource.objects.create(
            theory=self.theory,
            source=self.weak_source,
        )
        self.relation = atlas_models.PsychologistTheory.objects.create(
            psychologist=self.psychologist,
            theory=self.theory,
            relationship_type=atlas_models.PsychologistAttributionType.PROPOSED,
            review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        atlas_models.PsychologistTheorySource.objects.create(
            relationship=self.relation,
            source=self.weak_source,
        )

    def test_v066_release_audit_reports_weak_only_debt_without_failing_source_checked(self):
        stdout = StringIO()
        call_command("audit_v06_release", stdout=stdout)
        output = stdout.getvalue()
        self.assertIn("v0.6 release audit PASS", output)
        self.assertIn("weak_relations=1", output)
        self.assertIn("weak_reviewed=0", output)

    def test_v066_release_audit_rejects_weak_only_relation_marked_reviewed(self):
        self.relation.review_status = ScientificReviewStatus.REVIEWED
        self.relation.save(update_fields=("review_status", "updated_at"))
        with self.assertRaises(CommandError):
            call_command("audit_v06_release", stdout=StringIO(), stderr=StringIO())
