"""v0.8.4 Today API contract, orchestration, isolation, and query regressions."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from . import models
from .learning import get_recommendations


TODAY_URL = "/api/study/today/"
NOW = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)
TOP_LEVEL = {
    "version", "as_of", "local_date", "timezone", "capacity", "active_session",
    "review", "active_plans", "today_blocks", "overdue_blocks",
    "daily_challenge", "next_action", "recommendations",
}
NEXT_ACTION = {
    "kind", "reason_code", "target", "plan_id", "block_id",
    "recommendation_key", "can_start_session", "action",
}
BLOCK_FIELDS = {
    "id", "plan_id", "block_kind", "status", "scheduled_date", "sequence",
    "estimated_minutes", "snapshot_title", "scope_priority", "action_href",
    "target_active", "evidence_required", "can_start_session",
}


class TodayApiTests(APITestCase):
    def setUp(self):
        self.clock = patch("django.utils.timezone.now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.owner = get_user_model().objects.create_user("today-owner", password="unused")
        self.other = get_user_model().objects.create_user("today-other", password="unused")
        self.client.force_authenticate(self.owner)
        self.app_date = timezone.localdate()
        self.concept = models.Concept.objects.create(
            slug="today-concept", name_en="Today concept", is_active=True,
        )

    def response(self):
        result = self.client.get(TODAY_URL)
        self.assertEqual(result.status_code, 200, result.data)
        return result.data

    def settings_row(self, **fields):
        return models.UserStudySettings.objects.create(user=self.owner, **fields)

    def plan(self, *, user=None, name="Plan", status="active", target_date=None,
             generation_version=0, generation_fingerprint=""):
        return models.StudyPlan.objects.create(
            user=user or self.owner, name=name, status=status,
            start_date=self.app_date - timedelta(days=40), target_date=target_date,
            generation_version=generation_version,
            generation_fingerprint=generation_fingerprint,
        )

    def availability(self, plan, minutes, *, day=None):
        return models.StudyPlanAvailability.objects.create(
            plan=plan, weekday=self.app_date.weekday() if day is None else day,
            available_minutes=minutes,
        )

    def block(self, plan, *, day=None, minutes=20, status="pending", sequence=0,
              concept=None, scope=None, kind="concept_review"):
        targets = {"concept": concept or self.concept} if kind == "concept_review" else {}
        terminal = ({"completed_at": NOW} if status == "completed" else
                    {"skipped_at": NOW} if status == "skipped" else {})
        return models.StudyBlock.objects.create(
            plan=plan, scope=scope, block_kind=kind, status=status,
            scheduled_date=day or self.app_date, estimated_minutes=minutes,
            sequence=sequence, snapshot_title="Today work", **targets, **terminal,
        )

    def scope(self, plan, priority, *, concept=None):
        return models.StudyPlanScope.objects.create(
            plan=plan, priority=priority, concept=concept or self.concept,
        )

    def challenge(self):
        challenge = models.DailyChallenge.objects.create(prompt="Question", is_active=True)
        correct = models.DailyChallengeChoice.objects.create(
            challenge=challenge, text="Yes", is_correct=True,
        )
        models.DailyChallengeChoice.objects.create(
            challenge=challenge, text="No", is_correct=False,
        )
        return challenge, correct

    def card(self, slug, *, due_at=None, user=None, active=True):
        card = models.Flashcard.objects.create(
            slug=slug, front="Front", back="Back", is_active=active,
        )
        if due_at is not None:
            models.UserFlashcardProgress.objects.create(
                user=user or self.owner, flashcard=card, due_at=due_at,
            )
        return card

    def case_attempt(self, slug, *, user=None):
        case = models.ClinicalCase.objects.create(
            slug=slug, title=slug, patient_summary="Educational case", is_active=True,
        )
        revision = models.CaseRevision.objects.create(
            case=case, version=1, title=slug, patient_summary="Educational case",
            status=models.CaseRevision.Status.PUBLISHED,
        )
        step = models.CaseStep.objects.create(
            case=case, revision=revision, stable_key="entry", title="Entry",
            narrative="Educational content", sort_order=0, is_active=True,
        )
        revision.entry_step = step
        revision.save(update_fields=("entry_step", "updated_at"))
        case.current_revision = revision
        case.save(update_fields=("current_revision", "updated_at"))
        return models.CaseAttempt.objects.create(
            user=user or self.owner, case=case, revision=revision,
            current_step=step, status=models.CaseAttempt.Status.IN_PROGRESS,
        )

    def assert_action(self, payload, kind, reason, target_type, target_id=None):
        action = payload["next_action"]
        self.assertEqual(set(action), NEXT_ACTION)
        self.assertEqual((action["kind"], action["reason_code"]), (kind, reason))
        self.assertEqual(action["target"], {"type": target_type, "id": target_id})
        self.assertIsInstance(action["action"]["href"], str)
        self.assertTrue(action["action"]["href"].startswith("/"))
        self.assertIsInstance(action["action"]["label"], str)
        self.assertTrue(action["action"]["label"])
        return action

    def dismiss_visible_recommendations(self):
        for _ in range(10):
            items = self.response()["recommendations"]["items"]
            if not items:
                return
            for item in items:
                result = self.client.post(
                    f"/api/study/recommendations/{item['key']}/feedback/",
                    {"value": "dismissed", "client_event_id": str(uuid.uuid4())},
                    format="json",
                )
                self.assertEqual(result.status_code, 200, result.data)
        self.fail("Recommendation list did not converge after dismissal")

    def test_empty_account_exact_shape_defaults_and_no_settings_insert(self):
        payload = self.response()
        self.assertEqual(set(payload), TOP_LEVEL)
        self.assertEqual(payload["version"], "v1")
        self.assertEqual(payload["as_of"], NOW.isoformat())
        self.assertEqual(payload["timezone"], settings.TIME_ZONE)
        self.assertEqual(payload["local_date"], self.app_date.isoformat())
        self.assertEqual(payload["capacity"], {
            "available_minutes": 0, "scheduled_minutes": 0,
            "completed_minutes": 0, "remaining_minutes": 0,
            "over_capacity_minutes": 0,
        })
        self.assertEqual(payload["review"], {"due": 0, "overdue": 0, "new": 0})
        self.assertIsNone(payload["active_session"])
        for name in ("active_plans", "today_blocks", "overdue_blocks"):
            self.assertEqual(payload[name], {"total": 0, "items": [], "truncated": False})
        self.assertEqual(set(payload["daily_challenge"]), {
            "challenge_date", "available", "completed", "action",
        })
        self.assertEqual(payload["daily_challenge"]["challenge_date"], self.app_date.isoformat())
        self.assertFalse(payload["daily_challenge"]["available"])
        self.assertFalse(payload["daily_challenge"]["completed"])
        self.assertIsNone(payload["daily_challenge"]["action"])
        self.assert_action(payload, "onboarding", "create_plan", "none")
        self.assertEqual(payload["next_action"]["action"]["href"], "/study/plans/new")
        self.assertEqual(set(payload["recommendations"]), {
            "version", "as_of", "items", "returned_count", "suppressed_count",
            "truncated_sources",
        })
        self.assertEqual(payload["recommendations"]["as_of"], payload["as_of"])
        self.assertFalse(models.UserStudySettings.objects.filter(user=self.owner).exists())

    def test_authentication_and_query_contract(self):
        for query in ("?limit=8", "?x=1", "?x=1&x=2"):
            result = self.client.get(TODAY_URL + query)
            self.assertEqual((result.status_code, result.data["code"]),
                             (400, "study_today_invalid_query"))
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(TODAY_URL).status_code, 401)

    def test_one_plan_target_dates_and_zero_availability(self):
        plan = self.plan(target_date=self.app_date)
        block = self.block(plan, minutes=35)
        payload = self.response()
        self.assertEqual(payload["active_plans"]["items"][0], {
            "id": plan.id, "name": "Plan", "plan_kind": "general",
            "target_date": self.app_date.isoformat(), "days_remaining": 0,
            "generation_version": 0, "schedule_stale": False,
            "today_available_minutes": 0,
        })
        self.assertEqual(payload["capacity"], {
            "available_minutes": 0, "scheduled_minutes": 35,
            "completed_minutes": 0, "remaining_minutes": 0,
            "over_capacity_minutes": 35,
        })
        self.assertEqual(payload["today_blocks"]["total"], 1)
        self.assertEqual(set(payload["today_blocks"]["items"][0]), BLOCK_FIELDS)
        self.assertEqual(payload["today_blocks"]["items"][0]["id"], block.id)
        self.assert_action(payload, "today_block", "block_due_today", "study_block", block.id)
        self.assertTrue(payload["next_action"]["can_start_session"])
        past = self.plan(name="Past target", target_date=self.app_date - timedelta(days=1))
        self.assertEqual(self.response()["active_plans"]["items"][1]["days_remaining"], -1)
        self.assertEqual(past.target_date, self.app_date - timedelta(days=1))

    def test_multiple_plans_capacity_aggregates_all_and_caps_global_limit(self):
        self.settings_row(default_daily_minutes=60, default_session_minutes=25)
        first = self.plan(name="First")
        second = self.plan(name="Second")
        paused = self.plan(name="Paused", status="paused")
        self.availability(first, 50)
        self.availability(second, 50)
        self.availability(paused, 100)
        self.block(first, minutes=30)
        self.block(second, minutes=25)
        completed = self.block(second, minutes=20, status="completed")
        self.block(paused, minutes=100)
        payload = self.response()
        self.assertEqual(payload["capacity"], {
            "available_minutes": 60, "scheduled_minutes": 75,
            "completed_minutes": 20, "remaining_minutes": 40,
            "over_capacity_minutes": 15,
        })
        self.assertEqual(payload["active_plans"]["total"], 2)
        self.assertEqual([row["id"] for row in payload["active_plans"]["items"]],
                         [first.id, second.id])
        self.assertEqual(payload["today_blocks"]["total"], 2)
        self.assertNotIn(completed.id, [row["id"] for row in payload["today_blocks"]["items"]])

    def test_completed_estimate_survives_inactive_target_and_session_seconds_are_not_capacity(self):
        self.settings_row(default_daily_minutes=80, default_session_minutes=25)
        plan = self.plan()
        self.availability(plan, 60)
        completed_target = models.Concept.objects.create(
            slug="completed-target", name_en="Completed", is_active=True,
        )
        self.block(plan, minutes=30, status="completed", concept=completed_target)
        live = self.block(plan, minutes=20)
        completed_target.is_active = False
        completed_target.save(update_fields=("is_active",))
        started = self.client.post("/api/study/sessions/", {
            "primary_block_id": live.id, "client_event_id": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(started.status_code, 201, started.data)
        payload = self.response()
        self.assertEqual(payload["capacity"], {
            "available_minutes": 60, "scheduled_minutes": 50,
            "completed_minutes": 30, "remaining_minutes": 30,
            "over_capacity_minutes": 0,
        })
        self.assert_action(payload, "resume_session", "session_in_progress",
                           "study_session", started.data["session"]["id"])

    def test_overdue_and_today_order_by_priority_then_date_sequence_plan_id(self):
        first = self.plan(name="First")
        second = self.plan(name="Second")
        high = self.scope(second, 5)
        low = self.scope(first, 1)
        older = self.block(first, day=self.app_date - timedelta(days=5),
                           scope=low, sequence=1)
        highest = self.block(second, day=self.app_date - timedelta(days=1),
                             scope=high, sequence=3)
        same_priority_older = self.block(second, day=self.app_date - timedelta(days=3),
                                         scope=high, sequence=2)
        today_late = self.block(first, sequence=9)
        today_early = self.block(second, sequence=1)
        payload = self.response()
        self.assertEqual([row["id"] for row in payload["overdue_blocks"]["items"]],
                         [same_priority_older.id, highest.id, older.id])
        self.assertEqual([row["id"] for row in payload["today_blocks"]["items"]],
                         [today_early.id, today_late.id])
        self.assert_action(payload, "overdue_block", "block_overdue", "study_block",
                           same_priority_older.id)

    def test_superseded_inactive_archived_and_foreign_blocks_are_excluded(self):
        plan = self.plan()
        live = self.block(plan)
        excluded = [self.block(plan, status="superseded"),
                    self.block(plan, status="skipped")]
        inactive = models.Concept.objects.create(
            slug="inactive-today-concept", name_en="Inactive", is_active=False,
        )
        excluded.append(self.block(plan, concept=inactive))
        archived = self.plan(name="Archived", status="archived")
        excluded.append(self.block(archived))
        foreign = self.plan(name="Foreign", user=self.other)
        excluded.append(self.block(foreign))
        payload = self.response()
        self.assertEqual([row["id"] for row in payload["today_blocks"]["items"]], [live.id])
        self.assertEqual(payload["today_blocks"]["total"], 1)
        self.assertTrue(all(item.id != live.id for item in excluded))
        self.assertNotIn(foreign.id, [row["id"] for row in payload["active_plans"]["items"]])
        self.assert_action(payload, "today_block", "block_due_today", "study_block", live.id)

    def test_session_resume_precedes_case_and_unavailable_focus_still_resumes(self):
        plan = self.plan()
        block = self.block(plan)
        self.case_attempt("session-precedence-case")
        started = self.client.post("/api/study/sessions/", {
            "primary_block_id": block.id, "client_event_id": str(uuid.uuid4()),
        }, format="json")
        self.assertEqual(started.status_code, 201, started.data)
        session_id = started.data["session"]["id"]
        first = self.response()
        self.assertEqual(first["active_session"]["id"], session_id)
        self.assertEqual(first["active_session"]["as_of"], first["as_of"])
        self.assert_action(first, "resume_session", "session_in_progress",
                           "study_session", session_id)
        self.assertEqual(first["next_action"]["action"]["href"], f"/study/session/{session_id}")
        self.concept.is_active = False
        self.concept.save(update_fields=("is_active",))
        unavailable = self.response()
        self.assert_action(unavailable, "resume_session", "session_focus_unavailable",
                           "study_session", session_id)
        self.assertFalse(unavailable["active_session"]["primary_block"]["target_active"])
        self.assertIsNone(unavailable["active_session"]["primary_block"]["action_href"])
        self.assertEqual(unavailable["next_action"]["block_id"], block.id)

    def test_recent_case_resume_precedes_blocks_and_ties_on_latest_id(self):
        plan = self.plan()
        overdue = self.block(plan, day=self.app_date - timedelta(days=1))
        older = self.case_attempt("older-resumable-case")
        newer = self.case_attempt("newer-resumable-case")
        payload = self.response()
        self.assert_action(payload, "resume_case", "case_in_progress",
                           "clinical_case", newer.case_id)
        self.assertEqual(payload["next_action"]["action"]["href"],
                         f"/cases/{newer.case.slug}")
        models.CaseAttempt.objects.filter(pk=older.pk).update(updated_at=NOW + timedelta(minutes=1))
        self.assert_action(self.response(), "resume_case", "case_in_progress",
                           "clinical_case", older.case_id)
        models.CaseAttempt.objects.filter(pk=older.pk).update(updated_at=NOW - timedelta(days=31))
        newer.case.is_active = False
        newer.case.save(update_fields=("is_active",))
        self.assert_action(self.response(), "overdue_block", "block_overdue",
                           "study_block", overdue.id)

    def test_retired_pinned_case_remains_resumable_in_today_and_v2(self):
        attempt = self.case_attempt("retired-pinned-case")
        case = attempt.case
        attempt.revision.status = models.CaseRevision.Status.RETIRED
        attempt.revision.save(update_fields=("status", "updated_at"))
        current = models.CaseRevision.objects.create(
            case=case, version=2, title="Current revision",
            patient_summary="Updated educational case",
            status=models.CaseRevision.Status.PUBLISHED,
        )
        entry = models.CaseStep.objects.create(
            case=case, revision=current, stable_key="current-entry",
            title="Current entry", narrative="Current content", sort_order=1,
            is_active=True,
        )
        current.entry_step = entry
        current.save(update_fields=("entry_step", "updated_at"))
        case.current_revision = current
        case.save(update_fields=("current_revision", "updated_at"))

        resumed = self.client.post(f"/api/cases/{case.slug}/attempts/", {}, format="json")
        self.assertEqual(resumed.status_code, 200, resumed.data)
        self.assertTrue(resumed.data["resumed"])
        self.assertEqual(resumed.data["id"], attempt.id)

        today = self.response()
        self.assert_action(today, "resume_case", "case_in_progress", "clinical_case", case.id)
        self.assertTrue(any(
            item["type"] == "case_resume" and item["target"]["id"] == case.id
            for item in today["recommendations"]["items"]
        ))

    def test_srs_due_overdue_new_and_visibility(self):
        self.card("overdue-card", due_at=NOW - timedelta(days=1))
        self.card("due-card", due_at=NOW - timedelta(minutes=1))
        self.card("future-card", due_at=NOW + timedelta(days=1))
        self.card("new-card")
        self.card("hidden-card", due_at=NOW - timedelta(days=1), active=False)
        self.card("foreign-card", due_at=NOW - timedelta(days=1), user=self.other)
        local_start = datetime.combine(self.app_date, time.min,
                                       tzinfo=ZoneInfo(settings.TIME_ZONE)).astimezone(UTC)
        self.assertLess(NOW - timedelta(days=1), local_start)
        payload = self.response()
        self.assertEqual(payload["review"], {"due": 2, "overdue": 1, "new": 2})
        self.assert_action(payload, "srs_review", "srs_overdue", "review_queue")
        self.assertEqual(payload["next_action"]["action"]["href"], "/flashcards")
        models.UserFlashcardProgress.objects.filter(
            user=self.owner, flashcard__slug="overdue-card",
        ).update(due_at=NOW + timedelta(days=1))
        self.assert_action(self.response(), "srs_review", "srs_due", "review_queue")

    def test_daily_challenge_state_completion_and_optional_capacity(self):
        self.settings_row(default_daily_minutes=60, default_session_minutes=25)
        plan = self.plan()
        self.availability(plan, 60)
        challenge, choice = self.challenge()
        initial = self.response()
        self.assertEqual(initial["daily_challenge"], {
            "challenge_date": self.app_date.isoformat(), "available": True,
            "completed": False,
            "action": {"href": "/study#daily-challenge", "label": "چالش روزانه"},
        })
        self.assert_action(initial, "daily_challenge", "challenge_available", "daily_challenge")
        self.block(plan, minutes=60, status="completed")
        no_headroom = self.response()
        self.assertEqual(no_headroom["daily_challenge"]["available"], True)
        self.assertNotEqual(no_headroom["next_action"]["kind"], "daily_challenge")
        models.DailyChallengeAttempt.objects.create(
            user=self.owner, challenge=challenge, selected_choice=choice,
            activity_date=self.app_date, is_correct=True,
        )
        challenge.is_active = False
        challenge.save(update_fields=("is_active",))
        complete = self.response()["daily_challenge"]
        self.assertEqual((complete["available"], complete["completed"], complete["action"]),
                         (False, True, None))

    def test_stale_plan_remains_actionable_then_prepares_schedule(self):
        plan = self.plan(generation_version=2)
        block = self.block(plan)
        payload = self.response()
        self.assertTrue(payload["active_plans"]["items"][0]["schedule_stale"])
        self.assert_action(payload, "today_block", "block_due_today", "study_block", block.id)
        block.status = models.StudyBlock.Status.SUPERSEDED
        block.save(update_fields=("status",))
        self.dismiss_visible_recommendations()
        empty = self.response()
        self.assert_action(empty, "onboarding", "prepare_schedule", "study_plan", plan.id)
        self.assertEqual(empty["next_action"]["action"]["href"], f"/study/plans/{plan.id}")

    def test_nonempty_fingerprint_with_invalid_generation_summary_is_stale(self):
        plan = self.plan(generation_version=2, generation_fingerprint="old-fingerprint")
        plan.last_generated_at = NOW
        plan.last_generation_summary = {"generation_version": 2}  # missing required summary fields
        plan.save(update_fields=("last_generated_at", "last_generation_summary"))
        self.assertTrue(self.response()["active_plans"]["items"][0]["schedule_stale"])
        self.dismiss_visible_recommendations()
        self.assert_action(self.response(), "onboarding", "prepare_schedule", "study_plan", plan.id)

    def test_due_srs_then_challenge_then_v2_then_onboarding_precedence(self):
        self.settings_row(default_daily_minutes=60, default_session_minutes=25)
        plan = self.plan()
        self.availability(plan, 60)
        challenge, choice = self.challenge()
        card = self.card("chain-due", due_at=NOW - timedelta(hours=1))
        models.UserConceptProgress.objects.create(
            user=self.owner, concept=self.concept, progress_percent=25,
        )
        self.assert_action(self.response(), "srs_review", "srs_due", "review_queue")
        models.UserFlashcardProgress.objects.filter(user=self.owner, flashcard=card).update(
            due_at=NOW + timedelta(days=1),
        )
        self.assert_action(self.response(), "daily_challenge", "challenge_available",
                           "daily_challenge")
        models.DailyChallengeAttempt.objects.create(
            user=self.owner, challenge=challenge, selected_choice=choice,
            activity_date=self.app_date, is_correct=True,
        )
        recommendation = self.response()
        first_item = recommendation["recommendations"]["items"][0]
        self.assert_action(recommendation, "recommendation", "recommendation_v2",
                           first_item["target"]["type"], first_item["target"]["id"])
        self.dismiss_visible_recommendations()
        self.assert_action(self.response(), "onboarding", "prepare_schedule", "study_plan", plan.id)

    def test_onboarding_fallbacks_are_deterministic(self):
        self.plan(status="paused")
        self.assert_action(self.response(), "onboarding", "review_plans", "none")
        active = self.plan()
        self.dismiss_visible_recommendations()
        self.assert_action(self.response(), "onboarding", "prepare_schedule", "study_plan", active.id)
        active.generation_version = 1
        active.generation_fingerprint = "current"
        active.last_generated_at = NOW
        active.last_generation_summary = {
            "generation_version": 1, "unscheduled_candidates": 0,
            "capacity_shortfall_minutes": 0, "available_minutes": 0,
        }
        active.save(update_fields=(
            "generation_version", "generation_fingerprint", "last_generated_at",
            "last_generation_summary",
        ))
        self.dismiss_visible_recommendations()
        self.assert_action(self.response(), "onboarding", "review_plans", "none")
        self.card("new-onboarding-card")
        # V2's visible new-card advice precedes onboarding. Dismissing that advice
        # exposes the deterministic onboarding SRS-new branch.
        self.dismiss_visible_recommendations()
        self.assert_action(self.response(), "onboarding", "srs_new", "review_queue")

    def test_v2_fallback_is_exactly_visible_first_item_and_dismissal_applies(self):
        models.UserConceptProgress.objects.create(
            user=self.owner, concept=self.concept, progress_percent=25,
        )
        first = self.response()
        recommendations = first["recommendations"]
        self.assertEqual(recommendations["version"], "v2")
        self.assertEqual(recommendations["returned_count"], len(recommendations["items"]))
        self.assertLessEqual(len(recommendations["items"]), 8)
        item = recommendations["items"][0]
        action = self.assert_action(first, "recommendation", "recommendation_v2",
                                    item["target"]["type"], item["target"]["id"])
        self.assertEqual(action["recommendation_key"], item["key"])
        self.assertEqual(action["action"], item["action"])
        result = self.client.post(
            f"/api/study/recommendations/{item['key']}/feedback/",
            {"value": "dismissed", "client_event_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(result.status_code, 200, result.data)
        after = self.response()
        self.assertNotIn(item["key"], [row["key"] for row in after["recommendations"]["items"]])
        self.assertNotEqual(after["next_action"]["recommendation_key"], item["key"])
        self.assertGreaterEqual(after["recommendations"]["suppressed_count"], 1)

    def test_same_state_gives_same_selector_identity_and_no_active_session(self):
        plan = self.plan()
        block = self.block(plan)
        first = self.response()
        second = self.response()
        self.assertIsNone(first["active_session"])
        self.assertEqual(first["next_action"], second["next_action"])
        self.assertEqual(first["next_action"]["block_id"], block.id)
        self.assertEqual(first["recommendations"]["as_of"], first["as_of"])

    def test_study_timezone_boundary_keeps_app_day_challenge(self):
        boundary = datetime(2026, 9, 29, 20, 45, tzinfo=UTC)
        self.clock.stop()
        boundary_clock = patch("django.utils.timezone.now", return_value=boundary)
        boundary_clock.start()
        self.addCleanup(boundary_clock.stop)
        self.settings_row(study_timezone="America/Los_Angeles")
        plan = self.plan()
        self.availability(plan, 35, day=date(2026, 9, 29).weekday())
        self.block(plan, day=date(2026, 9, 29))
        challenge, choice = self.challenge()
        app_date = timezone.localdate()
        self.assertNotEqual(app_date, date(2026, 9, 29))
        models.DailyChallengeAttempt.objects.create(
            user=self.owner, challenge=challenge, selected_choice=choice,
            activity_date=app_date, is_correct=True,
        )
        self.card("boundary-overdue", due_at=datetime(2026, 9, 29, 6, tzinfo=UTC))
        self.card("boundary-due", due_at=datetime(2026, 9, 29, 8, tzinfo=UTC))
        payload = self.response()
        self.assertEqual((payload["local_date"], payload["timezone"]),
                         ("2026-09-29", "America/Los_Angeles"))
        self.assertEqual(payload["daily_challenge"]["challenge_date"], app_date.isoformat())
        self.assertTrue(payload["daily_challenge"]["completed"])
        self.assertEqual(payload["capacity"]["available_minutes"], 35)
        self.assertEqual(payload["today_blocks"]["total"], 1)
        self.assertEqual(payload["review"], {"due": 2, "overdue": 1, "new": 0})
        self.assertEqual(payload["active_plans"]["items"][0]["days_remaining"], None)

    def test_invalid_timezone_falls_back_without_write(self):
        row = self.settings_row(study_timezone="Invalid/Zone")
        original_updated_at = row.updated_at
        payload = self.response()
        self.assertEqual(payload["timezone"], settings.TIME_ZONE)
        self.assertEqual(payload["local_date"], self.app_date.isoformat())
        row.refresh_from_db()
        self.assertEqual(row.study_timezone, "Invalid/Zone")
        self.assertEqual(row.updated_at, original_updated_at)

    def test_get_is_read_only_across_canonical_tables(self):
        plan = self.plan()
        self.availability(plan, 45)
        self.block(plan)
        self.card("read-only-card", due_at=NOW - timedelta(hours=1))
        self.challenge()
        models.UserConceptProgress.objects.create(
            user=self.owner, concept=self.concept, progress_percent=25,
        )
        tables = (
            models.UserStudySettings, models.StudyPlan, models.StudyPlanAvailability,
            models.StudyPlanScope, models.StudyBlock, models.StudySession,
            models.UserFlashcardProgress, models.QuizAttempt, models.CaseAttempt,
            models.RecommendationFeedback, models.DailyChallengeAttempt,
            models.StudyActivity, models.UserConceptProgress, models.UserProgress,
        )
        before = {model: model.objects.count() for model in tables}
        with CaptureQueriesContext(connection) as queries:
            self.response()
        after = {model: model.objects.count() for model in tables}
        self.assertEqual(after, before)
        writes = [query["sql"] for query in queries if query["sql"].lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER")
        )]
        self.assertEqual(writes, [])
        self.assertFalse(models.UserStudySettings.objects.filter(user=self.owner).exists())

    def test_owner_isolation_has_no_foreign_plan_block_session_case_or_feedback(self):
        foreign_plan = self.plan(user=self.other, name="Private plan")
        foreign_block = self.block(foreign_plan)
        foreign_session = models.StudySession.objects.create(
            user=self.other, plan=foreign_plan, primary_block=foreign_block,
            block_id_at_start=foreign_block.id, client_event_id=uuid.uuid4(),
            planned_minutes=25, started_at=NOW,
        )
        foreign_case = self.case_attempt("foreign-private-case", user=self.other)
        foreign_card = self.card("foreign-private-card", due_at=NOW - timedelta(days=1),
                                 user=self.other)
        models.UserConceptProgress.objects.create(
            user=self.other, concept=self.concept, progress_percent=25,
        )
        payload = self.response()
        self.assertEqual(payload["active_plans"]["total"], 0)
        self.assertEqual(payload["today_blocks"]["total"], 0)
        self.assertIsNone(payload["active_session"])
        self.assertEqual(payload["review"]["due"], 0)
        self.assertNotEqual(payload["next_action"]["target"]["id"], foreign_case.case_id)
        self.assertNotIn(foreign_plan.id, [row["id"] for row in payload["active_plans"]["items"]])
        self.assertNotIn(foreign_block.id, [row["id"] for row in payload["today_blocks"]["items"]])
        self.assertNotEqual(payload["active_session"], foreign_session.id)
        self.assertEqual(foreign_card.user_progress.count(), 1)
        self.assertFalse(any(
            row["type"] == "case_resume" and row["target"]["id"] == foreign_case.case_id
            for row in payload["recommendations"]["items"]
        ))

    def test_legacy_overview_and_dashboard_keep_v1_contract_after_today(self):
        models.UserConceptProgress.objects.create(
            user=self.owner, concept=self.concept, progress_percent=25,
        )
        expected_recommendations = get_recommendations(self.owner)
        overview_before = self.client.get("/api/study/overview/")
        dashboard_before = self.client.get("/api/dashboard/")
        self.assertEqual((overview_before.status_code, dashboard_before.status_code), (200, 200))
        self.response()
        overview_after = self.client.get("/api/study/overview/")
        dashboard_after = self.client.get("/api/dashboard/")
        self.assertEqual(set(overview_after.data), set(overview_before.data))
        self.assertEqual(set(dashboard_after.data), set(dashboard_before.data))
        self.assertEqual(overview_after.data, overview_before.data)
        self.assertEqual(dashboard_after.data, dashboard_before.data)
        self.assertEqual(overview_after.data["recommendations"], expected_recommendations)
        self.assertEqual(dashboard_after.data["recommendations"], expected_recommendations)
        self.assertTrue(all(set(row) == {"type", "title", "reason", "href", "priority"}
                            for row in expected_recommendations))

    def test_populated_fixture_caps_exact_totals_and_query_budget(self):
        self.settings_row(default_daily_minutes=90, default_session_minutes=25)
        plans = [self.plan(name=f"Budget plan {i:02d}") for i in range(24)]
        for plan in plans:
            self.availability(plan, 10)
        for i in range(31):
            self.block(plans[i % len(plans)], day=self.app_date, minutes=10, sequence=i)
            self.block(plans[i % len(plans)], day=self.app_date - timedelta(days=1),
                       minutes=10, sequence=i)
        inactive = models.Concept.objects.create(
            slug="budget-inactive", name_en="Inactive", is_active=False,
        )
        self.block(plans[0], concept=inactive)
        self.block(plans[0], status="superseded")
        active = models.StudySession.objects.create(
            user=self.owner, plan=plans[0], primary_block=plans[0].blocks.first(),
            block_id_at_start=plans[0].blocks.first().id,
            client_event_id=uuid.uuid4(), planned_minutes=25, started_at=NOW,
        )
        for i in range(12):
            block = self.block(plans[1], day=self.app_date - timedelta(days=10 + i))
            models.StudySession.objects.create(
                user=self.owner, plan=plans[1], primary_block=block,
                block_id_at_start=block.id, client_event_id=uuid.uuid4(),
                status="completed", planned_minutes=25, started_at=NOW,
                completed_at=NOW, actual_seconds=0,
            )
        for i in range(85):
            self.card(f"budget-card-{i:03d}", due_at=NOW - timedelta(days=1))
        for i in range(12):
            concept = models.Concept.objects.create(
                slug=f"budget-concept-{i:02d}", name_en="Budget", is_active=True,
            )
            models.UserConceptProgress.objects.create(
                user=self.owner, concept=concept, progress_percent=20,
            )
        for i in range(12):
            quiz = models.Quiz.objects.create(slug=f"budget-quiz-{i:02d}", title="Quiz")
            models.QuizAttempt.objects.create(
                user=self.owner, quiz=quiz, status="completed", completed_at=NOW,
                score=40, correct_count=0, total_questions=1,
            )
        for i in range(12):
            self.case_attempt(f"budget-case-{i:02d}")
        first_recommendation = self.client.get("/api/study/recommendations/").data["items"][0]
        feedback = self.client.post(
            f"/api/study/recommendations/{first_recommendation['key']}/feedback/",
            {"value": "dismissed", "client_event_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(feedback.status_code, 200, feedback.data)
        with CaptureQueriesContext(connection) as queries:
            payload = self.response()
        measured = len(queries)
        print(f"Today populated fixture query count: {measured}")
        self.assertEqual(payload["active_plans"]["total"], 24)
        self.assertEqual(payload["today_blocks"]["total"], 31)
        self.assertEqual(payload["overdue_blocks"]["total"], 43)
        for name in ("active_plans", "today_blocks", "overdue_blocks"):
            self.assertEqual(len(payload[name]["items"]), 20)
            self.assertTrue(payload[name]["truncated"])
        self.assertEqual(payload["capacity"]["available_minutes"], 90)
        # The inactive-target pending Block still occupies 20 scheduled minutes;
        # only actionable display lists exclude it.
        self.assertEqual(payload["capacity"]["scheduled_minutes"], 330)
        self.assertEqual(payload["capacity"]["over_capacity_minutes"], 240)
        self.assertEqual(payload["review"]["due"], 85)
        self.assertLessEqual(len(payload["recommendations"]["items"]), 8)
        self.assertEqual(payload["active_session"]["id"], active.id)
        # Measured at 31 on the populated SQLite fixture; nine queries leave
        # reasonable backend variation without allowing per-row lookups.
        self.assertLessEqual(measured, 40, f"Today query count: {measured}")
