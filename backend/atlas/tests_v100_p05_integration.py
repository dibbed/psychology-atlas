"""Isolated non-scientific fixtures for P05/P04 boundaries and additive upgrades."""
from django.contrib import admin
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.utils import timezone

from .cms_governance import resource_binding
from .cms_governance_models import GovernanceDecision
from .cms_review_models import ReviewDecision
from .models import BrainAnatomicalEntity, BrainAnatomicalEntitySource, SourceReference
from .tests_v100_p01 import BASE
from .tests_v100_p04 import ReviewFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SourceGovernanceIntegrationTests(ReviewFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.source.url = "https://non-scientific-fixture.invalid/claim"
        self.source.save()
        self.rights_source = SourceReference.objects.create(
            title="NON-SCIENTIFIC isolated rights fixture", citation="Not legal or scientific evidence",
            url="https://non-scientific-fixture.invalid/rights", verification_status="source_checked")

    def rights(self):
        binding = resource_binding("disorder", self.disorder.pk)
        evidence = [{"source_id": self.rights_source.pk, "locator": "Synthetic isolated scope; no real permission"}]
        response = self.post(self.client, "governance/rights/", {
            "resource_type": "disorder", "resource_id": self.disorder.pk,
            "resource_version": binding["resource_version"], "material": "metadata", "intended_use": "public_display",
            "status": "allowed", "rightsholder": "NON-SCIENTIFIC fixture owner",
            "holder_identification": "Synthetic only, no real rights claim", "holder_evidence": evidence,
            "public_access": "unknown", "evidence": evidence,
            "reviewed_on": timezone.localdate().isoformat(), "effective_on": timezone.localdate().isoformat(),
            "expires_on": None, "review_on": None, "limitations": "Isolated tests only; no permission outside fixture",
            "territory": "", "conflict_note": "", "reason": "CORRECTION_REQUIRED"})
        self.assertEqual(response.status_code, 201, response.content)
        record = response.json()["record"]
        for action, payload in (("assign", {"reviewer_id": self.owner.pk}),
                                ("decide", {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED", "self_review_ack": True})):
            response = self.post(self.client, f"governance/rights/{record['id']}/{action}/", payload,
                                 etag=f'"{record["version"]}"')
            self.assertEqual(response.status_code, 200, response.content)
            record = response.json()["record"]
        return record

    def test_rights_revocation_invalidates_science_with_a_different_evidence_source(self):
        rights = self.rights()
        self.approved()
        before = ReviewDecision.objects.count()
        self.assertTrue(self.detail()["approval"]["eligible"])
        response = self.post(self.client, f"governance/rights/{rights['id']}/revoke/",
            {"reason": "CORRECTION_REQUIRED"}, etag=f'"{rights["version"]}"')
        self.assertEqual(response.status_code, 200, response.content)
        after = self.detail()
        self.assertFalse(after["approval"]["eligible"])
        self.assertIn("DEPENDENCY_CHANGED", after["approval"]["blockers"])
        self.assertEqual(ReviewDecision.objects.count(), before)
        self.assertTrue(GovernanceDecision.objects.exists())
        self.disorder.refresh_from_db()
        self.assertEqual(self.disorder.overview, "Synthetic original")

    def test_previewed_source_edit_stales_prior_science_without_rewriting_history(self):
        self.approved()
        before = list(ReviewDecision.objects.values_list("pk", "revision_hash", "dependency_digest"))
        response = self.post(self.client, "sources/preview/", {
            "operation": "update", "source_id": self.source.pk,
            "changes": {"citation": "NON-SCIENTIFIC fixture corrected citation"}})
        self.assertEqual(response.status_code, 201, response.content)
        plan = response.json()
        self.assertTrue(plan["preview"]["can_apply"], plan)
        response = self.post(self.client, f"sources/plans/{plan['id']}/apply/", {}, etag=f'"{plan["version"]}"')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("DEPENDENCY_CHANGED", self.detail()["approval"]["blockers"])
        self.assertEqual(list(ReviewDecision.objects.values_list("pk", "revision_hash", "dependency_digest")), before)

    def test_source_admin_has_no_direct_write_route(self):
        request = RequestFactory().get("/admin/atlas/sourcereference/")
        request.user = self.owner
        registered = admin.site._registry[SourceReference]
        self.assertTrue(registered.has_view_permission(request, self.source))
        self.assertFalse(registered.has_add_permission(request))
        self.assertFalse(registered.has_change_permission(request, self.source))
        self.assertFalse(registered.has_delete_permission(request, self.source))

    def test_typed_version_extension_cannot_bypass_reviewed_brain_protection(self):
        entity = BrainAnatomicalEntity.objects.create(slug="non-scientific-protected-p05",
            name_en="NON-SCIENTIFIC isolated structure", kind="structure", laterality="bilateral")
        BrainAnatomicalEntitySource.objects.create(entity=entity, source=self.source)
        entity.review_status = "reviewed"
        entity.save()
        response = self.post(self.client, "sources/preview/", {"operation": "update", "source_id": self.source.pk,
            "changes": {"resource_version": "NON-SCIENTIFIC fixture version 2"}})
        self.assertEqual(response.status_code, 201, response.content)
        plan = response.json()
        self.assertFalse(plan["preview"]["can_apply"], plan)
        self.assertTrue(plan["preview"]["blockers"])
        denied = self.post(self.client, f"sources/plans/{plan['id']}/apply/", {}, etag=f'"{plan["version"]}"')
        self.assertEqual(denied.status_code, 409, denied.content)
        entity.refresh_from_db()
        self.assertEqual(entity.review_status, "reviewed")

    def test_source_reader_cannot_leak_private_domain_reviews_through_impact(self):
        rights = self.rights()
        reader = self.user("source-only", staff=True, caps=("cms_enter", "cms_source_view"))
        client = self.signed(reader)
        for path in (f"governance/rights/{rights['id']}/", f"governance/rights/{rights['id']}/history/"):
            denied = client.get(BASE + path)
            self.assertEqual(denied.status_code, 404, denied.content)
            self.assertNotIn("Synthetic isolated scope", denied.content.decode())
        source = client.get(BASE + f"sources/{self.rights_source.pk}/")
        self.assertIn(source.status_code, (200, 403, 404), source.content)
        self.assertNotIn("Synthetic isolated scope", source.content.decode())
        self.assertNotIn(rights["id"], source.content.decode())


class P05MigrationTests(TransactionTestCase):
    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_additive_forward_reverse_preserves_legacy_content_and_review_history(self):
        old = ("atlas", "0040_v100_p04_review_workflow")
        new = ("atlas", "0041_v100_p05_source_governance")
        executor = MigrationExecutor(connection)
        executor.migrate([old])
        apps = executor.loader.project_state([old]).apps
        category = apps.get_model("atlas", "Category").objects.create(
            slug="non-scientific-p05-migration", name_en="NON-SCIENTIFIC preserved category")
        source = apps.get_model("atlas", "SourceReference").objects.create(
            title="NON-SCIENTIFIC preserved source", metadata={"preserve": ["raw", "bytes-like-history"]})
        expected = {model: list(apps.get_model("atlas", model).objects.order_by("pk").values())
                    for model in ("Category", "SourceReference", "ContentRevision", "ReviewDecision", "AdminAuditEvent")}
        executor = MigrationExecutor(connection)
        executor.migrate([new])
        upgraded = executor.loader.project_state([new]).apps
        for model, rows in expected.items():
            self.assertEqual(list(upgraded.get_model("atlas", model).objects.order_by("pk").values()), rows)
        for model in ("SourcePlan", "GovernanceRecord", "GovernanceDecision"):
            self.assertFalse(upgraded.get_model("atlas", model).objects.exists())
        executor = MigrationExecutor(connection)
        executor.migrate([old])
        reversed_apps = executor.loader.project_state([old]).apps
        self.assertEqual(reversed_apps.get_model("atlas", "Category").objects.get(pk=category.pk).name_en,
                         "NON-SCIENTIFIC preserved category")
        self.assertEqual(reversed_apps.get_model("atlas", "SourceReference").objects.get(pk=source.pk).metadata,
                         {"preserve": ["raw", "bytes-like-history"]})
        self.assertNotIn("atlas_governancerecord", connection.introspection.table_names())
