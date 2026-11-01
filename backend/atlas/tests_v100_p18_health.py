"""P18 owner-only read-only health. Never claim a backup adapter exists."""
from django.test import TestCase, override_settings

from .cms_job_models import AdminJob, AdminArtifact
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OwnerHealthTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client=self.sign_in(self.owner)

    def test_health_shows_real_database_and_job_counts_without_credentials(self):
        response=self.owner_client.get(BASE+"operations/health/")
        self.assertEqual(response.status_code,200,response.content[:350])
        data=response.json()
        self.assertEqual(data["scope"],"owner_operational_metadata")
        self.assertEqual(data["database"]["connection"],"ok")
        self.assertIn(data["database"]["vendor"],("sqlite","postgresql"))
        self.assertEqual(data["jobs"]["total"],AdminJob.objects.count())
        self.assertEqual(data["artifacts"]["total"],AdminArtifact.objects.count())
        self.assertEqual(data["backup"]["state"],"unavailable")
        self.assertNotIn("healthy",str(data["backup"]).lower())
        data_repr=str(data).lower()
        for sensitive in ("database_url","secret_key","password","dsn","storage_key","email"):
            self.assertNotIn(sensitive,data_repr)
        self.assertFalse(data["worker"]["alive_confirmed"])

    def test_non_owner_denied_and_no_runtime_mutations(self):
        staff=self.user("p18-not-owner",staff=True,caps=(
            "cms_enter","cms_dashboard","cms_user_view"))
        client=self.sign_in(staff)
        self.assertEqual(client.get(BASE+"operations/health/").status_code,403)
        self.assertEqual(self.owner_client.get(BASE+"operations/health/?cmd=sql").status_code,400)
        self.assertEqual(self.post(self.owner_client,"operations/health/",{
            "restore":"anything",
        }).status_code,405)
