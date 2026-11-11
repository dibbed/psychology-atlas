"""P18 owner-only read-only health. Never claim a backup adapter exists."""
import uuid
from django.test import TestCase, override_settings

from .cms_job_models import AdminJob, AdminArtifact
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OwnerHealthTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client=self.sign_in(self.owner)

    def test_health_shows_real_database_and_job_counts_without_credentials(self):
        response=self.owner_client.get(BASE+"operations/health/")
        self.assertEqual(response.status_code,200,response.content[:350])
        data=response.json()
        self.assertEqual(data["scope"],"owner_operational_metadata")
        self.assertEqual(data["database"]["connection"],"ok")
        self.assertIn(data["database"]["vendor"],("sqlite","postgresql"))
        self.assertEqual(data["jobs"]["total"],AdminJob.objects.count())
        self.assertEqual(data["artifacts"]["total"],AdminArtifact.objects.count())
        self.assertEqual(data["backup"]["state"],"unavailable")
        self.assertNotIn("healthy",str(data["backup"]).lower())
        data_repr=str(data).lower()
        for sensitive in ("database_url","secret_key","password","dsn","storage_key","email"):
            self.assertNotIn(sensitive,data_repr)
        self.assertFalse(data["worker"]["alive_confirmed"])

    def test_case_publication_receipt_drift_is_observed_without_repair(self):
        from .cms_case_publication_models import CasePublicationPlan, CasePublicationReceipt
        from .models import ClinicalCase, CaseRevision
        case = ClinicalCase.objects.create(
            slug="p18-synthetic-receipt", title="Synthetic unpublished case",
            patient_summary="Fictional only", educational_objective="Testing only",
            is_active=False, seed_managed=False,
        )
        revision = CaseRevision.objects.create(
            case=case, version=1, status=CaseRevision.Status.DRAFT,
            title="Synthetic", patient_summary="Fictional",
            educational_objective="Testing only",
        )
        plan = CasePublicationPlan.objects.create(
            revision=revision, manifest={"test": "synthetic"},
            manifest_digest="a" * 64, status="applied", created_by=self.owner,
        )
        before = self.owner_client.get(BASE+"operations/health/")
        self.assertEqual(before.status_code, 200, before.content[:350])
        gate = before.json()["publication_receipts"]
        self.assertEqual(gate["scope"], "case_revision_structural_receipts_only")
        self.assertEqual(gate["case_plans_applied"], 1)
        self.assertEqual(gate["case_plans_missing_applied_receipt"], 1)
        self.assertEqual(gate["case_receipt_digest_mismatches"], 0)
        self.assertEqual(gate["total_observed_mismatches"], 1)
        self.assertFalse(gate["full_publication_integrity_proven"])
        self.assertEqual(gate["repair_available"], False)
        receipt = CasePublicationReceipt.objects.create(
            plan=plan, event_type="applied", revision=revision,
            manifest_digest="a" * 64, idempotency_key=uuid.uuid4(),
            actor=self.owner, actor_ref="synthetic-test",
        )
        matched = self.owner_client.get(BASE+"operations/health/").json()["publication_receipts"]
        self.assertEqual(matched["total_observed_mismatches"], 0)
        self.assertEqual(matched["case_receipts_total"], 1)
        plan.manifest_digest = "b" * 64
        plan.save(update_fields=["manifest_digest"])
        stale = self.owner_client.get(BASE+"operations/health/").json()["publication_receipts"]
        self.assertEqual(stale["case_receipt_digest_mismatches"], 1)
        self.assertEqual(stale["total_observed_mismatches"], 1)
        self.assertEqual(CasePublicationReceipt.objects.get(pk=receipt.pk).manifest_digest, "a" * 64)
        self.assertFalse(case.is_active)

    def test_source_plan_receipt_history_presence_is_observed_without_repair(self):
        from .cms_source_models import SourcePlan, SourcePlanReceipt, SourceHistory

        preview = SourcePlan.objects.create(
            operation="update", source_pk=918, fingerprint="a" * 64,
            actor=self.owner, actor_ref="synthetic",
        )
        initial = self.owner_client.get(BASE + "operations/health/")
        self.assertEqual(initial.status_code, 200, initial.content[:350])
        before = initial.json()["source_plan_receipts"]
        self.assertEqual(before["scope"], "source_plan_receipt_history_presence_only")
        self.assertEqual(before["source_plans_total"], 1)
        self.assertEqual(before["source_plans_without_receipt"], 1)
        self.assertEqual(before["source_receipts_total"], 0)
        self.assertEqual(before["total_observed_mismatches"], 0)
        self.assertFalse(before["full_source_integrity_proven"])
        self.assertFalse(before["repair_available"])

        receipt = SourcePlanReceipt.objects.create(
            plan=preview, actor=self.owner, actor_ref="synthetic",
            result={"history_ids": []},
        )
        missing = self.owner_client.get(BASE + "operations/health/").json()["source_plan_receipts"]
        self.assertEqual(missing["source_receipts_without_history"], 1)
        self.assertEqual(missing["total_observed_mismatches"], 1)

        history = SourceHistory.objects.create(
            plan=preview, source_pk=918, version=1, operation="update",
            actor=self.owner, actor_ref="synthetic",
        )
        matched = self.owner_client.get(BASE + "operations/health/").json()["source_plan_receipts"]
        self.assertEqual(matched["source_receipts_without_history"], 0)
        self.assertEqual(matched["source_histories_total"], 1)
        self.assertEqual(matched["total_observed_mismatches"], 0)

        unreceipted = SourcePlan.objects.create(
            operation="archive", source_pk=919, fingerprint="b" * 64,
            actor=self.owner, actor_ref="synthetic",
        )
        SourceHistory.objects.create(
            plan=unreceipted, source_pk=919, version=1, operation="archive",
            actor=self.owner, actor_ref="synthetic",
        )
        drift = self.owner_client.get(BASE + "operations/health/").json()["source_plan_receipts"]
        self.assertEqual(drift["source_histories_without_receipt"], 1)
        self.assertEqual(drift["total_observed_mismatches"], 1)
        self.assertEqual(SourcePlanReceipt.objects.get(pk=receipt.pk).pk, receipt.pk)
        self.assertEqual(SourceHistory.objects.get(pk=history.pk).pk, history.pk)

    def test_non_owner_denied_and_no_runtime_mutations(self):
        staff=self.user("p18-not-owner",staff=True,caps=(
            "cms_enter","cms_dashboard","cms_user_view"))
        client=self.sign_in(staff)
        self.assertEqual(client.get(BASE+"operations/health/").status_code,403)
        self.assertEqual(self.owner_client.get(BASE+"operations/health/?cmd=sql").status_code,400)
        self.assertEqual(self.post(self.owner_client,"operations/health/",{
            "restore":"anything",
        }).status_code,405)
