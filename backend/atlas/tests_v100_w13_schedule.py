"""W13-02 existing server-localdate rotation, not a second scheduling engine."""
from datetime import date, datetime, timezone as utc_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from .learning import today_challenge
from .cms_practice_editor import _result
from .models import DailyChallenge, DailyChallengeChoice, DailyChallengeAttempt
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
