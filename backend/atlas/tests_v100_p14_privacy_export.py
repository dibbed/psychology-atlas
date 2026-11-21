"""Synthetic personal export through the existing leased queue; no canonical data writes."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone

from .cms_job_models import AdminArtifact, AdminJob
from .cms_jobs import claim_job, run_once
from .cms_models import AccountSecurityState, AdminAuditEvent
from .models import UserNote
from .tests_v100_p01 import BASE
from .tests_v100_p13_learning_io import LearningTransferFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PrivacyExportTests(LearningTransferFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.exporter = self.user("privacy-export-only", staff=True,
            caps=("cms_enter", "cms_user_view", "cms_privacy_export", "cms_artifact_download"))
        self.client = self.sign_in(self.exporter)
        self.note = UserNote.objects.create(user=self.normal, disorder=self.disorder, body="PRIVATE-SUBJECT-ONLY")
        UserNote.objects.create(user=self.scoped, disorder=self.disorder, body="PRIVATE-OTHER-NEVER")
        self.body = {"purpose": "DATA_SUBJECT_REQUEST", "case_ref": str(uuid.uuid4()), "request_key": str(uuid.uuid4())}
        self.route = f"users/{self.normal.pk}/privacy/export/"

    def authorize(self, body=None):
        self.step_up(self.client, self.exporter, "privacy_export", self.normal.pk, body or self.body)

    def enqueue(self):
        self.authorize()
        response = self.post(self.client, self.route, self.body)
        self.assertEqual(response.status_code, 202, response.content[:300])
        return AdminJob.objects.get(pk=response.json()["job"]["id"])

    def download_private(self, output):
        return self.client.get(BASE + f"artifacts/{output.pk}/download/?purpose=privacy_request")

    def test_real_worker_export_only_scope_and_safe_personal_projection(self):
        queued = self.enqueue()
        self.assertEqual(queued.kind, "privacy_export")
        same = self.post(self.client, self.route, self.body)
        self.assertEqual(same.status_code, 202, same.content[:300])
        self.assertEqual(same.json()["job"]["id"], str(queued.pk))
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        response = self.download_private(job.output_artifact)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        document = json.loads(response.content)
        self.assertEqual(document["schema_version"], "psychology-atlas-personal-export-v1")
        self.assertEqual(document["identity"]["id"], self.normal.pk)
        self.assertEqual(document["data"]["disorder_notes"][0]["body"], self.note.body)
        self.assertNotIn("PRIVATE-OTHER-NEVER", response.content.decode())
        for forbidden in ("password", "session_key", "secret_ciphertext", "is_correct\":true,\"text", "Synthetic historical question"):
            self.assertNotIn(forbidden, response.content.decode())
        self.assertEqual(self.history(), self.before)
        self.assertEqual(AdminAuditEvent.objects.filter(action="privacy.exported").count(), 1)
        safe = str(list(AdminAuditEvent.objects.values())) + str(job.checkpoint) + str(job.result)
        self.assertNotIn(self.note.body, safe)
        self.assertNotIn(self.body["case_ref"], safe)
        self.assertEqual(self.client.get(BASE + "jobs/").status_code, 200)
        self.assertEqual(self.client.get(BASE + "artifacts/?kind=privacy_export_json").status_code, 200)
        self.assertEqual(self.client.get(BASE + "users/privacy/schema/").status_code, 403)

    def test_closed_purpose_fresh_bound_proof_and_same_key_conflicts(self):
        for change in ({"purpose": "SUPPORT_REQUEST"}, {"case_ref": "email@example.invalid"}, {"request_key": str(uuid.UUID(int=0))}, {"scope": "all"}):
            response = self.post(self.client, self.route, {**self.body, **change})
            self.assertEqual(response.status_code, 400, response.content[:300])
        self.assertEqual(self.post(self.client, self.route, self.body).status_code, 403)
        self.authorize()
        changed = {**self.body, "case_ref": str(uuid.uuid4())}
        self.assertEqual(self.post(self.client, self.route, changed).status_code, 403)
        original = self.post(self.client, self.route, self.body)
        self.assertEqual(original.status_code, 202, original.content[:300])
        self.assertEqual(self.post(self.client, self.route, changed).status_code, 409)
        self.assertEqual(AdminJob.objects.count(), 1)

    def test_download_current_capability_generation_expiry_and_server_only_kinds(self):
        self.enqueue()
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        output = job.output_artifact
        self.assertEqual(self.download_private(output).status_code, 200)
        self.assertEqual(self.client.get(BASE + f"artifacts/{output.pk}/download/?purpose=research_review").status_code, 400)
        self.exporter.user_permissions.remove(self.exporter.user_permissions.get(codename="cms_artifact_download"))
        self.assertEqual(self.download_private(output).status_code, 403)
        self.exporter.user_permissions.add(self.owner.user_permissions.model.objects.get(codename="cms_artifact_download"))
        state, _ = AccountSecurityState.objects.get_or_create(user=self.normal)
        state.security_version += 1
        state.save()
        self.assertIn(self.download_private(output).status_code, (403, 404, 409))
        for kind in ("privacy_request_json", "privacy_export_json"):
            self.assertEqual(self.upload({}, kind=kind, client=self.sign_in(self.owner)).status_code, 400)

    def test_enqueue_audit_rollback_keeps_proof_and_no_job(self):
        self.authorize()
        with patch("atlas.cms_privacy_io.AdminAuditEvent.objects.create", side_effect=DatabaseError("synthetic audit outage")):
            self.assertEqual(self.post(self.client, self.route, self.body).status_code, 503)
        self.assertEqual(AdminJob.objects.count(), 0)
        self.assertEqual(AdminArtifact.objects.count(), 0)
        self.assertEqual(self.post(self.client, self.route, self.body).status_code, 202)

    def test_quarantine_intent_survives_input_storage_failure_and_same_key_needs_no_second_proof(self):
        self.authorize()
        with patch("atlas.cms_privacy_io.store_generated", side_effect=DatabaseError("synthetic storage outage")):
            self.assertEqual(self.post(self.client, self.route, self.body).status_code, 503)
        artifact = AdminArtifact.objects.get()
        self.assertEqual(artifact.state, "quarantine")
        self.assertFalse(AdminJob.objects.exists())
        self.assertEqual(self.post(self.client, self.route, self.body).status_code, 202)
        self.assertEqual(AdminArtifact.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="privacy.export_requested").count(), 1)

    def test_output_file_crash_recovers_immutable_bytes_and_one_receipt(self):
        from . import cms_privacy_io as service
        from .cms_artifacts import _path
        queued = self.enqueue()
        job = claim_job()
        original = service.store_generated
        def crash(artifact, raw):
            original(artifact, raw)
            raise DatabaseError("synthetic crash after durable bytes")
        with patch.object(service, "store_generated", side_effect=crash):
            with self.assertRaises(DatabaseError):
                service.process_export(job.pk, job.lease_token)
        job.refresh_from_db()
        output = job.output_artifact
        self.assertEqual(output.state, "quarantine")
        stamp = _path(output).stat().st_mtime_ns
        self.assertFalse(AdminAuditEvent.objects.filter(action="privacy.exported").exists())
        service.process_export(job.pk, job.lease_token)
        self.assertEqual(_path(output).stat().st_mtime_ns, stamp)
        AdminJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1), cancel_requested=True, attempt=3)
        reconciled = claim_job()
        self.assertEqual(reconciled.status, "succeeded")
        self.assertEqual(AdminAuditEvent.objects.filter(action="privacy.exported").count(), 1)
        self.assertEqual(self.history(), self.before)

    def test_changed_snapshot_after_preparation_crash_fails_closed(self):
        from . import cms_privacy_io as service
        job = self.enqueue()
        job = claim_job()
        with patch.object(service, "store_generated", side_effect=DatabaseError("synthetic crash before bytes")):
            with self.assertRaises(DatabaseError):
                service.process_export(job.pk, job.lease_token)
        self.note.body = "Different requested snapshot"
        self.note.save()
        from .cms_policy import CMSFailure
        with self.assertRaises(CMSFailure) as error:
            service.process_export(job.pk, job.lease_token)
        self.assertEqual(error.exception.detail["code"], "CHECKPOINT_INTEGRITY")
        self.assertFalse(AdminAuditEvent.objects.filter(action="privacy.exported").exists())

    def test_cancel_permission_revoke_and_lease_loss_fence_effects(self):
        from . import cms_privacy_io as service
        from .cms_policy import CMSFailure
        job = self.enqueue()
        AdminJob.objects.filter(pk=job.pk).update(cancel_requested=True)
        self.assertEqual(run_once().status, "cancelled")
        self.body["request_key"] = str(uuid.uuid4())
        self.enqueue()
        self.exporter.user_permissions.remove(self.exporter.user_permissions.get(codename="cms_privacy_export"))
        failed = run_once()
        self.assertEqual((failed.status, failed.error_code), ("failed", "PERMISSION_DENIED"))
        self.assertFalse(AdminArtifact.objects.filter(kind="privacy_export_json").exists())
        self.exporter.user_permissions.add(self.owner.user_permissions.model.objects.get(codename="cms_privacy_export"))
        retry = self.post(self.client, f"jobs/{failed.pk}/retry/", etag=f'"{failed.version}"')
        self.assertEqual(retry.status_code, 200, retry.content[:300])
        self.assertEqual(run_once().status, "succeeded")
        self.body["request_key"] = str(uuid.uuid4())
        self.enqueue()
        claimed = claim_job()
        AdminJob.objects.filter(pk=claimed.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(CMSFailure):
            service.process_export(claimed.pk, claimed.lease_token)
        self.assertEqual(AdminArtifact.objects.filter(kind="privacy_export_json").count(), 1)

    def test_bounds_never_truncate_or_materialize_oversized_notes(self):
        from . import cms_privacy_io as service
        self.enqueue()
        UserNote.objects.filter(pk=self.note.pk).update(body="x"*(service.MAX_BYTES+1))
        from django.db.models.query import QuerySet
        original = QuerySet.values
        def no_note_values(rows, *fields, **kwargs):
            if rows.model is UserNote and "body" in fields:
                raise AssertionError("Oversized note materialized")
            return original(rows, *fields, **kwargs)
        with patch.object(QuerySet, "values", no_note_values):
            failed = run_once()
        self.assertEqual((failed.status, failed.error_code), ("failed", "PRIVACY_LIMIT"))
        self.assertFalse(AdminArtifact.objects.filter(kind="privacy_export_json").exists())
        self.assertEqual(self.history(), self.before)

    def test_second_download_check_blocks_revocation_after_bytes_and_expiry(self):
        from . import cms_artifacts
        self.enqueue()
        job = run_once()
        output = job.output_artifact
        original = cms_artifacts.artifact_bytes
        def revoke(artifact):
            raw = original(artifact)
            AdminArtifact.objects.filter(pk=artifact.pk).update(state="revoked")
            return raw
        with patch.object(cms_artifacts, "artifact_bytes", side_effect=revoke):
            self.assertEqual(self.download_private(output).status_code, 409)
        AdminArtifact.objects.filter(pk=output.pk).update(state="ready", expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.download_private(output).status_code, 409)

    def test_legacy_oversized_identity_is_guarded_before_materialization(self):
        from . import cms_privacy_io as service
        from django.contrib.auth.models import User
        from django.db.models.query import QuerySet
        self.enqueue()
        # SQLite legacy rows may exceed a CharField's declared max_length.
        from django.db import connection
        if connection.vendor != "sqlite":
            self.skipTest("PostgreSQL enforces identity varchar lengths")
        User.objects.filter(pk=self.normal.pk).update(email="x"*(service.MAX_BYTES+1))
        original = QuerySet.values
        def guard(rows, *fields, **kwargs):
            if rows.model is User and "email" in fields:
                raise AssertionError("Oversized identity materialized")
            return original(rows, *fields, **kwargs)
        with patch.object(QuerySet, "values", guard):
            failed = run_once()
        self.assertEqual((failed.status, failed.error_code), ("failed", "PRIVACY_LIMIT"))

    def test_record_budget_is_guarded_before_text_scan_and_nonfinite_data_is_rejected(self):
        from . import cms_privacy_io as service
        from .models import UserFlashcardProgress
        self.enqueue()
        with patch.object(service, "MAX_RECORDS", 1), patch.object(service, "text_units", wraps=service.text_units) as units:
            failed = run_once()
        self.assertEqual(failed.error_code, "PRIVACY_LIMIT")
        self.assertEqual(units.call_count, 1)  # Identity only; don't scan the oversized notes scope.
        self.body["request_key"] = str(uuid.uuid4())
        self.enqueue()
        UserFlashcardProgress.objects.filter(user=self.normal).update(ease_factor=float("inf"))
        failed = run_once()
        self.assertEqual((failed.status, failed.error_code), ("failed", "PRIVACY_DATA_INVALID"))

    def test_expired_revoked_personal_file_uses_native_cleanup_with_live_job_hold(self):
        from .cms_artifacts import cleanup_supported
        if not cleanup_supported():
            self.skipTest("Native physical cleanup adapter unavailable on this platform")
        self.enqueue()
        job = run_once()
        output = job.output_artifact
        from .cms_artifacts import cleanup_eligible, _path
        from .cms_policy import CMSFailure
        AdminArtifact.objects.filter(pk=output.pk).update(state="revoked", expires_at=timezone.now()-timedelta(seconds=1))
        output.refresh_from_db()
        AdminJob.objects.filter(pk=job.pk).update(status="running")
        with self.assertRaises(CMSFailure) as hold:
            cleanup_eligible(output)
        self.assertEqual(hold.exception.detail["code"], "ARTIFACT_RETENTION_HOLD")
        AdminJob.objects.filter(pk=job.pk).update(status="succeeded")
        self.client = self.sign_in(self.owner)
        response = self.post(self.client, f"artifacts/{output.pk}/cleanup/", etag=f'"{output.version}"')
        self.assertEqual(response.status_code, 202, response.content[:300])
        cleaned = run_once()
        self.assertEqual((cleaned.status, cleaned.result["cleaned"]), ("succeeded", True))
        output.refresh_from_db()
        self.assertEqual(output.state, "expired")
        self.assertIsNotNone(output.purged_at)
        self.assertFalse(_path(output).exists())
        self.assertEqual(self.history(), self.before)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_same_key_enqueue_uses_one_authorized_manifest_and_job(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connections
        from .cms_privacy_io import enqueue_export
        from threading import Barrier
        self.authorize()
        sid = self.client.session["cms_session_id"]
        barrier = Barrier(2)
        def enqueue():
            try:
                barrier.wait(timeout=15)
                return enqueue_export(self.exporter.pk, sid, self.normal.pk, self.body, uuid.uuid4()).pk
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(enqueue) for _ in range(2)]
            identifiers = [future.result(timeout=25) for future in futures]
        self.assertEqual(identifiers[0], identifiers[1])
        self.assertEqual(AdminJob.objects.count(), 1)
        self.assertEqual(AdminArtifact.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="privacy.export_requested").count(), 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_personal_export_uses_one_snapshot_across_public_writer_commit(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connections, transaction
        from . import cms_privacy_io as service
        from .models import ConceptNote
        note = ConceptNote.objects.create(user=self.normal, concept=self.concept, body="old-concept")
        self.enqueue()
        job = claim_job()
        original, changed = service.text_units, []
        def writer():
            try:
                with transaction.atomic():
                    UserNote.objects.filter(pk=self.note.pk).update(body="new-disorder")
                    ConceptNote.objects.filter(pk=note.pk).update(body="new-concept")
            finally:
                connections.close_all()
        def guard(rows, fields):
            if rows.model is ConceptNote and not changed:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(writer).result(timeout=15)
                changed.append(True)
            return original(rows, fields)
        with patch.object(service, "text_units", side_effect=guard):
            service.process_export(job.pk, job.lease_token)
        job.refresh_from_db()
        document = json.loads(self.download_private(job.output_artifact).content)
        self.assertEqual(document["data"]["disorder_notes"][0]["body"], "PRIVATE-SUBJECT-ONLY")
        self.assertEqual(document["data"]["concept_notes"][0]["body"], "old-concept")
        self.assertEqual(ConceptNote.objects.get(pk=note.pk).body, "new-concept")
