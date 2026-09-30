"""Approved relation semantics exercised with synthetic test evidence only."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from .models import (
    BrainAnatomicalEntity, BrainAnatomicalEntitySource, BrainFunctionalAssociation,
    BrainFunctionalAssociationSource, BrainNetwork, BrainNetworkMembership,
    BrainNetworkMembershipSource, Concept, ScientificReviewStatus, SourceReference,
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
