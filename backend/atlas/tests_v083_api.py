"""Recommendation V2 HTTP and feedback regression tests."""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .learning import get_recommendations
from .models import (
    Category, Concept, Disorder, RecommendationFeedback, UserConceptProgress,
    UserProgress,
)
from .recommendations_v2 import fingerprint


class RecommendationV2ApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user("rec-owner", password="StrongPass123!")
        self.other = User.objects.create_user("rec-other", password="StrongPass123!")
        self.category = Category.objects.create(slug="rec-category", name_en="Category")
        self.disorder = Disorder.objects.create(
            category=self.category, slug="rec-disorder", name_en="Disorder", is_active=True
        )
        self.concept = Concept.objects.create(
            slug="rec-concept", name_en="Concept", is_active=True
        )
        UserConceptProgress.objects.create(
            user=self.owner, concept=self.concept, progress_percent=25
        )
        UserProgress.objects.create(
            user=self.owner, disorder=self.disorder, progress_percent=30
        )
        self.client.force_authenticate(self.owner)

    def _items(self):
        response = self.client.get("/api/study/recommendations/")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["items"]

    def _feedback(self, key, value="helpful", event_id=None):
        return self.client.post(
            f"/api/study/recommendations/{key}/feedback/",
            {"value": value, "client_event_id": str(event_id or uuid.uuid4())},
            format="json",
        )

    def test_v1_overview_and_dashboard_recommendations_remain_unchanged(self):
        expected = get_recommendations(self.owner)
        overview = self.client.get("/api/study/overview/")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(overview.data["recommendations"], expected)
        self.assertEqual(dashboard.data["recommendations"], expected)
        self.assertTrue(all(set(row) == {"type", "title", "reason", "href", "priority"} for row in expected))

    def test_stable_keys_order_and_read_has_no_side_effects(self):
        before = (
            UserConceptProgress.objects.get(user=self.owner).progress_percent,
            UserProgress.objects.get(user=self.owner).progress_percent,
        )
        first = self._items()
        second = self._items()
        self.assertEqual([row["key"] for row in first], [row["key"] for row in second])
        self.assertEqual([row["order"] for row in first], list(range(1, len(first) + 1)))
        self.assertEqual(RecommendationFeedback.objects.count(), 0)
        self.assertEqual(before, (
            UserConceptProgress.objects.get(user=self.owner).progress_percent,
            UserProgress.objects.get(user=self.owner).progress_percent,
        ))
        self.assertEqual(
            fingerprint("quiz_retry", "quiz", 42, "recent_incorrect_quiz_answers", "attempt:91"),
            "r2_abd11712d8ebc0fe25cdc9be158dc3e9a3688254150b80a01443633344eafcd2",
        )

    def test_feedback_replay_change_and_temporary_suppression(self):
        key = next(item["key"] for item in self._items() if item["type"] == "concept_review")
        event_id = uuid.uuid4()
        first = self._feedback(key, "dismissed", event_id)
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(RecommendationFeedback.objects.count(), 1)
        second = self._feedback(key, "dismissed", event_id)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data, first.data)
        self.assertEqual(RecommendationFeedback.objects.count(), 1)
        self.assertNotIn(key, [item["key"] for item in self._items()])
        conflict = self._feedback(key, "helpful", event_id)
        self.assertEqual((conflict.status_code, conflict.data["code"]), (409, "recommendation_feedback_conflict"))
        same_value = self._feedback(key, "dismissed")
        self.assertEqual(same_value.status_code, 200)
        self.assertEqual(RecommendationFeedback.objects.count(), 1)
        helpful = self._feedback(key, "helpful")
        self.assertEqual(helpful.status_code, 200)
        self.assertEqual(RecommendationFeedback.objects.count(), 2)
        item = next(item for item in self._items() if item["key"] == key)
        self.assertEqual(item["feedback"]["value"], "helpful")
        self.assertIsNone(item["feedback"]["suppressed_until"])
        unhelpful = self._feedback(key, "not_helpful")
        self.assertEqual(unhelpful.status_code, 200)
        self.assertEqual(RecommendationFeedback.objects.count(), 3)
        self.assertEqual(next(item for item in self._items() if item["key"] == key)["feedback"]["value"], "not_helpful")
        self.assertEqual(UserConceptProgress.objects.get(user=self.owner).progress_percent, 25)

    def test_expired_dismissal_is_visible_and_retry_survives_ineligible_target(self):
        key = next(item["key"] for item in self._items() if item["type"] == "concept_review")
        event_id = uuid.uuid4()
        response = self._feedback(key, "dismissed", event_id)
        self.assertEqual(response.status_code, 200)
        row = RecommendationFeedback.objects.get(user=self.owner, recommendation_key=key)
        RecommendationFeedback.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(days=9),
            suppressed_until=timezone.now() - timedelta(days=2),
        )
        item = next(item for item in self._items() if item["key"] == key)
        self.assertEqual(item["feedback"], {"value": None, "suppressed_until": None})
        self.concept.is_active = False
        self.concept.save(update_fields=["is_active"])
        replay = self._feedback(key, "dismissed", event_id)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(RecommendationFeedback.objects.count(), 1)
        self.assertEqual(self._feedback(key, "helpful").status_code, 404)

    def test_foreign_feedback_and_recommendations_are_invisible(self):
        foreign_concept = Concept.objects.create(
            slug="foreign-concept", name_en="Foreign Concept", is_active=True
        )
        UserConceptProgress.objects.create(
            user=self.other, concept=foreign_concept, progress_percent=5
        )
        self.client.force_authenticate(self.other)
        key = next(item["key"] for item in self._items() if item["target"]["id"] == foreign_concept.id)
        self.assertEqual(self._feedback(key).status_code, 200)
        self.client.force_authenticate(self.owner)
        self.assertNotIn(key, [item["key"] for item in self._items()])
        response = self._feedback(key)
        self.assertEqual((response.status_code, response.data["code"]), (404, "recommendation_not_found"))
        self.assertEqual(RecommendationFeedback.objects.filter(user=self.owner).count(), 0)

    def test_same_key_for_two_owners_never_leaks_feedback_state(self):
        UserConceptProgress.objects.create(
            user=self.other, concept=self.concept, progress_percent=25
        )
        owner_key = next(item["key"] for item in self._items() if item["target"]["id"] == self.concept.id)
        self.client.force_authenticate(self.other)
        other_key = next(item["key"] for item in self._items() if item["target"]["id"] == self.concept.id)
        self.assertEqual(owner_key, other_key)
        self.assertEqual(self._feedback(other_key, "dismissed").status_code, 200)
        self.client.force_authenticate(self.owner)
        owner_item = next(item for item in self._items() if item["key"] == owner_key)
        self.assertEqual(owner_item["feedback"], {"value": None, "suppressed_until": None})
        self.assertEqual(RecommendationFeedback.objects.filter(user=self.owner).count(), 0)

    def test_all_current_recommendations_dismissed_show_bounded_empty_state(self):
        original = self._items()
        self.assertGreater(len(original), 0)
        for item in original:
            response = self._feedback(item["key"], "dismissed")
            self.assertEqual(response.status_code, 200, response.data)
        listing = self.client.get("/api/study/recommendations/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["items"], [])
        self.assertEqual(listing.data["returned_count"], 0)
        self.assertEqual(listing.data["suppressed_count"], len(original))
        self.assertEqual(RecommendationFeedback.objects.filter(user=self.owner).count(), len(original))

    def test_invalid_queries_and_feedback_have_stable_errors(self):
        leading_zero = self.client.get("/api/study/recommendations/?limit=01")
        self.assertEqual((leading_zero.status_code, leading_zero.data["returned_count"]), (200, 1))
        for query in ("?limit=0", "?limit=21", "?limit=-1", "?limit= 2", "?limit=2.0", "?limit=true", "?limit=" + "9" * 5000, "?unexpected=1", "?limit=2&limit=3"):
            response = self.client.get("/api/study/recommendations/" + query)
            self.assertEqual((response.status_code, response.data["code"]), (400, "recommendation_invalid_query"), query)
        key = self._items()[0]["key"]
        bad = (
            {"value": "helpful"},
            {"value": "mastered", "client_event_id": str(uuid.uuid4())},
            {"value": "helpful", "client_event_id": "bad"},
            {"value": "helpful", "client_event_id": str(uuid.uuid4()), "user": self.other.pk},
        )
        for payload in bad:
            response = self.client.post(f"/api/study/recommendations/{key}/feedback/", payload, format="json")
            self.assertEqual((response.status_code, response.data["code"]), (400, "recommendation_feedback_invalid"))
        response = self._feedback("r2_" + "0" * 64)
        self.assertEqual((response.status_code, response.data["code"]), (404, "recommendation_not_found"))
        oversized = self.client.post(
            f"/api/study/recommendations/{key}/feedback/",
            data=json.dumps({"value": "helpful", "client_event_id": str(uuid.uuid4()), "padding": "x" * 1024}),
            content_type="application/json",
        )
        self.assertEqual((oversized.status_code, oversized.data["code"]), (400, "recommendation_feedback_invalid"))

    def test_daily_event_cap_does_not_charge_idempotent_replay(self):
        item = next(item for item in self._items() if item["type"] == "concept_review")
        now = timezone.now()
        existing_id = uuid.uuid4()
        for index in range(100):
            RecommendationFeedback.objects.create(
                user=self.owner,
                recommendation_key=item["key"],
                recommendation_type=item["type"],
                target_type=item["target"]["type"],
                target_id=item["target"]["id"],
                reason_code=item["reason_codes"][0],
                context_ref="current_progress",
                value="helpful",
                client_event_id=existing_id if index == 0 else uuid.uuid4(),
                created_at=now,
            )
        replay = self._feedback(item["key"], "helpful", existing_id)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(RecommendationFeedback.objects.count(), 100)
        response = self._feedback(item["key"], "not_helpful")
        self.assertEqual((response.status_code, response.data["code"]), (429, "recommendation_feedback_limit"))

    def test_owner_authentication_required(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/study/recommendations/").status_code, 401)
        self.assertEqual(self._feedback("r2_" + "0" * 64).status_code, 401)


class RecommendationV2ConcurrentFeedbackTests(TransactionTestCase):
    def test_concurrent_double_click_creates_one_current_event(self):
        user = User.objects.create_user("rec-concurrent", password="StrongPass123!")
        concept = Concept.objects.create(
            slug="rec-concurrent-concept", name_en="Concurrent", is_active=True
        )
        UserConceptProgress.objects.create(user=user, concept=concept, progress_percent=20)
        client = APIClient()
        client.force_authenticate(user)
        response = client.get("/api/study/recommendations/")
        self.assertEqual(response.status_code, 200, response.data)
        key = next(item["key"] for item in response.data["items"] if item["type"] == "concept_review")

        def submit():
            close_old_connections()
            local_client = APIClient()
            local_client.force_authenticate(user)
            result = local_client.post(
                f"/api/study/recommendations/{key}/feedback/",
                {"value": "dismissed", "client_event_id": str(uuid.uuid4())},
                format="json",
            )
            close_old_connections()
            return result.status_code, result.data

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual([status for status, _ in results], [200, 200], results)
        self.assertEqual(RecommendationFeedback.objects.filter(user=user).count(), 1)
