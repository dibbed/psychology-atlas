"""P09.03 NON-SCIENTIFIC ResearchRecord lineage on History detail and chronology."""
from django.test import TestCase, override_settings

from . import cms_content as content
from .cms_content_models import ContentRevision, ContentState
from .cms_models import AdminAuditEvent
from .models import Category, ResearchDataset, ResearchRecord, ResearchRecordDecision, TimelineEvent
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HistoryProvenanceTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.event = TimelineEvent.objects.create(slug="non-scientific-p09-linked", title_en="NON-SCIENTIFIC P09 linked",
            date_precision="year", year_start=1950, event_type="publication")
        self.unlinked = TimelineEvent.objects.create(slug="non-scientific-p09-unlinked", title_en="NON-SCIENTIFIC P09 unlinked",
            date_precision="year", year_start=1960, event_type="publication")
        self.mismatch = TimelineEvent.objects.create(slug="non-scientific-p09-mismatch", title_en="NON-SCIENTIFIC P09 mismatch",
            date_precision="year", year_start=1970, event_type="publication")
        self.dataset = self.dataset_for("non-scientific-p09-visible", "NON-SCIENTIFIC visible dataset", {})
        self.record = ResearchRecord.objects.create(dataset=self.dataset, section="timeline_events",
            external_id="NON-SCIENTIFIC-EXTERNAL-1", name_en="NON-SCIENTIFIC private research name",
            payload={"private_marker": "NON-SCIENTIFIC raw payload must not leak"},
            promoted_model="atlas.timelineevent", promoted_pk=self.event.pk)
        self.mismatched = ResearchRecord.objects.create(dataset=self.dataset, section="timeline_events",
            external_id="NON-SCIENTIFIC-EXTERNAL-2", name_en="NON-SCIENTIFIC mismatch name",
            payload={"private_marker": "NON-SCIENTIFIC mismatch payload"},
            promoted_model="atlas.concept", promoted_pk=self.mismatch.pk)
        self.states = {obj.pk: self.anchor(obj) for obj in (self.event, self.unlinked, self.mismatch)}

    def dataset_for(self, key, name, audit):
        return ResearchDataset.objects.create(key=key, source_filename="non-scientific.invalid.json",
            source_sha256=key.replace("-", "")[:64].ljust(64, "0"), dataset_name=name, dataset_version="1",
            ingestion_audit=audit)

    def anchor(self, obj):
        state = ContentState.objects.create(kind="timeline-event", canonical_pk=obj.pk, legacy_origin=True,
            canonical_digest=content.digest(content.canonical_snapshot("timeline-event", obj)), publication="current")
        payload = content.editable_snapshot("timeline-event", obj)
        revision = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
            base_digest=state.canonical_digest, payload=payload, payload_digest=content.digest(payload),
            dependency_digest=content.dependencies("timeline-event", obj), status="legacy")
        state.current_revision = revision
        state.save(update_fields=("current_revision",))
        return state

    def provenance(self, obj, client=None):
        return (client or self.client).get(BASE + f"content/timeline-event/{self.states[obj.pk].pk}/provenance/")

    def test_linked_detail_and_chronology_show_only_the_authorized_locator(self):
        response = self.provenance(self.event)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual((data["origin"]["status"], data["origin"]["count"]), ("linked", 1))
        self.assertEqual(data["origin"]["records"][0]["record_id"], self.record.pk)
        self.assertEqual(data["origin"]["records"][0]["external_id"], "NON-SCIENTIFIC-EXTERNAL-1")
        self.assertEqual(data["origin"]["records"][0]["dataset_name"], "NON-SCIENTIFIC visible dataset")
        self.assertNotIn("private_marker", str(data))
        self.assertNotIn("payload", str(data))
        self.assertNotIn("source_ids", str(data))
        self.assertEqual((data["canonical_write"], data["auto_review"]), (0, False))
        chronology = self.client.get(BASE + "content/history/chronology/")
        self.assertEqual(chronology.status_code, 200, chronology.content)
        rows = chronology.json()["results"]
        self.assertEqual([row["year_start"] for row in rows], [1950, 1960, 1970])
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id[self.event.pk]["origin"]["status"], "linked")
        self.assertEqual(by_id[self.event.pk]["origin"]["records"][0]["record_id"], self.record.pk)
        self.assertEqual(by_id[self.unlinked.pk]["origin"]["status"], "unlinked")
        self.assertEqual(by_id[self.mismatch.pk]["origin"]["status"], "unknown")
        self.assertNotIn("private_marker", chronology.content.decode())

    def test_legacy_unlinked_and_mismatched_model_are_explicit(self):
        unlinked = self.provenance(self.unlinked).json()
        self.assertEqual((unlinked["origin"]["status"], unlinked["origin"]["reason"]),
            ("unlinked", "NO_PROMOTED_RESEARCH_RECORD"))
        self.assertEqual(unlinked["origin"]["records"], [])
        mismatch = self.provenance(self.mismatch).json()
        self.assertEqual((mismatch["origin"]["status"], mismatch["origin"]["reason"]),
            ("unknown", "PROMOTED_MODEL_MISMATCH"))
        self.assertEqual(mismatch["origin"]["records"], [])
        self.assertNotIn("NON-SCIENTIFIC mismatch name", str(mismatch))

    def test_cross_scope_is_restricted_and_never_returns_details(self):
        hidden = self.dataset_for("non-scientific-p09-hidden", "NON-SCIENTIFIC hidden dataset", {"cms_domain": "dsm"})
        ResearchRecord.objects.create(dataset=hidden, section="timeline_events",
            external_id="NON-SCIENTIFIC-HIDDEN-EXTERNAL", name_en="NON-SCIENTIFIC hidden name",
            payload={"private_marker": "NON-SCIENTIFIC hidden payload"},
            promoted_model="atlas.timelineevent", promoted_pk=self.event.pk)
        user = self.user("non-scientific-p09-scoped", staff=True,
            caps=("cms_enter", "cms_history_view", "cms_research_view"))
        client = self.sign_in(user)
        response = self.provenance(self.event, client)
        self.assertEqual(response.status_code, 200, response.content)
        origin = response.json()["origin"]
        # Mixed visibility stays linked for the authorized record and reports the denied one by count only.
        self.assertEqual((origin["status"], origin["count"], origin["restricted_count"]), ("linked", 1, 1))
        self.assertEqual([row["external_id"] for row in origin["records"]], ["NON-SCIENTIFIC-EXTERNAL-1"])
        self.assertNotIn("NON-SCIENTIFIC-HIDDEN-EXTERNAL", str(response.json()))
        hidden_only = TimelineEvent.objects.create(slug="non-scientific-p09-hidden-only",
            title_en="NON-SCIENTIFIC P09 hidden only", date_precision="year", year_start=1980, event_type="publication")
        hidden_state = self.anchor(hidden_only)
        ResearchRecord.objects.create(dataset=hidden, section="timeline_events",
            external_id="NON-SCIENTIFIC-HIDDEN-ONLY", name_en="NON-SCIENTIFIC hidden only name",
            payload={"private_marker": "NON-SCIENTIFIC hidden only payload"},
            promoted_model="atlas.timelineevent", promoted_pk=hidden_only.pk)
        response = client.get(BASE + f"content/timeline-event/{hidden_state.pk}/provenance/")
        self.assertEqual(response.status_code, 200, response.content)
        origin = response.json()["origin"]
        self.assertEqual((origin["status"], origin["reason"]), ("restricted", "RESEARCH_SCOPE_DENIED"))
        self.assertEqual(origin["records"], [])
        self.assertNotIn("NON-SCIENTIFIC-HIDDEN-ONLY", str(response.json()))
        no_research = self.user("non-scientific-p09-no-research", staff=True, caps=("cms_enter", "cms_history_view"))
        response = self.provenance(self.event, self.sign_in(no_research))
        self.assertEqual((response.json()["origin"]["status"], response.json()["origin"]["reason"]),
            ("unavailable", "RESEARCH_VIEW_REQUIRED"))

    def test_names_require_raw_read_while_locator_remains_visible(self):
        user = self.user("non-scientific-p09-no-raw", staff=True,
            caps=("cms_enter", "cms_history_view", "cms_research_view"))
        response = self.provenance(self.event, self.sign_in(user))
        self.assertEqual(response.status_code, 200, response.content)
        record = response.json()["origin"]["records"][0]
        self.assertEqual(record["external_id"], "NON-SCIENTIFIC-EXTERNAL-1")
        self.assertNotIn("name_en", record)
        self.assertNotIn("NON-SCIENTIFIC private research name", str(response.json()))
        owner_record = self.provenance(self.event).json()["origin"]["records"][0]
        self.assertEqual(owner_record["name_en"], "NON-SCIENTIFIC private research name")

    def test_permissions_non_history_and_read_only_contract(self):
        before = [list(model.objects.order_by("pk").values()) for model in
            (ResearchRecord, ResearchRecordDecision, ContentState, AdminAuditEvent)]
        self.assertEqual(self.provenance(self.event).status_code, 200)
        self.assertEqual([list(model.objects.order_by("pk").values()) for model in
            (ResearchRecord, ResearchRecordDecision, ContentState, AdminAuditEvent)], before)
        denied = self.user("non-scientific-p09-denied", staff=True, caps=("cms_enter", "cms_core_view"))
        client = self.sign_in(denied)
        self.assertEqual(self.provenance(self.event, client).status_code, 403)
        self.assertEqual(client.get(BASE + "content/history/chronology/").status_code, 403)
        category = Category.objects.create(slug="non-scientific-p09-category", name_en="NON-SCIENTIFIC category")
        state = ContentState.objects.create(kind="category", canonical_pk=category.pk, legacy_origin=True,
            canonical_digest=content.digest(content.canonical_snapshot("category", category)), publication="current")
        payload = content.editable_snapshot("category", category)
        revision = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
            base_digest=state.canonical_digest, payload=payload, payload_digest=content.digest(payload),
            dependency_digest=content.dependencies("category", category), status="legacy")
        state.current_revision = revision
        state.save(update_fields=("current_revision",))
        self.assertEqual(self.client.get(BASE + f"content/category/{state.pk}/provenance/").status_code, 404)
        self.assertEqual(self.client.get(BASE + f"content/timeline-event/{self.states[self.event.pk].pk}/provenance/?q=x").status_code, 400)
