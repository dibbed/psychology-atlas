"""P17 private slug-only discovery; never full-text search learner content."""
from django.test import TestCase, override_settings

from .models import ClinicalCase, Quiz, Flashcard, SourceReference
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdminSearchSafeScopeTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client=self.sign_in(self.owner)
        self.case=ClinicalCase.objects.create(
            slug="p17-fictional-case",title="Private patient story",
            patient_summary="Sensitive synthetic story, never returned by search",
            educational_objective="Synthetic objective",is_active=False,seed_managed=False,
        )
        self.quiz=Quiz.objects.create(
            slug="p17-fictional-quiz",title="Unpublished quiz",is_active=False,seed_managed=False)
        self.card=Flashcard.objects.create(
            slug="p17-fictional-card",front="Secret synthetic front",
            back="Secret synthetic answer",is_active=False,seed_managed=False)
        self.source=SourceReference.objects.create(
            title="P17-fictional source",citation="Private source citation not searchable",
            verification_status="unreviewed")

    def test_slug_search_scoped_and_redacted(self):
        res=self.owner_client.get(BASE+"search/?q=p17-fictional&domain=all")
        self.assertEqual(res.status_code,200,res.content[:400])
        data=res.json()
        self.assertEqual(data["scope"],"private_slug_index")
        self.assertEqual({row["kind"] for row in data["results"]},
                         {"clinical_case","quiz","flashcard","source_reference"})
        self.assertEqual(data["count"],4)
        source=next(row for row in data["results"] if row["kind"]=="source_reference")
        self.assertEqual(source["resource_id"],self.source.pk)
        self.assertEqual(source["label"],"P17-fictional source")
        self.assertNotIn("patient",str(data).lower())
        self.assertNotIn("secret",str(data).lower())
        self.assertNotIn("front",str(data).lower())
        self.assertNotIn("user_id",str(data).lower())
        self.assertEqual(self.owner_client.get(BASE+"search/?q=p").status_code,400)
        self.assertEqual(self.owner_client.get(BASE+"search/?q=p17&sort=raw").status_code,400)

    def test_global_search_privileges_are_independent_of_domain_read(self):
        viewer=self.user("p17-learning-only",staff=True,caps=(
            "cms_enter","cms_search","cms_learning_view"))
        client=self.sign_in(viewer)
        res=client.get(BASE+"search/?q=p17-fictional&domain=all")
        self.assertEqual(res.status_code,200,res.content[:300])
        self.assertEqual({row["kind"] for row in res.json()["results"]},{"quiz","flashcard"})
        self.assertEqual(client.get(BASE+"search/?q=p17-fictional&domain=cases").status_code,403)
        self.assertEqual(client.get(BASE+"search/?q=p17-fictional&domain=sources").status_code,403)
        source_viewer=self.user("p17-source-only",staff=True,caps=(
            "cms_enter","cms_search","cms_source_view"))
        source_response=self.sign_in(source_viewer).get(BASE+"search/?q=p17&domain=all")
        self.assertEqual(source_response.status_code,200,source_response.content[:400])
        self.assertEqual({row["kind"] for row in source_response.json()["results"]},
                         {"source_reference"})
        no_search=self.user("p17-view-no-search",staff=True,caps=(
            "cms_enter","cms_cases_view","cms_learning_view"))
        self.assertEqual(self.sign_in(no_search).get(BASE+"search/?q=p17-fictional").status_code,403)

    def test_no_mutation_allowed(self):
        self.assertEqual(self.post(self.owner_client,"search/",{"q":"p17"}).status_code,405)
        self.assertFalse(self.case.is_active)
        self.assertFalse(self.quiz.is_active)
        self.assertFalse(self.card.is_active)
