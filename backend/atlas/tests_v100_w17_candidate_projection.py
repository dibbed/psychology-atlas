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

    def test_public_surface_routes_are_real_and_missing_consumers_are_explicit(self):
        from django.urls import resolve, Resolver404
        from .cms_domains import DOMAIN_SPECS
        from .cms_learning_fingerprint import KIND_MODELS
        from .cms_publication_candidate_preview import _PUBLIC_SURFACE_ROUTES

        kinds = set(KIND_MODELS) | {
            kind for kind, spec in DOMAIN_SPECS.items()
            if spec["domain"] in ("brain", "assessment")
        }
        self.assertEqual(set(_PUBLIC_SURFACE_ROUTES), kinds)
        self.assertIsNone(_PUBLIC_SURFACE_ROUTES["brain-network"]["detail"])
        self.assertIsNone(_PUBLIC_SURFACE_ROUTES["flashcard"]["detail"])
        self.assertEqual(_PUBLIC_SURFACE_ROUTES["flashcard"]["list"], "/api/flashcards/")
        self.assertEqual(_PUBLIC_SURFACE_ROUTES["quiz"]["detail"], "/api/quizzes/{slug}/")
        self.assertEqual(_PUBLIC_SURFACE_ROUTES["assessment-instrument"]["graph"], "/api/concept-map/")
        for kind, routes in _PUBLIC_SURFACE_ROUTES.items():
            self.assertIsNone(routes.get("compare"), kind)
            for surface, route in routes.items():
                if route is None:
                    continue
                with self.subTest(kind=kind, surface=surface, route=route):
                    self.assertTrue(route.startswith("/api/"))
                    self.assertNotIn("PRIVATE", route)
                    concrete = route.replace("{slug}", "synthetic-qa")
                    try:
                        match = resolve(concrete)
                    except Resolver404:
                        self.fail(f"Imaginary public endpoint: {kind} {surface} {concrete}")
                    self.assertIsNotNone(match.func)

    def test_public_root_paths_are_typed_and_cover_supported_editorial_kinds(self):
        from .cms_domains import DOMAIN_SPECS
        from .cms_publication_surface_parity import _PUBLIC_ROOT_PATHS
        editorial = {
            kind for kind, spec in DOMAIN_SPECS.items()
            if spec["domain"] in ("brain", "assessment")
        }
        self.assertEqual(editorial, set(_PUBLIC_ROOT_PATHS))
        for kind, paths in _PUBLIC_ROOT_PATHS.items():
            model = DOMAIN_SPECS[kind]["model"]
            for path in paths:
                with self.subTest(kind=kind, path=path):
                    self.assertLessEqual(len(path), 3)
                    current = model
                    for field_name in path:
                        field = current._meta.get_field(field_name)
                        self.assertTrue(field.is_relation and field.many_to_one)
                        current = field.remote_field.model
                    expected = ("BrainAnatomicalEntity" if kind.startswith("brain-")
                                else "AssessmentInstrument")
                    self.assertEqual(current.__name__, expected)

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
                contract = entry["public_reader_contract"]
                self.assertFalse(contract["public_candidate_payload_available"])
                self.assertEqual(contract["surfaces"]["detail"]["status"], "existing_reader")
                self.assertEqual(contract["surfaces"]["search"]["route"], "/api/search/")
                self.assertEqual(contract["surfaces"]["graph"]["route"], "/api/concept-map/")
                self.assertEqual(contract["surfaces"]["compare"]["status"], "not_implemented_for_kind")
                self.assertIsNone(contract["surfaces"]["compare"]["route"])
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

    def test_unpublished_brain_alias_reports_actual_current_public_parent_not_draft(self):
        from .models import (SourceReference, BrainAnatomicalEntity,
                             BrainAnatomicalEntitySource)
        from .brain_publication import public_anatomy
        src = SourceReference.objects.create(
            title="W17 NONSCIENTIFIC source", citation="Synthetic test source only",
            doi="10.1234/synthetic-w17", verification_status="source_checked",
        )
        parent = BrainAnatomicalEntity.objects.create(
            slug="w17-visible-parent", name_en="Synthetic public existing parent",
            kind="region", laterality="not_established", is_active=True,
        )
        BrainAnatomicalEntitySource.objects.create(
            entity=parent, source=src, note="Synthetic identity source",
        )
        parent.review_status = "reviewed"
        parent.save(update_fields=["review_status"])
        self.assertTrue(public_anatomy().filter(pk=parent.pk).exists())
        payload = {
            "entity": parent.pk, "source": src.pk,
            "text": "W17 SECRET PRIVATE ALIAS",
            "language": "en", "alias_type": "alternative",
            "source_note": "Synthetic proposal only",
        }
        self.state = ContentState.objects.create(
            kind="brain-anatomical-alias", canonical_digest=digest({}),
        )
        revision = ContentRevision.objects.create(
            state=self.state, sequence=1, base_version=0,
            base_digest=digest({}), payload=payload,
            payload_digest=digest(payload), dependency_digest=digest({}),
            actor=self.owner, status="draft",
        )
        self.state.current_revision, self.state.version = revision, 1
        self.state.save(update_fields=["current_revision", "version"])
        dossier = self.selection_and_dossier(domain="brain")
        response = self.client.get(
            BASE + f'publication/preparations/{dossier["id"]}/candidate-preview/')
        self.assertEqual(response.status_code, 200, response.content[:350])
        impact = response.json()["impact_preview"]["items"][0]
        witness = impact["current_public_anchor"]
        self.assertEqual(witness["status"], "visible_public_root")
        self.assertEqual(witness["root_type"], "brain_anatomical_entity")
        self.assertEqual(witness["root_count"], 1)
        self.assertEqual(witness["visible_count"], 1)
        self.assertFalse(witness["candidate_public"])
        self.assertEqual(
            impact["public_reader_contract"]["surfaces"]["graph"]["route"],
            "/api/concept-map/",
        )
        self.assertNotIn("W17 SECRET PRIVATE ALIAS", str(impact))
        self.assertFalse(self.state.publication == "current")
        # Real public consumers of the existing parent stay unchanged.
        detail = self.client.get("/api/brain-anatomy/w17-visible-parent/")
        self.assertEqual(detail.status_code, 200)
        search = self.client.get("/api/search/?q=w17-visible-parent")
        self.assertEqual(search.status_code, 200)
        self.assertIn("w17-visible-parent",
            [item["slug"] for item in search.json()["brain_entities"]])
        graph = self.client.get("/api/concept-map/")
        self.assertEqual(graph.status_code, 200)
        self.assertIn("brain_anatomy:w17-visible-parent",
            [node["id"] for node in graph.json()["nodes"]])
        for response in (detail, search, graph):
            self.assertNotIn("W17 SECRET PRIVATE ALIAS", response.content.decode())

    def test_unpublished_assessment_alias_parent_uses_actual_public_registry(self):
        from .models import SourceReference, AssessmentInstrument, AssessmentSource
        from .assessment_views import public_sets
        src = SourceReference.objects.create(
            title="W17 NONSCIENTIFIC assessment source",
            citation="Synthetic fixture only",
            doi="10.1234/w17assessment", verification_status="source_checked",
        )
        instrument = AssessmentInstrument.objects.create(
            slug="w17-existing-assessment", name_en="Synthetic assessment",
            is_active=True,
        )
        AssessmentSource.objects.create(
            instrument=instrument, source=src, note="Synthetic identity source",
        )
        instrument.review_status = "reviewed"
        instrument.save(update_fields=["review_status"])
        self.assertTrue(public_sets()["instruments"].filter(pk=instrument.pk).exists())
        payload = {
            "instrument": instrument.pk, "source": src.pk,
            "source_note": "Synthetic only", "text": "W17 PRIVATE ASSESSMENT ALIAS",
            "language": "en", "alias_type": "acronym",
        }
        state = ContentState.objects.create(
            kind="assessment-alias", canonical_digest=digest({}),
        )
        revision = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest=digest({}),
            payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), status="draft", actor=self.owner,
        )
        state.current_revision, state.version = revision, 1
        state.save(update_fields=["current_revision", "version"])
        self.state = state
        dossier = self.selection_and_dossier(domain="assessment")
        preview = self.client.get(
            BASE + f'publication/preparations/{dossier["id"]}/candidate-preview/')
        self.assertEqual(preview.status_code, 200, preview.content[:400])
        impact = preview.json()["impact_preview"]["items"][0]
        witness = impact["current_public_anchor"]
        self.assertEqual(witness["status"], "visible_public_root")
        self.assertEqual(witness["root_type"], "assessment_instrument")
        self.assertEqual(witness["visible_count"], 1)
        self.assertFalse(witness["candidate_public"])
        self.assertIsNone(preview.json()["public_projection"]["payload"])
        self.assertNotIn("W17 PRIVATE ASSESSMENT ALIAS", str(impact))
        detail = self.client.get("/api/assessments/w17-existing-assessment/")
        self.assertEqual(detail.status_code, 200)
        search = self.client.get("/api/search/?q=w17-existing-assessment")
        self.assertEqual(search.status_code, 200)
        self.assertIn("w17-existing-assessment",
            [item["slug"] for item in search.json()["assessments"]])
        graph = self.client.get("/api/concept-map/")
        self.assertEqual(graph.status_code, 200)
        self.assertIn("assessment:w17-existing-assessment",
            [node["id"] for node in graph.json()["nodes"]])
        for response in (detail, search, graph):
            self.assertNotIn("W17 PRIVATE ASSESSMENT ALIAS", response.content.decode())

    def test_retargeted_alias_witness_counts_old_and_new_parents_without_mutation(self):
        from .models import (SourceReference, BrainAnatomicalEntity,
                             BrainAnatomicalAlias)
        from .cms_content import canonical_snapshot
        from .cms_publication_surface_parity import _root_candidates, public_root_witnesses

        src = SourceReference.objects.create(
            title="Synthetic source", citation="Synthetic",
            doi="10.1234/alias-retarget", verification_status="source_checked",
        )
        old = BrainAnatomicalEntity.objects.create(
            slug="w17-original-parent", name_en="Synthetic old",
            kind="region", laterality="not_established", is_active=True)
        new = BrainAnatomicalEntity.objects.create(
            slug="w17-proposed-parent", name_en="Synthetic new",
            kind="region", laterality="not_established", is_active=True)
        alias = BrainAnatomicalAlias.objects.create(
            entity=old, source=src, text="synthetic-old-alias",
            language="en", alias_type="alternative",
            source_note="Synthetic attribution",
        )
        base_digest = digest(canonical_snapshot("brain-anatomical-alias", alias))
        state = ContentState.objects.create(
            kind="brain-anatomical-alias",
            canonical_pk=alias.pk, canonical_digest=base_digest,
        )
        payload = {"entity": new.pk}
        revision = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest=base_digest,
            payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), status="draft", actor=self.owner,
        )
        state.current_revision, state.version = revision, 1
        state.save(update_fields=["current_revision", "version"])
        ids, resolution = _root_candidates("brain-anatomical-alias", state)
        self.assertEqual(ids, tuple(sorted((old.pk, new.pk))))
        self.assertEqual(resolution, "resolved")
        before = BrainAnatomicalAlias.objects.get(pk=alias.pk).entity_id
        public = public_root_witnesses(
            "brain", [{"kind": "brain-anatomical-alias"}], [state])
        self.assertEqual(public[0]["root_count"], 2)
        self.assertEqual(public[0]["visible_count"], 0)
        self.assertEqual(public[0]["status"], "hidden_public_root")
        self.assertFalse(public[0]["post_apply_projection_available"])
        self.assertEqual(BrainAnatomicalAlias.objects.get(pk=alias.pk).entity_id, before)

    def test_public_alias_pagination_cannot_claim_global_uniqueness(self):
        from .cms_public_alias_disambiguation import public_exact_alias_disambiguation
        rows = [
            {"slug": f"synthetic-{idx}", "aliases": [],
             "aliases_truncated": False}
            for idx in range(10)
        ]
        data = public_exact_alias_disambiguation("synthetic", rows, [])
        self.assertEqual(data["status"], "more_than_limit")
        self.assertTrue(data["truncated"])
        self.assertEqual(data["visible_count"], 0)
        # The only disclosed aliases are those in the already-public payload,
        # never follow-up unbounded database queries to claim completeness.
        limited = public_exact_alias_disambiguation(
            "synthetic", [{"slug": "safe-public",
                           "aliases": [{"text": "synthetic"}],
                           "aliases_truncated": True}], [])
        self.assertEqual(limited["status"], "more_than_limit")
        self.assertTrue(limited["truncated"])
        self.assertEqual(limited["matches"],
                         [{"domain": "brain_anatomy", "slug": "safe-public"}])

    def test_public_search_exact_alias_ambiguity_only_counts_public_parents(self):
        from .models import (SourceReference, BrainAnatomicalEntity,
                             BrainAnatomicalEntitySource, BrainAnatomicalAlias,
                             AssessmentInstrument, AssessmentSource, AssessmentAlias)
        source = SourceReference.objects.create(
            title="W17 fabricated fixture reference",
            citation="Synthetic only, not a scientific claim",
            url="https://example.org/synthetic-only", verification_status="source_checked",
        )
        brain = BrainAnatomicalEntity.objects.create(
            slug="w17-public-brain-alias-parent", name_en="Synthetic brain",
            kind="structure", laterality="not_established", is_active=True)
        BrainAnatomicalEntitySource.objects.create(
            entity=brain, source=source, note="Synthetic source")
        brain.review_status = "reviewed"
        brain.save(update_fields=["review_status"])
        alias = BrainAnatomicalAlias.objects.create(
            entity=brain, source=source, text="w17-collision",
            language="en", alias_type="abbreviation",
            review_status="reviewed", source_note="Synthetic only")
        instrument = AssessmentInstrument.objects.create(
            slug="w17-public-assessment-alias-parent",
            name_en="Synthetic assessment", is_active=True)
        AssessmentSource.objects.create(
            instrument=instrument, source=source, note="Synthetic source")
        instrument.review_status = "reviewed"
        instrument.save(update_fields=["review_status"])
        AssessmentAlias.objects.create(
            instrument=instrument, source=source, source_note="Synthetic only",
            text="w17-collision", language="en", alias_type="acronym",
            review_status="reviewed")

        query = self.client.get("/api/search/", {"q": "w17-collision"})
        self.assertEqual(query.status_code, 200, query.content[:350])
        status = query.json()["alias_disambiguation"]
        self.assertEqual(status["status"], "multiple_exact_public_matches")
        self.assertEqual(status["visible_count"], 2)
        self.assertEqual(status["scope"], "public_brain_assessment_visible_search_page_only")
        self.assertFalse(status["truncated"])
        self.assertEqual(
            {(row["domain"], row["slug"]) for row in status["matches"]},
            {("brain_anatomy", brain.slug), ("assessment", instrument.slug)},
        )
        self.assertEqual([x["slug"] for x in query.json()["brain_entities"]], [brain.slug])
        self.assertEqual([x["slug"] for x in query.json()["assessments"]], [instrument.slug])

        # Existing public parent stays visible; unreviewed alias no longer
        # contributes to the exact-match public ambiguity.
        alias.review_status = "unreviewed"
        alias.save(update_fields=["review_status"])
        after = self.client.get("/api/search/", {"q": "w17-collision"}).json()
        self.assertEqual(after["alias_disambiguation"]["status"],
                         "one_exact_public_match")
        self.assertEqual(after["alias_disambiguation"]["visible_count"], 1)
        self.assertNotIn(brain.slug, [row["slug"] for row in after["brain_entities"]])
        self.assertNotIn("W17 SECRET", str(after))

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
