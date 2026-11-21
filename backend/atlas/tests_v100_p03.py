"""P03 selectors reuse the real P01 session/CSRF and P02 proposal fixtures."""
from django.test import TestCase, override_settings

from .cms_models import AdminAuditEvent
from .cms_content_models import ContentState
from .tests_v100_p01 import BASE
from .tests_v100_p02 import ContentFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConsoleSelectorTests(ContentFixture, TestCase):
    def test_read_only_collection_and_current_proposal_filter(self):
        self.grant(self.scoped, "cms_core_view")
        reader = self.sign_in(self.scoped)
        response = reader.get(BASE + "content/category/?page_size=1&sort=oldest")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.json()["results"][0]["id"], str(self.category_state.pk))
        created = self.post(self.client, "content/category/", {"payload": {"name_en": "Synthetic private proposal", "name_fa": "کودکی"}})
        self.assertEqual(created.status_code, 201)
        found = reader.get(BASE + "content/category/?q=كودكي&status=draft").json()
        self.assertEqual(found["count"], 1)
        self.assertEqual(found["results"][0]["id"], created.json()["id"])
        self.code(self.post(reader, "content/category/", {"payload": {"name_en": "Synthetic"}}), "PERMISSION_DENIED")

    def test_collection_scope_query_and_stable_paging(self):
        self.code(self.sign_in(self.scoped).get(BASE + "content/category/"), "PERMISSION_DENIED")
        for query in ("page_size=101", "page=0", "sort=payload", "status=secret", "owner_id=1", "q=" + "x" * 201):
            self.code(self.client.get(BASE + "content/category/?" + query), "INVALID_QUERY", 400)
        self.code(self.client.get(BASE + "content/user/"), "NOT_FOUND", 404)
        for index in range(2):
            self.post(self.client, "content/category/", {"payload": {"name_en": f"Synthetic {index}"}})
        first = self.client.get(BASE + "content/category/?page_size=2").json()
        second = self.client.get(BASE + "content/category/?page_size=2&page=2").json()
        self.assertEqual(first["count"], 3)
        self.assertEqual(len({row["id"] for row in first["results"] + second["results"]}), 3)

    def test_dashboard_real_counts_freshness_redaction_and_no_read_side_effects(self):
        self.post(self.client, "content/category/", {"payload": {"name_en": "Synthetic"}})
        counts = (ContentState.objects.count(), AdminAuditEvent.objects.count())
        response = self.client.get(BASE + "dashboard/")
        data = response.json()
        category = next(row for row in data["content"] if row["kind"] == "category")
        self.assertEqual(category, {"kind": "category", "total": 2, "drafts": 1})
        self.assertEqual(data["audit"]["count"], counts[1])
        self.assertTrue(data["measured_at"])
        self.assertEqual(data["scope"], "authorized_cms_anchors")
        self.assertIn("search_telemetry", data["unavailable"])
        self.assertEqual(counts, (ContentState.objects.count(), AdminAuditEvent.objects.count()))
        self.grant(self.scoped, "cms_dashboard")
        scoped = self.sign_in(self.scoped)
        redacted = scoped.get(BASE + "dashboard/").json()
        # P10 gives this scoped actor Brain view, but no other editorial domain or audit data.
        self.assertEqual(len(redacted["content"]), 13)
        self.assertTrue(all(row["kind"].startswith("brain-") and row["total"] == 0
                            and row["drafts"] == 0 for row in redacted["content"]))
        self.assertIsNone(redacted["audit"])
        self.scoped.user_permissions.clear()
        self.code(scoped.get(BASE + "dashboard/"), "PERMISSION_DENIED")

    def test_dashboard_has_separate_capability_and_closed_query(self):
        self.code(self.sign_in(self.scoped).get(BASE + "dashboard/"), "PERMISSION_DENIED")
        self.code(self.client.get(BASE + "dashboard/?user_id=1"), "INVALID_QUERY", 400)
        me = self.client.get(BASE + "me/").json()
        self.assertIn("cms_dashboard", me["ready_capabilities"])

    def test_browser_compression_does_not_weaken_cms_revision_etag(self):
        response = self.client.get(BASE + f"content/category/{self.category_state.pk}/", HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(response["ETag"], '"0"')
        self.assertNotIn("Content-Encoding", response)
        saved = self.post(self.client, f"content/category/{self.category_state.pk}/revisions/",
            {"payload": {"description": "Synthetic browser edit"}, "base_digest": response.json()["canonical_digest"]}, etag=response["ETag"])
        self.assertEqual(saved.status_code, 200, saved.content)
