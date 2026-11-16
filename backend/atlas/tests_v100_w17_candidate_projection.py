"""Turn 08 W17-01: exact private candidate projection, never public Apply."""
import uuid

from django.test import TestCase, override_settings

from .cms_content import digest
from .cms_content_models import ContentRevision, ContentState
from .cms_publication_preparation_models import PublicationPreparationDossier
from .models import StudyActivity
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExactCandidateProjectionTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.state = self.proposal("brain-anatomical-entity", "W17_SELECTED_PRIVATE")
        self.other = self.proposal("brain-anatomical-entity", "W17_UNSELECTED_PRIVATE")

    def proposal(self, kind, name):
        data = {"name_en": name}
        state = ContentState.objects.create(kind=kind, canonical_digest=digest({}))
        revision = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest=digest({}),
            payload=data, payload_digest=digest(data), dependency_digest=digest({}),
            actor=self.owner, status="draft",
        )
        state.current_revision = revision
        state.version = 1
        state.save(update_fields=["current_revision", "version"])
        return state

    def selection_and_dossier(self, client=None):
        client = client or self.client
        inventory = client.get(BASE + "publication/preflight/?domain=brain")
        self.assertEqual(inventory.status_code, 200, inventory.content[:300])
        candidate = next(x for x in inventory.json()["results"]
                         if x["resource_id"] == str(self.state.pk))
        chosen = self.post(client, "publication/selections/", {
            "domain": "brain", "request_key": str(uuid.uuid4()),
            "entries": [{
                "kind": self.state.kind, "resource_id": str(self.state.pk),
                "expected_digest": candidate["proposal_digest"],
            }],
        })
        self.assertEqual(chosen.status_code, 201, chosen.content[:300])
        selected = chosen.json()
        dossier = self.post(client, f'publication/selections/{selected["id"]}/prepare/', {
            "request_key": str(uuid.uuid4()),
            "selection_digest": selected["selection_digest"],
        })
        self.assertEqual(dossier.status_code, 201, dossier.content[:300])
        return dossier.json()

    def test_preview_is_dossier_bound_exact_and_never_public(self):
        dossier = self.selection_and_dossier()
        events = StudyActivity.objects.count()
        response = self.client.get(BASE +
            f'publication/preparations/{dossier["id"]}/candidate-preview/')
        self.assertEqual(response.status_code, 200, response.content[:350])
        data = response.json()
        self.assertEqual(data["schema"], "cms-private-candidate-projection-v1")
        self.assertEqual(data["selection_digest"], dossier["selection_digest"])
        self.assertEqual(data["dossier_digest"], dossier["dossier_digest"])
        self.assertEqual(data["scope"], "authorized_private_candidate_only")
        self.assertFalse(data["public_projection"]["available"])
        self.assertIsNone(data["public_projection"]["payload"])
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["resource_id"], str(self.state.pk))
        self.assertEqual(data["items"][0]["revision_id"], self.state.current_revision_id)
        self.assertEqual(data["items"][0]["display"], {"name_en": "W17_SELECTED_PRIVATE"})
        self.assertNotIn("W17_UNSELECTED_PRIVATE", response.content.decode())
        self.assertEqual(StudyActivity.objects.count(), events)
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)
        self.assertEqual(ContentState.objects.get(pk=self.state.pk).publication, "never_published")

    def test_stale_candidate_is_not_projected_and_immutable_receipt_survives(self):
        dossier = self.selection_and_dossier()
        data = {"name_en": "W17_CHANGED_DRAFT"}
        replacement = ContentRevision.objects.create(
            state=self.state, sequence=2, base_version=1, base_digest=digest({}),
            payload=data, payload_digest=digest(data), dependency_digest=digest({}),
            actor=self.owner, status="draft",
        )
        self.state.current_revision, self.state.version = replacement, 2
        self.state.save(update_fields=["current_revision", "version"])
        response = self.client.get(BASE +
            f'publication/preparations/{dossier["id"]}/candidate-preview/')
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("W17_CHANGED_DRAFT", response.content.decode())
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)

    def test_foreign_dossier_idor_and_preview_capability_denial(self):
        dossier = self.selection_and_dossier()
        other = self.sign_in(self.user("w17-foreign", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_brain_preview",
            "cms_publication_validate_brain", "cms_publication_select_brain",
        )))
        self.assertEqual(other.get(BASE +
            f'publication/preparations/{dossier["id"]}/candidate-preview/').status_code, 404)
        denied = self.sign_in(self.user("w17-no-preview", staff=True, caps=(
            "cms_enter", "cms_brain_view",
            "cms_publication_validate_brain", "cms_publication_select_brain",
        )))
        own = self.selection_and_dossier(denied)
        self.assertEqual(denied.get(BASE +
            f'publication/preparations/{own["id"]}/candidate-preview/').status_code, 403)
