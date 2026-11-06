"""P16 selected-for-review batches, never publication manifests or approval."""
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from .cms_content import digest
from .cms_content_models import ContentState, ContentRevision
from .models import Category, Disorder, Quiz, QuizQuestion, QuizChoice, StudyActivity
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PublicationSelectionsTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client = self.sign_in(self.owner)
        category = Category.objects.create(slug="p16-selection", name_en="P16 synthetic")
        disorder = Disorder.objects.create(
            category=category, slug="p16-selection-disorder",
            name_en="P16 synthetic only", is_active=True,
        )
        self.quiz = Quiz.objects.create(
            slug="p16-selection-quiz", title="Confidential draft question",
            disorder=disorder, is_active=False, seed_managed=False,
        )
        question = QuizQuestion.objects.create(quiz=self.quiz, prompt="Private hidden quiz body")
        QuizChoice.objects.create(question=question, text="Private correct answer", is_correct=True)
        QuizChoice.objects.create(question=question, text="Private wrong answer", is_correct=False)
        self.brain = self.proposal("brain-anatomical-entity", "P16 confidential brain")
        self.assessment = self.proposal("assessment-instrument", "P16 confidential assessment")

    def proposal(self, kind, name):
        state = ContentState.objects.create(kind=kind, canonical_digest=digest({}))
        data = {"name_en": name}
        revision = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest=digest({}),
            payload=data, payload_digest=digest(data), dependency_digest=digest({}),
            status="draft", actor=self.owner,
        )
        state.version, state.current_revision = 1, revision
        state.save(update_fields=("version", "current_revision"))
        return state

    def entry(self, domain, kind, identifier):
        response = self.owner_client.get(BASE + f"publication/preflight/?domain={domain}")
        self.assertEqual(response.status_code, 200, response.content[:300])
        row = next(v for v in response.json()["results"]
                   if v["kind"] == kind and str(v["resource_id"]) == str(identifier))
        return {"kind":kind,"resource_id":identifier,
                "expected_digest":row.get("content_digest") or row.get("proposal_digest")}

    def post_selection(self, domain, entries, *, key=None):
        return self.post(
            self.owner_client, "publication/selections/",
            {"domain":domain,"entries":entries,"request_key":str(key or uuid.uuid4())},
        )

    def test_learning_selection_is_immutable_audited_and_cannot_publish(self):
        entry = self.entry("learning", "quiz", self.quiz.pk)
        request_key = uuid.uuid4()
        first = self.post_selection("learning", [entry], key=request_key)
        self.assertEqual(first.status_code, 201, first.content[:400])
        body = first.json()
        self.assertEqual(body["status"], "review_selection_only")
        self.assertEqual(body["domain"], "learning")
        self.assertEqual(body["item_count"], 1)
        self.assertEqual(len(body["selection_digest"]), 64)
        self.assertFalse(body["publication_available"])
        self.assertFalse(body["approved"])
        self.assertNotIn("Private hidden quiz body", first.content.decode())
        self.assertNotIn("Private correct answer", first.content.decode())
        second = self.post_selection("learning", [entry], key=request_key)
        self.assertEqual(second.status_code, 200, second.content[:400])
        self.assertEqual(second.json()["id"], body["id"])
        self.assertEqual(second.json()["selection_digest"], body["selection_digest"])
        detail = self.owner_client.get(BASE + f'publication/selections/{body["id"]}/')
        self.assertEqual(detail.status_code, 200, detail.content[:400])
        self.assertEqual(detail.json()["selection_digest"], body["selection_digest"])
        self.assertFalse(Quiz.objects.get(pk=self.quiz.pk).is_active)
        self.assertEqual(StudyActivity.objects.count(), 0)
        from .cms_publication_selection_models import PublicationCandidateSelection
        from .cms_models import AdminAuditEvent
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="publication.selection_created").count(), 1)
        row = PublicationCandidateSelection.objects.get()
        self.assertEqual(row.selection["items"][0]["content_digest"], entry["expected_digest"])
        with self.assertRaises(ValidationError):
            row.save()
        with self.assertRaises(ValidationError):
            PublicationCandidateSelection.objects.filter(pk=row.pk).update(domain="brain")
        with self.assertRaises(ValidationError):
            PublicationCandidateSelection.objects.filter(pk=row.pk).delete()

    def test_same_key_recovers_original_snapshot_after_content_changes(self):
        from .cms_publication_selection_models import PublicationCandidateSelection
        entry = self.entry("learning", "quiz", self.quiz.pk)
        key = uuid.uuid4()
        first = self.post_selection("learning", [entry], key=key)
        self.assertEqual(first.status_code, 201)
        self.quiz.title = "New private revision after lost response"
        self.quiz.save(update_fields=("title",))
        recovered = self.post_selection("learning", [entry], key=key)
        self.assertEqual(recovered.status_code, 200, recovered.content[:200])
        self.assertTrue(recovered.json()["recovered"])
        self.assertEqual(recovered.json()["selection_digest"], first.json()["selection_digest"])
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)
        self.assertNotIn("New private revision", recovered.content.decode())
        # A new request key must not accidentally accept an obsolete digest.
        self.assertEqual(self.post_selection("learning", [entry]).status_code, 412)

    def test_stale_second_item_rejects_entire_transaction(self):
        entry = self.entry("learning", "quiz", self.quiz.pk)
        wrong = dict(entry, expected_digest="a" * 64)
        failed = self.post_selection("learning", [entry, wrong])
        self.assertIn(failed.status_code, (400, 409, 412), failed.content[:400])
        from .cms_publication_selection_models import PublicationCandidateSelection
        self.assertFalse(PublicationCandidateSelection.objects.exists())
        self.quiz.title = "Changed private body"
        self.quiz.save(update_fields=["title"])
        failed = self.post_selection("learning", [entry])
        self.assertEqual(failed.status_code, 412, failed.content[:400])
        self.assertFalse(PublicationCandidateSelection.objects.exists())

    def test_brain_and_assessment_snapshots_are_not_approvals(self):
        from .cms_publication_selection_models import PublicationCandidateSelection
        for domain, kind, state in (
            ("brain","brain-anatomical-entity",self.brain),
            ("assessment","assessment-instrument",self.assessment),
        ):
            entry = self.entry(domain, kind, str(state.pk))
            response = self.post_selection(domain, [entry])
            self.assertEqual(response.status_code, 201, response.content[:300])
            self.assertFalse(response.json()["publication_available"])
            self.assertNotIn("confidential", response.content.decode())
            self.assertEqual(ContentState.objects.get(pk=state.pk).publication, "never_published")
        self.assertEqual(PublicationCandidateSelection.objects.count(), 2)

    def test_replay_conflict_closed_shapes_permission_revocation(self):
        from .cms_publication_selection_models import PublicationCandidateSelection
        entry = self.entry("learning", "quiz", self.quiz.pk)
        key = uuid.uuid4()
        self.assertEqual(self.post_selection("learning", [entry], key=key).status_code, 201)
        changed = dict(entry, expected_digest="a"*64)
        self.assertEqual(self.post_selection("learning", [changed], key=key).status_code, 409)
        assessment_entry = self.entry("assessment", "assessment-instrument", str(self.assessment.pk))
        self.assertEqual(self.post_selection("assessment", [assessment_entry], key=key).status_code, 409)
        denied = self.user("p16-selector-denied", staff=True,
                           caps=("cms_enter","cms_learning_view","cms_publication_validate_learning"))
        client = self.sign_in(denied)
        self.assertEqual(self.post(client, "publication/selections/", {
            "domain":"learning", "entries":[entry], "request_key":str(uuid.uuid4())}).status_code, 403)
        self.assertEqual(self.post_selection("learning", []).status_code, 400)
        malformed = self.post(self.owner_client, "publication/selections/", {
            "domain":"learning","entries":[entry],"request_key":str(uuid.uuid4()),"apply":True})
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)
