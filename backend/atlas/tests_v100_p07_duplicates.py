"""P07.04 NON-SCIENTIFIC duplicate evidence and live archive impact."""
import uuid
from datetime import date

from django.test import TestCase, override_settings

from . import cms_content as content
from .cms_content_models import ContentRevision, ContentState
from .cms_models import AdminAuditEvent
from .models import (
    Bookmark, Category, ClinicalCase, Concept, ConceptAlias, DailyChallenge, Disorder,
    DisorderConcept, DisorderSymptom, DSMCorpus, DSMRecord, Flashcard, Quiz, StudyActivity,
    Symptom, UserNote, UserProgress,
)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DuplicateCandidateTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.category = Category.objects.create(slug="non-scientific-p07-dup", name_en="NON-SCIENTIFIC P07 duplicate category")
        self.subject = Disorder.objects.create(category=self.category, slug="non-scientific-p07-dup-subject",
            name_en="NON-SCIENTIFIC P07 disorder A")
        self.exact = Disorder.objects.create(category=self.category, slug="non-scientific-p07-dup-exact",
            name_en="NON-SCIENTIFIC P07 disorder A")
        self.identity = Disorder.objects.create(category=self.category, slug="NON-SCIENTIFIC-P07-DUP-SUBJECT",
            name_en="NON-SCIENTIFIC identity case variant")
        self.lexical = Disorder.objects.create(category=self.category, slug="non-scientific-p07-dup-lexical",
            name_en="NON-SCIENTIFIC P07 disorder B")
        self.unrelated = Disorder.objects.create(category=self.category, slug="non-scientific-p07-dup-unrelated",
            name_en="NON-SCIENTIFIC completely different wording")
        self.state = self.anchor("disorder", self.subject)

    def anchor(self, kind, obj):
        state = ContentState.objects.create(kind=kind, canonical_pk=obj.pk, legacy_origin=True,
            canonical_digest=content.digest(content.canonical_snapshot(kind, obj)), publication="current")
        payload = content.editable_snapshot(kind, obj)
        revision = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
            base_digest=state.canonical_digest, payload=payload, payload_digest=content.digest(payload),
            dependency_digest=content.dependencies(kind, obj), status="legacy")
        state.current_revision = revision
        state.save(update_fields=("current_revision",))
        return state

    def get_duplicates(self, kind=None, target=None, client=None):
        return (client or self.client).get(BASE + f"content/{kind or 'disorder'}/{target or self.state.pk}/duplicates/")

    def test_tiers_are_identity_probable_and_lexical_without_false_positive(self):
        response = self.get_duplicates()
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual((data["canonical_pk"], data["merge_available"], data["canonical_write"]), (self.subject.pk, False, 0))
        by_id = {row["id"]: row for row in data["candidates"]}
        self.assertEqual(by_id[self.identity.pk]["tier"], "identity_conflict")
        self.assertEqual(by_id[self.exact.pk]["tier"], "probable_duplicate")
        self.assertEqual(by_id[self.lexical.pk]["tier"], "lexical_only")
        self.assertNotIn(self.unrelated.pk, by_id)
        self.assertEqual([row["id"] for row in data["candidates"][:3]], [self.identity.pk, self.exact.pk, self.lexical.pk])
        self.assertEqual(data["tiers"], {"identity_conflict": 1, "probable_duplicate": 1, "lexical_only": 1})
        self.assertFalse(data["truncated"])
        self.assertNotIn("raw_document", str(data))
        self.assertNotIn("source_payload", str(data))

    def test_candidate_order_and_digest_are_deterministic(self):
        first = self.get_duplicates().json()
        second = self.get_duplicates().json()
        self.assertEqual(first["candidates"], second["candidates"])
        self.assertEqual(first["tiers"], second["tiers"])

    def test_alias_overlap_is_probable_but_never_auto_merged(self):
        subject = Concept.objects.create(slug="non-scientific-p07-alias-subject", name_en="NON-SCIENTIFIC concept subject",
            simple_definition="NON-SCIENTIFIC fixture")
        ConceptAlias.objects.create(concept=subject, text="NON-SCIENTIFIC shared alias")
        named = Concept.objects.create(slug="non-scientific-p07-alias-named", name_en="NON-SCIENTIFIC shared alias",
            simple_definition="NON-SCIENTIFIC fixture")
        aliased = Concept.objects.create(slug="non-scientific-p07-alias-aliased", name_en="NON-SCIENTIFIC other concept",
            simple_definition="NON-SCIENTIFIC fixture")
        ConceptAlias.objects.create(concept=aliased, text="NON-SCIENTIFIC shared alias")
        state = self.anchor("concept", subject)
        response = self.get_duplicates("concept", state.pk)
        self.assertEqual(response.status_code, 200, response.content)
        by_id = {row["id"]: row for row in response.json()["candidates"]}
        self.assertEqual(by_id[named.pk]["tier"], "probable_duplicate")
        self.assertEqual(by_id[aliased.pk]["tier"], "probable_duplicate")
        self.assertTrue(all(row["tier"] != "identity_conflict" for row in response.json()["candidates"]))
        self.assertEqual(Concept.objects.filter(pk__in=(subject.pk, named.pk, aliased.pk)).count(), 3)

    def test_dsm_duplicates_are_scoped_to_the_same_corpus(self):
        corpus = DSMCorpus.objects.create(key="non-scientific-p07-dup", title="NON-SCIENTIFIC corpus",
            version_date=date(2026, 1, 1), source_filename="non-scientific.invalid.json", source_sha256="a" * 64)
        other = DSMCorpus.objects.create(key="non-scientific-p07-dup-other", title="NON-SCIENTIFIC corpus other",
            version_date=date(2026, 1, 1), source_filename="non-scientific.invalid.json", source_sha256="b" * 64)
        subject = DSMRecord.objects.create(corpus=corpus, master_id="NON-SCIENTIFIC-DSM-A", name_en="NON-SCIENTIFIC DSM record")
        same = DSMRecord.objects.create(corpus=corpus, master_id="non-scientific-dsm-a", name_en="NON-SCIENTIFIC DSM record")
        foreign = DSMRecord.objects.create(corpus=other, master_id="NON-SCIENTIFIC-DSM-A", name_en="NON-SCIENTIFIC DSM record")
        state = self.anchor("dsm-record", subject)
        response = self.get_duplicates("dsm-record", state.pk)
        self.assertEqual(response.status_code, 200, response.content)
        ids = [row["id"] for row in response.json()["candidates"]]
        self.assertIn(same.pk, ids)
        self.assertNotIn(foreign.pk, ids)

    def test_read_is_write_free_and_draft_has_no_identity_claim(self):
        def snapshot():
            return [list(model.objects.order_by("pk").values()) for model in
                (Disorder, ContentState, ContentRevision, AdminAuditEvent)]
        before = snapshot()
        self.assertEqual(self.get_duplicates().status_code, 200)
        self.assertEqual(snapshot(), before)
        draft = ContentState.objects.create(kind="disorder", canonical_digest=content.digest({}))
        payload = {"name_en": "NON-SCIENTIFIC draft only"}
        revision = ContentRevision.objects.create(state=draft, sequence=0, base_version=0,
            base_digest=draft.canonical_digest, payload=payload, payload_digest=content.digest(payload),
            dependency_digest=content.digest({}), status="draft")
        draft.current_revision = revision
        draft.save(update_fields=("current_revision",))
        response = self.get_duplicates(target=draft.pk)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["reason"], "NO_CANONICAL_IDENTITY")
        self.assertEqual(response.json()["candidates"], [])

    def test_permissions_fail_closed_and_unknown_or_query_is_rejected(self):
        reader = self.user("non-scientific-p07-dup-view", staff=True, caps=("cms_enter", "cms_core_view"))
        client = self.sign_in(reader)
        self.assertEqual(self.get_duplicates(client=client).status_code, 403)
        self.grant(reader, "cms_core_preview")
        self.assertEqual(self.get_duplicates(client=client).status_code, 200)
        dsm = self.user("non-scientific-p07-dup-dsm", staff=True,
            caps=("cms_enter", "cms_dsm_view", "cms_dsm_preview"))
        self.assertEqual(self.get_duplicates(client=self.sign_in(dsm)).status_code, 403)
        self.assertEqual(self.get_duplicates(kind="not-a-kind").status_code, 404)
        self.assertEqual(self.client.get(BASE + f"content/disorder/{self.state.pk}/duplicates/?q=x").status_code, 400)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ArchiveImpactTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.category = Category.objects.create(slug="non-scientific-p07-impact", name_en="NON-SCIENTIFIC P07 impact category")
        self.disorder = Disorder.objects.create(category=self.category, slug="non-scientific-p07-impact-subject",
            name_en="NON-SCIENTIFIC P07 impact disorder")
        self.symptom = Symptom.objects.create(slug="non-scientific-p07-impact-symptom", name_en="NON-SCIENTIFIC symptom")
        self.concept = Concept.objects.create(slug="non-scientific-p07-impact-concept", name_en="NON-SCIENTIFIC concept",
            simple_definition="NON-SCIENTIFIC fixture")
        DisorderSymptom.objects.create(disorder=self.disorder, symptom=self.symptom)
        DisorderConcept.objects.create(disorder=self.disorder, concept=self.concept)
        Bookmark.objects.create(user=self.owner, disorder=self.disorder)
        UserProgress.objects.create(user=self.owner, disorder=self.disorder)
        UserNote.objects.create(user=self.owner, disorder=self.disorder, body="NON-SCIENTIFIC note")
        Quiz.objects.create(slug="non-scientific-p07-impact-quiz", title="NON-SCIENTIFIC quiz", disorder=self.disorder)
        ClinicalCase.objects.create(slug="non-scientific-p07-impact-case", title="NON-SCIENTIFIC case",
            patient_summary="NON-SCIENTIFIC fixture", primary_disorder=self.disorder)
        Flashcard.objects.create(slug="non-scientific-p07-impact-card", front="NON-SCIENTIFIC front",
            back="NON-SCIENTIFIC back", disorder=self.disorder)
        DailyChallenge.objects.create(prompt="NON-SCIENTIFIC prompt", explanation="NON-SCIENTIFIC explanation",
            disorder=self.disorder)
        StudyActivity.objects.create(user=self.owner, activity_type=StudyActivity.Kind.DISORDER_VIEW,
            disorder=self.disorder)
        self.state = self.anchor("disorder", self.disorder)

    def anchor(self, kind, obj):
        state = ContentState.objects.create(kind=kind, canonical_pk=obj.pk, legacy_origin=True,
            canonical_digest=content.digest(content.canonical_snapshot(kind, obj)), publication="current")
        payload = content.editable_snapshot(kind, obj)
        revision = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
            base_digest=state.canonical_digest, payload=payload, payload_digest=content.digest(payload),
            dependency_digest=content.dependencies(kind, obj), status="legacy")
        state.current_revision = revision
        state.save(update_fields=("current_revision",))
        return state

    def impact(self, client=None):
        return (client or self.client).get(BASE + f"content/disorder/{self.state.pk}/archive-impact/")

    def relations(self, data):
        return {(row["model"], row["field"]): row for row in data["relations"]}

    def test_live_orm_counts_and_on_delete_classes(self):
        response = self.impact()
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        rows = self.relations(data)
        self.assertEqual(rows[("atlas.disordersymptom", "disorder")]["count"], 1)
        self.assertEqual(rows[("atlas.disorderconcept", "disorder")]["count"], 1)
        self.assertEqual(rows[("atlas.bookmark", "disorder")]["count"], 1)
        self.assertEqual(rows[("atlas.quiz", "disorder")]["count"], 1)
        self.assertEqual(rows[("atlas.clinicalcase", "primary_disorder")]["count"], 1)
        self.assertEqual(rows[("atlas.flashcard", "disorder")]["count"], 1)
        self.assertEqual(rows[("atlas.dailychallenge", "disorder")]["count"], 1)
        self.assertEqual(rows[("atlas.studyactivity", "disorder")]["count"], 1)
        self.assertEqual(rows[("atlas.bookmark", "disorder")]["impact"], "cascade")
        self.assertEqual(rows[("atlas.quiz", "disorder")]["impact"], "detach")
        self.assertEqual(rows[("atlas.studyblock", "disorder")]["impact"], "protect")
        self.assertEqual(data["totals"]["rows"], sum(row["count"] for row in data["relations"]))
        self.assertGreaterEqual(data["totals"]["relations"], 8)
        self.assertEqual((data["canonical_write"], data["raw_archive_changed"]), (0, False))
        self.assertEqual(data["search_graph"], "computed_at_read_time")
        self.assertEqual(len(data["impact_digest"]), 64)
        self.assertEqual(data["impact_digest"], self.impact().json()["impact_digest"])

    def test_impact_is_read_only_and_digest_changes_with_new_dependency(self):
        before = [list(model.objects.order_by("pk").values()) for model in
            (Disorder, ContentState, ContentRevision, AdminAuditEvent)]
        first = self.impact().json()
        self.assertEqual([list(model.objects.order_by("pk").values()) for model in
            (Disorder, ContentState, ContentRevision, AdminAuditEvent)], before)
        Bookmark.objects.create(user=self.staff, disorder=self.disorder)
        second = self.impact().json()
        self.assertEqual(self.relations(second)[("atlas.bookmark", "disorder")]["count"], 2)
        self.assertNotEqual(first["impact_digest"], second["impact_digest"])

    def test_archive_intent_keeps_canonical_and_dependency_counts(self):
        before = list(Disorder.objects.order_by("pk").values())
        first = self.impact().json()
        state = content.archive_proposal(self.owner.pk, self.client.session["cms_session_id"], "disorder",
            str(self.state.pk), self.state.version, uuid.uuid4())
        self.assertEqual(state.current_revision.intent, "archive")
        second = self.impact().json()
        self.assertEqual(list(Disorder.objects.order_by("pk").values()), before)
        self.assertEqual(self.relations(first)[("atlas.bookmark", "disorder")]["count"],
            self.relations(second)[("atlas.bookmark", "disorder")]["count"])
        self.assertEqual(second["content_state"]["intent"], "archive")

    def test_permissions_and_cross_domain_fail_closed(self):
        reader = self.user("non-scientific-p07-impact-view", staff=True, caps=("cms_enter", "cms_core_view"))
        client = self.sign_in(reader)
        self.assertEqual(self.impact(client=client).status_code, 403)
        self.grant(reader, "cms_core_preview")
        self.assertEqual(self.impact(client=client).status_code, 200)
        dsm = self.user("non-scientific-p07-impact-dsm", staff=True,
            caps=("cms_enter", "cms_dsm_view", "cms_dsm_preview"))
        self.assertEqual(self.impact(client=self.sign_in(dsm)).status_code, 403)
        self.assertEqual(self.client.get(BASE + f"content/disorder/{self.state.pk}/archive-impact/?q=x").status_code, 400)
        self.assertEqual(self.client.get(BASE + "content/not-a-kind/1/archive-impact/").status_code, 404)
