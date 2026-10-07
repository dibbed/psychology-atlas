"""Global integration uses existing synthetic Brain and curated Assessment fixtures."""
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models.query import QuerySet
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from unittest.mock import patch

from . import models as m
from .assessment_publication import publish as publish_assessments
from .brain_controlled_publication import publish as publish_brain
from .signals import GRAPH_MODELS
from .tests_v092_brain_api import BrainFixtureMixin
from .tests_v094_assessments import CuratedFixture
from .views import _get_atlas_graph


class IntegrationFixture(BrainFixtureMixin, CuratedFixture):
    @classmethod
    def setUpTestData(cls):
        BrainFixtureMixin.setUpTestData.__func__(cls)
        cls.brain_source = cls.source
        CuratedFixture.setUpTestData.__func__(cls)

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def search(self, q):
        response = self.client.get("/api/search/", {"q": q})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def graph(self, **params):
        response = self.client.get("/api/concept-map/", params)
        self.assertEqual(response.status_code, 200)
        return response.json()


@override_settings(REST_FRAMEWORK={"DEFAULT_THROTTLE_CLASSES": []})
class GlobalIntegrationTests(IntegrationFixture, TestCase):
    def test_additive_empty_search_contract(self):
        for q in ("", "x", " "):
            data = self.search(q)
            self.assertEqual(set(data), {"query", "disorders", "concepts", "symptoms", "therapies", "techniques",
                                         "psychologists", "theories", "timeline_events", "brain_entities", "assessments"})
            self.assertTrue(all(not rows for key, rows in data.items() if key != "query"))

    def test_global_rows_use_current_list_serialization(self):
        for endpoint, key, q in (("brain-anatomy", "brain_entities", "fixture-child"),
                                  ("assessments", "assessments", self.instrument.slug)):
            with self.subTest(endpoint=endpoint):
                expected = self.client.get(f"/api/{endpoint}/", {"q": q}).json()["results"]
                self.assertEqual(self.search(q)[key], expected)

    def test_names_slugs_aliases_and_persian_normalization(self):
        for q in ("Fixture Child", "fixture-child", "FC", "کانون یک", "كانون يك"):
            with self.subTest(q=q):
                self.assertEqual([row["slug"] for row in self.search(q)["brain_entities"]], [self.child.slug])
        for q in (self.instrument.name_en, self.instrument.slug, "PHQ", "PHQ-9",
                  self.instrument.name_fa.translate(str.maketrans({"ی": "ي", "ک": "ك"}))):
            with self.subTest(q=q):
                self.assertIn(self.instrument.slug, [row["slug"] for row in self.search(q)["assessments"]])

    def test_exact_aliases_precede_descriptions_with_stable_deduplication(self):
        partial = self.anatomy("fixture-partial", name_en="AAA partial", description_en="FC in description only")
        m.BrainAnatomicalAlias.objects.create(entity=self.child, text="FC alternate", language="en",
            review_status="reviewed", source=self.brain_source, source_note="Synthetic spelling support")
        self.assertEqual([row["slug"] for row in self.search("FC")["brain_entities"]], [self.child.slug, partial.slug])
        other = self.synthetic_instrument("synthetic-phq", "AAA description match", description="PHQ in description only")
        first = self.search("PHQ")["assessments"]
        self.assertEqual([row["slug"] for row in first], [self.instrument.slug, other.slug])
        self.assertEqual(first, self.search("PHQ")["assessments"])

    def test_ambiguous_acronym_keeps_distinct_canonical_families(self):
        other = self.synthetic_instrument("synthetic-ambiguous", "Synthetic other family")
        m.AssessmentAlias.objects.create(instrument=other, text="PHQ", language="en", alias_type="acronym",
            source=self.source, source_note="Synthetic acronym", review_status="reviewed")
        self.assertEqual([row["slug"] for row in self.search("PHQ")["assessments"]], [self.instrument.slug, other.slug])

    def test_unreviewed_aliases_are_neither_searchable_nor_graph_labels(self):
        m.BrainAnatomicalAlias.objects.create(entity=self.child, text="PrivateBrainToken", language="en")
        m.AssessmentAlias.objects.create(instrument=self.instrument, text="PrivateAssessmentToken", language="en",
            alias_type="name", source=self.source, source_note="Synthetic unreviewed spelling")
        self.assertEqual(self.search("PrivateBrainToken")["brain_entities"], [])
        self.assertEqual(self.search("PrivateAssessmentToken")["assessments"], [])
        self.assertNotIn("PrivateBrainToken", str(self.graph()))
        self.assertNotIn("PrivateAssessmentToken", str(self.graph()))

    def test_inactive_parent_hides_entire_brain_branch(self):
        self.root.is_active = False
        self.root.save(update_fields=["is_active"])
        self.assertEqual(self.search("Fixture")["brain_entities"], [])
        self.assertEqual(self.graph(node_type="brain_anatomy")["nodes"], [])
        response = self.client.get("/api/concept-map/path/", {"from": "brain_anatomy:fixture-child", "to": "brain_anatomy:fixture-root"})
        self.assertEqual(response.status_code, 404)

    def test_inactive_or_unreviewed_instruments_hide_search_and_graph(self):
        for field, value in (("is_active", False), ("review_status", "unreviewed")):
            setattr(self.instrument, field, value)
            self.instrument.save(update_fields=[field])
            self.assertEqual(self.search("PHQ")["assessments"], [])
            self.assertNotIn("assessment:" + self.instrument.slug, {node["id"] for node in self.graph()["nodes"]})
            setattr(self.instrument, field, True if field == "is_active" else "reviewed")
            self.instrument.save(update_fields=[field])

    def test_version_alias_and_nested_summary_require_public_version(self):
        m.AssessmentAlias.objects.create(instrument=self.instrument, version=self.version, text="SyntheticVersionToken",
            language="en", alias_type="acronym", source=self.source, source_note="Synthetic version spelling", review_status="reviewed")
        self.assertEqual(len(self.search("SyntheticVersionToken")["assessments"]), 1)
        self.version.is_active = False
        self.version.save(update_fields=["is_active"])
        self.assertEqual(self.search("SyntheticVersionToken")["assessments"], [])
        rows = self.search(self.instrument.slug)["assessments"]
        self.assertEqual(rows[0]["versions"]["results"], [])
        self.assertEqual(len(rows), 1)

    def test_unresolved_entity_or_hierarchy_provenance_fails_closed(self):
        # Corruption fixtures deliberately bypass guarded curator writes.
        QuerySet.update(m.BrainHierarchyLinkSource.objects.filter(relationship=self.link), note="\u00a0")
        self.assertEqual(self.search("FC")["brain_entities"], [])
        self.assertEqual(self.graph(node_type="brain_anatomy")["edges"], [])
        QuerySet.update(m.SourceReference.objects.filter(pk=self.brain_source.pk), verification_status="citation_from_model_knowledge")
        self.assertEqual(self.graph(node_type="brain_anatomy")["nodes"], [])

    def test_graph_nodes_metadata_domain_and_kind_filters(self):
        data = self.graph()
        self.assertEqual(data["meta"]["node_types"]["brain_anatomy"], 2)
        self.assertEqual(data["meta"]["node_types"]["assessment"], m.AssessmentInstrument.objects.count())
        by_id = {node["id"]: node for node in data["nodes"]}
        self.assertEqual(by_id["brain_anatomy:fixture-child"]["href"], "/brain/fixture-child")
        self.assertEqual(by_id["assessment:" + self.instrument.slug]["href"], "/assessments/" + self.instrument.slug)
        for node_type in ("brain_anatomy", "assessment"):
            self.assertEqual(self.graph(node_type=node_type)["nodes"], self.graph(domain=node_type)["nodes"])
            self.assertTrue(all(node["review_status"] == "reviewed" for node in self.graph(node_type=node_type)["nodes"]))
        self.assertEqual([node["slug"] for node in self.graph(node_type="brain_anatomy", kind="structure")["nodes"]], [self.child.slug])

    def test_graph_hierarchy_retains_predicate_direction_and_claim_provenance(self):
        data = self.graph(node_type="brain_anatomy", relation="brain_part_of")
        self.assertEqual(data["meta"]["available_edge_kinds"]["brain_part_of"], 1)
        edge, = data["edges"]
        self.assertEqual((edge["source"], edge["target"]), ("brain_anatomy:fixture-child", "brain_anatomy:fixture-root"))
        self.assertEqual(edge["predicate"], "part_of")
        self.assertEqual(edge["direction"], "child_to_parent")
        self.assertTrue(edge["structural"])
        self.assertEqual(edge["source_version"], "Fixture v1")
        self.assertEqual(edge["sources"][0]["id"], self.brain_source.pk)
        self.assertEqual(edge["sources"][0]["note"], "Synthetic part-of claim")

    def test_graph_maps_only_public_version_aliases_to_canonical_families(self):
        def family_aliases():
            return next(node["aliases"] for node in self.graph(node_type="assessment")["nodes"]
                        if node["slug"] == self.instrument.slug)
        self.assertIn("PHQ-9", family_aliases())
        bdi = next(node for node in self.graph(node_type="assessment")["nodes"]
                   if node["slug"] == "beck-depression-inventory")
        self.assertIn("BDI-II", bdi["aliases"])
        self.version.is_active = False
        self.version.save(update_fields=["is_active"])
        self.assertNotIn("PHQ-9", family_aliases())
        self.version.is_active = True
        self.version.save(update_fields=["is_active"])
        alias = self.instrument.aliases.get(text="PHQ-9")
        alias.review_status = "unreviewed"
        alias.save(update_fields=["review_status"])
        self.assertNotIn("PHQ-9", family_aliases())
        self.assertEqual({node["type"] for node in self.graph(node_type="assessment")["nodes"]}, {"assessment"})

    def test_no_network_version_study_finding_or_crossdomain_edges(self):
        self.add_relations(self.child)
        data = self.graph()
        self.assertFalse({node["type"] for node in data["nodes"]} & {"brain_network", "assessment_version", "study", "finding"})
        new_ids = {node["id"] for node in data["nodes"] if node["type"] in {"brain_anatomy", "assessment"}}
        incident = [edge for edge in data["edges"] if edge["source"] in new_ids or edge["target"] in new_ids]
        self.assertEqual({edge["kind"] for edge in incident}, {"brain_part_of"})

    def test_paths_require_structural_opt_in_and_preserve_reverse_direction(self):
        params = {"from": "brain_anatomy:fixture-root", "to": "brain_anatomy:fixture-child"}
        self.assertFalse(self.client.get("/api/concept-map/path/", params).json()["found"])
        for opt_in in ({"include_structural": "1"}, {"relation": "brain_part_of"}):
            data = self.client.get("/api/concept-map/path/", dict(params, **opt_in)).json()
            self.assertTrue(data["found"])
            self.assertTrue(data["structural_edges_included"])
            self.assertEqual(data["edges"][0]["traversal_direction"], "reverse")
            self.assertEqual(data["edges"][0]["source"], params["to"])
        data = self.client.get("/api/concept-map/path/", {"from": params["to"], "to": params["from"], "relation": "brain_part_of"}).json()
        self.assertEqual(data["edges"][0]["traversal_direction"], "forward")
        data = self.client.get("/api/concept-map/path/", {"from": params["from"], "to": "assessment:" + self.instrument.slug,
                                                        "include_structural": "1"}).json()
        self.assertFalse(data["found"])

    def test_neighborhood_accepts_new_types_without_inventing_links(self):
        concept = m.Concept.objects.create(slug="synthetic-center", name_en="Synthetic center", simple_definition="Test only")
        for node_type in ("brain_anatomy", "assessment"):
            response = self.client.get(f"/api/concepts/{concept.slug}/neighborhood/", {"node_type": node_type})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([node["id"] for node in response.json()["nodes"]], ["concept:" + concept.slug])
        self.assertEqual(self.client.get("/api/concept-map/", {"node_type": "brain_network"}).status_code, 400)

    def test_invalidation_covers_included_entities_aliases_parents_and_sources(self):
        for model in (m.BrainAnatomicalEntity, m.BrainAnatomicalAlias, m.BrainAnatomicalEntitySource,
                      m.BrainHierarchyLink, m.BrainHierarchyLinkSource, m.AssessmentInstrument, m.AssessmentVersion,
                      m.AssessmentAlias, m.AssessmentSource, m.SourceReference):
            self.assertIn(model, GRAPH_MODELS)

    def test_query_counts_do_not_scale_with_public_entities(self):
        def count(url, params=None):
            with CaptureQueriesContext(connection) as captured:
                response = self.client.get(url, params or {})
            self.assertEqual(response.status_code, 200)
            return len(captured)
        before_graph = count("/api/concept-map/")
        before_search = count("/api/search/", {"q": "Fixture"})
        for index in range(12):
            self.anatomy(f"fixture-extra-{index}", name_en=f"Fixture Extra {index}")
            self.synthetic_instrument(f"synthetic-extra-{index}", f"Fixture Instrument {index}")
        self.assertEqual(count("/api/concept-map/"), before_graph)
        # Assessments start matching here: their bounded prefetch adds four fixed reads.
        self.assertLessEqual(count("/api/search/", {"q": "Fixture"}), before_search + 4)
        self.assertEqual(len(self.search("Fixture")["brain_entities"]), 10)
        self.assertEqual(len(self.search("Fixture")["assessments"]), 10)


@override_settings(REST_FRAMEWORK={"DEFAULT_THROTTLE_CLASSES": []})
class GraphTransactionTests(BrainFixtureMixin, TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.setUpTestData()
        self.client = APIClient()

    def test_commit_revocation_clears_cache_rebuilt_by_another_reader(self):
        initial = _get_atlas_graph()
        self.assertIsNotNone(cache.get("atlas_graph"))
        with transaction.atomic():
            self.root.is_active = False
            self.root.save(update_fields=["is_active"])
            # Another connection can still read the previous committed state.
            cache.set("atlas_graph", initial)
        self.assertIsNone(cache.get("atlas_graph"))
        self.assertEqual(_get_atlas_graph()[0], [])

    def test_rollback_cannot_publish_uncommitted_graph_into_shared_cache(self):
        initial = _get_atlas_graph()
        with transaction.atomic():
            self.root.is_active = False
            self.root.save(update_fields=["is_active"])
            self.assertEqual(_get_atlas_graph()[0], [])
            self.assertIsNone(cache.get("atlas_graph"))
            transaction.set_rollback(True)
        self.assertEqual(_get_atlas_graph(), initial)

    def test_alias_and_relation_source_changes_clear_warm_graph(self):
        _get_atlas_graph()
        alias = self.child.aliases.get()
        alias.review_status = "unreviewed"
        alias.save(update_fields=["review_status"])
        self.assertIsNone(cache.get("atlas_graph"))
        self.assertNotIn("FC", str(_get_atlas_graph()))
        self.link.review_status = "unreviewed"
        self.link.save(update_fields=["review_status"])
        _get_atlas_graph()
        source_link = self.link.source_links.get()
        source_link.note = "Changed synthetic claim"
        source_link.save(update_fields=["note"])
        self.assertIsNone(cache.get("atlas_graph"))
        self.link.review_status = "reviewed"
        self.link.save(update_fields=["review_status"])
        self.assertEqual(_get_atlas_graph()[1][0]["sources"][0]["note"], source_link.note)

    def test_shared_source_update_invalidates_and_bulk_update_is_guarded(self):
        source = m.SourceReference.objects.create(title="Synthetic unused source", citation="Test only",
            url="https://example.org/unused-source", verification_status="verified")
        _get_atlas_graph()
        m.SourceReference.objects.filter(pk=source.pk).update(title="Changed synthetic source")
        self.assertIsNone(cache.get("atlas_graph"))
        source.refresh_from_db()
        self.assertEqual(source.title, "Changed synthetic source")
        initial = _get_atlas_graph()
        source.title = "Unsupported bulk replacement"
        with self.assertRaises(ValidationError), transaction.atomic():
            m.SourceReference.objects.bulk_update([source], ["title"])
        source.refresh_from_db()
        self.assertEqual(source.title, "Changed synthetic source")
        self.assertEqual(_get_atlas_graph(), initial)

    def test_revocation_during_cold_build_cannot_cache_old_public_data(self):
        from .views import _build_atlas_graph

        def concurrent_revocation():
            snapshot = _build_atlas_graph()
            self.root.is_active = False
            self.root.save(update_fields=["is_active"])
            return snapshot

        with patch("atlas.views._build_atlas_graph", side_effect=concurrent_revocation):
            _get_atlas_graph()
        self.assertEqual(_get_atlas_graph()[0], [])

    def test_revocation_between_revision_check_and_cache_set_rejects_old_entry(self):
        original_set = cache.set

        def concurrent_set(key, value, *args, **kwargs):
            if key == "atlas_graph":
                self.root.is_active = False
                self.root.save(update_fields=["is_active"])
            return original_set(key, value, *args, **kwargs)

        with patch("atlas.views.cache.set", side_effect=concurrent_set):
            _get_atlas_graph()
        self.assertEqual(_get_atlas_graph()[0], [])

    def test_parent_change_rebuilds_only_the_curated_primary_edge(self):
        other = self.anatomy("fixture-other-parent", name_en="Other synthetic parent")
        _get_atlas_graph()
        self.link.review_status = "unreviewed"
        self.link.parent = other
        self.link.save()
        self.link.review_status = "reviewed"
        self.link.save(update_fields=["review_status"])
        self.assertIsNone(cache.get("atlas_graph"))
        self.assertEqual(_get_atlas_graph()[1][0]["target"], "brain_anatomy:" + other.slug)
        old_path = self.client.get("/api/concept-map/path/", {
            "from": "brain_anatomy:" + self.root.slug, "to": "brain_anatomy:" + self.child.slug, "relation": "brain_part_of",
        })
        self.assertFalse(old_path.json()["found"])


@override_settings(REST_FRAMEWORK={"DEFAULT_THROTTLE_CLASSES": []})
class GraphPublicationTests(TransactionTestCase):
    def setUp(self):
        cache.clear()

    def test_controlled_publication_and_dry_run_invalidate_without_bulk_bypass(self):
        self.assertEqual(_get_atlas_graph()[0], [])
        publish_brain(dry_run=True)
        publish_assessments(apply=False)
        self.assertEqual(_get_atlas_graph()[0], [])
        publish_brain(dry_run=False)
        publish_assessments(apply=True)
        self.assertIsNone(cache.get("atlas_graph"))
        nodes, edges, kinds = _get_atlas_graph()
        self.assertEqual(sum(node["type"] == "brain_anatomy" for node in nodes), 87)
        self.assertEqual(sum(node["type"] == "assessment" for node in nodes), 4)
        self.assertEqual(kinds["brain_part_of"], 70)
        self.assertEqual({edge["kind"] for edge in edges}, {"brain_part_of"})
