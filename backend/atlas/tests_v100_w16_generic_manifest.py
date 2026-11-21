"""W16-02: immutable, non-authorizing frozen review manifest and public dry-run.

All examples are synthetic; the tests never award genuine scientific/rights
publication clearance or touch the canonical application database.
"""
import uuid

from django.db.models.query import QuerySet
from django.test import TestCase, override_settings

from .cms_content import digest
from .cms_content_models import ContentRevision, ContentState
from .cms_models import AdminAuditEvent
from .models import BrainAnatomicalEntity
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GenericFrozenManifestTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client = self.sign_in(self.owner)
        self.state = ContentState.objects.create(
            kind="brain-anatomical-entity", canonical_digest=digest({}))
        payload = {"name_en": "W16_PROTECTED_PRIVATE_PROPOSED_NAME",
                   "description_en": "W16_PRIVATE_NEVER_PUBLIC_TEXT"}
        revision = ContentRevision.objects.create(
            state=self.state, sequence=1, base_version=0, base_digest=digest({}),
            payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), actor=self.owner, status="draft",
        )
        self.state.current_revision = revision
        self.state.version = 1
        self.state.save(update_fields=["current_revision", "version"])
        inventory = self.owner_client.get(BASE + "publication/preflight/?domain=brain")
        self.assertEqual(inventory.status_code, 200, inventory.content[:350])
        row = next(item for item in inventory.json()["results"]
                   if item["resource_id"] == str(self.state.pk))
        selected = self.post(self.owner_client, "publication/selections/", {
            "domain": "brain", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": self.state.kind, "resource_id": str(self.state.pk),
                         "expected_digest": row["proposal_digest"]}],
        })
        self.assertEqual(selected.status_code, 201, selected.content[:300])
        self.selection = selected.json()
        dossier = self.post(self.owner_client,
            f'publication/selections/{self.selection["id"]}/prepare/', {
                "request_key": str(uuid.uuid4()),
                "selection_digest": self.selection["selection_digest"]})
        self.assertEqual(dossier.status_code, 201, dossier.content[:300])
        self.dossier = dossier.json()
        self.url = "publication/preparations/" + self.dossier["id"] + "/"

    def freeze(self, key, *, client=None, **extra):
        return self.post(client or self.owner_client, self.url + "freeze/", {
            "dossier_digest": self.dossier["dossier_digest"],
            "request_key": str(key), **extra,
        })

    def test_dry_run_and_freeze_are_exact_bounded_immutable_and_no_publish(self):
        from .cms_publication_plan_models import PublicationFrozenManifest
        dry = self.owner_client.get(BASE + self.url + "dry-run/")
        self.assertEqual(dry.status_code, 200, dry.content[:350])
        self.assertEqual(dry.json()["schema"], "cms-frozen-review-manifest-v1")
        self.assertFalse(dry.json()["publication_available"])
        self.assertEqual(dry.json()["dossier_digest"], self.dossier["dossier_digest"])
        self.assertEqual(dry.json()["item_count"], 1)
        self.assertEqual(dry.json()["actions"][0]["kind"], self.state.kind)
        self.assertEqual(dry.json()["actions"][0]["revision_id"], self.state.current_revision_id)
        self.assertEqual(dry.json()["actions"][0]["action"], "create")
        self.assertEqual(dry.json()["public_projection"], None)
        for private in ("W16_PROTECTED_PRIVATE_PROPOSED_NAME", "W16_PRIVATE_NEVER_PUBLIC_TEXT"):
            self.assertNotIn(private, dry.content.decode())
        self.assertEqual(PublicationFrozenManifest.objects.count(), 0)
        key = uuid.uuid4()
        first = self.freeze(key)
        self.assertEqual(first.status_code, 201, first.content[:350])
        result = first.json()
        self.assertEqual(result["manifest_digest"], dry.json()["manifest_digest"])
        self.assertEqual(result["dossier_id"], self.dossier["id"])
        self.assertFalse(result["publication_available"])
        self.assertFalse(result["approved"])
        self.assertEqual(PublicationFrozenManifest.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(
            action="publication.review_manifest_frozen").count(), 1)
        same = self.freeze(key)
        self.assertEqual(same.status_code, 200)
        self.assertEqual(same.json()["id"], result["id"])
        self.assertTrue(same.json()["recovered"])
        other = self.freeze(uuid.uuid4())
        self.assertEqual(other.status_code, 409)
        self.assertEqual(PublicationFrozenManifest.objects.count(), 1)
        detail = self.owner_client.get(
            BASE + "publication/plans/" + result["id"] + "/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["manifest_digest"], result["manifest_digest"])
        self.assertEqual(detail.json()["status"], "frozen_review_only")
        self.assertEqual(detail.json()["actions"][0]["action"], "create")
        self.assertIsNone(detail.json()["public_projection"])
        self.assertFalse(BrainAnatomicalEntity.objects.filter(
            slug="W16_PROTECTED_PRIVATE_PROPOSED_NAME").exists())
        self.assertEqual(self.state.publication, "never_published")
        self.assertEqual(self.state.canonical_pk, None)
        self.assertEqual(PublicationFrozenManifest.objects.get(pk=result["id"]).manifest_digest,
                         result["manifest_digest"])

    def test_learning_manifest_hides_question_and_answer_keys_and_stays_inactive(self):
        from .models import Category, Disorder, Quiz, QuizQuestion, QuizChoice
        from .cms_publication_plan_models import PublicationFrozenManifest
        parent = Category.objects.create(slug="w16-l-pt", name_en="Synthetic")
        disorder = Disorder.objects.create(
            slug="w16-l-parent", name_en="Synthetic disorder",
            category=parent, is_active=True)
        quiz = Quiz.objects.create(slug="w16-l-quiz", title="PRIVATE TITLE",
            disorder=disorder, is_active=False, seed_managed=False)
        question = QuizQuestion.objects.create(
            quiz=quiz, prompt="NEVER_EXPOSE_QUIZ_QUESTION")
        QuizChoice.objects.create(question=question, text="NEVER_EXPOSE_CORRECT",
                                  is_correct=True, is_active=True)
        QuizChoice.objects.create(question=question, text="NEVER_EXPOSE_WRONG",
                                  is_correct=False, is_active=True)
        inv = self.owner_client.get(BASE + "publication/preflight/?domain=learning")
        self.assertEqual(inv.status_code, 200)
        candidate = next(item for item in inv.json()["results"]
                         if item["kind"] == "quiz" and item["resource_id"] == quiz.pk)
        selected = self.post(self.owner_client, "publication/selections/", {
            "domain": "learning", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": "quiz", "resource_id": quiz.pk,
                         "expected_digest": candidate["content_digest"]}],
        })
        self.assertEqual(selected.status_code, 201)
        dossier = self.post(self.owner_client,
            f'publication/selections/{selected.json()["id"]}/prepare/', {
                "request_key": str(uuid.uuid4()),
                "selection_digest": selected.json()["selection_digest"]})
        self.assertEqual(dossier.status_code, 201)
        path = f'publication/preparations/{dossier.json()["id"]}/'
        check = self.owner_client.get(BASE + path + "dry-run/")
        self.assertEqual(check.status_code, 200, check.content[:350])
        self.assertEqual(check.json()["actions"][0]["action"], "activate")
        self.assertEqual(check.json()["item_count"], 1)
        self.assertFalse(check.json()["approved"])
        sealed = self.post(self.owner_client, path + "freeze/", {
            "request_key": str(uuid.uuid4()),
            "dossier_digest": dossier.json()["dossier_digest"]})
        self.assertEqual(sealed.status_code, 201, sealed.content[:300])
        for secret in ("NEVER_EXPOSE_QUIZ_QUESTION", "NEVER_EXPOSE_CORRECT",
                       "NEVER_EXPOSE_WRONG", "PRIVATE TITLE"):
            self.assertNotIn(secret, check.content.decode())
            self.assertNotIn(secret, sealed.content.decode())
            self.assertNotIn(secret, str(PublicationFrozenManifest.objects.get(
                pk=sealed.json()["id"]).manifest))
        self.assertFalse(Quiz.objects.get(pk=quiz.pk).is_active)

    def test_assessment_manifest_uses_real_public_routes_without_apply(self):
        from .cms_publication_plan_models import PublicationFrozenManifest
        state = ContentState.objects.create(kind="assessment-instrument",
            canonical_digest=digest({}))
        payload = {"name_en": "W16_ASSESSMENT_SECRET"}
        rev = ContentRevision.objects.create(state=state, sequence=1, base_version=0,
            base_digest=digest({}), payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), actor=self.owner, status="draft")
        state.current_revision, state.version = rev, 1
        state.save(update_fields=["current_revision", "version"])
        inventory = self.owner_client.get(BASE +
            "publication/preflight/?domain=assessment")
        candidate = next(x for x in inventory.json()["results"]
                         if x["resource_id"] == str(state.pk))
        select = self.post(self.owner_client, "publication/selections/", {
            "domain": "assessment", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": state.kind, "resource_id": str(state.pk),
                         "expected_digest": candidate["proposal_digest"]}],
        })
        self.assertEqual(select.status_code, 201)
        dossier = self.post(self.owner_client,
            f'publication/selections/{select.json()["id"]}/prepare/', {
                "selection_digest": select.json()["selection_digest"],
                "request_key": str(uuid.uuid4())})
        self.assertEqual(dossier.status_code, 201, dossier.content[:300])
        url = "publication/preparations/" + dossier.json()["id"] + "/"
        dry = self.owner_client.get(BASE + url + "dry-run/")
        self.assertEqual(dry.status_code, 200)
        surface = dry.json()["actions"][0]["public_reader_contract"]["surfaces"]
        self.assertEqual(surface["detail"]["route"], "/api/assessments/{slug}/")
        self.assertIsNone(surface["compare"]["route"])
        applied = self.post(self.owner_client, url + "freeze/", {
            "dossier_digest": dossier.json()["dossier_digest"],
            "request_key": str(uuid.uuid4())})
        self.assertEqual(applied.status_code, 201)
        self.assertFalse(applied.json()["publication_available"])
        self.assertEqual(PublicationFrozenManifest.objects.count(), 1)
        self.assertNotIn("W16_ASSESSMENT_SECRET", applied.content.decode())
        self.assertEqual(state.publication, "never_published")

    def test_owner_scoped_role_without_freeze_capability_is_denied(self):
        # This actor owns their own Selection and Dossier, but no W16 freeze grant.
        restricted = self.sign_in(self.user("w16-no-freeze-own", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_brain_preview",
            "cms_publication_validate_brain", "cms_publication_select_brain",
        )))
        inventory = restricted.get(BASE + "publication/preflight/?domain=brain")
        self.assertEqual(inventory.status_code, 200)
        candidate = next(item for item in inventory.json()["results"]
                         if item["resource_id"] == str(self.state.pk))
        selected = self.post(restricted, "publication/selections/", {
            "domain": "brain", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": self.state.kind, "resource_id": str(self.state.pk),
                         "expected_digest": candidate["proposal_digest"]}],
        })
        self.assertEqual(selected.status_code, 201)
        dossier = self.post(restricted,
            f'publication/selections/{selected.json()["id"]}/prepare/', {
                "selection_digest": selected.json()["selection_digest"],
                "request_key": str(uuid.uuid4())})
        self.assertEqual(dossier.status_code, 201)
        url = "publication/preparations/" + dossier.json()["id"] + "/"
        self.assertEqual(restricted.get(BASE + url + "dry-run/").status_code, 403)
        self.assertEqual(self.post(restricted, url + "freeze/", {
            "request_key": str(uuid.uuid4()),
            "dossier_digest": dossier.json()["dossier_digest"]}).status_code, 403)

    def test_stale_revision_rejects_dry_run_and_freeze_without_a_plan(self):
        from .cms_publication_plan_models import PublicationFrozenManifest
        payload = {"name_en": "W16_NEW_HIDDEN_REVISION"}
        revision = ContentRevision.objects.create(
            state=self.state, sequence=2, base_version=1, base_digest=digest({}),
            payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), actor=self.owner, status="draft")
        self.state.current_revision = revision
        self.state.version = 2
        self.state.save(update_fields=["current_revision", "version"])
        self.assertEqual(self.owner_client.get(
            BASE + self.url + "dry-run/").status_code, 409)
        self.assertEqual(self.freeze(uuid.uuid4()).status_code, 409)
        self.assertEqual(PublicationFrozenManifest.objects.count(), 0)

    def test_scope_permission_tamper_and_body_are_fail_closed(self):
        from .cms_publication_plan_models import PublicationFrozenManifest
        foreign = self.sign_in(self.user("w16-foreign", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_publication_validate_brain",
            "cms_publication_select_brain", "cms_publication_freeze_brain",
            "cms_publication_verify_brain", "cms_brain_preview",
        )))
        denied = self.sign_in(self.user("w16-no-freeze", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_publication_validate_brain",
            "cms_publication_select_brain",
        )))
        self.assertEqual(foreign.get(BASE + self.url + "dry-run/").status_code, 404)
        self.assertEqual(self.freeze(uuid.uuid4(), client=foreign).status_code, 404)
        self.assertEqual(denied.get(BASE + self.url + "dry-run/").status_code, 404)
        self.assertEqual(self.freeze(uuid.uuid4(), client=denied).status_code, 404)
        self.assertEqual(self.owner_client.get(
            BASE + self.url + "dry-run/?raw=1").status_code, 400)
        self.assertEqual(self.freeze(uuid.uuid4(), surplus=True).status_code, 400)
        self.assertEqual(self.post(
            self.owner_client, self.url + "freeze/", {}).status_code, 400)
        row = self.freeze(uuid.uuid4()).json()
        manifest = PublicationFrozenManifest.objects.get(pk=row["id"])
        QuerySet.update(PublicationFrozenManifest.objects.filter(pk=manifest.pk),
                        manifest_digest="f" * 64)
        self.assertEqual(self.owner_client.get(
            BASE + "publication/plans/" + row["id"] + "/").status_code, 409)
