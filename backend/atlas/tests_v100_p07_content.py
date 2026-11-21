"""P07 lifecycle acceptance using isolated, explicitly NON-SCIENTIFIC fixtures."""
import importlib
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import path

from config.urls import urlpatterns as project_urls

from . import cms_content as content, cms_review as review
from .cms_content_models import ContentRevision, ContentState
from .cms_content_views import ContentArchiveView, ContentPreviewView, ContentSchemaView, ContentValidateView
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure
from .cms_review_models import ReviewDecision, ReviewPolicy, ReviewTask
from .models import (
    Category, Concept, ConceptAlias, ConceptRelationship, ConceptRelationshipSource,
    ConceptSource, ConceptSymptom, ConceptSymptomSource, DifferentialRelationship,
    Disorder, DisorderConcept, DisorderSource, DisorderSymptom, DSMCorpus, DSMRecord,
    DSMRecordRelation, SourceReference, Symptom,
)
from .tests_v100_p01 import BASE, SecurityFixture


# Exported classes are exercised independently of the parent's URL-registration work.
urlpatterns = [
    path("api/admin/content/schema/", ContentSchemaView.as_view()),
    path("api/admin/content/<str:kind>/<str:target_id>/validate/", ContentValidateView.as_view()),
    path("api/admin/content/<str:kind>/<str:target_id>/preview/", ContentPreviewView.as_view()),
    path("api/admin/content/<str:kind>/<str:target_id>/archive/", ContentArchiveView.as_view()),
    *project_urls,
]


@override_settings(ROOT_URLCONF=__name__, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DomainLifecycleTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        ReviewPolicy.objects.get_or_create(pk=1)
        self.client = self.sign_in(self.owner)
        self.session = self.client.session["cms_session_id"]
        self.source = SourceReference.objects.create(title="NON-SCIENTIFIC P07 test source",
            citation="NON-SCIENTIFIC isolated fixture; no scientific or legal assertion",
            url="https://example.invalid/p07", verification_status="source_checked")
        self.category = Category.objects.create(slug="non-scientific-p07", name_en="NON-SCIENTIFIC P07 category")
        self.disorder = Disorder.objects.create(category=self.category, slug="non-scientific-p07-a",
            name_en="NON-SCIENTIFIC P07 disorder A")
        other = Disorder.objects.create(category=self.category, slug="non-scientific-p07-b",
            name_en="NON-SCIENTIFIC P07 disorder B")
        self.symptom = Symptom.objects.create(slug="non-scientific-p07", name_en="NON-SCIENTIFIC P07 symptom")
        self.concept = Concept.objects.create(slug="non-scientific-p07-a", name_en="NON-SCIENTIFIC concept A",
            simple_definition="NON-SCIENTIFIC test definition")
        other_concept = Concept.objects.create(slug="non-scientific-p07-b", name_en="NON-SCIENTIFIC concept B",
            simple_definition="NON-SCIENTIFIC test definition")
        relationship = ConceptRelationship.objects.create(source_concept=self.concept, target_concept=other_concept)
        symptom_link = ConceptSymptom.objects.create(concept=self.concept, symptom=self.symptom)
        self.corpus = DSMCorpus.objects.create(key="non-scientific-p07", title="NON-SCIENTIFIC P07 corpus", version_date=date(2026, 1, 1),
            source_filename="non-scientific-fixture.json", source_sha256="a" * 64,
            raw_document={"private_test_marker": "NON-SCIENTIFIC raw corpus must not leak"})
        self.record = DSMRecord.objects.create(corpus=self.corpus, master_id="NON-SCIENTIFIC-A",
            name_en="NON-SCIENTIFIC P07 record A", source_payload={"private_test_marker": "NON-SCIENTIFIC raw record must not leak"})
        other_record = DSMRecord.objects.create(corpus=self.corpus, master_id="NON-SCIENTIFIC-B",
            name_en="NON-SCIENTIFIC P07 record B")
        self.objects = {
            "category": self.category, "disorder": self.disorder, "symptom": self.symptom,
            "disorder-symptom": DisorderSymptom.objects.create(disorder=self.disorder, symptom=self.symptom),
            "differential-relationship": DifferentialRelationship.objects.create(disorder=self.disorder,
                related_disorder=other, relationship_type="differential"),
            "disorder-source": DisorderSource.objects.create(disorder=self.disorder, source=self.source),
            "concept": self.concept, "concept-relationship": relationship,
            "concept-alias": ConceptAlias.objects.create(concept=self.concept, text="NON-SCIENTIFIC test alias"),
            "concept-relationship-source": ConceptRelationshipSource.objects.create(relationship=relationship, source=self.source),
            "concept-symptom": symptom_link,
            "concept-symptom-source": ConceptSymptomSource.objects.create(relationship=symptom_link, source=self.source),
            "disorder-concept": DisorderConcept.objects.create(disorder=self.disorder, concept=self.concept),
            "concept-source": ConceptSource.objects.create(concept=self.concept, source=self.source),
            "dsm-corpus": self.corpus, "dsm-record": self.record,
            "dsm-record-relation": DSMRecordRelation.objects.create(source=self.record, target=other_record, relationship_type="nearby"),
        }
        self.other_disorder, self.other_concept = other, other_concept

    def anchor(self, kind):
        obj = self.objects[kind]
        state = ContentState.objects.create(kind=kind, canonical_pk=obj.pk, legacy_origin=True,
            canonical_digest=content.digest(content.canonical_snapshot(kind, obj)), publication="current")
        snapshot = content.editable_snapshot(kind, obj)
        revision = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
            base_digest=state.canonical_digest, payload=snapshot, payload_digest=content.digest(snapshot),
            dependency_digest=content.dependencies(kind, obj), status="legacy")
        state.current_revision = revision
        state.save(update_fields=("current_revision",))
        return state

    def propose(self, state, values, actor=None, session=None):
        state.refresh_from_db()
        return content.propose((actor or self.owner).pk, session or self.session, state.kind, str(state.pk),
            values, state.version, state.canonical_digest, "CONTENT_UPDATE", uuid.uuid4())

    def evidence(self, state):
        return [{"source_id": self.source.pk, "locator": "NON-SCIENTIFIC fixture section",
            "fields": [key for key, value in state.current_revision.payload.items() if value]}]

    def submit(self, state):
        state.refresh_from_db()
        return review.submit_review(self.owner.pk, self.session, state.kind, str(state.pk), state.version,
            self.evidence(state), uuid.uuid4())

    def approve(self, state):
        state = self.submit(state)
        for review_type in ("source", "scientific"):
            task = ReviewTask.objects.get(subject__state=state, review_type=review_type)
            state = review.assign_review(self.owner.pk, self.session, state.kind, str(state.pk), state.version,
                task.pk, task.version, self.owner.pk, uuid.uuid4())
            task.refresh_from_db()
            state = review.decide_review(self.owner.pk, self.session, state.kind, str(state.pk), state.version,
                task.pk, task.version, "approve", "SOURCE_VERIFIED" if review_type == "source" else "SCIENCE_VERIFIED",
                [], True, uuid.uuid4())
        return state

    def assert_failure(self, callback, code):
        with self.assertRaises(CMSFailure) as error:
            callback()
        self.assertEqual(str(error.exception.detail["code"]), code)

    def test_all_seventeen_kinds_edit_review_without_canonical_publication(self):
        self.assertEqual(set(self.objects), {kind for kind in ContentState.Kind.values if kind in content.REGISTRY and content.domain_for(kind) in {"core", "dsm"}})
        fields = {"category": "description", "disorder": "overview", "symptom": "description", "concept": "simple_definition",
            "concept-alias": "text", "dsm-corpus": "purpose", "dsm-record": "summary"}
        for kind, obj in self.objects.items():
            with self.subTest(kind=kind):
                canonical = content.canonical_snapshot(kind, obj)
                state = self.anchor(kind)
                field = fields.get(kind, "note" if kind.endswith("source") or kind == "disorder-symptom" else "explanation")
                state = self.propose(state, {field: "NON-SCIENTIFIC revised fixture"})
                state = self.approve(state)
                self.assertEqual(state.current_revision.status, "approved")
                self.assertTrue(review.approval_eligibility(state, obj)["eligible"])
                obj.refresh_from_db()
                self.assertEqual(content.canonical_snapshot(kind, obj), canonical)
                self.assertEqual(state.current_revision.intent, "edit")

    def test_all_seventeen_kinds_create_validate_preview_discard_without_canonical_writes(self):
        extra = SourceReference.objects.create(title="NON-SCIENTIFIC second P07 source", citation="NON-SCIENTIFIC fixture")
        payloads = {
            "category": {"name_en": "NON-SCIENTIFIC draft category"},
            "disorder": {"name_en": "NON-SCIENTIFIC draft disorder"},
            "symptom": {"slug": "non-scientific-draft-symptom", "name_en": "NON-SCIENTIFIC draft symptom"},
            "disorder-symptom": {"disorder": self.other_disorder.pk, "symptom": self.symptom.pk},
            "differential-relationship": {"disorder": self.other_disorder.pk, "related_disorder": self.disorder.pk, "relationship_type": "related"},
            "disorder-source": {"disorder": self.other_disorder.pk, "source": extra.pk},
            "concept": {"slug": "non-scientific-draft-concept", "name_en": "NON-SCIENTIFIC draft concept", "simple_definition": "NON-SCIENTIFIC draft"},
            "concept-relationship": {"source_concept": self.other_concept.pk, "target_concept": self.concept.pk},
            "concept-alias": {"concept": self.concept.pk, "text": "NON-SCIENTIFIC draft alias"},
            "concept-relationship-source": {"relationship": self.objects["concept-relationship"].pk, "source": extra.pk},
            "concept-symptom": {"concept": self.concept.pk, "symptom": self.symptom.pk, "relationship_type": "manifestation"},
            "concept-symptom-source": {"relationship": self.objects["concept-symptom"].pk, "source": extra.pk},
            "disorder-concept": {"disorder": self.disorder.pk, "concept": self.concept.pk, "role": "maintaining"},
            "concept-source": {"concept": self.concept.pk, "source": extra.pk},
            "dsm-corpus": {"key": "non-scientific-draft-corpus", "title": "NON-SCIENTIFIC draft corpus"},
            "dsm-record": {"corpus": self.corpus.pk, "master_id": "NON-SCIENTIFIC-DRAFT", "name_en": "NON-SCIENTIFIC draft record"},
            "dsm-record-relation": {"source": self.record.pk, "target": self.objects["dsm-record-relation"].target_id, "relationship_type": "differential"},
        }
        for kind, values in payloads.items():
            with self.subTest(kind=kind):
                Model = content.kind_entry(kind)[0]
                count = Model.objects.count()
                state = content.propose(self.owner.pk, self.session, kind, None, values, None, None, "DRAFT_CREATION", uuid.uuid4())
                self.assertIsNone(state.canonical_pk)
                self.assertEqual(state.publication, "never_published")
                for action in ("validate", "preview"):
                    _, result = content.inspect_proposal(self.owner.pk, self.session, kind, str(state.pk), state.version, action)
                    self.assertTrue(result["valid"])
                    self.assertFalse(result["publication_available"])
                state = content.discard(self.owner.pk, self.session, kind, str(state.pk), state.version, state.canonical_digest, uuid.uuid4())
                self.assertEqual(state.current_revision.status, "discarded")
                self.assertEqual(Model.objects.count(), count)

    def test_archive_intent_keeps_live_visibility_and_is_hash_bound_through_review(self):
        state = self.anchor("concept")
        old_hash = review.subject_hash(state.current_revision)
        state = content.archive_proposal(self.owner.pk, self.session, state.kind, str(state.pk), state.version, uuid.uuid4())
        self.assertEqual(state.current_revision.intent, "archive")
        self.assertNotEqual(review.subject_hash(state.current_revision), old_hash)
        state = self.approve(state)
        self.concept.refresh_from_db()
        self.assertTrue(self.concept.is_active)
        self.assertEqual(state.current_revision.intent, "archive")
        self.assertEqual(state.current_revision.status, "approved")
        subject = review.latest_tasks(state)[0].subject
        subject.intent = "edit"
        self.assertNotEqual(review.subject_hash(subject), review.latest_tasks(state)[0].revision_hash)

    def test_domain_and_reference_permissions_fail_closed_before_writes_or_counts(self):
        scoped = self.user("non-scientific-core-editor", staff=True,
            caps=("cms_enter", "cms_core_view", "cms_core_edit", "cms_core_create"))
        client = self.sign_in(scoped)
        session = client.session["cms_session_id"]
        state = self.anchor("dsm-record")
        self.assert_failure(lambda: self.propose(state, {"summary": "NON-SCIENTIFIC denied"}, scoped, session), "PERMISSION_DENIED")
        self.assertEqual(client.get(BASE + "content/dsm-record/").status_code, 403)
        self.assertEqual(client.get(BASE + "content/not-a-kind/").status_code, 404)
        link = self.anchor("concept-source")
        self.assert_failure(lambda: self.propose(link, {"note": "NON-SCIENTIFIC denied"}, scoped, session), "PERMISSION_DENIED")
        self.assertEqual(link.revisions.count(), 1)
        response = client.get(BASE + "content/concept-source/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 0)
        response = client.get(BASE + "reviews/?kind=concept-source")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 0)

    def test_dsm_reader_queue_and_schema_filter_core_before_counts(self):
        for kind in self.objects:
            self.anchor(kind)
        user = self.user("non-scientific-dsm-reader", staff=True, caps=("cms_enter", "cms_dsm_view"))
        client = self.sign_in(user)
        response = client.get(BASE + "content/schema/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({item["domain"] for item in response.json()["kinds"]}, {"dsm"})
        response = client.get(BASE + "reviews/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({item["record"]["domain"] for item in response.json()["results"]}, {"dsm"})
        self.assertEqual(client.get(BASE + "content/concept/").status_code, 403)
        self.assertEqual(client.get(BASE + "reviews/?kind=not-a-kind").status_code, 400)

    def test_review_assignment_uses_the_target_domain_and_reference_capabilities(self):
        state = self.propose(self.anchor("dsm-record"), {"summary": "NON-SCIENTIFIC review scope"})
        state = self.submit(state)
        core_reviewer = self.user("non-scientific-wrong-domain-reviewer", staff=True,
            caps=("cms_enter", "cms_dsm_view", "cms_review_decide_core_source"))
        task = review.latest_tasks(state)[0]
        self.assert_failure(lambda: review.assign_review(self.owner.pk, self.session, state.kind, str(state.pk), state.version,
            task.pk, task.version, core_reviewer.pk, uuid.uuid4()), "INVALID_REVIEWER")

    def test_current_session_and_permissions_rechecked(self):
        state = self.anchor("symptom")
        self.owner.user_permissions.clear()
        self.assert_failure(lambda: self.propose(state, {"description": "NON-SCIENTIFIC denied"}), "PERMISSION_DENIED")
        self.assertEqual(state.revisions.count(), 1)

    def test_date_input_is_json_native_and_raw_hash_dependency_detects_drift(self):
        state = self.propose(self.anchor("dsm-corpus"), {"version_date": "2026-02-01"})
        self.assertEqual(state.current_revision.payload["version_date"], "2026-02-01")
        self.assertEqual(content.dependencies(state.kind, self.corpus, state.current_revision.payload), state.current_revision.dependency_digest)
        self.corpus.raw_document = {"private_test_marker": "NON-SCIENTIFIC changed raw corpus"}
        self.corpus.save(update_fields=("raw_document",))
        self.assertNotEqual(content.dependencies(state.kind, self.corpus, state.current_revision.payload), state.current_revision.dependency_digest)

    def test_cas_full_snapshot_validation_and_audit_failure_roll_back(self):
        state = self.anchor("concept-alias")
        state = self.propose(state, {"text": "NON-SCIENTIFIC updated alias"})
        self.assert_failure(lambda: content.propose(self.owner.pk, self.session, state.kind, str(state.pk),
            {"text": "NON-SCIENTIFIC stale"}, 0, state.canonical_digest, "CONTENT_UPDATE", uuid.uuid4()), "STALE_REVISION")
        before = list(state.revisions.values())
        with patch("atlas.cms_content.AdminAuditEvent.objects.create", side_effect=DatabaseError("NON-SCIENTIFIC fault injection")):
            with self.assertRaises(DatabaseError):
                self.propose(state, {"text": "NON-SCIENTIFIC rolled back"})
        self.assertEqual(list(state.revisions.values()), before)
        with self.assertRaises(ValidationError):
            state.revisions.update(payload={})
        state.refresh_from_db()
        self.assertEqual(state.version, 1)

    def test_parent_source_policy_changes_make_review_stale(self):
        state = self.propose(self.anchor("concept-alias"), {"text": "NON-SCIENTIFIC proposed alias"})
        state = self.submit(state)
        tasks = review.latest_tasks(state)
        self.concept.name_en = "NON-SCIENTIFIC changed parent"
        self.concept.save(update_fields=("name_en",))
        self.assertIn("DEPENDENCY_CHANGED", review.freshness(state, self.objects[state.kind], tasks, review.current_policy()))
        self.source.citation = "NON-SCIENTIFIC changed source"
        self.source.save(update_fields=("citation",))
        self.assertIn("DEPENDENCY_CHANGED", review.freshness(state, self.objects[state.kind], tasks, review.current_policy()))
        policy = review.current_policy()
        policy.version += 1
        policy.save(update_fields=("version",))
        self.assertIn("POLICY_CHANGED", review.freshness(state, self.objects[state.kind], tasks, policy))

    def test_raw_values_absent_from_detail_history_validate_and_preview(self):
        for kind in ("dsm-corpus", "dsm-record"):
            state = self.anchor(kind)
            for suffix in ("", "revisions/"):
                response = self.client.get(BASE + f"content/{kind}/{state.pk}/" + suffix)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertNotIn("private_test_marker", response.content.decode())
                self.assertNotIn("must not leak", response.content.decode())
                if not suffix:
                    raw_field = "raw_document" if kind == "dsm-corpus" else "source_payload"
                    summary = response.json()["immutable_fields"][raw_field]
                    self.assertEqual(len(summary["sha256"]), 64)
                    self.assertGreater(summary["size_bytes"], 0)
            before = (ContentRevision.objects.count(), AdminAuditEvent.objects.count(), state.version)
            for action in ("validate", "preview"):
                response = self.post(self.client, f"content/{kind}/{state.pk}/{action}/", {}, etag='"0"')
                self.assertEqual(response.status_code, 200, response.content)
                self.assertNotIn("private_test_marker", response.content.decode())
                self.assertEqual(self.post(self.client, f"content/{kind}/{state.pk}/{action}/", {}, etag='"1"').status_code, 412)
            state.refresh_from_db()
            self.assertEqual((ContentRevision.objects.count(), state.version), (before[0], before[2]))
            obj = self.objects[kind]
            obj.refresh_from_db()
            self.assertIn("private_test_marker", obj.raw_document if kind == "dsm-corpus" else obj.source_payload)

    def test_legacy_hash_and_protected_update_contract_remains(self):
        for kind in ("category", "disorder"):
            state = self.anchor(kind)
            original = state.current_revision
            expected = content.digest({"id": original.pk, "payload": original.payload,
                "base": original.base_digest, "schema": original.schema_version})
            self.assertEqual(review.subject_hash(original), expected)
            for values in ({"slug": "non-scientific-replacement"}, {"is_active": False}):
                with self.assertRaises(CMSFailure):
                    self.propose(state, values)
            original.refresh_from_db()
            self.assertEqual(review.subject_hash(original), expected)

    def test_field_values_overlay_full_canonical_without_rewriting_legacy_payload_or_hash(self):
        self.category.sort_order = 37
        self.category.save(update_fields=("sort_order",))
        self.disorder.clinical_features = "NON-SCIENTIFIC existing clinical fixture"
        self.disorder.save(update_fields=("clinical_features",))
        for kind, field, value in (("category", "sort_order", 37),
                ("disorder", "clinical_features", self.disorder.clinical_features)):
            state = self.anchor(kind)
            original = state.current_revision
            before = original.payload.copy(), original.payload_digest, review.subject_hash(original)
            dto = content.revision_data(state, self.objects[kind])
            self.assertNotIn(field, dto["payload"])
            self.assertEqual(dto["field_values"][field], value)
            state = self.propose(state, {"name_fa": "NON-SCIENTIFIC overlay"})
            dto = content.revision_data(state, self.objects[kind])
            self.assertEqual(dto["field_values"]["name_fa"], "NON-SCIENTIFIC overlay")
            self.assertEqual(dto["field_values"][field], value)
            if kind == "disorder":
                self.assertEqual(dto["field_values"]["category"], self.category.pk)
            original.refresh_from_db()
            self.assertEqual((original.payload, original.payload_digest, review.subject_hash(original)), before)

    def test_ordinary_field_values_do_not_validate_or_expose_legacy_raw_json(self):
        self.corpus.source_registry = "NON-SCIENTIFIC malformed legacy structured value"
        self.corpus.save(update_fields=("source_registry",))
        state = self.anchor("dsm-corpus")
        with patch("atlas.cms_content.validate_snapshot", side_effect=AssertionError("Ordinary DTO must not validate")):
            dto = content.revision_data(state, self.corpus)
        self.assertEqual(dto["field_values"]["source_registry"], self.corpus.source_registry)
        self.assertNotIn("raw_document", dto["field_values"])
        self.assertEqual(len(dto["immutable_fields"]["raw_document"]["sha256"]), 64)

    def test_migration_reverse_guard_rejects_retained_new_kind_or_archive_history(self):
        migration = importlib.import_module("atlas.migrations.0044_v100_p07_content_domains")
        from django.apps import apps
        from django.db import connection
        self.anchor("symptom")
        with self.assertRaises(RuntimeError):
            migration.guard_reverse(apps, SimpleNamespace(connection=connection))

    def test_backfill_covers_all_fifteen_new_kinds_preserves_old_hashes_and_is_idempotent(self):
        from django.apps import apps
        from django.db import connection
        old = [self.anchor(kind) for kind in ("category", "disorder")]
        revisions = list(ContentRevision.objects.filter(state__in=old).order_by("pk").values())
        states = list(ContentState.objects.filter(pk__in=[row.pk for row in old]).order_by("pk").values())
        events = list(AdminAuditEvent.objects.order_by("pk").values())
        migration = importlib.import_module("atlas.migrations.0044_v100_p07_content_domains")
        editor = SimpleNamespace(connection=connection)
        migration.backfill(apps, editor)
        for kind, obj in self.objects.items():
            state = ContentState.objects.get(kind=kind, canonical_pk=obj.pk)
            if kind not in {"category", "disorder"}:
                self.assertEqual(state.current_revision.status, "legacy")
                self.assertTrue(state.legacy_origin)
                self.assertEqual(state.canonical_digest, content.digest(content.canonical_snapshot(kind, obj)))
                self.assertNotIn("raw_document", state.current_revision.payload)
                self.assertNotIn("source_payload", state.current_revision.payload)
                self.assertFalse(ReviewTask.objects.filter(subject__state=state).exists())
        counts = ContentState.objects.count(), ContentRevision.objects.count()
        migration.backfill(apps, editor)
        self.assertEqual((ContentState.objects.count(), ContentRevision.objects.count()), counts)
        self.assertEqual(list(ContentRevision.objects.filter(state__in=old).order_by("pk").values()), revisions)
        self.assertEqual(list(ContentState.objects.filter(pk__in=[row.pk for row in old]).order_by("pk").values()), states)
        self.assertEqual(list(AdminAuditEvent.objects.order_by("pk").values()), events)

    def test_archive_and_review_audit_failure_roll_back_immutable_history_and_tasks(self):
        state = self.anchor("concept")

        def snapshot():
            return [list(Model.objects.order_by("pk").values()) for Model in
                (ContentState, ContentRevision, ReviewTask, ReviewDecision, AdminAuditEvent)]

        before = snapshot()
        with patch("atlas.cms_content.AdminAuditEvent.objects.create", side_effect=DatabaseError("NON-SCIENTIFIC fault")):
            with self.assertRaises(DatabaseError):
                content.archive_proposal(self.owner.pk, self.session, state.kind, str(state.pk), state.version, uuid.uuid4())
        self.assertEqual(snapshot(), before)
        state = self.propose(state, {"simple_definition": "NON-SCIENTIFIC draft"})
        before = snapshot()
        with patch("atlas.cms_review.AdminAuditEvent.objects.create", side_effect=DatabaseError("NON-SCIENTIFIC fault")):
            with self.assertRaises(DatabaseError):
                self.submit(state)
        self.assertEqual(snapshot(), before)
        state = self.submit(state)
        task = ReviewTask.objects.get(subject__state=state, review_type="source")
        before = snapshot()
        with patch("atlas.cms_review.AdminAuditEvent.objects.create", side_effect=DatabaseError("NON-SCIENTIFIC fault")):
            with self.assertRaises(DatabaseError):
                review.assign_review(self.owner.pk, self.session, state.kind, str(state.pk), state.version,
                    task.pk, task.version, self.owner.pk, uuid.uuid4())
        self.assertEqual(snapshot(), before)
        state = review.assign_review(self.owner.pk, self.session, state.kind, str(state.pk), state.version,
            task.pk, task.version, self.owner.pk, uuid.uuid4())
        task.refresh_from_db()
        before = snapshot()
        with patch("atlas.cms_review.AdminAuditEvent.objects.create", side_effect=DatabaseError("NON-SCIENTIFIC fault")):
            with self.assertRaises(DatabaseError):
                review.decide_review(self.owner.pk, self.session, state.kind, str(state.pk), state.version,
                    task.pk, task.version, "approve", "SOURCE_VERIFIED", [], True, uuid.uuid4())
        self.assertEqual(snapshot(), before)
