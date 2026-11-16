"""W13-02 existing server-localdate rotation, not a second scheduling engine."""
from datetime import date, datetime, timezone as utc_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from .learning import today_challenge
from .cms_practice_editor import _result
from .models import Concept, DailyChallenge, DailyChallengeChoice, DailyChallengeAttempt
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DailyChallengeSchedulingTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.sign_in(self.owner)

    def test_admin_contract_uses_active_timezone_and_date_rollover(self):
        item = DailyChallenge.objects.create(
            prompt="NON-SCIENTIFIC date example", explanation="Synthetic",
            is_active=False,
        )
        now = datetime(2026, 11, 16, 23, 45, tzinfo=utc_timezone.utc)
        with patch("django.utils.timezone.now", return_value=now):
            with timezone.override("America/Los_Angeles"):
                a = _result("daily", item)["schedule"]
                self.assertEqual(a["activity_date"], "2026-11-16")
                self.assertEqual(a["timezone"], "America/Los_Angeles")
            with timezone.override("Asia/Tokyo"):
                b = _result("daily", item)["schedule"]
                self.assertEqual(b["activity_date"], "2026-11-17")
                self.assertEqual(b["timezone"], "Asia/Tokyo")
        self.assertEqual(a["rule"], "localdate_eligible_rotation_v1")
        self.assertTrue(a["candidate_pool_dynamic"])
        self.assertFalse(a["editorial_calendar_supported"])


    def test_dynamic_pool_reorder_disable_and_empty_preserve_historical_attempt(self):
        items = []
        for order in (10, 20):
            challenge = DailyChallenge.objects.create(
                prompt=f"NON-SCIENTIFIC pool {order}", is_active=True, sort_order=order)
            right = DailyChallengeChoice.objects.create(
                challenge=challenge, text="answer", is_correct=True)
            DailyChallengeChoice.objects.create(
                challenge=challenge, text="distractor", is_correct=False)
            items.append((challenge, right))
        day = date(2026, 11, 19)
        original = today_challenge(day)
        self.assertIsNotNone(original)
        correct = next(answer for challenge, answer in items if challenge.pk == original.pk)
        attempt = DailyChallengeAttempt.objects.create(
            user=self.normal, activity_date=day,
            challenge=original, selected_choice=correct, is_correct=True)
        items[0][0].sort_order = 30
        items[0][0].save(update_fields=["sort_order"])
        self.assertNotEqual(today_challenge(day).pk, original.pk)
        for challenge, _ in items:
            challenge.is_active = False
            challenge.save(update_fields=["is_active"])
        self.assertIsNone(today_challenge(day))
        attempt.refresh_from_db()
        self.assertEqual(attempt.challenge_id, original.pk)
        self.assertEqual(attempt.selected_choice_id, correct.pk)

    def test_rights_revocation_removes_live_selection_without_exposing_answer_key(self):
        from .cms_governance import resource_binding
        from .cms_review_models import ReviewPolicy
        from .models import SourceReference
        ReviewPolicy.objects.get_or_create(pk=1)
        items = []
        for order in (10, 20):
            item = DailyChallenge.objects.create(
                prompt=f"NON-SCIENTIFIC rights {order}", sort_order=order, is_active=True)
            DailyChallengeChoice.objects.create(
                challenge=item, text="true", is_correct=True)
            DailyChallengeChoice.objects.create(
                challenge=item, text="false", is_correct=False)
            items.append(item)
        day = date(2026, 11, 16)
        candidate = today_challenge(day)
        self.assertIsNotNone(candidate)
        # Current governance registry scopes the linked Concept, not DailyChallenge
        # itself. A raw record on an unsupported resource type is not a valid policy.
        linked = Concept.objects.create(
            slug="w13-synthetic-restricted-concept", name_en="Synthetic restricted concept")
        candidate.concept = linked
        candidate.save(update_fields=["concept"])
        evidence_source = SourceReference.objects.create(
            title="NON-SCIENTIFIC rights scheduling evidence")
        evidence = [{"source_id": evidence_source.pk, "locator": "Test-only rights scope"}]
        requested = self.post(self.admin, "governance/rights/", {
            "resource_type": "concept", "resource_id": linked.pk,
            "resource_version": resource_binding("concept", linked.pk)["resource_version"],
            "material": "metadata", "intended_use": "public_display",
            "status": "restricted", "rightsholder": "NON-SCIENTIFIC fixture owner",
            "holder_identification": "Synthetic approval only", "holder_evidence": evidence,
            "public_access": "unknown", "evidence": evidence,
            "reviewed_on": timezone.localdate().isoformat(),
            "effective_on": timezone.localdate().isoformat(),
            "expires_on": None, "review_on": None, "limitations": "Synthetic rights only",
            "territory": "", "conflict_note": "", "reason": "CORRECTION_REQUIRED",
        })
        self.assertEqual(requested.status_code, 201, requested.content[:300])
        record = requested.json()["record"]
        for action, changes in (
            ("assign", {"reviewer_id": self.owner.pk}),
            ("decide", {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED",
                         "self_review_ack": True}),
        ):
            result = self.post(self.admin, f"governance/rights/{record['id']}/{action}/",
                               changes, etag=f'"{record["version"]}"')
            self.assertEqual(result.status_code, 200, result.content[:300])
            record = result.json()["record"]
        replacement = today_challenge(day)
        self.assertIsNotNone(replacement)
        self.assertNotEqual(replacement.pk, candidate.pk)
        response = self.client.get("/api/daily-challenge/")
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertNotIn("is_correct", str(response.data))
        self.assertEqual(DailyChallengeAttempt.objects.count(), 0)

    def test_rotation_is_deterministic_for_a_fixed_pool_and_attempts_are_pinned(self):
        entries = []
        for order in (20, 10):
            item = DailyChallenge.objects.create(
                prompt=f"NON-SCIENTIFIC challenge {order}", is_active=True,
                sort_order=order,
            )
            correct = DailyChallengeChoice.objects.create(
                challenge=item, text="Correct", is_correct=True, is_active=True)
            DailyChallengeChoice.objects.create(
                challenge=item, text="Incorrect", is_correct=False, is_active=True)
            entries.append((item, correct))
        selected = today_challenge(date(2026, 11, 16))
        self.assertIsNotNone(selected)
        self.assertEqual(today_challenge(date(2026, 11, 16)).pk, selected.pk)
        matching = next(pair for pair in entries if pair[0].pk == selected.pk)
        historical = DailyChallengeAttempt.objects.create(
            user=self.normal, challenge=matching[0], selected_choice=matching[1],
            activity_date=date(2026, 11, 16), is_correct=True,
        )
        matching[0].is_active = False
        matching[0].save(update_fields=["is_active"])
        self.assertNotEqual(today_challenge(date(2026, 11, 16)).pk, selected.pk)
        historical.refresh_from_db()
        self.assertEqual(historical.challenge_id, selected.pk)
        self.assertEqual(historical.selected_choice_id, matching[1].pk)
