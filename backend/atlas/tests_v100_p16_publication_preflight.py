"""P16 initial publication inventory: scoped inspection without activation."""
from django.test import TestCase, override_settings

from .models import CaseRevision, ClinicalCase, Quiz, Flashcard, StudyActivity
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PublicationPreflightContractTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client=self.sign_in(self.owner)
        self.case=ClinicalCase.objects.create(
            slug="p16-inactive-case",title="Synthetic learning case",
            patient_summary="Fictional",is_active=False,structure_mode=ClinicalCase.StructureMode.BRANCHING,
            seed_managed=False,
        )
        self.revision=CaseRevision.objects.create(
            case=self.case,version=1,title=self.case.title,
            patient_summary=self.case.patient_summary,status=CaseRevision.Status.DRAFT,
        )
        self.quiz=Quiz.objects.create(slug="p16-inactive-quiz",title="Synthetic private quiz",
                                      is_active=False,seed_managed=False)
        self.card=Flashcard.objects.create(slug="p16-inactive-card",front="Fictional",
                                           back="Fictional",is_active=False,seed_managed=False)

    def test_scoped_case_drafts_are_never_marked_publishable(self):
        url=BASE+"publication/preflight/?domain=cases&page_size=20&page=1"
        count_before=(CaseRevision.objects.count(),Quiz.objects.count(),StudyActivity.objects.count())
        response=self.owner_client.get(url)
        self.assertEqual(response.status_code,200,response.content[:350])
        data=response.json()
        self.assertTrue(data["publication_available"])  # Guarded CaseRevision workflow exists, not auto-apply
        self.assertEqual(data["domain"],"cases")
        target=next(item for item in data["results"] if item["resource_id"]==self.revision.pk)
        self.assertIn("SCIENTIFIC_REVIEW_NOT_LINKED",target["blockers"])
        self.assertIn("SOURCE_RIGHTS_REVIEW_NOT_LINKED",target["blockers"])
        self.assertIn("CASE_GRAPH_INVALID",target["blockers"])
        from .cms_case_fingerprint import case_revision_fingerprint
        self.assertEqual(target["revision_digest"],case_revision_fingerprint(self.revision))
        self.revision.title="Changed fictional review target"
        self.revision.save(update_fields=["title"])
        updated=self.owner_client.get(url)
        self.assertEqual(updated.status_code,200)
        second=next(item for item in updated.json()["results"]
                    if item["resource_id"]==self.revision.pk)
        self.assertNotEqual(target["revision_digest"],second["revision_digest"])
        self.assertFalse(second["eligible"])
        self.assertFalse(target["eligible"])
        self.assertEqual((CaseRevision.objects.count(),Quiz.objects.count(),
                          StudyActivity.objects.count()),count_before)
        self.assertEqual(self.case.current_revision_id,None)

    def test_learning_queue_and_independent_permissions(self):
        r=self.owner_client.get(BASE+"publication/preflight/?domain=learning")
        self.assertEqual(r.status_code,200,r.content[:400])
        items={(item["kind"],item["resource_id"]) for item in r.json()["results"]}
        self.assertIn(("quiz",self.quiz.pk),items)
        self.assertIn(("flashcard",self.card.pk),items)
        wrong=self.user("p16-learning-queue-only-view",staff=True,caps=("cms_enter","cms_learning_view"))
        self.assertEqual(self.sign_in(wrong).get(
            BASE+"publication/preflight/?domain=learning").status_code,403)
        scoper=self.user("p16-learning-queue-scoped",staff=True,caps=(
            "cms_enter","cms_learning_view","cms_publication_validate_learning"))
        scoper_client=self.sign_in(scoper)
        self.assertEqual(scoper_client.get(
            BASE+"publication/preflight/?domain=learning").status_code,200)
        self.assertEqual(scoper_client.get(
            BASE+"publication/preflight/?domain=cases").status_code,403)

    def test_refuses_unknown_query_and_mutations(self):
        self.assertEqual(self.owner_client.get(
            BASE+"publication/preflight/?domain=not-registered").status_code,400)
        self.assertEqual(self.owner_client.get(
            BASE+"publication/preflight/?domain=cases&user_id=1").status_code,400)
        self.assertEqual(self.post(self.owner_client,"publication/preflight/",
            {"domain":"cases","status":"published"}).status_code,405)
