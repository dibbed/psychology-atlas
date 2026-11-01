"""NON-SCIENTIFIC private evidence; no real legal permission or source is created."""
import json
from datetime import timedelta
from tempfile import TemporaryDirectory
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from .cms_governance import resource_binding, rights_eligibility
from .cms_job_models import AdminArtifact, ResearchRecordDecision
from .cms_review_models import ReviewPolicy
from .cms_audit import attribution
from .cms_content import digest
from .models import Category, SourceReference, ResearchDataset, ResearchRecord
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PrivateGovernanceEvidenceTests(SecurityFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        ReviewPolicy.objects.get_or_create(pk=1)
        self.temp = TemporaryDirectory(prefix="atlas-p06-NON-SCIENTIFIC-")
        self.addCleanup(self.temp.cleanup)
        config = override_settings(CMS_ARTIFACT_ROOT=self.temp.name)
        config.enable()
        self.addCleanup(config.disable)
        self.client = self.sign_in(self.owner)
        self.category = Category.objects.create(slug="non-scientific-private-evidence", name_en="NON-SCIENTIFIC fixture")
        self.binding = resource_binding("category", self.category.pk)

    def artifact(self):
        raw = json.dumps({"schema_version": "psychology-atlas-evidence-v1", "title": "NON-SCIENTIFIC synthetic evidence",
            "source_url": "https://private-fixture.invalid/NOT-LEGAL-EVIDENCE", "locator": "Isolated test only"}).encode()
        response = self.client.post(BASE + "artifacts/", {"file": SimpleUploadedFile("NON-SCIENTIFIC.json", raw, "application/json"),
            "kind": "evidence_json", "resource_type": "category", "resource_id": str(self.category.pk),
            "resource_version": self.binding["resource_version"]}, HTTP_X_CSRFTOKEN=self.csrf(self.client))
        self.assertEqual(response.status_code, 201, response.content)
        artifact = response.json()["artifact"]
        validated = self.post(self.client, f"artifacts/{artifact['id']}/validate/", etag=response["ETag"])
        self.assertEqual(validated.status_code, 200, validated.content)
        return validated.json()["artifact"]

    def proposal(self, artifact):
        evidence = [{"artifact_id": artifact["id"], "locator": "NON-SCIENTIFIC fixture locator"}]
        day = timezone.localdate().isoformat()
        return {"resource_type": "category", "resource_id": self.category.pk, "resource_version": self.binding["resource_version"],
            "material": "metadata", "intended_use": "public_display", "status": "allowed", "evidence": evidence,
            "rightsholder": "NON-SCIENTIFIC synthetic holder", "holder_identification": "NOT a legal identity",
            "holder_evidence": evidence, "reviewed_on": day, "effective_on": day,
            "limitations": "Only isolated test data; NEVER a real permission", "public_access": "unknown"}

    def approved(self, artifact):
        response = self.post(self.client, "governance/rights/", self.proposal(artifact))
        self.assertEqual(response.status_code, 201, response.content)
        record = response.json()["record"]
        assigned = self.post(self.client, f"governance/rights/{record['id']}/assign/", {"reviewer_id": self.owner.pk}, etag=response["ETag"])
        self.assertEqual(assigned.status_code, 200, assigned.content)
        decision = self.post(self.client, f"governance/rights/{record['id']}/decide/",
            {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED", "self_review_ack": True}, etag=assigned["ETag"])
        self.assertEqual(decision.status_code, 200, decision.content)
        return decision.json()["record"]

    def rights(self):
        return rights_eligibility("category", self.category.pk, self.binding["resource_version"], "metadata", "public_display")

    def test_private_evidence_review_and_revoke_stales_effective_decision(self):
        artifact = self.artifact()
        record = self.approved(artifact)
        self.assertTrue(self.rights()["permitted"])
        download = self.client.get(BASE + f"artifacts/{artifact['id']}/download/?purpose=rights_review")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Cache-Control"], "no-store")
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        revoked = self.post(self.client, f"artifacts/{artifact['id']}/revoke/", etag=f'"{artifact["version"]}"')
        self.assertEqual(revoked.status_code, 200, revoked.content)
        self.assertFalse(self.rights()["permitted"])
        detail = self.client.get(BASE + f"governance/rights/{record['id']}/").json()["record"]
        self.assertIn("ARTIFACT_NOT_READY", detail["blockers"])
        self.assertEqual(self.client.get(BASE + f"artifacts/{artifact['id']}/download/?purpose=rights_review").status_code, 409)
        self.assertEqual(SourceReference.objects.count(), 0)

    def test_expired_private_evidence_never_grants_permission(self):
        artifact = self.artifact()
        self.approved(artifact)
        AdminArtifact.objects.filter(pk=artifact["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(self.rights()["permitted"])

    def test_other_resource_scope_and_missing_file_permission_are_denied(self):
        artifact = self.artifact()
        other = Category.objects.create(slug="non-scientific-other-scope", name_en="NON-SCIENTIFIC other")
        payload = {**self.proposal(artifact), "resource_id": other.pk, "resource_version": resource_binding("category", other.pk)["resource_version"]}
        response = self.post(self.client, "governance/rights/", payload)
        self.assertEqual(response.status_code, 400, response.content)
        editor = self.user("non-scientific-no-file-access", staff=True, caps=("cms_enter", "cms_core_view", "cms_core_edit"))
        client = self.sign_in(editor)
        response = self.post(client, "governance/rights/", self.proposal(artifact))
        self.assertIn(response.status_code, (403, 404), response.content)

    def test_quarantine_and_corrupted_file_cannot_become_legal_evidence(self):
        artifact = self.artifact()
        AdminArtifact.objects.filter(pk=artifact["id"]).update(state="quarantine")
        response = self.post(self.client, "governance/rights/", self.proposal(artifact))
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(self.rights()["permitted"])
        row = AdminArtifact.objects.get(pk=artifact["id"])
        row.state = "ready"
        row.save()
        (Path(self.temp.name) / row.storage_key).write_bytes(b"NON-SCIENTIFIC damaged fixture")
        response = self.post(self.client, "governance/rights/", self.proposal(artifact))
        self.assertIn(response.status_code, (400, 409), response.content)
        self.assertFalse(self.rights()["permitted"])

    def test_private_derived_source_mapping_stales_plan_and_blocks_unused_delete(self):
        source = SourceReference.objects.create(title="NON-SCIENTIFIC mapping fixture", url="https://source-fixture.invalid/map")
        before = self.post(self.client, "sources/preview/", {"operation": "delete", "source_id": source.pk})
        self.assertEqual(before.status_code, 201, before.content)
        plan = before.json()
        self.assertTrue(plan["preview"]["can_apply"])
        dataset = ResearchDataset.objects.create(key="non-scientific-derived-archive", source_filename="NON-SCIENTIFIC.json",
            source_sha256="f" * 64, raw_document={}, is_active=False, ingestion_audit={"cms_owner_ref": attribution(self.owner.pk)})
        record = ResearchRecord.objects.create(dataset=dataset, section="sources", external_id="NON-SCIENTIFIC", payload={})
        ResearchRecordDecision.objects.create(record=record, sequence=1, action="map", mapping={"source_ids": [source.pk]},
            payload_digest=digest(record.payload), actor=self.owner, actor_ref=attribution(self.owner.pk), reason="RESEARCH_MAP")
        stale = self.post(self.client, f"sources/plans/{plan['id']}/apply/", etag=before["ETag"])
        self.assertEqual(stale.status_code, 412, stale.content)
        after = self.post(self.client, "sources/preview/", {"operation": "delete", "source_id": source.pk})
        self.assertEqual(after.status_code, 201, after.content)
        self.assertFalse(after.json()["preview"]["can_apply"])
        self.assertTrue(SourceReference.objects.filter(pk=source.pk).exists())
        reader = self.user("non-scientific-source-reader", staff=True, caps=("cms_enter", "cms_source_view", "cms_research_view"))
        client = self.sign_in(reader)
        self.assertEqual(client.get(BASE + f"sources/{source.pk}/").status_code, 403)
        bibliography = client.get(BASE + "sources/")
        self.assertEqual(bibliography.status_code, 200)
        self.assertIsNone(bibliography.json()["results"][0]["usage_count"])

    def test_external_source_ids_are_dataset_local_not_private_cross_dataset_links(self):
        source = SourceReference.objects.create(title="NON-SCIENTIFIC source A", url="https://source-a.invalid/")
        legacy = ResearchDataset.objects.create(key="non-scientific-legacy-A", source_filename="A.json", source_sha256="1" * 64)
        ResearchRecord.objects.create(dataset=legacy, section="sources", external_id="S1", payload={},
            promoted_model="atlas.sourcereference", promoted_pk=source.pk)
        private = ResearchDataset.objects.create(key="non-scientific-private-B", source_filename="B.json", source_sha256="2" * 64,
            ingestion_audit={"cms_owner_ref": attribution(self.owner.pk)})
        ResearchRecord.objects.create(dataset=private, section="concepts", external_id="B", source_ids=["S1"], payload={"source_id": "S1"})
        reader = self.user("non-scientific-dataset-local", staff=True, caps=("cms_enter", "cms_source_view", "cms_research_view"))
        client = self.sign_in(reader)
        response = client.get(BASE + f"sources/{source.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn(str(private.pk) + ":payload", str(response.json()["impact"]))
