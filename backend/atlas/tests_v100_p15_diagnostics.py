"""Purpose-bound diagnostics use the learner's current recommendation assembly."""
import uuid
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .cms_models import AdminAuditEvent
from .models import RecommendationFeedback, StudyPlan, StudyPlanAvailability, UserProgress, UserStudySettings
from .recommendation_views import assemble_recommendations
from .tests_v100_p01 import BASE
from .tests_v100_p14_privacy import PrivacyFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StudyDiagnosticsTests(PrivacyFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.body = {**self.body, "scope": "recommendations"}
        UserProgress.objects.create(user=self.normal, disorder=self.disorder, progress_percent=30)

    def read(self, body=None):
        body = body or self.body
        self.step_up(self.client, self.owner, "privacy_read", self.normal.pk, body)
        return self.post(self.client, self.route, body)

    def test_recommendations_match_real_owner_service_and_feedback_without_writes(self):
        learner = APIClient()
        learner.force_authenticate(self.normal)
        now = timezone.now()
        with patch("django.utils.timezone.now", return_value=now):
            expected = learner.get("/api/study/recommendations/").json()
            self.assertTrue(expected["items"])
            response = self.read()
            self.assertEqual(response.status_code, 200, response.content[:300])
            self.assertEqual(response.json()["results"], [expected])
            self.assertEqual(expected["version"], "v2")
            key = expected["items"][0]["key"]
            dismissed = learner.post(f"/api/study/recommendations/{key}/feedback/",
                {"value": "dismissed", "client_event_id": str(uuid.uuid4())}, format="json")
            self.assertEqual(dismissed.status_code, 200, dismissed.content[:300])
            before = list(RecommendationFeedback.objects.values())
            expected = assemble_recommendations(self.normal, now)
            response = self.read()
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()["results"], [expected])
        self.assertEqual(expected["suppressed_count"], 1)
        self.assertEqual(list(RecommendationFeedback.objects.values()), before)
        self.assertFalse(UserStudySettings.objects.exists())
        self.assertEqual(UserProgress.objects.get(user=self.normal).progress_percent, 30)
        self.assertEqual(AdminAuditEvent.objects.filter(action="privacy.read.recommendations").count(), 2)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_recommendations_require_private_study_scope_and_fresh_subject_bound_proof(self):
        response = self.post(self.client, self.route, self.body)
        self.assertEqual(response.status_code, 403, response.content[:300])
        self.step_up(self.client, self.owner, "privacy_read", self.normal.pk, self.body)
        response = self.post(self.client, f"users/{self.scoped.pk}/privacy/read/", self.body)
        self.assertEqual(response.status_code, 403, response.content[:300])
        self.client = self.sign_in(self.reader)
        self.authorize()
        response = self.post(self.client, self.route, self.body)
        self.assertEqual(response.status_code, 403, response.content[:300])
        schema = self.client.get(BASE + "users/privacy/schema/").json()
        self.assertNotIn("recommendations", [row["key"] for row in schema["scopes"]])
        self.assertFalse(AdminAuditEvent.objects.filter(action="privacy.read.recommendations").exists())

    def test_recommendation_failure_rolls_back_audit_and_mfa_and_rejects_extra_pages(self):
        from .cms_models import AdminSession
        self.step_up(self.client, self.owner, "privacy_read", self.normal.pk, self.body)
        session_id = self.client.session["cms_session_id"]
        proof = AdminSession.objects.get(pk=session_id).step_up
        with patch("atlas.recommendation_views.assemble_recommendations", side_effect=DatabaseError("synthetic outage")):
            response = self.post(self.client, self.route, self.body)
        self.assertEqual(response.status_code, 503, response.content[:300])
        self.assertEqual(AdminSession.objects.get(pk=session_id).step_up, proof)
        self.assertFalse(AdminAuditEvent.objects.filter(action="privacy.read.recommendations").exists())
        response = self.post(self.client, self.route, {**self.body, "page": 2})
        self.assertEqual(response.status_code, 400, response.content[:300])

    def test_availability_is_bounded_and_owned_by_the_selected_subject(self):
        plan = StudyPlan.objects.create(user=self.normal, name="Subject plan")
        other = StudyPlan.objects.create(user=self.scoped, name="Foreign plan")
        availability = StudyPlanAvailability.objects.create(plan=plan, weekday=2, available_minutes=35)
        StudyPlanAvailability.objects.create(plan=other, weekday=5, available_minutes=90)
        response = self.read({**self.body, "scope": "study_availability"})
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["id"], availability.pk)
        self.assertEqual(response.json()["results"][0]["available_minutes"], 35)
