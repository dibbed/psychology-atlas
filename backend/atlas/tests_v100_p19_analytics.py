"""P19 owner-only internal pipeline counts: recorded states are never scientific approvals."""
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings

from .cms_content_models import ContentRevision, ContentState
from .cms_governance_models import GovernanceRecord
from .cms_review_models import ReviewTask
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OwnerPipelineAnalyticsTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client_owner = self.sign_in(self.owner)

    def test_reconciled_counts_never_claim_approval_or_publication(self):
        state = ContentState.objects.create(
            kind="category", canonical_digest="0" * 64,
            publication="never_published",
        )
        revision = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest="0" * 64,
            payload={"name_en": "P19 secret draft should never be returned"},
            payload_digest="1" * 64, dependency_digest="2" * 64, actor=self.owner,
            status="approved",
        )
        state.current_revision = revision
        state.save(update_fields=["current_revision"])
        ContentState.objects.create(kind="therapy", canonical_digest="3" * 64)
        ContentRevision.objects.create(
            state=state, sequence=2, base_version=0, base_digest="0" * 64,
            payload={"name_en": "P19 hidden superseded draft"},
            payload_digest="4" * 64, dependency_digest="5" * 64, actor=self.owner,
            status="superseded",
        )
        ReviewTask.objects.create(
            subject=revision, review_type="scientific", revision_hash="1" * 64,
            dependency_digest="2" * 64, policy_version=0, policy_mode="solo_owner",
            status="approved",
        )
        GovernanceRecord.objects.create(
            kind="rights", domain="core", resource_type="category", resource_id=84,
            resource_version="test", status="approved",
        )
        response = self.client_owner.get(BASE + "analytics/overview/")
        self.assertEqual(response.status_code, 200, response.content[:350])
        metrics = response.json()
        self.assertEqual(metrics["scope"], "owner_recorded_pipeline_counts_only")
        content = metrics["content"]
        self.assertEqual(content["states_total"], 2)
        self.assertEqual(content["states_with_current_revision"], 1)
        self.assertEqual(content["states_without_current_revision"], 1)
        self.assertEqual(content["revisions_total"], 2)
        self.assertEqual(content["current_revision_statuses"]["approved"], 1)
        self.assertEqual(content["recorded_publication_markers"]["never_published"], 2)
        self.assertEqual(content["by_domain"]["core"]["states"], 1)
        self.assertEqual(content["by_domain"]["therapy"]["states"], 1)
        self.assertEqual(content["pointer_state_mismatches"], 0)
        self.assertEqual(metrics["reviews"]["tasks_by_status"]["approved"], 1)
        self.assertEqual(metrics["reviews"]["decisions_total"], 0)
        self.assertEqual(metrics["governance"]["rights"]["by_status"]["approved"], 1)
        self.assertEqual(metrics["governance"]["rights"]["decisions_total"], 0)
        self.assertFalse(metrics["publication_authorized"])
        self.assertFalse(metrics["scientific_rights_attested"])
        self.assertFalse(metrics["complete_release_readiness_proven"])
        for private in ("P19 secret", "hidden superseded", "actor_id", "payload", "assignee", "resource_id"):
            self.assertNotIn(private, response.content.decode())

    def test_permissions_revocation_queries_and_methods_are_fail_closed(self):
        user = self.user("p19-analytics-denied", staff=True, caps=(
            "cms_enter", "cms_dashboard", "cms_core_view"))
        viewer = self.sign_in(user)
        self.assertEqual(viewer.get(BASE + "analytics/overview/").status_code, 403)
        self.assertEqual(self.client_owner.get(BASE + "analytics/overview/?raw=1").status_code, 400)
        self.assertEqual(self.post(self.client_owner, "analytics/overview/", {"export": True}).status_code, 405)
        self.assertEqual(self.client_owner.get(BASE + "analytics/overview/").status_code, 200)
        # Owner revocation in the same session must take effect on the next request.
        Permission.objects.get(
            codename="cms_owner", content_type__model="rolepolicy"
        ).user_set.remove(self.owner)
        self.assertEqual(self.client_owner.get(BASE + "analytics/overview/").status_code, 403)
