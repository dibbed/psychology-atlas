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

    def test_worker_poll_observation_is_not_process_liveness_attestation(self):
        from datetime import timedelta
        from unittest.mock import patch
        from django.core.management import call_command
        from django.utils import timezone
        from .cms_worker_pulse import CmsWorkerPulse

        before = self.owner_client.get(BASE + "operations/health/")
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json()["worker"]["successful_polls_recorded"], 0)
        self.assertFalse(before.json()["worker"]["poll_recently_observed"])
        self.assertFalse(before.json()["worker"]["alive_confirmed"])

        # A real management-command invocation, with no job available, must
        # still record a committed successful queue poll.
        call_command("cms_worker", once=True)
        observed = self.owner_client.get(BASE + "operations/health/")
        self.assertEqual(observed.status_code, 200, observed.content[:500])
        worker = observed.json()["worker"]
        self.assertEqual(worker["successful_polls_recorded"], 1)
        self.assertTrue(worker["poll_recently_observed"])
        self.assertIsNotNone(worker["last_successful_poll_at"])
        self.assertGreaterEqual(worker["fresh_window_seconds"], 120)
        self.assertFalse(worker["alive_confirmed"])
        self.assertIn("NOT_A_LIVENESS_PROOF", worker["notice"])
        self.assertEqual(CmsWorkerPulse.objects.count(), 1)

        call_command("cms_worker", once=True)
        again = self.owner_client.get(BASE + "operations/health/").json()["worker"]
        self.assertEqual(again["successful_polls_recorded"], 2)
        self.assertEqual(CmsWorkerPulse.objects.count(), 1)

        past = timezone.now() - timedelta(hours=1)
        CmsWorkerPulse.objects.filter(pk=1).update(last_successful_poll_at=past)
        old = self.owner_client.get(BASE + "operations/health/").json()["worker"]
        self.assertFalse(old["poll_recently_observed"])
        self.assertFalse(old["alive_confirmed"])
        self.assertEqual(old["successful_polls_recorded"], 2)

        # Failed polling must never fabricate evidence.
        with patch("atlas.management.commands.cms_worker.run_once",
                   side_effect=Exception("test-only synthetic failure")):
            with self.assertRaises(Exception):
                call_command("cms_worker", once=True)
        self.assertEqual(CmsWorkerPulse.objects.get(pk=1).successful_polls, 2)
        self.assertNotIn("test-only synthetic failure", str(old))

    def test_bounded_queue_triage_distinguishes_overdue_work_from_scheduled_retries(self):
        from datetime import timedelta
        from django.utils import timezone

        empty = self.owner_client.get(BASE+"operations/health/")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["queue_triage"]["overdue_ready_count"], 0)
        self.assertFalse(empty.json()["queue_triage"]["requires_operator_review"])
        self.assertFalse(empty.json()["queue_triage"]["worker_outage_proven"])

        now = timezone.now()
        artifact = AdminArtifact.objects.create(
            kind="research_json", domain="research", owner=self.owner,
            owner_ref="synthetic", state="ready", storage_key="p18-triage-fixture",
            filename="fixture.json", sha256="e"*64, size=10,
            expires_at=now+timedelta(days=1),
        )
        base = {"kind": "research_intake", "actor": self.owner, "actor_ref": "synthetic",
                "policy_version": 1, "artifact": artifact, "payload_digest": "d"*64,
                "attempt": 0}
        for status, when, missing_lease in (
            ("queued", now-timedelta(minutes=12), False),
            ("queued", now-timedelta(minutes=2), False),
            ("queued", now+timedelta(hours=1), False),
            ("running", now-timedelta(minutes=5), True),
        ):
            AdminJob.objects.create(
                **base, status=status, request_key=uuid.uuid4(), available_at=when,
                lease_token=None if missing_lease else uuid.uuid4(),
                lease_expires_at=None if missing_lease else now+timedelta(minutes=1),
            )
        response = self.owner_client.get(BASE+"operations/health/")
        self.assertEqual(response.status_code, 200, response.content[:450])
        triage = response.json()["queue_triage"]
        self.assertEqual(triage["threshold_seconds"], 600)
        self.assertEqual(triage["ready_count"], 2)
        self.assertEqual(triage["scheduled_future_count"], 1)
        self.assertEqual(triage["overdue_ready_count"], 1)
        self.assertEqual(triage["running_missing_lease_count"], 1)
        self.assertEqual(triage["running_expired_lease_count"], 0)
        self.assertTrue(triage["requires_operator_review"])
        self.assertEqual(triage["signals"], ["ready_queue_overdue", "running_lease_missing"])
        self.assertFalse(triage["worker_outage_proven"])
        self.assertFalse(triage["automatic_repair_available"])
        self.assertFalse(response.json()["worker"]["alive_confirmed"])
        for sensitive in ("p18-triage-fixture", "payload_digest", "lease_token", "filename"):
            self.assertNotIn(sensitive, response.content.decode())
        self.assertEqual(AdminJob.objects.count(), 4)
        self.assertEqual(AdminJob.objects.filter(status="queued").count(), 3)

    def test_running_job_with_future_expiry_but_missing_token_is_flagged(self):
        """A token-less lease is malformed even when its expiry is in the future."""
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        artifact = AdminArtifact.objects.create(
            kind="research_json", domain="research", owner=self.owner,
            owner_ref="synthetic", state="ready", storage_key="p18-token-gap-fixture",
            filename="synthetic.json", sha256="b" * 64, size=10,
            expires_at=now + timedelta(days=1),
        )
        job = AdminJob.objects.create(
            kind="research_intake", actor=self.owner, actor_ref="synthetic",
            policy_version=1, artifact=artifact, payload_digest="c" * 64,
            request_key=uuid.uuid4(), status="running", attempt=1,
            available_at=now - timedelta(seconds=30),
            lease_token=None, lease_expires_at=now + timedelta(minutes=1),
        )
        result = self.owner_client.get(BASE + "operations/health/")
        self.assertEqual(result.status_code, 200, result.content[:350])
        jobs = result.json()["jobs"]
        self.assertEqual(jobs["running_missing_lease_count"], 1)
        self.assertEqual(jobs["running_expired_lease_count"], 0)
        triage = result.json()["queue_triage"]
        self.assertEqual(triage["running_missing_lease_count"], 1)
        self.assertIn("running_lease_missing", triage["signals"])
        self.assertTrue(triage["requires_operator_review"])
        self.assertFalse(triage["automatic_repair_available"])
        self.assertEqual(AdminJob.objects.get(pk=job.pk).status, "running")
        self.assertIsNone(AdminJob.objects.get(pk=job.pk).lease_token)

    def test_expired_running_without_lease_token_is_never_auto_reclaimed(self):
        """A corrupted token-less running row requires human reconciliation."""
        from datetime import timedelta
        from django.utils import timezone
        from .cms_jobs import claim_job

        now = timezone.now()
        artifact = AdminArtifact.objects.create(
            kind="research_json", domain="research", owner=self.owner,
            owner_ref="synthetic", state="ready", storage_key="p18-expired-token-gap",
            filename="synthetic.json", sha256="d" * 64, size=10,
            expires_at=now + timedelta(days=1),
        )
        job = AdminJob.objects.create(
            kind="research_intake", actor=self.owner, actor_ref="synthetic",
            policy_version=1, artifact=artifact, payload_digest="d" * 64,
            request_key=uuid.uuid4(), status="running", attempt=1,
            available_at=now - timedelta(minutes=5), lease_token=None,
            lease_expires_at=now - timedelta(minutes=1),
        )
        original_version = job.version
        self.assertIsNone(claim_job())
        job.refresh_from_db()
        self.assertEqual(job.status, "running")
        self.assertEqual(job.version, original_version)
        self.assertEqual(job.attempt, 1)
        self.assertIsNone(job.lease_token)
        triage = self.owner_client.get(BASE + "operations/health/").json()["queue_triage"]
        self.assertEqual(triage["running_missing_lease_count"], 1)
        self.assertEqual(triage["running_expired_lease_count"], 0)
        self.assertTrue(triage["requires_operator_review"])

    def test_scheduled_jobs_are_not_mislabeled_as_ready_worker_backlog(self):
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()
        artifact = AdminArtifact.objects.create(
            kind="research_json", domain="research", owner=self.owner,
            owner_ref="synthetic", state="ready", storage_key="p18-fake-artifact",
            filename="synthetic.json", sha256="f" * 64, size=10,
            expires_at=now + timedelta(days=1),
        )
        base = {
            "kind": "research_intake", "actor": self.owner, "actor_ref": "synthetic",
            "policy_version": 1, "artifact": artifact,
            "payload_digest": "a" * 64, "attempt": 0,
        }
        ready = AdminJob.objects.create(
            **base, status="queued", request_key=uuid.uuid4(),
            available_at=now - timedelta(minutes=8),
        )
        AdminJob.objects.filter(pk=ready.pk).update(
            created_at=now - timedelta(minutes=9),
        )
        scheduled = AdminJob.objects.create(
            **base, status="queued", request_key=uuid.uuid4(),
            available_at=now + timedelta(hours=3),
        )
        running = AdminJob.objects.create(
            **base, status="running", request_key=uuid.uuid4(),
            available_at=now - timedelta(minutes=3),
            lease_token=uuid.uuid4(),
            lease_expires_at=now - timedelta(minutes=1),
        )
        missing = AdminJob.objects.create(
            **base, status="running", request_key=uuid.uuid4(),
            available_at=now - timedelta(minutes=4),
            lease_token=None, lease_expires_at=None,
        )
        result = self.owner_client.get(BASE + "operations/health/")
        self.assertEqual(result.status_code, 200, result.content[:500])
        jobs = result.json()["jobs"]
        self.assertEqual(jobs["total"], 4)
        self.assertEqual(jobs["by_status"]["queued"], 2)
        self.assertEqual(jobs["queued_ready_count"], 1)
        self.assertEqual(jobs["queued_scheduled_count"], 1)
        self.assertEqual(jobs["ready_queue_age_seconds"] >= 8 * 60, True)
        self.assertEqual(jobs["oldest_ready_at"], ready.available_at.isoformat())
        self.assertEqual(jobs["next_scheduled_at"], scheduled.available_at.isoformat())
        self.assertEqual(jobs["running_expired_lease_count"], 1)
        self.assertEqual(jobs["running_missing_lease_count"], 1)
        self.assertEqual(jobs["stale_lease_count"], 1)
        self.assertFalse(jobs["worker_liveness_proven"])
        self.assertFalse(result.json()["worker"]["alive_confirmed"])
        self.assertEqual(result.json()["backup"]["state"], "unavailable")
        for sensitive in ("storage_key", "payload_digest", "lease_token", "request_key", "filename"):
            self.assertNotIn(sensitive, result.content.decode())
        self.assertEqual(AdminJob.objects.get(pk=running.pk).status, "running")
        self.assertEqual(AdminJob.objects.get(pk=missing.pk).status, "running")

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
        self.assertEqual(before["scope"], "source_plan_receipt_history_and_bounded_result_sample")
        self.assertEqual(before["source_plans_total"], 1)
        self.assertEqual(before["source_plans_without_receipt"], 1)
        self.assertEqual(before["source_receipts_total"], 0)
        self.assertEqual(before["total_observed_mismatches"], 0)
        self.assertFalse(before["full_source_integrity_proven"])
        self.assertFalse(before["repair_available"])

        receipt = SourcePlanReceipt.objects.create(
            plan=preview, actor=self.owner, actor_ref="synthetic",
            result={"history_ids": [], "successor_ids": []},
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
        self.assertEqual(matched["source_receipt_result_history_mismatches"], 1)
        self.assertEqual(matched["total_observed_mismatches"], 1)

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
        self.assertEqual(drift["total_observed_mismatches"], 2)
        self.assertEqual(SourcePlanReceipt.objects.get(pk=receipt.pk).pk, receipt.pk)
        self.assertEqual(SourceHistory.objects.get(pk=history.pk).pk, history.pk)

    def test_source_receipt_result_ids_match_persisted_history_and_successors(self):
        from unittest.mock import patch
        from .cms_source_models import SourcePlan, SourcePlanReceipt, SourceHistory, SourceSuccessor

        def fixture(source_id, declared_history=None, declared_successors=None):
            plan = SourcePlan.objects.create(
                operation="successor", source_pk=source_id, fingerprint="c" * 64,
                actor=self.owner, actor_ref="synthetic",
            )
            history = SourceHistory.objects.create(
                plan=plan, source_pk=source_id, version=1, operation="successor",
                actor=self.owner, actor_ref="synthetic",
            )
            edge = SourceSuccessor.objects.create(
                plan=plan, source_pk=source_id, successor_pk=source_id + 1000,
                operation="successor",
            )
            receipt = SourcePlanReceipt.objects.create(
                plan=plan, actor=self.owner, actor_ref="synthetic",
                result={
                    "history_ids": [history.pk] if declared_history is None else declared_history,
                    "successor_ids": [edge.pk] if declared_successors is None else declared_successors,
                },
            )
            return plan, history, edge, receipt

        _, expected_history, _, valid_receipt = fixture(950)
        good = self.owner_client.get(BASE + "operations/health/").json()["source_plan_receipts"]
        self.assertEqual(good["source_receipt_result_history_mismatches"], 0)
        self.assertEqual(good["source_receipt_result_successor_mismatches"], 0)
        self.assertEqual(good["sampled_receipts"], 1)
        self.assertTrue(good["sample_complete"])
        self.assertFalse(good["full_source_integrity_proven"])

        _, _, _, bad_receipt = fixture(951, declared_history=[], declared_successors=[-1])
        drift = self.owner_client.get(BASE + "operations/health/").json()["source_plan_receipts"]
        self.assertEqual(drift["source_receipt_result_history_mismatches"], 1)
        self.assertEqual(drift["source_receipt_result_successor_mismatches"], 1)
        self.assertEqual(drift["total_observed_mismatches"], 2)
        self.assertEqual(drift["sampled_receipts"], 2)
        self.assertFalse(drift["repair_available"])
        self.assertNotIn("history_ids", str(drift))
        self.assertEqual(SourcePlanReceipt.objects.get(pk=valid_receipt.pk).result["history_ids"], [expected_history.pk])
        self.assertEqual(SourcePlanReceipt.objects.get(pk=bad_receipt.pk).result["history_ids"], [])

        with patch("atlas.cms_operations_health._SOURCE_RESULT_SCAN_LIMIT", 1):
            partial = self.owner_client.get(BASE + "operations/health/").json()["source_plan_receipts"]
        self.assertEqual(partial["sampled_receipts"], 1)
        self.assertFalse(partial["sample_complete"])
        self.assertFalse(partial["full_source_integrity_proven"])

    def test_non_owner_denied_and_no_runtime_mutations(self):
        staff=self.user("p18-not-owner",staff=True,caps=(
            "cms_enter","cms_dashboard","cms_user_view"))
        client=self.sign_in(staff)
        self.assertEqual(client.get(BASE+"operations/health/").status_code,403)
        self.assertEqual(self.owner_client.get(BASE+"operations/health/?cmd=sql").status_code,400)
        self.assertEqual(self.post(self.owner_client,"operations/health/",{
            "restore":"anything",
        }).status_code,405)
