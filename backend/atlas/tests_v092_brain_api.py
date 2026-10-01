"""Synthetic fixtures only; none of these names or claims are atlas content."""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models.query import QuerySet
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .models import (
    BrainAnatomicalAlias, BrainAnatomicalEntity, BrainAnatomicalEntitySource,
    BrainHierarchyLink, BrainHierarchyLinkSource, ScientificReviewStatus, SourceReference,
    BrainNetwork, BrainNetworkSource, BrainNetworkMembership, BrainNetworkMembershipSource,
    BrainFunctionalAssociation, BrainFunctionalAssociationSource, BrainExternalIdentifier, Concept,
)


class BrainFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.source = SourceReference.objects.create(
            title="Synthetic API source", citation="Synthetic test citation, v1",
            url="https://example.org/test-only", verification_status="source_checked",
        )
        cls.root = cls.anatomy("fixture-root", name_en="Fixture Root", kind="whole_brain")
        cls.child = cls.anatomy("fixture-child", name_en="Fixture Child", name_fa="کانون یک")
        cls.link = BrainHierarchyLink.objects.create(child=cls.child, parent=cls.root, source_version="Fixture v1")
        BrainHierarchyLinkSource.objects.create(relationship=cls.link, source=cls.source, note="Synthetic part-of claim")
        cls.link.review_status = ScientificReviewStatus.REVIEWED
        cls.link.save()
        BrainAnatomicalAlias.objects.create(entity=cls.child, text="FC", language="en", alias_type="abbreviation",
            review_status="reviewed", source=cls.source, source_note="Synthetic abbreviation support")

    @classmethod
    def anatomy(cls, slug, **kwargs):
        entity = BrainAnatomicalEntity.objects.create(
            slug=slug, kind=kwargs.pop("kind", "structure"), laterality=kwargs.pop("laterality", "bilateral"),
            name_en=kwargs.pop("name_en", slug), **kwargs,
        )
        BrainAnatomicalEntitySource.objects.create(entity=entity, source=cls.source, note="Synthetic identity")
        entity.review_status = ScientificReviewStatus.REVIEWED
        entity.save()
        return entity

    def setUp(self):
        self.client = APIClient()

    @classmethod
    def add_relations(cls, entity):
        network = BrainNetwork.objects.create(slug="fixture-network", name_en="Fixture Network")
        BrainNetworkSource.objects.create(network=network, source=cls.source)
        network.review_status = "reviewed"
        network.save()
        concept = Concept.objects.create(slug="fixture-construct", name_en="Fixture Construct", simple_definition="Test only")
        membership = BrainNetworkMembership.objects.create(evidence_key="fixture-membership", entity=entity, network=network,
            source_version="Synthetic v1", method="Test method", qualifier="Test qualification")
        association = BrainFunctionalAssociation.objects.create(evidence_key="fixture-function", entity=entity, concept=concept,
            source_version="Synthetic v1", method="Test method", explanation_en="Test association only",
            task_context="Test task", population_context="Test population", limitations="Association is not causation")
        for row, source_model in ((membership, BrainNetworkMembershipSource), (association, BrainFunctionalAssociationSource)):
            source_model.objects.create(relationship=row, source=cls.source, note="Synthetic supported claim")
            row.review_status = "reviewed"
            row.save()
        return network, membership, association


class BrainAPITests(BrainFixtureMixin, TestCase):
    def test_public_list_pagination_order_and_provenance(self):
        response = self.client.get("/api/brain-anatomy/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual([row["slug"] for row in response.data["results"]], [self.child.slug, self.root.slug])
        self.assertEqual(response.data["results"][0]["sources"][0]["source"]["citation"], self.source.citation)

    def test_detail_has_reviewed_part_of_and_missing_is_404(self):
        response = self.client.get(f"/api/brain-anatomy/{self.child.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["parent"]["predicate"], "part_of")
        self.assertEqual(response.data["parent"]["entity"]["slug"], self.root.slug)
        self.assertEqual(response.data["parent"]["sources"][0]["note"], "Synthetic part-of claim")
        self.assertEqual(self.client.get("/api/brain-anatomy/absent/").status_code, 404)

    def test_search_names_persian_variants_aliases_and_slug(self):
        for query in ("Fixture Child", "کانون یک", "كانون يك", "FC", "fixture-child"):
            with self.subTest(query=query):
                response = self.client.get("/api/brain-anatomy/", {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["slug"] for row in response.data["results"]], [self.child.slug])

    def test_valid_and_malformed_filters(self):
        response = self.client.get("/api/brain-anatomy/", {"kind": "structure", "laterality": "bilateral", "parent": self.root.slug})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        for params in ({"kind": "brain"}, {"laterality": "both"}, {"parent": "bad/slug"}, {"parent": "absent"}, {"review_status": "unreviewed"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/brain-anatomy/", params).status_code, 400)

    def test_inactive_or_unreviewed_ancestry_is_excluded(self):
        for field, value in (("is_active", False), ("review_status", ScientificReviewStatus.UNREVIEWED)):
            setattr(self.root, field, value)
            self.root.save()
            self.assertEqual(self.client.get(f"/api/brain-anatomy/{self.child.slug}/").status_code, 404)
            self.assertEqual(self.client.get("/api/brain-anatomy/").data["count"], 0)
            setattr(self.root, field, True if field == "is_active" else ScientificReviewStatus.REVIEWED)
            self.root.save()

    def test_unreviewed_hierarchy_and_weak_sources_cannot_be_public(self):
        self.link.review_status = ScientificReviewStatus.SOURCE_CHECKED
        self.link.save()
        self.assertEqual(self.client.get(f"/api/brain-anatomy/{self.child.slug}/").status_code, 404)
        QuerySet.update(SourceReference.objects.filter(pk=self.source.pk), verification_status="citation_from_model_knowledge")
        self.assertEqual(self.client.get("/api/brain-anatomy/").data["count"], 0)

    def test_public_api_is_read_only(self):
        self.assertEqual(self.client.post("/api/brain-anatomy/", {}).status_code, 405)

    def test_new_unreviewed_alias_is_not_public_or_searchable(self):
        alias = BrainAnatomicalAlias.objects.create(entity=self.child, text="Unverified Alias", language="fa")
        detail = self.client.get(f"/api/brain-anatomy/{self.child.slug}/").data
        self.assertNotIn(alias.text, [row["text"] for row in detail["aliases"]])
        self.assertEqual(self.client.get("/api/brain-anatomy/", {"q": alias.text}).data["count"], 0)
        alias.source = self.source
        alias.source_note = "Synthetic reviewed spelling"
        alias.review_status = "reviewed"
        alias.save()
        self.assertEqual(self.client.get("/api/brain-anatomy/", {"q": alias.text}).data["count"], 1)

    def test_external_identifiers_require_individual_review_and_mapping_provenance(self):
        identifier = BrainExternalIdentifier.objects.create(
            entity=self.child, namespace="Synthetic Atlas", identifier="S-17", source_version="Test v1", source=self.source,
        )
        url = f"/api/brain-anatomy/{self.child.slug}/"
        self.assertEqual(self.client.get(url).data["external_identifiers"], [])
        identifier.review_status = "reviewed"
        with self.assertRaises(ValidationError):
            identifier.save()
        identifier.source_note = "Synthetic identifier mapping"
        identifier.save()
        published = self.client.get(url).data["external_identifiers"]
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["review_status"], "reviewed")
        self.assertEqual(published[0]["source_note"], "Synthetic identifier mapping")
        identifier.identifier = "S-18"
        with self.assertRaises(ValidationError):
            identifier.save()
        identifier.review_status = "unreviewed"
        with self.assertRaises(ValidationError):
            identifier.save(update_fields=["identifier"])
        identifier.save()
        self.assertEqual(self.client.get(url).data["external_identifiers"], [])
        QuerySet.update(BrainExternalIdentifier.objects.filter(pk=identifier.pk), review_status="reviewed", source_note="\u00a0")
        self.assertEqual(self.client.get(url).data["external_identifiers"], [])

    def test_hierarchy_provenance_excludes_blank_claim_links(self):
        other = SourceReference.objects.create(title="Synthetic second source", citation="Synthetic citation",
                                              url="https://example.org/second", verification_status="verified")
        self.link.review_status = "unreviewed"
        self.link.save(update_fields=["review_status"])
        citation = BrainHierarchyLinkSource.objects.create(relationship=self.link, source=other, note="Synthetic second claim")
        self.link.review_status = "reviewed"
        self.link.save(update_fields=["review_status"])
        QuerySet.update(BrainHierarchyLinkSource.objects.filter(pk=citation.pk), note="\u00a0")
        parent = self.client.get(f"/api/brain-anatomy/{self.child.slug}/").data["parent"]
        self.assertEqual(len(parent["sources"]), 1)
        self.assertEqual(parent["sources"][0]["source"]["id"], self.source.pk)

    def test_malformed_source_locator_cannot_pass_publication_gate(self):
        from .brain_publication import source_is_resolved

        QuerySet.update(SourceReference.objects.filter(pk=self.source.pk), url="", pmid="12345\n")
        self.source.refresh_from_db()
        self.assertFalse(source_is_resolved(self.source))
        self.assertEqual(self.client.get("/api/brain-anatomy/").data["count"], 0)

    def test_whitespace_only_sources_have_matching_python_and_sql_gates(self):
        from .brain_publication import source_is_resolved, resolved_sources

        for whitespace in ("\f", "\v", "\u00a0", "\u0085", "\u2003", "\u3000", "\x1c"):
            for field in ("title", "citation"):
                with self.subTest(whitespace=repr(whitespace), field=field):
                    self.source.title = "Synthetic title"
                    self.source.citation = "Synthetic citation"
                    setattr(self.source, field, whitespace)
                    QuerySet.update(SourceReference.objects.filter(pk=self.source.pk), title=self.source.title, citation=self.source.citation)
                    self.assertFalse(source_is_resolved(self.source))
                    self.assertFalse(resolved_sources().filter(pk=self.source.pk).exists())
                    self.assertEqual(self.client.get("/api/brain-anatomy/").data["count"], 0)

    def test_multiple_alias_hits_do_not_duplicate_or_change_exact_rank(self):
        BrainAnatomicalAlias.objects.create(entity=self.child, text="FC additional", language="en",
            review_status="reviewed", source=self.source, source_note="Synthetic abbreviation support")
        partial = self.anatomy("test-partial", name_en="AAA FC partial")
        response = self.client.get("/api/brain-anatomy/", {"q": "FC"})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual([row["slug"] for row in response.data["results"]], [self.child.slug, partial.slug])

    def test_approved_relations_keep_distinct_context_and_exclude_inactive_endpoints(self):
        network, membership, association = self.add_relations(self.child)
        response = self.client.get(f"/api/brain-anatomy/{self.child.slug}/")
        self.assertEqual(response.data["network_memberships"][0]["predicate"], "participates_in_network")
        function = response.data["functional_associations"][0]
        self.assertEqual(function["predicate"], "functional_association")
        self.assertEqual(function["limitations"], "Association is not causation")
        self.assertEqual(function["sources"][0]["note"], "Synthetic supported claim")
        network.is_active = False
        network.save()
        association.concept.is_active = False
        association.concept.save()
        response = self.client.get(f"/api/brain-anatomy/{self.child.slug}/")
        self.assertEqual(response.data["network_memberships"], [])
        self.assertEqual(response.data["functional_associations"], [])

    def test_relation_with_multiple_sources_is_serialized_once(self):
        network, membership, association = self.add_relations(self.child)
        other = SourceReference.objects.create(title="Other test source", citation="Synthetic secondary evidence",
                                              url="https://example.org/other", verification_status="verified")
        network.review_status = "unreviewed"
        network.save(update_fields=["review_status"])
        BrainNetworkSource.objects.create(network=network, source=other)
        network.review_status = "reviewed"
        network.save(update_fields=["review_status"])
        membership.review_status = "unreviewed"
        membership.save(update_fields=["review_status"])
        BrainNetworkMembershipSource.objects.create(relationship=membership, source=other, note="Second synthetic claim source")
        membership.review_status = "reviewed"
        membership.save(update_fields=["review_status"])
        response = self.client.get(f"/api/brain-anatomy/{self.child.slug}/")
        self.assertEqual(len(response.data["network_memberships"]), 1)
        self.assertEqual(len(response.data["network_memberships"][0]["sources"]), 2)

    def test_pagination_cap_pages_and_no_staging_exposure(self):
        response = self.client.get("/api/brain-anatomy/", {"page_size": 1})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(self.client.get("/api/brain-anatomy/", {"page": 999}).status_code, 404)
        detail = self.client.get(f"/api/brain-anatomy/{self.child.slug}/").data
        for field in ("raw_document", "raw_text", "payload", "seed_managed", "promoted_pk", "metadata"):
            self.assertNotIn(field, detail)
        self.assertEqual(self.client.get("/api/brain-networks/").status_code, 404)

    def test_corrupt_cycle_unsourced_entity_and_blank_claim_fail_closed(self):
        returning = BrainHierarchyLink.objects.create(child=self.root, parent=self.child, source_version="Test v1", is_active=False)
        BrainHierarchyLinkSource.objects.create(relationship=returning, source=self.source, note="Synthetic cycle test")
        returning.review_status = "reviewed"
        returning.save()
        QuerySet.update(BrainHierarchyLink.objects.filter(pk=returning.pk), is_active=True)
        self.assertEqual(self.client.get("/api/brain-anatomy/").data["count"], 0)
        QuerySet.update(BrainHierarchyLink.objects.filter(pk=returning.pk), is_active=False)
        citation = self.link.source_links.get()
        QuerySet.update(BrainHierarchyLinkSource.objects.filter(pk=citation.pk), note="\n\t")
        self.assertEqual(self.client.get(f"/api/brain-anatomy/{self.child.slug}/").status_code, 404)
        unsourced = BrainAnatomicalEntity.objects.create(slug="corrupt-unsourced", name_en="Test Unsourced", kind="structure", laterality="bilateral")
        QuerySet.update(BrainAnatomicalEntity.objects.filter(pk=unsourced.pk), review_status="reviewed")
        self.assertEqual(self.client.get(f"/api/brain-anatomy/{unsourced.slug}/").status_code, 404)


class BrainQueryProfileTests(BrainFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.add_relations(cls.root)
        for number in range(35):
            BrainExternalIdentifier.objects.create(
                entity=cls.root, namespace="Synthetic Profile Atlas", identifier=f"Profile-{number:03}",
                source_version="Test v1", source=cls.source, review_status="reviewed",
                source_note="Synthetic profiling mapping claim",
            )
        for number in range(45):
            entity = cls.anatomy(f"profile-{number:03}", name_en=f"Profile Test {number:03}")
            BrainAnatomicalAlias.objects.create(entity=entity, text=f"Test Alias {number}", language="en",
                review_status="reviewed", source=cls.source, source_note="Synthetic search fixture alias")
            link = BrainHierarchyLink.objects.create(child=entity, parent=cls.root, source_version="Test profile v1")
            BrainHierarchyLinkSource.objects.create(relationship=link, source=cls.source, note="Synthetic profiling hierarchy")
            link.review_status = "reviewed"
            link.save()

    def test_profile_and_nested_bounds(self):
        measurements = {}
        for label, url, params in (
            ("list", "/api/brain-anatomy/", {}),
            ("detail", f"/api/brain-anatomy/{self.root.slug}/", {}),
            ("search", "/api/brain-anatomy/", {"q": "Test Alias"}),
            ("filters", "/api/brain-anatomy/", {"parent": self.root.slug, "kind": "structure"}),
        ):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200)
            measurements[label] = len(queries)
            if label == "detail":
                self.assertEqual(len(response.data["children"]), 30)
                self.assertTrue(response.data["children_truncated"])
                self.assertEqual(len(response.data["external_identifiers"]), 30)
                self.assertTrue(response.data["external_identifiers_truncated"])
        print(f"Brain test-only fixture query measurements: {measurements}")
        # Budgets frozen after observing populated fixtures, including relation sources.
        for label, budget in {"list": 4, "detail": 11, "search": 4, "filters": 5}.items():
            self.assertLessEqual(measurements[label], budget, label)
        with CaptureQueriesContext(connection) as small_page:
            self.assertEqual(self.client.get("/api/brain-anatomy/", {"page_size": 1}).status_code, 200)
        self.assertEqual(len(small_page), measurements["list"])

    def test_default_and_maximum_page_sizes(self):
        for number in range(270):
            self.anatomy(f"page-cap-{number:03}", name_en=f"Page Cap Test {number:03}")
        default = self.client.get("/api/brain-anatomy/")
        self.assertEqual(len(default.data["results"]), 30)
        capped = self.client.get("/api/brain-anatomy/", {"page_size": 10000})
        self.assertGreater(capped.data["count"], 300)
        self.assertEqual(len(capped.data["results"]), 300)


class BrainSourceLocatorTests(TestCase):
    def test_django_persistence_and_publication_reject_malformed_url_hosts(self):
        from django.core.exceptions import ValidationError
        from .brain_publication import source_is_resolved, resolved_sources

        source = SourceReference.objects.create(title="Synthetic URL source", citation="Synthetic evidence",
            url="https://example.org/test", verification_status="source_checked")
        values = (("https://x<>", False), ("https://example.org:bad", False), ("https://example.org:65536", False),
                  ("https://-bad.example.org", False), ("https://999.999.999.999", False),
                  ("https://[:::]", False), ("https://example.org/\n", False), ("https://example.org/\x1c", False), ("https://example.org/\u2003", False),
                  ("https://EXAMPLE.org:443/test?q=1#part", True), ("https://127.0.0.1/test", True))
        for url, valid in values:
            with self.subTest(url=url):
                if not valid:
                    source.url = url
                    with self.assertRaises(ValidationError):
                        source.save()
                QuerySet.update(SourceReference.objects.filter(pk=source.pk), url=url)
                source.refresh_from_db()
                self.assertEqual(source_is_resolved(source), valid)
                self.assertEqual(resolved_sources().filter(pk=source.pk).exists(), valid)

    def test_doi_and_pmid_model_bounds_match_publication_on_both_engines(self):
        from django.core.exceptions import ValidationError
        from django.db import connection
        from .brain_publication import source_is_resolved, resolved_sources

        source = SourceReference.objects.create(title="Synthetic identifier bounds", citation="Synthetic evidence",
            url="https://example.org/identifier-bounds", verification_status="source_checked")
        for field, value in (("doi", "10.1234/" + "a" * 248), ("pmid", "1" * 65)):
            source.refresh_from_db()
            setattr(source, field, value)
            self.assertFalse(source_is_resolved(source))
            with self.subTest(field=field), self.assertRaises(ValidationError):
                source.save(update_fields=[field])
            if connection.vendor == "sqlite":
                QuerySet.update(SourceReference.objects.filter(pk=source.pk), **{field: value})
                self.assertFalse(resolved_sources().filter(pk=source.pk).exists())
                QuerySet.update(SourceReference.objects.filter(pk=source.pk), **{field: ""})

    def test_doi_whitespace_is_rejected_identically_by_python_and_sql(self):
        from .brain_publication import source_is_resolved, resolved_sources

        source = SourceReference.objects.create(title="Synthetic DOI whitespace", citation="Synthetic evidence",
            url="https://example.org/doi-whitespace", verification_status="source_checked")
        for whitespace in ("\x1c", "\u00a0", "\u2003", "\u3000"):
            QuerySet.update(SourceReference.objects.filter(pk=source.pk), doi="10.1234/" + whitespace)
            source.refresh_from_db()
            with self.subTest(whitespace=repr(whitespace)):
                self.assertFalse(source_is_resolved(source))
                self.assertFalse(resolved_sources().filter(pk=source.pk).exists())
