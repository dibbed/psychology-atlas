"""Isolated NON-SCIENTIFIC domain-reader and private-raw regressions."""
from unittest.mock import patch

from django.test import TransactionTestCase, override_settings

from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure
from .cms_sources import require_impact_scope, source_impact
from .models import DSMCorpus, DSMRecord, SourceReference
from .tests_v100_p02 import ContentFixture
from .tests_v100_p01 import BASE


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DomainIntegrationTests(ContentFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.corpus = DSMCorpus.objects.create(key="non-scientific-left-invalid", title="NON-SCIENTIFIC .invalid",
            source_filename="NON-SCIENTIFIC.invalid.json", source_sha256="a" * 64,
            raw_document={"fixture": "RAW-NON-SCIENTIFIC-PRIVATE.invalid"}, is_active=False)
        self.other = DSMCorpus.objects.create(key="non-scientific-right-invalid", title="NON-SCIENTIFIC .invalid",
            source_filename="NON-SCIENTIFIC.invalid.json", source_sha256="b" * 64, is_active=False)
        self.left = DSMRecord.objects.create(corpus=self.corpus, master_id="FIXTURE-1.invalid",
            name_en="NON-SCIENTIFIC first", linked_disorder=self.disorder,
            summary="NON-SCIENTIFIC isolated study preview", key_features=["NON-SCIENTIFIC .invalid"],
            source_payload={"fixture": "RAW-NON-SCIENTIFIC-PRIVATE.invalid"})
        self.child = DSMRecord.objects.create(corpus=self.corpus, master_id="FIXTURE-2.invalid",
            name_en="NON-SCIENTIFIC child", parent=self.left)
        self.right = DSMRecord.objects.create(corpus=self.other, master_id="FIXTURE-1.invalid",
            name_en="NON-SCIENTIFIC changed", linked_disorder=self.disorder)
        self.raw_state = self.anchor("dsm-record", self.left)
        self.corpus_state = self.anchor("dsm-corpus", self.corpus)

    def raw(self, client=None, state=None, etag='"0"'):
        return self.post(client or self.client,
            f"content/dsm-record/{(state or self.raw_state).pk}/raw-preview/",
            {"purpose": "source_review", "reason": "RESEARCH_RAW"}, etag=etag)

    def test_scoped_options_reject_foreign_domain_before_counts(self):
        response = self.client.get(BASE + "content/options/dsm-record/?page_size=1")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["count"], len(response.json()["results"])), (3, 1))
        self.assertNotIn("source_payload", str(response.json()))
        client = self.sign_in(self.scoped)
        response = client.get(BASE + "content/options/dsm-record/")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("count", response.json())
        self.grant(self.scoped, "cms_core_view")
        self.assertEqual(client.get(BASE + "content/options/source/").status_code, 403)

    def test_source_options_are_bibliographic_not_impact_or_raw(self):
        source = SourceReference.objects.create(title="NON-SCIENTIFIC fixture.invalid", citation="NON-SCIENTIFIC")
        response = self.client.get(BASE + "content/options/source/?q=" + str(source.pk))
        self.assertEqual(response.status_code, 200, response.content)
        item = next(row for row in response.json()["results"] if row["id"] == source.pk)
        self.assertEqual(set(item), {"id", "label", "version"})

    def test_tree_and_compare_have_no_canonical_save_or_public_activation(self):
        before = list(DSMRecord.objects.order_by("pk").values())
        raw_before = self.corpus.raw_document.copy()
        with patch.object(DSMRecord, "save", side_effect=AssertionError("Preview cannot save")), \
                patch.object(DSMCorpus, "save", side_effect=AssertionError("Preview cannot activate")):
            tree = self.client.get(BASE + f"content/dsm/tree/?corpus={self.corpus.pk}")
            compared = self.client.get(BASE + f"content/dsm/compare/?left={self.corpus.pk}&right={self.other.pk}&page_size=1")
            graph = self.client.get(BASE + f"content/dsm/graph/?corpus={self.corpus.pk}&record={self.left.pk}")
            study = self.client.get(BASE + f"content/dsm/study/?record={self.left.pk}")
        self.assertEqual(tree.status_code, 200, tree.content)
        self.assertEqual(tree.json()["results"][0]["children_count"], 1)
        self.assertEqual(tree.json()["graph"]["scope"], "page")
        self.assertEqual(compared.status_code, 200, compared.content)
        self.assertEqual((compared.json()["count"], len(compared.json()["results"])), (2, 1))
        self.assertEqual(compared.json()["results"][0]["status"], "changed")
        self.assertIn("name_en", compared.json()["results"][0]["changed_fields"])
        self.assertTrue(compared.json()["raw_archive_changed"])
        self.assertEqual(graph.status_code, 200, graph.content)
        self.assertIn({"source_id": self.left.pk, "target_id": self.child.pk, "relationship_type": "parent_child"}, graph.json()["edges"])
        self.assertEqual(study.status_code, 200, study.content)
        self.assertEqual(study.json()["sections"][0]["value"], self.left.key_features)
        self.assertFalse(study.json()["publication_available"])
        self.assertNotIn("RAW-NON-SCIENTIFIC-PRIVATE.invalid", str(tree.json()) + str(compared.json()))
        self.assertEqual(list(DSMRecord.objects.order_by("pk").values()), before)
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.raw_document, raw_before)
        self.assertFalse(self.corpus.is_active)

    def test_tree_rejects_parent_from_another_corpus_and_unknown_query(self):
        self.assertEqual(self.client.get(BASE + f"content/dsm/tree/?corpus={self.corpus.pk}&parent={self.right.pk}").status_code, 404)
        self.assertEqual(self.client.get(BASE + f"content/dsm/tree/?corpus={self.corpus.pk}&raw=true").status_code, 400)
        self.assertEqual(self.client.get(BASE + f"content/dsm/compare/?left={self.corpus.pk}&right={self.corpus.pk}").status_code, 400)

    def test_private_raw_is_explicit_current_scoped_audited_and_uneditable(self):
        detail = self.client.get(BASE + f"content/dsm-record/{self.raw_state.pk}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertNotIn("RAW-NON-SCIENTIFIC-PRIVATE.invalid", str(detail.json()))
        response = self.raw()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["raw"], self.left.source_payload)
        self.assertFalse(response.json()["editable"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertTrue(AdminAuditEvent.objects.filter(action="research.raw", target_key=str(self.raw_state.pk), outcome="success").exists())
        self.assertEqual(self.raw(etag='W/"0"').status_code, 400)
        self.assertEqual(self.raw(etag='"1"').status_code, 412)
        limited = self.user("non-scientific-dsm-reader", staff=True, caps=("cms_enter", "cms_dsm_view", "cms_dsm_preview"))
        client = self.sign_in(limited)
        before = AdminAuditEvent.objects.filter(action="research.raw", outcome="success").count()
        self.assertEqual(self.raw(client).status_code, 403)
        self.assertEqual(AdminAuditEvent.objects.filter(action="research.raw", outcome="success").count(), before)

    def test_raw_refuses_protected_assessment_content_even_to_owner(self):
        row = DSMRecord.objects.create(corpus=self.corpus, master_id="NON-SCIENTIFIC-PROTECTED.invalid",
            name_en="NON-SCIENTIFIC refusal fixture", source_payload={"manual_text": "NON-SCIENTIFIC prohibited fixture"})
        state = self.anchor("dsm-record", row)
        response = self.raw(state=state)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "PROTECTED_MATERIAL")

    def test_raw_refuses_canonical_drift_without_disclosing_archive(self):
        DSMRecord.objects.filter(pk=self.left.pk).update(summary="NON-SCIENTIFIC drift")
        response = self.raw()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("RAW-NON-SCIENTIFIC-PRIVATE.invalid", str(response.json()))

    def test_pending_source_link_is_retained_and_impact_scope_does_not_leak(self):
        source = SourceReference.objects.create(title="NON-SCIENTIFIC source-link.invalid", citation="NON-SCIENTIFIC")
        created = self.post(self.client, "content/disorder-source/", {"payload": {
            "disorder": self.disorder.pk, "source": source.pk, "note": "NON-SCIENTIFIC .invalid"},
            "reason": "DRAFT_CREATION"})
        self.assertEqual(created.status_code, 201, created.content)
        impact = source_impact(source)
        retained = [row for row in impact["archives"] if row["model"] == "ContentRevision"]
        self.assertTrue(retained)
        self.assertTrue(all(not row["mutable"] and row["domain"] == "core" for row in retained))
        self.grant(self.scoped, "cms_source_view")
        with self.assertRaises(CMSFailure) as denied:
            require_impact_scope(self.scoped, impact)
        self.assertEqual(str(denied.exception.detail["code"]), "SOURCE_IMPACT_SCOPE_DENIED")
