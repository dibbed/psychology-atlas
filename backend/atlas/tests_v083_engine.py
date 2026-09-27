"""Recommendation V2 rule and read-only endpoint regressions."""

import hashlib
import json
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from .recommendations_v2 import build_candidates
from .models import (
    CaseAttempt,
    CaseRevision,
    CaseStep,
    Category,
    ClinicalCase,
    CognitiveDistortionPracticeItem,
    Concept,
    Disorder,
    Flashcard,
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizChoice,
    QuizQuestion,
    RecommendationFeedback,
    ScientificReviewStatus,
    SourceReference,
    StudyBlock,
    StudyPlan,
    StudyPlanAvailability,
    StudyPlanScope,
    Theory,
    TheoryConcept,
    TheoryConceptSource,
    UserConceptProgress,
    UserFlashcardProgress,
    UserProgress,
    UserStudySettings,
)


def expected_key(kind, target_type, target_id, reason_code, context_ref):
    identity = ["rec-v2", kind, target_type, target_id, reason_code, context_ref]
    raw = json.dumps(identity, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return "r2_" + hashlib.sha256(raw).hexdigest()


class RecommendationV2EngineTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="v083-owner", password="test-pass")
        self.other = get_user_model().objects.create_user(username="v083-other", password="test-pass")
        self.client.force_authenticate(self.user)
        self.category = Category.objects.create(slug="v083-category", name_en="V083 Category")

    def listing(self, limit=20):
        response = self.client.get(f"/api/study/recommendations/?limit={limit}")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["version"], "v2")
        return response.json()

    def items(self):
        return self.listing()["items"]

    def concept(self, slug, **kwargs):
        return Concept.objects.create(slug=slug, name_en=slug, simple_definition="Factual definition", **kwargs)

    def disorder(self, slug, **kwargs):
        return Disorder.objects.create(category=self.category, slug=slug, name_en=slug, **kwargs)

    def active_plan(self, name="Plan", **kwargs):
        return StudyPlan.objects.create(
            user=self.user,
            name=name,
            status=StudyPlan.Status.ACTIVE,
            start_date=date(2026, 1, 1),
            **kwargs,
        )

    def block(self, plan, scheduled_date, kind, **kwargs):
        return StudyBlock.objects.create(
            plan=plan,
            block_kind=kind,
            status=StudyBlock.Status.PENDING,
            scheduled_date=scheduled_date,
            estimated_minutes=25,
            snapshot_title="Scheduled work",
            **kwargs,
        )

    def quiz_attempt(self, quiz, *, completed_at, wrong=True, user=None):
        attempt = QuizAttempt.objects.create(
            user=user or self.user,
            quiz=quiz,
            status=QuizAttempt.Status.COMPLETED,
            completed_at=completed_at,
            total_questions=1,
            correct_count=0 if wrong else 1,
            score=0 if wrong else 100,
        )
        question = QuizQuestion.objects.create(quiz=quiz, prompt=f"Question {attempt.id}")
        choice = QuizChoice.objects.create(question=question, text="Selected", is_correct=not wrong)
        QuizAttemptAnswer.objects.create(
            attempt=attempt, question=question, selected_choice=choice, is_correct=not wrong
        )
        return attempt

    def case_attempt(self, case, *, user=None):
        revision = CaseRevision.objects.create(
            case=case,
            version=1,
            title=case.title,
            patient_summary=case.patient_summary,
            status=CaseRevision.Status.PUBLISHED,
        )
        step = CaseStep.objects.create(
            case=case,
            revision=revision,
            stable_key="entry",
            title="Entry",
            narrative="Educational content",
            sort_order=0,
        )
        revision.entry_step = step
        revision.save(update_fields=["entry_step", "updated_at"])
        case.current_revision = revision
        case.save(update_fields=["current_revision", "updated_at"])
        return CaseAttempt.objects.create(
            user=user or self.user,
            case=case,
            revision=revision,
            current_step=step,
            status=CaseAttempt.Status.IN_PROGRESS,
        )

    def test_worked_fingerprint_example_and_identical_reads(self):
        self.assertEqual(
            expected_key("quiz_retry", "quiz", 42, "recent_incorrect_quiz_answers", "attempt:91"),
            "r2_abd11712d8ebc0fe25cdc9be158dc3e9a3688254150b80a01443633344eafcd2",
        )
        concept = self.concept("stable-concept")
        UserConceptProgress.objects.create(user=self.user, concept=concept, progress_percent=25)
        plan = self.active_plan(generation_version=2, generation_fingerprint="")
        expected = {
            expected_key("concept_review", "concept", concept.id, "concept_progress_low", "current_progress"),
            expected_key("plan_schedule_stale", "study_plan", plan.id, "schedule_stale", "generation:2"),
        }
        first = self.listing()
        for _ in range(3):
            current = self.listing()
            self.assertEqual([item["key"] for item in current["items"]], [item["key"] for item in first["items"]])
            self.assertEqual([item["order"] for item in current["items"]], list(range(1, len(current["items"]) + 1)))
        self.assertEqual({item["key"] for item in first["items"]}, expected)
        self.assertEqual([item["priority"] for item in first["items"]], [110, 50])

    def test_due_queue_wins_new_queue_and_inactive_cards_are_excluded(self):
        now = timezone.now()
        active = Flashcard.objects.create(slug="due-card", front="Front", back="Back")
        Flashcard.objects.create(slug="new-card", front="Front", back="Back")
        hidden = Flashcard.objects.create(slug="hidden-card", front="Front", back="Back", is_active=False)
        inactive_concept = self.concept("inactive-card-concept", is_active=False)
        Flashcard.objects.create(slug="inactive-target-card", front="Front", back="Back", concept=inactive_concept)
        UserFlashcardProgress.objects.create(user=self.user, flashcard=active, due_at=now - timedelta(hours=1))
        UserFlashcardProgress.objects.create(user=self.user, flashcard=hidden, due_at=now - timedelta(hours=1))
        queues = [item for item in self.items() if item["target"]["type"] == "review_queue"]
        self.assertEqual(len(queues), 1)
        self.assertEqual(queues[0]["type"], "srs_review")
        self.assertEqual(queues[0]["priority"], 100)
        self.assertEqual(queues[0]["action"]["href"], "/flashcards")
        self.assertEqual(queues[0]["target"]["id"], None)

    def test_study_timezone_defines_daily_queue_identity(self):
        instant = datetime(2026, 1, 1, 23, 30, tzinfo=datetime_timezone.utc)
        card = Flashcard.objects.create(slug="timezone-due", front="Front", back="Back")
        UserFlashcardProgress.objects.create(user=self.user, flashcard=card, due_at=instant - timedelta(hours=1))
        settings = UserStudySettings.objects.create(user=self.user, study_timezone="Asia/Tehran")
        with patch("atlas.recommendation_views.timezone.now", return_value=instant):
            tehran = next(item for item in self.items() if item["type"] == "srs_review")
        self.assertEqual(
            tehran["key"], expected_key("srs_review", "review_queue", None, "srs_due", "due_day:2026-01-02")
        )
        settings.study_timezone = "America/New_York"
        settings.save(update_fields=["study_timezone"])
        with patch("atlas.recommendation_views.timezone.now", return_value=instant):
            new_york = next(item for item in self.items() if item["type"] == "srs_review")
        self.assertEqual(
            new_york["key"], expected_key("srs_review", "review_queue", None, "srs_due", "due_day:2026-01-01")
        )

    def test_low_progress_is_stored_heuristic_only_and_inactive_targets_excluded(self):
        concept = self.concept("low-concept")
        disorder = self.disorder("low-disorder")
        inactive = self.concept("inactive-low-concept", is_active=False)
        UserConceptProgress.objects.create(user=self.user, concept=concept, progress_percent=69)
        UserConceptProgress.objects.create(user=self.user, concept=inactive, progress_percent=1)
        UserProgress.objects.create(user=self.user, disorder=disorder, progress_percent=69)
        rows = self.items()
        self.assertEqual([item["type"] for item in rows], ["concept_review", "disorder_review"])
        self.assertEqual([item["target"]["slug"] for item in rows], ["low-concept", "low-disorder"])
        self.assertTrue(all(item["priority"] == 50 for item in rows))
        self.assertFalse(any("mastery" in json.dumps(item).lower() for item in rows))

    def test_quiz_latest_completed_attempt_supersedes_older_incorrect(self):
        now = timezone.now()
        quiz = Quiz.objects.create(slug="retry-quiz", title="Retry quiz")
        first = self.quiz_attempt(quiz, completed_at=now - timedelta(days=2), wrong=True)
        rows = [item for item in self.items() if item["type"] == "quiz_retry"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], expected_key("quiz_retry", "quiz", quiz.id, "recent_incorrect_quiz_answers", f"attempt:{first.id}"))
        self.quiz_attempt(quiz, completed_at=now - timedelta(days=1), wrong=False)
        self.assertFalse(any(item["type"] == "quiz_retry" for item in self.items()))

    def test_quiz_old_and_inactive_attempts_are_excluded(self):
        now = timezone.now()
        old = Quiz.objects.create(slug="old-quiz", title="Old quiz")
        inactive = Quiz.objects.create(slug="inactive-quiz", title="Inactive quiz", is_active=False)
        self.quiz_attempt(old, completed_at=now - timedelta(days=31))
        self.quiz_attempt(inactive, completed_at=now - timedelta(days=1))
        self.assertFalse(any(item["type"] == "quiz_retry" for item in self.items()))

    def test_other_users_private_facts_never_generate_owner_advice(self):
        concept = self.concept("foreign-progress")
        quiz = Quiz.objects.create(slug="foreign-quiz", title="Foreign quiz")
        UserConceptProgress.objects.create(user=self.other, concept=concept, progress_percent=10)
        self.quiz_attempt(quiz, completed_at=timezone.now() - timedelta(days=1), user=self.other)
        StudyPlan.objects.create(
            user=self.other, name="Private plan", status=StudyPlan.Status.ACTIVE,
            start_date=date(2026, 1, 1),
        )
        self.assertFalse(any(
            item["type"] in {"concept_review", "quiz_retry", "plan_generate"}
            for item in self.items()
        ))

    def test_case_resume_uses_in_progress_canonical_attempt_without_new_evidence(self):
        case = ClinicalCase.objects.create(slug="resume-case", title="Resume case", patient_summary="Educational case")
        attempt = self.case_attempt(case)
        before = (attempt.revision_id, attempt.current_step_id, attempt.state_version, attempt.score)
        row = next(item for item in self.items() if item["type"] == "case_resume")
        self.assertEqual(row["target"], {"type": "clinical_case", "id": case.id, "slug": case.slug})
        self.assertEqual(row["key"], expected_key("case_resume", "clinical_case", case.id, "case_in_progress", f"attempt:{attempt.id}"))
        attempt.refresh_from_db()
        self.assertEqual((attempt.revision_id, attempt.current_step_id, attempt.state_version, attempt.score), before)
        case.is_active = False
        case.save(update_fields=["is_active"])
        self.assertFalse(any(item["type"] == "case_resume" for item in self.items()))

    def test_old_in_progress_case_does_not_become_permanent_advice(self):
        case = ClinicalCase.objects.create(slug="old-resume-case", title="Old case", patient_summary="Educational case")
        attempt = self.case_attempt(case)
        CaseAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - timedelta(days=31))
        self.assertFalse(any(item["type"] == "case_resume" for item in self.items()))

    def test_stale_and_missing_plan_schedule_precede_capacity(self):
        stale = self.active_plan(name="Stale", generation_version=3, generation_fingerprint="")
        missing = self.active_plan(name="Missing", generation_version=0)
        for plan in (stale, missing):
            plan.last_generation_summary = {"generation_version": 3, "unscheduled_candidates": 9, "capacity_shortfall_minutes": 200}
            plan.save(update_fields=["last_generation_summary"])
        rows = [item for item in self.items() if item["target"]["type"] == "study_plan"]
        self.assertEqual([item["type"] for item in rows], ["plan_schedule_stale", "plan_generate"])
        self.assertEqual(rows[0]["key"], expected_key("plan_schedule_stale", "study_plan", stale.id, "schedule_stale", "generation:3"))
        self.assertEqual(rows[1]["key"], expected_key("plan_generate", "study_plan", missing.id, "schedule_missing", "generation:0"))

    def test_capacity_facts_fold_into_single_plan_item(self):
        plan = self.active_plan(
            name="Capacity", generation_version=2, generation_fingerprint="fresh",
            last_generated_at=timezone.now(),
            last_generation_summary={
                "generation_version": 2, "unscheduled_candidates": 4,
                "capacity_shortfall_minutes": 90, "available_minutes": 0,
            },
        )
        StudyPlanAvailability.objects.create(plan=plan, weekday=0, available_minutes=0)
        concept = self.concept("capacity-concept")
        StudyPlanScope.objects.create(plan=plan, concept=concept, priority=5)
        rows = [item for item in self.items() if item["target"]["type"] == "study_plan"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "plan_capacity")
        self.assertEqual(rows[0]["key"], expected_key("plan_capacity", "study_plan", plan.id, "plan_capacity_gap", "generation:2"))
        self.assertLessEqual(len(rows[0]["reason_codes"]), 4)
        self.assertLessEqual(len(rows[0]["signals"]), 4)

    def test_same_day_block_suppresses_generic_action_but_future_block_does_not(self):
        today = timezone.localdate()
        concept = self.concept("scheduled-concept")
        UserConceptProgress.objects.create(user=self.user, concept=concept, progress_percent=20)
        plan = self.active_plan(name="Block owner")
        block = self.block(plan, today, StudyBlock.Kind.CONCEPT_REVIEW, concept=concept)
        types = [item["type"] for item in self.items()]
        self.assertNotIn("concept_review", types)
        self.assertNotIn("overdue_block", types)
        block.scheduled_date = today - timedelta(days=1)
        block.save(update_fields=["scheduled_date"])
        types = [item["type"] for item in self.items()]
        self.assertIn("overdue_block", types)
        self.assertNotIn("concept_review", types)
        block.scheduled_date = today + timedelta(days=1)
        block.save(update_fields=["scheduled_date"])
        types = [item["type"] for item in self.items()]
        self.assertIn("concept_review", types)
        self.assertNotIn("overdue_block", types)

    def test_today_blocks_suppress_matching_quiz_case_disorder_practice_and_queue(self):
        today = timezone.localdate()
        plan = self.active_plan(name="Specific scheduled actions")
        quiz = Quiz.objects.create(slug="scheduled-quiz", title="Scheduled quiz")
        self.quiz_attempt(quiz, completed_at=timezone.now() - timedelta(days=1))
        case = ClinicalCase.objects.create(slug="scheduled-case", title="Scheduled case", patient_summary="Educational case")
        self.case_attempt(case)
        disorder = self.disorder("scheduled-disorder")
        UserProgress.objects.create(user=self.user, disorder=disorder, progress_percent=20)
        distortion = self.concept("scheduled-distortion", subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        StudyPlanScope.objects.create(plan=plan, concept=distortion, include_practice=True)
        CognitiveDistortionPracticeItem.objects.create(
            slug="scheduled-practice-item", prompt="Identify example", explanation="Explanation", target_concept=distortion,
        )
        card = Flashcard.objects.create(slug="scheduled-card", front="Front", back="Back")
        UserFlashcardProgress.objects.create(user=self.user, flashcard=card, due_at=timezone.now() - timedelta(hours=1))
        blocks = [
            self.block(plan, today, StudyBlock.Kind.QUIZ_PRACTICE, quiz=quiz),
            self.block(plan, today, StudyBlock.Kind.CASE_PRACTICE, clinical_case=case),
            self.block(plan, today, StudyBlock.Kind.DISORDER_REVIEW, disorder=disorder),
            self.block(plan, today, StudyBlock.Kind.DISTORTION_PRACTICE, concept=distortion),
            self.block(plan, today, StudyBlock.Kind.FLASHCARD_REVIEW),
        ]
        suppressed = {"quiz_retry", "case_resume", "disorder_review", "distortion_practice", "srs_review"}
        self.assertTrue(suppressed.isdisjoint(item["type"] for item in self.items()))
        for block in blocks:
            block.scheduled_date = today + timedelta(days=1)
            block.save(update_fields=["scheduled_date"])
        self.assertTrue(suppressed.issubset(item["type"] for item in self.items()))

    def test_explicit_distortion_scope_requires_active_practice_item(self):
        concept = self.concept("scoped-distortion", subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        plan = self.active_plan(name="Distortion scope")
        scope = StudyPlanScope.objects.create(plan=plan, concept=concept, include_practice=True)
        item = CognitiveDistortionPracticeItem.objects.create(
            slug="distortion-practice", prompt="Identify the example", explanation="Example explanation",
            target_concept=concept,
        )
        row = next(item for item in self.items() if item["type"] == "distortion_practice")
        self.assertEqual(row["key"], expected_key("distortion_practice", "concept", concept.id, "explicit_distortion_scope", f"plan:{plan.id}:scope:{scope.id}"))
        self.assertNotIn("your thoughts", json.dumps(row).lower())
        item.is_active = False
        item.save(update_fields=["is_active"])
        self.assertFalse(any(item["type"] == "distortion_practice" for item in self.items()))

    def test_reviewed_direct_graph_gate_and_concept_reading_dedup(self):
        concept = self.concept("graph-concept")
        theory = Theory.objects.create(slug="reviewed-theory", name_en="Reviewed theory", review_status=ScientificReviewStatus.REVIEWED)
        plan = self.active_plan(name="Graph scope")
        scope = StudyPlanScope.objects.create(plan=plan, theory=theory)
        weak = TheoryConcept.objects.create(
            theory=theory, concept=concept, relationship_type="grounds", review_status=ScientificReviewStatus.SOURCE_CHECKED,
        )
        source = SourceReference.objects.create(title="Checked source", verification_status="source_checked", url="https://example.org/source")
        TheoryConceptSource.objects.create(relationship=weak, source=source)
        self.assertFalse(any(item["type"] == "graph_explore" for item in self.items()))
        relation = TheoryConcept.objects.create(
            theory=theory, concept=concept, relationship_type="informs", review_status=ScientificReviewStatus.REVIEWED,
        )
        self.assertFalse(any(item["type"] == "graph_explore" for item in self.items()))
        model_only = SourceReference.objects.create(
            title="Unverified model citation", verification_status="citation_from_model_knowledge"
        )
        TheoryConceptSource.objects.create(relationship=relation, source=model_only)
        self.assertFalse(any(item["type"] == "graph_explore" for item in self.items()))
        TheoryConceptSource.objects.create(relationship=relation, source=source)
        graph = next(item for item in self.items() if item["type"] == "graph_explore")
        self.assertEqual(graph["key"], expected_key("graph_explore", "concept", concept.id, "reviewed_explicit_relation", f"theoryconcept:{relation.id}:informs:scope:{scope.id}"))
        self.assertEqual(graph["target"]["slug"], concept.slug)
        self.assertIn("informs", json.dumps(graph, ensure_ascii=False))
        UserConceptProgress.objects.create(user=self.user, concept=concept, progress_percent=15)
        types = [item["type"] for item in self.items()]
        self.assertIn("concept_review", types)
        self.assertNotIn("graph_explore", types)

    def test_get_creates_no_feedback_or_learning_state(self):
        concept = self.concept("read-only-concept")
        progress = UserConceptProgress.objects.create(user=self.user, concept=concept, progress_percent=25)
        plan = self.active_plan(name="Read only")
        before = (progress.updated_at, plan.updated_at, progress.progress_percent, plan.generation_version)
        for _ in range(3):
            self.listing()
        progress.refresh_from_db()
        plan.refresh_from_db()
        self.assertEqual((progress.updated_at, plan.updated_at, progress.progress_percent, plan.generation_version), before)
        self.assertEqual(RecommendationFeedback.objects.count(), 0)
        self.assertEqual(StudyBlock.objects.count(), 0)

    def test_empty_draft_paused_and_archived_plans_produce_no_advice(self):
        empty = self.listing()
        self.assertEqual(empty["items"], [])
        self.assertEqual((empty["returned_count"], empty["suppressed_count"],
                          empty["truncated_sources"]), (0, 0, False))
        for status in (StudyPlan.Status.DRAFT, StudyPlan.Status.PAUSED, StudyPlan.Status.ARCHIVED):
            StudyPlan.objects.create(
                user=self.user, name=f"{status} plan", status=status,
                start_date=timezone.localdate(),
            )
        self.assertEqual(self.items(), [])
        self.assertEqual(RecommendationFeedback.objects.count(), 0)

    def test_active_plan_without_blocks_and_inactive_or_archived_targets(self):
        plan = self.active_plan(name="No generated blocks")
        self.assertEqual([item["type"] for item in self.items()], ["plan_generate"])
        concept = self.concept("archived-target")
        block = self.block(plan, timezone.localdate() - timedelta(days=1),
                           StudyBlock.Kind.CONCEPT_REVIEW, concept=concept)
        self.assertIn(block.id, [item["target"]["id"] for item in self.items()
                                 if item["type"] == "overdue_block"])
        concept.is_active = False
        concept.save(update_fields=["is_active"])
        self.assertNotIn(block.id, [item["target"]["id"] for item in self.items()
                                    if item["type"] == "overdue_block"])
        plan.status = StudyPlan.Status.ARCHIVED
        plan.save(update_fields=["status"])
        self.assertEqual(self.items(), [])

    def test_exam_target_today_and_passed_are_bounded_facts(self):
        today = timezone.localdate()
        for offset in (0, -1):
            plan = self.active_plan(
                name=f"Exam {offset}", plan_kind=StudyPlan.Kind.EXAM,
                target_date=today + timedelta(days=offset),
                generation_version=1, generation_fingerprint="fresh",
                last_generated_at=timezone.now(),
                last_generation_summary={
                    "generation_version": 1, "unscheduled_candidates": 1,
                    "capacity_shortfall_minutes": 25, "available_minutes": 0,
                },
            )
            item = next(item for item in self.items()
                        if item["type"] == "plan_capacity" and item["target"]["id"] == plan.id)
            self.assertEqual(next(signal["days_remaining"] for signal in item["signals"]
                                  if signal["kind"] == "exam_target_date"), 0)

    def test_no_due_cards_attempts_or_active_content_has_no_queue_or_retry(self):
        card = Flashcard.objects.create(slug="future-card", front="Front", back="Back")
        UserFlashcardProgress.objects.create(
            user=self.user, flashcard=card, due_at=timezone.now() + timedelta(days=1),
        )
        inactive = Flashcard.objects.create(
            slug="inactive-card-only", front="Front", back="Back", is_active=False,
        )
        UserFlashcardProgress.objects.create(
            user=self.user, flashcard=inactive, due_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse({"srs_review", "srs_start", "quiz_retry", "case_resume"}
                         & {item["type"] for item in self.items()})

    def test_populated_fixture_query_budget_and_source_caps(self):
        for index in range(11):
            concept = self.concept(f"budget-concept-{index:02d}")
            UserConceptProgress.objects.create(user=self.user, concept=concept, progress_percent=20)
        for index in range(11):
            disorder = self.disorder(f"budget-disorder-{index:02d}")
            UserProgress.objects.create(user=self.user, disorder=disorder, progress_percent=20)
        plans = [self.active_plan(name=f"Budget plan {index:02d}") for index in range(21)]
        for index in range(51):
            target = self.concept(f"budget-block-target-{index:02d}")
            self.block(
                plans[0], timezone.localdate() - timedelta(days=1),
                StudyBlock.Kind.CONCEPT_REVIEW, concept=target,
            )
        UserConceptProgress.objects.create(user=self.user, concept=target, progress_percent=0)
        for index in range(20):
            quiz = Quiz.objects.create(slug=f"budget-quiz-{index:02d}", title="Budget quiz")
            self.quiz_attempt(quiz, completed_at=timezone.now() - timedelta(days=1))
        for index in range(20):
            case = ClinicalCase.objects.create(
                slug=f"budget-case-{index:02d}", title="Budget case", patient_summary="Educational case",
            )
            self.case_attempt(case)
        for index in range(80):
            card = Flashcard.objects.create(
                slug=f"budget-card-{index:02d}", front="Front", back="Back",
            )
            UserFlashcardProgress.objects.create(
                user=self.user, flashcard=card, due_at=timezone.now() - timedelta(hours=1),
            )
        with CaptureQueriesContext(connection) as queries:
            payload = self.listing()
        self.assertTrue(payload["truncated_sources"])
        self.assertEqual(payload["returned_count"], 20)
        all_candidates, _ = build_candidates(self.user, timezone.now())
        self.assertFalse(any(
            item["type"] == "concept_review" and item["target"]["id"] == target.id
            for item in all_candidates
        ))
        # Many blocks, attempts of both types, and cards must not add one query
        # per candidate. Allow limited backend variation without N+1.
        self.assertLessEqual(len(queries), 25, f"Recommendation query count: {len(queries)}")
