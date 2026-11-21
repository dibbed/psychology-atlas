"""P15 server-authoritative operational counts, not learner mastery."""
from django.test import TestCase, override_settings

from .models import StudyBlock, StudyPlan, StudySession, StudyActivity, RecommendationFeedback
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StudyOperationsSummaryTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.sign_in(self.owner)

    def test_status_counts_are_real_and_do_not_expose_private_user_data(self):
        base = (StudyPlan.objects.count(), StudyBlock.objects.count(),
                StudySession.objects.count(), StudyActivity.objects.count())
        response = self.admin.get(BASE + "study/overview/")
        self.assertEqual(response.status_code, 200, response.content[:350])
        data = response.json()
        self.assertEqual(data["scope"], "aggregate_operational_counts")
        self.assertEqual(data["plans"]["total"], base[0])
        self.assertEqual(data["blocks"]["total"], base[1])
        self.assertEqual(data["sessions"]["total"], base[2])
        self.assertEqual(data["activities"]["total"], base[3])
        self.assertEqual(data["feedback"]["total"], RecommendationFeedback.objects.count())
        self.assertNotIn("username", str(data).lower())
        self.assertNotIn("email", str(data).lower())
        self.assertNotIn("user_id", str(data).lower())
        self.assertNotIn("progress_percent", str(data))
        self.assertFalse(data["mastery_inferred_from_session_completion"])
        self.assertEqual((StudyPlan.objects.count(), StudyBlock.objects.count(),
                          StudySession.objects.count(), StudyActivity.objects.count()), base)

    def test_denied_permissions_and_query_injection(self):
        low = self.user("p15-no-study-scope",staff=True,caps=("cms_enter","cms_user_view"))
        self.assertEqual(self.sign_in(low).get(BASE+"study/overview/").status_code,403)
        self.assertEqual(self.admin.get(BASE+"study/overview/?user_id=1").status_code,400)
        self.assertEqual(self.post(self.admin,"study/overview/",{"status":"completed"}).status_code,405)
