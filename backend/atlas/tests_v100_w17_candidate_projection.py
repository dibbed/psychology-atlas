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

    def selection_and_dossier(self, client=None, domain="brain"):
        client = client or self.client
        inventory = client.get(BASE + f"publication/preflight/?domain={domain}")
        self.assertEqual(inventory.status_code, 200, inventory.content[:300])
        candidate = next(x for x in inventory.json()["results"]
                         if x["resource_id"] == str(self.state.pk))
        chosen = self.post(client, "publication/selections/", {
            "domain": domain, "request_key": str(uuid.uuid4()),
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

    def test_private_reader_topology_covers_every_supported_selected_kind(self):
        from .cms_domains import DOMAIN_SPECS
        from .cms_learning_fingerprint import KIND_MODELS
        from .cms_publication_candidate_preview import _PUBLIC_READER_PATHS
        selected = set(KIND_MODELS) | {
            kind for kind, spec in DOMAIN_SPECS.items()
            if spec["domain"] in ("brain", "assessment")
        }
        self.assertEqual(set(_PUBLIC_READER_PATHS), selected)
        self.assertTrue(all("detail" in _PUBLIC_READER_PATHS[kind] for kind in selected))
        self.assertTrue(all(
            set(readers) <= {"detail", "search", "graph", "compare"}
            for readers in _PUBLIC_READER_PATHS.values()))

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

    def test_private_public_surface_impact_is_revision_pinned_and_non_authoritative(self):
        for domain, kind, expected_search in (
            ("brain", "brain-anatomical-entity", "global_search.brain_entities"),
            ("assessment", "assessment-instrument", "global_search.assessments"),
        ):
            with self.subTest(domain=domain):
                self.state = self.proposal(kind, f"W17_{domain.upper()}_PRIVATE")
                dossier = self.selection_and_dossier(domain=domain)
                result = self.client.get(BASE +
                    f'publication/preparations/{dossier["id"]}/candidate-preview/')
                self.assertEqual(result.status_code, 200, result.content[:300])
                impact = result.json()["impact_preview"]
                self.assertEqual(impact["schema"], "cms-private-public-surface-impact-v1")
                self.assertEqual(impact["dossier_digest"], dossier["dossier_digest"])
                self.assertEqual(len(impact["items"]), 1)
                entry = impact["items"][0]
                self.assertEqual(entry["revision_id"], self.state.current_revision_id)
                self.assertEqual(entry["resource_id"], str(self.state.pk))
                self.assertEqual(entry["readers"]["search"], expected_search)
                self.assertEqual(entry["change_intent"], "create")
                self.assertIn("name_en", entry["change_footprint"]["changed_public_fields"])
                self.assertEqual(entry["change_footprint"]["surface_field_names"]["search"], ["name_en"])
                self.assertEqual(entry["change_footprint"]["surface_field_names"]["graph"], ["name_en"])
                self.assertFalse(entry["before_public_visibility"])
                self.assertEqual(entry["after_apply"], "not_available_without_frozen_authority")
                self.assertFalse(impact["public_effect"])
                self.assertNotIn(f"W17_{domain.upper()}_PRIVATE", str(impact))
                self.assertIsNone(result.json()["public_projection"]["payload"])
                self.assertEqual(ContentState.objects.get(pk=self.state.pk).publication,
                                 "never_published")

    def test_edit_preview_compares_actual_canonical_base_without_writing_it(self):
        from .cms_content import canonical_snapshot
        from .models import BrainAnatomicalEntity
        canonical = BrainAnatomicalEntity.objects.create(
            slug="w17-original", name_en="Original synthetic brain label",
            kind="region", laterality="not_established", is_active=False,
        )
        base = digest(canonical_snapshot("brain-anatomical-entity", canonical))
        payload = {"name_en": "W17 PRIVATE PROPOSED LABEL"}
        state = ContentState.objects.create(
            kind="brain-anatomical-entity", canonical_pk=canonical.pk,
            canonical_digest=base,
        )
        revision = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest=base,
            payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), status="draft", actor=self.owner,
        )
        state.version, state.current_revision = 1, revision
        state.save(update_fields=["version", "current_revision"])
        self.state = state
        dossier = self.selection_and_dossier(domain="brain")
        response = self.client.get(BASE +
            f'publication/preparations/{dossier["id"]}/candidate-preview/')
        self.assertEqual(response.status_code, 200, response.content[:350])
        impact = response.json()["impact_preview"]["items"][0]
        self.assertEqual(impact["change_intent"], "update")
        self.assertEqual(impact["change_footprint"]["changed_public_fields"], ["name_en"])
        self.assertFalse(impact["before_public_visibility"])
        canonical.refresh_from_db()
        self.assertEqual(canonical.name_en, "Original synthetic brain label")
        self.assertFalse(canonical.is_active)
        self.assertEqual(ContentState.objects.get(pk=state.pk).publication, "never_published")

    def test_learning_exact_candidate_impact_is_read_only_and_redacts_answers(self):
        from .models import Category, Disorder, Quiz, QuizQuestion, QuizChoice
        category = Category.objects.create(slug="w17-learning-parent", name_en="Synthetic")
        disorder = Disorder.objects.create(
            category=category, slug="w17-learning-parent", name_en="Synthetic",
            is_active=True)
        quiz = Quiz.objects.create(
            slug="w17-learning-draft", title="Synthetic private quiz",
            disorder=disorder, is_active=False, seed_managed=False,
        )
        question = QuizQuestion.objects.create(quiz=quiz, prompt="W17_SECRET_QUESTION")
        QuizChoice.objects.create(
            question=question, text="W17_SECRET_TRUE", is_correct=True, is_active=True)
        QuizChoice.objects.create(
            question=question, text="W17_SECRET_FALSE", is_correct=False, is_active=True)
        inventory = self.client.get(BASE + "publication/preflight/?domain=learning")
        self.assertEqual(inventory.status_code, 200)
        entry = next(item for item in inventory.json()["results"]
                     if item["kind"] == "quiz" and item["resource_id"] == quiz.pk)
        selected = self.post(self.client, "publication/selections/", {
            "domain": "learning", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": "quiz", "resource_id": quiz.pk,
                         "expected_digest": entry["content_digest"]}],
        })
        self.assertEqual(selected.status_code, 201)
        dossier = self.post(self.client,
            f'publication/selections/{selected.json()["id"]}/prepare/', {
                "request_key": str(uuid.uuid4()),
                "selection_digest": selected.json()["selection_digest"],
            })
        self.assertEqual(dossier.status_code, 201, dossier.content[:300])
        before_learner = StudyActivity.objects.count()
        result = self.client.get(BASE +
            f'publication/preparations/{dossier.json()["id"]}/candidate-preview/')
        self.assertEqual(result.status_code, 200, result.content[:300])
        impact = result.json()["impact_preview"]["items"][0]
        self.assertEqual(impact["kind"], "quiz")
        self.assertEqual(impact["change_intent"], "potential_activation")
        self.assertFalse(impact["before_public_visibility"])
        self.assertEqual(impact["change_footprint"]["changed_public_fields"], [])
        for private in ("W17_SECRET_QUESTION", "W17_SECRET_TRUE", "W17_SECRET_FALSE"):
            self.assertNotIn(private, result.content.decode())
        self.assertEqual(StudyActivity.objects.count(), before_learner)
        self.assertFalse(Quiz.objects.get(pk=quiz.pk).is_active)

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
