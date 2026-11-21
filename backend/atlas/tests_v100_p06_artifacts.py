"""NON-SCIENTIFIC .invalid data, real MFA/CSRF, disposable DB/private storage."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch
import uuid

from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from . import cms_artifacts as service
from .cms_governance import resource_binding
from .cms_governance_models import GovernanceRecord, GovernanceRevision
from .cms_job_models import AdminArtifact, AdminJob, ResearchRecordDecision
from .cms_jobs import checkpoint_job, claim_job, enqueue_job, run_once
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure
from .models import Category
from .tests_v100_p01 import BASE, SecurityFixture

def research_document(count=1):
    return {"dataset_metadata": {"dataset_name": "NON-SCIENTIFIC fixture .invalid", "dataset_version": "1"},
        "concepts": [{"id": "NON-SCIENTIFIC-" + str(index), "name_en": "NON-SCIENTIFIC .invalid",
            "definition_en": "PRIVATE RAW NON-SCIENTIFIC .invalid " + str(index)} for index in range(count)]}


class ArtifactFixture(SecurityFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix="atlas-p06-NON-SCIENTIFIC-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private"
        configured = override_settings(CMS_ARTIFACT_ROOT=self.root)
        configured.enable()
        self.addCleanup(configured.disable)
        self.client = self.sign_in(self.owner)
        self.sid = self.client.session["cms_session_id"]

    def upload(self, document=None, *, raw=None, client=None, kind="research_json", **scope):
        raw = raw if raw is not None else json.dumps(document if document is not None else research_document(), ensure_ascii=False).encode("utf-8")
        client = client or self.client
        return client.post(BASE + "artifacts/", {"file": SimpleUploadedFile("NON-SCIENTIFIC.json", raw,
            content_type="application/json"), "kind": kind, **scope}, HTTP_X_CSRFTOKEN=self.csrf(client))

    def created(self, document=None, **values):
        response = self.upload(document, **values)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["artifact"]

    def validate(self, artifact, expected=None):
        return self.post(self.client, f"artifacts/{artifact['id']}/validate/", etag=expected or f'"{artifact["version"]}"')

    def ready(self, document=None, **values):
        artifact = self.created(document, **values)
        response = self.validate(artifact)
        self.assertEqual(response.status_code, 200, response.content)
        artifact = response.json()["artifact"]
        self.assertEqual(artifact["state"], "ready", artifact)
        return artifact

    def download(self, artifact, client=None):
        return (client or self.client).get(BASE + f"artifacts/{artifact['id']}/download/?purpose=research_review")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PrivateArtifactTests(ArtifactFixture, TransactionTestCase):
    @skipUnless(os.name == "nt", "Physical cleanup requires the Windows handle adapter")
    def test_cleanup_root_swap_at_final_delete_preserves_replacement_and_original(self):
        for timing in ("after_intent", "after_final_file_check"):
            with self.subTest(timing=timing):
                row = self.expire(self.ready())
                self.cleanup_job(row)
                moved = Path(self.temp.name) / ("renamed-private-" + timing)
                unrelated = b"NON-SCIENTIFIC unrelated replacement"
                original = (self.root / row.storage_key).read_bytes()
                attempts = []
                def swap_after_intent(job_id, token, effect):
                    current = checkpoint_job(job_id, token, effect)
                    if current.checkpoint.get("cleanup_prepared") and timing == "after_intent":
                        self.root.rename(moved)
                        self.root.mkdir()
                        (self.root / row.storage_key).write_bytes(unrelated)
                        attempts.append(timing)
                    return current
                def swap_at_delete(storage, handle):
                    attempts.append(timing)
                    for source, target in ((self.root, moved),
                            (self.root.parent, self.root.parent.with_name(self.root.parent.name + "-moved")),
                            (self.root / row.storage_key, self.root / "moved-leaf.json")):
                        with self.assertRaises(OSError):
                            source.rename(target)
                    with self.assertRaises(OSError):
                        (self.root / row.storage_key).write_bytes(unrelated)
                    raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
                with patch("atlas.cms_jobs.checkpoint_job", side_effect=swap_after_intent), \
                        patch.object(Path, "unlink", side_effect=AssertionError("pathname deletion forbidden")):
                    if timing == "after_final_file_check":
                        with patch.object(service._WindowsCleanup, "delete", swap_at_delete):
                            result = run_once()
                    else:
                        result = run_once()
                self.assertEqual(attempts, [timing])
                if timing == "after_intent":
                    self.assertEqual((self.root / row.storage_key).read_bytes(), unrelated)
                    self.assertEqual((moved / row.storage_key).read_bytes(), original)
                    if result.status == "running":
                        result = claim_job()
                    self.assertEqual(result.status, "failed")
                else:
                    self.assertEqual((self.root / row.storage_key).read_bytes(), original)
                row.refresh_from_db()
                self.assertIsNone(row.purged_at)
                self.assertNotEqual(result.status, "succeeded")
                self.assertEqual(result.error_code, "CHECKPOINT_INTEGRITY")
                self.assertFalse(AdminAuditEvent.objects.filter(action="artifact.cleanup").exists())

    @skipUnless(os.name == "nt", "Physical cleanup requires the Windows handle adapter")
    def test_cleanup_root_recreated_after_intent_cannot_fake_a_receipt(self):
        row = self.expire(self.ready())
        self.cleanup_job(row)
        worker = claim_job()
        def interrupt(job_id, token, effect):
            current = checkpoint_job(job_id, token, effect)
            if current.checkpoint.get("cleanup_prepared"):
                raise RuntimeError("NON-SCIENTIFIC crash after intent")
            return current
        with patch("atlas.cms_jobs.checkpoint_job", side_effect=interrupt), self.assertRaises(RuntimeError):
            service.process_cleanup(worker.pk, worker.lease_token)
        moved = Path(self.temp.name) / "original-private"
        original = (self.root / row.storage_key).read_bytes()
        self.root.rename(moved)
        self.root.mkdir()
        (self.root / "unrelated.json").write_bytes(b"NON-SCIENTIFIC unrelated replacement")
        AdminJob.objects.filter(pk=worker.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        result = claim_job()
        row.refresh_from_db()
        self.assertIsNone(row.purged_at)
        self.assertEqual((result.status, result.error_code), ("failed", "CHECKPOINT_INTEGRITY"))
        self.assertEqual((moved / row.storage_key).read_bytes(), original)
        self.assertEqual((self.root / "unrelated.json").read_bytes(), b"NON-SCIENTIFIC unrelated replacement")
        self.assertFalse(AdminAuditEvent.objects.filter(action="artifact.cleanup").exists())

    def test_cleanup_unsupported_platform_has_no_job_or_storage_effect(self):
        row = self.expire(self.ready())
        original = (self.root / row.storage_key).read_bytes()
        with patch("atlas.cms_artifacts.sys.platform", "linux"):
            self.assertFalse(service.artifact_data(row)["cleanup_supported"])
            response = self.post(self.client, f"artifacts/{row.pk}/cleanup/", etag='"2"')
            self.code(response, "CLEANUP_PLATFORM_UNAVAILABLE", 503)
        self.assertEqual(service.artifact_data(row)["cleanup_supported"], os.name == "nt")
        self.assertEqual(AdminJob.objects.count(), 0)
        self.assertEqual((self.root / row.storage_key).read_bytes(), original)
        row.refresh_from_db()
        self.assertIsNone(row.purged_at)
        self.assertEqual(row.version, 2)

    def expire(self, artifact):
        AdminArtifact.objects.filter(pk=artifact["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        return AdminArtifact.objects.get(pk=artifact["id"])

    def cleanup_job(self, row):
        return enqueue_job(self.owner.pk, self.sid, row.pk, uuid.uuid4(), uuid.uuid4(),
            kind="artifact_cleanup", expected=row.version)

    @skipUnless(os.name == "nt", "Physical cleanup requires the Windows handle adapter")
    def test_cleanup_http_expiry_etag_and_persisted_receipt(self):
        artifact = self.ready()
        path = f"artifacts/{artifact['id']}/cleanup/"
        self.code(self.post(self.client, path), "PRECONDITION_REQUIRED", 428)
        self.code(self.post(self.client, path, etag='"1"'), "STALE_REVISION", 412)
        self.code(self.post(self.client, path, etag='"2"'), "ARTIFACT_NOT_EXPIRED", 409)
        row = self.expire(artifact)
        response = self.post(self.client, path, etag='"2"')
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response["Location"], BASE + "jobs/" + response.json()["job"]["id"] + "/")
        self.assertTrue((self.root / row.storage_key).exists())
        identity = (self.root / row.storage_key).stat()
        with patch.object(Path, "unlink", side_effect=AssertionError("pathname deletion forbidden")):
            job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        row.refresh_from_db()
        self.assertEqual((row.state, row.version), ("expired", 3))
        self.assertIsNotNone(row.purged_at)
        self.assertFalse((self.root / row.storage_key).exists())
        self.assertEqual((job.progress_done, job.progress_total, job.checkpoint["complete"]), (1, 1, True))
        self.assertEqual(job.result, {"artifact_id": str(row.pk), "cleaned": True})
        root = self.root.stat()
        self.assertEqual(job.checkpoint["directory_identity"], {"dev": root.st_dev, "ino": root.st_ino})
        self.assertEqual(job.checkpoint["file_identity"], {"dev": identity.st_dev, "ino": identity.st_ino})
        self.assertEqual(AdminAuditEvent.objects.filter(action="artifact.cleanup", reason="ARTIFACT_CLEANUP").count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="job.succeeded").count(), 1)
        self.assertIsNotNone(self.client.get(BASE + f"artifacts/{row.pk}/").json()["artifact"]["purged_at"])
        self.code(self.post(self.client, path, etag='"3"'), "ARTIFACT_RETENTION_HOLD", 409)
        self.assertEqual(AdminArtifact.objects.count(), 1)
        rejected = self.expire(self.created())
        AdminArtifact.objects.filter(pk=rejected.pk).update(state="rejected")
        revoked = self.expire(self.created())
        AdminArtifact.objects.filter(pk=revoked.pk).update(state="revoked")
        expired = self.client.get(BASE + "artifacts/?state=expired&page_size=1").json()
        self.assertEqual(expired["count"], 2)
        self.assertEqual(len(expired["results"]), 1)
        self.assertEqual(expired["results"][0]["state"], "expired")
        self.assertEqual(self.client.get(BASE + "artifacts/?state=rejected").json()["count"], 0)
        self.assertEqual(self.client.get(BASE + "artifacts/?state=revoked").json()["results"][0]["state"], "revoked")

    def test_cleanup_holds_all_historical_evidence_and_holder_references(self):
        category = Category.objects.create(slug="non-scientific-hold", name_en="NON-SCIENTIFIC .invalid")
        for field in ("evidence", "holder_evidence"):
            with self.subTest(field=field):
                row = self.expire(self.ready())
                record = GovernanceRecord.objects.create(kind="rights", domain="core", resource_type="category",
                    resource_id=category.pk, resource_version="NON-SCIENTIFIC", status="revoked")
                revision = GovernanceRevision.objects.create(record=record, sequence=1,
                    payload={field: [{"artifact_id": str(row.pk), "locator": "NON-SCIENTIFIC .invalid"}]},
                    payload_digest="0" * 64, resource_digest="0" * 64, dependency_digest="0" * 64,
                    status="rejected", policy_version=1, policy_mode="solo", actor=self.owner,
                    actor_ref="NON-SCIENTIFIC", action="reject", reason="NON-SCIENTIFIC")
                with self.assertRaises(CMSFailure) as error:
                    service.cleanup_eligible(row)
                self.assertEqual(str(error.exception.detail["code"]), "ARTIFACT_RETENTION_HOLD")
                self.assertTrue((self.root / row.storage_key).exists())
                self.assertTrue(GovernanceRevision.objects.filter(pk=revision.pk).exists())

    @skipUnless(os.name == "nt", "Physical cleanup requires the Windows handle adapter")
    def test_cleanup_corrupt_path_hash_and_missing_bytes_never_claim_success(self):
        for corruption in ("path", "hash", "missing"):
            with self.subTest(corruption=corruption):
                row = self.expire(self.ready())
                self.cleanup_job(row)
                path = self.root / row.storage_key
                if corruption == "path":
                    AdminArtifact.objects.filter(pk=row.pk).update(storage_key="../NON-SCIENTIFIC.json")
                elif corruption == "hash":
                    path.write_bytes(b"x" * row.size)
                else:
                    path.unlink()
                result = run_once()
                self.assertEqual(result.status, "failed")
                self.assertFalse(result.checkpoint.get("cleanup_prepared", False))
                row.refresh_from_db()
                self.assertIsNone(row.purged_at)
                if corruption != "missing":
                    self.assertTrue(path.exists())
        self.assertFalse(AdminAuditEvent.objects.filter(action="artifact.cleanup").exists())

    @skipUnless(os.name == "nt", "Physical cleanup requires the Windows handle adapter")
    def test_cleanup_audit_failure_after_unlink_reconciles_last_attempt_without_unlink(self):
        for audit_action in ("artifact.cleanup", "job.succeeded"):
            with self.subTest(audit_action=audit_action):
                row = self.expire(self.ready())
                job = self.cleanup_job(row)
                if audit_action == "artifact.cleanup":
                    worker = claim_job()
                    AdminJob.objects.filter(pk=job.pk).update(attempt=3)
                else:
                    AdminJob.objects.filter(pk=job.pk).update(attempt=2)
                create = AdminAuditEvent.objects.create
                def fail_audit(**values):
                    if values.get("action") == audit_action:
                        raise DatabaseError("NON-SCIENTIFIC audit outage")
                    return create(**values)
                with patch.object(AdminAuditEvent.objects, "create", side_effect=fail_audit):
                    if audit_action == "artifact.cleanup":
                        with self.assertRaises(DatabaseError):
                            service.process_cleanup(worker.pk, worker.lease_token)
                    else:
                        interrupted = run_once()
                        self.assertEqual(interrupted.status, "running")
                        self.assertEqual(interrupted.error_code, "WORKER_INTERRUPTED")
                job.refresh_from_db()
                row.refresh_from_db()
                self.assertTrue(job.checkpoint["cleanup_prepared"])
                self.assertFalse(job.checkpoint.get("complete", False))
                self.assertIsNone(row.purged_at)
                self.assertFalse((self.root / row.storage_key).exists())
                self.assertEqual((job.progress_done, job.progress_total), (0, 1))
                AdminJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
                database = connection.settings_dict["NAME"]
                connections.close_all()
                if connection.vendor == "sqlite" and str(database) != ":memory:" and not str(database).startswith("file:memory"):
                    script = """import django
django.setup()
from pathlib import Path
from unittest.mock import patch
from atlas.cms_jobs import run_once
with patch.object(Path, 'unlink', side_effect=AssertionError('reconciliation must not unlink')):
    job = run_once()
assert job.status == 'succeeded' and job.attempt == 3, (job.status, job.error_code)
"""
                    restarted = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30,
                        env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", "DB_ENGINE": "sqlite",
                            "SQLITE_PATH": str(database), "CMS_ARTIFACT_ROOT": str(self.root)},
                        cwd=Path(__file__).resolve().parents[1])
                    self.assertEqual(restarted.returncode, 0, restarted.stderr)
                    recovered = AdminJob.objects.get(pk=job.pk)
                else:
                    with patch.object(Path, "unlink", side_effect=AssertionError("reconciliation must not unlink")):
                        recovered = claim_job()
                self.assertEqual((recovered.status, recovered.attempt), ("succeeded", 3))
                row.refresh_from_db()
                self.assertIsNotNone(row.purged_at)
                self.assertEqual(row.version, 3)
                self.assertEqual(AdminAuditEvent.objects.filter(action="artifact.cleanup", target_key=str(row.pk)).count(), 1)
                self.assertEqual(AdminAuditEvent.objects.filter(action="job.succeeded", target_key=str(job.pk)).count(), 1)

    @skipUnless(os.name == "nt", "Physical cleanup requires the Windows handle adapter")
    def test_cleanup_stale_token_ownership_and_changed_intent_fail_closed(self):
        row = self.expire(self.ready())
        self.grant(self.scoped, "cms_research_view", "cms_research_intake", "cms_artifact_upload")
        scoped = self.sign_in(self.scoped)
        self.code(self.post(scoped, f"artifacts/{row.pk}/cleanup/", etag='"2"'), "NOT_FOUND", 404)
        self.cleanup_job(row)
        worker = claim_job()
        with patch("atlas.cms_artifacts.artifact_bytes", wraps=service.artifact_bytes) as reading:
            with self.assertRaises(CMSFailure) as error:
                service.process_cleanup(worker.pk, uuid.uuid4())
            self.assertEqual(str(error.exception.detail["code"]), "LEASE_LOST")
            reading.assert_not_called()
        calls = 0
        def interrupt(job_id, token, effect):
            nonlocal calls
            current = checkpoint_job(job_id, token, effect)
            calls += 1
            if current.checkpoint.get("cleanup_prepared"):
                raise RuntimeError("NON-SCIENTIFIC crash after durable intent")
            return current
        with patch("atlas.cms_jobs.checkpoint_job", side_effect=interrupt), self.assertRaises(RuntimeError):
            service.process_cleanup(worker.pk, worker.lease_token)
        worker.refresh_from_db()
        self.assertGreater(calls, 0)
        with service.policy_lock():
            self.assertIsNone(service.reconcile_cleanup(worker))
        self.owner.user_permissions.clear()
        with patch("atlas.cms_artifacts.artifact_bytes", wraps=service.artifact_bytes) as reading:
            with self.assertRaises(CMSFailure):
                service.process_cleanup(worker.pk, worker.lease_token)
            reading.assert_not_called()
        self.grant(self.owner, "cms_owner")
        with override_settings(CMS_ARTIFACT_ROOT=Path(self.temp.name) / "different-private-root"):
            with self.assertRaises(CMSFailure) as error:
                with service.policy_lock():
                    service.reconcile_cleanup(worker)
            self.assertEqual(str(error.exception.detail["code"]), "CHECKPOINT_INTEGRITY")
        worker.checkpoint["size"] += 1
        worker.save()
        AdminJob.objects.filter(pk=worker.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        failed = claim_job()
        self.assertEqual((failed.status, failed.error_code), ("failed", "CHECKPOINT_INTEGRITY"))
        self.assertTrue((self.root / row.storage_key).exists())

    def test_storage_is_lazy_upload_quarantine_validation_download_exact_bytes_and_no_paths(self):
        self.assertFalse(self.root.exists())
        self.assertEqual(self.client.get(BASE + "artifacts/").json()["results"], [])
        self.assertFalse(self.root.exists())
        raw = b'{ "dataset_metadata":{"dataset_name":"NON-SCIENTIFIC .invalid"}, "concepts":[] }\n'
        artifact = self.created(raw=raw)
        self.assertEqual(artifact["state"], "quarantine")
        self.assertEqual(artifact["sha256"], hashlib.sha256(raw).hexdigest())
        self.code(self.download(artifact), "ARTIFACT_NOT_READY", 409)
        self.assertEqual(self.validate(artifact).status_code, 200)
        response = self.download(artifact)
        self.assertEqual(response.content, raw)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", response["Content-Disposition"])
        detail = self.client.get(BASE + f"artifacts/{artifact['id']}/")
        for forbidden in ("storage_key", str(self.root), "raw_document", "payload"):
            self.assertNotIn(forbidden, detail.content.decode())
        row = AdminArtifact.objects.get(pk=artifact["id"])
        self.assertEqual(row.storage_key, row.pk.hex + ".json")
        self.assertNotIn(AdminArtifact, admin.site._registry)
        self.assertNotIn(AdminJob, admin.site._registry)
        self.assertNotIn(ResearchRecordDecision, admin.site._registry)

    def test_mutations_use_etag_csrf_and_current_permissions(self):
        artifact = self.created()
        path = f"artifacts/{artifact['id']}/validate/"
        self.code(self.post(self.client, path), "PRECONDITION_REQUIRED", 428)
        self.code(self.post(self.client, path, etag='"0"'), "STALE_REVISION", 412)
        self.code(self.client.post(BASE + path, {}, content_type="application/json", HTTP_IF_MATCH='"1"'), "CSRF_FAILED")
        self.assertEqual(self.validate(artifact).status_code, 200)
        self.code(self.validate(artifact), "STALE_REVISION", 412)
        self.owner.user_permissions.clear()
        self.code(self.post(self.client, f"artifacts/{artifact['id']}/revoke/", etag='"2"'), "PERMISSION_DENIED")
        self.assertEqual(AdminArtifact.objects.get(pk=artifact["id"]).state, "ready")

    def test_foreign_owners_and_domains_are_not_found_upload_download_independent(self):
        artifact = self.ready()
        self.grant(self.scoped, "cms_research_view", "cms_research_intake", "cms_artifact_upload", "cms_artifact_download")
        scoped = self.sign_in(self.scoped)
        self.code(scoped.get(BASE + f"artifacts/{artifact['id']}/"), "NOT_FOUND", 404)
        own = self.ready(client=scoped)
        response = self.download(own, scoped)
        self.assertEqual(response.status_code, 200, response.content)
        self.scoped.user_permissions.remove(*self.scoped.user_permissions.filter(codename="cms_artifact_download"))
        self.code(self.download(own, scoped), "PERMISSION_DENIED")
        self.assertEqual(scoped.get(BASE + f"artifacts/{own['id']}/").status_code, 200)
        row = AdminArtifact.objects.get(pk=own["id"])
        row.domain = "unknown"
        row.save()
        self.code(self.download(own), "NOT_FOUND", 404)

    def test_expired_revoked_and_corrupt_artifacts_never_download(self):
        artifact = self.ready()
        row = AdminArtifact.objects.get(pk=artifact["id"])
        file = self.root / row.storage_key
        original = file.read_bytes()
        file.write_bytes(b"x" * len(original))
        self.code(self.download(artifact), "ARTIFACT_INTEGRITY", 409)
        file.write_bytes(original)
        AdminArtifact.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.code(self.download(artifact), "ARTIFACT_NOT_READY", 409)
        detail = self.client.get(BASE + f"artifacts/{row.pk}/").json()["artifact"]
        self.assertEqual((detail["state"], detail["version"]), ("expired", 2))
        self.assertEqual(self.client.get(BASE + "artifacts/?state=expired").json()["count"], 1)
        self.assertEqual(self.client.get(BASE + "artifacts/?state=ready").json()["count"], 0)
        AdminArtifact.objects.filter(pk=row.pk).update(expires_at=timezone.now() + timedelta(days=1))
        response = self.post(self.client, f"artifacts/{row.pk}/revoke/", etag='"2"')
        self.assertEqual(response.status_code, 200, response.content)
        self.code(self.download(artifact), "ARTIFACT_NOT_READY", 409)
        self.assertTrue(file.exists())

    def test_traversal_link_and_missing_storage_are_rejected(self):
        artifact = self.ready()
        row = AdminArtifact.objects.get(pk=artifact["id"])
        AdminArtifact.objects.filter(pk=row.pk).update(storage_key="../NON-SCIENTIFIC.json")
        self.code(self.download(artifact), "ARTIFACT_INTEGRITY", 409)
        row.storage_key = row.pk.hex + ".json"
        row.save()
        file = self.root / row.storage_key
        target = Path(self.temp.name) / "NON-SCIENTIFIC.json"
        target.write_bytes(file.read_bytes())
        peer = self.root / "NON-SCIENTIFIC-hardlink.json"
        peer.hardlink_to(file)
        self.code(self.download(artifact), "ARTIFACT_INTEGRITY", 409)
        peer.unlink()
        file.unlink()
        try:
            file.symlink_to(target)
        except OSError:
            # Windows may disallow creating symlinks; exercise the same metadata check explicitly.
            file.write_bytes(target.read_bytes())
            with patch("atlas.cms_artifacts._link", return_value=True):
                self.code(self.download(artifact), "ARTIFACT_STORAGE_UNAVAILABLE", 503)
        else:
            self.code(self.download(artifact), "ARTIFACT_INTEGRITY", 409)
        file.unlink()
        self.code(self.download(artifact), "ARTIFACT_UNAVAILABLE", 409)

    def test_json_format_and_all_document_bounds_reject_without_raw_errors(self):
        samples = [(b'{"x":1,"x":2}', "INVALID_JSON"), (b'{"x":NaN}', "INVALID_JSON"),
            (b'{"x":1e999}', "INVALID_JSON"), (b'\xff', "INVALID_JSON"), (b'[]', "UNSUPPORTED_SCHEMA"),
            (b'{"x":' + b'[' * 65 + b'0' + b']' * 65 + b'}', "JSON_LIMIT"),
            (json.dumps({"x": "x" * (service.MAX_STRING + 1)}).encode(), "JSON_LIMIT"),
            (b'{"x":"\\ud800"}', "JSON_LIMIT"),
            (b'{"\\ud800":1}', "JSON_LIMIT"),
            (json.dumps({"ＳＣＯＲＩＮＧ ＫＥＹ": "NON-SCIENTIFIC .invalid"}).encode(), "PROTECTED_CONTENT"),
            (json.dumps({"questions": ["NON-SCIENTIFIC .invalid"]}).encode(), "PROTECTED_CONTENT")]
        for raw, code in samples:
            with self.subTest(code=code, size=len(raw)):
                artifact = self.created(raw=raw)
                response = self.validate(artifact)
                self.assertEqual(response.status_code, 200, response.content)
                data = response.json()["artifact"]
                self.assertEqual((data["state"], data["validation_code"]), ("rejected", code))
                self.assertNotIn("NON-SCIENTIFIC .invalid", data["validation_code"])
                self.code(self.download(data), "ARTIFACT_NOT_READY", 409)
        with self.assertRaises(CMSFailure):
            service.bounded_json(b" " * (service.MAX_BYTES + 1))
        with self.assertRaises(CMSFailure):
            service.prepare_document("research_json", json.dumps(research_document(service.MAX_RECORDS + 1)).encode())
        with patch.object(service, "MAX_RECORDS", 2), self.assertRaises(CMSFailure):
            service.prepare_document("research_json", json.dumps({**research_document(2), "sources": [{"id": "a"}, {"id": "b"}]}).encode())
        with patch.object(service, "MAX_NODES", 2), self.assertRaises(CMSFailure):
            service.bounded_json(json.dumps(research_document()).encode())

    def test_schema_duplicate_and_metadata_only_assessment_protection(self):
        samples = [("research_json", {"schema_version": "unsupported", **research_document()}, "UNSUPPORTED_SCHEMA"),
            ("research_json", {**research_document(), "concepts": [{"id": "same"}, {"id": "same"}]}, "DUPLICATE_RECORD"),
            ("assessment_json", {"schema_version": "psychology-atlas-assessments-v1", "dataset_metadata": {"key": "non-scientific", "version": "1"},
                "records": [{"id": "test", "category": "instrument", "data": {"slug": "non-scientific", "description": "private manual"}}]}, "PROTECTED_CONTENT")]
        for kind, document, code in samples:
            artifact = self.created(document, kind=kind)
            self.assertEqual(self.validate(artifact).json()["artifact"]["validation_code"], code)

    def test_assessment_disguised_manual_narrative_notes_and_unknown_fields_are_rejected(self):
        base = {"schema_version": "psychology-atlas-assessments-v1", "dataset_metadata": {"key": "non-scientific", "version": "1"},
            "records": [{"id": "NON-SCIENTIFIC", "category": "instrument", "data": {"slug": "non-scientific", "name_en": "NON-SCIENTIFIC .invalid"}}]}
        for changes in ({"description": "Disguised NON-SCIENTIFIC manual"}, {"name_en": "NON-SCIENTIFIC item 1\nNON-SCIENTIFIC item 2"},
                {"metadata": {"safe_key": "NON-SCIENTIFIC manual"}}, {"notes": "NON-SCIENTIFIC narrative"}):
            document = json.loads(json.dumps(base))
            document["records"][0]["data"].update(changes)
            artifact = self.created(document, kind="assessment_json")
            result = self.validate(artifact).json()["artifact"]
            self.assertEqual((result["state"], result["validation_code"]), ("rejected", "PROTECTED_CONTENT"))

    def test_evidence_snapshot_rejects_quarantine_expiry_missing_and_wrong_kind(self):
        category = Category.objects.create(slug="non-scientific-invalid", name_en="NON-SCIENTIFIC .invalid")
        binding = resource_binding("category", category.pk)
        scope = {key: binding[key] for key in ("resource_type", "resource_id", "resource_version")}
        evidence = {"schema_version": "psychology-atlas-evidence-v1", "title": "NON-SCIENTIFIC",
            "source_url": "https://NON-SCIENTIFIC.invalid", "locator": "NON-SCIENTIFIC"}
        artifact = self.created(evidence, kind="evidence_json", **scope)
        with self.assertRaises(CMSFailure):
            service.evidence_snapshot([artifact["id"]], **scope)
        self.validate(artifact)
        AdminArtifact.objects.filter(pk=artifact["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        for ids in ([artifact["id"]], [str(uuid.uuid4())], [self.ready()["id"]]):
            with self.assertRaises(CMSFailure):
                service.evidence_snapshot(ids, **scope)

    def test_upload_size_type_unknown_fields_and_public_root_fail_closed(self):
        for kind in ("zip", "csv", "../research_json"):
            self.code(self.upload(kind=kind), "UNSUPPORTED_SCHEMA", 400)
        self.code(self.upload(raw=b"x", remote_url="https://NON-SCIENTIFIC.invalid"), "INVALID_FIELDS", 400)
        upload = SimpleUploadedFile("NON-SCIENTIFIC.json", b"{}", content_type="application/json")
        upload.size = service.MAX_BYTES + 1
        with self.assertRaises(CMSFailure):
            service.upload_artifact(self.owner.pk, self.sid, upload, "research_json", None, None, None, uuid.uuid4())
        self.assertFalse(self.root.exists())
        with override_settings(MEDIA_ROOT=self.root):
            self.code(self.upload(), "ARTIFACT_STORAGE_UNAVAILABLE", 503)
        self.assertFalse(self.root.exists())

    def test_upload_and_validation_audit_failure_roll_back_rows_and_cleanup_bytes(self):
        original = AdminAuditEvent.objects.create
        def fail(**values):
            if values["action"].startswith("artifact."):
                raise DatabaseError("NON-SCIENTIFIC .invalid private diagnostic")
            return original(**values)
        with patch.object(AdminAuditEvent.objects, "create", side_effect=fail):
            self.code(self.upload(), "WRITE_FAILED", 503)
        self.assertFalse(AdminArtifact.objects.exists())
        self.assertEqual(list(self.root.iterdir()), [])
        artifact = self.created()
        with patch.object(AdminAuditEvent.objects, "create", side_effect=fail):
            self.code(self.validate(artifact), "WRITE_FAILED", 503)
        row = AdminArtifact.objects.get(pk=artifact["id"])
        self.assertEqual((row.state, row.version), ("quarantine", 1))

    def test_download_rechecks_permissions_after_private_file_read(self):
        artifact = self.ready()
        original = service.artifact_bytes
        def revoked_after_read(row):
            raw = original(row)
            self.owner.user_permissions.clear()
            return raw
        with patch("atlas.cms_artifacts.artifact_bytes", side_effect=revoked_after_read):
            response = self.download(artifact)
        self.code(response, "PERMISSION_DENIED")
        self.assertNotIn("PRIVATE RAW", response.content.decode())
        self.assertFalse(AdminAuditEvent.objects.filter(action="artifact.download").exists())

    def test_revocation_during_pure_validation_cannot_make_artifact_ready(self):
        artifact = self.created()
        original = service.prepare_document
        def revoked_after_preparation(*args):
            result = original(*args)
            service.revoke_artifact(self.owner.pk, self.sid, artifact["id"], 1, uuid.uuid4())
            return result
        with patch("atlas.cms_artifacts.prepare_document", side_effect=revoked_after_preparation):
            self.code(self.validate(artifact), "STALE_REVISION", 412)
        row = AdminArtifact.objects.get(pk=artifact["id"])
        self.assertEqual((row.state, row.version), ("revoked", 2))

    def test_exact_evidence_binding_snapshot_and_independent_reviewer(self):
        category = Category.objects.create(slug="non-scientific-invalid", name_en="NON-SCIENTIFIC .invalid")
        binding = resource_binding("category", category.pk)
        scope = {key: binding[key] for key in ("resource_type", "resource_id", "resource_version")}
        evidence = {"schema_version": "psychology-atlas-evidence-v1", "title": "NON-SCIENTIFIC fixture",
            "source_url": "https://NON-SCIENTIFIC.invalid", "locator": "NON-SCIENTIFIC fixture only"}
        artifact = self.ready(evidence, kind="evidence_json", **scope)
        self.assertIn(artifact["id"], {row["id"] for row in self.client.get(BASE + "artifacts/").json()["results"]})
        snapshot = service.evidence_snapshot([artifact["id"]], **scope)
        self.assertEqual(snapshot, service.evidence_snapshot([artifact["id"]], **scope))
        self.assertEqual(snapshot[0]["sha256"], artifact["sha256"])
        self.assertNotIn("source_url", json.dumps(snapshot))
        for key, bad in (("resource_id", category.pk + 1), ("resource_version", "wrong")):
            with self.assertRaises(CMSFailure):
                service.evidence_snapshot([artifact["id"]], **{**scope, key: bad})
        self.grant(self.scoped, "cms_core_view", "cms_artifact_download", "cms_rights_decide", "cms_review_decide_core_rights")
        reviewer = self.sign_in(self.scoped)
        self.assertEqual(self.download(artifact, reviewer).status_code, 200)
        self.scoped.user_permissions.remove(*self.scoped.user_permissions.filter(codename="cms_core_view"))
        self.code(self.download(artifact, reviewer), "NOT_FOUND", 404)
        row = AdminArtifact.objects.get(pk=artifact["id"])
        (self.root / row.storage_key).write_bytes(b"x" * row.size)
        with self.assertRaises(CMSFailure):
            service.evidence_snapshot([artifact["id"]], **scope)
        self.post(self.client, f"artifacts/{artifact['id']}/revoke/", etag='"2"')
        with self.assertRaises(CMSFailure):
            service.evidence_snapshot([artifact["id"]], **scope)
