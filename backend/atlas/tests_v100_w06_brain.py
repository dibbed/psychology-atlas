"""Synthetic Brain CMS intake acceptance. No scientific approval or canonical publication."""
import hashlib
import json
import uuid
from datetime import timedelta

from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from . import cms_artifacts
from .cms_job_models import AdminArtifact, AdminJob
from .cms_jobs import run_once
from .models import BrainAnatomicalEntity, BrainNetwork, ResearchDataset, ResearchRecord
from .tests_v100_p01 import BASE
from .tests_v100_p06_artifacts import ArtifactFixture


def brain_document():
    return {
        "schema_version": "brain-staging-v1",
        "dataset_metadata": {"key": "synthetic-brain", "version": "v1"},
        "records": [
            {"id": "anatomy-one", "category": "anatomy", "slug": "synthetic-cortex",
             "name_en": "Synthetic Cortex", "kind": "structure", "laterality": "bilateral",
             "source_version": "synthetic-v1", "spatial_scope": "synthetic-only",
             "review_status": "unreviewed", "source_ids": ["unverified-source"],
             "source_notes": {"unverified-source": "not an independently verified citation"}},
        ],
    }


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BrainCMSIntakeTests(ArtifactFixture, TransactionTestCase):
    def ready_brain(self, doc=None, raw=None):
        return self.ready(raw=raw or json.dumps(doc or brain_document(), ensure_ascii=False).encode(), kind="brain_json")

    def test_http_worker_staging_preserves_raw_and_never_publishes(self):
        doc = brain_document()
        raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode()
        artifact = self.ready_brain(raw=raw)
        key = str(uuid.uuid4())
        response = self.post(self.client, "research/imports/", {"artifact_id": artifact["id"], "request_key": key})
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(self.post(self.client, "research/imports/", {"artifact_id": artifact["id"], "request_key": key}).json()["job"]["id"], response.json()["job"]["id"])
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        dataset = ResearchDataset.objects.get(pk=job.result["dataset_id"])
        self.assertEqual(dataset.raw_text.encode(), raw)
        self.assertEqual(dataset.raw_document, doc)
        self.assertEqual(dataset.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertFalse(dataset.is_active)
        self.assertEqual(dataset.ingestion_audit["brain_staging_schema"], "brain-staging-v1")
        record = dataset.records.get()
        self.assertEqual((record.section, record.external_id, record.review_status, record.verification_status),
                         ("brain_anatomy", "anatomy-one", "unreviewed", "staging_only"))
        self.assertEqual(record.payload, doc["records"][0])
        self.assertEqual((BrainAnatomicalEntity.objects.count(), BrainNetwork.objects.count()), (0, 0))
        self.assertEqual(self.client.get(BASE + "research/datasets/").json()["count"], 1)
        self.assertEqual(self.client.get(BASE + f"research/datasets/{dataset.pk}/records/").status_code, 200)
        detail = self.client.get(BASE + f"research/datasets/{dataset.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["dataset"]["brain_staging"])
        self.assertEqual(detail.json()["brain_validation"]["canonical_writes"], 0)
        self.assertIn("unresolved_source", {issue["code"] for issue in detail.json()["brain_validation"]["issues"]})
        self.assertNotIn("source_notes", detail.content.decode())
        self.assertNotIn("source_notes", self.client.get(BASE + f"research/records/{record.pk}/").content.decode())

    def test_invalid_structures_rejected_before_job(self):
        for doc in ({"schema_version": "wrong", "dataset_metadata": {"key": "k", "version": "v"}, "records": []},
                    {**brain_document(), "records": [{"id": "one", "category": "anatomy", "function": "unsupported"}]},
                    {**brain_document(), "records": [{"id": "one", "category": "anatomy", "source_ids": ["x", 2]}]},
                    {**brain_document(), "records": [{"id": "x", "category": "anatomy"}, {"id": "x", "category": "anatomy"}]},
                    {**brain_document(), "records": [42]}):
            with self.subTest(doc=doc):
                artifact = self.created(doc, kind="brain_json")
                response = self.validate(artifact)
                self.assertEqual(response.json()["artifact"]["state"], "rejected")
        self.assertFalse(AdminJob.objects.exists())
        self.assertFalse(ResearchDataset.objects.exists())

    def test_invalid_json_and_depth_limit(self):
        artifact = self.created(raw=b'{"schema_version": ', kind="brain_json")
        self.assertEqual(self.validate(artifact).json()["artifact"]["validation_code"], "INVALID_JSON")
        deep = {"data": []}
        node = deep["data"]
        for _ in range(70):
            nested = []
            node.append(nested)
            node = nested
        artifact = self.created(deep, kind="brain_json")
        self.assertEqual(self.validate(artifact).json()["artifact"]["validation_code"], "JSON_LIMIT")

    def test_duplicate_sha_and_request_reuse_staging_without_rewrite(self):
        artifact = self.ready_brain()
        first = self.post(self.client, "research/imports/", {"artifact_id": artifact["id"], "request_key": str(uuid.uuid4())})
        run_once()
        dataset = ResearchDataset.objects.get()
        original = list(ResearchRecord.objects.values())
        duplicate = self.post(self.client, "research/imports/", {"artifact_id": artifact["id"], "request_key": str(uuid.uuid4())})
        run_once()
        self.assertTrue(AdminJob.objects.get(pk=duplicate.json()["job"]["id"]).result["duplicate"])
        self.assertEqual(list(ResearchRecord.objects.values()), original)
        self.assertEqual(ResearchDataset.objects.count(), 1)

    def test_revoke_prevents_worker_effect_and_private_http(self):
        artifact = self.ready_brain()
        response = self.post(self.client, "research/imports/", {"artifact_id": artifact["id"], "request_key": str(uuid.uuid4())})
        revoked = self.post(self.client, f'artifacts/{artifact["id"]}/revoke/', etag=f'"{artifact["version"]}"')
        self.assertEqual(revoked.status_code, 200, revoked.content)
        job = run_once()
        self.assertEqual(job.status, "failed")
        self.assertFalse(ResearchDataset.objects.exists())
        self.assertNotEqual(self.client.get(BASE + f'artifacts/{artifact["id"]}/download/?purpose=research_review').status_code, 200)

    def test_oversized_upload_never_records_artifact(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        oversized = SimpleUploadedFile("oversize.json", b"x" * (cms_artifacts.MAX_BYTES + 1), content_type="application/json")
        response = self.client.post(BASE + "artifacts/", {"file": oversized, "kind": "brain_json"}, HTTP_X_CSRFTOKEN=self.csrf(self.client))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AdminArtifact.objects.exists())

    def test_unauthorized_role_cannot_see_brain_staging(self):
        artifact = self.ready_brain()
        self.post(self.client, "research/imports/", {"artifact_id": artifact["id"], "request_key": str(uuid.uuid4())})
        run_once()
        role = self.user("synthetic-unprivileged-brain", staff=True, caps=("cms_enter", "cms_research_view", "cms_research_intake"))
        other = self.sign_in(role)
        self.assertEqual(other.get(BASE + "research/datasets/").json()["count"], 0)
        self.assertEqual(other.get(BASE + f"research/datasets/{ResearchDataset.objects.get().pk}/").status_code, 404)
        self.assertEqual(other.get(BASE + f"research/records/{ResearchRecord.objects.get().pk}/").status_code, 404)
        self.assertEqual(other.get(BASE + f"artifacts/{artifact['id']}/").status_code, 404)

    def test_crash_after_committed_chunk_resumes_with_lease_fencing(self):
        from unittest.mock import patch
        from .cms_jobs import checkpoint_job, claim_job

        doc = brain_document()
        doc["records"] = [
            {**doc["records"][0], "id": f"record-{i}", "slug": f"synthetic-{i}"}
            for i in range(105)
        ]
        artifact = self.ready_brain(doc)
        self.post(self.client, "research/imports/", {"artifact_id": artifact["id"], "request_key": str(uuid.uuid4())})
        first = claim_job()
        def interrupt(job_id, lease, effect):
            result = checkpoint_job(job_id, lease, effect)
            if result.progress_done == 100:
                raise RuntimeError("synthetic post-commit worker interruption")
            return result
        with patch("atlas.cms_jobs.checkpoint_job", side_effect=interrupt):
            with self.assertRaises(RuntimeError):
                cms_artifacts.process_intake(first.pk, first.lease_token)
        self.assertEqual(ResearchRecord.objects.count(), 100)
        AdminJob.objects.filter(pk=first.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
        second = claim_job()
        self.assertEqual(first.pk, second.pk)
        with self.assertRaises(Exception):
            cms_artifacts.process_intake(first.pk, first.lease_token)
        result = cms_artifacts.process_intake(second.pk, second.lease_token)
        self.assertEqual(result["records"], 105)
        self.assertEqual(ResearchRecord.objects.count(), 105)
        self.assertEqual(BrainAnatomicalEntity.objects.count(), 0)

    def test_brain_edit_revocation_blocks_queued_job(self):
        from django.contrib.auth.models import Permission
        # The scoped curator may upload only while every required capability is current.
        self.grant(self.scoped, "cms_research_view", "cms_research_intake", "cms_artifact_upload",
                   "cms_brain_view", "cms_brain_edit")
        client = self.sign_in(self.scoped)
        raw = json.dumps(brain_document()).encode()
        artifact = self.created(raw=raw, kind="brain_json", client=client)
        response = self.post(client, f"artifacts/{artifact['id']}/validate/", etag='"1"')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.post(client, "research/imports/", {"artifact_id": artifact["id"],
            "request_key": str(uuid.uuid4())}).status_code, 202)
        self.scoped.user_permissions.remove(*Permission.objects.filter(codename="cms_brain_edit"))
        job = run_once()
        self.assertEqual(job.status, "failed")
        self.assertEqual(ResearchDataset.objects.count(), 0)
