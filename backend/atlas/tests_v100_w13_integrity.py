"""W13-01: synthetic F02 regression: mutable Concept dependencies never validate stale practice."""
from django.test import TestCase, override_settings

from .models import (
    Concept, CognitiveDistortionPracticeItem, CognitiveDistortionPracticeChoice,
    CognitiveDistortionPracticeAttempt, StudyActivity,
)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PracticeDependencyIntegrityTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.target = Concept.objects.create(
            slug="w13-integrity-target", name_en="NON-SCIENTIFIC target",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, simple_definition="Synthetic",
        )
        self.alternate = Concept.objects.create(
            slug="w13-integrity-alternate", name_en="NON-SCIENTIFIC alternate",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, simple_definition="Synthetic",
        )
        self.item = CognitiveDistortionPracticeItem.objects.create(
            slug="w13-integrity-item", prompt="NON-SCIENTIFIC scenario",
            explanation="NON-SCIENTIFIC explanation", target_concept=self.target,
            is_active=False, seed_managed=False,
        )
        self.correct = CognitiveDistortionPracticeChoice.objects.create(
            item=self.item, concept=self.target, text="Correct synthetic choice",
            is_correct=True, is_active=True, sort_order=0,
        )
        self.wrong = CognitiveDistortionPracticeChoice.objects.create(
            item=self.item, concept=self.alternate, text="Wrong synthetic choice",
            is_correct=False, is_active=True, sort_order=1,
        )

    def detail(self):
        return self.client.get(BASE + f"learning/practice/distortions/{self.item.pk}/")

    def simulate(self):
        return self.post(self.client,
            f"learning/practice/distortions/{self.item.pk}/simulate/",
            {"choice_id": self.correct.pk})

    def test_valid_baseline_and_no_learner_mutation(self):
        before = (CognitiveDistortionPracticeAttempt.objects.count(),
                  StudyActivity.objects.count())
        self.assertTrue(self.detail().json()["valid"])
        response = self.simulate()
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertTrue(response.json()["preview_only"])
        self.assertEqual(before, (CognitiveDistortionPracticeAttempt.objects.count(),
                                  StudyActivity.objects.count()))

    def test_deactivated_target_blocks_simulation_with_no_learning_writes(self):
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        self.assertIn("TARGET_INVALID", self.detail().json()["issues"])
        self.assertEqual(self.simulate().status_code, 409)
        self.assertFalse(CognitiveDistortionPracticeAttempt.objects.exists())

    def test_target_subtype_drift_blocks_simulation(self):
        self.target.subtype = Concept.Subtype.GENERAL
        self.target.save(update_fields=["subtype"])
        self.assertIn("TARGET_INVALID", self.detail().json()["issues"])
        self.assertEqual(self.simulate().status_code, 409)

    def test_alternative_subtype_drift_blocks_simulation(self):
        self.alternate.subtype = Concept.Subtype.GENERAL
        self.alternate.save(update_fields=["subtype"])
        self.assertIn("CHOICE_CONCEPT_INVALID", self.detail().json()["issues"])
        self.assertEqual(self.simulate().status_code, 409)

    def test_alternative_deactivation_blocks_simulation(self):
        self.alternate.is_active = False
        self.alternate.save(update_fields=["is_active"])
        self.assertIn("CHOICE_CONCEPT_INVALID", self.detail().json()["issues"])
        self.assertEqual(self.simulate().status_code, 409)

    def test_inactive_historical_choice_is_not_rewritten(self):
        third = Concept.objects.create(
            slug="w13-integrity-third", name_en="NON-SCIENTIFIC prior choice",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, simple_definition="Synthetic",
        )
        old_choice = CognitiveDistortionPracticeChoice.objects.create(
            item=self.item, concept=third, text="Preserved historical choice",
            is_correct=False, is_active=False, sort_order=2,
        )
        third.is_active = False
        third.save(update_fields=["is_active"])
        self.assertTrue(self.detail().json()["valid"])
        self.assertEqual(self.simulate().status_code, 200)
        old_choice.refresh_from_db()
        self.assertFalse(old_choice.is_active)
        self.assertEqual(old_choice.text, "Preserved historical choice")
