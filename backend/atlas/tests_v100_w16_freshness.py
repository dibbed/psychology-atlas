"""Turn 08 W16-00: semantic dependency drift must invalidate private dossiers."""
import uuid

from django.test import TestCase, override_settings

from .cms_learning_fingerprint import draft_fingerprint
from .cms_publication_preparation_models import PublicationPreparationDossier
from .models import (
    CognitiveDistortionPracticeChoice, CognitiveDistortionPracticeItem,
    Concept, StudyActivity, UserConceptProgress,
)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningPublicationFreshnessTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.target = Concept.objects.create(
            slug="w16-target", name_en="Synthetic target",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, is_active=True,
        )
        self.alternative = Concept.objects.create(
            slug="w16-alternative", name_en="Synthetic alternative",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, is_active=True,
        )
        self.practice = CognitiveDistortionPracticeItem.objects.create(
            slug="w16-private-practice", prompt="Synthetic learning prompt",
            explanation="Synthetic explanation", target_concept=self.target,
            is_active=False, seed_managed=False,
        )
        CognitiveDistortionPracticeChoice.objects.create(
            item=self.practice, concept=self.target, text="Target",
            is_correct=True, is_active=True,
        )
        CognitiveDistortionPracticeChoice.objects.create(
            item=self.practice, concept=self.alternative, text="Alternative",
            is_correct=False, is_active=True,
        )

    def _prepared(self):
        candidate = self.client.get(BASE + "publication/preflight/?domain=learning")
        self.assertEqual(candidate.status_code, 200)
        row = next(row for row in candidate.json()["results"]
                   if row["kind"] == "distortion_practice" and
                   row["resource_id"] == self.practice.pk)
        self.assertEqual(row["content_issues"], [])
        selected = self.post(self.client, "publication/selections/", {
            "domain": "learning", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": "distortion_practice", "resource_id": self.practice.pk,
                         "expected_digest": row["content_digest"]}],
        })
        self.assertEqual(selected.status_code, 201, selected.content[:300])
        selection = selected.json()
        prepared = self.post(self.client,
            f'publication/selections/{selection["id"]}/prepare/', {
            "request_key": str(uuid.uuid4()),
            "selection_digest": selection["selection_digest"],
        })
        self.assertEqual(prepared.status_code, 201, prepared.content[:300])
        return selection, prepared.json()

    def test_target_subtype_drift_without_timestamp_stales_dossier_and_blocks_reprepare(self):
        selected, prepared = self._prepared()
        before_timestamp = Concept.objects.get(pk=self.target.pk).updated_at
        original_digest = draft_fingerprint("distortion_practice", self.practice)["content_digest"]
        Concept.objects.filter(pk=self.target.pk).update(subtype=Concept.Subtype.GENERAL)
        self.assertEqual(Concept.objects.get(pk=self.target.pk).updated_at, before_timestamp)
        after = draft_fingerprint("distortion_practice", self.practice)
        self.assertNotEqual(after["content_digest"], original_digest)
        self.assertIn("TARGET_INVALID", after["content_issues"])
        verified = self.client.get(
            BASE + f'publication/preparations/{prepared["id"]}/verify/')
        self.assertEqual(verified.status_code, 200)
        self.assertFalse(verified.json()["snapshot_current"])
        self.assertEqual(verified.json()["recheck_summary"]["snapshot_counts"]["stale"], 1)
        failed = self.post(self.client,
            f'publication/selections/{selected["id"]}/prepare/', {
            "request_key": str(uuid.uuid4()),
            "selection_digest": selected["selection_digest"],
        })
        self.assertEqual(failed.status_code, 409)
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)
        self.assertFalse(StudyActivity.objects.exists())
        self.assertFalse(UserConceptProgress.objects.exists())

    def test_active_option_subtype_and_availability_invalidate_preparation(self):
        for changed in ("subtype", "is_active"):
            with self.subTest(changed=changed):
                selected, prepared = self._prepared()
                old = draft_fingerprint("distortion_practice", self.practice)["content_digest"]
                if changed == "subtype":
                    Concept.objects.filter(pk=self.alternative.pk).update(
                        subtype=Concept.Subtype.GENERAL)
                else:
                    Concept.objects.filter(pk=self.alternative.pk).update(is_active=False)
                result = draft_fingerprint("distortion_practice", self.practice)
                self.assertNotEqual(result["content_digest"], old)
                self.assertIn("CHOICE_CONCEPT_INVALID", result["content_issues"])
                verified = self.client.get(
                    BASE + f'publication/preparations/{prepared["id"]}/verify/')
                self.assertEqual(verified.status_code, 200)
                self.assertFalse(verified.json()["snapshot_current"])
                Concept.objects.filter(pk=self.alternative.pk).update(
                    is_active=True, subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        self.assertFalse(StudyActivity.objects.exists())
