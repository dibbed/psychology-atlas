from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models.query import QuerySet
from django.test import TestCase

from .models import BrainAnatomicalAlias, BrainAnatomicalEntity, BrainAnatomicalEntitySource, BrainHierarchyLink, SourceReference


class BrainAuditTests(TestCase):
    def anatomy(self, slug, **kwargs):
        return BrainAnatomicalEntity.objects.create(slug=slug, name_en=slug, kind="structure", laterality="bilateral", **kwargs)

    def test_empty_atlas_is_valid_and_explicitly_data_blocked(self):
        output = StringIO()
        call_command("audit_brain_atlas", stdout=output)
        self.assertIn("DATA BLOCKED", output.getvalue())
        self.assertIn("anatomy=0", output.getvalue())

    def test_unsourced_review_and_invalid_alias_are_detected(self):
        entity = self.anatomy("test-unsourced")
        QuerySet.update(BrainAnatomicalEntity.objects.filter(pk=entity.pk), review_status="reviewed")
        alias = BrainAnatomicalAlias.objects.create(entity=entity, text="Test", language="en")
        QuerySet.update(BrainAnatomicalAlias.objects.filter(pk=alias.pk), language="unsupported")
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("audit_brain_atlas", stdout=output)
        self.assertIn("missing_resolved_provenance", output.getvalue())
        self.assertIn("invalid_alias", output.getvalue())

    def test_cycle_laterality_and_inactive_hierarchy_are_detected(self):
        first, second = self.anatomy("test-first"), self.anatomy("test-second")
        BrainHierarchyLink.objects.create(child=second, parent=first, source_version="Test only")
        link = BrainHierarchyLink.objects.create(child=first, parent=second, source_version="Test only", is_active=False)
        QuerySet.update(BrainHierarchyLink.objects.filter(pk=link.pk), is_active=True)
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("audit_brain_atlas", stdout=output)
        self.assertIn("hierarchy_cycle", output.getvalue())
        QuerySet.update(BrainHierarchyLink.objects.filter(pk=link.pk), is_active=False)
        QuerySet.update(BrainAnatomicalEntity.objects.filter(pk=first.pk), is_active=False)
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("audit_brain_atlas", stdout=output)
        self.assertIn("inactive_hierarchy", output.getvalue())

    def test_weak_source_is_not_checked_provenance(self):
        entity = self.anatomy("test-weak")
        source = SourceReference.objects.create(title="Test weak reference")
        BrainAnatomicalEntitySource.objects.create(entity=entity, source=source)
        entity.review_status = "source_checked"
        entity.save()
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("audit_brain_atlas", stdout=output)
        self.assertIn("missing_resolved_provenance", output.getvalue())

    def test_audit_output_is_deterministic_and_read_only(self):
        snapshots = []
        for _ in range(2):
            output = StringIO()
            call_command("audit_brain_atlas", stdout=output)
            snapshots.append(output.getvalue())
        self.assertEqual(*snapshots)
        self.assertEqual(BrainAnatomicalEntity.objects.count(), 0)

    def test_downgraded_evidence_produces_a_deterministic_audit_error(self):
        from .tests_v092_brain_api import BrainFixtureMixin

        entity = self.anatomy("test-downgraded")
        source = SourceReference.objects.create(title="Synthetic evidence", citation="Synthetic citation",
                                               url="https://example.org/test", verification_status="verified")
        fixture = type("SyntheticFixture", (BrainFixtureMixin,), {"source": source})
        fixture.add_relations(entity)
        source.verification_status = "citation_from_model_knowledge"
        source.save()
        outputs = []
        for _ in range(2):
            output = StringIO()
            with self.assertRaises(CommandError):
                call_command("audit_brain_atlas", stdout=output)
            outputs.append(output.getvalue())
        self.assertEqual(*outputs)
        self.assertIn("invalid_source_link", outputs[0])
