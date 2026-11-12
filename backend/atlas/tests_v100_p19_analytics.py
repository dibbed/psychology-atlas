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

    def test_owner_csv_export_uses_real_denominators_without_private_text(self):
        import csv
        import io
        from .cms_job_models import AdminJob

        state = ContentState.objects.create(
            kind="category", canonical_digest="a" * 64,
        )
        revision = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest="a" * 64,
            payload={"name_en": "SECRET_P19_CSV_PRIVATE"},
            payload_digest="b" * 64, dependency_digest="c" * 64,
            actor=self.owner, status="draft",
        )
        state.current_revision = revision
        state.save(update_fields=["current_revision"])
        json_response = self.client_owner.get(BASE + "analytics/overview/")
        self.assertEqual(json_response.status_code, 200)
        response = self.client_owner.get(BASE + "analytics/overview/export.csv/")
        self.assertEqual(response.status_code, 200, response.content[:250])
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")
        content = response.content.decode("utf-8-sig")
        self.assertNotIn("SECRET_P19_CSV_PRIVATE", content)
        for private in ("actor_id", "payload", "email", "storage_key", "assignee",
                        "resource_id", "citation", "rightsholder"):
            self.assertNotIn(private, content.lower())
        rows = list(csv.DictReader(io.StringIO(content)))
        self.assertTrue(rows)
        self.assertEqual(set(rows[0]), {"section", "metric", "category", "value", "denominator"})
        def value(section, metric, category=""):
            matching = [row for row in rows
                        if row["section"] == section and row["metric"] == metric
                        and row["category"] == category]
            self.assertEqual(len(matching), 1, matching)
            return matching[0]["value"]
        snapshot = json_response.json()
        self.assertEqual(int(value("content", "states_total")), snapshot["content"]["states_total"])
        self.assertEqual(int(value("content", "states_with_current_revision")),
                         snapshot["content"]["states_with_current_revision"])
        self.assertEqual(int(value("content_by_domain", "states", "core")),
                         snapshot["content"]["by_domain"]["core"]["states"])
        self.assertEqual(int(value("current_revision_status", "status", "draft")), 1)
        self.assertEqual(int(value("reviews", "decisions_total")), snapshot["reviews"]["decisions_total"])
        self.assertEqual(value("safety", "publication_authorized"), "false")
        self.assertEqual(value("safety", "scientific_rights_attested"), "false")
        self.assertEqual(value("safety", "complete_release_readiness_proven"), "false")
        self.assertEqual(AdminJob.objects.count(), 0)

    def test_csv_export_denies_non_owner_query_mutation_and_live_revocation(self):
        user = self.user("p19-csv-denied", staff=True, caps=("cms_enter", "cms_dashboard"))
        denied = self.sign_in(user)
        target = BASE + "analytics/overview/export.csv/"
        self.assertEqual(denied.get(target).status_code, 403)
        self.assertEqual(self.client_owner.get(target + "?all=true").status_code, 400)
        self.assertEqual(self.post(self.client_owner, "analytics/overview/export.csv/", {"raw": True}).status_code, 405)
        self.assertEqual(self.client_owner.get(target).status_code, 200)
        Permission.objects.get(codename="cms_owner", content_type__model="rolepolicy").user_set.remove(self.owner)
        self.assertEqual(self.client_owner.get(target).status_code, 403)

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
