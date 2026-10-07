"""Controlled real-corpus publication, rollback, receipt integrity and public API."""
import io
import copy
import json
from pathlib import Path
import tempfile
from threading import Barrier, Thread
from queue import Queue
from unittest import skipUnless
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from . import brain_controlled_publication as publication
from . import models as m
from .brain_staging import validate_brain_staging


class ControlledPublicationFailureTests(TestCase):
    def test_unreviewed_artifact_hash_fails_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changed.json"
            path.write_bytes(publication.DOSSIER.read_bytes() + b" ")
            with self.assertRaisesMessage(CommandError, "artifact hash"):
                publication.publish(dossier=path, dry_run=False)
        self.assertEqual(m.SourceReference.objects.count(), 0)
        self.assertFalse(m.ResearchDataset.objects.exists())

    def test_dry_run_rolls_back_sources_archive_and_all_canonical_rows(self):
        result, derived = publication.publish()
        self.assertEqual(result["status"], "DRY_RUN_VALIDATED")
        self.assertEqual(result["canonical_writes"], 0)
        self.assertEqual(result["counts"]["anatomy"], 87)
        self.assertTrue(all(r["source_reference_id"] > 0 for r in derived["records"] if r["category"] == "source"))
        self.assertFalse(m.SourceReference.objects.exists())
        self.assertFalse(m.ResearchDataset.objects.exists())
        self.assertFalse(any(publication.canonical_counts().values()))

    def test_late_failure_rolls_back_every_dependency(self):
        project = publication.projection
        def late_failure(row, sources):
            if row["category"] == "hierarchy" and row["child_slug"] == "ca3-field":
                raise CommandError("Injected late publication failure")
            return project(row, sources)
        with patch.object(publication, "projection", side_effect=late_failure):
            with self.assertRaisesMessage(CommandError, "Injected late"):
                publication.publish(dry_run=False)
        self.assertFalse(m.SourceReference.objects.exists())
        self.assertFalse(m.ResearchDataset.objects.exists())
        self.assertFalse(any(publication.canonical_counts().values()))

    def test_source_identity_conflict_preserves_registry_and_empty_brain(self):
        m.SourceReference.objects.create(title="Conflicting paper", doi="10.1152/jn.00338.2011",
                                        url="https://example.org/conflict", verification_status="source_checked")
        with self.assertRaisesMessage(CommandError, "Source resolution CONFLICT"):
            publication.publish(dry_run=False)
        self.assertEqual(m.SourceReference.objects.count(), 1)
        self.assertFalse(any(publication.canonical_counts().values()))

    def test_duplicate_bibliography_is_ambiguous_not_silently_merged(self):
        info = publication.approved_artifacts()[0]["dataset_metadata"]["verified_source_catalog"]["source-yeo-2011"]
        for _ in range(2):
            m.SourceReference.objects.create(**{f: info.get(f) for f in publication.SOURCE_FIELDS}, verification_status="source_checked")
        with self.assertRaisesMessage(CommandError, "Source resolution AMBIGUOUS"):
            publication.publish(dry_run=False)
        self.assertEqual(m.SourceReference.objects.count(), 2)
        self.assertFalse(m.ResearchDataset.objects.exists())

    def test_checked_locator_match_with_conflicting_bibliography_is_rejected(self):
        info = publication.approved_artifacts()[0]["dataset_metadata"]["verified_source_catalog"]["source-yeo-2011"]
        fields = {f: info.get(f) for f in publication.SOURCE_FIELDS}
        fields["authors"] = ["Different author"]
        m.SourceReference.objects.create(**fields, verification_status="source_checked")
        with self.assertRaisesMessage(CommandError, "Source resolution CONFLICT"):
            publication.publish(dry_run=False)
        self.assertEqual(m.SourceReference.objects.count(), 1)
        self.assertFalse(m.ResearchDataset.objects.exists())

    def test_incomplete_or_different_checked_source_metadata_is_rejected(self):
        info = publication.approved_artifacts()[0]["dataset_metadata"]["verified_source_catalog"]["source-yeo-2011"]
        for field, value in (("organization", ""), ("authors", []), ("publication_year", None),
                             ("source_type", "website")):
            with self.subTest(field=field):
                fields = {f: info.get(f) for f in publication.SOURCE_FIELDS}
                fields[field] = value
                source = m.SourceReference.objects.create(**fields, verification_status="source_checked")
                with self.assertRaisesMessage(CommandError, "Approved source metadata differs"):
                    publication.publish(dry_run=False)
                self.assertFalse(m.ResearchDataset.objects.exists())
                self.assertFalse(any(publication.canonical_counts().values()))
                source.delete()

    def predecessor_archive(self):
        from .brain_staging import ingest_brain_document
        previous = json.loads(publication.PREDECESSOR.read_text(encoding="utf-8"))
        derived, _, _ = publication.resolve_document(previous, create=True)
        derived["dataset_metadata"]["target_resolution"] = {"portable_master_sha256": publication.PREDECESSOR_SHA}
        archive, _ = ingest_brain_document(publication.encoded(derived), "previous.resolved.json")
        return archive

    def test_pinned_predecessor_is_preserved_and_superseded_by_controlled_publication(self):
        previous = self.predecessor_archive()
        before = (list(m.ResearchDataset.objects.values()), list(previous.records.values()))
        result, _ = publication.publish(dry_run=False)
        previous.refresh_from_db()
        self.assertEqual(list(m.ResearchDataset.objects.filter(pk=previous.pk).values()), before[0])
        self.assertEqual(list(previous.records.values()), before[1])
        self.assertEqual(result["counts"]["anatomy"], 87)
        self.assertEqual(sum(r["classification"] == "EXISTING_MATCH" for r in result["source_resolution"]), 24)
        validation = validate_brain_staging()
        self.assertEqual(validation["issues"], [])
        self.assertEqual(validation["superseded_datasets"], [previous.key])
        self.assertEqual(validation["candidate_count"], 333)
        self.assertEqual(validate_brain_staging(previous.key)["candidate_count"], 0)
        self.assertEqual(publication.publish(dry_run=False)[0]["canonical_writes"], 0)

    def test_changed_predecessor_or_forged_pin_cannot_bypass_conflict_validation(self):
        from .brain_staging import ingest_brain_document
        previous = json.loads(publication.PREDECESSOR.read_text(encoding="utf-8"))
        altered = copy.deepcopy(previous)
        altered["dataset_metadata"]["target_resolution"] = {"portable_master_sha256": publication.PREDECESSOR_SHA}
        altered["records"][24]["name_en"] = "Unreviewed changed identity"
        ingest_brain_document(publication.encoded(altered), "forged.json")
        with self.assertRaisesMessage(CommandError, "Brain staging validation failed"):
            publication.publish(dry_run=False)
        self.assertFalse(any(publication.canonical_counts().values()))
        self.assertEqual(m.ResearchDataset.objects.count(), 1)

    def test_predecessor_dry_run_preserves_archive_and_rolls_back_supersession(self):
        previous = self.predecessor_archive()
        before = (list(m.SourceReference.objects.values()), list(m.ResearchDataset.objects.values()), list(m.ResearchRecord.objects.values()))
        self.assertEqual(publication.publish()[0]["canonical_writes"], 0)
        self.assertEqual(list(m.SourceReference.objects.values()), before[0])
        self.assertEqual(list(m.ResearchDataset.objects.values()), before[1])
        self.assertEqual(list(m.ResearchRecord.objects.values()), before[2])
        self.assertEqual(validate_brain_staging(previous.key)["superseded_datasets"], [])


class PublishedCorpusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.result, _ = publication.publish(dry_run=False)

    def setUp(self):
        self.client = APIClient()

    @override_settings(ALLOWED_HOSTS=["atlas.example.org"], DEBUG=False, SECURE_SSL_REDIRECT=True)
    def test_verification_uses_the_configured_public_host(self):
        output = io.StringIO()
        call_command("verify_brain_publication", stdout=output)
        report = json.loads(output.getvalue())
        self.assertTrue(all(probe["status"] == 200 for probe in report["api"]))
        self.assertEqual(report["counts"]["anatomy"], 87)

    def test_source_metadata_revocation_invalidates_publication_receipt(self):
        source = m.SourceReference.objects.get(doi="10.1152/jn.00338.2011")
        # Simulate out-of-band damage; normal source writes already forbid this.
        with connection.cursor() as cursor:
            cursor.execute("UPDATE atlas_sourcereference SET organization = %s WHERE id = %s", ["", source.pk])
        with self.assertRaisesMessage(CommandError, "Approved source metadata differs"):
            publication.publish(dry_run=False)

    def test_duplicate_external_id_in_another_section_invalidates_receipt(self):
        archive = m.ResearchDataset.objects.get(key=self.result["dataset_key"])
        original = archive.records.first()
        m.ResearchRecord.objects.create(dataset=archive, section="aaaa-duplicate", external_id=original.external_id,
            payload=original.payload, source_ids=original.source_ids, review_status=original.review_status,
            verification_status=original.verification_status, promoted_model=original.promoted_model,
            promoted_pk=original.promoted_pk)
        with self.assertRaisesMessage(CommandError, "duplicate external record IDs"):
            publication.verify_receipt(archive)
        self.assertEqual(publication.published_record_ids(archive), set())

    def test_changed_searchable_archive_index_invalidates_receipt(self):
        archive = m.ResearchDataset.objects.get(key=self.result["dataset_key"])
        first_id = publication.approved_artifacts()[0]["records"][0]["id"]
        original = archive.records.get(external_id=first_id)
        for field in ("section", "canonical_key", "slug", "name_en", "name_fa"):
            with self.subTest(field=field):
                m.ResearchRecord.objects.filter(pk=original.pk).update(**{field: "altered"})
                with self.assertRaisesMessage(CommandError, "Published record identity/state conflict"):
                    publication.verify_receipt(archive)
                self.assertEqual(publication.published_record_ids(archive), set())
                m.ResearchRecord.objects.filter(pk=original.pk).update(**{field: getattr(original, field)})

    def test_changed_dataset_index_or_audit_invalidates_receipt(self):
        archive = m.ResearchDataset.objects.get(key=self.result["dataset_key"])
        for field, value in (("key", "altered"), ("dataset_name", "altered"), ("dataset_version", "altered"),
                             ("source_filename", "altered.json"), ("ingestion_audit", {"publication_manifest_sha256": publication.MANIFEST_SHA})):
            with self.subTest(field=field):
                previous = getattr(archive, field)
                m.ResearchDataset.objects.filter(pk=archive.pk).update(**{field: value})
                archive.refresh_from_db()
                with self.assertRaisesMessage(CommandError, "Publication archive/receipt differs"):
                    publication.verify_receipt(archive)
                m.ResearchDataset.objects.filter(pk=archive.pk).update(**{field: previous})
                archive.refresh_from_db()

    def test_manifest_reconciliation_and_exact_idempotence(self):
        before = {model._meta.label: list(model.objects.values()) for model in
                  (m.SourceReference, m.ResearchDataset, m.ResearchRecord, m.BrainAnatomicalEntity,
                   m.BrainNetwork, m.BrainHierarchyLink, m.BrainAnatomicalAlias, m.BrainExternalIdentifier)}
        again, _ = publication.publish(dry_run=False)
        self.assertEqual(again["status"], "ALREADY_PUBLISHED")
        self.assertEqual(again["canonical_writes"], 0)
        for label, values in before.items():
            model = next(model for model in (m.SourceReference, m.ResearchDataset, m.ResearchRecord,
                m.BrainAnatomicalEntity, m.BrainNetwork, m.BrainHierarchyLink, m.BrainAnatomicalAlias,
                m.BrainExternalIdentifier) if model._meta.label == label)
            self.assertEqual(list(model.objects.values()), values)
        self.assertEqual(publication.canonical_counts(), dict(anatomy=87, network=7, alias=50,
            external_identifier=94, hierarchy=70, network_membership=0, functional_association=0))

    def test_importer_repeat_read_only_promoter_and_audit_accept_exact_receipt(self):
        archive = m.ResearchDataset.objects.get(key=self.result["dataset_key"])
        from .brain_staging import ingest_brain_document
        with tempfile.TemporaryDirectory() as directory:
            resolved = Path(directory) / "target.resolved.json"
            call_command("publish_curated_brain", expected_dossier_sha256=publication.DOSSIER_SHA,
                expected_manifest_sha256=publication.MANIFEST_SHA, apply=True,
                resolved_output=resolved, stdout=io.StringIO())
            self.assertEqual(resolved.read_bytes(), archive.raw_text.encode("utf-8"))
        same, created = ingest_brain_document(archive.raw_text, "same.resolved.json")
        self.assertFalse(created)
        self.assertEqual(same.pk, archive.pk)
        output = io.StringIO()
        call_command("promote_brain_staging", dataset=archive.key, stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["canonical_writes"], 0)
        output = io.StringIO()
        call_command("audit_brain_atlas", as_json=True, stdout=output)
        audit = json.loads(output.getvalue())
        self.assertEqual(audit["errors"], [])
        self.assertEqual(audit["staging_issues"], 0)
        self.assertEqual(audit["review_debt"], [])
        self.assertEqual(audit["publication"], "PUBLISHED: pinned v0.9.2C manifest reconciled")

    def test_promotion_pointer_cannot_forge_receipt_or_hide_conflicts(self):
        row = m.ResearchRecord.objects.filter(section="brain_aliases").first()
        row.promoted_pk = 999999
        row.save(update_fields=("promoted_pk",))
        with self.assertRaisesMessage(CommandError, "Published record"):
            publication.publish(dry_run=False)
        self.assertTrue(validate_brain_staging(self.result["dataset_key"])["issues"])
        with self.assertRaises(CommandError):
            call_command("audit_brain_atlas", as_json=True, stdout=io.StringIO())

    def test_curator_changes_require_fresh_approval_not_automatic_overwrite(self):
        row = m.BrainAnatomicalEntity.objects.get(slug="amygdala")
        row.review_status = "unreviewed"
        row.save(update_fields=("review_status",))
        with self.assertRaisesMessage(CommandError, "Published record"):
            publication.publish(dry_run=False)
        row.refresh_from_db()
        self.assertEqual(row.review_status, "unreviewed")
        self.assertEqual(self.client.get("/api/brain-anatomy/amygdala/").status_code, 404)

    def test_archived_review_revocation_is_not_overwritten_or_ignored(self):
        dataset = m.ResearchDataset.objects.get(key=self.result["dataset_key"])
        dataset.is_active = False
        dataset.save(update_fields=("is_active",))
        with self.assertRaisesMessage(CommandError, "archive/receipt"):
            publication.publish(dry_run=False)
        dataset.is_active = True
        dataset.save(update_fields=("is_active",))
        row = m.ResearchRecord.objects.get(external_id="anatomy-amygdala")
        row.review_status = "unreviewed"
        row.save(update_fields=("review_status",))
        with self.assertRaisesMessage(CommandError, "Published record"):
            publication.publish(dry_run=False)
        row.refresh_from_db()
        self.assertEqual(row.review_status, "unreviewed")

    def test_public_real_corpus_list_detail_search_filters_and_pagination(self):
        response = self.client.get("/api/brain-anatomy/", {"page_size": 300})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 87)
        self.assertEqual(len(response.data["results"]), 87)
        self.assertEqual({r["review_status"] for r in response.data["results"]}, {"reviewed"})
        self.assertEqual(self.client.get("/api/brain-anatomy/", {"page": 2}).status_code, 200)
        for query, expected in (("Amygdala", "amygdala"), ("Locus coeruleus", "locus-ceruleus"),
                                ("آمیگدال", "amygdala"), ("کورپوس کالوزوم", "corpus-callosum")):
            result = self.client.get("/api/brain-anatomy/", {"q": query})
            self.assertIn(expected, {r["slug"] for r in result.data["results"]})
        result = self.client.get("/api/brain-anatomy/", {"parent": "frontal-lobe"})
        self.assertEqual({r["slug"] for r in result.data["results"]}, {"precentral-gyrus", "middle-frontal-gyrus", "inferior-frontal-gyrus", "superior-frontal-gyrus"})
        result = self.client.get("/api/brain-anatomy/", {"kind": "subcortical_structure", "laterality": "left"})
        self.assertEqual([r["slug"] for r in result.data["results"]], ["subthalamic-nucleus-left"])
        detail = self.client.get("/api/brain-anatomy/ca1-field/").data
        self.assertEqual(detail["parent"]["entity"]["slug"], "hippocampus-proper")
        self.assertEqual(detail["external_identifiers"][0]["namespace"], "FMA")
        self.assertIn("FMA 5.1.0", detail["parent"]["source_version"])
        self.assertTrue(detail["sources"])
        self.assertEqual(detail["network_memberships"], [])
        self.assertEqual(detail["functional_associations"], [])
        for field in ("aliases", "sources", "children", "external_identifiers"):
            self.assertLessEqual(len(detail[field]), 30)
        for slug in ("gray-matter", "white-matter", "missing-region", "myelencephalon"):
            self.assertEqual(self.client.get("/api/brain-anatomy/" + slug + "/").status_code, 404)

    def test_inactive_parent_hides_real_descendants(self):
        parent = m.BrainAnatomicalEntity.objects.get(slug="frontal-lobe")
        parent.is_active = False
        parent.save(update_fields=("is_active",))
        self.assertEqual(self.client.get("/api/brain-anatomy/precentral-gyrus/").status_code, 404)
        self.assertEqual(self.client.get("/api/brain-anatomy/frontal-lobe/").status_code, 404)

    def test_real_data_query_budgets_do_not_increase_synthetic_limits(self):
        for path, params, budget in (("/api/brain-anatomy/", {}, 4),
             ("/api/brain-anatomy/ca1-field/", {}, 11),
             ("/api/brain-anatomy/", {"q": "Locus coeruleus"}, 4),
             ("/api/brain-anatomy/", {"parent": "frontal-lobe"}, 5),
             ("/api/brain-anatomy/", {"kind": "subcortical_structure", "laterality": "left"}, 5)):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(path, params)
            self.assertEqual(response.status_code, 200)
            self.assertLessEqual(len(queries), budget, (path, params, len(queries)))

    @skipUnless(connection.vendor == "postgresql", "PostgreSQL execution-plan regression")
    def test_primary_ancestry_checks_validate_links_once_per_query(self):
        from .brain_publication import public_anatomy
        sql, params = public_anatomy().order_by().values("pk").query.sql_with_params()
        with connection.cursor() as cursor:
            cursor.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params)
            plan = cursor.fetchone()[0][0]["Plan"]
        nodes, checks = [plan], []
        while nodes:
            node = nodes.pop()
            nodes.extend(node.get("Plans", []))
            if node.get("Subplan Name") == "CTE checked_links":
                checks.append((node["Actual Loops"], node["Actual Rows"]))
        self.assertEqual(checks, [(1, 70)])
        self.assertEqual(plan["Actual Rows"], 87)


@skipUnless(connection.vendor == "postgresql", "Real concurrent publication requires PostgreSQL")
class PostgreSQLControlledPublicationTests(TransactionTestCase):
    def test_concurrent_duplicate_passes_serialize_and_publish_once(self):
        barrier, results = Barrier(2), Queue()
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                result, _ = publication.publish(dry_run=False)
                results.put(result["status"])
            except Exception as error:
                results.put(error)
            finally:
                connection.close()
        workers = [Thread(target=worker) for _ in range(2)]
        for thread in workers:
            thread.start()
        for thread in workers:
            thread.join(60)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual([results.get_nowait(), results.get_nowait()], ["PUBLISHED", "ALREADY_PUBLISHED"])
        self.assertEqual(m.SourceReference.objects.count(), 25)
        self.assertEqual(m.ResearchDataset.objects.count(), 1)
        self.assertEqual(m.BrainAnatomicalEntity.objects.count(), 87)
        self.assertEqual(m.BrainHierarchyLink.objects.count(), 70)
