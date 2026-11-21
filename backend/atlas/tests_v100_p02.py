"""Real session/API, rollback, migration and multi-connection P02 acceptance tests."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, RequestFactory, TransactionTestCase, override_settings

from .cms_audit import security_event
from .cms_content import canonical_snapshot, dependencies, digest, editable_snapshot, propose
from .cms_content_models import ContentRevision, ContentState
from .cms_models import AdminAuditEvent, RolePolicy
from .cms_policy import CMSFailure, policy_lock
from .models import Category, Disorder
from .tests_v100_p01 import BASE, SecurityFixture


class ContentFixture(SecurityFixture):
    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(slug="synthetic-category", name_en="Synthetic category")
        self.disorder = Disorder.objects.create(category=self.category, slug="synthetic-disorder", name_en="Synthetic disorder", overview="Synthetic original")
        self.state = self.anchor("disorder", self.disorder)
        self.category_state = self.anchor("category", self.category)
        self.client = self.sign_in(self.owner)

    def anchor(self, kind, obj):
        state = ContentState.objects.create(kind=kind, canonical_pk=obj.pk, legacy_origin=True,
            canonical_digest=digest(canonical_snapshot(kind, obj)), publication="current")
        snapshot = editable_snapshot(kind, obj)
        revision = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
            base_digest=state.canonical_digest, payload=snapshot, payload_digest=digest(snapshot),
            dependency_digest=dependencies(kind, obj), status="legacy")
        state.current_revision = revision
        state.save(update_fields=("current_revision",))
        return state

    def save_proposal(self, values, version=0, client=None, **extra):
        return self.post(client or self.client, f"content/disorder/{self.state.pk}/revisions/",
            {"payload": values, "base_digest": self.state.canonical_digest, **extra}, etag='"%s"' % version)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RevisionAPITests(ContentFixture, TransactionTestCase):
    def test_success_commits_revision_version_and_audit_without_canonical_edit(self):
        response = self.save_proposal({"overview": "Synthetic proposed claim"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["ETag"], '"1"')
        self.assertEqual(response["Cache-Control"], "no-store")
        self.disorder.refresh_from_db()
        self.assertEqual(self.disorder.overview, "Synthetic original")
        event = AdminAuditEvent.objects.get(action="revision.created")
        self.assertEqual((event.base_revision, event.new_revision, event.diff), (0, 1, ["overview"]))
        self.assertEqual(str(event.request_id), response["X-Request-ID"])
        self.assertEqual(ContentRevision.objects.filter(state=self.state).count(), 2)

    def test_stale_save_has_safe_diff_and_independent_denial(self):
        self.save_proposal({"name_fa": "Synthetic current name"})
        response = self.save_proposal({"overview": "Synthetic secret narrative"})
        self.code(response, "STALE_REVISION", 412)
        data = response.json()
        self.assertEqual(data["current_revision"], 1)
        self.assertEqual(data["current_etag"], '"1"')
        self.assertEqual({x["field"] for x in data["diff"]}, {"name_fa", "overview"})
        by_field = {x["field"]: x for x in data["diff"]}
        self.assertFalse(by_field["name_fa"]["mine_changed"])
        self.assertTrue(by_field["name_fa"]["current_changed"])
        self.assertTrue(by_field["overview"]["mine_changed"])
        self.assertNotIn("Synthetic secret narrative", response.content.decode())
        self.assertEqual(AdminAuditEvent.objects.filter(action="revision.created").count(), 1)
        event = AdminAuditEvent.objects.get(error_code="STALE_REVISION")
        self.assertEqual(event.outcome, "denied")
        self.assertEqual(event.request_id.hex, uuid.UUID(data["request_id"]).hex)

    def test_rebase_after_reload_preserves_first_editor_change(self):
        self.save_proposal({"name_fa": "Synthetic current name"})
        detail = self.client.get(BASE + f"content/disorder/{self.state.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["payload"]["name_fa"], "Synthetic current name")
        self.assertEqual(self.save_proposal({"overview": "Synthetic second claim"}, version=1).status_code, 200)
        self.state.refresh_from_db()
        self.assertEqual(self.state.current_revision.payload["name_fa"], "Synthetic current name")

    def test_precondition_and_digest_fail_closed(self):
        path = f"content/disorder/{self.state.pk}/revisions/"
        self.code(self.post(self.client, path, {"payload": {"name_en": "Changed"}}), "PRECONDITION_REQUIRED", 428)
        self.code(self.post(self.client, path, {"payload": {"name_en": "Changed"}}, etag='W/"0"'), "INVALID_PRECONDITION", 400)
        self.code(self.save_proposal({"name_en": "Changed"}, base_digest="f" * 64), "STALE_REVISION", 412)
        self.state.refresh_from_db()
        self.assertEqual(self.state.version, 0)

    def test_external_canonical_drift_is_rechecked_inside_transaction(self):
        Disorder.objects.filter(pk=self.disorder.pk).update(overview="Synthetic external writer")
        response = self.save_proposal({"name_fa": "Synthetic proposed"})
        self.code(response, "STALE_REVISION", 412)
        self.assertEqual(response.json()["blockers"], ["CANONICAL_RECONCILIATION_REQUIRED"])
        self.assertEqual(ContentRevision.objects.filter(state=self.state).count(), 1)

    def test_closed_fields_models_and_scopes(self):
        for field in ("is_active", "reviewed", "seed_managed", "slug", "category_id", "actor", "model", "password", "note"):
            self.code(self.save_proposal({field: "synthetic forbidden"}), "INVALID_FIELDS", 400)
        for kind in ("UserNote", "user", "researchrecord", "case", "atlas.Disorder"):
            self.code(self.post(self.client, f"content/{kind}/", {"payload": {"name_en": "Synthetic"}}), "NOT_FOUND", 404)
        scoped = self.sign_in(self.scoped)
        self.code(scoped.get(BASE + f"content/disorder/{self.state.pk}/"), "NOT_FOUND", 404)
        self.code(self.save_proposal({"name_fa": "Synthetic"}, client=scoped), "PERMISSION_DENIED")
        self.assertEqual(self.client.get(BASE + f"content/category/{self.state.pk}/").status_code, 404)

    def test_anonymous_jwt_csrf_and_revoked_capability_cannot_write(self):
        path = f"content/disorder/{self.state.pk}/revisions/"
        self.code(self.post(Client(enforce_csrf_checks=True), path, {"payload": {"name_en": "Synthetic"}}, etag='"0"'), "UNAUTHENTICATED")
        self.code(self.client.post(BASE + path, json.dumps({"payload": {"name_en": "Synthetic"}}), content_type="application/json", HTTP_IF_MATCH='"0"'), "CSRF_FAILED")
        self.owner.user_permissions.clear()
        self.code(self.save_proposal({"name_en": "Synthetic"}), "PERMISSION_DENIED")
        self.assertEqual(ContentRevision.objects.filter(state=self.state).count(), 1)

    def test_audit_failure_rolls_back_and_records_failed_after_exit(self):
        original = AdminAuditEvent.objects.create
        def failing(**kwargs):
            if kwargs["action"] == "revision.created":
                raise DatabaseError("Synthetic private SQL error never exposed")
            self.assertEqual(len(connection.atomic_blocks), 1)
            return original(**kwargs)
        with patch.object(AdminAuditEvent.objects, "create", side_effect=failing):
            response = self.save_proposal({"overview": "Synthetic private claim"})
        self.code(response, "WRITE_FAILED", 503)
        self.state.refresh_from_db()
        self.assertEqual(self.state.version, 0)
        self.assertEqual(ContentRevision.objects.filter(state=self.state).count(), 1)
        self.assertFalse(AdminAuditEvent.objects.filter(action="revision.created").exists())
        self.assertEqual(AdminAuditEvent.objects.get(error_code="WRITE_FAILED").outcome, "failed")
        self.assertNotIn("SQL", response.content.decode())

    def test_late_failure_rolls_back_success_event_and_revision(self):
        with patch.object(ContentState, "refresh_from_db", side_effect=DatabaseError("Synthetic late failure")):
            response = self.save_proposal({"overview": "Synthetic rejected value"})
        self.code(response, "WRITE_FAILED", 503)
        self.state.refresh_from_db()
        self.assertEqual(self.state.version, 0)
        self.assertFalse(AdminAuditEvent.objects.filter(action="revision.created").exists())
        self.assertTrue(AdminAuditEvent.objects.filter(outcome="failed").exists())

    def test_runtime_and_validation_failures_roll_back_and_are_audited(self):
        for error in (RuntimeError("Synthetic private runtime error"), ValidationError("Synthetic private validation error")):
            with patch.object(ContentState, "refresh_from_db", side_effect=error):
                response = self.save_proposal({"overview": "Synthetic failed proposal"})
            self.code(response, "INTERNAL_ERROR", 503)
            self.assertNotIn("Synthetic", response.content.decode())
        self.state.refresh_from_db()
        self.assertEqual(self.state.version, 0)
        self.assertEqual(AdminAuditEvent.objects.filter(error_code="INTERNAL_ERROR", outcome="failed").count(), 2)
        self.assertFalse(AdminAuditEvent.objects.filter(action="revision.created").exists())

    def test_recovery_denial_is_audited_after_rollback(self):
        response = self.client.post("/account/two_factor/backup/tokens/", {"generate": "1"}, HTTP_X_CSRFTOKEN=self.csrf(self.client))
        self.code(response, "STEP_UP_REQUIRED")
        self.assertEqual(AdminAuditEvent.objects.get(error_code="STEP_UP_REQUIRED").outcome, "denied")

    def test_total_audit_outage_fails_closed_without_logging_payload(self):
        with patch.object(AdminAuditEvent.objects, "create", side_effect=DatabaseError("Synthetic secret SQL")):
            response = self.save_proposal({"overview": "Synthetic private draft"})
        self.code(response, "AUDIT_UNAVAILABLE", 503)
        self.state.refresh_from_db()
        self.assertEqual(self.state.version, 0)
        self.assertFalse(AdminAuditEvent.objects.filter(action="revision.created").exists())
        self.assertNotIn("Synthetic", response.content.decode())

    def test_history_preview_requires_scope_and_is_not_cached(self):
        self.save_proposal({"overview": "Synthetic revised text"})
        response = self.client.get(BASE + f"content/disorder/{self.state.pk}/revisions/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual([row["sequence"] for row in response.json()["results"]], [1, 0])
        self.assertEqual(response.json()["results"][1]["payload"]["overview"], "Synthetic original")
        self.code(self.sign_in(self.scoped).get(BASE + f"content/disorder/{self.state.pk}/revisions/"), "NOT_FOUND", 404)

    def test_existing_role_mutation_audit_identifies_created_group(self):
        response = self.post(self.client, "roles/groups/", {"name": "Synthetic audited group", "permissions": []}, etag=self.etag())
        self.assertEqual(response.status_code, 200, response.content)
        event = AdminAuditEvent.objects.get(action="roles.create_group")
        self.assertEqual(event.target_id, Group.objects.get(name="Synthetic audited group").pk)
        self.assertEqual((event.target_kind, event.base_revision, event.new_revision), ("group", 0, 1))

    def test_private_reason_is_not_persisted_or_reflected(self):
        for reason in ("Synthetic private note", {"note": "Synthetic private note"}):
            response = self.save_proposal({"overview": "Synthetic changed"}, reason=reason)
            self.code(response, "INVALID_REASON", 400)
            self.assertNotIn("Synthetic", response.content.decode())
        self.assertFalse(AdminAuditEvent.objects.filter(action="revision.created").exists())

    def test_redaction_validation_and_no_raw_admin_writers(self):
        self.save_proposal({"overview": "Synthetic password token private narrative"})
        response = self.client.get(BASE + "audit/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        serialized = response.content.decode()
        for value in ("Synthetic password token private narrative", self.owner.username, self.owner.email, self.client.session.session_key):
            if value:
                self.assertNotIn(value, serialized)
        with self.assertRaises(ValidationError):
            AdminAuditEvent.objects.create(action="revision.created", outcome="success", diff={"overview": "private"})
        for model in (ContentState, ContentRevision, AdminAuditEvent):
            self.assertFalse(admin.site.is_registered(model))
        request = RequestFactory().get("/admin/")
        request.user = self.owner
        for model in (Category, Disorder):
            raw = admin.site._registry[model]
            self.assertFalse(raw.has_add_permission(request))
            self.assertFalse(raw.has_change_permission(request))
            self.assertFalse(raw.has_delete_permission(request))
            self.assertNotIn("delete_selected", raw.get_actions(request))
        self.assertEqual(self.post(self.client, "audit/", {}).status_code, 405)

    def test_append_only_records_and_actor_erasure(self):
        self.save_proposal({"overview": "Synthetic new value"})
        event = AdminAuditEvent.objects.get(action="revision.created")
        ref = event.actor_ref
        revision = ContentRevision.objects.get(state=self.state, sequence=1)
        for obj in (event, revision):
            with self.assertRaises(ValidationError):
                obj.save()
            with self.assertRaises(ValidationError):
                obj.delete()
            with self.assertRaises(ValidationError):
                type(obj).objects.filter(pk=obj.pk).update(actor=None)
            with self.assertRaises(ValidationError):
                type(obj).objects.filter(pk=obj.pk).delete()
            with self.assertRaises(ValidationError):
                type(obj).objects.bulk_update([obj], ["actor"])
            for manager in (type(obj)._base_manager, type(obj).retained):
                with self.assertRaises(ValidationError):
                    manager.filter(pk=obj.pk).update(**({"outcome": "denied"} if obj is event else {"payload": {"overview": "Forged"}}))
                with self.assertRaises(ValidationError):
                    manager.filter(pk=obj.pk).delete()
                with self.assertRaises(ValidationError):
                    manager.filter(pk=obj.pk)._raw_delete(connection.alias)
        self.owner.delete()
        event.refresh_from_db()
        revision.refresh_from_db()
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.actor_ref, ref)
        self.assertIsNone(revision.actor_id)

    def test_draft_visibility_and_discard_retains_history(self):
        public = Client()
        urls = ["/api/disorders/", f"/api/disorders/{self.disorder.slug}/", "/api/categories/", "/api/search/?q=Synthetic", "/api/concept-map/"]
        before = [(url, public.get(url).content) for url in urls]
        response = self.post(self.client, "content/disorder/", {"payload": {"name_en": "Synthetic hidden draft", "overview": "Synthetic hidden snapshot"}})
        self.assertEqual(response.status_code, 201, response.content)
        draft = response.json()
        self.save_proposal({"overview": "Synthetic updated draft"})
        for url, content in before:
            result = public.get(url)
            self.assertEqual(result.status_code, 200, url)
            self.assertEqual(result.content, content, url)
        self.assertEqual(Disorder.objects.count(), 1)
        response = self.post(self.client, f"content/disorder/{draft['id']}/discard/", {"base_digest": draft["canonical_digest"]}, etag='"1"')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["revision_status"], "discarded")
        self.assertEqual(ContentRevision.objects.filter(state_id=draft["id"]).count(), 2)
        self.code(self.post(self.client, f"content/disorder/{draft['id']}/revisions/", {"payload": {"name_en": "Again"}, "base_digest": draft["canonical_digest"]}, etag='"2"'), "INVALID_TRANSITION", 409)

    def test_submitted_snapshot_is_immutable_and_cannot_be_edited(self):
        revision = ContentRevision.objects.create(state=self.state, sequence=1, base_version=0, base_digest=self.state.canonical_digest,
            payload={"name_en": "Synthetic submitted"}, payload_digest=digest({"name_en": "Synthetic submitted"}), dependency_digest=digest({}), status="submitted")
        ContentState.objects.filter(pk=self.state.pk).update(version=1, current_revision=revision)
        self.code(self.save_proposal({"name_en": "Forged"}, version=1), "INVALID_TRANSITION", 409)

    def test_security_sink_rejects_business_transaction_and_survives_rollback(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                security_event(self.owner, "PERMISSION_DENIED", 403)
        try:
            with policy_lock():
                Disorder.objects.filter(pk=self.disorder.pk).update(name_en="Synthetic rolled back")
                raise CMSFailure("PERMISSION_DENIED")
        except CMSFailure:
            security_event(self.owner, "PERMISSION_DENIED", 403)
        self.disorder.refresh_from_db()
        self.assertEqual(self.disorder.name_en, "Synthetic disorder")
        self.assertEqual(AdminAuditEvent.objects.get(error_code="PERMISSION_DENIED").outcome, "denied")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RevisionConcurrencyTests(ContentFixture, TransactionTestCase):
    def test_two_connections_on_same_base_have_one_commit(self):
        barrier = Barrier(2)
        session_id = self.client.session["cms_session_id"]
        def worker(i):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                state = propose(self.owner.pk, session_id, "disorder", str(self.state.pk), {"overview": "Synthetic editor " + str(i)},
                    0, self.state.canonical_digest, "CONTENT_UPDATE", uuid.uuid4())
                return state.version
            except CMSFailure as exc:
                security_event(self.owner, str(exc.detail["code"]), exc.status_code)
                return str(exc.detail["code"])
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertCountEqual(results, [1, "STALE_REVISION"])
        self.assertEqual(AdminAuditEvent.objects.filter(action="revision.created").count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(error_code="STALE_REVISION", outcome="denied").count(), 1)
        self.assertEqual(ContentRevision.objects.filter(state=self.state).count(), 2)

    def test_revocation_under_shared_lock_is_checked_before_commit(self):
        self.owner.user_permissions.clear()
        with self.assertRaises(CMSFailure):
            propose(self.owner.pk, self.client.session["cms_session_id"], "disorder", str(self.state.pk),
                {"name_en": "Unauthorized"}, 0, self.state.canonical_digest, "CONTENT_UPDATE", uuid.uuid4())
        self.assertEqual(ContentRevision.objects.filter(state=self.state).count(), 1)


class RevisionMigrationTests(TransactionTestCase):
    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_upgrade_backfills_real_visibility_preserves_events_and_reverses(self):
        old_tip = ("atlas", "0038_v100_p01_admin_security")
        new_tip = ("atlas", "0039_v100_p02_audit_revisions")
        executor = MigrationExecutor(connection)
        executor.migrate([old_tip])
        apps = executor.loader.project_state([old_tip]).apps
        OldCategory, OldDisorder = apps.get_model("atlas", "Category"), apps.get_model("atlas", "Disorder")
        category = OldCategory.objects.create(slug="synthetic-preserved", name_en="Synthetic", is_active=True)
        empty = OldCategory.objects.create(slug="synthetic-empty", name_en="Synthetic empty", is_active=True)
        disorder = OldDisorder.objects.create(slug="synthetic-published", name_en="Synthetic published", category_id=category.pk)
        hidden = OldDisorder.objects.create(slug="synthetic-inactive", name_en="Synthetic inactive", category_id=category.pk, is_active=False)
        old_actor = apps.get_model("auth", "User").objects.create(username="synthetic-migration-actor")
        old_event = apps.get_model("atlas", "AdminSecurityEvent").objects.create(actor_id=old_actor.pk, action="session.login", outcome="denied")
        old_time = old_event.created_at
        executor = MigrationExecutor(connection)
        executor.migrate([new_tip])
        historical = executor.loader.project_state([new_tip]).apps
        HistoricalState = historical.get_model("atlas", "ContentState")
        HistoricalRevision = historical.get_model("atlas", "ContentRevision")
        event = AdminAuditEvent.objects.get(pk=old_event.pk)
        self.assertEqual(event.outcome, "denied")
        self.assertEqual(event.created_at, old_time)
        self.assertEqual(len(event.actor_ref), 64)
        self.assertNotIn("synthetic", event.actor_ref)
        self.assertEqual(HistoricalState.objects.get(kind="category", canonical_pk=category.pk).publication, "current")
        self.assertEqual(HistoricalState.objects.get(kind="category", canonical_pk=empty.pk).publication, "never_published")
        self.assertEqual(HistoricalState.objects.get(kind="disorder", canonical_pk=hidden.pk).publication, "never_published")
        state = HistoricalState.objects.get(kind="disorder", canonical_pk=disorder.pk)
        self.assertEqual(state.current_revision.status, "legacy")
        self.assertIsNone(state.current_revision.actor_id)
        self.assertEqual(state.canonical_digest, digest(canonical_snapshot("disorder", Disorder.objects.get(pk=disorder.pk))))
        self.assertEqual(HistoricalRevision.objects.filter(state=state).count(), 1)
        executor = MigrationExecutor(connection)
        executor.migrate([old_tip])
        apps = executor.loader.project_state([old_tip]).apps
        self.assertEqual(apps.get_model("atlas", "AdminSecurityEvent").objects.get(pk=old_event.pk).outcome, "denied")
        self.assertEqual(apps.get_model("atlas", "Disorder").objects.get(pk=disorder.pk).name_en, "Synthetic published")
