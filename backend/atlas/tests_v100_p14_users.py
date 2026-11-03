"""P14 least-privilege user discovery; no private learning material in catalog."""
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature

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

    def test_role_contract_distinguishes_direct_and_inherited_permissions(self):
        group = Group.objects.create(name="Synthetic inherited learning")
        group.permissions.add(Permission.objects.get(content_type__app_label="atlas",
            content_type__model="rolepolicy", codename="cms_learning_view"))
        self.scoped.groups.add(group)
        response = self.admin.get(BASE + f"roles/users/{self.scoped.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cms_brain_view", response.json().get("direct_permissions", []))
        self.assertNotIn("cms_learning_view", response.json()["direct_permissions"])
        self.assertIn("cms_learning_view", response.json()["permissions"])
        self.assertEqual(response.headers["ETag"], self.etag())

    def test_delegated_editor_preserves_unchanged_higher_direct_grants(self):
        editor = self.user("p14-delegate", staff=True, caps=("cms_enter", "cms_roles_view",
            "cms_roles_edit", "cms_delegate_learning_view"))
        client = self.sign_in(editor)
        before = self.admin.get(BASE + f"roles/users/{self.scoped.pk}/").json()
        snapshot = client.get(BASE + f"roles/users/{self.scoped.pk}/")
        direct = snapshot.json().get("direct_permissions", [])
        self.assertIn("cms_brain_view", direct)
        response = self.post(client, f"roles/users/{self.scoped.pk}/",
            {"permissions": direct + ["cms_learning_view"]}, etag=snapshot.headers["ETag"])
        self.assertEqual(response.status_code, 200, response.content[:300])
        after = self.admin.get(BASE + f"roles/users/{self.scoped.pk}/").json()
        self.assertEqual(set(after["direct_permissions"]), set(before["direct_permissions"]) | {"cms_learning_view"})
        denied = self.post(client, f"roles/users/{self.scoped.pk}/",
            {"permissions": after["direct_permissions"] + ["cms_owner"]}, etag=self.etag())
        self.assertEqual(denied.status_code, 403)

    def test_sessions_expose_consistent_policy_tag_and_reject_stale_revocation(self):
        from .cms_models import AdminSession
        listing = self.admin.get(BASE + f"sessions/?user_id={self.owner.pk}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.headers.get("ETag"), self.etag())
        session_id = listing.json()["results"][0]["id"]
        changed = self.post(self.admin, f"roles/users/{self.scoped.pk}/",
            {"permissions": ["cms_enter", "cms_catalog", "cms_brain_view", "cms_learning_view"]}, etag=self.etag())
        self.assertEqual(changed.status_code, 200)
        stale = self.post(self.admin, f"sessions/{session_id}/revoke/", etag=listing.headers["ETag"])
        self.assertEqual(stale.status_code, 412)
        self.assertIsNone(AdminSession.objects.get(pk=session_id).revoked_at)

    def test_role_detail_queries_and_session_target_are_closed_and_bounded(self):
        for route in ("roles/permissions/?extra=1", f"roles/users/{self.scoped.pk}/?extra=1"):
            self.assertEqual(self.admin.get(BASE + route).status_code, 400, route)
        for query in ("user_id=0", "user_id=9223372036854775808", "user_id=1&user_id=2"):
            self.assertEqual(self.admin.get(BASE + "sessions/?" + query).status_code, 400, query)


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CMSAccessSnapshotConcurrencyTests(SecurityFixture, TransactionTestCase):
    def test_role_snapshot_holds_policy_until_body_and_etag_are_bound(self):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        from threading import Event
        from django.db import close_old_connections, connection, connections
        from django.test import Client
        from .cms_models import RolePolicy
        from .cms_policy import mutate_role
        admin = self.sign_in(self.owner)
        sid, version = admin.session["cms_session_id"], RolePolicy.objects.get(pk=1).version
        read_paused, release, writer_started = Event(), Event(), Event()
        target = self.scoped.pk

        def read():
            close_old_connections()
            client = Client(enforce_csrf_checks=True)
            client.cookies = admin.cookies.copy()

            def observe(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if (not read_paused.is_set() and "auth_user_user_permissions" in sql
                        and "auth_permission" in sql and target in (params or ())):
                    read_paused.set()
                    if not release.wait(10):
                        raise AssertionError("Synthetic role snapshot wait timed out")
                return result

            try:
                with connection.execute_wrapper(observe):
                    response = client.get(BASE + f"roles/users/{target}/")
                return response.status_code, response.json(), response.headers.get("ETag")
            finally:
                connections.close_all()

        def write():
            close_old_connections()

            def observe(execute, sql, params, many, context):
                if "pg_advisory_xact_lock" in sql:
                    writer_started.set()
                return execute(sql, params, many, context)

            try:
                with connection.execute_wrapper(observe):
                    return mutate_role(self.owner.pk, "user", target, {"permissions":
                        ["cms_enter", "cms_catalog", "cms_brain_view", "cms_source_view"]}, version, sid)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(read)
            try:
                self.assertTrue(read_paused.wait(5))
                writer = pool.submit(write)
                self.assertTrue(writer_started.wait(5))
                with self.assertRaises(TimeoutError):
                    writer.result(timeout=1)
            finally:
                release.set()
            status, body, etag = reader.result(timeout=10)
            self.assertEqual(writer.result(timeout=10), version + 1)
        self.assertEqual(status, 200)
        self.assertEqual(etag, f'"{version}"')
        self.assertNotIn("cms_source_view", body["direct_permissions"])
        self.assertEqual(RolePolicy.objects.get(pk=1).version, version + 1)
