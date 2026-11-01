"""NON-SCIENTIFIC .invalid staging, crash reconciliation and immutable decisions."""
from datetime import timedelta
import json
from unittest.mock import patch
import uuid

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from . import cms_artifacts as service
from .cms_audit import attribution
from .cms_job_models import AdminArtifact, AdminJob, ResearchRecordDecision
from .cms_jobs import checkpoint_job, claim_job, enqueue_job, run_once
from .cms_models import AdminAuditEvent, AdminSession
from .cms_policy import CMSFailure
from .models import Category, Concept, DSMCorpus, DSMRecord, ResearchDataset, ResearchRecord, SourceReference
from .tests_v100_p01 import BASE
from .tests_v100_p06_artifacts import ArtifactFixture, research_document


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ResearchIntakeTests(ArtifactFixture, TransactionTestCase):
    def test_cleanup_retains_raw_dataset_and_all_live_or_succeeded_intake_jobs(self):
        artifact = self.ready()
        job = self.enqueue(artifact)
        duplicate = self.ready()
        row = AdminArtifact.objects.get(pk=duplicate["id"])
        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.save()
        for status in ("queued", "running", "reconciling", "succeeded"):
            with self.subTest(status=status):
                AdminJob.objects.filter(pk=job.pk).update(status=status)
                with self.assertRaises(CMSFailure) as error:
                    service.cleanup_eligible(row)
                self.assertEqual(str(error.exception.detail["code"]), "ARTIFACT_RETENTION_HOLD")
        AdminJob.objects.filter(pk=job.pk).update(status="queued")
        run_once()
        dataset = ResearchDataset.objects.get(source_sha256=row.sha256)
        raw = (dataset.raw_text, dataset.raw_document, dataset.records.count())
        AdminJob.objects.filter(pk=job.pk).update(status="failed")
        with self.assertRaises(CMSFailure) as error:
            service.cleanup_eligible(row)
        self.assertEqual(str(error.exception.detail["code"]), "ARTIFACT_RETENTION_HOLD")
        dataset.refresh_from_db()
        self.assertEqual((dataset.raw_text, dataset.raw_document, dataset.records.count()), raw)
        self.assertTrue((self.root / row.storage_key).exists())

    def enqueue(self, artifact=None, count=1):
        artifact = artifact or self.ready(research_document(count))
        return enqueue_job(self.owner.pk, self.sid, artifact["id"], uuid.uuid4(), uuid.uuid4())

    def ingest(self, artifact=None, count=1):
        job = self.enqueue(artifact, count)
        run_once()
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded", job.error_code)
        return job, ResearchDataset.objects.get(pk=job.result["dataset_id"])

    def test_http_intake_replay_metadata_browsing_and_lossless_inactive_index(self):
        document = research_document(3)
        document["concepts"][0].update(slug="NON_SCIENTIFIC", review={"status": "reviewed"}, verification_status="verified")
        raw = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()
        artifact = self.ready(raw=raw)
        data = {"artifact_id": artifact["id"], "request_key": str(uuid.uuid4())}
        response = self.post(self.client, "research/imports/", data)
        self.assertEqual(response.status_code, 202, response.content)
        self.assertTrue(response["Location"].startswith("/api/admin/jobs/"))
        self.assertEqual(self.post(self.client, "research/imports/", data).json()["job"]["id"], response.json()["job"]["id"])
        canonical = (Concept.objects.count(), SourceReference.objects.count())
        run_once()
        job = AdminJob.objects.get(pk=response.json()["job"]["id"])
        self.assertEqual(job.status, "succeeded", job.error_code)
        dataset = ResearchDataset.objects.get(pk=job.result["dataset_id"])
        self.assertEqual(dataset.raw_text.encode("utf-8"), raw)
        self.assertEqual(dataset.raw_document, document)
        self.assertFalse(dataset.is_active)
        self.assertEqual((job.progress_done, job.progress_total), (3, 3))
        self.assertEqual((Concept.objects.count(), SourceReference.objects.count()), canonical)
        record = dataset.records.get(external_id="NON-SCIENTIFIC-0")
        self.assertEqual(record.payload, document["concepts"][0])
        self.assertEqual((record.slug, record.review_status, record.verification_status, record.promoted_pk),
            ("non-scientific", "unreviewed", "staging_only", None))
        self.assertEqual(record.canonical_key, "concept:non-scientific")
        for path in ("research/datasets/", f"research/datasets/{dataset.pk}/records/",
                f"research/records/{record.pk}/", f"research/records/{record.pk}/history/"):
            response = self.client.get(BASE + path)
            self.assertEqual(response.status_code, 200, response.content)
            for secret in ("PRIVATE RAW", "raw_document", "raw_text", '"payload"', "definition_en"):
                self.assertNotIn(secret, response.content.decode())
        self.assertEqual(AdminAuditEvent.objects.filter(action="research.intake").count(), 1)

    def test_duplicate_sha_reuses_existing_dataset_and_records_without_overwrite_or_activation(self):
        artifact = self.ready(research_document(2))
        first, dataset = self.ingest(artifact)
        before = (ResearchDataset.objects.values().get(pk=dataset.pk), list(dataset.records.order_by("pk").values()))
        second, same = self.ingest(artifact)
        self.assertEqual(same.pk, dataset.pk)
        self.assertTrue(second.result["duplicate"])
        self.assertEqual((ResearchDataset.objects.values().get(pk=dataset.pk), list(dataset.records.order_by("pk").values())), before)
        self.assertEqual(ResearchDataset.objects.count(), 1)
        self.assertEqual(first.result["records"], second.result["records"])

    def test_committed_chunks_crash_resume_reconcile_without_duplicate_or_raw_changes(self):
        job = self.enqueue(count=205)
        worker = claim_job()
        effects = []
        def interrupted(job_id, token, effect):
            previous = AdminJob.objects.get(pk=job_id).progress_done
            current = checkpoint_job(job_id, token, effect)
            effects.append(current.progress_done - previous)
            if current.progress_done == 100:
                raise RuntimeError("NON-SCIENTIFIC crash after committed effect")
            return current
        with patch("atlas.cms_jobs.checkpoint_job", side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                service.process_intake(worker.pk, worker.lease_token)
        job.refresh_from_db()
        self.assertEqual((job.checkpoint["offset"], job.progress_done), (100, 100))
        self.assertEqual(ResearchRecord.objects.count(), 100)
        dataset = ResearchDataset.objects.get(pk=job.checkpoint["dataset_id"])
        original_bytes = dataset.raw_text
        AdminJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        replacement = claim_job()
        with patch("atlas.cms_artifacts.artifact_bytes", wraps=service.artifact_bytes) as reading:
            with self.assertRaises(CMSFailure) as error:
                service.process_intake(worker.pk, worker.lease_token)
            self.assertEqual(str(error.exception.detail["code"]), "LEASE_LOST")
            reading.assert_not_called()
        result = service.process_intake(replacement.pk, replacement.lease_token)
        self.assertEqual(result["records"], 205)
        self.assertEqual(ResearchRecord.objects.count(), 205)
        self.assertEqual(ResearchDataset.objects.count(), 1)
        self.assertEqual(ResearchDataset.objects.get(pk=dataset.pk).raw_text, original_bytes)
        self.assertTrue(all(delta <= 100 for delta in effects))
        self.assertEqual(AdminAuditEvent.objects.filter(action="research.intake").count(), 1)

    def test_second_job_cannot_accept_first_jobs_crashed_partial_archive_as_duplicate(self):
        artifact = self.ready(research_document(105))
        first = self.enqueue(artifact)
        worker = claim_job()
        def crash(job_id, token, effect):
            current = checkpoint_job(job_id, token, effect)
            if current.progress_done == 100:
                raise RuntimeError("NON-SCIENTIFIC committed chunk crash")
            return current
        with patch("atlas.cms_jobs.checkpoint_job", side_effect=crash), self.assertRaises(RuntimeError):
            service.process_intake(worker.pk, worker.lease_token)
        second = self.enqueue(artifact)
        competitor = claim_job()
        self.assertEqual(competitor.pk, second.pk)
        with self.assertRaises(CMSFailure) as error:
            service.process_intake(competitor.pk, competitor.lease_token)
        self.assertEqual(str(error.exception.detail["code"]), "INTAKE_INCOMPLETE")
        self.assertEqual(ResearchRecord.objects.count(), 100)
        second.refresh_from_db()
        self.assertEqual((second.progress_done, second.checkpoint), (0, {}))
        # The first lease remains the only authority that can finish its archive.
        service.process_intake(worker.pk, worker.lease_token)
        checkpoint_job(worker.pk, worker.lease_token, lambda row: setattr(row, "status", "succeeded"))
        result = service.process_intake(competitor.pk, competitor.lease_token)
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["records"], 105)
        self.assertEqual(ResearchRecord.objects.count(), 105)

    def test_same_sha_cannot_give_another_actor_private_dataset_or_raw_access(self):
        document = research_document()
        first, dataset = self.ingest(self.ready(document))
        self.grant(self.scoped, "cms_research_view", "cms_research_intake", "cms_artifact_upload", "cms_research_raw_read")
        client = self.sign_in(self.scoped)
        artifact = self.created(document, client=client)
        response = self.post(client, f"artifacts/{artifact['id']}/validate/", etag='"1"')
        self.assertEqual(response.status_code, 200, response.content)
        job = enqueue_job(self.scoped.pk, client.session["cms_session_id"], artifact["id"], uuid.uuid4(), uuid.uuid4())
        worker = claim_job()
        with self.assertRaises(CMSFailure) as error:
            service.process_intake(worker.pk, worker.lease_token)
        self.assertEqual(str(error.exception.detail["code"]), "NOT_FOUND")
        self.assertEqual(client.get(BASE + "research/datasets/").json()["count"], 0)
        record = dataset.records.get()
        self.code(client.get(BASE + f"research/records/{record.pk}/"), "NOT_FOUND", 404)
        self.code(self.post(client, f"research/records/{record.pk}/raw-preview/",
            {"purpose": "research_review", "reason": "RESEARCH_RAW"}), "NOT_FOUND", 404)
        self.assertEqual(ResearchDataset.objects.count(), 1)

    def test_duplicate_legacy_archive_keeps_existing_flags_and_detects_corruption(self):
        artifact = self.ready()
        job, dataset = self.ingest(artifact)
        # Model the pre-CMS importer, whose existing reviewed/promoted index must not be rewritten.
        ResearchDataset.objects.filter(pk=dataset.pk).update(ingestion_audit={"list_record_total": 1}, is_active=True)
        record = dataset.records.get()
        ResearchRecord.objects.filter(pk=record.pk).update(review_status="reviewed", verification_status="verified", promoted_model="Concept", promoted_pk=999)
        before = (ResearchDataset.objects.values().get(pk=dataset.pk), ResearchRecord.objects.values().get(pk=record.pk))
        duplicate, _ = self.ingest(artifact)
        self.assertTrue(duplicate.result["duplicate"])
        self.assertEqual((ResearchDataset.objects.values().get(pk=dataset.pk), ResearchRecord.objects.values().get(pk=record.pk)), before)
        ResearchRecord.objects.filter(pk=record.pk).update(payload={"id": "NON-SCIENTIFIC changed"})
        pending = self.enqueue(artifact)
        worker = claim_job()
        with self.assertRaises(CMSFailure) as error:
            service.process_intake(worker.pk, worker.lease_token)
        self.assertEqual(str(error.exception.detail["code"]), "ARCHIVE_INTEGRITY")

    def test_final_chunk_completion_receipt_is_atomic_read_only_and_checks_integrity(self):
        job = self.enqueue(count=101)
        worker = claim_job()
        AdminJob.objects.filter(pk=job.pk).update(attempt=3)
        self.assertIsNone(service.reconcile_intake(worker))
        def crash_after_final(job_id, token, effect):
            current = checkpoint_job(job_id, token, effect)
            if current.checkpoint.get("complete"):
                raise RuntimeError("NON-SCIENTIFIC final chunk committed before crash")
            return current
        with patch("atlas.cms_jobs.checkpoint_job", side_effect=crash_after_final), self.assertRaises(RuntimeError):
            service.process_intake(worker.pk, worker.lease_token)
        job.refresh_from_db()
        self.assertTrue(job.checkpoint["complete"])
        self.assertEqual(job.status, "running")
        before = (list(ResearchDataset.objects.values()), list(ResearchRecord.objects.values()),
            list(AdminAuditEvent.objects.values()), list(AdminJob.objects.values()))
        result = service.reconcile_intake(job)
        self.assertEqual(result["records"], 101)
        self.assertEqual((list(ResearchDataset.objects.values()), list(ResearchRecord.objects.values()),
            list(AdminAuditEvent.objects.values()), list(AdminJob.objects.values())), before)
        for changed in ({"offset": 100}, {"sha256": "0" * 64}, {"dataset_id": 999999},
                {"duplicate": True, "verified_duplicate": False}):
            original = job.checkpoint
            job.checkpoint = {**original, **changed}
            with self.assertRaises(CMSFailure) as error:
                service.reconcile_intake(job)
            self.assertEqual(str(error.exception.detail["code"]), "CHECKPOINT_INTEGRITY")
            job.checkpoint = original
        AdminJob.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        with patch("atlas.cms_artifacts.process_intake", side_effect=AssertionError("Completed effects must never dispatch again")) as handler:
            recovered = run_once()
        self.assertEqual((recovered.status, recovered.attempt, recovered.lease_token), ("succeeded", 3, None))
        self.assertEqual(recovered.result, result)
        handler.assert_not_called()

    def test_empty_and_verified_duplicate_completion_receipts(self):
        artifact = self.ready(research_document(0))
        job, dataset = self.ingest(artifact)
        self.assertEqual(service.reconcile_intake(job)["records"], 0)
        self.assertTrue(job.checkpoint["complete"])
        self.assertFalse(job.checkpoint["duplicate"])
        duplicate, same = self.ingest(artifact)
        self.assertEqual(same.pk, dataset.pk)
        self.assertEqual(service.reconcile_intake(duplicate), duplicate.result)
        self.assertTrue(duplicate.checkpoint["verified_duplicate"])

    def test_permission_session_cancellation_and_artifact_revocation_fence_before_read(self):
        job = self.enqueue()
        worker = claim_job()
        for condition, expected in (("permission", "PERMISSION_DENIED"), ("session", "UNAUTHENTICATED"),
                ("artifact", "ARTIFACT_NOT_READY"), ("cancel", "JOB_CANCELLED")):
            with self.subTest(condition=condition):
                if condition == "permission":
                    self.owner.user_permissions.clear()
                elif condition == "session":
                    AdminSession.objects.filter(pk=self.sid).update(revoked_at=timezone.now())
                elif condition == "artifact":
                    AdminArtifact.objects.filter(pk=job.artifact_id).update(state="revoked")
                else:
                    AdminJob.objects.filter(pk=job.pk).update(cancel_requested=True)
                with patch("atlas.cms_artifacts.artifact_bytes") as reading:
                    with self.assertRaises(CMSFailure) as error:
                        service.process_intake(worker.pk, worker.lease_token)
                    self.assertEqual(str(error.exception.detail["code"]), expected)
                    reading.assert_not_called()
                if condition == "permission":
                    self.grant(self.owner, "cms_owner")
                elif condition == "session":
                    AdminSession.objects.filter(pk=self.sid).update(revoked_at=None)
                elif condition == "artifact":
                    AdminArtifact.objects.filter(pk=job.artifact_id).update(state="ready")
        self.assertFalse(ResearchDataset.objects.exists())

    def test_preparation_runs_outside_checkpoint_transactions_and_effects_are_bounded(self):
        from django.db import connection
        job = self.enqueue(count=201)
        worker = claim_job()
        original = service._record_fields
        lengths = []
        def prepare(*args):
            self.assertFalse(connection.in_atomic_block)
            return original(*args)
        def checked(job_id, token, effect):
            before = ResearchRecord.objects.count()
            result = checkpoint_job(job_id, token, effect)
            lengths.append(ResearchRecord.objects.count() - before)
            return result
        def bounded_archive_reads(execute, sql, params, many, context):
            if connection.in_atomic_block and sql.lstrip().upper().startswith("SELECT"):
                self.assertNotIn('"atlas_researchdataset"."raw_document"', sql)
                self.assertNotIn('"atlas_researchdataset"."raw_text"', sql)
            return execute(sql, params, many, context)
        with connection.execute_wrapper(bounded_archive_reads), patch("atlas.cms_artifacts._record_fields", side_effect=prepare), patch("atlas.cms_jobs.checkpoint_job", side_effect=checked):
            service.process_intake(worker.pk, worker.lease_token)
        self.assertEqual([size for size in lengths if size], [100, 100, 1])

    def test_dsm_parser_validator_stages_only_and_rejects_bad_health(self):
        document = {"عنوان": "NON-SCIENTIFIC .invalid", "نسخه_MASTER": {"نام": "NON-SCIENTIFIC"},
            "آمار_MASTER": {"تعداد_گره‌های_آدرس‌پذیر_دارای_پروفایل_MASTER": 1},
            "فصل‌های_اختلال": [{"شناسه_MASTER": "NON-SCIENTIFIC-M1",
                "پروفایل_آموزشی_پیشرفته_MASTER": {"نام_انگلیسی": "NON-SCIENTIFIC .invalid", "نام_فارسی": "آزمایشی غیرعلمی"}}]}
        before = (DSMCorpus.objects.count(), DSMRecord.objects.count())
        job, dataset = self.ingest(self.ready(document, kind="dsm_json"))
        self.assertEqual(dataset.records.get().section, "dsm_record")
        self.assertEqual((DSMCorpus.objects.count(), DSMRecord.objects.count()), before)
        document["تست_سلامت_MASTER"] = {"نتیجه": "FAIL"}
        artifact = self.created(document, kind="dsm_json")
        self.assertEqual(self.validate(artifact).json()["artifact"]["state"], "rejected")

    def test_existing_importer_fallback_ids_remain_section_relative(self):
        document = research_document(0)
        document["sources"] = [{"id": "NON-SCIENTIFIC-source", "title": "NON-SCIENTIFIC .invalid"}]
        document["concepts"] = [{"name_en": "NON-SCIENTIFIC first .invalid"}, {"name_en": "NON-SCIENTIFIC second .invalid"}]
        job, dataset = self.ingest(self.ready(document))
        records = list(dataset.records.filter(section="concepts").order_by("pk"))
        self.assertTrue(records[0].external_id.endswith(":0"))
        self.assertTrue(records[1].external_id.endswith(":1"))
        self.assertEqual(records[0].canonical_key, "concept:name:non scientific first invalid")

    def test_nested_dsm_uses_existing_pruned_record_projection_and_preserves_full_document(self):
        child = {"شناسه_MASTER": "NON-SCIENTIFIC-M2", "پروفایل_آموزشی_پیشرفته_MASTER": {"نام_انگلیسی": "NON-SCIENTIFIC child .invalid"}}
        document = {"فصل‌های_اختلال": [{"شناسه_MASTER": "NON-SCIENTIFIC-M1",
            "پروفایل_آموزشی_پیشرفته_MASTER": {"نام_انگلیسی": "NON-SCIENTIFIC parent .invalid"}, "children": [child]}]}
        job, dataset = self.ingest(self.ready(document, kind="dsm_json"))
        parent = dataset.records.get(external_id="NON-SCIENTIFIC-M1")
        self.assertNotIn("پروفایل_آموزشی_پیشرفته_MASTER", parent.payload["children"][0])
        self.assertEqual(dataset.raw_document, document)
        self.assertEqual(dataset.records.count(), 2)

    def test_assessment_strict_metadata_archive_no_canonical_or_review_flags(self):
        document = {"schema_version": "psychology-atlas-assessments-v1",
            "dataset_metadata": {"key": "non-scientific-invalid", "version": "1"}, "records": [
                {"id": "NON-SCIENTIFIC", "category": "instrument", "data": {"slug": "non-scientific", "name_en": "NON-SCIENTIFIC .invalid"}}]}
        job, dataset = self.ingest(self.ready(document, kind="assessment_json"))
        record = dataset.records.get()
        self.assertEqual((record.section, record.payload, record.review_status), ("assessment_instrument", document["records"][0], "unreviewed"))
        self.assertFalse(dataset.is_active)
        document["records"][0]["data"]["manual_text"] = "NON-SCIENTIFIC private"
        artifact = self.created(document, kind="assessment_json")
        self.assertEqual(self.validate(artifact).json()["artifact"]["validation_code"], "PROTECTED_CONTENT")

    def test_research_domain_cannot_list_detail_history_raw_or_decide_assessment(self):
        job, dataset = self.ingest()
        record = dataset.records.get()
        self.grant(self.scoped, "cms_research_view", "cms_research_map", "cms_research_raw_read")
        ResearchDataset.objects.filter(pk=dataset.pk).update(ingestion_audit={**dataset.ingestion_audit, "cms_owner_ref": attribution(self.scoped.pk)})
        client = self.sign_in(self.scoped)
        self.assertEqual(client.get(BASE + f"research/records/{record.pk}/").status_code, 200)
        record.section = "assessment_instrument"
        record.save(update_fields=("section",))
        self.assertEqual(client.get(BASE + "research/datasets/").json()["count"], 0)
        for suffix in ("", "history/"):
            self.code(client.get(BASE + f"research/records/{record.pk}/{suffix}"), "NOT_FOUND", 404)
        self.code(self.post(client, f"research/records/{record.pk}/raw-preview/", {"purpose": "research_review", "reason": "RESEARCH_RAW"}), "NOT_FOUND", 404)
        self.code(self.post(client, f"research/records/{record.pk}/decisions/", {"action": "map", "mapping": {}, "reason": "RESEARCH_MAP"}, etag='"0"'), "NOT_FOUND", 404)
        self.code(client.get(BASE + f"research/datasets/{dataset.pk}/records/"), "NOT_FOUND", 404)

    def test_raw_preview_is_explicit_scoped_audited_and_audit_failure_leaks_nothing(self):
        job, dataset = self.ingest()
        record = dataset.records.get()
        path = f"research/records/{record.pk}/raw-preview/"
        self.code(self.post(self.client, path, {"purpose": "arbitrary", "reason": "RESEARCH_RAW"}), "INVALID_PURPOSE", 400)
        data = {"purpose": "research_review", "reason": "RESEARCH_RAW"}
        response = self.post(self.client, path, data)
        self.assertEqual(response.json()["record"]["payload"], record.payload)
        event = AdminAuditEvent.objects.get(request_id=response["X-Request-ID"])
        self.assertEqual((event.action, event.reason, event.target_id), ("research.raw", "RESEARCH_RAW", record.pk))
        self.assertNotIn("PRIVATE RAW", json.dumps(event.diff))
        original = AdminAuditEvent.objects.create
        def fail(**values):
            if values["action"] == "research.raw":
                raise DatabaseError("NON-SCIENTIFIC private diagnostic")
            return original(**values)
        with patch.object(AdminAuditEvent.objects, "create", side_effect=fail):
            response = self.post(self.client, path, data)
        self.code(response, "WRITE_FAILED", 503)
        self.assertNotIn("PRIVATE RAW", response.content.decode())
        ResearchRecord.objects.filter(pk=record.pk).update(payload={"manual_text": "NON-SCIENTIFIC"})
        self.code(self.post(self.client, path, data), "PROTECTED_CONTENT", 400)

    def test_immutable_map_stage_reject_defer_with_etags_no_canonical_changes(self):
        job, dataset = self.ingest()
        record = dataset.records.get()
        original = dict(ResearchRecord.objects.values().get(pk=record.pk))
        category = Category.objects.create(slug="non-scientific-target", name_en="NON-SCIENTIFIC .invalid", is_active=False)
        mapping = {"canonical_key": "category:" + category.slug, "name_en": "NON-SCIENTIFIC .invalid",
            "name_fa": "آزمایشی غیرعلمی", "source_ids": []}
        path = f"research/records/{record.pk}/decisions/"
        def decide(action, mapping={}, version=0):
            return self.post(self.client, path, {"action": action, "mapping": mapping, "reason": "RESEARCH_" + action.upper()}, etag=f'"{version}"')
        self.code(decide("stage"), "MAPPING_REQUIRED", 409)
        response = decide("map", mapping)
        self.assertEqual(response.status_code, 200, response.content)
        self.code(decide("reject"), "STALE_REVISION", 412)
        response = decide("stage", version=1)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["record"]["staging_state"], "stage")
        self.assertEqual(decide("reject", version=2).status_code, 200)
        self.assertEqual(decide("defer", version=3).status_code, 200)
        self.assertEqual(list(record.cms_decisions.values_list("action", flat=True)), ["map", "stage", "reject", "defer"])
        decision = record.cms_decisions.first()
        decision.reason = "RESEARCH_REJECT"
        with self.assertRaises(ValidationError):
            decision.save()
        self.assertEqual(ResearchRecord.objects.values().get(pk=record.pk), original)
        category.refresh_from_db()
        self.assertFalse(category.is_active)
        self.assertFalse(ResearchDataset.objects.get(pk=dataset.pk).is_active)
        self.assertEqual(self.client.get(BASE + f"research/records/{record.pk}/history/").json()["count"], 4)

    def test_decision_audit_rollback_mapping_validation_current_caps_and_paging(self):
        job, dataset = self.ingest()
        record = dataset.records.get()
        path = f"research/records/{record.pk}/decisions/"
        data = {"action": "defer", "mapping": {}, "reason": "RESEARCH_DEFER"}
        original = AdminAuditEvent.objects.create
        def fail(**values):
            if values["action"] == "research.decision":
                raise DatabaseError("NON-SCIENTIFIC private diagnostic")
            return original(**values)
        with patch.object(AdminAuditEvent.objects, "create", side_effect=fail):
            self.code(self.post(self.client, path, data, etag='"0"'), "WRITE_FAILED", 503)
        self.assertFalse(ResearchRecordDecision.objects.exists())
        for query in ("page=0", "page_size=101", "raw=1", "path=C:/private"):
            self.code(self.client.get(BASE + "research/datasets/?" + query), "INVALID_QUERY", 400)
        self.owner.user_permissions.clear()
        self.grant(self.owner, "cms_enter", "cms_research_view")
        self.code(self.post(self.client, path, data, etag='"0"'), "PERMISSION_DENIED")
