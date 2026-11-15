"""Synthetic W06-02 research export acceptance; permissions and raw must never be inferred."""
import hashlib
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from .cms_job_models import AdminArtifact, AdminJob
from .cms_jobs import claim_job, run_once
from .cms_models import AdminAuditEvent
from .models import ResearchDataset, ResearchRecord
from .tests_v100_p01 import BASE
from .tests_v100_p06_artifacts import ArtifactFixture, research_document


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ResearchExportAcceptanceTests(ArtifactFixture, TransactionTestCase):
    def dataset(self):
        artifact = self.ready(research_document(count=3))
        intake = self.post(self.client, "research/imports/", {
            "artifact_id": artifact["id"], "request_key": str(uuid.uuid4())})
        self.assertEqual(intake.status_code, 202, intake.content)
        self.assertEqual(run_once().status, "succeeded")
        return ResearchDataset.objects.get()

    def request_export(self, *, kind="dataset", target_id=None, projection=None, key=None, client=None):
        dataset = ResearchDataset.objects.first()
        body = {"target_kind": kind, "target_id": target_id if target_id is not None else dataset.pk,
            "projection": projection if projection is not None else ["id", "section", "external_id", "staging_state"],
            "request_key": key or str(uuid.uuid4())}
        return self.post(client or self.client, "research/exports/", body), body

    def test_dataset_export_snapshot_checksum_exact_projection_and_private_download(self):
        dataset = self.dataset()
        response, body = self.request_export()
        self.assertEqual(response.status_code, 202, response.content)
        job_id = response.json()["job"]["id"]
        manifest_id = AdminJob.objects.get(pk=job_id).artifact_id
        self.assertEqual(self.client.get(BASE + f"artifacts/{manifest_id}/download/?purpose=research_review").status_code, 404)
        self.assertEqual(AdminAuditEvent.objects.filter(action="research.exported").count(), 0)
        self.assertEqual(self.post(self.client, "research/exports/", body).json()["job"]["id"], job_id)
        result = run_once()
        self.assertEqual(result.status, "succeeded", result.error_code)
        job = AdminJob.objects.get(pk=job_id)
        self.assertEqual(job.output_artifact.kind, "research_export_json")
        self.assertEqual(job.output_artifact.domain, "research")
        self.assertEqual(job.output_artifact.state, "ready")
        download = self.client.get(BASE + f"artifacts/{job.output_artifact_id}/download/?purpose=research_review")
        self.assertEqual(download.status_code, 200, download.content)
        raw = download.content
        self.assertEqual(job.output_artifact.sha256, hashlib.sha256(raw).hexdigest())
        doc = json.loads(raw)
        self.assertEqual(doc["schema_version"], "psychology-atlas-research-export-v1")
        self.assertEqual(doc["dataset"]["source_sha256"], dataset.source_sha256)
        self.assertEqual(doc["projection"], body["projection"])
        self.assertEqual(len(doc["records"]), 3)
        self.assertEqual(set(doc["records"][0]), set(body["projection"]))
        self.assertNotIn("source_ids", raw.decode())
        self.assertNotIn("payload", raw.decode())
        self.assertNotIn("raw_text", raw.decode())
        self.assertEqual(ResearchDataset.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="research.exported").count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="artifact.download").count(), 1)

    def test_single_record_selection_and_stable_snapshot(self):
        dataset = self.dataset()
        record = dataset.records.order_by("pk").first()
        response, body = self.request_export(kind="record", target_id=record.pk,
            projection=["id", "external_id", "staging_state"])
        self.assertEqual(response.status_code, 202, response.content)
        original = record.external_id
        # Mutating canonical metadata after selection cannot mutate the already selected snapshot.
        ResearchRecord.objects.filter(pk=record.pk).update(external_id="later-value")
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        raw = self.client.get(BASE + f"artifacts/{job.output_artifact_id}/download/?purpose=research_review").content
        doc = json.loads(raw)
        self.assertEqual(len(doc["records"]), 1)
        self.assertEqual(doc["records"][0], {"id": record.pk, "external_id": original, "staging_state": "unmapped"})
        self.assertEqual(doc["target"], {"kind": "record", "id": record.pk})

    def test_bad_projection_and_input_refuse_before_job(self):
        self.dataset()
        for field in ("payload", "raw_text", "raw_document", "source_ids", "mapping", "formula", "__dict__"):
            with self.subTest(field=field):
                response, _ = self.request_export(projection=["id", field])
                self.assertEqual(response.status_code, 400, response.content)
        for projection in ([], ["id", "id"], [3], "id"):
            with self.subTest(projection=projection):
                response, _ = self.request_export(projection=projection)
                self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(AdminJob.objects.filter(kind="research_export").exists())

    def test_sensitive_projection_requires_raw_read_capability(self):
        dataset = self.dataset()
        owner = self.user("restricted-exporter", staff=True, caps=(
            "cms_enter", "cms_research_view", "cms_research_export", "cms_artifact_download"))
        # Owner cannot borrow another user's dataset even with export permission.
        other = self.sign_in(owner)
        response, _ = self.request_export(client=other)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(AdminJob.objects.filter(kind="research_export").exists())
        allowed, _ = self.request_export(projection=["id", "name_en"])
        self.assertEqual(allowed.status_code, 202)

    def test_scope_and_download_rechecked_after_revoke(self):
        dataset = self.dataset()
        response, body = self.request_export()
        self.assertEqual(response.status_code, 202)
        job = run_once()
        self.assertEqual(job.status, "succeeded")
        artifact = job.output_artifact
        stale = self.client.get(BASE + f"artifacts/{artifact.pk}/download/?purpose=research_review")
        self.assertEqual(stale.status_code, 200)
        revoke = self.post(self.client, f"artifacts/{artifact.pk}/revoke/", etag=f'"{artifact.version}"')
        self.assertEqual(revoke.status_code, 200, revoke.content)
        denied = self.client.get(BASE + f"artifacts/{artifact.pk}/download/?purpose=research_review")
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(self.post(self.client, "research/exports/", body).json()["job"]["id"], response.json()["job"]["id"])

    def test_expired_output_refused_at_download(self):
        self.dataset()
        response, _ = self.request_export()
        self.assertEqual(response.status_code, 202)
        job = run_once()
        AdminArtifact.objects.filter(pk=job.output_artifact_id).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.get(BASE + f"artifacts/{job.output_artifact_id}/download/?purpose=research_review").status_code, 409)

    def test_revoke_request_prevents_worker_export(self):
        self.dataset()
        response, _ = self.request_export()
        self.assertEqual(response.status_code, 202)
        artifact = AdminJob.objects.get(pk=response.json()["job"]["id"]).artifact
        revoke = self.post(self.client, f"artifacts/{artifact.pk}/revoke/", etag=f'"{artifact.version}"')
        self.assertEqual(revoke.status_code, 200)
        job = run_once()
        self.assertEqual(job.status, "failed")
        self.assertIsNone(job.output_artifact_id)

    def test_idempotency_same_key_conflicting_selection(self):
        dataset = self.dataset()
        key = str(uuid.uuid4())
        first, _ = self.request_export(key=key)
        self.assertEqual(first.status_code, 202)
        second, _ = self.request_export(key=key, projection=["id", "section"])
        self.assertEqual(second.status_code, 409)
        self.assertEqual(AdminJob.objects.filter(kind="research_export").count(), 1)

    def test_output_private_and_cross_scope_hidden(self):
        dataset = self.dataset()
        response, _ = self.request_export()
        self.assertEqual(response.status_code, 202)
        job = run_once()
        outsider = self.user("outsider-export", staff=True, caps=(
            "cms_enter", "cms_research_view", "cms_research_export", "cms_artifact_download"))
        client = self.sign_in(outsider)
        self.assertEqual(client.get(BASE + "research/datasets/").json()["count"], 0)
        self.assertEqual(client.get(BASE + "jobs/").json()["count"], 0)
        self.assertEqual(client.get(BASE + f"jobs/{job.pk}/").status_code, 404)
        self.assertEqual(client.get(BASE + f"artifacts/{job.output_artifact_id}/").status_code, 404)
        self.assertEqual(client.get(BASE + f"artifacts/{job.output_artifact_id}/download/?purpose=research_review").status_code, 404)

    def test_reconcile_after_crash_is_one_receipt(self):
        self.dataset()
        response, _ = self.request_export()
        self.assertEqual(response.status_code, 202)
        from .cms_jobs import checkpoint_job
        from . import cms_research_export
        original = cms_research_export.checkpoint_job
        def interrupt(job_id, token, effect):
            value = original(job_id, token, effect)
            if value.checkpoint.get("complete"):
                raise RuntimeError("simulated crash after output committed")
            return value
        with patch.object(cms_research_export, "checkpoint_job", side_effect=interrupt):
            interrupted = run_once()
        self.assertEqual(interrupted.status, "running")
        self.assertEqual(AdminArtifact.objects.filter(kind="research_export_json",state="ready").count(), 1)
        AdminJob.objects.filter(kind="research_export").update(lease_expires_at=timezone.now()-timedelta(seconds=1))
        result = run_once()
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(AdminArtifact.objects.filter(kind="research_export_json").count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="research.exported").count(), 1)

    def test_scoped_exporter_raw_denial_and_permission_revoke_after_export(self):
        from django.contrib.auth.models import Permission
        user = self.user("scoped-exporter", staff=True, caps=(
            "cms_enter", "cms_research_view", "cms_research_intake", "cms_research_export",
            "cms_artifact_upload", "cms_artifact_download"))
        client = self.sign_in(user)
        uploaded = self.upload(research_document(count=2), client=client)
        self.assertEqual(uploaded.status_code, 201, uploaded.content)
        artifact = uploaded.json()["artifact"]
        self.assertEqual(self.post(client, f"artifacts/{artifact['id']}/validate/", etag='"1"').status_code, 200)
        self.assertEqual(self.post(client, "research/imports/", {
            "artifact_id": artifact["id"], "request_key": str(uuid.uuid4())}).status_code, 202)
        self.assertEqual(run_once().status, "succeeded")
        dataset = ResearchDataset.objects.get(source_sha256=artifact["sha256"])
        denied = self.post(client, "research/exports/", {
            "target_kind": "dataset", "target_id": dataset.pk,
            "projection": ["id", "name_en"], "request_key": str(uuid.uuid4())})
        self.assertEqual(denied.status_code, 403, denied.content)
        raw_permission = Permission.objects.get(codename="cms_research_raw_read")
        user.user_permissions.add(raw_permission)
        sensitive_request = self.post(client, "research/exports/", {
            "target_kind": "dataset", "target_id": dataset.pk,
            "projection": ["id", "name_en"], "request_key": str(uuid.uuid4())})
        self.assertEqual(sensitive_request.status_code, 202, sensitive_request.content)
        sensitive_job_id = sensitive_request.json()["job"]["id"]
        user.user_permissions.remove(raw_permission)
        self.assertEqual(client.get(BASE + f"jobs/{sensitive_job_id}/").status_code, 403)
        self.assertEqual(client.get(BASE + "jobs/?status=queued").json()["count"], 0)
        self.assertEqual(client.get(BASE + "artifacts/?kind=research_request_json").json()["count"], 0)
        failed = run_once()
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error_code, "PERMISSION_DENIED")
        self.assertIsNone(failed.output_artifact_id)
        user.user_permissions.add(raw_permission)
        retry = self.post(client, f"jobs/{failed.pk}/retry/", etag=f'"{failed.version}"')
        self.assertEqual(retry.status_code, 200, retry.content)
        sensitive_completed = run_once()
        self.assertEqual(sensitive_completed.status, "succeeded", sensitive_completed.error_code)
        sensitive_path = BASE + f"artifacts/{sensitive_completed.output_artifact_id}/download/?purpose=research_review"
        self.assertEqual(client.get(sensitive_path).status_code, 200)
        user.user_permissions.remove(raw_permission)
        self.assertEqual(client.get(sensitive_path).status_code, 403)
        self.assertEqual(client.get(BASE + f"artifacts/{sensitive_completed.output_artifact_id}/").status_code, 403)
        self.assertEqual(client.get(BASE + "artifacts/?kind=research_export_json").json()["count"], 0)
        queued = self.post(client, "research/exports/", {
            "target_kind": "dataset", "target_id": dataset.pk,
            "projection": ["id", "external_id"], "request_key": str(uuid.uuid4())})
        self.assertEqual(queued.status_code, 202, queued.content)
        completed = run_once()
        self.assertEqual(completed.status, "succeeded", completed.error_code)
        route = BASE + f"artifacts/{completed.output_artifact_id}/download/?purpose=research_review"
        self.assertEqual(client.get(route).status_code, 200)
        user.user_permissions.remove(Permission.objects.get(codename="cms_research_export"))
        self.assertEqual(client.get(route).status_code, 403)

    def test_worker_permission_revoke_and_prepare_interruption_retry(self):
        from . import cms_research_export
        self.dataset()
        queued, _ = self.request_export()
        self.assertEqual(queued.status_code, 202)
        original = cms_research_export.checkpoint_job

        def interrupt(job_id, token, effect):
            result = original(job_id, token, effect)
            if result.checkpoint.get("output_prepared") and not result.checkpoint.get("complete"):
                raise RuntimeError("synthetic interruption before private file commit")
            return result

        with patch.object(cms_research_export, "checkpoint_job", side_effect=interrupt):
            failed = run_once()
        self.assertEqual(failed.status, "failed")
        output_id = failed.output_artifact_id
        self.assertIsNotNone(output_id)
        self.assertEqual(self.post(self.client, f"jobs/{failed.pk}/retry/", etag=f'"{failed.version}"').status_code, 200)
        completed = run_once()
        self.assertEqual(completed.status, "succeeded", completed.error_code)
        self.assertEqual(completed.output_artifact_id, output_id)
        self.assertEqual(AdminArtifact.objects.filter(kind="research_export_json").count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="research.exported").count(), 1)

    def test_rejected_targets_and_private_file_tampering(self):
        from .cms_artifacts import _path
        self.dataset()
        for kind, identifier in (("wrong", 1), ([], 1), ("dataset", 999999), ("record", 999999), ("dataset", "1"), ("dataset", -1)):
            response, _ = self.request_export(kind=kind, target_id=identifier)
            self.assertIn(response.status_code, (400, 404), response.content)
        self.assertFalse(AdminJob.objects.filter(kind="research_export").exists())
        response, _ = self.request_export()
        self.assertEqual(response.status_code, 202)
        job = run_once()
        self.assertEqual(job.status, "succeeded")
        target = _path(job.output_artifact)
        raw = target.read_bytes()
        target.write_bytes(b"x" + raw[1:])
        self.assertEqual(self.client.get(BASE +
            f"artifacts/{job.output_artifact_id}/download/?purpose=research_review").status_code, 409)
        self.assertEqual(AdminAuditEvent.objects.filter(action="artifact.download").count(), 0)
