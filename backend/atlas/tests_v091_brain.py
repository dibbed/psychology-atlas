"""Brain foundation invariants; all names and sources here are synthetic fixtures."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from .models import (
    BrainAnatomicalAlias,
    BrainAnatomicalEntity,
    BrainAnatomicalEntitySource,
    BrainExternalIdentifier,
    BrainHierarchyLink,
    BrainHierarchyLinkSource,
    BrainNetwork,
    BrainNetworkAlias,
    BrainNetworkSource,
    ScientificReviewStatus,
    SourceReference,
)


class BrainFoundationTests(TestCase):
    def anatomy(self, slug, *, kind=BrainAnatomicalEntity.Kind.STRUCTURE,
                laterality=BrainAnatomicalEntity.Laterality.BILATERAL, **kwargs):
        return BrainAnatomicalEntity.objects.create(
            slug=slug, name_en=slug.replace("-", " ").title(),
            kind=kind, laterality=laterality, **kwargs,
        )

    def link(self, child, parent, **kwargs):
        return BrainHierarchyLink.objects.create(
            child=child, parent=parent, source_version="Fixture atlas v1", **kwargs,
        )

    def source(self):
        return SourceReference.objects.create(title="Synthetic test source")

    def test_canonical_defaults_kind_laterality_and_ownership(self):
        entity = self.anatomy("fixture-structure", seed_managed=True)
        self.assertEqual(entity.kind, BrainAnatomicalEntity.Kind.STRUCTURE)
        self.assertEqual(entity.laterality, BrainAnatomicalEntity.Laterality.BILATERAL)
        self.assertEqual(entity.review_status, ScientificReviewStatus.UNREVIEWED)
        self.assertTrue(entity.is_active)
        self.assertTrue(entity.seed_managed)
        self.assertTrue(entity.has_active_ancestry())

    def test_slug_is_stable_and_case_insensitively_unique(self):
        entity = self.anatomy("stable-slug")
        entity.name_en = "Renamed fixture"
        entity.save()
        self.assertEqual(entity.slug, "stable-slug")
        entity.slug = "changed-slug"
        with self.assertRaises(ValidationError):
            entity.save()
        with self.assertRaises(ValidationError):
            self.anatomy("STABLE-SLUG")
        with self.assertRaises(ValidationError):
            self.anatomy(" stable-slug ")
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrainAnatomicalEntity.objects.bulk_create([
                BrainAnatomicalEntity(
                    slug="Stable-Slug", name_en="Duplicate", kind="structure", laterality="bilateral"
                )
            ])

    def test_canonical_name_whitespace_is_normalized_without_merging_atlas_identities(self):
        with self.assertRaises(ValidationError):
            BrainAnatomicalEntity.objects.create(
                slug="bad-name", name_en="  Test  name ", kind="structure", laterality="bilateral"
            )
        first = BrainAnatomicalEntity.objects.create(
            slug="atlas-one-area", name_en="Area X", kind="region", laterality="left"
        )
        second = BrainAnatomicalEntity.objects.create(
            slug="atlas-two-area", name_en="Area X", kind="region", laterality="left"
        )
        self.assertNotEqual(first.pk, second.pk)

    def test_alias_type_language_and_normalized_uniqueness(self):
        first = self.anatomy("first")
        second = self.anatomy("second")
        alias = BrainAnatomicalAlias.objects.create(
            entity=first, text="  ABC  ", language="en", alias_type="abbreviation"
        )
        self.assertEqual(alias.text, "ABC")
        with self.assertRaises(ValidationError):
            BrainAnatomicalAlias.objects.create(entity=first, text="abc", language="en")
        BrainAnatomicalAlias.objects.create(entity=second, text="ABC", language="en", alias_type="abbreviation")
        BrainAnatomicalAlias.objects.create(entity=first, text="ABC", language="fa")
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrainAnatomicalAlias.objects.bulk_create([
                BrainAnatomicalAlias(entity=first, text=" Abc ", language="en")
            ])

    def test_external_identifier_scopes_namespace_and_version(self):
        source = self.source()
        first = self.anatomy("first")
        second = self.anatomy("second")
        BrainExternalIdentifier.objects.create(
            entity=first, namespace="Fixture", identifier="A1", source_version="v1", source=source
        )
        with self.assertRaises(ValidationError):
            BrainExternalIdentifier.objects.create(
                entity=second, namespace="fixture", identifier="A1", source_version="V1", source=source
            )
        BrainExternalIdentifier.objects.create(
            entity=second, namespace="fixture", identifier="A1", source_version="v2", source=source
        )
        network = BrainNetwork.objects.create(slug="network", name_en="Network")
        with self.assertRaises(ValidationError):
            BrainExternalIdentifier.objects.create(
                network=network, namespace="fixture", identifier="A1", source_version="v1", source=source
            )
        with self.assertRaises(ValidationError):
            BrainExternalIdentifier.objects.create(
                namespace="fixture", identifier="ownerless", source_version="v1", source=source
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrainExternalIdentifier.objects.bulk_create([
                BrainExternalIdentifier(
                    entity=first, network=network, namespace="fixture", identifier="both",
                    source_version="v1", source=source,
                )
            ])

    def test_network_has_separate_identity_alias_and_provenance(self):
        source = self.source()
        network = BrainNetwork.objects.create(slug="network-one", name_en="Network One", seed_managed=False)
        self.assertEqual(network.kind, BrainNetwork.Kind.FUNCTIONAL)
        self.assertEqual(network.review_status, ScientificReviewStatus.UNREVIEWED)
        self.assertFalse(hasattr(network, "parent"))
        BrainNetworkAlias.objects.create(network=network, text="N1", language="en", alias_type="abbreviation")
        BrainNetworkSource.objects.create(network=network, source=source, note="Identity only")
        BrainExternalIdentifier.objects.create(
            network=network, namespace="fixture", identifier="N1", source_version="v1", source=source
        )
        network.review_status = ScientificReviewStatus.SOURCE_CHECKED
        network.save()
        self.assertEqual(network.review_status, ScientificReviewStatus.SOURCE_CHECKED)
        with self.assertRaises(ValidationError):
            BrainNetwork.objects.create(slug="NETWORK-ONE", name_en="Duplicate")
        network.slug = "renamed-network"
        with self.assertRaises(ValidationError):
            network.save()
        network.slug = "network-one"
        with self.assertRaises(ValidationError):
            BrainNetworkAlias.objects.create(network=network, text="n1", language="en")
        with self.assertRaises(ProtectedError):
            network.delete()

    def test_roots_children_and_one_active_parent(self):
        root = self.anatomy("root", kind="whole_brain")
        other_root = self.anatomy("other-root", kind="whole_brain")
        child = self.anatomy("child")
        self.assertFalse(root.parent_links.exists())
        first = self.link(child, root)
        self.assertTrue(child.has_active_ancestry())
        with self.assertRaises(ValidationError):
            self.link(child, other_root)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrainHierarchyLink.objects.bulk_create([
                BrainHierarchyLink(child=child, parent=other_root, source_version="Fixture atlas v1")
            ])
        first.is_active = False
        first.save()
        replacement = self.link(child, other_root)
        self.assertTrue(replacement.is_active)
        self.assertEqual(child.parent_links.count(), 2)

    def test_self_parent_rejected_in_model_and_database(self):
        entity = self.anatomy("self")
        with self.assertRaises(ValidationError):
            self.link(entity, entity)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrainHierarchyLink.objects.bulk_create([
                BrainHierarchyLink(child=entity, parent=entity, source_version="Fixture atlas v1")
            ])

    def test_direct_cycle_rejected(self):
        first = self.anatomy("first")
        second = self.anatomy("second")
        self.link(second, first)
        with self.assertRaises(ValidationError):
            self.link(first, second)

    def test_multi_hop_cycle_and_reparenting_rejected(self):
        root = self.anatomy("root")
        middle = self.anatomy("middle")
        leaf = self.anatomy("leaf")
        extra = self.anatomy("extra")
        self.link(middle, root)
        self.link(leaf, middle)
        moving = self.link(extra, leaf)
        with self.assertRaises(ValidationError):
            self.link(root, leaf)
        moving.is_active = False
        moving.save()
        moving.child = root
        moving.is_active = True
        with self.assertRaises(ValidationError):
            moving.save()

    def test_opposite_side_and_inactive_parent_rejected(self):
        left = self.anatomy("left", laterality="left")
        right = self.anatomy("right", laterality="right")
        midline = self.anatomy("midline", laterality="midline")
        with self.assertRaises(ValidationError):
            self.link(right, left)
        with self.assertRaises(ValidationError):
            self.link(midline, left)
        left.is_active = False
        left.save()
        left_child = self.anatomy("left-child", laterality="left")
        with self.assertRaises(ValidationError):
            self.link(left_child, left)
        inactive_child = self.anatomy("inactive-child", is_active=False)
        with self.assertRaises(ValidationError):
            self.link(inactive_child, right)

    def test_laterality_edits_cannot_invalidate_active_hierarchy(self):
        parent = self.anatomy("left-parent", laterality="left")
        child = self.anatomy("left-child", laterality="left")
        self.link(child, parent)

        child.laterality = BrainAnatomicalEntity.Laterality.RIGHT
        with self.assertRaises(ValidationError):
            child.save()
        child.refresh_from_db()
        self.assertEqual(child.laterality, BrainAnatomicalEntity.Laterality.LEFT)

        parent.laterality = BrainAnatomicalEntity.Laterality.RIGHT
        with self.assertRaises(ValidationError):
            parent.save()
        parent.refresh_from_db()
        self.assertEqual(parent.laterality, BrainAnatomicalEntity.Laterality.LEFT)

    def test_deactivated_ancestor_hides_descendants_without_deleting_links(self):
        root = self.anatomy("root")
        middle = self.anatomy("middle")
        leaf = self.anatomy("leaf")
        self.link(middle, root)
        self.link(leaf, middle)
        stale_root = BrainAnatomicalEntity.objects.get(pk=root.pk)
        root.is_active = False
        root.save()
        self.assertFalse(stale_root.has_active_ancestry())
        self.assertFalse(middle.has_active_ancestry())
        self.assertFalse(leaf.has_active_ancestry())
        self.assertEqual(BrainHierarchyLink.objects.count(), 2)

    def test_entity_and_relation_sources_do_not_upgrade_review_automatically(self):
        source = self.source()
        root = self.anatomy("root")
        child = self.anatomy("child")
        link = self.link(child, root)
        BrainAnatomicalEntitySource.objects.create(entity=root, source=source, note="Identity")
        BrainHierarchyLinkSource.objects.create(relationship=link, source=source, note="Part of claim")
        root.refresh_from_db()
        link.refresh_from_db()
        self.assertEqual(root.review_status, ScientificReviewStatus.UNREVIEWED)
        self.assertEqual(link.review_status, ScientificReviewStatus.UNREVIEWED)
        root.review_status = ScientificReviewStatus.SOURCE_CHECKED
        root.save()
        link.review_status = ScientificReviewStatus.SOURCE_CHECKED
        link.save()
        self.assertNotEqual(root.review_status, ScientificReviewStatus.REVIEWED)
        self.assertNotEqual(link.review_status, ScientificReviewStatus.REVIEWED)
        with self.assertRaises(ProtectedError):
            source.delete()

    def test_reviewed_state_requires_correct_level_of_source(self):
        root = self.anatomy("root")
        child = self.anatomy("child")
        link = self.link(child, root)
        root.review_status = ScientificReviewStatus.REVIEWED
        with self.assertRaises(ValidationError):
            root.save()
        link.review_status = ScientificReviewStatus.REVIEWED
        with self.assertRaises(ValidationError):
            link.save()
        source = self.source()
        BrainAnatomicalEntitySource.objects.create(entity=root, source=source)
        with self.assertRaises(ValidationError):
            link.save()  # Entity-level evidence does not support the relation.
        with self.assertRaises(ValidationError):
            BrainHierarchyLinkSource.objects.create(relationship=link, source=source, note=" ")
        BrainHierarchyLinkSource.objects.create(
            relationship=link, source=source, note="Child is part of root in fixture hierarchy"
        )
        root.save()
        link.save()

    def test_checked_records_keep_their_last_source_link(self):
        source = self.source()
        other_source = SourceReference.objects.create(title="Other synthetic source")
        entity = self.anatomy("sourced-entity")
        first = BrainAnatomicalEntitySource.objects.create(entity=entity, source=source)
        entity.review_status = ScientificReviewStatus.SOURCE_CHECKED
        entity.save()
        with self.assertRaises(ProtectedError):
            first.delete()
        BrainAnatomicalEntitySource.objects.create(entity=entity, source=other_source)
        with self.assertRaises(ProtectedError):
            BrainAnatomicalEntitySource.objects.filter(entity=entity).delete()
        self.assertEqual(entity.source_links.count(), 2)
        first.delete()
        self.assertIsNone(first.pk)
        with self.assertRaises(ProtectedError):
            BrainAnatomicalEntitySource.objects.filter(entity=entity).delete()

        network = BrainNetwork.objects.create(slug="sourced-network", name_en="Sourced Network")
        BrainNetworkSource.objects.create(network=network, source=source)
        network.review_status = ScientificReviewStatus.REVIEWED
        network.save()
        with self.assertRaises(ProtectedError):
            BrainNetworkSource.objects.filter(network=network).delete()

        child = self.anatomy("sourced-child")
        link = self.link(child, entity)
        relation_source = BrainHierarchyLinkSource.objects.create(
            relationship=link, source=source, note="Synthetic part-of claim"
        )
        link.review_status = ScientificReviewStatus.SOURCE_CHECKED
        link.save()
        with self.assertRaises(ProtectedError):
            relation_source.delete()

        link.review_status = ScientificReviewStatus.UNREVIEWED
        link.save()
        relation_source.delete()
        self.assertFalse(link.source_links.exists())

    def test_delete_protection_for_children_history_sources_aliases_and_identifiers(self):
        source = self.source()
        root = self.anatomy("root")
        child = self.anatomy("child")
        link = self.link(child, root)
        link.is_active = False
        link.save()
        with self.assertRaises(ProtectedError):
            root.delete()
        with self.assertRaises(ProtectedError):
            child.delete()
        isolated = self.anatomy("isolated")
        BrainAnatomicalAlias.objects.create(entity=isolated, text="Alias", language="en")
        with self.assertRaises(ProtectedError):
            isolated.delete()
        sourced = self.anatomy("sourced")
        BrainAnatomicalEntitySource.objects.create(entity=sourced, source=source)
        with self.assertRaises(ProtectedError):
            sourced.delete()
        mapped = self.anatomy("mapped")
        BrainExternalIdentifier.objects.create(
            entity=mapped, namespace="fixture", identifier="M1", source_version="v1", source=source
        )
        with self.assertRaises(ProtectedError):
            mapped.delete()
        self.anatomy("unused").delete()
