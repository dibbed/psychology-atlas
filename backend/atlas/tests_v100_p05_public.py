"""Public consumer regressions; governance decisions are owned by P05 integration tests.

The eligibility stub represents the frozen governance API at the consumer boundary.
It deliberately never grants scientific review, form authorization or legacy access.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from . import models as m
from .brain_publication import public_sources, resolved_sources, source_is_resolved
from .cms_governance_models import GovernanceRecord
from .cms_public_rights import public_rights, public_visible
from .cms_source_models import SourceState
from .tests_v092_brain_api import BrainFixtureMixin
from .tests_v094_assessments import CuratedFixture
from .tests_v100_p01 import SecurityFixture


def scope(kind, obj, material="metadata", use="public_display"):
    return GovernanceRecord.objects.create(kind="rights", domain="core", resource_type=kind,
        resource_id=obj.pk, resource_version="synthetic-consumer-version", material=material,
        intended_use=use, status="revoked")


class PublicConsumerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.category = m.Category.objects.create(slug="public-fixture", name_en="Fixture")
        self.disorder = m.Disorder.objects.create(category=self.category, slug="fixture-disorder", name_en="Fixture Disorder")
        self.concept = m.Concept.objects.create(slug="fixture-concept", name_en="Fixture Concept", simple_definition="Fixture text")
        m.DisorderConcept.objects.create(disorder=self.disorder, concept=self.concept)
        self.eligibility = patch("atlas.cms_public_rights._eligible", return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_flashcard_item_revocation_redacts_real_fields_and_denies_review_without_srs_write(self):
        card = m.Flashcard.objects.create(slug="non-scientific-rights-card", concept=self.concept,
            front="NON-SCIENTIFIC PRIVATE FRONT", back="NON-SCIENTIFIC PRIVATE BACK", hint="NON-SCIENTIFIC PRIVATE HINT")
        user = User.objects.create(username="synthetic-card-learner")
        self.client.force_authenticate(user)
        scope("flashcard", card, "item")
        response = self.client.get("/api/flashcards/")
        row = response.data["results"][0]
        self.assertEqual((row["front"], row["back"], row["hint"]), ("", "", ""))
        self.assertEqual(row["slug"], card.slug)
        self.assertNotIn("PRIVATE", str(response.data))
        self.assertEqual(self.client.post(f"/api/flashcards/{card.slug}/review/", {"rating": "good"}, format="json").status_code, 404)
        self.assertFalse(m.UserFlashcardProgress.objects.filter(user=user).exists())
        self.assertFalse(m.StudyActivity.objects.filter(user=user).exists())

    def test_quiz_item_revocation_preserves_metadata_but_denies_questions_and_feedback(self):
        quiz = m.Quiz.objects.create(slug="non-scientific-rights-quiz", title="NON-SCIENTIFIC Quiz", disorder=self.disorder)
        question = m.QuizQuestion.objects.create(quiz=quiz, prompt="NON-SCIENTIFIC PRIVATE PROMPT")
        m.QuizChoice.objects.create(question=question, text="NON-SCIENTIFIC PRIVATE CHOICE", is_correct=True)
        user = User.objects.create(username="synthetic-quiz-learner")
        self.client.force_authenticate(user)
        scope("quiz", quiz, "item")
        detail = self.client.get(f"/api/quizzes/{quiz.slug}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["questions"], [])
        self.assertNotIn("PRIVATE", str(detail.data))
        self.assertEqual(self.client.post(f"/api/quizzes/{quiz.slug}/submit/", {"answers": []}, format="json").status_code, 404)
        self.assertFalse(m.QuizAttempt.objects.filter(user=user).exists())

    def test_case_item_revocation_blocks_resumed_step_and_decision_without_destroying_attempt(self):
        case = m.ClinicalCase.objects.create(slug="non-scientific-rights-case", title="NON-SCIENTIFIC Case", structure_mode="branching")
        revision = m.CaseRevision.objects.create(case=case, version=1, status="published", title=case.title)
        step = m.CaseStep.objects.create(case=case, revision=revision, stable_key="terminal", node_kind="information",
            title="NON-SCIENTIFIC PRIVATE STEP", narrative="NON-SCIENTIFIC PRIVATE NARRATIVE", sort_order=1)
        m.CaseTransition.objects.create(revision=revision, source_step=step, outcome="complete")
        revision.entry_step = step
        revision.save()
        case.current_revision = revision
        case.save()
        user = User.objects.create(username="synthetic-case-learner")
        self.client.force_authenticate(user)
        started = self.client.post(f"/api/cases/{case.slug}/attempts/", {}, format="json")
        self.assertEqual(started.status_code, 201, started.data)
        attempt_id = started.data["id"]
        before = m.CaseAttempt.objects.filter(pk=attempt_id).values().get()
        scope("clinical_case", case, "item")
        self.assertEqual(self.client.get(f"/api/cases/{case.slug}/").status_code, 200)
        for path in (f"/api/cases/{case.slug}/attempts/current/", f"/api/case-attempts/{attempt_id}/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("PRIVATE", str(response.data))
        self.assertEqual(self.client.post(f"/api/cases/{case.slug}/attempts/", {}, format="json").status_code, 404)
        self.assertEqual(self.client.post(f"/api/case-attempts/{attempt_id}/decisions/",
            {"step_id": step.pk, "state_version": 0, "choice_id": None}, format="json").status_code, 404)
        self.assertEqual(before, m.CaseAttempt.objects.filter(pk=attempt_id).values().get())
        self.assertFalse(m.CaseAttemptEvent.objects.filter(attempt_id=attempt_id).exists())

    def test_revoked_metadata_agrees_across_list_detail_search_graph_and_nested(self):
        scope("disorder", self.disorder)
        self.assertEqual(self.client.get("/api/disorders/").data["count"], 0)
        self.assertEqual(self.client.get("/api/disorders/fixture-disorder/").status_code, 404)
        self.assertEqual(self.client.get("/api/search/", {"q": "Fixture Disorder"}).data["disorders"], [])
        graph = self.client.get("/api/concept-map/").data
        self.assertNotIn("disorder:fixture-disorder", {node["id"] for node in graph["nodes"]})
        self.assertTrue(all("disorder:fixture-disorder" not in (edge["source"], edge["target"]) for edge in graph["edges"]))
        detail = self.client.get("/api/concepts/fixture-concept/").data
        self.assertEqual(detail["disorders"], [])

    def test_item_translation_and_other_use_scopes_leave_metadata_visible(self):
        for material, use in (("item", "public_display"), ("translation", "public_display"), ("metadata", "owner_access")):
            with self.subTest(material=material, use=use):
                scope("disorder", self.disorder, material, use)
                self.assertEqual(self.client.get("/api/disorders/").data["count"], 1)
                self.assertEqual(self.client.get("/api/disorders/fixture-disorder/").status_code, 200)
                self.assertEqual(len(self.client.get("/api/search/", {"q": "Fixture Disorder"}).data["disorders"]), 1)
                self.assertIn("disorder:fixture-disorder", {node["id"] for node in self.client.get("/api/concept-map/").data["nodes"]})

    def test_legacy_never_invokes_eligibility_and_preserves_inactive_gate(self):
        self.assertEqual(self.client.get("/api/disorders/").data["count"], 1)
        self.eligibility.assert_not_called()
        self.disorder.is_active = False
        self.disorder.save()
        self.assertEqual(self.client.get("/api/disorders/fixture-disorder/").status_code, 404)

    def test_nested_symptom_and_category_metadata_do_not_leak(self):
        symptom = m.Symptom.objects.create(slug="private-symptom", name_en="Private Symptom")
        m.DisorderSymptom.objects.create(disorder=self.disorder, symptom=symptom)
        scope("symptom", symptom)
        scope("category", self.category)
        detail = self.client.get("/api/disorders/fixture-disorder/").data
        self.assertEqual(detail["symptoms"], [])
        self.assertIsNone(detail["category"])
        self.assertIsNone(detail["category_slug"])
        graph = self.client.get("/api/concept-map/").data
        self.assertNotIn("symptom:private-symptom", {node["id"] for node in graph["nodes"]})

    def test_source_lifecycle_overlay_keeps_scientific_resolution_unchanged(self):
        source = m.SourceReference.objects.create(title="Private Source", citation="Synthetic checked citation",
            url="https://example.org/checked", verification_status="source_checked")
        m.DisorderSource.objects.create(disorder=self.disorder, source=source)
        for state_field in ("archived", "deleted"):
            with self.subTest(state=state_field):
                state, _ = SourceState.objects.get_or_create(source_pk=source.pk)
                setattr(state, state_field, True)
                state.save()
                self.assertTrue(source_is_resolved(source))
                self.assertTrue(resolved_sources().filter(pk=source.pk).exists())
                self.assertFalse(public_sources().filter(pk=source.pk).exists())
                self.assertEqual(self.client.get("/api/disorders/fixture-disorder/").data["sources"], [])

    def test_source_metadata_rights_apply_without_changing_resolution(self):
        source = m.SourceReference.objects.create(title="Denied Source", citation="Synthetic checked citation",
            url="https://example.org/denied", verification_status="source_checked")
        m.DisorderSource.objects.create(disorder=self.disorder, source=source)
        scope("source_reference", source)
        self.assertTrue(source_is_resolved(source))
        self.assertTrue(resolved_sources().filter(pk=source.pk).exists())
        self.assertEqual(self.client.get("/api/disorders/fixture-disorder/").data["sources"], [])

    def test_dsm_metadata_is_hidden_in_nested_detail_and_graph(self):
        corpus = m.DSMCorpus.objects.create(key="fixture-dsm", title="Synthetic DSM")
        parent = m.DSMRecord.objects.create(corpus=corpus, master_id="parent", name_en="DSM Parent")
        child = m.DSMRecord.objects.create(corpus=corpus, master_id="child", name_en="DSM Child", parent=parent)
        scope("dsm_record", child)
        self.assertEqual(self.client.get("/api/dsm/records/child/").status_code, 404)
        self.assertEqual(self.client.get("/api/dsm/records/parent/").data["children"], [])
        self.assertNotIn("child", {node["id"] for node in self.client.get("/api/dsm/graph/").data["nodes"]})


class BrainPublicConsumerTests(BrainFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.eligibility = patch("atlas.cms_public_rights._eligible", return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_revoked_ancestor_hides_descendants_and_preserves_review(self):
        scope("brain_anatomical_entity", self.root)
        self.assertEqual(self.client.get("/api/brain-anatomy/").data["count"], 0)
        self.assertEqual(self.client.get("/api/brain-anatomy/fixture-child/").status_code, 404)
        self.assertEqual(self.client.get("/api/search/", {"q": "Fixture Child"}).data["brain_entities"], [])
        self.assertFalse(any(node["type"] == "brain_anatomy" for node in self.client.get("/api/concept-map/").data["nodes"]))
        self.root.refresh_from_db()
        self.assertEqual(self.root.review_status, "reviewed")

    def test_translation_denial_only_redacts_existing_translated_prose(self):
        self.child.review_status = "unreviewed"
        self.child.save()
        self.child.description_en = "Fixture English text"
        self.child.description_fa = "Fixture translated text"
        self.child.review_status = "reviewed"
        self.child.save()
        scope("brain_anatomical_entity", self.child, "translation")
        detail = self.client.get("/api/brain-anatomy/fixture-child/").data
        self.assertEqual(detail["name_fa"], self.child.name_fa)
        self.assertEqual(detail["description_en"], "Fixture English text")
        self.assertEqual(detail["description_fa"], "")
        self.assertEqual(self.client.get("/api/brain-anatomy/").data["count"], 2)


class AssessmentPublicConsumerTests(CuratedFixture, TestCase):
    def setUp(self):
        super().setUp()
        patch("atlas.cms_public_rights._eligible", return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_item_denial_keeps_instrument_and_exact_version_metadata(self):
        scope("assessment_version", self.version, "item")
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/").data
        self.assertIn(self.version.key, {row["key"] for row in detail["versions"]["results"]})
        self.form.refresh_from_db()
        self.assertEqual(self.form.authorization_status, "unknown")
        self.assertEqual(self.form.review_status, "reviewed")

    def test_access_material_use_denial_leaves_metadata_and_other_access(self):
        access = self.version.access_records.first()
        scope("assessment_access", access, access.material_type, access.use)
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/").data
        version = next(row for row in detail["versions"]["results"] if row["key"] == self.version.key)
        self.assertNotIn(access.key, {row["key"] for row in version["access"]["results"]})
        access.refresh_from_db()
        self.assertEqual(access.review_status, "reviewed")


class PublicGraphDateTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_cached_atlas_and_dsm_graph_expire_at_date_boundary_without_a_write(self):
        category = m.Category.objects.create(slug="date-fixture", name_en="Date fixture")
        disorder = m.Disorder.objects.create(category=category, slug="date-disorder", name_en="Date Disorder")
        corpus = m.DSMCorpus.objects.create(key="date-dsm", title="Date DSM")
        record = m.DSMRecord.objects.create(corpus=corpus, master_id="dated", name_en="Dated")
        scope("disorder", disorder)
        scope("dsm_record", record)
        today = date(2026, 10, 10)
        with patch("atlas.views.timezone.localdate", return_value=today), patch("atlas.cms_public_rights._eligible", return_value=True):
            self.assertIn("disorder:date-disorder", {row["id"] for row in self.client.get("/api/concept-map/").data["nodes"]})
            self.assertIn("dated", {row["id"] for row in self.client.get("/api/dsm/graph/").data["nodes"]})
            self.assertIsNotNone(cache.get("atlas_graph"))
        with patch("atlas.views.timezone.localdate", return_value=today + timedelta(days=1)), patch("atlas.cms_public_rights._eligible", return_value=False):
            self.assertNotIn("disorder:date-disorder", {row["id"] for row in self.client.get("/api/concept-map/").data["nodes"]})
            self.assertNotIn("dated", {row["id"] for row in self.client.get("/api/dsm/graph/").data["nodes"]})

    def test_source_transaction_preview_does_not_poison_shared_scope_cache(self):
        source = m.SourceReference.objects.create(title="Rollback fixture")
        with transaction.atomic():
            SourceState.objects.create(source_pk=source.pk, archived=True)
            self.assertFalse(public_visible(source))
            self.assertIsNone(cache.get("atlas_public_rights_scopes"))
            transaction.set_rollback(True)
        self.assertTrue(public_visible(source))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DecidedRightsPublicTests(SecurityFixture, TransactionTestCase):
    """Actual authenticated governance services and public HTTP readers, without eligibility stubs."""
    def setUp(self):
        super().setUp()
        from .cms_models import AdminSession
        from .cms_review_models import ReviewPolicy
        ReviewPolicy.objects.get_or_create(pk=1)
        self.editor = self.user("rights-editor", staff=True, caps=("cms_enter", "cms_core_view", "cms_core_edit"))
        self.sign_in(self.editor)
        self.sign_in(self.owner)
        self.editor_session = AdminSession.objects.get(user=self.editor).pk
        self.owner_session = AdminSession.objects.get(user=self.owner).pk
        category = m.Category.objects.create(slug="real-rights-category", name_en="Rights fixture")
        self.disorder = m.Disorder.objects.create(category=category, slug="real-rights-disorder", name_en="Real Rights Disorder")
        self.source = m.SourceReference.objects.create(title="Rights fixture evidence", citation="Synthetic rights evidence",
            url="https://example.org/rights", verification_status="source_checked")
        self.public = APIClient()

    def propose(self, status, material="metadata", use="public_display", expires_on=None,
                resource_type="disorder", resource=None):
        from .cms_governance import create_governance, resource_binding
        from django.utils import timezone
        resource = resource or self.disorder
        evidence = [{"source_id": self.source.pk, "locator": "Synthetic scope, test only"}]
        return create_governance(self.editor.pk, self.editor_session, "rights", {
            "resource_type": resource_type, "resource_id": resource.pk,
            "resource_version": resource_binding(resource_type, resource.pk)["resource_version"],
            "material": material, "intended_use": use, "status": status,
            "rightsholder": "Synthetic fixture holder", "holder_identification": "Synthetic holder evidence",
            "holder_evidence": evidence, "evidence": evidence, "public_access": "public",
            "reviewed_on": timezone.localdate().isoformat(), "effective_on": timezone.localdate().isoformat(),
            "expires_on": expires_on, "review_on": None, "limitations": "Synthetic exact scope only",
            "territory": "", "conflict_note": "", "reason": "CORRECTION_REQUIRED",
        }, "5cbe87e9-182f-47e6-a873-a6f222602fa0")

    def action(self, record, action, values):
        from .cms_governance import mutate_governance
        record.refresh_from_db()
        return mutate_governance(self.owner.pk, self.owner_session, "rights", record.pk, record.version,
            action, values, "5cbe87e9-182f-47e6-a873-a6f222602fa0")

    def approve(self, record):
        record = self.action(record, "assign", {"reviewer_id": self.owner.pk})
        return self.action(record, "decide", {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED", "self_review_ack": False})

    def assert_public(self, visible):
        self.assertEqual(self.public.get("/api/disorders/real-rights-disorder/").status_code, 200 if visible else 404)
        self.assertEqual(self.public.get("/api/disorders/").data["count"], int(visible))
        self.assertEqual(bool(self.public.get("/api/search/", {"q": "Real Rights Disorder"}).data["disorders"]), visible)
        self.assertEqual("disorder:real-rights-disorder" in {row["id"] for row in self.public.get("/api/concept-map/").data["nodes"]}, visible)

    def test_editor_pending_restricted_does_not_hide_but_approval_does(self):
        record = self.propose("restricted")
        self.assert_public(True)
        self.approve(record)
        self.assert_public(False)

    def test_pending_restricted_cannot_override_effective_allowed_and_revoke_hides(self):
        allowed = self.approve(self.propose("allowed"))
        self.propose("restricted")
        self.assert_public(True)
        self.action(allowed, "revoke", {"reason": "CORRECTION_REQUIRED"})
        self.assert_public(False)

    def test_approved_unknown_denies_without_any_scientific_grant(self):
        record = self.approve(self.propose("unknown"))
        from .cms_governance import resource_binding, rights_eligibility
        result = rights_eligibility("disorder", self.disorder.pk,
            resource_binding("disorder", self.disorder.pk)["resource_version"], "metadata", "public_display")
        self.assertTrue(result["registered"])
        self.assertFalse(result["permitted"])
        self.assert_public(False)

    def test_actual_approved_expiry_removes_cached_graph_without_write(self):
        from django.utils import timezone
        today = timezone.localdate()
        self.approve(self.propose("allowed", expires_on=today.isoformat()))
        self.assert_public(True)
        self.assertIsNotNone(cache.get("atlas_graph"))
        with patch("atlas.views.timezone.localdate", return_value=today + timedelta(days=1)):
            self.assert_public(False)

    def test_cached_graph_reviewer_permission_removal_denies_without_governance_write(self):
        self.approve(self.propose("allowed"))
        self.assert_public(True)
        self.assertIsNotNone(cache.get("atlas_graph"))
        self.owner.user_permissions.clear()
        self.assert_public(False)

    def test_revocation_is_observed_with_another_workers_stale_scope_and_graph_caches(self):
        record = self.approve(self.propose("allowed"))
        self.assert_public(True)
        old_graph, old_revision = cache.get("atlas_graph"), cache.get("atlas_graph_revision")
        self.action(record, "revoke", {"reason": "CORRECTION_REQUIRED"})
        # Restore a second worker's process-local cache, which receives no signals from this writer.
        cache.set("atlas_graph", old_graph)
        cache.set("atlas_graph_revision", old_revision)
        cache.set("atlas_public_rights_scopes", {"scopes": set(), "inactive_sources": set()})
        self.assert_public(False)

    def test_restricted_distortion_choice_is_not_disclosed_or_submittable(self):
        target = m.Concept.objects.create(slug="synthetic-rights-target", name_en="Synthetic target",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        visible = m.Concept.objects.create(slug="synthetic-rights-visible", name_en="Synthetic visible",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        hidden = m.Concept.objects.create(slug="synthetic-rights-hidden", name_en="PRIVATE SYNTHETIC CONCEPT",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        item = m.CognitiveDistortionPracticeItem.objects.create(slug="synthetic-rights-practice",
            prompt="Synthetic exercise", explanation="Synthetic explanation", target_concept=target)
        m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=target, text="Target", is_correct=True)
        m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=visible, text="Visible")
        denied = m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=hidden, text="Hidden")
        self.assertEqual(self.public.get("/api/cognitive-distortions/practice/").data["count"], 1)
        self.approve(self.propose("restricted", resource_type="concept", resource=hidden))
        response = self.public.get("/api/cognitive-distortions/practice/")
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("PRIVATE SYNTHETIC CONCEPT", str(response.data))
        self.assertNotIn(denied.pk, [choice["id"] for choice in response.data["items"][0]["choices"]])
        self.public.force_authenticate(self.normal)
        submit = self.public.post(f"/api/cognitive-distortions/practice/{item.slug}/submit/", {"choice_id": denied.pk}, format="json")
        self.assertEqual(submit.status_code, 404)
        self.assertFalse(m.CognitiveDistortionPracticeAttempt.objects.exists())
        self.assertFalse(m.StudyActivity.objects.exists())

    def test_distortion_submission_rechecks_rights_after_admission(self):
        from .views import _practice_item_queryset
        target = m.Concept.objects.create(slug="synthetic-race-target", name_en="Synthetic target",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        other = m.Concept.objects.create(slug="synthetic-race-other", name_en="Synthetic other",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        item = m.CognitiveDistortionPracticeItem.objects.create(slug="synthetic-race-practice",
            prompt="Synthetic exercise", explanation="Synthetic explanation", target_concept=target)
        correct = m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=target, text="Correct", is_correct=True)
        m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=other, text="Other")
        admitted = list(_practice_item_queryset())
        self.assertEqual(len(admitted), 1)
        self.approve(self.propose("restricted", resource_type="concept", resource=target))
        self.public.force_authenticate(self.normal)
        with patch("atlas.views._practice_item_queryset", return_value=admitted):
            response = self.public.post(f"/api/cognitive-distortions/practice/{item.slug}/submit/",
                                        {"choice_id": correct.pk}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(m.CognitiveDistortionPracticeAttempt.objects.exists())
        self.assertFalse(m.UserConceptProgress.objects.exists())
        self.assertFalse(m.StudyActivity.objects.exists())

    def test_distortion_submission_rechecks_selected_choice_after_admission(self):
        from .views import _practice_item_queryset
        target = m.Concept.objects.create(slug="synthetic-choice-race-target", name_en="Synthetic target",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        visible = m.Concept.objects.create(slug="synthetic-choice-race-visible", name_en="Synthetic visible",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        hidden = m.Concept.objects.create(slug="synthetic-choice-race-hidden", name_en="Synthetic hidden",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        item = m.CognitiveDistortionPracticeItem.objects.create(slug="synthetic-choice-race-practice",
            prompt="Synthetic exercise", explanation="Synthetic explanation", target_concept=target)
        m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=target, text="Correct", is_correct=True)
        m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=visible, text="Visible")
        denied = m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=hidden, text="Hidden")
        admitted = list(_practice_item_queryset())
        self.approve(self.propose("restricted", resource_type="concept", resource=hidden))
        self.public.force_authenticate(self.normal)
        with patch("atlas.views._practice_item_queryset", return_value=admitted):
            response = self.public.post(f"/api/cognitive-distortions/practice/{item.slug}/submit/",
                                        {"choice_id": denied.pk}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(m.CognitiveDistortionPracticeAttempt.objects.exists())
        self.assertFalse(m.UserConceptProgress.objects.exists())
        self.assertFalse(m.StudyActivity.objects.exists())

    @skipUnlessDBFeature("has_select_for_update")
    def test_distortion_submit_waits_for_concurrent_rights_restriction(self):
        import time
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import connection, connections, transaction
        from .views import _practice_item_queryset

        target = m.Concept.objects.create(slug="synthetic-pg-target", name_en="Synthetic target",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        other = m.Concept.objects.create(slug="synthetic-pg-other", name_en="Synthetic other",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        item = m.CognitiveDistortionPracticeItem.objects.create(slug="synthetic-pg-practice",
            prompt="Synthetic exercise", explanation="Synthetic explanation", target_concept=target)
        correct = m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=target, text="Correct", is_correct=True)
        m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=other, text="Other")
        admitted = list(_practice_item_queryset())
        self.assertEqual(len(admitted), 1)
        record = self.action(self.propose("restricted", resource_type="concept", resource=target),
                             "assign", {"reviewer_id": self.owner.pk})
        decision_saved, release_writer, reader_ready = Event(), Event(), Event()
        reader_pid = []

        def restrict():
            try:
                with transaction.atomic():
                    self.action(record, "decide", {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED", "self_review_ack": False})
                    decision_saved.set()
                    if not release_writer.wait(15):
                        raise TimeoutError("Synthetic rights writer timed out")
            finally:
                connections.close_all()

        def submit():
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    reader_pid.append(cursor.fetchone()[0])
                client = APIClient()
                client.force_authenticate(self.normal)
                reader_ready.set()
                return client.post(f"/api/cognitive-distortions/practice/{item.slug}/submit/",
                                   {"choice_id": correct.pk}, format="json").status_code
            finally:
                connections.close_all()

        with patch("atlas.views._practice_item_queryset", return_value=admitted):
            with ThreadPoolExecutor(max_workers=2) as pool:
                writer = pool.submit(restrict)
                try:
                    self.assertTrue(decision_saved.wait(10))
                    reader = pool.submit(submit)
                    self.assertTrue(reader_ready.wait(10))
                    observed_lock = False
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline and not reader.done():
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", reader_pid)
                            row = cursor.fetchone()
                        if row and row[0] == "Lock":
                            observed_lock = True
                            break
                        time.sleep(0.02)
                    self.assertTrue(observed_lock, "Submission did not wait for the rights decision")
                finally:
                    release_writer.set()
                writer.result(timeout=15)
                self.assertEqual(reader.result(timeout=15), 404)
        self.assertFalse(m.CognitiveDistortionPracticeAttempt.objects.exists())
        self.assertFalse(m.UserConceptProgress.objects.exists())
        self.assertFalse(m.StudyActivity.objects.exists())

    def test_restricted_distortion_target_hides_practice_and_denies_submit(self):
        target = m.Concept.objects.create(slug="synthetic-rights-denied-target", name_en="PRIVATE TARGET",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        other = m.Concept.objects.create(slug="synthetic-rights-other", name_en="Synthetic other",
            subtype=m.Concept.Subtype.COGNITIVE_DISTORTION, is_active=True)
        item = m.CognitiveDistortionPracticeItem.objects.create(slug="synthetic-rights-target-practice",
            prompt="Synthetic exercise", explanation="Synthetic explanation", target_concept=target)
        correct = m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=target, text="Correct", is_correct=True)
        m.CognitiveDistortionPracticeChoice.objects.create(item=item, concept=other, text="Other")
        self.assertEqual(self.public.get("/api/cognitive-distortions/practice/").data["count"], 1)
        self.approve(self.propose("restricted", resource_type="concept", resource=target))
        self.assertEqual(self.public.get("/api/cognitive-distortions/practice/").data["count"], 0)
        self.assertEqual(self.public.get("/api/cognitive-distortions/overview/").data["practice_count"], 0)
        self.public.force_authenticate(self.normal)
        self.assertEqual(self.public.post(f"/api/cognitive-distortions/practice/{item.slug}/submit/",
                                         {"choice_id": correct.pk}, format="json").status_code, 404)
        self.assertFalse(m.CognitiveDistortionPracticeAttempt.objects.exists())
        self.assertFalse(m.StudyActivity.objects.exists())

    def _daily_fixture(self, concept=None, disorder=None):
        challenge = m.DailyChallenge.objects.create(
            prompt="PRIVATE SYNTHETIC CHALLENGE", explanation="PRIVATE SYNTHETIC EXPLANATION",
            concept=concept, disorder=disorder,
        )
        right = m.DailyChallengeChoice.objects.create(
            challenge=challenge, text="Synthetic right", is_correct=True)
        m.DailyChallengeChoice.objects.create(
            challenge=challenge, text="Synthetic wrong", is_correct=False)
        return challenge, right

    def test_daily_restricted_concept_hides_anonymous_and_existing_attempt_without_erasure(self):
        target = m.Concept.objects.create(
            slug="daily-rights-target", name_en="PRIVATE SYNTHETIC CONCEPT",
            simple_definition="PRIVATE SYNTHETIC DEFINITION")
        challenge, right = self._daily_fixture(concept=target)
        self.assertEqual(self.public.get("/api/daily-challenge/").status_code, 200)
        self.public.force_authenticate(self.normal)
        first = self.public.post("/api/daily-challenge/", {"choice_id": right.pk}, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        historical = m.DailyChallengeAttempt.objects.get(user=self.normal, challenge=challenge)
        before = (historical.pk, historical.selected_choice_id, historical.is_correct)
        activity_count = m.StudyActivity.objects.count()
        self.approve(self.propose("restricted", resource_type="concept", resource=target))
        self.public.force_authenticate(user=None)
        anonymous = self.public.get("/api/daily-challenge/")
        self.assertEqual(anonymous.status_code, 404)
        self.assertNotIn("PRIVATE", str(anonymous.data))
        self.public.force_authenticate(self.normal)
        existing_get = self.public.get("/api/daily-challenge/")
        repeated_post = self.public.post("/api/daily-challenge/", {"choice_id": right.pk}, format="json")
        self.assertEqual(existing_get.status_code, 404)
        self.assertEqual(repeated_post.status_code, 404)
        self.assertNotIn("PRIVATE", str(existing_get.data) + str(repeated_post.data))
        historical.refresh_from_db()
        self.assertEqual(before, (historical.pk, historical.selected_choice_id, historical.is_correct))
        self.assertEqual(m.StudyActivity.objects.count(), activity_count)
        from .learning import today_challenge
        self.assertIsNone(today_challenge())

    def test_daily_restricted_disorder_denies_new_attempt_and_activity(self):
        challenge, right = self._daily_fixture(disorder=self.disorder)
        self.assertEqual(self.public.get("/api/daily-challenge/").status_code, 200)
        self.approve(self.propose("restricted", resource_type="disorder", resource=self.disorder))
        self.assertEqual(self.public.get("/api/daily-challenge/").status_code, 404)
        self.public.force_authenticate(self.normal)
        result = self.public.post("/api/daily-challenge/", {"choice_id": right.pk}, format="json")
        self.assertEqual(result.status_code, 404)
        self.assertFalse(m.DailyChallengeAttempt.objects.exists())
        self.assertFalse(m.StudyActivity.objects.exists())

    def test_daily_restricted_related_material_does_not_expose_nested_text(self):
        concept = m.Concept.objects.create(
            slug="daily-text-target", name_en="SYNTHETIC TEXT",
            simple_definition="PRIVATE SYNTHETIC DEFINITION")
        self._daily_fixture(concept=concept)
        self.approve(self.propose(
            "restricted", material="text", resource_type="concept", resource=concept))
        response = self.public.get("/api/daily-challenge/")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("PRIVATE", str(response.data))

    def test_daily_expired_rights_hide_content_and_prevent_new_learning_evidence(self):
        from django.utils import timezone
        today = timezone.localdate()
        concept = m.Concept.objects.create(slug="daily-expiry-target", name_en="Synthetic")
        challenge, choice = self._daily_fixture(concept=concept)
        self.approve(self.propose(
            "allowed", resource_type="concept", resource=concept,
            expires_on=today.isoformat()))
        self.assertEqual(self.public.get("/api/daily-challenge/").status_code, 200)
        with patch("atlas.views.timezone.localdate", return_value=today + timedelta(days=1)):
            anonymous = self.public.get("/api/daily-challenge/")
            self.assertEqual(anonymous.status_code, 404)
            self.public.force_authenticate(self.normal)
            denied = self.public.post(
                "/api/daily-challenge/", {"choice_id": choice.pk}, format="json")
            self.assertEqual(denied.status_code, 404)
        self.assertFalse(m.DailyChallengeAttempt.objects.exists())
        self.assertFalse(m.StudyActivity.objects.exists())
        self.assertFalse(m.UserConceptProgress.objects.exists())

    def test_daily_submit_rechecks_rights_after_admission_and_preserves_no_write(self):
        concept = m.Concept.objects.create(slug="daily-admitted-target", name_en="Synthetic")
        challenge, right = self._daily_fixture(concept=concept)
        from .learning import today_challenge
        admitted = today_challenge()
        self.assertEqual(admitted.pk, challenge.pk)
        self.approve(self.propose("restricted", resource_type="concept", resource=concept))
        self.public.force_authenticate(self.normal)
        with patch("atlas.views.today_challenge", return_value=admitted):
            response = self.public.post(
                "/api/daily-challenge/", {"choice_id": right.pk}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(m.DailyChallengeAttempt.objects.exists())
        self.assertFalse(m.StudyActivity.objects.exists())
        self.assertFalse(m.UserConceptProgress.objects.exists())

    def test_restricted_symptom_text_is_redacted_from_disorder_detail(self):
        symptom = m.Symptom.objects.create(slug="rights-symptom", name_en="Synthetic symptom",
                                           description="PRIVATE SYNTHETIC SYMPTOM TEXT")
        m.DisorderSymptom.objects.create(disorder=self.disorder, symptom=symptom)
        url = "/api/disorders/real-rights-disorder/"
        before = self.public.get(url)
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.data["symptoms"][0]["description"], symptom.description)
        self.approve(self.propose("restricted", material="text",
                                  resource_type="symptom", resource=symptom))
        after = self.public.get(url)
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.data["symptoms"][0]["slug"], symptom.slug)
        self.assertEqual(after.data["symptoms"][0]["description"], "")
        self.assertNotIn(symptom.description, str(after.data))

    def test_approved_item_restriction_does_not_hide_metadata(self):
        self.approve(self.propose("restricted", material="item"))
        self.assert_public(True)

    def test_changed_canonical_version_makes_metadata_rights_stale(self):
        self.approve(self.propose("allowed"))
        self.assert_public(True)
        self.disorder.short_description = "Changed canonical version"
        self.disorder.save()
        self.assert_public(False)
