"""P14 least-privilege user discovery; no private learning material in catalog."""
from django.test import TestCase, override_settings

from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CMSUserDiscoveryTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.admin=self.sign_in(self.owner)

    def test_user_catalog_search_is_bounded_and_does_not_reveal_sensitive_data(self):
        result=self.admin.get(BASE+"users/?q=normal&page=1&page_size=20")
        self.assertEqual(result.status_code,200,result.content[:350])
        self.assertGreaterEqual(result.json()["count"],1)
        row=next((r for r in result.json()["results"] if r["id"]==self.normal.pk),None)
        self.assertIsNotNone(row)
        self.assertEqual(row["username"],"normal")
        data=str(result.json()).lower()
        for secret in ("password","email","note","progress","access_token","session_key","totp"):
            self.assertNotIn(secret,data)
        self.assertEqual(self.admin.get(BASE+"users/?q="+"z"*202).status_code,400)
        self.assertEqual(self.admin.get(BASE+"users/?page_size=500").status_code,400)

    def test_object_detail_exposes_roles_only_to_role_viewer(self):
        detail=self.admin.get(BASE+f"users/{self.normal.pk}/")
        self.assertEqual(detail.status_code,200,detail.content[:350])
        self.assertIn("effective_permissions",detail.json())
        self.assertEqual(detail.json()["username"],"normal")
        self.assertEqual(self.admin.get(BASE+"users/987654321/").status_code,404)
        viewer=self.user("p14-only-viewer",staff=True,
            caps=("cms_enter","cms_user_view"))
        client=self.sign_in(viewer)
        response=client.get(BASE+f"users/{self.normal.pk}/")
        self.assertEqual(response.status_code,200,response.content[:250])
        self.assertNotIn("effective_permissions",response.json())
        self.assertNotIn("email",response.json())
        self.assertNotIn("last_login",response.json())

    def test_session_overview_requires_independent_revoke_sessions_capability(self):
        active = self.admin.get(BASE + f"sessions/?user_id={self.owner.pk}")
        self.assertEqual(active.status_code, 200, active.content[:300])
        self.assertGreaterEqual(active.json()["count"], 1)
        self.assertNotIn("django_session_id", str(active.json()))
        self.assertNotIn("step_up", str(active.json()))
        self.assertNotIn("token", str(active.json()).lower())
        viewer=self.user("p14-user-without-session-scope",staff=True,
            caps=("cms_enter","cms_user_view"))
        self.assertEqual(self.sign_in(viewer).get(
            BASE + f"sessions/?user_id={self.normal.pk}").status_code,403)

    def test_unauthorized_account_access_and_mutating_methods_fail_closed(self):
        staff=self.user("p14-no-user-scope",staff=True,caps=("cms_enter","cms_catalog"))
        client=self.sign_in(staff)
        self.assertEqual(client.get(BASE+"users/").status_code,403)
        self.assertEqual(client.get(BASE+f"users/{self.normal.pk}/").status_code,403)
        self.assertEqual(self.post(self.admin,f"users/{self.normal.pk}/",
            {"is_active":False}).status_code,405)
        self.normal.refresh_from_db()
        self.assertTrue(self.normal.is_active)
