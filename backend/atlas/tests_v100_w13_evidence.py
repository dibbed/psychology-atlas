"""W13-02 synthetic Learning source provenance, no scientific approval or learner writes."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from .cms_governance_models import GovernanceRecord
from .cms_learning_io import _selected_rows, _export_document
from .cms_case_editor import revision_etag
from .cms_policy import CMSFailure

from .cms_learning_evidence_models import LearningEvidenceRevision, LearningEvidenceSource
from .cms_source_models import SourceState
from .models import (
    Concept, Quiz, QuizQuestion, QuizAttempt, Flashcard, UserFlashcardProgress,
    DailyChallenge, DailyChallengeAttempt, DailyChallengeChoice,
    CognitiveDistortionPracticeItem, CognitiveDistortionPracticeChoice,
    CognitiveDistortionPracticeAttempt, QuizChoice, SourceReference, StudyActivity,
)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningEvidenceContractTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.sign_in(self.owner)
        self.source = SourceReference.objects.create(title="NON-SCIENTIFIC example source")
        self.quiz = Quiz.objects.create(slug="w13-evidence-quiz", title="Synthetic", is_active=False)
        self.question = QuizQuestion.objects.create(
            quiz=self.quiz, prompt="Synthetic question", explanation="Synthetic claim",
            is_active=True,
        )
        self.card = Flashcard.objects.create(
            slug="w13-evidence-card", front="Fictional prompt", back="Fictional explanation",
            is_active=False,
        )
        self.daily = DailyChallenge.objects.create(
            prompt="Fictional challenge", explanation="Fictional explanation",
            is_active=False,
        )
        concept = Concept.objects.create(
            slug="w13-evidence-concept", name_en="NON-SCIENTIFIC concept",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, simple_definition="Synthetic",
        )
        self.distortion = CognitiveDistortionPracticeItem.objects.create(
            slug="w13-evidence-practice", prompt="Synthetic prompt",
            explanation="Synthetic explanation", target_concept=concept,
            is_active=False,
        )

    def url(self, kind, pk):
        return BASE + f"learning/evidence/{kind}/{pk}/"

    def bind(self, kind, pk, sources=None, etag=None, client=None):
        client = client or self.admin
        if etag is None:
            etag = client.get(self.url(kind, pk))["ETag"]
        return self.post(client, f"learning/evidence/{kind}/{pk}/",
                         {"sources": sources if sources is not None else [
                             {"source_id": self.source.pk, "locator": "Synthetic claim location"}]},
                         etag=etag)

    def test_each_learning_family_has_private_claim_level_source_revision(self):
        baseline = (QuizAttempt.objects.count(), UserFlashcardProgress.objects.count(),
                    DailyChallengeAttempt.objects.count(),
                    CognitiveDistortionPracticeAttempt.objects.count(), StudyActivity.objects.count())
        for kind, item in (("quiz-question", self.question), ("flashcard", self.card),
                           ("daily", self.daily), ("distortions", self.distortion)):
            initial = self.admin.get(self.url(kind, item.pk))
            self.assertEqual(initial.status_code, 200, initial.content[:300])
            self.assertEqual(initial.json()["status"], "unlinked")
            response = self.bind(kind, item.pk, etag=initial["ETag"])
            self.assertEqual(response.status_code, 200, response.content[:400])
            data = response.json()
            self.assertEqual((data["revision"], data["status"], data["scientific_review"]),
                             (1, "source_attached_unreviewed", "unreviewed"))
            self.assertEqual(data["links"][0]["source_id"], self.source.pk)
            self.assertEqual((data["canonical_write"], data["learner_write"]), (0, 0))
            self.assertEqual(self.admin.get(self.url(kind, item.pk)).json()["revision"], 1)
        self.assertEqual(LearningEvidenceRevision.objects.count(), 4)
        self.assertEqual(LearningEvidenceSource.objects.count(), 4)
        self.assertEqual(baseline, (QuizAttempt.objects.count(), UserFlashcardProgress.objects.count(),
                         DailyChallengeAttempt.objects.count(),
                         CognitiveDistortionPracticeAttempt.objects.count(), StudyActivity.objects.count()))

    def test_replay_and_invalid_payload_fail_without_writes(self):
        first = self.admin.get(self.url("flashcard", self.card.pk))
        ok = self.bind("flashcard", self.card.pk, etag=first["ETag"])
        self.assertEqual(ok.status_code, 200, ok.content[:300])
        self.assertEqual(self.bind("flashcard", self.card.pk, etag=first["ETag"]).status_code, 412)
        invalid = self.bind("flashcard", self.card.pk,
                            sources=[{"source_id": self.source.pk, "locator": " " }])
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(LearningEvidenceRevision.objects.count(), 1)

    def test_source_drift_and_archive_are_visible_without_auto_review(self):
        self.assertEqual(self.bind("daily", self.daily.pk).status_code, 200)
        self.source.title = "NON-SCIENTIFIC changed source"
        self.source.save(update_fields=["title"])
        changed = self.admin.get(self.url("daily", self.daily.pk))
        self.assertEqual(changed.json()["status"], "requires_review")
        self.assertEqual(changed.json()["links"][0]["status"], "stale")
        self.daily.explanation = "Revised synthetic claim"
        self.daily.save(update_fields=["explanation"])
        updated = self.admin.get(self.url("daily", self.daily.pk))
        self.assertEqual(updated.json()["status"], "requires_review")
        self.assertEqual(self.bind("daily", self.daily.pk, etag=updated["ETag"]).status_code, 200)
        SourceState.objects.update_or_create(source_pk=self.source.pk, defaults={"archived": True})
        archived = self.admin.get(self.url("daily", self.daily.pk))
        self.assertEqual(archived.json()["links"][0]["status"], "restricted")
        self.assertEqual(self.bind("daily", self.daily.pk).status_code, 409)
        self.assertEqual(LearningEvidenceRevision.objects.count(), 2)

    def test_actor_without_source_capability_cannot_read_or_bind(self):
        limited = self.user("w13-evidence-limited", staff=True,
                            caps=("cms_enter", "cms_learning_view", "cms_learning_edit"))
        client = self.sign_in(limited)
        self.assertEqual(client.get(self.url("flashcard", self.card.pk)).status_code, 403)
        self.assertEqual(self.bind("flashcard", self.card.pk,
                                 etag='"1"', client=client).status_code, 403)
        self.assertFalse(LearningEvidenceRevision.objects.exists())

    def test_rights_revocation_redacts_scoped_source_locator_without_revision_rewrite(self):
        self.assertEqual(self.bind("daily", self.daily.pk).status_code, 200)
        GovernanceRecord.objects.create(
            kind="rights", domain="learning", resource_type="source_reference",
            resource_id=self.source.pk, resource_version="synthetic-restricted",
            material="item", intended_use="public_display", status="revoked",
        )
        cache.clear()
        with patch("atlas.cms_public_rights._eligible", return_value=False):
            response = self.admin.get(self.url("daily", self.daily.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "requires_review")
        self.assertEqual(data["links"][0]["status"], "restricted")
        self.assertIsNone(data["links"][0]["source_title"])
        self.assertIsNone(data["links"][0]["locator"])
        self.assertEqual(LearningEvidenceRevision.objects.count(), 1)

    def test_empty_explanation_cannot_be_attached_to_scientific_source(self):
        self.daily.explanation = ""
        self.daily.save(update_fields=["explanation"])
        self.assertEqual(self.bind("daily", self.daily.pk).status_code, 409)
        self.assertFalse(LearningEvidenceRevision.objects.exists())

    def test_transfer_refuses_current_citations_in_all_four_families(self):
        cases = (
            ("quiz", self.quiz, "quiz-question", self.question),
            ("flashcard", self.card, "flashcard", self.card),
            ("daily", self.daily, "daily", self.daily),
            ("distortions", self.distortion, "distortions", self.distortion),
        )
        for kind, item, evidence_kind, target in cases:
            with self.subTest(kind=kind):
                selection = [{"kind": kind, "resource_id": item.pk,
                              "etag": str(revision_etag(item))}]
                authorized_rows = _selected_rows(selection)
                self.assertEqual(len(authorized_rows), 1)
                self.assertEqual(self.bind(evidence_kind, target.pk).status_code, 200)
                with self.assertRaises(CMSFailure) as preflight:
                    _selected_rows(selection)
                self.assertEqual(preflight.exception.detail["code"],
                                 "LEARNING_EVIDENCE_TRANSFER_UNSUPPORTED")
                with self.assertRaises(CMSFailure) as worker:
                    _export_document(authorized_rows)
                self.assertEqual(worker.exception.detail["code"],
                                 "LEARNING_EVIDENCE_TRANSFER_UNSUPPORTED")
        self.assertEqual(LearningEvidenceRevision.objects.count(), 4)
        self.assertEqual(LearningEvidenceSource.objects.count(), 4)

    def test_explicit_source_detachment_makes_content_transferable_without_deleting_history(self):
        self.assertEqual(self.bind("flashcard", self.card.pk).status_code, 200)
        etag = self.admin.get(self.url("flashcard", self.card.pk))["ETag"]
        self.assertEqual(self.post(self.admin, f"learning/evidence/flashcard/{self.card.pk}/",
            {"sources": [], "change_reason": "Synthetic explicit withdrawal"}, etag=etag).status_code, 200)
        selection = [{"kind": "flashcard", "resource_id": self.card.pk,
                      "etag": str(revision_etag(self.card))}]
        exported = _export_document(_selected_rows(selection))
        self.assertIn(b"psychology-atlas-learning-authoring-v1", exported)
        self.assertEqual(LearningEvidenceRevision.objects.count(), 2)
        self.assertEqual(LearningEvidenceSource.objects.count(), 1)
        self.assertEqual(self.admin.get(self.url("flashcard", self.card.pk)).json()["status"],
                         "unlinked")

    def test_active_or_history_protected_learning_cannot_rebind(self):
        self.card.is_active = True
        self.card.save(update_fields=["is_active"])
        self.assertEqual(self.bind("flashcard", self.card.pk).status_code, 409)
        self.assertFalse(LearningEvidenceRevision.objects.exists())

    def test_old_quiz_question_evidence_not_silently_transferred(self):
        self.assertEqual(self.bind("quiz-question", self.question.pk).status_code, 200)
        old = self.question.pk
        self.question.delete()
        replacement = QuizQuestion.objects.create(
            quiz=self.quiz, prompt="Replacement", explanation="Different claim", is_active=True)
        self.assertEqual(self.admin.get(self.url("quiz-question", old)).status_code, 404)
        self.assertEqual(self.admin.get(self.url("quiz-question", replacement.pk)).json()["status"], "unlinked")
        self.assertEqual(LearningEvidenceRevision.objects.count(), 1)
        self.assertEqual(LearningEvidenceSource.objects.count(), 1)

    def test_claim_context_mutations_invalidate_attached_sources(self):
        QuizChoice.objects.create(question=self.question, text="a", is_correct=True)
        alternate = QuizChoice.objects.create(question=self.question, text="b", is_correct=False)
        for kind, item in (("quiz-question", self.question),
                           ("flashcard", self.card), ("daily", self.daily),
                           ("distortions", self.distortion)):
            with self.subTest(kind=kind):
                if kind == "daily":
                    DailyChallengeChoice.objects.create(challenge=item, text="one", is_correct=True)
                    DailyChallengeChoice.objects.create(challenge=item, text="two", is_correct=False)
                if kind == "distortions":
                    CognitiveDistortionPracticeChoice.objects.create(
                        item=item, concept=item.target_concept, text="one", is_correct=True)
                self.assertEqual(self.bind(kind, item.pk).status_code, 200)
                before = self.admin.get(self.url(kind, item.pk))
                self.assertEqual(before.json()["status"], "source_attached_unreviewed")
                if kind == "quiz-question":
                    item.prompt = "New prompt, same explanation"
                    item.save(update_fields=["prompt"])
                elif kind == "flashcard":
                    item.front = "New front, same back"
                    item.save(update_fields=["front"])
                elif kind == "daily":
                    item.prompt = "New daily prompt, same explanation"
                    item.save(update_fields=["prompt"])
                else:
                    item.prompt = "New practice prompt, same explanation"
                    item.save(update_fields=["prompt"])
                changed = self.admin.get(self.url(kind, item.pk))
                self.assertEqual(changed.json()["status"], "requires_review")
                self.assertNotEqual(changed["ETag"], before["ETag"])
        self.question.prompt = "Synthetic question"
        self.question.save(update_fields=["prompt"])
        previous = self.admin.get(self.url("quiz-question", self.question.pk))
        self.assertEqual(self.bind("quiz-question", self.question.pk).status_code, 200)
        alternate.is_correct = True
        alternate.save(update_fields=["is_correct"])
        self.assertEqual(self.admin.get(self.url("quiz-question", self.question.pk)).json()["status"],
                         "requires_review")

    def test_legacy_explanation_only_fingerprint_requires_manual_recheck(self):
        # A 0059-era row has only the explanation digest. Construct an immutable
        # legacy fixture without bypassing append-only update protections.
        revision = LearningEvidenceRevision.objects.create(
            kind="flashcard", target_pk=self.card.pk, sequence=1,
            fingerprint_version="claim-text-v1", content_digest="0" * 64,
            actor=self.owner,
        )
        LearningEvidenceSource.objects.create(
            revision=revision, source=self.source,
            locator="Original synthetic claim", source_digest="0" * 64,
        )
        response = self.admin.get(self.url("flashcard", self.card.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "requires_review")
        self.assertEqual(self.bind("flashcard", self.card.pk, etag=response["ETag"]).status_code, 200)
        self.assertEqual(LearningEvidenceRevision.objects.count(), 2)
        self.assertEqual(LearningEvidenceRevision.objects.order_by("sequence").first().content_digest, "0" * 64)

    def test_concept_dependency_subtype_drift_marks_evidence_stale(self):
        self.assertEqual(self.bind("distortions", self.distortion.pk).status_code, 200)
        original = self.admin.get(self.url("distortions", self.distortion.pk))
        concept = self.distortion.target_concept
        concept.subtype = Concept.Subtype.GENERAL
        concept.save(update_fields=["subtype"])
        changed = self.admin.get(self.url("distortions", self.distortion.pk))
        self.assertEqual(changed.json()["status"], "requires_review")
        self.assertNotEqual(changed["ETag"], original["ETag"])

    def test_real_governance_restriction_redacts_read_and_blocks_new_binding(self):
        from django.utils import timezone
        from .cms_governance import resource_binding
        from .cms_review_models import ReviewPolicy
        ReviewPolicy.objects.get_or_create(pk=1)
        self.assertEqual(self.bind("flashcard", self.card.pk).status_code, 200)
        source_version = resource_binding("source_reference", self.source.pk)["resource_version"]
        evidence_source = SourceReference.objects.create(title="NON-SCIENTIFIC rights evidence")
        evidence = [{"source_id": evidence_source.pk, "locator": "Synthetic rights decision only"}]
        request = {
            "resource_type": "source_reference", "resource_id": self.source.pk,
            "resource_version": source_version, "material": "metadata",
            "intended_use": "public_display", "status": "restricted",
            "rightsholder": "NON-SCIENTIFIC fixture holder",
            "holder_identification": "No real rights grant",
            "holder_evidence": evidence, "public_access": "unknown",
            "evidence": evidence, "reviewed_on": timezone.localdate().isoformat(),
            "effective_on": timezone.localdate().isoformat(), "expires_on": None,
            "review_on": None, "limitations": "Synthetic tests only",
            "territory": "", "conflict_note": "", "reason": "CORRECTION_REQUIRED",
        }
        created = self.post(self.admin, "governance/rights/", request)
        self.assertEqual(created.status_code, 201, created.content[:500])
        row = created.json()["record"]
        for action, values in (
            ("assign", {"reviewer_id": self.owner.pk}),
            ("decide", {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED",
                         "self_review_ack": True}),
        ):
            result = self.post(self.admin, f"governance/rights/{row['id']}/{action}/", values,
                               etag=f'"{row["version"]}"')
            self.assertEqual(result.status_code, 200, result.content[:500])
            row = result.json()["record"]
        from django.core.cache import cache
        cache.clear()
        detail = self.admin.get(self.url("flashcard", self.card.pk))
        self.assertEqual(detail.status_code, 200, detail.content[:400])
        link = detail.json()["links"][0]
        self.assertEqual(link["status"], "restricted")
        self.assertIsNone(link["locator"])
        self.assertIsNone(link["source_title"])
        self.assertEqual(self.bind("flashcard", self.card.pk, etag=detail["ETag"]).status_code, 409)
        history = self.admin.get(self.url("flashcard", self.card.pk) + "history/")
        self.assertEqual(history.status_code, 200)
        self.assertIsNone(history.json()["revisions"][0]["links"][0]["locator"])

    def test_repeated_identical_revision_does_not_create_extra_history(self):
        first = self.bind("flashcard", self.card.pk)
        self.assertEqual(first.status_code, 200)
        replay = self.bind("flashcard", self.card.pk, etag=first["ETag"])
        self.assertEqual(replay.status_code, 200, replay.content[:400])
        self.assertEqual(LearningEvidenceRevision.objects.count(), 1)

    def test_source_removal_requires_a_real_reason_and_keeps_history(self):
        self.assertEqual(self.bind("flashcard", self.card.pk).status_code, 200)
        etag = self.admin.get(self.url("flashcard", self.card.pk))["ETag"]
        attempt = self.post(self.admin, f"learning/evidence/flashcard/{self.card.pk}/",
                            {"sources": [], "change_reason": "  "}, etag=etag)
        self.assertEqual(attempt.status_code, 400, attempt.content[:300])
        self.assertEqual(LearningEvidenceRevision.objects.count(), 1)

    def test_history_reuses_source_and_context_state_across_revisions(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        first = self.bind("flashcard", self.card.pk, sources=[
            {"source_id": self.source.pk, "locator": "Synthetic revision 0"}])
        self.assertEqual(first.status_code, 200)
        with CaptureQueriesContext(connection) as first_queries:
            initial = self.admin.get(self.url("flashcard", self.card.pk) + "history/")
        self.assertEqual(initial.status_code, 200)
        for number in range(1, 12):
            response = self.bind("flashcard", self.card.pk, sources=[
                {"source_id": self.source.pk, "locator": f"Synthetic revision {number}"}])
            self.assertEqual(response.status_code, 200, response.content[:200])
        with CaptureQueriesContext(connection) as all_queries:
            history = self.admin.get(self.url("flashcard", self.card.pk) + "history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["revisions"]), 12)
        self.assertLess(len(all_queries) - len(first_queries), 25,
                        "Repeated revisions of one source must reuse current policy and source checks")

    def test_history_role_denial_cannot_disclose_old_locator(self):
        self.assertEqual(self.bind("flashcard", self.card.pk).status_code, 200)
        limited = self.user("w13-history-unprivileged", staff=True,
                            caps=("cms_enter", "cms_learning_view", "cms_learning_edit"))
        client = self.sign_in(limited)
        response = client.get(self.url("flashcard", self.card.pk) + "history/")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"Synthetic claim location", response.content)

    def test_revision_and_audit_are_atomic_if_audit_insert_fails(self):
        etag = self.admin.get(self.url("flashcard", self.card.pk))["ETag"]
        with patch("atlas.cms_learning_evidence.AdminAuditEvent.objects.create",
                   side_effect=RuntimeError("synthetic audit database failure")):
            with self.assertRaises(RuntimeError):
                self.bind("flashcard", self.card.pk, etag=etag)
        self.assertEqual(LearningEvidenceRevision.objects.count(), 0)
        self.assertEqual(LearningEvidenceSource.objects.count(), 0)

    def test_evidence_history_is_append_only_and_records_removal_reason(self):
        self.assertEqual(self.bind("flashcard", self.card.pk).status_code, 200)
        detached = self.post(self.admin, f"learning/evidence/flashcard/{self.card.pk}/",
            {"sources": [], "change_reason": "Evidence was withdrawn for further review"},
            etag=self.admin.get(self.url("flashcard", self.card.pk))["ETag"])
        self.assertEqual(detached.status_code, 200, detached.content[:400])
        response = self.admin.get(self.url("flashcard", self.card.pk) + "history/")
        self.assertEqual(response.status_code, 200, response.content[:400])
        revisions = response.json()["revisions"]
        self.assertEqual([row["revision"] for row in revisions], [1, 2])
        self.assertEqual(revisions[1]["removed_source_ids"], [self.source.pk])
        self.assertEqual(revisions[1]["change_reason"], "Evidence was withdrawn for further review")
        self.assertEqual(LearningEvidenceRevision.objects.count(), 2)
        self.assertEqual(LearningEvidenceSource.objects.count(), 1)
