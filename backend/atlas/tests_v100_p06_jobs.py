"""NON-SCIENTIFIC isolated fixtures; real MFA/CSRF plus lease-fenced effects."""
import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import Permission

from django.db import OperationalError
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from .cms_job_models import AdminArtifact, AdminJob
from .cms_jobs import _failed, checkpoint_job, claim_job, enqueue_job, mutate_job, run_once
from .cms_models import AdminAuditEvent, AdminSession, RolePolicy
from .cms_policy import CMSFailure
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DurableJobTests(SecurityFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.sid = self.client.session["cms_session_id"]
        self.artifact = AdminArtifact.objects.create(kind="research_json", domain="research", owner=self.owner,
            owner_ref="NON-SCIENTIFIC", state="ready", storage_key=uuid.uuid4().hex + ".json",
            filename="NON-SCIENTIFIC.json", sha256=hashlib.sha256(b"{}").hexdigest(), size=2,
            expires_at=timezone.now() + timedelta(days=1))

    def enqueue(self, key=None, artifact=None):
        return enqueue_job(self.owner.pk, self.sid, (artifact or self.artifact).pk, key or uuid.uuid4(), uuid.uuid4())

    def test_request_key_replays_same_job_and_rejects_other_payload(self):
        key = uuid.uuid4()
        job = self.enqueue(key)
        self.assertEqual(self.enqueue(key).pk, job.pk)
        self.artifact.version += 1
        self.artifact.save()
        with self.assertRaises(CMSFailure) as error:
            self.enqueue(key)
        self.assertEqual(str(error.exception.detail["code"]), "IDEMPOTENCY_CONFLICT")
        self.assertEqual(AdminJob.objects.count(), 1)

    def test_expired_lease_resumes_checkpoint_and_fences_previous_worker(self):
        self.enqueue()
        old = claim_job()
        checkpoint_job(old.pk, old.lease_token, lambda row: setattr(row, "checkpoint", {"offset": 100}))
        self.assertIsNone(claim_job())
        AdminJob.objects.filter(pk=old.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        new = claim_job()
        self.assertEqual(new.checkpoint, {"offset": 100})
        self.assertNotEqual(new.lease_token, old.lease_token)
        with self.assertRaises(CMSFailure) as error:
            checkpoint_job(old.pk, old.lease_token, lambda row: self.fail("stale worker dispatched an effect"))
        self.assertEqual(str(error.exception.detail["code"]), "LEASE_LOST")
        self.assertEqual(new.attempt, 2)

    def test_effect_and_checkpoint_roll_back_together(self):
        self.enqueue()
        job = claim_job()
        before = AdminJob.objects.get(pk=job.pk).version
        def effect(row):
            row.checkpoint = {"offset": 100}
            AdminAuditEvent.objects.create(actor=self.owner, action="research.intake", outcome="success", reason="RESEARCH_INTAKE")
            raise RuntimeError("NON-SCIENTIFIC simulated crash before commit")
        count = AdminAuditEvent.objects.count()
        with self.assertRaises(RuntimeError):
            checkpoint_job(job.pk, job.lease_token, effect)
        job.refresh_from_db()
        self.assertEqual(job.checkpoint, {})
        self.assertEqual(job.version, before)
        self.assertEqual(AdminAuditEvent.objects.count(), count)

    def test_queued_cancel_and_running_safe_cancel_preserve_no_effect(self):
        queued = self.enqueue()
        result = mutate_job(self.owner.pk, self.sid, queued.pk, queued.version, "cancel", uuid.uuid4())
        self.assertEqual(result.status, "cancelled")
        self.enqueue()
        running = claim_job()
        mutate_job(self.owner.pk, self.sid, running.pk, running.version, "cancel", uuid.uuid4())
        with self.assertRaises(CMSFailure) as error:
            checkpoint_job(running.pk, running.lease_token, lambda row: self.fail("cancelled effect ran"))
        self.assertEqual(str(error.exception.detail["code"]), "JOB_CANCELLED")
        running.refresh_from_db()
        self.assertEqual(running.status, "cancelled")
        self.assertIsNone(running.lease_token)

    def test_current_permission_session_policy_and_artifact_revocation_deny_effect(self):
        for scenario in ("permission", "session", "policy", "artifact"):
            with self.subTest(scenario=scenario):
                self.grant(self.owner, "cms_owner")
                self.client = self.sign_in(self.owner)
                self.sid = self.client.session["cms_session_id"]
                self.artifact.state = "ready"
                self.artifact.save()
                self.enqueue()
                job = claim_job()
                if scenario == "permission":
                    self.owner.user_permissions.clear()
                elif scenario == "session":
                    AdminSession.objects.filter(pk=self.sid).update(revoked_at=timezone.now())
                elif scenario == "policy":
                    policy = RolePolicy.objects.get(pk=1)
                    policy.version += 1
                    policy.save()
                else:
                    self.artifact.state = "revoked"
                    self.artifact.save()
                with self.assertRaises(CMSFailure):
                    checkpoint_job(job.pk, job.lease_token, lambda row: self.fail("revoked authority dispatched effect"))
                AdminJob.objects.filter(pk=job.pk).update(status="failed")

    def test_worker_checks_authority_before_calling_handler(self):
        self.enqueue()
        AdminSession.objects.filter(pk=self.sid).update(revoked_at=timezone.now())
        with patch("atlas.cms_artifacts.process_intake") as handler:
            job = run_once()
        handler.assert_not_called()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.attempt, 1)

    def test_transient_attempts_are_bounded_and_terminal_lease_is_cleared(self):
        self.enqueue()
        with patch("atlas.cms_artifacts.process_intake", side_effect=OperationalError("database is locked")) as handler:
            for attempt in range(1, 4):
                AdminJob.objects.update(available_at=timezone.now())
                job = run_once()
                self.assertEqual(job.attempt, attempt)
                self.assertEqual(job.status, "queued" if attempt < 3 else "failed")
                self.assertIsNone(job.lease_token)
            self.assertIsNone(run_once())
        self.assertEqual(handler.call_count, 3)

    def test_completion_and_audit_failure_do_not_fabricate_success(self):
        self.enqueue()
        with patch("atlas.cms_artifacts.process_intake", return_value={"dataset_id": 123, "records": 0, "duplicate": False}):
            job = run_once()
        self.assertEqual(job.status, "succeeded")
        self.assertIsNone(job.lease_token)
        self.assertIsNone(job.lease_expires_at)
        self.assertEqual(job.result["dataset_id"], 123)
        self.assertTrue(AdminAuditEvent.objects.filter(action="job.succeeded", target_key=str(job.pk)).exists())
        before = AdminJob.objects.count()
        with patch("atlas.cms_jobs.audit", side_effect=RuntimeError("NON-SCIENTIFIC audit failure")):
            with self.assertRaises(RuntimeError):
                self.enqueue()
        self.assertEqual(AdminJob.objects.count(), before)

    def test_http_preconditions_csrf_and_foreign_actor_are_enforced(self):
        job = self.enqueue()
        detail = self.client.get(BASE + f"jobs/{job.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail["Cache-Control"], "no-store")
        self.assertNotIn("storage_key", str(detail.json()))
        self.assertNotIn("lease_token", str(detail.json()))
        self.assertEqual(self.post(self.client, f"jobs/{job.pk}/cancel/").status_code, 428)
        self.assertEqual(self.post(self.client, f"jobs/{job.pk}/cancel/", etag='"999"').status_code, 412)
        self.assertEqual(self.client.post(BASE + f"jobs/{job.pk}/cancel/", {}, content_type="application/json").status_code, 403)
        other = self.user("NON-SCIENTIFIC-other", staff=True, caps=("cms_enter", "cms_research_view", "cms_research_intake"))
        client = self.sign_in(other)
        self.assertEqual(client.get(BASE + f"jobs/{job.pk}/").status_code, 404)
        self.assertEqual(client.get(BASE + "jobs/").json()["count"], 0)
        self.assertEqual(self.post(self.client, f"jobs/{job.pk}/cancel/", etag=detail["ETag"]).status_code, 200)

    def test_expired_worker_cannot_commit_failure_before_reconciliation(self):
        self.enqueue()
        old = claim_job()
        AdminJob.objects.filter(pk=old.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        _failed(old.pk, old.lease_token, "INTERNAL_ERROR")
        old.refresh_from_db()
        self.assertEqual(old.status, "running")
        self.assertEqual(old.error_code, "")
        replacement = claim_job()
        self.assertNotEqual(replacement.lease_token, old.lease_token)

    def test_original_domain_revocation_filters_before_pagination_and_denies_actions(self):
        user = self.user("non-scientific-DSM-importer", staff=True,
            caps=("cms_enter", "cms_research_view", "cms_research_intake", "cms_dsm_view", "cms_dsm_edit"))
        client = self.sign_in(user)
        artifact = AdminArtifact.objects.create(kind="dsm_json", domain="dsm", owner=user,
            owner_ref="NON-SCIENTIFIC", state="ready", storage_key=uuid.uuid4().hex + ".json",
            filename="NON-SCIENTIFIC.json", sha256="a" * 64, size=2, expires_at=timezone.now() + timedelta(days=1))
        job = enqueue_job(user.pk, client.session["cms_session_id"], artifact.pk, uuid.uuid4(), uuid.uuid4())
        self.assertEqual(client.get(BASE + f"jobs/{job.pk}/").status_code, 200)
        user.user_permissions.remove(*Permission.objects.filter(codename="cms_dsm_view", content_type__model="rolepolicy"))
        self.assertEqual(client.get(BASE + f"jobs/{job.pk}/").status_code, 404)
        self.assertEqual(client.get(BASE + "jobs/").json()["count"], 0)
        self.assertEqual(self.post(client, f"jobs/{job.pk}/cancel/", etag=f'"{job.version}"').status_code, 404)
        job.refresh_from_db()
        self.assertEqual(job.status, "queued")

    def test_owner_cancel_attributes_actual_actor_without_rewriting_creator(self):
        creator = self.user("non-scientific-job-creator", staff=True, caps=("cms_enter", "cms_research_view", "cms_research_intake"))
        client = self.sign_in(creator)
        self.artifact.owner = creator
        self.artifact.save()
        job = enqueue_job(creator.pk, client.session["cms_session_id"], self.artifact.pk, uuid.uuid4(), uuid.uuid4())
        changed = mutate_job(self.owner.pk, self.sid, job.pk, job.version, "cancel", uuid.uuid4())
        self.assertEqual(changed.actor_id, creator.pk)
        event = AdminAuditEvent.objects.filter(action="job.cancelled", target_key=str(job.pk)).latest("pk")
        self.assertEqual(event.actor_id, self.owner.pk)

    def test_transient_claim_retry_is_bounded_and_does_not_dispatch_a_handler(self):
        with patch("atlas.cms_jobs.claim_job", side_effect=[OperationalError("database is locked"), None]) as claim, patch("atlas.cms_jobs.time.sleep"):
            self.assertIsNone(run_once())
        self.assertEqual(claim.call_count, 2)
        with patch("atlas.cms_jobs.claim_job", side_effect=OperationalError("database is locked")) as claim, patch("atlas.cms_jobs.time.sleep"):
            with self.assertRaises(CMSFailure) as error:
                run_once()
        self.assertEqual(str(error.exception.detail["code"]), "WORKER_UNAVAILABLE")
        self.assertEqual(claim.call_count, 3)

    def test_reconciled_last_attempt_does_not_redispatch_completed_effects(self):
        self.enqueue()
        job = claim_job()
        AdminJob.objects.filter(pk=job.pk).update(attempt=3, checkpoint={"complete": True},
            lease_expires_at=timezone.now() - timedelta(seconds=1))
        result = {"dataset_id": 123, "records": 1, "duplicate": False, "artifact_id": str(self.artifact.pk)}
        with patch("atlas.cms_artifacts.reconcile_intake", return_value=result), patch("atlas.cms_artifacts.process_intake") as handler:
            recovered = run_once()
        self.assertEqual(recovered.status, "succeeded")
        self.assertEqual(recovered.attempt, 3)
        self.assertEqual(recovered.result, result)
        self.assertIsNone(recovered.lease_token)
        handler.assert_not_called()

    def test_finalization_failure_keeps_committed_completion_recoverable(self):
        self.enqueue()
        job = claim_job()
        AdminJob.objects.filter(pk=job.pk).update(attempt=3, checkpoint={"complete": True})
        _failed(job.pk, job.lease_token, "TRANSIENT_DATABASE", True)
        job.refresh_from_db()
        self.assertEqual(job.status, "running")
        result = {"dataset_id": 123, "records": 1, "duplicate": False}
        with patch("atlas.cms_artifacts.reconcile_intake", return_value=result):
            recovered = claim_job()
        self.assertEqual(recovered.status, "succeeded")
        self.assertEqual(recovered.attempt, 3)

    def test_acknowledged_cancel_precedes_retry_exhaustion(self):
        self.enqueue()
        job = claim_job()
        AdminJob.objects.filter(pk=job.pk).update(attempt=3, cancel_requested=True,
            lease_expires_at=timezone.now() - timedelta(seconds=1))
        cancelled = claim_job()
        self.assertEqual(cancelled.status, "cancelled")
        self.assertTrue(AdminAuditEvent.objects.filter(target_key=str(job.pk), action="job.cancelled").exists())

    def test_unknown_job_schema_never_dispatches_effect(self):
        job = self.enqueue()
        AdminJob.objects.filter(pk=job.pk).update(schema_version=2)
        with patch("atlas.cms_artifacts.process_intake") as handler:
            failed = run_once()
        self.assertEqual((failed.status, failed.error_code), ("failed", "INVALID_JOB_SCHEMA"))
        handler.assert_not_called()
