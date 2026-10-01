"""All input documents in this module are synthetic, unapproved test fixtures."""

import copy
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .brain_staging import ingest_brain_document, validate_brain_staging
from .models import BrainAnatomicalEntity, BrainExternalIdentifier, BrainHierarchyLink, BrainNetwork, ResearchDataset, ResearchRecord, SourceReference


class BrainStagingTests(TestCase):
    def setUp(self):
        self.source = SourceReference.objects.create(title="Synthetic staging source", citation="Synthetic test evidence",
                                                  url="https://example.org/staging-test", verification_status="source_checked")
        self.document = {
            "schema_version": "brain-staging-v1", "dataset_metadata": {"key": "test-only-brain", "version": "v1"},
            "records": [
                {"id": "source-one", "category": "source", "source_reference_id": self.source.pk,
                 "title": self.source.title, "citation": self.source.citation, "url": self.source.url},
                {"id": "anatomy-one", "category": "anatomy", "slug": "test-only-structure", "name_en": "Test Only Structure",
                 "kind": "structure", "laterality": "bilateral", "source_version": "Test version 1", "spatial_scope": "Test scope only",
                 "source_ids": ["source-one"], "source_notes": {"source-one": "Synthetic identity claim"}, "review_status": "unreviewed"},
            ],
        }

    def ingest(self, document=None):
        return ingest_brain_document(json.dumps(document or self.document, ensure_ascii=False), "test-only.json")

    def test_lossless_idempotent_staging_and_no_canonical_promotion(self):
        dataset, created = self.ingest()
        self.assertTrue(created)
        again, created = self.ingest()
        self.assertFalse(created)
        self.assertEqual(again.pk, dataset.pk)
        self.assertEqual(dataset.raw_document, self.document)
        self.assertEqual(dataset.records.count(), 2)
        for _ in range(2):
            report = validate_brain_staging()
            self.assertEqual(report["candidate_count"], 2)
            self.assertEqual(report["canonical_writes"], 0)
        self.assertEqual(BrainAnatomicalEntity.objects.count(), 0)
        self.assertEqual(BrainNetwork.objects.count(), 0)
        self.assertEqual(BrainHierarchyLink.objects.count(), 0)
        self.assertFalse(dataset.records.exclude(promoted_model="", promoted_pk=None).exists())

    def test_repeat_import_preserves_local_review_and_source_payload(self):
        dataset, _ = self.ingest()
        record = dataset.records.get(external_id="anatomy-one")
        record.review_status = "source_checked"
        record.save()
        snapshot = list(dataset.records.order_by("pk").values())
        self.ingest()
        validate_brain_staging()
        self.assertEqual(list(dataset.records.order_by("pk").values()), snapshot)

    def test_generic_corpus_is_never_promoted_or_rewritten(self):
        dataset = ResearchDataset.objects.create(key="generic-test", source_filename="generic.json", source_sha256="a" * 64,
                                                raw_document={"concepts": [{"name_en": "Brain network mention"}]})
        record = ResearchRecord.objects.create(dataset=dataset, section="concepts", external_id="generic-one",
                                              payload={"name_en": "Brain network mention", "biography": "cortex imaging neuro"})
        snapshot = ResearchRecord.objects.filter(pk=record.pk).values().get()
        self.assertEqual(validate_brain_staging()["candidate_count"], 0)
        self.assertEqual(ResearchRecord.objects.filter(pk=record.pk).values().get(), snapshot)

    def test_missing_source_and_unsupported_claims_remain_staging_only(self):
        for alteration, expected in (({"source_ids": ["missing"]}, "unresolved_source"),
                                     ({"coordinates": [1, 2, 3]}, "unsupported_fields"),
                                     ({"function": "Brain activation diagnoses a disorder"}, "unsupported_fields"),
                                     ({"laterality": "both"}, "invalid_laterality")):
            with self.subTest(alteration=alteration):
                document = copy.deepcopy(self.document)
                document["records"][1].update(alteration)
                dataset, _ = self.ingest(document)
                report = validate_brain_staging(dataset.key)
                self.assertIn(expected, {row["code"] for row in report["issues"]})
        self.assertEqual(BrainAnatomicalEntity.objects.count(), 0)

    def test_ambiguous_identity_and_duplicate_source_ids_are_reported(self):
        document = copy.deepcopy(self.document)
        duplicate = copy.deepcopy(document["records"][1])
        duplicate.update(id="second-identity", laterality="left")
        document["records"].append(duplicate)
        document["records"].append(copy.deepcopy(document["records"][0]))
        dataset, _ = self.ingest(document)
        self.assertEqual(dataset.records.count(), 4)
        codes = {row["code"] for row in validate_brain_staging(dataset.key)["issues"]}
        self.assertIn("ambiguous_identity", codes)
        self.assertIn("duplicate_external_id", codes)

    def test_aliases_are_explicit_not_identity_inference(self):
        document = copy.deepcopy(self.document)
        document["records"].append({
            "id": "alias-one", "category": "alias", "owner_type": "anatomy", "owner_slug": "test-only-structure",
            "text": "TOS", "language": "en", "alias_type": "abbreviation", "source_ids": ["source-one"],
            "source_notes": {"source-one": "Synthetic abbreviation"}, "review_status": "unreviewed",
        })
        dataset, _ = self.ingest(document)
        self.assertEqual(validate_brain_staging(dataset.key)["classifications"]["C"], 1)
        self.assertEqual(BrainAnatomicalEntity.objects.count(), 0)

    def test_staged_hierarchy_rejects_cycles_and_opposite_laterality(self):
        document = copy.deepcopy(self.document)
        first = document["records"][1]
        first["laterality"] = "left"
        second = copy.deepcopy(first)
        second.update(id="other-anatomy", slug="other-test", name_en="Other Test", laterality="right")
        document["records"].append(second)
        for child, parent in ((first["slug"], second["slug"]), (second["slug"], first["slug"])):
            document["records"].append({
                "id": f"link-{child}", "category": "hierarchy", "child_slug": child, "parent_slug": parent,
                "predicate": "part_of", "source_version": "Test version 1", "review_status": "reviewed",
                "source_ids": ["source-one"], "source_notes": {"source-one": "Synthetic hierarchy"},
            })
        dataset, _ = self.ingest(document)
        codes = {row["code"] for row in validate_brain_staging(dataset.key)["issues"]}
        self.assertIn("hierarchy_cycle", codes)
        self.assertIn("laterality_conflict", codes)

    def test_incidental_category_is_classified_as_unsupported(self):
        document = copy.deepcopy(self.document)
        document["records"].append({"id": "incidental", "category": "biography", "text": "brain cortex imaging"})
        dataset, _ = self.ingest(document)
        self.assertEqual(validate_brain_staging(dataset.key)["classifications"]["H"], 1)

    def test_dry_run_has_no_persistence_and_unknown_schema_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(self.document), encoding="utf-8")
            call_command("import_brain_dataset", str(path), dry_run=True, stdout=StringIO())
        self.assertEqual(ResearchDataset.objects.count(), 0)
        document = copy.deepcopy(self.document)
        document["schema_version"] = "generic"
        with self.assertRaises(CommandError):
            self.ingest(document)

    def test_validation_is_deterministic(self):
        self.ingest()
        self.assertEqual(validate_brain_staging(), validate_brain_staging())

    def test_corrupt_staging_payload_is_reported_without_rewriting_it(self):
        dataset, _ = self.ingest()
        record = dataset.records.get(external_id="anatomy-one")
        record.payload = ["corrupt test-only staging payload"]
        record.save()
        report = validate_brain_staging(dataset.key)
        self.assertIn("unsupported_category", {row["code"] for row in report["issues"]})
        record.refresh_from_db()
        self.assertEqual(record.payload, ["corrupt test-only staging payload"])

    def test_malformed_candidate_field_types_remain_staging(self):
        for field, value in (("kind", []), ("slug", {}), ("source_ids", [{}]), ("source_notes", [])):
            document = copy.deepcopy(self.document)
            document["records"][1][field] = value
            dataset, _ = self.ingest(document)
            self.assertTrue(validate_brain_staging(dataset.key)["issues"])

    def test_cross_dataset_conflicting_identity_is_never_merged(self):
        self.ingest()
        other = copy.deepcopy(self.document)
        other["dataset_metadata"]["version"] = "v2"
        other["records"][1]["laterality"] = "left"
        self.ingest(other)
        self.assertIn("ambiguous_identity", {row["code"] for row in validate_brain_staging()["issues"]})
        self.assertEqual(BrainAnatomicalEntity.objects.count(), 0)

    def test_selected_identity_conflict_is_reported_once_when_other_dataset_shares_it(self):
        selected = copy.deepcopy(self.document)
        duplicate = copy.deepcopy(selected["records"][1])
        duplicate.update(id="second-identity", laterality="left")
        selected["records"].append(duplicate)
        dataset, _ = self.ingest(selected)
        other = copy.deepcopy(self.document)
        other["dataset_metadata"]["version"] = "v2"
        other["records"][1]["laterality"] = "right"
        self.ingest(other)

        issues = [row for row in validate_brain_staging(dataset.key)["issues"]
                  if row["code"] == "ambiguous_identity"]
        self.assertEqual(len(issues), 2)
        self.assertEqual(len({(row["dataset"], row["record"], row["code"]) for row in issues}), 2)

    def test_duplicate_relation_evidence_keys_are_not_ready_for_curation(self):
        from .models import Concept

        Concept.objects.create(slug="synthetic-concept", name_en="Synthetic Concept", simple_definition="Test")
        document = copy.deepcopy(self.document)
        network = {"id": "network-one", "category": "network", "slug": "synthetic-network", "name_en": "Synthetic Network",
                   "kind": "functional", "source_version": "Test v1", "definition": "Test definition", "method": "Test method",
                   "source_ids": ["source-one"], "source_notes": {"source-one": "Synthetic source"}, "review_status": "unreviewed"}
        document["records"].append(network)
        for category in ("network_membership", "functional_association"):
            relation = {"id": category, "category": category, "evidence_key": "synthetic-evidence", "source_version": "Test v1",
                        "method": "Test method", "source_ids": ["source-one"], "source_notes": {"source-one": "Synthetic claim"},
                        "review_status": "unreviewed"}
            if category == "network_membership":
                relation.update(entity_slug="test-only-structure", network_slug="synthetic-network",
                                predicate="participates_in_network", qualifier="Synthetic participation")
            else:
                relation.update(subject_type="anatomy", subject_slug="test-only-structure", concept_slug="synthetic-concept",
                                predicate="functional_association", task_context="Synthetic task", population_context="Synthetic population",
                                limitations="Test limitation", explanation_en="Test association")
            document["records"].extend([relation, {**relation, "id": category + "-duplicate"}])
        dataset, _ = self.ingest(document)
        report = validate_brain_staging(dataset.key)
        duplicates = [row for row in report["issues"] if row["code"] == "duplicate_evidence_key"]
        self.assertEqual(len(duplicates), 4)
        other = copy.deepcopy(document)
        other["dataset_metadata"]["version"] = "v2"
        other["records"] = [row for row in other["records"] if not row["id"].endswith("-duplicate")]
        other_dataset, _ = self.ingest(other)
        self.assertEqual(len([row for row in validate_brain_staging()["issues"] if row["code"] == "duplicate_evidence_key"]), 6)
        selected = validate_brain_staging(other_dataset.key)
        self.assertEqual(len([row for row in selected["issues"] if row["code"] == "duplicate_evidence_key"]), 2)

    def test_external_mapping_conflicts_include_other_dossiers_and_canonical_rows(self):
        document = copy.deepcopy(self.document)
        document["records"].append({
            "id": "mapping-one", "category": "external_identifier", "owner_type": "anatomy",
            "owner_slug": "test-only-structure", "namespace": "Synthetic Atlas", "identifier": "S-17",
            "source_version": "Test v1", "review_status": "unreviewed", "source_ids": ["source-one"],
            "source_notes": {"source-one": "Synthetic mapping claim"},
        })
        dataset, _ = self.ingest(document)
        self.assertEqual(validate_brain_staging(dataset.key)["issues"], [])
        other = copy.deepcopy(document)
        other["dataset_metadata"]["version"] = "v2"
        other["records"][-1].update(namespace="synthetic atlas", source_version="test V1")
        self.ingest(other)
        selected = validate_brain_staging(dataset.key)
        self.assertEqual([row["code"] for row in selected["issues"] if row["record"] == "mapping-one"],
                         ["duplicate_external_identifier"])
        entity = BrainAnatomicalEntity.objects.create(slug="canonical-mapping-test", name_en="Synthetic Mapping Owner",
                                                      kind="structure", laterality="bilateral")
        BrainExternalIdentifier.objects.create(entity=entity, namespace="SYNTHETIC ATLAS", identifier="S-17",
                                               source_version="TEST V1", source=self.source)
        codes = {row["code"] for row in validate_brain_staging(dataset.key)["issues"] if row["record"] == "mapping-one"}
        self.assertEqual(codes, {"duplicate_external_identifier", "canonical_external_identifier_conflict"})

    def test_alias_conflicts_include_other_dossiers_and_canonical_owners(self):
        from .models import BrainAnatomicalAlias, BrainNetworkAlias

        entity = BrainAnatomicalEntity.objects.create(slug="test-only-structure", name_en="Test Only Structure",
                                                      kind="structure", laterality="bilateral")
        network = BrainNetwork.objects.create(slug="synthetic-network", name_en="Synthetic Network")
        for owner_type, owner, alias_model in (("anatomy", entity, BrainAnatomicalAlias),
                                               ("network", network, BrainNetworkAlias)):
            alias_model.objects.create(text="Synthetic Alias", language="en", **{alias_model.alias_owner_field: owner})
            document = copy.deepcopy(self.document)
            if owner_type == "network":
                document["records"].append({"id": "network-one", "category": "network", "slug": network.slug,
                    "name_en": network.name_en, "kind": network.kind, "source_version": "Test v1", "definition": "Synthetic definition",
                    "method": "Synthetic method", "review_status": "unreviewed", "source_ids": ["source-one"],
                    "source_notes": {"source-one": "Synthetic network identity"}})
            record_id = f"alias-{owner_type}"
            document["records"].append({"id": record_id, "category": "alias", "owner_type": owner_type,
                "owner_slug": owner.slug, "text": "Synthetic Alias", "language": "en", "alias_type": "alternative",
                "review_status": "unreviewed", "source_ids": ["source-one"], "source_notes": {"source-one": "Synthetic spelling"}})
            dataset, _ = self.ingest(document)
            self.assertIn("canonical_alias_conflict", {row["code"] for row in validate_brain_staging(dataset.key)["issues"]
                                                       if row["record"] == record_id})
            other = copy.deepcopy(document)
            other["dataset_metadata"]["version"] = "v2"
            other["records"][-1]["text"] = "synthetic   ALIAS"
            self.ingest(other)
            issues = [row["code"] for row in validate_brain_staging(dataset.key)["issues"] if row["record"] == record_id]
            self.assertEqual(issues, ["canonical_alias_conflict", "duplicate_alias"])

    def test_existing_canonical_evidence_key_is_not_a_new_candidate(self):
        from .tests_v092_brain_api import BrainFixtureMixin

        entity = BrainAnatomicalEntity.objects.create(slug="test-only-structure", name_en="Test Only Structure", kind="structure", laterality="bilateral")
        fixture = type("SyntheticFixture", (BrainFixtureMixin,), {"source": self.source})
        fixture.add_relations(entity)
        document = copy.deepcopy(self.document)
        document["records"].append({"id": "existing-claim", "category": "network_membership", "evidence_key": "fixture-membership",
            "entity_slug": entity.slug, "network_slug": "fixture-network", "source_version": "Test v1", "method": "Test",
            "qualifier": "Test", "predicate": "participates_in_network", "review_status": "unreviewed",
            "source_ids": ["source-one"], "source_notes": {"source-one": "Test claim"}})
        dataset, _ = self.ingest(document)
        self.assertIn("canonical_evidence_key_conflict", {row["code"] for row in validate_brain_staging(dataset.key)["issues"]})

    def test_alias_length_matches_normalized_canonical_capacity(self):
        for length, valid in ((255, True), (256, False)):
            document = copy.deepcopy(self.document)
            document["dataset_metadata"]["version"] = f"alias-{length}"
            document["records"].append({"id": "alias-length", "category": "alias", "owner_type": "anatomy",
                "owner_slug": "test-only-structure", "text": "  " + "a" * length + "  ", "language": "en",
                "alias_type": "alternative", "source_ids": ["source-one"], "source_notes": {"source-one": "Synthetic spelling"},
                "review_status": "unreviewed"})
            dataset, _ = self.ingest(document)
            codes = {row["code"] for row in validate_brain_staging(dataset.key)["issues"] if row["record"] == "alias-length"}
            with self.subTest(length=length):
                self.assertEqual("invalid_alias" not in codes, valid)
        self.assertEqual(BrainAnatomicalEntity.objects.count(), 0)

    def test_candidate_lengths_cannot_exceed_existing_canonical_fields(self):
        for category, fields in (("anatomy", {"name_fa": "x" * 256, "persian_reviewed": True}),
                                 ("hierarchy", {"source_version": "x" * 121}),
                                 ("external_identifier", {"namespace": "x" * 121, "identifier": "x" * 256}),
                                 ("network_membership", {"source_version": "x" * 121})):
            document = copy.deepcopy(self.document)
            document["dataset_metadata"]["version"] = category
            document["records"].append({"id": "oversized", "category": category, "review_status": "unreviewed", **fields})
            dataset, _ = self.ingest(document)
            with self.subTest(category=category):
                codes = {row["code"] for row in validate_brain_staging(dataset.key)["issues"] if row["record"] == "oversized"}
                self.assertIn("invalid_field_length", codes)
        self.assertEqual(BrainAnatomicalEntity.objects.count(), 0)

    def test_repeated_claim_source_ids_are_not_ready_for_curation(self):
        for repeated_key in (True, False):
            document = copy.deepcopy(self.document)
            document["dataset_metadata"]["version"] = str(repeated_key)
            if not repeated_key:
                document["records"].append({**document["records"][0], "id": "source-two"})
                document["records"][1]["source_notes"]["source-two"] = "Same synthetic source through another key"
            document["records"][1]["source_ids"] = ["source-one", "source-one" if repeated_key else "source-two"]
            dataset, _ = self.ingest(document)
            report = validate_brain_staging(dataset.key)
            with self.subTest(repeated_key=repeated_key):
                self.assertIn("duplicate_source_id", {row["code"] for row in report["issues"]})
                self.assertEqual(report["canonical_writes"], 0)
                self.assertEqual(dataset.raw_document, document)
