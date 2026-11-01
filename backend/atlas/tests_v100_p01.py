"""P01 uses real Django sessions, CSRF and package OTP; no force_authenticate."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.core.cache import cache
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework_simplejwt.tokens import RefreshToken

from .cms_capabilities import CAPABILITIES, KNOWN_PERMISSIONS, READY_CAPABILITIES
from .cms_models import AccountSecurityState, AdminLoginThrottle, AdminAuditEvent, AdminSession, RolePolicy
from .cms_policy import CMSFailure, effective_permissions, mutate_role, owners, policy_lock, require
from .cms_sessions import binding, generation, revoke_account, verify_mfa

BASE = "/api/admin/"
PASSWORD = "Synthetic-admin-test-only-123!"


class SecurityFixture:
    def setUp(self):
        super().setUp()
        cache.clear()
        RolePolicy.objects.get_or_create(pk=1)
        self.owner = self.user("owner", staff=True, caps=["cms_owner"])
        self.scoped = self.user("scoped", staff=True, caps=["cms_enter", "cms_catalog", "cms_brain_view"])
        self.staff = self.user("staff", staff=True)
        self.normal = self.user("normal")

    def user(self, name, staff=False, caps=()):
        user = User.objects.create_user(name, password=PASSWORD, is_staff=staff)
        self.grant(user, *caps)
        return user

    def grant(self, user, *caps):
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="atlas", content_type__model="rolepolicy", codename__in=caps))

    def csrf(self, client):
        response = client.get(BASE + "auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return response.json()["csrf_token"]

    def post(self, client, path, data=None, etag=None, **headers):
        headers["HTTP_X_CSRFTOKEN"] = self.csrf(client)
        if etag is not None:
            headers["HTTP_IF_MATCH"] = etag
        return client.post(BASE + path, json.dumps(data or {}), content_type="application/json", **headers)

    def backup(self, user):
        device, _ = StaticDevice.objects.get_or_create(user=user, name="backup", confirmed=True)
        return StaticToken.objects.create(device=device, token=StaticToken.random_token()).token

    def sign_in(self, user, client=None):
        client = client or Client(enforce_csrf_checks=True)
        device, _ = TOTPDevice.objects.get_or_create(user=user, name="default", confirmed=True)
        response = self.post(client, "auth/login/", {"username": user.username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.post(client, "auth/verify/", {"method": "recovery", "token": self.backup(user)})
        self.assertEqual(response.status_code, 200, response.content)
        return client

    def step_up(self, client, user, action, target_id, data):
        response = self.post(client, "auth/step-up/", {"method": "recovery", "token": self.backup(user), "action": action, "target_id": target_id, "payload": data})
        self.assertEqual(response.status_code, 200, response.content)

    def etag(self):
        return '"%s"' % RolePolicy.objects.get(pk=1).version

    def code(self, response, code, status=403):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["code"], code)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdminAuthenticationTests(SecurityFixture, TestCase):
    def test_login_csrf_and_origin_required_even_anonymous(self):
        client = Client(enforce_csrf_checks=True)
        data = {"username": self.owner.username, "password": PASSWORD}
        self.code(client.post(BASE + "auth/login/", data), "CSRF_FAILED")
        self.code(self.post(client, "auth/login/", data, HTTP_ORIGIN="https://foreign.invalid"), "CSRF_FAILED")
        self.assertEqual(AdminSession.objects.count(), 0)

    def test_normal_staff_disabled_and_unknown_have_same_login_failure(self):
        self.owner.is_active = False
        self.owner.save(update_fields=("is_active",))
        for user in (self.normal, self.staff, self.owner):
            self.code(self.post(Client(enforce_csrf_checks=True), "auth/login/", {"username": user.username, "password": PASSWORD}), "LOGIN_FAILED")
        self.code(self.post(Client(enforce_csrf_checks=True), "auth/login/", {"username": "missing", "password": PASSWORD}), "LOGIN_FAILED")

    def test_password_only_is_not_cms_ready(self):
        client = Client(enforce_csrf_checks=True)
        self.post(client, "auth/login/", {"username": self.owner.username, "password": PASSWORD})
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        self.code(self.post(client, "auth/complete/"), "MFA_REQUIRED")
        self.code(self.post(client, "auth/verify/", {"token": "123456"}), "MFA_ENROLLMENT_REQUIRED")

    def test_password_relogin_clears_previous_mfa_marker(self):
        client = self.sign_in(self.owner)
        old_key = client.session.session_key
        old_id = client.session["cms_session_id"]
        self.post(client, "auth/login/", {"username": self.owner.username, "password": PASSWORD})
        self.assertNotEqual(client.session.session_key, old_key)
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        self.assertIsNotNone(AdminSession.objects.get(pk=old_id).revoked_at)

    def test_pending_auth_cannot_survive_account_revocation(self):
        client = Client(enforce_csrf_checks=True)
        self.post(client, "auth/login/", {"username": self.owner.username, "password": PASSWORD})
        with policy_lock():
            revoke_account(self.owner)
        self.code(self.post(client, "auth/verify/", {"method": "recovery", "token": self.backup(self.owner)}), "UNAUTHENTICATED")
        self.code(client.get("/account/two_factor/setup/"), "UNAUTHENTICATED")

    def test_revoke_between_mfa_verification_and_session_creation_fails_closed(self):
        client = Client(enforce_csrf_checks=True)
        self.post(client, "auth/login/", {"username": self.owner.username, "password": PASSWORD})
        TOTPDevice.objects.create(user=self.owner, name="default")
        real_verify = verify_mfa
        def revoke_after_verification(*args, **kwargs):
            device = real_verify(*args, **kwargs)
            with policy_lock():
                revoke_account(self.owner)
            return device
        with patch("atlas.cms_views.verify_mfa", side_effect=revoke_after_verification):
            self.code(self.post(client, "auth/verify/", {"method": "recovery", "token": self.backup(self.owner)}), "UNAUTHENTICATED")
        self.assertFalse(AdminSession.objects.exists())

    def test_raw_admin_session_and_owner_jwt_cannot_bypass_marker(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        client.logout()
        token = RefreshToken.for_user(self.owner)
        self.code(client.get(BASE + "me/", HTTP_AUTHORIZATION=f"Bearer {token.access_token}"), "UNAUTHENTICATED")

    def test_real_totp_rotation_replay_and_logout(self):
        client = Client(enforce_csrf_checks=True)
        device = TOTPDevice.objects.create(user=self.owner, name="default")
        self.post(client, "auth/login/", {"username": self.owner.username, "password": PASSWORD})
        before = client.session.session_key
        token = str(totp(device.bin_key)).zfill(device.digits)
        response = self.post(client, "auth/verify/", {"token": token})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotEqual(before, client.session.session_key)
        response = client.get(BASE + "me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()["capabilities"]), CAPABILITIES)
        self.assertEqual(set(response.json()["ready_capabilities"]), READY_CAPABILITIES)
        self.assertFalse(response.json()["security"]["production_ready"])
        self.assertNotIn(client.session.session_key, response.content.decode())
        with self.assertRaises(CMSFailure):
            verify_mfa(self.owner, token)
        self.code(client.post(BASE + "auth/logout/", {}), "CSRF_FAILED")
        self.assertEqual(self.post(client, "auth/logout/").status_code, 200)
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        self.assertIsNotNone(AdminSession.objects.get().revoked_at)

    def test_otp_and_recovery_are_one_time(self):
        TOTPDevice.objects.create(user=self.owner, name="default")
        token = self.backup(self.owner)
        device = verify_mfa(self.owner, token, "recovery")
        self.assertEqual(device.user_id, self.owner.pk)
        self.assertFalse(StaticToken.objects.filter(token=token).exists())
        with self.assertRaises(CMSFailure):
            verify_mfa(self.owner, token, "recovery")

    def test_idle_absolute_expiry_and_disabled_account(self):
        for field, value in (("last_seen", timezone.now() - timedelta(minutes=31)), ("expires_at", timezone.now() - timedelta(seconds=1))):
            client = self.sign_in(self.owner)
            row = AdminSession.objects.get(pk=client.session["cms_session_id"])
            AdminSession.objects.filter(pk=row.pk).update(**{field: value})
            self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        client = self.sign_in(self.owner)
        self.owner.is_staff = False
        self.owner.save(update_fields=("is_staff",))
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")

    def test_revoked_permissions_rechecked_without_cached_instance(self):
        client = self.sign_in(self.scoped)
        self.assertEqual(client.get(BASE + "catalog/").status_code, 200)
        self.scoped.has_perm("atlas.cms_catalog")
        self.scoped.user_permissions.remove(Permission.objects.get(codename="cms_catalog", content_type__model="rolepolicy"))
        self.code(client.get(BASE + "catalog/"), "PERMISSION_DENIED")
        self.scoped.user_permissions.clear()
        self.code(client.get(BASE + "me/"), "PERMISSION_DENIED")

    def test_unknown_capability_and_role_name_never_authorize(self):
        Group.objects.get_or_create(name="Owner")[0].user_set.add(self.staff)
        self.assertEqual(effective_permissions(self.staff), set())
        with self.assertRaises(CMSFailure):
            require(self.owner, "cms_new_unregistered_action")
        from .cms_views import AdminAPIView
        from rest_framework.test import APIRequestFactory
        response = AdminAPIView.as_view()(APIRequestFactory().get("/api/admin/future/"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "UNAUTHENTICATED")

    def test_shared_database_throttle_and_time_window(self):
        for _ in range(5):
            self.code(self.post(Client(enforce_csrf_checks=True), "auth/login/", {"username": "wrong", "password": PASSWORD}), "LOGIN_FAILED")
        self.code(self.post(Client(enforce_csrf_checks=True), "auth/login/", {"username": self.owner.username, "password": PASSWORD}), "LOGIN_THROTTLED", 429)
        AdminLoginThrottle.objects.update(window_start=timezone.now() - timedelta(minutes=6))
        self.assertEqual(self.sign_in(self.owner).get(BASE + "me/").status_code, 200)

    def test_mfa_enrollment_wizard_bridge_and_recovery_route(self):
        client = Client(enforce_csrf_checks=True)
        self.post(client, "auth/login/", {"username": self.owner.username, "password": PASSWORD})
        response = client.get("/account/two_factor/setup/")
        self.assertEqual(response.status_code, 200)
        from .cms_integration import CMSSetupView
        from django.urls import resolve
        self.assertIs(resolve("/account/two_factor/setup/").func.view_class, CMSSetupView)
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        self.assertEqual(client.get("/account/two_factor/disable/").status_code, 403)
        client = self.sign_in(self.owner)
        self.assertEqual(client.get("/account/two_factor/backup/tokens/").status_code, 200)
        response = client.post("/account/two_factor/backup/tokens/", {})
        self.code(response, "CSRF_FAILED")

    def test_real_enrollment_wizard_complete_bridge_and_backup_regeneration(self):
        client = Client(enforce_csrf_checks=True)
        self.post(client, "auth/login/", {"username": self.owner.username, "password": PASSWORD})
        url = "/account/two_factor/setup/"
        response = client.get(url)
        wizard = response.context["wizard"]
        prefix = wizard["management_form"].prefix
        def wizard_post(step, fields):
            return client.post(url, {prefix + "-current_step": step, **fields}, HTTP_X_CSRFTOKEN=self.csrf(client))
        response = wizard_post("welcome", {})
        current = response.context["wizard"]["steps"].current
        if current == "method":
            response = wizard_post("method", {"method-method": "generator"})
        self.assertEqual(response.context["wizard"]["steps"].current, "generator")
        form = response.context["wizard"]["form"]
        token = str(totp(form.bin_key)).zfill(form.digits)
        response = wizard_post("generator", {"generator-token": token})
        self.assertEqual(response.status_code, 302, response.content)
        self.assertTrue(TOTPDevice.objects.filter(user=self.owner, confirmed=True).exists())
        with self.assertRaises(CMSFailure):
            verify_mfa(self.owner, token)
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        self.assertEqual(self.post(client, "auth/complete/").status_code, 200)
        self.assertEqual(client.get(BASE + "me/").status_code, 200)
        backup_url = "/account/two_factor/backup/tokens/"
        self.code(client.post(backup_url, {}, HTTP_X_CSRFTOKEN=self.csrf(client)), "STEP_UP_REQUIRED")
        self.step_up(client, self.owner, "regenerate_recovery", self.owner.pk, {})
        generated = client.post(backup_url, {}, HTTP_X_CSRFTOKEN=self.csrf(client))
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(StaticToken.objects.filter(device__user=self.owner).count(), 10)
        token = StaticToken.objects.filter(device__user=self.owner).first().token
        self.assertIn(token, generated.content.decode())
        self.assertNotIn(token, client.get(backup_url).content.decode())
        self.code(client.post(backup_url, {}, HTTP_X_CSRFTOKEN=self.csrf(client)), "STEP_UP_REQUIRED")
        row = AdminSession.objects.get(pk=client.session["cms_session_id"])
        AdminSession.objects.filter(pk=row.pk).update(last_seen=timezone.now() - timedelta(minutes=31))
        self.code(client.get(backup_url), "UNAUTHENTICATED")

    def test_mfa_revoke_and_offline_recovery(self):
        client = self.sign_in(self.owner)
        self.step_up(client, self.owner, "revoke_mfa", self.owner.pk, {})
        response = self.post(client, "auth/mfa/revoke/", etag=self.etag())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(generation(self.owner.pk), 1)
        self.assertFalse(TOTPDevice.objects.filter(user=self.owner).exists())
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        client = self.sign_in(self.owner)
        call_command("cms_recover_owner", user_id=self.owner.pk, reason="synthetic rehearsal", identity_verified=True, stdout=StringIO())
        self.code(client.get(BASE + "me/"), "UNAUTHENTICATED")
        self.assertEqual(owners().count(), 1)
        with self.assertRaises(CommandError):
            call_command("cms_recover_owner", user_id=self.normal.pk, reason="test", identity_verified=True, stdout=StringIO())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RoleAndScopeTests(SecurityFixture, TestCase):
    def test_every_registered_privileged_route_denies_anonymous_normal_and_staff(self):
        get_paths = ["me/", "catalog/", "roles/permissions/", "roles/groups/", "roles/groups/999/", f"roles/users/{self.owner.pk}/", "sessions/"]
        post_paths = ["auth/step-up/", "auth/mfa/revoke/", "roles/groups/", "roles/groups/999/", "roles/groups/999/delete/",
            f"roles/users/{self.owner.pk}/", f"sessions/{uuid.uuid4()}/revoke/", f"users/{self.owner.pk}/revoke-sessions/"]
        for user in (None, self.normal, self.staff):
            client = Client(enforce_csrf_checks=True)
            if user:
                client.force_login(user)
            for path in get_paths:
                with self.subTest(user=user, path=path):
                    self.assertEqual(client.get(BASE + path).status_code, 403)
            for path in post_paths:
                with self.subTest(user=user, path=path):
                    self.assertEqual(self.post(client, path, etag=self.etag()).status_code, 403)

    def test_scoped_privileged_mutations_cannot_use_owner_paths(self):
        client = self.sign_in(self.scoped)
        for path, data in (("roles/groups/", {"name": "forged", "permissions": ["cms_owner"]}),
            (f"roles/users/{self.owner.pk}/", {"permissions": []}),
            (f"users/{self.owner.pk}/revoke-sessions/", {})):
            self.code(self.post(client, path, data, etag=self.etag()), "PERMISSION_DENIED")
        self.assertEqual(owners().count(), 1)

    def test_lookup_pagination_bounds_and_query_allowlist(self):
        client = self.sign_in(self.owner)
        for i in range(35):
            Group.objects.create(name="synthetic-page-%02d" % i)
        response = client.get(BASE + "roles/groups/")
        self.assertEqual(len(response.json()["results"]), 30)
        self.assertEqual(response.json()["page_size"], 30)
        self.assertEqual(len(client.get(BASE + "roles/groups/", {"page": 2}).json()["results"]), 6)
        for query in ({"page_size": 101}, {"page": "-1"}, {"model": "auth.User"}, {"sort": "password"}):
            self.code(client.get(BASE + "roles/groups/", query), "INVALID_QUERY", 400)

    def test_scoped_me_catalog_and_lookup_boundaries(self):
        client = self.sign_in(self.scoped)
        self.assertEqual(set(client.get(BASE + "me/").json()["capabilities"]), {"cms_enter", "cms_catalog", "cms_brain_view"})
        catalog = client.get(BASE + "catalog/").json()["capabilities"]
        self.assertEqual(next(c["status"] for c in catalog if c["codename"] == "cms_brain_view"), "READY")
        for path in ("roles/permissions/", "roles/groups/", f"roles/users/{self.owner.pk}/"):
            self.code(client.get(BASE + path), "PERMISSION_DENIED")
        self.code(client.get(BASE + "sessions/", {"user_id": self.owner.pk}), "PERMISSION_DENIED")
        owner_client = self.sign_in(self.owner)
        owner_catalog = owner_client.get(BASE + "catalog/").json()["capabilities"]
        self.assertEqual(next(c["status"] for c in owner_catalog if c["codename"] == "cms_brain_create"), "READY")
        self.assertEqual(next(c["status"] for c in owner_catalog if c["codename"] == "cms_publication_apply_brain"), "PLANNED")
        self.assertEqual(owner_client.get(BASE + "roles/permissions/").status_code, 200)
        self.assertNotIn("django_session", json.dumps(owner_client.get(BASE + "sessions/").json()))
        self.code(self.post(client, f"sessions/{owner_client.session['cms_session_id']}/revoke/", etag=self.etag()), "NOT_FOUND", 404)

    def test_delegation_ceiling_and_unknown_grants(self):
        self.grant(self.scoped, "cms_roles_edit", "cms_roles_view", "cms_delegate_brain_view")
        client = self.sign_in(self.scoped)
        path = f"roles/users/{self.staff.pk}/"
        for caps, code in ((["cms_owner"], "DELEGATION_DENIED"), (["cms_core_view"], "DELEGATION_DENIED"), (["cms_unknown"], "INVALID_PERMISSIONS")):
            self.code(self.post(client, path, {"permissions": caps}, etag=self.etag()), code, 400 if code == "INVALID_PERMISSIONS" else 403)
        self.assertEqual(self.post(client, path, {"permissions": ["cms_brain_view"]}, etag=self.etag()).status_code, 200)
        self.assertEqual(set(client.get(BASE + "roles/permissions/").json()["permissions"]), {"cms_brain_view", "cms_delegate_brain_view"})
        owner_group = Group.objects.get(name="CMS Owner V1")
        self.code(client.get(BASE + f"roles/groups/{owner_group.pk}/"), "NOT_FOUND", 404)
        self.code(self.post(client, path, {"groups": [owner_group.pk]}, etag=self.etag()), "NOT_FOUND", 404)

    def test_owner_grant_stepup_target_payload_expiry_and_single_use(self):
        client = self.sign_in(self.owner)
        data = {"permissions": ["cms_owner"]}
        path = f"roles/users/{self.staff.pk}/"
        self.code(self.post(client, path, data, etag=self.etag()), "STEP_UP_REQUIRED")
        self.step_up(client, self.owner, "user", self.normal.pk, data)
        self.code(self.post(client, path, data, etag=self.etag()), "STEP_UP_REQUIRED")
        self.step_up(client, self.owner, "user", self.staff.pk, {"permissions": ["cms_enter"]})
        self.code(self.post(client, path, data, etag=self.etag()), "STEP_UP_REQUIRED")
        self.step_up(client, self.owner, "user", self.staff.pk, data)
        row = AdminSession.objects.get(pk=client.session["cms_session_id"])
        proof = row.step_up; proof["expires"] = 0
        AdminSession.objects.filter(pk=row.pk).update(step_up=proof)
        self.code(self.post(client, path, data, etag=self.etag()), "STEP_UP_REQUIRED")
        self.step_up(client, self.owner, "user", self.staff.pk, data)
        response = self.post(client, path, data, etag=self.etag())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(owners().count(), 2)
        self.assertEqual(AdminSession.objects.get(pk=row.pk).step_up, {})
        self.code(self.post(client, f"roles/users/{self.normal.pk}/", data, etag=self.etag()), "STEP_UP_REQUIRED")

    def test_last_owner_all_role_status_membership_group_paths(self):
        client = self.sign_in(self.owner)
        path = f"roles/users/{self.owner.pk}/"
        for data in ({"permissions": []}, {"is_staff": False}, {"is_active": False}):
            self.step_up(client, self.owner, "user", self.owner.pk, data)
            self.code(self.post(client, path, data, etag=self.etag()), "LAST_OWNER", 409)
        group = Group.objects.get(name="CMS Owner V1")
        self.owner.user_permissions.clear()
        self.owner.groups.add(group)
        data = {"groups": []}
        self.step_up(client, self.owner, "user", self.owner.pk, data)
        self.code(self.post(client, path, data, etag=self.etag()), "LAST_OWNER", 409)
        self.step_up(client, self.owner, "group", group.pk, {"permissions": []})
        self.code(self.post(client, f"roles/groups/{group.pk}/", {"permissions": []}, etag=self.etag()), "LAST_OWNER", 409)
        self.step_up(client, self.owner, "delete_group", group.pk, {})
        self.code(self.post(client, f"roles/groups/{group.pk}/delete/", etag=self.etag()), "LAST_OWNER", 409)
        self.assertEqual(owners().count(), 1)

    def test_superuser_is_counted_and_unknown_permission_is_denied(self):
        root = User.objects.create_superuser("synthetic-root", password=PASSWORD)
        self.assertEqual(owners().count(), 2)
        self.assertEqual(effective_permissions(root), KNOWN_PERMISSIONS)
        client = self.sign_in(self.owner)
        data = {"is_superuser": False}
        self.step_up(client, self.owner, "user", root.pk, data)
        self.assertEqual(self.post(client, f"roles/users/{root.pk}/", data, etag=self.etag()).status_code, 200)
        self.assertEqual(owners().count(), 1)

    def test_preconditions_csrf_and_atomic_rollback(self):
        client = self.sign_in(self.owner)
        path = f"roles/users/{self.staff.pk}/"
        self.code(self.post(client, path, {"permissions": []}), "PRECONDITION_REQUIRED", 428)
        self.code(self.post(client, path, {"permissions": []}, etag='"999999"'), "STALE_REVISION", 412)
        self.code(client.post(BASE + path, {}), "CSRF_FAILED")
        original_version = RolePolicy.objects.get(pk=1).version
        with patch("atlas.cms_policy.AdminAuditEvent.objects.create", side_effect=RuntimeError("synthetic audit failure")):
            with self.assertRaises(RuntimeError):
                self.post(client, path, {"permissions": ["cms_enter"]}, etag=self.etag())
        self.assertFalse(self.staff.user_permissions.exists())
        self.assertEqual(RolePolicy.objects.get(pk=1).version, original_version)

    def test_group_create_edit_delete_and_owner_template_name_independence(self):
        client = self.sign_in(self.owner)
        self.assertEqual(self.post(client, "roles/groups/", {"name": "test-domain", "permissions": ["cms_brain_view"]}, etag=self.etag()).status_code, 200)
        group = Group.objects.get(name="test-domain")
        self.assertEqual(self.post(client, f"roles/groups/{group.pk}/", {"permissions": ["cms_brain_view", "cms_enter"]}, etag=self.etag()).status_code, 200)
        self.assertEqual(self.post(client, f"roles/groups/{group.pk}/delete/", etag=self.etag()).status_code, 200)
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())
        group = Group.objects.get(name="CMS Owner V1")
        group.name = "arbitrary-name"; group.save()
        self.staff.groups.add(group)
        self.assertIn("cms_owner", effective_permissions(self.staff))

    def test_raw_django_auth_admin_is_readonly_and_secrets_unregistered(self):
        client = self.sign_in(self.owner)
        self.assertEqual(client.get("/admin/").status_code, 200)
        token = self.csrf(client)
        response = client.post(f"/admin/auth/user/{self.owner.pk}/change/", {"is_active": "", "HTTP_X_CSRFTOKEN": token}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 403)
        self.owner.refresh_from_db(); self.assertTrue(self.owner.is_active)
        for model in (Permission, TOTPDevice, StaticDevice, StaticToken, AdminSession, RolePolicy):
            self.assertFalse(admin.site.is_registered(model))
        response = client.get(f"/admin/auth/user/{self.owner.pk}/change/")
        self.assertNotIn(self.owner.password, response.content.decode())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class JWTRevocationTests(SecurityFixture, TestCase):
    def test_existing_public_jwt_login_refresh_logout_me_and_register_contract(self):
        client = Client()
        response = client.post("/api/auth/login/", {"username": self.normal.username, "password": PASSWORD})
        self.assertEqual(set(response.json()), {"access", "refresh"})
        tokens = response.json()
        self.assertEqual(client.get("/api/auth/me/", HTTP_AUTHORIZATION="Bearer " + tokens["access"]).status_code, 200)
        self.assertEqual(client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}).status_code, 200)
        response = client.post("/api/auth/register/", {"email": "synthetic-register@example.test", "password": PASSWORD})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"user", "access", "refresh"})
        self.assertEqual(client.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, HTTP_AUTHORIZATION="Bearer " + tokens["access"]).status_code, 204)
        self.assertEqual(client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)

    def test_same_second_revoke_relogin_legacy_claim_and_stale_refresh(self):
        client = Client()
        legacy = RefreshToken.for_user(self.normal)
        self.assertEqual(client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {legacy.access_token}").status_code, 200)
        now = timezone.now()
        with patch("atlas.cms_sessions.timezone.now", return_value=now):
            with policy_lock():
                revoke_account(self.normal)
            self.assertEqual(client.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {legacy.access_token}").status_code, 401)
            self.assertEqual(client.post("/api/auth/refresh/", {"refresh": str(legacy)}).status_code, 401)
            fresh = client.post("/api/auth/login/", {"username": self.normal.username, "password": PASSWORD}).json()
            self.assertEqual(client.get("/api/auth/me/", HTTP_AUTHORIZATION="Bearer " + fresh["access"]).status_code, 200)
            self.assertEqual(client.post("/api/auth/refresh/", {"refresh": fresh["refresh"]}).status_code, 200)

    def test_account_and_targeted_session_revoke_scope_and_stepup(self):
        owner_client, scoped_client = self.sign_in(self.owner), self.sign_in(self.scoped)
        target_id = scoped_client.session["cms_session_id"]
        self.code(self.post(owner_client, f"sessions/{target_id}/revoke/", etag=self.etag()), "STEP_UP_REQUIRED")
        self.step_up(owner_client, self.owner, "revoke_session", target_id, {})
        self.assertEqual(self.post(owner_client, f"sessions/{target_id}/revoke/", etag=self.etag()).status_code, 200)
        self.code(scoped_client.get(BASE + "me/"), "UNAUTHENTICATED")
        scoped_client = self.sign_in(self.scoped)
        token = Client().post("/api/auth/login/", {"username": self.scoped.username, "password": PASSWORD}).json()
        self.step_up(owner_client, self.owner, "revoke_account", self.scoped.pk, {})
        self.assertEqual(self.post(owner_client, f"users/{self.scoped.pk}/revoke-sessions/", etag=self.etag()).status_code, 200)
        self.code(scoped_client.get(BASE + "me/"), "UNAUTHENTICATED")
        self.assertEqual(Client().get("/api/auth/me/", HTTP_AUTHORIZATION="Bearer " + token["access"]).status_code, 401)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PolicyConcurrencyTests(SecurityFixture, TransactionTestCase):
    def parallel(self, call):
        barrier = Barrier(2)
        def worker(i):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return call(i)
            except CMSFailure as exc:
                return str(exc.detail["code"])
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, range(2)))

    def test_concurrent_last_owner_demotions_preserve_one_owner(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="cms_owner", content_type__model="rolepolicy"))
        clients = [self.sign_in(self.owner), self.sign_in(self.staff)]
        users = [self.owner, self.staff]
        for client, user in zip(clients, users):
            self.step_up(client, user, "user", user.pk, {"is_active": False})
        session_ids = [c.session["cms_session_id"] for c in clients]
        version = RolePolicy.objects.get(pk=1).version
        def call(i):
            return mutate_role(users[i].pk, "user", users[i].pk, {"is_active": False}, version, session_ids[i])
        results = self.parallel(call)
        self.assertEqual(sum(isinstance(x, int) for x in results), 1, results)
        self.assertIn("STALE_REVISION", results)
        self.assertEqual(owners().count(), 1)

    def test_concurrent_grants_do_not_overwrite(self):
        client = self.sign_in(self.owner)
        version = RolePolicy.objects.get(pk=1).version
        session_id = client.session["cms_session_id"]
        def call(i):
            return mutate_role(self.owner.pk, "user", self.staff.pk, {"permissions": [["cms_brain_view"], ["cms_core_view"]][i]}, version, session_id)
        results = self.parallel(call)
        self.assertEqual(sum(isinstance(x, int) for x in results), 1, results)
        self.assertIn("STALE_REVISION", results)
        self.assertEqual(self.staff.user_permissions.count(), 1)

    def test_concurrent_last_owner_guard_without_stale_precondition(self):
        self.grant(self.staff, "cms_owner")
        clients = [self.sign_in(self.owner), self.sign_in(self.staff)]
        users = [self.owner, self.staff]
        for client, user in zip(clients, users):
            self.step_up(client, user, "user", user.pk, {"is_staff": False})
        sessions = [c.session["cms_session_id"] for c in clients]
        results = self.parallel(lambda i: mutate_role(users[i].pk, "user", users[i].pk, {"is_staff": False}, None, sessions[i]))
        self.assertEqual(sum(isinstance(x, int) for x in results), 1, results)
        self.assertIn("LAST_OWNER", results)
        self.assertEqual(owners().count(), 1)

    def test_concurrent_recovery_token_consumed_once(self):
        token = self.backup(self.owner)
        results = self.parallel(lambda i: verify_mfa(User.objects.get(pk=self.owner.pk), token, "recovery").pk)
        self.assertEqual(sum(isinstance(x, int) for x in results), 1, results)
        self.assertIn("MFA_INVALID", results)

    def test_concurrent_owner_membership_removal_and_group_deletion(self):
        group = Group.objects.create(name="synthetic-group-owner")
        group.permissions.add(Permission.objects.get(codename="cms_owner", content_type__model="rolepolicy"))
        self.owner.user_permissions.clear()
        self.owner.groups.add(group)
        self.grant(self.staff, "cms_owner")
        clients = [self.sign_in(self.owner), self.sign_in(self.staff)]
        self.step_up(clients[0], self.owner, "user", self.owner.pk, {"groups": []})
        self.step_up(clients[1], self.staff, "delete_group", group.pk, {})
        sessions = [c.session["cms_session_id"] for c in clients]
        def call(i):
            if i == 0:
                return mutate_role(self.owner.pk, "user", self.owner.pk, {"groups": []}, None, sessions[0])
            return mutate_role(self.staff.pk, "delete_group", group.pk, {}, None, sessions[1])
        results = self.parallel(call)
        self.assertTrue(any(isinstance(x, int) for x in results), results)
        self.assertTrue(owners().filter(pk=self.staff.pk).exists())


class AdminSecurityMigrationTests(TransactionTestCase):
    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_upgrade_reverse_preserve_existing_user_group_and_scientific_data(self):
        before_tip = ("atlas", "0037_v094_assessments_atlas")
        executor = MigrationExecutor(connection)
        executor.migrate([before_tip])
        apps = executor.loader.project_state([before_tip]).apps
        old_user = apps.get_model("auth", "User").objects.create(username="synthetic-preserved", is_staff=False, is_active=True, password="synthetic-hash")
        collision, _ = apps.get_model("auth", "Group").objects.get_or_create(name="CMS Owner V1")
        old_user.groups.add(collision)
        old_source = apps.get_model("atlas", "SourceReference").objects.create(title="synthetic-preserved-source")
        executor = MigrationExecutor(connection)
        executor.migrate([("atlas", "0038_v100_p01_admin_security")])
        self.assertEqual(User.objects.get(pk=old_user.pk).password, "synthetic-hash")
        self.assertFalse(User.objects.get(pk=old_user.pk).is_staff)
        self.assertEqual(Group.objects.get(pk=collision.pk).permissions.count(), 0)
        self.assertEqual(Permission.objects.filter(content_type__app_label="atlas", content_type__model="rolepolicy").count(), len(KNOWN_PERMISSIONS))
        self.assertEqual(RolePolicy.objects.count(), 1)
        from .models import SourceReference
        self.assertEqual(SourceReference.objects.get(pk=old_source.pk).title, "synthetic-preserved-source")
        executor = MigrationExecutor(connection)
        executor.migrate([before_tip])
        self.assertTrue(User.objects.filter(pk=old_user.pk, groups=collision.pk).exists())
        self.assertTrue(Group.objects.filter(pk=collision.pk).exists())
