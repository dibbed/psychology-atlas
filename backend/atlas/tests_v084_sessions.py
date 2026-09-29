"""v0.8.4 StudySession API, transaction, and canonical-boundary regressions."""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from . import models


BASE = "/api/study/sessions/"


def fixture(owner, suffix):
    concept = models.Concept.objects.create(
        slug=f"session-concept-{suffix}", name_en="Session concept", is_active=True
    )
    plan = models.StudyPlan.objects.create(
        user=owner, name="Session plan", status=models.StudyPlan.Status.ACTIVE
    )
    block = models.StudyBlock.objects.create(
        plan=plan, block_kind=models.StudyBlock.Kind.CONCEPT_REVIEW,
        scheduled_date=timezone.localdate(), estimated_minutes=20,
        snapshot_title="Concept", concept=concept,
    )
    return concept, plan, block


class StudySessionApiTests(APITestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("session-owner", password="unused")
        self.other = get_user_model().objects.create_user("session-other", password="unused")
        self.concept, self.plan, self.block = fixture(self.owner, "owner")
        _, self.foreign_plan, self.foreign_block = fixture(self.other, "other")
        models.UserStudySettings.objects.create(
            user=self.owner, default_daily_minutes=60, default_session_minutes=25
        )
        self.client.force_authenticate(self.owner)

    def start(self, block=None, event=None, minutes=None):
        payload = {
            "primary_block_id": (block or self.block).pk,
            "client_event_id": str(event or uuid.uuid4()),
        }
        if minutes is not None:
            payload["planned_minutes"] = minutes
        return self.client.post(BASE, payload, format="json")

    def test_start_current_retrieve_and_exact_payload(self):
        self.assertIsNone(self.client.get(BASE + "current/").data["session"])
        response = self.start()
        self.assertEqual((response.status_code, response.data["created"]), (201, True))
        row = response.data["session"]
        self.assertEqual(set(row), {
            "id", "status", "plan_id", "primary_block_id", "block_id_at_start",
            "planned_minutes", "started_at", "completed_at", "abandoned_at",
            "actual_seconds", "elapsed_seconds", "elapsed_capped", "as_of",
            "created_at", "updated_at", "primary_block",
        })
        self.assertNotIn("client_event_id", row)
        self.assertEqual(row["planned_minutes"], 25)
        self.assertEqual(row["primary_block"], {
            "id": self.block.id, "plan_id": self.plan.id,
            "block_kind": "concept_review", "status": "pending",
            "scheduled_date": self.block.scheduled_date.isoformat(),
            "estimated_minutes": 20, "snapshot_title": "Concept",
            "action_href": f"/concepts/{self.concept.slug}",
            "target_active": True, "evidence_required": False,
        })
        self.assertEqual(self.client.get(BASE + "current/").data["session"]["id"], row["id"])
        self.assertEqual(self.client.get(BASE + f"{row['id']}/").data["session"]["id"], row["id"])
        self.block.refresh_from_db()
        self.assertEqual(self.block.status, "pending")
        self.assertIsNone(self.block.started_at)

    def test_event_replay_equivalent_active_and_stale_browser_retry(self):
        event = uuid.uuid4()
        first = self.start(event=event)
        session_id = first.data["session"]["id"]
        for response in (self.start(event=event), self.start(event=uuid.uuid4(), minutes=25)):
            self.assertEqual((response.status_code, response.data["created"]), (200, False))
            self.assertEqual(response.data["session"]["id"], session_id)
        self.client.post(BASE + f"{session_id}/complete/", {}, format="json")
        replay = self.start(event=event)
        self.assertEqual((replay.status_code, replay.data["session"]["status"]), (200, "completed"))
        later = self.start()
        self.assertEqual(later.status_code, 201)
        self.assertNotEqual(later.data["session"]["id"], session_id)
        stale = self.start(event=event)
        self.assertEqual((stale.status_code, stale.data["session"]["id"]), (200, session_id))

    def test_active_and_event_conflicts(self):
        event = uuid.uuid4()
        self.start(event=event)
        second = models.StudyBlock.objects.create(
            plan=self.plan, block_kind="concept_review", scheduled_date=timezone.localdate(),
            estimated_minutes=10, snapshot_title="Second", concept=self.concept,
        )
        for response, code in (
            (self.start(block=second), "study_session_active"),
            (self.start(minutes=30), "study_session_active"),
            (self.start(block=second, event=event), "study_session_event_conflict"),
            (self.start(event=event, minutes=30), "study_session_event_conflict"),
        ):
            self.assertEqual((response.status_code, response.data["code"]), (409, code))
        self.assertEqual(models.StudySession.objects.count(), 1)

    def test_complete_abandon_and_cross_terminal_transitions(self):
        session_id = self.start().data["session"]["id"]
        complete = self.client.post(BASE + f"{session_id}/complete/", {}, format="json")
        self.assertEqual((complete.status_code, complete.data["session"]["status"]), (200, "completed"))
        repeat = self.client.post(BASE + f"{session_id}/complete/", {}, format="json")
        self.assertEqual(repeat.data["session"]["completed_at"], complete.data["session"]["completed_at"])
        self.assertEqual(repeat.data["session"]["actual_seconds"], complete.data["session"]["actual_seconds"])
        crossed = self.client.post(BASE + f"{session_id}/abandon/", {}, format="json")
        self.assertEqual((crossed.status_code, crossed.data["code"]), (409, "study_session_transition_conflict"))
        next_id = self.start().data["session"]["id"]
        abandoned = self.client.post(BASE + f"{next_id}/abandon/", {}, format="json")
        self.assertEqual(abandoned.data["session"]["status"], "abandoned")
        self.assertEqual(self.client.post(BASE + f"{next_id}/abandon/", {}, format="json").status_code, 200)
        self.assertEqual(self.client.post(BASE + f"{next_id}/complete/", {}, format="json").data["code"], "study_session_transition_conflict")
        self.assertIsNone(self.client.get(BASE + "current/").data["session"])

    def test_server_duration_floor_cap_and_timestamps(self):
        session_id = self.start().data["session"]["id"]
        row = models.StudySession.objects.get(pk=session_id)
        models.StudySession.objects.filter(pk=session_id).update(started_at=timezone.now() - timedelta(days=3))
        completed = self.client.post(BASE + f"{session_id}/complete/", {}, format="json").data["session"]
        self.assertEqual((completed["actual_seconds"], completed["elapsed_seconds"], completed["elapsed_capped"]), (86400, 86400, True))
        next_id = self.start().data["session"]["id"]
        models.StudySession.objects.filter(pk=next_id).update(started_at=timezone.now() + timedelta(seconds=5))
        zero = self.client.post(BASE + f"{next_id}/abandon/", {}, format="json").data["session"]
        self.assertEqual((zero["actual_seconds"], zero["elapsed_seconds"]), (0, 0))
        self.assertGreaterEqual(zero["abandoned_at"], zero["started_at"])

    def test_owner_isolation_and_foreign_block(self):
        foreign = self.start(block=self.foreign_block)
        self.assertEqual((foreign.status_code, foreign.data["code"]), (404, "study_block_not_found"))
        session_id = self.start().data["session"]["id"]
        self.client.force_authenticate(self.other)
        self.assertIsNone(self.client.get(BASE + "current/").data["session"])
        for suffix, method in (("/", "get"), ("/complete/", "post"), ("/abandon/", "post")):
            response = getattr(self.client, method)(BASE + f"{session_id}" + suffix, **({"data": {}, "format": "json"} if method == "post" else {}))
            self.assertEqual((response.status_code, response.data["code"]), (404, "study_session_not_found"))

    def test_block_plan_mismatch_and_direct_model_clean(self):
        mismatch = models.StudySession(
            user=self.owner, plan=self.foreign_plan, primary_block=self.block,
            block_id_at_start=self.block.id, client_event_id=uuid.uuid4(),
            planned_minutes=25, started_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            mismatch.save()
        missing_block_with_explicit_pk = models.StudySession(
            pk=12345, user=self.owner, plan=self.plan, primary_block=None,
            block_id_at_start=self.block.id, client_event_id=uuid.uuid4(),
            planned_minutes=25, started_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            missing_block_with_explicit_pk.save()
        self.assertEqual(models.StudySession.objects.count(), 0)

    def test_unavailable_plan_block_and_target(self):
        for status in ("draft", "paused", "archived", "completed"):
            self.plan.status = status
            self.plan.save(update_fields=("status",))
            response = self.start()
            self.assertEqual((response.status_code, response.data["code"]), (409, "study_session_block_unavailable"))
        self.plan.status = "active"
        self.plan.save(update_fields=("status",))
        for status in ("completed", "skipped", "superseded"):
            self.block.status = status
            self.block.completed_at = None
            self.block.skipped_at = None
            if status == "completed":
                self.block.completed_at = timezone.now()
            if status == "skipped":
                self.block.skipped_at = timezone.now()
            self.block.save()
            response = self.start()
            self.assertEqual((response.status_code, response.data["code"]), (409, "study_session_block_unavailable"))
        self.block.status = "pending"
        self.block.completed_at = self.block.skipped_at = None
        self.block.save()
        self.concept.is_active = False
        self.concept.save(update_fields=("is_active",))
        response = self.start()
        self.assertEqual((response.status_code, response.data["code"]), (409, "study_session_block_unavailable"))

    def test_end_after_archive_or_block_delete_preserves_history(self):
        session_id = self.start().data["session"]["id"]
        original_block_id = self.block.id
        self.plan.status = "archived"
        self.plan.save(update_fields=("status",))
        self.block.delete()
        detail = self.client.get(BASE + f"{session_id}/").data["session"]
        self.assertIsNone(detail["primary_block"])
        self.assertIsNone(detail["primary_block_id"])
        self.assertEqual(detail["block_id_at_start"], original_block_id)
        self.assertEqual(self.client.post(BASE + f"{session_id}/complete/", {}, format="json").status_code, 200)

    def test_validation_query_and_body_bounds(self):
        base = {"primary_block_id": self.block.id, "client_event_id": str(uuid.uuid4())}
        cases = [
            {}, {"primary_block_id": True, "client_event_id": base["client_event_id"]},
            {**base, "planned_minutes": False}, {**base, "planned_minutes": 4},
            {**base, "planned_minutes": 61}, {**base, "client_event_id": "not-uuid"},
            {**base, "unknown": 1}, [base], "hello", 17,
        ]
        for body in cases:
            response = self.client.post(BASE, body, format="json")
            self.assertEqual((response.status_code, response.data["code"]), (400, "study_session_invalid"), body)
        malformed = self.client.post(BASE, "{", content_type="application/json")
        oversized = self.client.post(BASE, json.dumps({**base, "padding": "x" * 1024}), content_type="application/json")
        for response in (malformed, oversized):
            self.assertEqual((response.status_code, response.data["code"]), (400, "study_session_invalid"))
        for url in (BASE + "?x=1", BASE + "current/?x=1"):
            response = self.client.post(url, base, format="json") if url.startswith(BASE + "?") else self.client.get(url)
            self.assertEqual((response.status_code, response.data["code"]), (400, "study_session_invalid_query"))
        self.assertEqual(models.StudySession.objects.count(), 0)

    def test_terminal_body_query_and_authentication(self):
        session_id = self.start().data["session"]["id"]
        url = BASE + f"{session_id}/complete/"
        for body in ([1], "x", {"actual_seconds": 20}):
            response = self.client.post(url, body, format="json")
            self.assertEqual((response.status_code, response.data["code"]), (400, "study_session_invalid"))
        response = self.client.post(url + "?x=1", {}, format="json")
        self.assertEqual((response.status_code, response.data["code"]), (400, "study_session_invalid_query"))
        self.assertEqual(self.client.post(url, data="", content_type="application/json").status_code, 200)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(BASE + "current/").status_code, 401)
        self.assertEqual(self.client.post(BASE, {}, format="json").status_code, 401)

    def test_notes_and_daily_optional_actions(self):
        notes = models.StudyBlock.objects.create(
            plan=self.plan, block_kind="notes_review", scheduled_date=timezone.localdate(),
            estimated_minutes=10, snapshot_title="Notes",
        )
        self.assertEqual(self.start(block=notes).data["session"]["primary_block"]["action_href"], "/notes")
        active = models.StudySession.objects.get(user=self.owner, status="in_progress")
        self.client.post(BASE + f"{active.id}/abandon/", {}, format="json")
        challenge_block = models.StudyBlock.objects.create(
            plan=self.plan, block_kind="daily_challenge_optional",
            scheduled_date=timezone.localdate(), estimated_minutes=10,
            snapshot_title="Daily challenge",
        )
        absent = self.start(block=challenge_block)
        self.assertEqual((absent.status_code, absent.data["code"]), (409, "study_session_block_unavailable"))
        challenge = models.DailyChallenge.objects.create(prompt="Question")
        choice = models.DailyChallengeChoice.objects.create(challenge=challenge, text="Correct", is_correct=True)
        available = self.start(block=challenge_block)
        self.assertEqual(available.status_code, 201)
        self.assertEqual(available.data["session"]["primary_block"]["action_href"], "/study#daily-challenge")
        models.DailyChallengeAttempt.objects.create(
            user=self.owner, challenge=challenge, activity_date=timezone.localdate(),
            selected_choice=choice, is_correct=True,
        )
        changed = self.client.get(BASE + f"{available.data['session']['id']}/").data["session"]
        self.assertIsNone(changed["primary_block"]["action_href"])
        self.assertFalse(changed["primary_block"]["target_active"])

    def test_canonical_evidence_predating_session_still_completes_block(self):
        quiz = models.Quiz.objects.create(slug="session-evidence-quiz", title="Quiz")
        case = models.ClinicalCase.objects.create(slug="session-evidence-case", title="Case", patient_summary="Summary")
        revision = models.CaseRevision.objects.create(case=case, version=1, title="Revision")
        step = models.CaseStep.objects.create(
            case=case, revision=revision, stable_key="entry", title="Entry",
            narrative="Narrative", sort_order=0,
        )
        revision.entry_step = step
        revision.save(update_fields=("entry_step",))
        case.current_revision = revision
        case.save(update_fields=("current_revision",))
        distortion = models.Concept.objects.create(
            slug="session-distortion", name_en="Distortion",
            subtype=models.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True,
        )
        card = models.Flashcard.objects.create(slug="session-evidence-card", front="Front", back="Back")
        item = models.CognitiveDistortionPracticeItem.objects.create(
            slug="session-evidence-item", prompt="Prompt", explanation="Explanation",
            target_concept=distortion,
        )
        choice = models.CognitiveDistortionPracticeChoice.objects.create(
            item=item, concept=distortion, text="Choice", is_correct=True,
        )
        cases = (
            ("quiz_practice", {"quiz": quiz}, lambda: models.QuizAttempt.objects.create(
                user=self.owner, quiz=quiz, status="completed", completed_at=timezone.now())),
            ("case_practice", {"clinical_case": case}, lambda: models.CaseAttempt.objects.create(
                user=self.owner, case=case, revision=revision, status="completed", completed_at=timezone.now())),
            ("flashcard_review", {}, lambda: models.StudyActivity.objects.create(
                user=self.owner, activity_type="flashcard_review", flashcard=card)),
            ("distortion_practice", {"concept": distortion}, lambda: models.CognitiveDistortionPracticeAttempt.objects.create(
                user=self.owner, item=item, selected_choice=choice, is_correct=True)),
        )
        for kind, target, create_evidence in cases:
            with self.subTest(kind=kind):
                block = models.StudyBlock.objects.create(
                    plan=self.plan, block_kind=kind, scheduled_date=timezone.localdate(),
                    estimated_minutes=20, snapshot_title=kind, **target,
                )
                evidence = create_evidence()
                started = self.start(block=block)
                self.assertEqual(started.status_code, 201, started.data)
                done = self.client.post(f"/api/study/blocks/{block.id}/complete/", {}, format="json")
                self.assertEqual(done.status_code, 200, done.data)
                self.assertIn(evidence.id, done.data["metadata"]["completion_evidence"].values())
                session_id = started.data["session"]["id"]
                self.assertEqual(self.client.post(BASE + f"{session_id}/complete/", {}, format="json").status_code, 200)

    def test_canonical_evidence_unmodified_and_block_evidence_floor(self):
        quiz = models.Quiz.objects.create(slug="session-quiz", title="Quiz")
        block = models.StudyBlock.objects.create(
            plan=self.plan, block_kind="quiz_practice", scheduled_date=timezone.localdate(),
            estimated_minutes=20, snapshot_title="Quiz", quiz=quiz,
        )
        canonical = (
            models.StudyPlan, models.StudyBlock, models.QuizAttempt,
            models.CaseAttempt, models.CaseAttemptEvent, models.UserFlashcardProgress,
            models.RecommendationFeedback, models.StudyActivity,
            models.UserConceptProgress, models.UserProgress,
            models.DailyChallengeAttempt, models.CognitiveDistortionPracticeAttempt,
        )
        before = {model.__name__: list(model.objects.order_by("pk").values()) for model in canonical}
        session_id = self.start(block=block).data["session"]["id"]
        self.client.post(BASE + f"{session_id}/complete/", {}, format="json")
        after = {model.__name__: list(model.objects.order_by("pk").values()) for model in canonical}
        self.assertEqual(after, before)
        missing = self.client.post(f"/api/study/blocks/{block.id}/complete/", {}, format="json")
        self.assertEqual(missing.data["code"], "study_block_evidence_missing")
        self.assertEqual(models.StudyBlock.objects.get(pk=block.id).status, "pending")

    def test_read_only_audit_reports_session_corruption(self):
        session_id = self.start().data["session"]["id"]
        # An impossible duration can be introduced only by bypassing the model and DB checks.
        # The normal audit remains read-only and accepts valid session rows.
        before = list(models.StudySession.objects.values())
        out = StringIO()
        # The Plan audit also expects seven availability rows and an active scope.
        models.StudyPlanScope.objects.create(plan=self.plan, concept=self.concept)
        for weekday in range(7):
            models.StudyPlanAvailability.objects.create(plan=self.plan, weekday=weekday, available_minutes=30)
        models.StudyPlanScope.objects.create(plan=self.foreign_plan, concept=self.concept)
        for weekday in range(7):
            models.StudyPlanAvailability.objects.create(plan=self.foreign_plan, weekday=weekday, available_minutes=30)
        call_command("audit_study_plans", stdout=out)
        self.assertIn("sessions=1", out.getvalue())
        self.assertEqual(list(models.StudySession.objects.values()), before)
        models.StudySession.objects.filter(pk=session_id).update(plan=self.foreign_plan)
        corrupt = list(models.StudySession.objects.values())
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("audit_study_plans", stdout=out)
        self.assertIn(f"session:{session_id}:foreign_plan", out.getvalue())
        self.assertEqual(list(models.StudySession.objects.values()), corrupt)


class StudySessionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("session-race", password="unused")
        self.concept, self.plan, self.block = fixture(self.user, "race")
        self.second = models.StudyBlock.objects.create(
            plan=self.plan, block_kind="concept_review", scheduled_date=timezone.localdate(),
            estimated_minutes=20, snapshot_title="Second", concept=self.concept,
        )

    def _race(self, requests):
        def submit(args):
            block, event = args
            close_old_connections()
            client = APIClient()
            client.force_authenticate(self.user)
            response = client.post(BASE, {
                "primary_block_id": block.id, "client_event_id": str(event),
            }, format="json")
            close_old_connections()
            return response.status_code, response.data
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(submit, requests))

    def test_concurrent_equivalent_start_creates_one_row(self):
        event = uuid.uuid4()
        results = self._race([(self.block, event), (self.block, event)])
        self.assertEqual(sorted(code for code, _ in results), [200, 201], results)
        self.assertEqual(models.StudySession.objects.filter(user=self.user).count(), 1)
        self.assertEqual(results[0][1]["session"]["id"], results[1][1]["session"]["id"])

    def test_concurrent_different_start_creates_one_and_conflicts_one(self):
        results = self._race([(self.block, uuid.uuid4()), (self.second, uuid.uuid4())])
        self.assertEqual(sorted(code for code, _ in results), [201, 409], results)
        self.assertEqual(next(body["code"] for code, body in results if code == 409), "study_session_active")
        self.assertEqual(models.StudySession.objects.filter(user=self.user, status="in_progress").count(), 1)

    def test_database_active_and_event_constraints(self):
        first = models.StudySession.objects.create(
            user=self.user, plan=self.plan, primary_block=self.block,
            block_id_at_start=self.block.id, client_event_id=uuid.uuid4(),
            planned_minutes=25, started_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.StudySession.objects.create(
                user=self.user, plan=self.plan, primary_block=self.second,
                block_id_at_start=self.second.id, client_event_id=uuid.uuid4(),
                planned_minutes=25, started_at=timezone.now(),
            )
        first.status = "completed"
        first.completed_at = timezone.now()
        first.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.StudySession.objects.create(
                user=self.user, plan=self.plan, primary_block=self.second,
                block_id_at_start=self.second.id, client_event_id=first.client_event_id,
                planned_minutes=25, started_at=timezone.now(),
            )

    def test_concurrent_terminal_requests_are_idempotent_or_conflict(self):
        def start():
            client = APIClient()
            client.force_authenticate(self.user)
            return client.post(BASE, {
                "primary_block_id": self.block.id,
                "client_event_id": str(uuid.uuid4()),
            }, format="json").data["session"]["id"]

        def end(session_id, suffix):
            close_old_connections()
            client = APIClient()
            client.force_authenticate(self.user)
            response = client.post(BASE + f"{session_id}/{suffix}/", {}, format="json")
            close_old_connections()
            return response.status_code, response.data

        first_id = start()
        with ThreadPoolExecutor(max_workers=2) as pool:
            same = list(pool.map(lambda _: end(first_id, "complete"), range(2)))
        self.assertEqual([code for code, _ in same], [200, 200], same)
        self.assertEqual(same[0][1]["session"]["completed_at"], same[1][1]["session"]["completed_at"])

        second_id = start()
        with ThreadPoolExecutor(max_workers=2) as pool:
            mixed = list(pool.map(lambda suffix: end(second_id, suffix), ("complete", "abandon")))
        self.assertEqual(sorted(code for code, _ in mixed), [200, 409], mixed)
        self.assertEqual(next(body["code"] for code, body in mixed if code == 409), "study_session_transition_conflict")

    def test_database_bounds_and_lifecycle_checks(self):
        row = models.StudySession.objects.create(
            user=self.user, plan=self.plan, primary_block=self.block,
            block_id_at_start=self.block.id, client_event_id=uuid.uuid4(),
            planned_minutes=25, started_at=timezone.now(),
        )
        invalid_updates = (
            {"block_id_at_start": 0}, {"planned_minutes": 4},
            {"planned_minutes": 241}, {"actual_seconds": 86401},
            {"status": "completed"}, {"status": "abandoned"},
            {"status": "unknown"}, {"completed_at": timezone.now()},
        )
        for update in invalid_updates:
            with self.subTest(update=update), self.assertRaises(IntegrityError), transaction.atomic():
                models.StudySession.objects.filter(pk=row.pk).update(**update)
        self.assertEqual(models.StudySession.objects.get(pk=row.pk).status, "in_progress")

    def test_user_and_plan_deletion_boundaries(self):
        row = models.StudySession.objects.create(
            user=self.user, plan=self.plan, primary_block=self.block,
            block_id_at_start=self.block.id, client_event_id=uuid.uuid4(),
            planned_minutes=25, started_at=timezone.now(),
        )
        self.block.delete()
        row.refresh_from_db()
        self.assertIsNone(row.primary_block_id)
        self.assertGreater(row.block_id_at_start, 0)
        self.plan.delete()
        self.assertFalse(models.StudySession.objects.filter(pk=row.pk).exists())
