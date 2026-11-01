"""P07 pure helpers: isolated NON-SCIENTIFIC fixtures, never real corpus intake."""
import json
from copy import deepcopy
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError

from .cms_domains import (DOMAIN_SPECS, dependency_snapshot, domain_for, entry_tuple,
    preview_snapshot, required_reference_capabilities, schema_data, validate_snapshot)
from .cms_capabilities import CAPABILITIES
from .cms_policy import CMSFailure
from .cms_source_models import SourceState
from .models import (Category, Concept, ConceptAlias, ConceptRelationship, ConceptSource,
    ConceptSymptom, DSMCorpus, DSMRecord, Disorder, DisorderSource, DisorderSymptom, SourceReference, Symptom)


class DomainHelpersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(slug="non-scientific-category", name_en="NON-SCIENTIFIC category")
        cls.disorder = Disorder.objects.create(category=cls.category, slug="non-scientific-disorder", name_en="NON-SCIENTIFIC disorder")
        cls.symptom = Symptom.objects.create(slug="non-scientific-symptom", name_en="NON-SCIENTIFIC symptom")
        cls.concept = Concept.objects.create(slug="non-scientific-concept", name_en="NON-SCIENTIFIC concept", simple_definition="NON-SCIENTIFIC fixture")
        cls.other_concept = Concept.objects.create(slug="non-scientific-other", name_en="NON-SCIENTIFIC other", simple_definition="NON-SCIENTIFIC fixture")
        cls.relationship = ConceptRelationship.objects.create(source_concept=cls.concept, target_concept=cls.other_concept)
        cls.concept_symptom = ConceptSymptom.objects.create(concept=cls.concept, symptom=cls.symptom)
        cls.source = SourceReference.objects.create(title="NON-SCIENTIFIC fixture; no evidence or approval", source_type="other")
        cls.corpus = DSMCorpus.objects.create(key="non-scientific-corpus", title="NON-SCIENTIFIC corpus", source_filename="NON-SCIENTIFIC.json", source_sha256="0" * 64,
            raw_document={"NON-SCIENTIFIC-RAW": "must not leak"}, source_registry={"FIXTURE": {"title": "NON-SCIENTIFIC registry"}})
        cls.other_corpus = DSMCorpus.objects.create(key="non-scientific-corpus-two", title="NON-SCIENTIFIC other corpus", source_filename="NON-SCIENTIFIC-two.json", source_sha256="1" * 64)
        cls.record = DSMRecord.objects.create(corpus=cls.corpus, master_id="NON-SCIENTIFIC-1", source_payload={"NON-SCIENTIFIC-RAW": "private payload"})
        cls.child = DSMRecord.objects.create(corpus=cls.corpus, master_id="NON-SCIENTIFIC-2", parent=cls.record)
        cls.foreign = DSMRecord.objects.create(corpus=cls.other_corpus, master_id="NON-SCIENTIFIC-3")

    def payloads(self):
        return {
            "category": {"slug": "non-scientific-new-category", "name_en": "NON-SCIENTIFIC new", "sort_order": 4},
            "disorder": {"slug": "non-scientific-new-disorder", "category": self.category.pk, "name_en": "NON-SCIENTIFIC new", "clinical_features": "NON-SCIENTIFIC feature"},
            "symptom": {"slug": "non-scientific-new-symptom", "name_en": "NON-SCIENTIFIC new", "domain": "cognitive"},
            "disorder-symptom": {"disorder": self.disorder.pk, "symptom": self.symptom.pk, "prominence": "core", "sort_order": 2},
            "differential-relationship": {"disorder": self.disorder.pk, "related_disorder": self.disorder.pk + 50000, "relationship_type": "related"},
            "disorder-source": {"disorder": self.disorder.pk, "source": self.source.pk, "note": "NON-SCIENTIFIC link"},
            "concept": {"slug": "non-scientific-new-concept", "name_en": "NON-SCIENTIFIC new", "simple_definition": "NON-SCIENTIFIC definition", "subtype": "cognitive_distortion"},
            "concept-relationship": {"source_concept": self.other_concept.pk, "target_concept": self.concept.pk, "relationship_type": "contrasts"},
            "concept-alias": {"concept": self.concept.pk, "text": "NON-SCIENTIFIC alias", "language": "en"},
            "concept-relationship-source": {"relationship": self.relationship.pk, "source": self.source.pk},
            "concept-symptom": {"concept": self.other_concept.pk, "symptom": self.symptom.pk, "relationship_type": "overlaps_with"},
            "concept-symptom-source": {"relationship": self.concept_symptom.pk, "source": self.source.pk},
            "disorder-concept": {"disorder": self.disorder.pk, "concept": self.concept.pk, "role": "maintaining"},
            "concept-source": {"concept": self.concept.pk, "source": self.source.pk},
            "dsm-corpus": {"key": "non-scientific-new-corpus", "title": "NON-SCIENTIFIC new", "version_date": "2026-10-30", "study_guide": ["NON-SCIENTIFIC note"]},
            "dsm-record": {"corpus": self.corpus.pk, "master_id": "NON-SCIENTIFIC-NEW", "parent": self.record.pk, "summary": "NON-SCIENTIFIC summary", "source_keys": ["FIXTURE"], "key_features": ["NON-SCIENTIFIC feature"]},
            "dsm-record-relation": {"source": self.record.pk, "target": self.child.pk, "relationship_type": "nearby"},
        }

    def test_registry_covers_exactly_seventeen_typed_schema_families(self):
        self.assertEqual({kind for kind, spec in DOMAIN_SPECS.items() if spec["domain"] in {"core", "dsm"}}, set(self.payloads()))
        for kind, spec in ((kind, spec) for kind, spec in DOMAIN_SPECS.items() if spec["domain"] in {"core", "dsm"}):
            with self.subTest(kind=kind):
                self.assertEqual(entry_tuple(kind), (spec["model"], spec["serializer"], spec["snapshot_fields"]))
                schema = schema_data(kind)
                self.assertEqual(schema["domain"], "dsm" if kind.startswith("dsm-") else "core")
                json.dumps(schema)
                self.assertEqual(set(spec["serializer"]().fields), {f["name"] for f in schema["fields"] if not f["readonly_reason"] or f["create_only"]})
                for field in schema["fields"]:
                    self.assertTrue({"name", "type", "required", "choices", "max_length", "related_kind", "create_only", "readonly_reason"} <= field.keys())

    def test_valid_proposals_in_all_families_are_json_native_without_saving(self):
        other = Disorder.objects.create(category=self.category, slug="non-scientific-other-disorder", name_en="NON-SCIENTIFIC other disorder")
        payloads = self.payloads()
        payloads["differential-relationship"]["related_disorder"] = other.pk
        for kind, payload in payloads.items():
            with self.subTest(kind=kind):
                before = DOMAIN_SPECS[kind]["model"].objects.count()
                actual = validate_snapshot(kind, payload)
                self.assertEqual(actual, payload)
                json.dumps(actual)
                self.assertEqual(DOMAIN_SPECS[kind]["model"].objects.count(), before)

    def test_legacy_category_disorder_payloads_preserve_their_exact_shape(self):
        for kind, obj, payload in (("category", self.category, {"name_en": "NON-SCIENTIFIC category", "name_fa": "", "description": ""}),
                ("disorder", self.disorder, {"name_en": "NON-SCIENTIFIC disorder", "name_fa": "", "short_description": "", "overview": ""})):
            self.assertEqual(validate_snapshot(kind, payload, obj), payload)
            self.assertEqual(validate_snapshot(kind, {"name_en": "NON-SCIENTIFIC draft"}), {"name_en": "NON-SCIENTIFIC draft"})

    def test_unknown_kind_fails_closed(self):
        for helper in (entry_tuple, domain_for, schema_data):
            with self.assertRaises(CMSFailure) as caught:
                helper("NON-SCIENTIFIC-unknown")
            self.assertEqual(caught.exception.status_code, 404)

    def test_protected_fields_and_unknown_fields_are_refused(self):
        cases = (("category", "is_active", False), ("disorder", "data_origin", "dsm_master"),
            ("concept", "is_active", False), ("dsm-corpus", "raw_document", {}),
            ("dsm-corpus", "source_sha256", "2" * 64), ("dsm-corpus", "source_filename", "NON-SCIENTIFIC"),
            ("dsm-record", "source_payload", {}), ("dsm-record", "search_text", "NON-SCIENTIFIC"),
            ("dsm-corpus", "version", 4), ("symptom", "unknown", "NON-SCIENTIFIC"))
        for kind, field, value in cases:
            with self.subTest(kind=kind, field=field), self.assertRaises(ValidationError):
                validate_snapshot(kind, {**self.payloads()[kind], field: value})
        for payload in (None, [], {}, {"name_en": ["NON-SCIENTIFIC"]}, {"name_en": "x" * 201}):
            with self.subTest(payload_type=type(payload).__name__), self.assertRaises(ValidationError):
                validate_snapshot("category", payload)

    def test_create_only_identity_and_normalized_conflicts(self):
        for kind, obj, field in (("category", self.category, "slug"), ("dsm-corpus", self.corpus, "key"), ("dsm-record", self.record, "master_id")):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                validate_snapshot(kind, {field: "NON-SCIENTIFIC-CHANGED"}, obj)
        with self.assertRaises(ValidationError):
            validate_snapshot("category", {"slug": " NON-SCIENTIFIC-CATEGORY ", "name_en": "NON-SCIENTIFIC conflict"})
        self.assertEqual(validate_snapshot("category", {"slug": " ＮＥＷ-fixture ", "name_en": "NON-SCIENTIFIC new"})["slug"], "new-fixture")

    def test_fk_type_missing_endpoint_and_wrong_endpoint_kind_are_refused(self):
        for value in (True, "1", -1, 0, 2**63, self.category.pk + 50000):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_snapshot("disorder", {"name_en": "NON-SCIENTIFIC", "category": value})
        with self.assertRaises(ValidationError):
            validate_snapshot("concept-symptom-source", {"relationship": 50000, "source": self.source.pk})

    def test_model_uniqueness_and_self_relationship_constraints(self):
        DisorderSymptom.objects.create(disorder=self.disorder, symptom=self.symptom)
        with self.assertRaises(ValidationError):
            validate_snapshot("disorder-symptom", self.payloads()["disorder-symptom"])
        with self.assertRaises(ValidationError):
            validate_snapshot("concept-relationship", {"source_concept": self.concept.pk, "target_concept": self.concept.pk})
        ConceptAlias.objects.create(concept=self.concept, text="NON-SCIENTIFIC alias", language="en")
        with self.assertRaises(ValidationError):
            validate_snapshot("concept-alias", self.payloads()["concept-alias"])

    def test_dsm_same_corpus_self_and_tree_cycles(self):
        for payload in ({"parent": self.record.pk}, {"parent": self.child.pk}, {"parent": self.foreign.pk}, {"corpus": self.other_corpus.pk}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                validate_snapshot("dsm-record", payload, self.record)
        for target in (self.record.pk, self.foreign.pk):
            with self.subTest(target=target), self.assertRaises(ValidationError):
                validate_snapshot("dsm-record-relation", {"source": self.record.pk, "target": target, "relationship_type": "nearby"})

    def test_structured_dsm_fields_are_typed_and_bounded(self):
        base = self.payloads()["dsm-record"]
        for fields in ({"source_keys": {}}, {"key_features": "NON-SCIENTIFIC"}, {"quality": []},
                {"assessment": ["x"] * 101}, {"homonym_info": {"raw_document": {}}},
                {"source_keys": ["NONEXISTENT"]}, {"prevalence_numeric": float("nan")}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                validate_snapshot("dsm-record", {**base, **fields})

    def test_preview_has_no_raw_no_writes_no_signals_no_cache_effect(self):
        payload = {"summary": "NON-SCIENTIFIC candidate", "parent": None}
        original = {name: deepcopy(value) for name, value in self.record.__dict__.items() if name != "_state"}
        original_state = self.record._state
        with patch.object(cache, "set", side_effect=AssertionError("cache mutation")), \
                patch.object(cache, "delete", side_effect=AssertionError("cache mutation")), \
                patch.object(DSMRecord, "save", side_effect=AssertionError("canonical save")), \
                patch("django.db.models.signals.post_save.send", side_effect=AssertionError("signal")):
            preview = preview_snapshot("dsm-record", payload, self.record)
        self.assertEqual({name: value for name, value in self.record.__dict__.items() if name != "_state"}, original)
        self.assertIs(self.record._state, original_state)
        self.assertEqual(preview["candidate"], payload)
        self.assertFalse(preview["publication_available"])
        self.assertNotIn("NON-SCIENTIFIC-RAW", json.dumps(preview))
        self.record.refresh_from_db()
        self.assertEqual(self.record.summary, "")

    def test_dependencies_track_endpoints_source_lifecycle_and_raw_drift_safely(self):
        ConceptSource.objects.create(concept=self.concept, source=self.source, note="NON-SCIENTIFIC source link")
        before = dependency_snapshot("concept-relationship", self.relationship)
        self.category.name_en = "NON-SCIENTIFIC changed parent"
        self.category.save()
        self.concept.name_en = "NON-SCIENTIFIC changed endpoint"
        self.concept.save()
        after = dependency_snapshot("concept-relationship", self.relationship)
        self.assertNotEqual(before, after)
        state = SourceState.objects.create(source_pk=self.source.pk, version=2, resource_version="NON-SCIENTIFIC-v2")
        changed = dependency_snapshot("concept-relationship", self.relationship)
        self.assertNotEqual(after, changed)
        state.archived = True
        state.save()
        with self.assertRaises(ValidationError):
            validate_snapshot("concept-source", {"note": "NON-SCIENTIFIC", "source": self.source.pk, "concept": self.concept.pk})
        before = dependency_snapshot("dsm-record", self.record)
        DSMRecord.objects.filter(pk=self.record.pk).update(source_payload={"NON-SCIENTIFIC-RAW": "changed"})
        self.record.refresh_from_db()
        after = dependency_snapshot("dsm-record", self.record)
        self.assertNotEqual(before, after)
        self.assertNotIn("NON-SCIENTIFIC-RAW", json.dumps(after))

    def test_payload_references_override_canonical_dependencies_and_permissions(self):
        current = dependency_snapshot("dsm-record", self.record)
        candidate = dependency_snapshot("dsm-record", self.record, {"linked_disorder": self.disorder.pk})
        self.assertNotEqual(current, candidate)
        self.assertIn("cms_core_view", required_reference_capabilities("dsm-record", {"linked_disorder": self.disorder.pk}))
        self.assertIn("cms_source_view", required_reference_capabilities("concept-source", {"source": self.source.pk}))
        self.assertEqual(required_reference_capabilities("dsm-record-relation", self.payloads()["dsm-record-relation"]), ["cms_dsm_view"])
        for kind, payload in self.payloads().items():
            with self.subTest(kind=kind):
                self.assertLessEqual(set(required_reference_capabilities(kind, payload)), CAPABILITIES)

    def test_source_option_kind_and_raw_field_policy_are_explicit(self):
        schema = {field["name"]: field for field in schema_data("concept-source")["fields"]}
        self.assertEqual(schema["source"]["related_kind"], "source")
        self.assertEqual(schema["concept"]["related_kind"], "concept")
        for kind, raw in (("dsm-corpus", "raw_document"), ("dsm-record", "source_payload")):
            fields = {field["name"]: field for field in schema_data(kind)["fields"]}
            self.assertIn("IMMUTABLE_RAW", fields[raw]["readonly_reason"])
            self.assertNotIn(raw, entry_tuple(kind)[2])
        fields = {field["name"]: field for field in schema_data("dsm-record")["fields"]}
        self.assertEqual(fields["key_features"]["structure"]["root"], "array")

    def test_serializer_representation_is_json_native_and_save_is_disabled(self):
        serializer = entry_tuple("concept-symptom")[1](data=self.payloads()["concept-symptom"])
        serializer.is_valid(raise_exception=True)
        with self.assertRaises(TypeError):
            serializer.save()
        self.assertEqual(serializer.data["concept"], self.other_concept.pk)
        json.dumps(serializer.data)

    def test_other_identities_are_create_only_and_equivalent_spelling_preserves_canonical(self):
        for kind, obj in (("symptom", self.symptom), ("concept", self.concept)):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                validate_snapshot(kind, {"slug": "non-scientific-renamed"}, obj)
        result = validate_snapshot("dsm-record", {"master_id": self.record.master_id.lower()}, self.record)
        self.assertEqual(result["master_id"], self.record.master_id)

    def test_all_reference_and_choice_constraints_are_rechecked_on_sparse_edits(self):
        link = DisorderSource.objects.create(disorder=self.disorder, source=self.source)
        SourceState.objects.create(source_pk=self.source.pk, archived=True)
        with self.assertRaises(ValidationError):
            validate_snapshot("disorder-source", {"note": "NON-SCIENTIFIC update"}, link)
        cases = (("concept", {"kind": "NON-SCIENTIFIC-invalid"}, self.concept),
            ("dsm-record", {"sort_index": -1}, self.record),
            ("dsm-record", {"chapter_number": 65536}, self.record),
            ("dsm-record", {"chapter_number": True}, self.record),
            ("dsm-corpus", {"version_date": "NON-SCIENTIFIC-invalid"}, self.corpus),
            ("differential-relationship", {"disorder": self.disorder.pk, "related_disorder": self.disorder.pk, "relationship_type": "related"}, None))
        for kind, payload, obj in cases:
            with self.subTest(kind=kind, payload=payload), self.assertRaises(ValidationError):
                validate_snapshot(kind, payload, obj)

    def test_payload_bytes_text_and_structured_depth_have_independent_bounds(self):
        payload = {"overview": "x" * 20001}
        with self.assertRaises(ValidationError):
            validate_snapshot("disorder", payload, self.disorder)
        with self.assertRaises(ValidationError):
            validate_snapshot("dsm-record", {"summary": "ع" * 70000}, self.record)
        nested = "NON-SCIENTIFIC"
        for _ in range(8):
            nested = [nested]
        for value in (nested, [object()], ["x" * 2001]):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValidationError):
                validate_snapshot("dsm-record", {"assessment": value}, self.record)

    def test_corpus_scoped_identity_uniqueness_and_typed_relation_constraints(self):
        with self.assertRaises(ValidationError):
            validate_snapshot("dsm-record", {"corpus": self.corpus.pk, "master_id": " non-scientific-1 "})
        allowed = {"corpus": self.other_corpus.pk, "master_id": "NON-SCIENTIFIC-1"}
        self.assertEqual(validate_snapshot("dsm-record", allowed), allowed)
        with self.assertRaises(ValidationError):
            validate_snapshot("concept-relationship", {"source_concept": self.concept.pk, "target_concept": self.other_concept.pk})
        with self.assertRaises(ValidationError):
            validate_snapshot("concept-symptom", {"concept": self.concept.pk, "symptom": self.symptom.pk})

    def test_dependency_bounds_fail_closed_and_source_versions_are_detected(self):
        link = ConceptSource.objects.create(concept=self.concept, source=self.source)
        initial = dependency_snapshot("concept-source", link)
        self.source.title = "NON-SCIENTIFIC changed source"
        self.source.save()
        self.assertNotEqual(initial, dependency_snapshot("concept-source", link))
        with patch("atlas.cms_domains.MAX_DEPENDENCIES", 1), self.assertRaises(ValidationError):
            dependency_snapshot("dsm-record", self.child)
        for invalid in ({"parent": True}, {"parent": "NON-SCIENTIFIC"}, {"raw_document": {}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                dependency_snapshot("dsm-record", self.record, invalid)

    def test_helpers_execute_only_selects_and_return_bounded_freshness_data(self):
        self.concept.simple_definition = "NON-SCIENTIFIC private long text " * 400
        self.concept.save()
        with CaptureQueriesContext(connection) as queries:
            before = dependency_snapshot("concept-relationship", self.relationship, lock=True)
            preview_snapshot("dsm-record", {"summary": "NON-SCIENTIFIC preview"}, self.record)
        self.assertTrue(queries)
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries), [q["sql"][:80] for q in queries])
        self.assertNotIn(self.concept.simple_definition, json.dumps(before))
        self.assertLess(len(json.dumps(before)), 15000)

    def test_dsm_preview_retains_study_fields_and_typed_graph_candidate_without_raw(self):
        payload = dict(entry_tuple("dsm-record")[1](self.record).data)
        payload.update(summary="NON-SCIENTIFIC study candidate", key_features=["NON-SCIENTIFIC feature"],
            self_test=["NON-SCIENTIFIC question"], exam_tip="NON-SCIENTIFIC tip")
        result = preview_snapshot("dsm-record", payload, self.record)
        self.assertTrue({"summary", "key_features", "assessment", "exam_tip", "self_test", "structural_path"} <= result["candidate"].keys())
        graph = preview_snapshot("dsm-record-relation", self.payloads()["dsm-record-relation"])
        self.assertEqual((graph["candidate"]["source"], graph["candidate"]["target"]), (self.record.pk, self.child.pk))
        for value in (result, graph):
            self.assertFalse(value["publication_available"])
            self.assertNotIn("source_payload", json.dumps(value))
            self.assertNotIn("raw_document", json.dumps(value))
