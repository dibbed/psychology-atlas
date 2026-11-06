"""P16 closed Learning draft fingerprints: no publication authority is granted."""
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from .models import (
    Category, CognitiveDistortionPracticeChoice, CognitiveDistortionPracticeItem,
    Concept, DailyChallenge, DailyChallengeChoice, Disorder, Flashcard,
    Quiz, QuizChoice, QuizQuestion, StudyActivity,
)
from .tests_v100_p01 import BASE, SecurityFixture
from .cms_learning_fingerprint import draft_fingerprint


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningDraftFingerprintTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        category = Category.objects.create(slug="p16-fp-test", name_en="Synthetic")
        self.disorder = Disorder.objects.create(
            category=category, slug="p16-fp-disorder", name_en="Synthetic", is_active=True,
        )
        self.quiz = Quiz.objects.create(
            slug="p16-fp-quiz", title="Synthetic unpublished quiz",
            disorder=self.disorder, is_active=False, seed_managed=False,
        )
        self.question = QuizQuestion.objects.create(
            quiz=self.quiz, prompt="Sensitive unpublished example?", explanation="Only an example",
        )
        self.correct = QuizChoice.objects.create(
            question=self.question, text="Secret true choice", is_correct=True,
        )
        QuizChoice.objects.create(question=self.question, text="Secret false choice", is_correct=False)

    def item(self, kind, pk):
        response = self.client.get(BASE + "publication/preflight/?domain=learning")
        self.assertEqual(response.status_code, 200, response.content[:350])
        item = next((row for row in response.json()["results"]
                     if row["kind"] == kind and row["resource_id"] == pk), None)
        self.assertIsNotNone(item, response.content[:350])
        return item, response

    def test_quiz_content_fingerprint_binds_inactive_children_without_leaking_answers(self):
        first, response = self.item("quiz", self.quiz.pk)
        self.assertEqual(len(first["content_digest"]), 64)
        self.assertEqual(first["content_issues"], [])
        self.assertEqual(first["dependency_ids"], {"disorder": [self.disorder.pk]})
        self.assertIn("P16_MANIFEST_AND_RECEIPT_REQUIRED", first["blockers"])
        self.assertFalse(first["eligible"])
        for secret in ("Sensitive unpublished example?", "Secret true choice", "Secret false choice"):
            self.assertNotIn(secret, response.content.decode())
        again, _ = self.item("quiz", self.quiz.pk)
        self.assertEqual(first["content_digest"], again["content_digest"])
        self.correct.is_active = False
        self.correct.save(update_fields=["is_active"])
        changed, _ = self.item("quiz", self.quiz.pk)
        self.assertNotEqual(first["content_digest"], changed["content_digest"])
        self.assertIn("CONTENT_VALIDATION_REQUIRED", changed["blockers"])
        self.assertIn("QUIZ_ANSWER_KEY_INVALID", changed["content_issues"])
        self.assertFalse(Quiz.objects.get(pk=self.quiz.pk).is_active)
        self.assertFalse(StudyActivity.objects.exists())

    def test_dependency_closure_and_content_changes_are_detectable(self):
        concept = Concept.objects.create(
            slug="p16-fp-concept", name_en="Synthetic concept", is_active=False,
        )
        card = Flashcard.objects.create(
            slug="p16-fp-card", front="Private first face", back="Private second face",
            concept=concept, is_active=False, seed_managed=False,
        )
        first, _ = self.item("flashcard", card.pk)
        self.assertEqual(first["dependency_ids"], {"concept": [concept.pk]})
        self.assertIn("INACTIVE_DEPENDENCY", first["content_issues"])
        concept.is_active = True
        concept.save(update_fields=["is_active"])
        second, _ = self.item("flashcard", card.pk)
        self.assertNotEqual(first["content_digest"], second["content_digest"])
        self.assertNotIn("INACTIVE_DEPENDENCY", second["content_issues"])
        card.front = "Edited unpublished face"
        card.save(update_fields=["front"])
        third, _ = self.item("flashcard", card.pk)
        self.assertNotEqual(second["content_digest"], third["content_digest"])

    def test_daily_and_distortion_choices_are_fingerprinted_without_publication(self):
        concept = Concept.objects.create(
            slug="p16-fp-distortion", name_en="Synthetic cognitive distortion",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, is_active=True,
        )
        daily = DailyChallenge.objects.create(
            prompt="Daily private prompt", concept=concept, is_active=False, seed_managed=False,
        )
        DailyChallengeChoice.objects.create(challenge=daily, text="Daily true", is_correct=True)
        DailyChallengeChoice.objects.create(challenge=daily, text="Daily false", is_correct=False)
        practice = CognitiveDistortionPracticeItem.objects.create(
            slug="p16-fp-practice", prompt="Private practice", explanation="Synthetic explanation",
            target_concept=concept, is_active=False, seed_managed=False,
        )
        CognitiveDistortionPracticeChoice.objects.create(
            item=practice, concept=concept, text="Practice true", is_correct=True,
        )
        first_daily, _ = self.item("daily_challenge", daily.pk)
        first_practice, _ = self.item("distortion_practice", practice.pk)
        self.assertEqual(first_daily["content_issues"], [])
        self.assertIn("CHOICES_INSUFFICIENT", first_practice["content_issues"])
        for row in (first_daily, first_practice):
            self.assertFalse(row["eligible"])
            self.assertIn("P16_MANIFEST_AND_RECEIPT_REQUIRED", row["blockers"])
        daily.prompt = "A newer private prompt"
        daily.save(update_fields=["prompt"])
        second, _ = self.item("daily_challenge", daily.pk)
        self.assertNotEqual(first_daily["content_digest"], second["content_digest"])

    def test_quiz_snapshot_queries_do_not_grow_per_question(self):
        for position in range(12):
            question = QuizQuestion.objects.create(
                quiz=self.quiz, prompt=f"Private prompt {position}", explanation="Synthetic",
                sort_order=position + 1,
            )
            QuizChoice.objects.create(question=question, text="True", is_correct=True)
            QuizChoice.objects.create(question=question, text="False", is_correct=False)
        with CaptureQueriesContext(connection) as captured:
            snapshot = draft_fingerprint("quiz", self.quiz)
        self.assertEqual(snapshot["content_issues"], [])
        # One questions fetch, one bulk choices fetch and bounded dependencies.
        self.assertLessEqual(len(captured), 5)
