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

    def test_research_staging_identifiers_not_raw_content_and_strict_capability(self):
        from .models import ResearchDataset, ResearchRecord
        dataset = ResearchDataset.objects.create(
            key="p17-internal-dataset", source_filename="private-original.json",
            source_sha256="f" * 64, is_active=False,
            raw_text="P17-SECRET-RAW-CORPUS",
            raw_document={"patient": "P17-SECRET-PATIENT"},
        )
        record = ResearchRecord.objects.create(
            dataset=dataset, section="concepts", external_id="Private external id",
            slug="p17-internal-concept", canonical_key="concept:p17-internal-concept",
            name_en="P17-SECRET-RESEARCH-NAME",
            payload={"question": "P17-SECRET-ANSWER"},
        )
        result = self.owner_client.get(BASE + "search/?q=p17-internal&domain=research")
        self.assertEqual(result.status_code, 200, result.content[:350])
        data = result.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual({item["kind"] for item in data["results"]},
                         {"research_dataset", "research_record"})
        self.assertEqual({item["resource_id"] for item in data["results"]},
                         {dataset.pk, record.pk})
        self.assertFalse(next(row for row in data["results"]
                             if row["kind"] == "research_dataset")["is_active"])
        for secret in ("P17-SECRET", "raw_text", "raw_document", "payload",
                       "source_filename", "external_id", "name_en"):
            self.assertNotIn(secret, result.content.decode())
        self.assertEqual(self.owner_client.get(
            BASE + "search/?q=p17-secret&domain=research").json()["count"], 0)
        viewer = self.user("p17-research-scoped", staff=True, caps=(
            "cms_enter", "cms_search", "cms_research_view"))
        client = self.sign_in(viewer)
        self.assertEqual(client.get(BASE + "search/?q=p17-internal&domain=research").json()["count"], 2)
        no_research = self.user("p17-without-research", staff=True, caps=(
            "cms_enter", "cms_search", "cms_learning_view"))
        other = self.sign_in(no_research)
        self.assertEqual(other.get(BASE + "search/?q=p17-internal&domain=research").status_code, 403)
        self.assertEqual(other.get(BASE + "search/?q=p17-internal&domain=all").json()["count"], 0)

    def test_audit_search_exact_numeric_id_without_actor_or_event_payload(self):
        from .cms_models import AdminAuditEvent
        for _ in range(12):
            row = AdminAuditEvent.objects.create(
                actor=self.owner, action="session.login", outcome="success",
                target_kind="session", target_key="", reason="",
            )
        q = str(row.pk)
        result = self.owner_client.get(BASE + "search/?q=" + q + "&domain=audit")
        self.assertEqual(result.status_code, 200, result.content[:300])
        self.assertEqual(result.json()["count"], 1)
        self.assertEqual(result.json()["results"][0],
            {"kind": "audit_event", "resource_id": row.pk, "slug": q})
        for secret in ("actor_ref", "actor_id", "session.login",
                       "request_id", "target_key", "diff"):
            self.assertNotIn(secret, result.content.decode())
        self.assertEqual(self.owner_client.get(
            BASE + "search/?q=session&domain=audit").json()["count"], 0)
        audit_viewer = self.user("p17-audit-only", staff=True,
            caps=("cms_enter", "cms_search", "cms_audit_view"))
        client = self.sign_in(audit_viewer)
        self.assertEqual(client.get(BASE + "search/?q=" + q + "&domain=audit").json()["count"], 1)
        no_audit = self.user("p17-no-audit", staff=True,
            caps=("cms_enter", "cms_search", "cms_cases_view"))
        other = self.sign_in(no_audit)
        self.assertEqual(other.get(BASE + "search/?q=" + q + "&domain=audit").status_code, 403)
        self.assertEqual(other.get(BASE + "search/?q=" + q + "&domain=all").json()["count"], 0)

    def test_no_mutation_allowed(self):
        self.assertEqual(self.post(self.owner_client,"search/",{"q":"p17"}).status_code,405)
        self.assertFalse(self.case.is_active)
        self.assertFalse(self.quiz.is_active)
        self.assertFalse(self.card.is_active)
