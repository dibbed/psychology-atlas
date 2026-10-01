"""Brain foundation invariants; all names and sources here are synthetic fixtures."""

from queue import SimpleQueue
from threading import Event, Thread, current_thread
from unittest import skipUnless
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.db.models.query import QuerySet
from django.test import TestCase, TransactionTestCase

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
    # Only DB-constraint tests use the deliberately unvalidated base manager.
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

    def test_bulk_canonical_writes_cannot_bypass_provenance(self):
        entity = self.anatomy("unsourced-entity")
        network = BrainNetwork.objects.create(slug="unsourced-network", name_en="Unsourced Network")
        for owner in (entity, network):
            model = type(owner)
            with self.subTest(model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.objects.filter(pk=owner.pk).update(review_status=ScientificReviewStatus.REVIEWED)
                owner.review_status = ScientificReviewStatus.SOURCE_CHECKED
                with self.assertRaises(ValidationError), transaction.atomic():
                    model.objects.bulk_update([owner], ["review_status"])
                owner.refresh_from_db()
                self.assertEqual(owner.review_status, ScientificReviewStatus.UNREVIEWED)
                with self.assertRaises(ValidationError):
                    model.objects.bulk_create([model(
                        slug="bulk-unsourced", name_en="Bulk Unsourced", review_status=ScientificReviewStatus.REVIEWED,
                    )])
                self.assertFalse(model.objects.filter(slug="bulk-unsourced").exists())

    def test_bulk_hierarchy_writes_cannot_bypass_graph_validation(self):
        root = self.anatomy("root")
        middle = self.anatomy("middle")
        leaf = self.anatomy("leaf")
        link = self.link(middle, root)
        self.link(leaf, middle)
        with self.assertRaises(ValidationError):
            BrainHierarchyLink.objects.filter(pk=link.pk).update(parent=leaf)
        link.parent = leaf
        with self.assertRaises(ValidationError), transaction.atomic():
            BrainHierarchyLink.objects.bulk_update([link], ["parent"])
        link.refresh_from_db()
        self.assertEqual(link.parent_id, root.pk)
        with self.assertRaises(ValidationError):
            BrainHierarchyLink.objects.bulk_create([
                BrainHierarchyLink(child=root, parent=leaf, source_version="Fixture v1")
            ])
        self.assertFalse(root.parent_links.exists())

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
            BrainAnatomicalEntity._base_manager.bulk_create([
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
            BrainAnatomicalAlias._base_manager.bulk_create([
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
            BrainExternalIdentifier._base_manager.bulk_create([
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
            BrainHierarchyLink._base_manager.bulk_create([
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
            BrainHierarchyLink._base_manager.bulk_create([
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

    def test_partial_hierarchy_saves_cannot_skip_active_graph_validation(self):
        parent = self.anatomy("left-parent", laterality="left")
        child = self.anatomy("left-child", laterality="left")
        link = self.link(child, parent)
        opposite = self.anatomy("opposite-parent", laterality="right")
        descendant = self.anatomy("descendant", laterality="left")
        self.link(descendant, child)
        inactive = self.anatomy("inactive-parent", is_active=False)
        ancestor = self.anatomy("inactive-ancestor")
        hidden_branch = self.anatomy("hidden-branch", laterality="left")
        self.link(hidden_branch, ancestor)
        ancestor.is_active = False
        ancestor.save()
        for invalid_parent in (opposite, descendant, inactive, hidden_branch):
            with self.subTest(parent=invalid_parent.slug):
                link.is_active = False  # This field will not be persisted.
                link.parent = invalid_parent
                with self.assertRaises(ValidationError):
                    link.save(update_fields=["parent"])
                link.refresh_from_db()
                self.assertTrue(link.is_active)
                self.assertEqual(link.parent_id, parent.pk)

        link.is_active = False
        link.parent = opposite
        with self.assertRaises(ValidationError):
            link.save(False, False, None, ["parent"])
        link.refresh_from_db()
        self.assertTrue(link.is_active)
        self.assertEqual(link.parent_id, parent.pk)

    def test_partial_hierarchy_saves_validate_stored_endpoints_and_ignore_unwritten_edits(self):
        left = self.anatomy("left", laterality="left")
        right = self.anatomy("right", laterality="right")
        child = self.anatomy("left-child", laterality="left")
        link = self.link(child, left)
        link.parent = right  # A metadata-only update must keep the stored valid parent.
        link.source_version = "Fixture atlas v2"
        link.save(update_fields=["source_version"])
        link.refresh_from_db()
        self.assertEqual(link.parent_id, left.pk)
        self.assertEqual(link.source_version, "Fixture atlas v2")

        link.is_active = False
        link.parent = right
        link.save()  # Historical inactive links may retain incompatible endpoints.
        link.parent = left  # Not included in the activation write.
        link.is_active = True
        with self.assertRaises(ValidationError):
            link.save(update_fields=["is_active"])
        link.refresh_from_db()
        self.assertFalse(link.is_active)
        self.assertEqual(link.parent_id, right.pk)

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

    def test_source_reassignment_preserves_required_provenance(self):
        source = self.source()
        other_source = SourceReference.objects.create(title="Other synthetic source")
        root = self.anatomy("root")
        targets = (
            (BrainAnatomicalEntitySource, "entity", self.anatomy("target")),
            (BrainNetworkSource, "network", BrainNetwork.objects.create(slug="target-network", name_en="Target")),
            (BrainHierarchyLinkSource, "relationship", self.link(self.anatomy("target-child"), root)),
        )
        for status in (ScientificReviewStatus.SOURCE_CHECKED, ScientificReviewStatus.REVIEWED):
            for model, field, target in targets:
                with self.subTest(model=model.__name__, status=status):
                    suffix = f"{field}-{status}"
                    if field == "entity":
                        owner = self.anatomy(suffix)
                    elif field == "network":
                        owner = BrainNetwork.objects.create(slug=suffix, name_en=suffix)
                    else:
                        owner = self.link(self.anatomy(suffix), root)
                    citation = model.objects.create(**{field: owner, "source": source, "note": "Fixture claim"})
                    owner.review_status = status
                    owner.save()
                    setattr(citation, field, target)
                    with self.assertRaises(ProtectedError):
                        citation.save()
                    citation.refresh_from_db()
                    self.assertEqual(getattr(citation, f"{field}_id"), owner.pk)
                    if status == ScientificReviewStatus.REVIEWED:
                        owner.review_status = ScientificReviewStatus.UNREVIEWED
                        owner.save(update_fields=["review_status"])
                    model.objects.create(**{field: owner, "source": other_source, "note": "Other fixture claim"})
                    if status == ScientificReviewStatus.REVIEWED:
                        owner.review_status = status
                        owner.save(update_fields=["review_status"])
                        citation.note = "Changed reviewed evidence"
                        with self.assertRaises(ValidationError):
                            citation.save(update_fields=["note"])
                        owner.review_status = ScientificReviewStatus.UNREVIEWED
                        owner.save(update_fields=["review_status"])
                    setattr(citation, field, target)
                    citation.save()
                    self.assertEqual(owner.source_links.count(), 1)
                    citation.delete()  # Target remains unreviewed; free its unique source pair.

    def test_source_bulk_reassignment_cannot_bypass_provenance_validation(self):
        source = self.source()
        root = self.anatomy("root")
        other = self.anatomy("other")
        network = BrainNetwork.objects.create(slug="network", name_en="Network")
        other_network = BrainNetwork.objects.create(slug="other-network", name_en="Other network")
        relation = self.link(self.anatomy("child"), root)
        other_relation = self.link(self.anatomy("other-child"), root)
        for model, field, owner, target in (
            (BrainAnatomicalEntitySource, "entity", root, other),
            (BrainNetworkSource, "network", network, other_network),
            (BrainHierarchyLinkSource, "relationship", relation, other_relation),
        ):
            with self.subTest(model=model.__name__):
                citation = model.objects.create(**{field: owner, "source": source, "note": "Fixture claim"})
                owner.review_status = ScientificReviewStatus.SOURCE_CHECKED
                owner.save()
                with self.assertRaises(ValidationError):
                    model.objects.filter(pk=citation.pk).update(**{f"{field}_id": target.pk})
                setattr(citation, field, target)
                with self.assertRaises(ValidationError), transaction.atomic():
                    model.objects.bulk_update([citation], [field])
                citation.note = "Updated fixture claim"
                citation.save(update_fields=["note"])  # The pending owner change is not written.
                citation.refresh_from_db()
                self.assertEqual(getattr(citation, f"{field}_id"), owner.pk)
                self.assertEqual(citation.note, "Updated fixture claim")

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


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class BrainIntegrityConcurrencyTests(TransactionTestCase):
    def test_source_deletion_locks_citation_before_checking_its_owner(self):
        old_owner = BrainAnatomicalEntity.objects.create(
            slug="old-owner", name_en="Old Owner", kind="structure", laterality="bilateral",
        )
        target = BrainAnatomicalEntity.objects.create(
            slug="target", name_en="Target", kind="structure", laterality="bilateral",
        )
        source = SourceReference.objects.create(title="Synthetic concurrency source")
        citation = BrainAnatomicalEntitySource.objects.create(entity=old_owner, source=source)
        owner_read, release_delete, move_attempted, move_finished = (Event() for _ in range(4))
        outcomes = SimpleQueue()
        original_lock = QuerySet.select_for_update

        def controlled_lock(queryset, *args, **kwargs):
            if queryset.model is BrainAnatomicalEntity and current_thread().name == "source-deletion":
                owner_read.set()
                if not release_delete.wait(10):
                    raise RuntimeError("Timed out releasing the source deletion")
            return original_lock(queryset, *args, **kwargs)

        def delete():
            close_old_connections()
            try:
                BrainAnatomicalEntitySource.objects.filter(pk=citation.pk).delete()
                outcomes.put(("delete", "deleted"))
            except Exception as error:
                outcomes.put(("delete", repr(error)))
            finally:
                connection.close()

        def move():
            close_old_connections()
            try:
                moving = BrainAnatomicalEntitySource.objects.get(pk=citation.pk)
                moving.entity_id = target.pk
                move_attempted.set()
                moving.save(force_update=True)
                owner = BrainAnatomicalEntity.objects.get(pk=target.pk)
                owner.review_status = ScientificReviewStatus.SOURCE_CHECKED
                owner.save()
                outcomes.put(("move", "saved"))
            except DatabaseError:
                outcomes.put(("move", "lost-row"))
            except Exception as error:
                outcomes.put(("move", repr(error)))
            finally:
                move_finished.set()
                connection.close()

        threads = [Thread(target=delete, name="source-deletion", daemon=True),
                   Thread(target=move, name="source-reassignment", daemon=True)]
        with patch.object(QuerySet, "select_for_update", controlled_lock):
            try:
                threads[0].start()
                self.assertTrue(owner_read.wait(10))
                threads[1].start()
                self.assertTrue(move_attempted.wait(10))
                self.assertFalse(move_finished.wait(1), "Citation moved after deletion had read its old owner")
            finally:
                release_delete.set()
                for thread in threads:
                    if thread.ident is not None:
                        thread.join(10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(dict(outcomes.get_nowait() for _ in range(2)), {"delete": "deleted", "move": "lost-row"})
        target.refresh_from_db()
        self.assertEqual(target.review_status, ScientificReviewStatus.UNREVIEWED)

    def test_incident_laterality_edits_serialize_before_validation(self):
        parent = BrainAnatomicalEntity.objects.create(
            slug="parent", name_en="Parent", kind="structure", laterality="bilateral",
        )
        child = BrainAnatomicalEntity.objects.create(
            slug="child", name_en="Child", kind="structure", laterality="left",
        )
        BrainHierarchyLink.objects.create(child=child, parent=parent, source_version="Fixture v1")
        child_validated, parent_attempted, parent_validated, release_child = (Event() for _ in range(4))
        results = SimpleQueue()
        original_clean = BrainAnatomicalEntity.clean

        def controlled_clean(entity):
            original_clean(entity)
            if entity.pk == child.pk:
                child_validated.set()
                if not release_child.wait(10):
                    raise RuntimeError("Timed out waiting to release the child write")
            elif entity.pk == parent.pk:
                parent_validated.set()

        def edit(pk, laterality):
            close_old_connections()
            try:
                entity = BrainAnatomicalEntity.objects.get(pk=pk)
                entity.laterality = laterality
                if pk == parent.pk:
                    parent_attempted.set()
                entity.save()
                results.put((pk, "saved"))
            except ValidationError:
                results.put((pk, "rejected"))
            except Exception as error:
                results.put((pk, repr(error)))
            finally:
                connection.close()

        threads = [Thread(target=edit, args=(child.pk, "right"), daemon=True),
                   Thread(target=edit, args=(parent.pk, "left"), daemon=True)]
        with patch.object(BrainAnatomicalEntity, "clean", controlled_clean):
            try:
                threads[0].start()
                self.assertTrue(child_validated.wait(10))
                threads[1].start()
                self.assertTrue(parent_attempted.wait(10))
                self.assertFalse(parent_validated.wait(1), "Parent validated before the child committed")
            finally:
                release_child.set()
                for thread in threads:
                    if thread.ident is not None:
                        thread.join(10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        outcomes = dict(results.get_nowait() for _ in range(2))
        self.assertEqual(outcomes, {child.pk: "saved", parent.pk: "rejected"})
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual((parent.laterality, child.laterality), ("bilateral", "right"))
