"""Purpose-bound synthetic privacy reads; never target the protected database."""
import json
import uuid
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature

from .cms_models import AdminAuditEvent
from .models import Category, Disorder, UserNote
from .tests_v100_p01 import BASE, PASSWORD, SecurityFixture


class PrivacyFixture(SecurityFixture):
    def setUp(self):
        super().setUp()
        category = Category.objects.create(slug="privacy-synthetic", name_en="Synthetic")
        self.disorder = Disorder.objects.create(category=category, slug="privacy-synthetic", name_en="Synthetic")
        self.note = UserNote.objects.create(user=self.normal, disorder=self.disorder, body="Synthetic private subject note")
        UserNote.objects.create(user=self.scoped, disorder=self.disorder, body="Synthetic other subject note")
        self.reader = self.user("privacy-operator", staff=True,
            caps=("cms_enter", "cms_user_view", "cms_privacy_sensitive_read"))
        self.client = self.sign_in(self.reader)
        self.body = {"purpose": "SUPPORT_REQUEST", "case_ref": str(uuid.uuid4()), "scope": "disorder_notes", "page": 1}
        self.route = f"users/{self.normal.pk}/privacy/read/"

    def authorize(self, body=None, target=None):
        self.step_up(self.client, self.reader, "privacy_read", target or self.normal.pk, body or self.body)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CMSPurposePrivacyTests(PrivacyFixture, TestCase):
    def test_subject_read_requires_current_purpose_and_fresh_bound_mfa(self):
        denied = self.post(self.client, self.route, self.body)
        self.assertEqual(denied.status_code, 403, denied.content[:300])
        self.authorize()
        response = self.post(self.client, self.route, self.body)
        self.assertEqual(response.status_code, 200, response.content[:300])
        data = response.json()
        self.assertEqual(data["subject_id"], self.normal.pk)
        self.assertEqual(data["scope"], "disorder_notes")
        self.assertEqual([row["body"] for row in data["results"]], [self.note.body])
        self.assertNotIn("Synthetic other subject note", str(data))
        for secret in ("password", "email", "token", "session_key"):
            self.assertNotIn(secret, str(data).lower())
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        event = AdminAuditEvent.objects.get(action="privacy.read.disorder_notes")
        self.assertEqual((event.target_id, event.reason), (self.normal.pk, "PRIVACY_SUPPORT"))
        self.assertNotIn(self.note.body, str(AdminAuditEvent.objects.values()))
        self.assertEqual(self.post(self.client, self.route, self.body).status_code, 403)

    def test_content_curator_and_independent_scope_denials(self):
        curator = self.user("privacy-curator", staff=True, caps=("cms_enter", "cms_user_view", "cms_learning_view"))
        client = self.sign_in(curator)
        self.assertEqual(self.post(client, self.route, self.body).status_code, 403)
        self.assertFalse(AdminAuditEvent.objects.filter(action__startswith="privacy.read.").exists())
        self.authorize()
        forged = {**self.body, "scope": "concept_notes"}
        rejected = self.post(self.client, self.route, forged)
        self.assertEqual(rejected.status_code, 403, rejected.content[:300])
        self.assertEqual(self.post(self.client, f"users/{self.scoped.pk}/privacy/read/", self.body).status_code, 403)

    def test_closed_purpose_scope_page_and_reference_validation(self):
        for changed in ({"purpose": "ANYTHING"}, {"case_ref": "private@example.invalid"},
                {"scope": "auth.User"}, {"page": 0}, {"page": True}, {"extra": "ignored"}):
            with self.subTest(changed=changed):
                response = self.post(self.client, self.route, {**self.body, **changed})
                self.assertEqual(response.status_code, 400, response.content[:300])
        self.assertFalse(AdminAuditEvent.objects.filter(action__startswith="privacy.read.").exists())

    def test_current_permission_revocation_and_audit_failure_return_no_private_data(self):
        from .cms_models import AdminSession
        self.authorize()
        sid = self.client.session["cms_session_id"]
        proof = dict(AdminSession.objects.get(pk=sid).step_up)
        with patch("atlas.cms_privacy.AdminAuditEvent.objects.create", side_effect=DatabaseError("Synthetic audit outage")):
            response = self.post(self.client, self.route, self.body)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(self.note.body, response.content.decode())
        self.assertEqual(AdminSession.objects.get(pk=sid).step_up, proof)
        owner = self.sign_in(self.owner)
        revoked = self.post(owner, f"roles/users/{self.reader.pk}/", {"permissions": ["cms_enter", "cms_user_view"]}, etag=self.etag())
        self.assertEqual(revoked.status_code, 200)
        response = self.post(self.client, self.route, self.body)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AdminAuditEvent.objects.filter(action__startswith="privacy.read.").exists())

    def test_oversized_legacy_note_page_is_denied_before_materialization(self):
        from django.db import connection
        from django.db.models.query import QuerySet
        self.note.body = ("\x00" if connection.vendor == "sqlite" else "") + "Synthetic" * 20000
        self.note.save(update_fields=("body",))
        self.authorize()
        fetch = QuerySet._fetch_all
        materialized = []

        def observe(query):
            if query.model is UserNote and "body" in query.query.values_select:
                materialized.append(True)
            return fetch(query)

        with patch.object(QuerySet, "_fetch_all", observe):
            response = self.post(self.client, self.route, self.body)
        self.assertEqual(response.status_code, 400, response.content[:300])
        self.assertEqual(response.json()["code"], "PRIVACY_LIMIT")
        self.assertFalse(materialized)

    def test_every_closed_scope_projects_only_its_declared_personal_fields(self):
        from .cms_privacy import SCOPES
        for scope, (_, _, fields) in SCOPES.items():
            with self.subTest(scope=scope):
                body = {**self.body, "scope": scope}
                self.authorize(body)
                response = self.post(self.client, self.route, body)
                self.assertEqual(response.status_code, 200, response.content[:300])
                self.assertTrue(all(set(row) == set(fields) for row in response.json()["results"]))

    def test_raw_request_is_bounded_and_personal_rows_remain_unchanged(self):
        before = list(UserNote.objects.order_by("pk").values())
        response = self.post(self.client, self.route, {**self.body, "case_ref": "x" * 9000})
        self.assertEqual(response.status_code, 400)
        self.authorize()
        self.assertEqual(self.post(self.client, self.route, self.body).status_code, 200)
        self.assertEqual(list(UserNote.objects.order_by("pk").values()), before)

    def test_scope_catalog_requires_independent_user_and_privacy_grants(self):
        from .cms_privacy import SCOPES
        response = self.client.get(BASE + "users/privacy/schema/")
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual({row["key"] for row in response.json()["scopes"]}, set(SCOPES))
        self.assertTrue(all(row["label"] and row["label"] != row["key"] for row in response.json()["scopes"]))
        restricted = self.user("privacy-no-user-scope", staff=True, caps=("cms_enter", "cms_privacy_sensitive_read"))
        self.assertEqual(self.sign_in(restricted).get(BASE + "users/privacy/schema/").status_code, 403)


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CMSPrivacyReadConcurrencyTests(PrivacyFixture, TransactionTestCase):
    def test_learner_note_update_waits_until_bounded_page_has_been_projected(self):
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        from threading import Event
        from django.db import close_old_connections, connection, connections
        from django.test import Client
        from .cms_privacy import MAX_TEXT_UNITS, text_units
        for index in range(19):
            disorder = Disorder.objects.create(category=self.disorder.category, slug=f"privacy-page-{index}", name_en="Synthetic")
            UserNote.objects.create(user=self.normal, disorder=disorder, body="x" * 3000)
        learner = Client()
        login = learner.post("/api/auth/login/", {"username": self.normal.username, "password": PASSWORD})
        self.assertEqual(login.status_code, 200)
        access = login.json()["access"]
        self.authorize()
        measured, release, writing = Event(), Event(), Event()

        def measure(rows, fields):
            size = text_units(rows, fields)
            measured.set()
            if not release.wait(10):
                raise AssertionError("Synthetic privacy boundary wait timed out")
            return size

        def read():
            close_old_connections()
            client = Client(enforce_csrf_checks=True)
            client.cookies = self.client.cookies.copy()
            try:
                response = self.post(client, self.route, self.body)
                return response.status_code, response.json()
            finally:
                connections.close_all()

        def write():
            close_old_connections()

            def observe(execute, sql, params, many, context):
                if "atlas_usernote" in sql and "FOR UPDATE" in sql:
                    writing.set()
                return execute(sql, params, many, context)

            try:
                with connection.execute_wrapper(observe):
                    response = Client().put(f"/api/notes/{self.disorder.slug}/", json.dumps({"body": "z" * 12000}),
                        content_type="application/json", HTTP_AUTHORIZATION="Bearer " + access)
                return response.status_code
            finally:
                connections.close_all()

        with patch("atlas.cms_privacy.text_units", side_effect=measure), ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(read)
            try:
                self.assertTrue(measured.wait(5))
                writer = pool.submit(write)
                self.assertTrue(writing.wait(5))
                with self.assertRaises(TimeoutError):
                    writer.result(timeout=1)
            finally:
                release.set()
            status, data = reader.result(timeout=10)
            self.assertEqual(writer.result(timeout=10), 200)
        self.assertEqual(status, 200)
        self.assertLessEqual(sum(len(row["body"]) for row in data["results"]), MAX_TEXT_UNITS)
        self.note.refresh_from_db()
        self.assertEqual(len(self.note.body), 12000)
