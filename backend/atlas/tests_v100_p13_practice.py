"""P13 practice CMS: no attempt/history mutation, valid answer keys, private drafts."""
from django.test import TestCase, override_settings

from .models import (
    Concept, DailyChallenge, DailyChallengeAttempt,
    CognitiveDistortionPracticeItem, CognitiveDistortionPracticeChoice,
    CognitiveDistortionPracticeAttempt, StudyActivity,
)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PracticeCMSContractTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.sign_in(self.owner)
        self.correct = Concept.objects.create(
            slug="p13-distortion-one", name_en="Synthetic distortion one",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, simple_definition="Fictional",
        )
        self.other = Concept.objects.create(
            slug="p13-distortion-two", name_en="Synthetic distortion two",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION, simple_definition="Fictional",
        )

    def test_daily_challenge_draft_answer_key_preview_and_history_pin(self):
        create = self.post(self.admin, "learning/practice/daily/", {
            "prompt":"Synthetic daily question", "explanation":"Educational only",
            "concept_id":None, "disorder_id":None,
        })
        self.assertEqual(create.status_code, 201, create.content[:350])
        identifier = create.json()["item_id"]
        challenge = DailyChallenge.objects.get(pk=identifier)
        self.assertFalse(challenge.is_active)
        detail = self.admin.get(BASE+f"learning/practice/daily/{identifier}/")
        self.assertEqual(detail.status_code, 200)
        edit = self.post(self.admin, f"learning/practice/daily/{identifier}/edit/", {
            "prompt":"Synthetic daily question", "explanation":"Educational only",
            "choices":[
                {"text":"Fictional correct", "is_correct":True},
                {"text":"Fictional incorrect", "is_correct":False},
            ],
        }, etag=detail["ETag"])
        self.assertEqual(edit.status_code, 200, edit.content[:380])
        self.assertTrue(edit.json()["valid"])
        choice = challenge.choices.get(is_correct=True)
        counts=(DailyChallengeAttempt.objects.count(),StudyActivity.objects.count())
        sim=self.post(self.admin,f"learning/practice/daily/{identifier}/simulate/",{"choice_id":choice.pk})
        self.assertEqual(sim.status_code, 200, sim.content[:350])
        self.assertTrue(sim.json()["correct"])
        self.assertTrue(sim.json()["preview_only"])
        self.assertEqual(counts,(DailyChallengeAttempt.objects.count(),StudyActivity.objects.count()))
        user_attempt=DailyChallengeAttempt.objects.create(
            user=self.normal,challenge=challenge,
            selected_choice=choice, is_correct=True,activity_date="2026-10-01",
        )
        blocked=self.post(self.admin,f"learning/practice/daily/{identifier}/edit/",{
            "prompt":"Changed answer","explanation":"","choices":[
                {"text":"Changed A","is_correct":False},{"text":"Changed B","is_correct":True},
            ]},etag=edit["ETag"])
        self.assertEqual(blocked.status_code,409,blocked.content[:300])
        user_attempt.refresh_from_db()
        self.assertEqual(user_attempt.selected_choice_id,choice.pk)
        self.assertTrue(user_attempt.is_correct)

    def test_distortion_practice_requires_correct_concept_match_and_preserves_history(self):
        create=self.post(self.admin,"learning/practice/distortions/",{
            "slug":"p13-distortion-example","prompt":"Synthetic thought?",
            "explanation":"Fictional explanation","difficulty":"basic",
            "target_concept_id":self.correct.pk,
        })
        self.assertEqual(create.status_code,201,create.content[:300])
        identifier=create.json()["item_id"]
        detail=self.admin.get(BASE+f"learning/practice/distortions/{identifier}/")
        self.assertEqual(detail.status_code,200)
        invalid=self.post(self.admin,f"learning/practice/distortions/{identifier}/edit/",{
            "prompt":"Fictional","explanation":"Example",
            "choices":[
                {"concept_id":self.correct.pk,"text":"A","is_correct":False},
                {"concept_id":self.other.pk,"text":"B","is_correct":True},
            ],
        },etag=detail["ETag"])
        self.assertEqual(invalid.status_code,400,invalid.content[:300])
        self.assertFalse(CognitiveDistortionPracticeChoice.objects.filter(item_id=identifier).exists())
        edit=self.post(self.admin,f"learning/practice/distortions/{identifier}/edit/",{
            "prompt":"Fictional","explanation":"Example",
            "choices":[
                {"concept_id":self.correct.pk,"text":"A","is_correct":True},
                {"concept_id":self.other.pk,"text":"B","is_correct":False},
            ],
        },etag=detail["ETag"])
        self.assertEqual(edit.status_code,200,edit.content[:300])
        self.assertTrue(edit.json()["valid"])
        item=CognitiveDistortionPracticeItem.objects.get(pk=identifier)
        choice=item.choices.get(is_correct=True)
        sim=self.post(self.admin,f"learning/practice/distortions/{identifier}/simulate/",{"choice_id":choice.pk})
        self.assertEqual(sim.status_code,200,sim.content[:300])
        self.assertTrue(sim.json()["correct"])
        attempt=CognitiveDistortionPracticeAttempt.objects.create(
            user=self.normal,item=item,selected_choice=choice,is_correct=True)
        self.assertEqual(self.post(self.admin,f"learning/practice/distortions/{identifier}/edit/",{
            "prompt":"Wrong","explanation":"", "choices":[
                {"concept_id":self.correct.pk,"text":"X","is_correct":True},
                {"concept_id":self.other.pk,"text":"Y","is_correct":False},
            ]},etag=edit["ETag"]).status_code,409)
        attempt.refresh_from_db()
        self.assertEqual((attempt.selected_choice_id,attempt.is_correct),(choice.pk,True))

    def test_viewer_cannot_mutate_practice_or_see_private_results_as_public(self):
        viewer=self.user("p13-practice-viewer",staff=True,caps=("cms_enter","cms_learning_view"))
        client=self.sign_in(viewer)
        self.assertEqual(client.get(BASE+"learning/practice/daily/").status_code,200)
        self.assertEqual(self.post(client,"learning/practice/daily/",{
            "prompt":"No","explanation":"","concept_id":None,"disorder_id":None,
        }).status_code,403)
        editor=self.user("p13-practice-editor-no-view",staff=True,
                         caps=("cms_enter","cms_learning_edit"))
        self.assertEqual(self.post(self.sign_in(editor),"learning/practice/daily/",{
            "prompt":"No","explanation":"","concept_id":None,"disorder_id":None,
        }).status_code,403)
