"""Approved relation semantics exercised with synthetic test evidence only."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction, connection, close_old_connections
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from queue import SimpleQueue
from threading import Event, Thread
from unittest import skipUnless
from unittest.mock import patch

from .models import (
    BrainAnatomicalEntity, BrainAnatomicalEntitySource, BrainFunctionalAssociation,
    BrainFunctionalAssociationSource, BrainNetwork, BrainNetworkMembership,
    BrainNetworkMembershipSource, BrainNetworkSource, BrainHierarchyLink, BrainHierarchyLinkSource,
    Concept, ScientificReviewStatus, SourceReference,
)


class BrainRelationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = SourceReference.objects.create(title="Synthetic relation source", citation="Test evidence only",
                                                  url="https://example.org/test-evidence", verification_status="source_checked")
        cls.entity = BrainAnatomicalEntity.objects.create(slug="test-entity", name_en="Test Entity", kind="structure", laterality="bilateral")
        BrainAnatomicalEntitySource.objects.create(entity=cls.entity, source=cls.source)
        cls.network = BrainNetwork.objects.create(slug="test-network", name_en="Test Network")
        cls.concept = Concept.objects.create(slug="test-construct", name_en="Test Construct", simple_definition="Test only")

    def membership(self, **kwargs):
        return BrainNetworkMembership.objects.create(
            evidence_key=kwargs.pop("evidence_key", "test-membership"), entity=kwargs.pop("entity", self.entity),
            network=kwargs.pop("network", self.network), source_version="Test definition v1",
            method="Test membership method", qualifier="Participation in test definition only", **kwargs,
        )

    def association(self, **kwargs):
        return BrainFunctionalAssociation.objects.create(
            evidence_key=kwargs.pop("evidence_key", "test-association"), concept=self.concept,
            entity=kwargs.pop("entity", self.entity), network=kwargs.pop("network", None),
            source_version="Test extraction v1", method="Test method", task_context="Test task",
            population_context="Test population", limitations="Synthetic association is not causation",
            explanation_en="Synthetic construct association", **kwargs,
        )

    def test_distinct_predicates_and_no_inferred_review(self):
        membership = self.membership()
        association = self.association()
        self.assertEqual(membership.predicate, "participates_in_network")
        self.assertEqual(association.predicate, "functional_association")
        self.assertEqual(membership.review_status, "unreviewed")
        self.assertFalse(association.seed_managed)

    def test_network_and_anatomy_are_exclusive_association_subjects(self):
        self.association(entity=None, network=self.network)
        for endpoints in ((None, None), (self.entity, self.network)):
            with self.subTest(endpoints=endpoints), self.assertRaises(ValidationError):
                self.association(evidence_key="invalid-subject", entity=endpoints[0], network=endpoints[1])

    def test_database_enforces_exactly_one_association_subject(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrainFunctionalAssociation._base_manager.bulk_create([
                BrainFunctionalAssociation(evidence_key="bad-subject", entity=self.entity, network=self.network, concept=self.concept)
            ])

    def test_checked_relations_require_relation_level_resolved_sources(self):
        for relation, source_model in ((self.membership(), BrainNetworkMembershipSource),
                                       (self.association(), BrainFunctionalAssociationSource)):
            with self.subTest(model=type(relation).__name__):
                relation.review_status = ScientificReviewStatus.REVIEWED
                with self.assertRaises(ValidationError):
                    relation.save()
                source_model.objects.create(relationship=relation, source=self.source, note="Exact synthetic claim support")
                relation.save()
                self.assertEqual(relation.review_status, ScientificReviewStatus.REVIEWED)
                with self.assertRaises(ProtectedError):
                    relation.source_links.all().delete()
                with self.assertRaises(ProtectedError):
                    self.source.delete()

    def test_weak_or_incomplete_source_does_not_support_review(self):
        relation = self.membership()
        weak = SourceReference.objects.create(title="Weak test source", verification_status="citation_from_model_knowledge")
        BrainNetworkMembershipSource.objects.create(relationship=relation, source=weak, note="Unverified test claim")
        relation.review_status = ScientificReviewStatus.SOURCE_CHECKED
        with self.assertRaises(ValidationError):
            relation.save()

    def test_reviewed_relation_context_and_endpoints_require_new_review(self):
        other = BrainAnatomicalEntity.objects.create(slug="other-test-entity", name_en="Other Test Entity",
                                                     kind="structure", laterality="bilateral")
        for relation, source_model in ((self.membership(), BrainNetworkMembershipSource),
                                       (self.association(), BrainFunctionalAssociationSource)):
            source_model.objects.create(relationship=relation, source=self.source, note="Synthetic reviewed claim")
            relation.review_status = "reviewed"
            relation.save()
            fields = relation.required_context + ("explanation_fa",)
            for field in fields:
                with self.subTest(model=type(relation).__name__, field=field):
                    relation.refresh_from_db()
                    setattr(relation, field, "Changed unreviewed scientific context")
                    with self.assertRaises(ValidationError):
                        relation.save()
            relation.refresh_from_db()
            relation.entity = other
            with self.assertRaises(ValidationError):
                relation.save()
            relation.refresh_from_db()
            relation.method = "Changed unreviewed method"
            relation.review_status = "unreviewed"
            with self.assertRaises(ValidationError):
                relation.save(update_fields=["method"])
            relation.save()
            relation.refresh_from_db()
            self.assertEqual(relation.review_status, "unreviewed")
            self.assertEqual(relation.method, "Changed unreviewed method")

    def test_reviewed_relation_source_evidence_cannot_change_until_approval_is_removed(self):
        second = SourceReference.objects.create(title="Synthetic second citation", citation="Synthetic evidence",
                                                url="https://example.org/second", verification_status="source_checked")
        for relation, source_model in ((self.membership(), BrainNetworkMembershipSource),
                                       (self.association(), BrainFunctionalAssociationSource)):
            link = source_model.objects.create(relationship=relation, source=self.source, note="Synthetic claim")
            source_model.objects.create(relationship=relation, source=second, note="Synthetic second claim")
            relation.review_status = "reviewed"
            relation.save()
            link.note = "Changed evidence claim"
            with self.assertRaises(ValidationError):
                link.save(update_fields=["note"])
            with self.assertRaises(ProtectedError):
                link.delete()
            with self.assertRaises(ProtectedError):
                relation.source_links.filter(pk=link.pk).delete()
            relation.review_status = "unreviewed"
            relation.save(update_fields=["review_status"])
            link.save(update_fields=["note"])
            link.refresh_from_db()
            self.assertEqual(link.note, "Changed evidence claim")

    def test_source_notes_identify_the_supported_claim(self):
        relation = self.membership()
        with self.assertRaises(ValidationError):
            BrainNetworkMembershipSource.objects.create(relationship=relation, source=self.source, note=" \n ")

    def test_required_evidence_context_is_validated(self):
        for field in ("method", "source_version", "task_context", "population_context", "limitations", "explanation_en"):
            with self.subTest(field=field):
                obj = self.association(evidence_key=f"context-{field.replace('_', '-')}")
                setattr(obj, field, " \n ")
                with self.assertRaises(ValidationError):
                    obj.save()

    def test_active_relations_reject_inactive_endpoints(self):
        for field in ("entity", "network", "concept"):
            endpoint = getattr(self, field)
            endpoint.is_active = False
            endpoint.save()
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.association(entity=None, network=self.network) if field == "network" else self.association()
            endpoint.is_active = True
            endpoint.save()

    def test_evidence_identity_is_immutable_and_bulk_writes_are_guarded(self):
        obj = self.membership()
        obj.evidence_key = "changed-key"
        with self.assertRaises(ValidationError):
            obj.save()
        with self.assertRaises(ValidationError):
            BrainNetworkMembership.objects.filter(pk=obj.pk).update(review_status="reviewed")

    def test_partial_save_validates_the_persisted_relation(self):
        obj = self.membership()
        inactive = BrainNetwork.objects.create(slug="inactive-test", name_en="Inactive Test", is_active=False)
        obj.network = inactive
        obj.qualifier = "Updated test qualifier"
        obj.save(update_fields=["qualifier"])
        obj.refresh_from_db()
        self.assertEqual(obj.network_id, self.network.pk)
        obj.network = inactive
        obj.is_active = False
        with self.assertRaises(ValidationError):
            obj.save(update_fields=["network"])

    def test_related_entities_cannot_be_deleted(self):
        self.membership()
        self.association()
        for obj in (self.entity, self.network, self.concept):
            with self.subTest(model=type(obj).__name__), self.assertRaises(ProtectedError):
                obj.delete()

    def test_checked_relation_keeps_its_last_resolved_source_when_weak_sources_exist(self):
        relation = self.membership()
        strong_link = BrainNetworkMembershipSource.objects.create(relationship=relation, source=self.source, note="Test claim")
        weak = SourceReference.objects.create(title="Weak test reference")
        BrainNetworkMembershipSource.objects.create(relationship=relation, source=weak, note="Unverified test claim")
        relation.review_status = "reviewed"
        relation.save()
        with self.assertRaises(ProtectedError):
            strong_link.delete()

    def test_alias_approval_requires_resolved_provenance(self):
        from .models import BrainAnatomicalAlias, BrainNetworkAlias

        for model, owner in ((BrainAnatomicalAlias, {"entity": self.entity}), (BrainNetworkAlias, {"network": self.network})):
            with self.subTest(model=model.__name__):
                alias = model.objects.create(text="Synthetic Alias", language="en", **owner)
                alias.review_status = "reviewed"
                with self.assertRaises(ValidationError):
                    alias.save()
                alias.source = self.source
                alias.source_note = "Exact synthetic spelling support"
                alias.save()
                self.assertEqual(alias.review_status, "reviewed")

    def test_reviewed_alias_edits_require_return_to_unreviewed(self):
        from .models import BrainAnatomicalAlias

        alias = BrainAnatomicalAlias.objects.create(entity=self.entity, text="Synthetic Alias", language="en",
            review_status="reviewed", source=self.source, source_note="Synthetic claim")
        alias.text = "Unreviewed edit"
        with self.assertRaises(ValidationError):
            alias.save()
        alias.review_status = "unreviewed"
        alias.save()

    def test_reviewed_alias_edits_require_new_review_and_partial_saves_keep_persisted_evidence(self):
        from .models import BrainAnatomicalAlias

        alias = BrainAnatomicalAlias.objects.create(entity=self.entity, text="Synthetic Alias", language="en",
                                                  review_status="reviewed", source=self.source, source_note="Synthetic claim")
        alias.text = "Unreviewed edit"
        with self.assertRaises(ValidationError):
            alias.save()
        alias.save(update_fields=["review_status"])
        alias.refresh_from_db()
        self.assertEqual(alias.text, "Synthetic Alias")
        alias.review_status = "unreviewed"
        alias.text = "Unreviewed edit"
        alias.save()

    def test_reviewed_canonical_content_requires_re_review_including_partial_saves(self):
        BrainNetworkSource.objects.create(network=self.network, source=self.source)
        for obj in (self.entity, self.network):
            obj.review_status = "reviewed"
            obj.save()
            fields = ("name_en", "name_fa", "description_en", "description_fa", "kind")
            for field in fields:
                obj.refresh_from_db()
                value = "Synthetic changed content" if field != "kind" else ("region" if obj == self.entity else "functional")
                setattr(obj, field, value)
                with self.subTest(model=type(obj).__name__, field=field), self.assertRaises(ValidationError):
                    obj.save()
            obj.refresh_from_db()
            obj.description_en = "Changed unreviewed description"
            obj.review_status = "unreviewed"
            with self.assertRaises(ValidationError):
                obj.save(update_fields=["description_en"])
            obj.save(update_fields=["review_status", "description_en"])
            obj.refresh_from_db()
            self.assertEqual(obj.review_status, "unreviewed")
            self.assertEqual(obj.description_en, "Changed unreviewed description")
        self.entity.review_status = "reviewed"
        self.entity.save()
        self.entity.laterality = "left"
        with self.assertRaises(ValidationError):
            self.entity.save()

    def test_reviewed_hierarchy_claim_requires_re_review_including_partial_saves(self):
        parent = BrainAnatomicalEntity.objects.create(slug="test-parent", name_en="Test Parent", kind="structure", laterality="bilateral")
        other = BrainAnatomicalEntity.objects.create(slug="test-other-parent", name_en="Test Other Parent", kind="structure", laterality="bilateral")
        link = BrainHierarchyLink.objects.create(child=self.entity, parent=parent, source_version="Test v1")
        BrainHierarchyLinkSource.objects.create(relationship=link, source=self.source, note="Synthetic hierarchy claim")
        link.review_status = "reviewed"
        link.save()
        for field, value in (("parent", other), ("source_version", "Test v2"), ("explanation_en", "Changed claim")):
            link.refresh_from_db()
            setattr(link, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                link.save()
        link.refresh_from_db()
        link.parent = other
        link.review_status = "unreviewed"
        with self.assertRaises(ValidationError):
            link.save(update_fields=["parent"])
        link.save(update_fields=["review_status", "parent"])
        link.refresh_from_db()
        self.assertEqual(link.parent_id, other.pk)
        self.assertEqual(link.review_status, "unreviewed")

    def test_reviewed_canonical_and_hierarchy_sources_require_re_review(self):
        BrainNetworkSource.objects.create(network=self.network, source=self.source, note="Synthetic network identity")
        parent = BrainAnatomicalEntity.objects.create(slug="test-parent", name_en="Test Parent", kind="structure", laterality="bilateral")
        hierarchy = BrainHierarchyLink.objects.create(child=self.entity, parent=parent, source_version="Test v1")
        BrainHierarchyLinkSource.objects.create(relationship=hierarchy, source=self.source, note="Synthetic hierarchy claim")
        other = SourceReference.objects.create(title="Synthetic second source", citation="Synthetic evidence",
            url="https://example.org/second", verification_status="source_checked")
        for owner, model in ((self.entity, BrainAnatomicalEntitySource), (self.network, BrainNetworkSource),
                             (hierarchy, BrainHierarchyLinkSource)):
            model.objects.create(**{model.owner_field: owner}, source=other, note="Synthetic second source")
            owner.review_status = "reviewed"
            owner.save()
            citation = owner.source_links.get(source=self.source)
            citation.note = "Changed claim evidence"
            with self.subTest(model=model.__name__):
                with self.assertRaises(ValidationError):
                    citation.save(update_fields=["note"])
                with self.assertRaises(ProtectedError):
                    owner.source_links.filter(pk=citation.pk).delete()
                citation.source = SourceReference.objects.create(title=f"Synthetic new {model.__name__}")
                with self.assertRaises(ValidationError):
                    citation.save()
                owner.review_status = "unreviewed"
                owner.save(update_fields=["review_status"])
                citation.source = self.source
                citation.save(update_fields=["note"])
                citation.refresh_from_db()
                self.assertEqual(citation.note, "Changed claim evidence")

    def test_source_reference_edits_require_all_linked_brain_approvals_to_be_removed(self):
        from .models import BrainAnatomicalAlias, BrainNetworkAlias, BrainExternalIdentifier

        alias = BrainAnatomicalAlias.objects.create(entity=self.entity, text="Synthetic reviewed alias", language="en",
            source=self.source, source_note="Synthetic spelling", review_status="reviewed")
        network_alias = BrainNetworkAlias.objects.create(network=self.network, text="Synthetic network alias", language="en",
            source=self.source, source_note="Synthetic spelling", review_status="reviewed")
        identifier = BrainExternalIdentifier.objects.create(entity=self.entity, namespace="Synthetic", identifier="S-1",
            source_version="Test v1", source=self.source, source_note="Synthetic mapping", review_status="reviewed")
        parent = BrainAnatomicalEntity.objects.create(slug="synthetic-parent", name_en="Synthetic Parent", kind="structure", laterality="bilateral")
        hierarchy = BrainHierarchyLink.objects.create(child=self.entity, parent=parent, source_version="Test v1")
        BrainHierarchyLinkSource.objects.create(relationship=hierarchy, source=self.source, note="Synthetic hierarchy")
        BrainNetworkSource.objects.create(network=self.network, source=self.source, note="Synthetic definition")
        membership, association = self.membership(), self.association()
        for relation, source_model in ((membership, BrainNetworkMembershipSource), (association, BrainFunctionalAssociationSource)):
            source_model.objects.create(relationship=relation, source=self.source, note="Synthetic evidence")
        owners = (self.entity, self.network, hierarchy, membership, association, alias, network_alias, identifier)
        for owner in owners:
            owner.review_status = "reviewed"
            owner.save()
        for field, value in (("title", "Replacement source"), ("citation", "Replacement citation"),
                             ("url", "https://example.org/replacement"), ("doi", "10.1234/replacement"),
                             ("pmid", "12345"), ("organization", "Replacement publisher"),
                             ("verification_status", "verified"), ("authors", ["Replacement author"])):
            self.source.refresh_from_db()
            setattr(self.source, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.source.save(update_fields=[field])
        with self.assertRaises(ValidationError):
            SourceReference.objects.filter(pk=self.source.pk).update(citation="Replacement citation")
        self.source.refresh_from_db()
        self.source.title = "Replacement source"
        with self.assertRaises(ValidationError), transaction.atomic():
            SourceReference.objects.bulk_update([self.source], ["title"])
        with self.assertRaises(ValidationError):
            SourceReference.objects.bulk_create([self.source], update_conflicts=True, unique_fields=["id"], update_fields=["title"])
        for owner in owners:
            with self.assertRaises(ValidationError):
                SourceReference.objects.filter(pk=self.source.pk).update(title="Replacement source")
            owner.review_status = "unreviewed"
            owner.save(update_fields=["review_status"])
        self.source.refresh_from_db()
        self.source.title = "Replacement source"
        self.source.save(update_fields=["title"])
        self.source.refresh_from_db()
        self.assertEqual(self.source.title, "Replacement source")

    def test_source_checked_aliases_and_identifiers_cannot_lose_resolved_sources(self):
        from django.db.models import F
        from .models import BrainAnatomicalAlias, BrainNetworkAlias, BrainExternalIdentifier

        owners = (BrainAnatomicalAlias.objects.create(entity=self.entity, text="Synthetic checked alias", language="en",
                    source=self.source, source_note="Synthetic spelling", review_status="source_checked"),
                  BrainNetworkAlias.objects.create(network=self.network, text="Synthetic checked network alias", language="en",
                    source=self.source, source_note="Synthetic spelling", review_status="source_checked"),
                  BrainExternalIdentifier.objects.create(entity=self.entity, namespace="Synthetic", identifier="S-checked",
                    source_version="Test v1", source=self.source, source_note="Synthetic mapping", review_status="source_checked"))
        for owner in owners:
            self.source.refresh_from_db()
            self.source.verification_status = "citation_from_model_knowledge"
            with self.assertRaises(ValidationError):
                self.source.save(update_fields=["verification_status"])
            owner.review_status = "unreviewed"
            owner.save(update_fields=["review_status"])
        self.source.save(update_fields=["verification_status"])
        self.source.refresh_from_db()
        self.assertEqual(self.source.verification_status, "citation_from_model_knowledge")
        self.source.title = F("organization")
        with self.assertRaises(ValidationError):
            self.source.save(update_fields=["title"])

    def test_source_checked_relations_keep_last_resolved_evidence_but_allow_other_weak_sources(self):
        other = SourceReference.objects.create(title="Synthetic other source", citation="Synthetic evidence",
            url="https://example.org/other-checked", verification_status="source_checked")
        for relation, model in ((self.membership(), BrainNetworkMembershipSource), (self.association(), BrainFunctionalAssociationSource)):
            model.objects.create(relationship=relation, source=self.source, note="Synthetic evidence")
            relation.review_status = "source_checked"
            relation.save()
            self.source.refresh_from_db()
            self.source.verification_status = "citation_from_model_knowledge"
            with self.assertRaises(ValidationError):
                self.source.save(update_fields=["verification_status"])
            model.objects.create(relationship=relation, source=other, note="Synthetic alternative evidence")
        self.source.save(update_fields=["verification_status"])
        self.source.refresh_from_db()
        self.assertEqual(self.source.verification_status, "citation_from_model_knowledge")

    def test_source_checked_anatomy_network_and_hierarchy_keep_last_resolved_evidence(self):
        parent = BrainAnatomicalEntity.objects.create(slug="checked-evidence-parent", name_en="Synthetic Checked Parent", kind="structure", laterality="bilateral")
        hierarchy = BrainHierarchyLink.objects.create(child=self.entity, parent=parent, source_version="Test v1")
        BrainHierarchyLinkSource.objects.create(relationship=hierarchy, source=self.source, note="Synthetic hierarchy evidence")
        BrainNetworkSource.objects.create(network=self.network, source=self.source)
        other = SourceReference.objects.create(title="Synthetic alternative source", citation="Synthetic evidence",
            url="https://example.org/alternative", verification_status="source_checked")
        for owner in (self.entity, self.network, hierarchy):
            owner.review_status = "source_checked"
            owner.save()
        for owner, model in ((self.entity, BrainAnatomicalEntitySource), (self.network, BrainNetworkSource),
                             (hierarchy, BrainHierarchyLinkSource)):
            self.source.refresh_from_db()
            self.source.verification_status = "citation_from_model_knowledge"
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                self.source.save(update_fields=["verification_status"])
            model.objects.create(**{model.owner_field: owner}, source=other, note="Synthetic alternative evidence")
        self.source.save(update_fields=["verification_status"])
        self.source.refresh_from_db()
        self.assertEqual(self.source.verification_status, "citation_from_model_knowledge")


    def test_checked_canonical_evidence_cannot_be_removed_or_replaced_by_weak_sources(self):
        parent = BrainAnatomicalEntity.objects.create(slug="retention-parent", name_en="Synthetic Parent", kind="structure", laterality="bilateral")
        hierarchy = BrainHierarchyLink.objects.create(child=self.entity, parent=parent, source_version="Test v1")
        BrainHierarchyLinkSource.objects.create(relationship=hierarchy, source=self.source, note="Synthetic hierarchy claim")
        BrainNetworkSource.objects.create(network=self.network, source=self.source)
        weak = SourceReference.objects.create(title="Synthetic weak evidence")
        replacement_weak = SourceReference.objects.create(title="Synthetic weak replacement")
        target_network = BrainNetwork.objects.create(slug="retention-target", name_en="Synthetic Target")
        root = BrainAnatomicalEntity.objects.create(slug="retention-root", name_en="Synthetic Root", kind="whole_brain", laterality="bilateral")
        target_hierarchy = BrainHierarchyLink.objects.create(child=parent, parent=root, source_version="Test v1")
        alternative = SourceReference.objects.create(title="Synthetic resolved alternative", citation="Synthetic evidence",
            url="https://example.org/retention", verification_status="source_checked")
        for owner, model in ((self.entity, BrainAnatomicalEntitySource), (self.network, BrainNetworkSource),
                             (hierarchy, BrainHierarchyLinkSource)):
            strong = owner.source_links.get(source=self.source)
            model.objects.create(**{model.owner_field: owner}, source=weak, note="Synthetic historical claim")
            owner.review_status = "source_checked"
            owner.save()
            with self.subTest(model=model.__name__):
                with self.assertRaises(ProtectedError):
                    strong.delete()
                with self.assertRaises(ProtectedError):
                    owner.source_links.filter(pk=strong.pk).delete()
                target = {"entity": parent, "network": target_network, "relationship": target_hierarchy}[model.owner_field]
                setattr(strong, model.owner_field, target)
                with self.assertRaises(ProtectedError):
                    strong.save()
                strong.refresh_from_db()
                strong.source = alternative
                strong.save()  # A resolved replacement is safe.
                strong.source = replacement_weak
                with self.assertRaises(ProtectedError):
                    strong.save()
                strong.refresh_from_db()
                model.objects.create(**{model.owner_field: owner}, source=self.source, note="Synthetic retained claim")
                strong.delete()
                self.assertTrue(owner.source_links.filter(source=self.source).exists())

    def test_canonical_checked_approval_requires_resolved_evidence(self):
        weak = SourceReference.objects.create(title="Synthetic unchecked evidence")
        parent = BrainAnatomicalEntity.objects.create(slug="weak-parent", name_en="Synthetic Parent", kind="structure", laterality="bilateral")
        hierarchy = BrainHierarchyLink.objects.create(child=self.entity, parent=parent, source_version="Test v1")
        anatomy = BrainAnatomicalEntity.objects.create(slug="weak-anatomy", name_en="Synthetic Anatomy", kind="structure", laterality="bilateral")
        for owner, model in ((anatomy, BrainAnatomicalEntitySource), (self.network, BrainNetworkSource), (hierarchy, BrainHierarchyLinkSource)):
            model.objects.create(**{model.owner_field: owner}, source=weak, note="Synthetic unchecked claim")
            for status in ("source_checked", "reviewed"):
                owner.review_status = status
                with self.subTest(model=model.__name__, status=status), self.assertRaises(ValidationError):
                    owner.save()


@skipUnless(connection.vendor == "postgresql", "Source curation locking requires PostgreSQL")
class BrainSourceConcurrencyTests(TransactionTestCase):
    def test_source_edit_waits_for_inflight_review_and_then_requires_re_review(self):
        source = SourceReference.objects.create(title="Synthetic concurrent source", citation="Synthetic evidence",
            url="https://example.org/concurrent", verification_status="source_checked")
        entity = BrainAnatomicalEntity.objects.create(slug="concurrent-source-test", name_en="Synthetic Concurrent Entity",
            kind="structure", laterality="bilateral")
        BrainAnatomicalEntitySource.objects.create(entity=entity, source=source)
        validating, release, editing, finished = Event(), Event(), Event(), Event()
        results = SimpleQueue()
        original_clean = BrainAnatomicalEntity.full_clean

        def paused_clean(row, *args, **kwargs):
            if row.pk == entity.pk and row.review_status == "reviewed":
                validating.set()
                if not release.wait(10):
                    raise RuntimeError("Synthetic review barrier timed out")
            return original_clean(row, *args, **kwargs)

        def approve():
            close_old_connections()
            try:
                row = BrainAnatomicalEntity.objects.get(pk=entity.pk)
                row.review_status = "reviewed"
                row.save()
                results.put("reviewed")
            except Exception as error:
                results.put(error)
            finally:
                close_old_connections()

        def edit():
            close_old_connections()
            try:
                row = SourceReference.objects.get(pk=source.pk)
                row.citation = "Unreviewed replacement evidence"
                editing.set()
                row.save()
                results.put("source edit unexpectedly accepted")
            except ValidationError:
                results.put("source edit rejected")
            except Exception as error:
                results.put(error)
            finally:
                finished.set()
                close_old_connections()

        with patch.object(BrainAnatomicalEntity, "full_clean", paused_clean):
            approval_thread = Thread(target=approve)
            source_thread = Thread(target=edit)
            approval_thread.start()
            try:
                self.assertTrue(validating.wait(5))
                source_thread.start()
                self.assertTrue(editing.wait(5))
                self.assertFalse(finished.wait(0.3))
            finally:
                release.set()
                approval_thread.join(10)
                if source_thread.ident is not None:
                    source_thread.join(10)
            self.assertFalse(approval_thread.is_alive())
            self.assertFalse(source_thread.is_alive())
        outcomes = [results.get(), results.get()]
        self.assertCountEqual(outcomes, ["reviewed", "source edit rejected"])
        source.refresh_from_db()
        self.assertEqual(source.citation, "Synthetic evidence")
