"""P12 first contract: scoped, read-only CaseRevision graph inspection.

These fixtures are synthetic educational material, never real patient records.
"""
from django.test import TestCase, override_settings

from .models import (
    CaseAttempt, CaseAttemptAnswer, CaseAttemptEvent, CaseChoice, CaseQuestion,
    CaseRevision, CaseStep, CaseTransition, ClinicalCase, StudyActivity,
)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CaseGraphPreviewContractTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client = self.sign_in(self.owner)
        self.case = ClinicalCase.objects.create(
            slug="p12-synthetic-case", title="P12 Synthetic education",
            patient_summary="Fictional educational narrative", structure_mode="branching",
        )
        self.revision = CaseRevision.objects.create(
            case=self.case, version=1, status=CaseRevision.Status.PUBLISHED,
            title="First fictional revision", patient_summary="Fictional only",
        )
        self.first = CaseStep.objects.create(
            case=self.case, revision=self.revision, stable_key="intro",
            node_kind=CaseStep.NodeKind.INFORMATION,
            title="Fictional introduction", narrative="A synthetic learning prompt",
            sort_order=0,
        )
        self.end = CaseStep.objects.create(
            case=self.case, revision=self.revision, stable_key="end",
            node_kind=CaseStep.NodeKind.TERMINAL,
            title="Fictional terminal", narrative="Synthetic completion",
            sort_order=1,
        )
        CaseTransition.objects.create(
            revision=self.revision, source_step=self.first, target_step=self.end,
            outcome=CaseTransition.Outcome.CONTINUE,
        )
        self.revision.entry_step = self.first
        self.revision.save(update_fields=["entry_step"])
        self.case.current_revision = self.revision
        self.case.save(update_fields=["current_revision"])

    def url(self, revision=None, case=None):
        return BASE + f"cases/{case or self.case.pk}/revisions/{revision or self.revision.pk}/graph/"

    def test_graph_is_private_read_only_and_reuses_validator(self):
        attempt = CaseAttempt.objects.create(
            user=self.normal, case=self.case, revision=self.revision,
            current_step=self.first, status=CaseAttempt.Status.IN_PROGRESS,
        )
        counts = (CaseAttempt.objects.count(), StudyActivity.objects.count())
        response = self.owner_client.get(self.url())
        self.assertEqual(response.status_code, 200, response.content[:400])
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["issues"], [])
        self.assertEqual(data["entry_step_id"], self.first.pk)
        self.assertEqual([step["stable_key"] for step in data["steps"]], ["intro", "end"])
        self.assertEqual(len(data["transitions"]), 1)
        self.assertEqual(data["transitions"][0]["target_step_id"], self.end.pk)
        self.assertFalse(data["simulation_creates_attempt"])
        self.assertFalse(data["publication_available"])
        self.assertNotIn("user_id", data)
        self.assertNotIn("attempts", data)
        self.assertEqual(counts, (CaseAttempt.objects.count(), StudyActivity.objects.count()))
        attempt.refresh_from_db()
        self.assertEqual(attempt.revision_id, self.revision.pk)

    def test_revision_fingerprint_tracks_draft_edits_without_mutating_published_evidence(self):
        graph = self.owner_client.get(self.url())
        validation_url = BASE + f"cases/{self.case.pk}/revisions/{self.revision.pk}/validate/"
        validation = self.owner_client.get(validation_url)
        self.assertEqual(graph.status_code, 200)
        self.assertEqual(validation.status_code, 200)
        published_digest = graph.json()["revision_digest"]
        self.assertEqual(validation.json()["revision_digest"], published_digest)
        self.assertRegex(published_digest, r"^[a-f0-9]{64}$")
        self.assertEqual(self.owner_client.get(self.url()).json()["revision_digest"], published_digest)
        self.assertNotIn(self.revision.patient_summary, str(published_digest))

        cloned = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/",
            etag=graph["ETag"])
        self.assertEqual(cloned.status_code, 201, cloned.content[:300])
        draft_id = cloned.json()["revision_id"]
        draft_url = self.url(revision=draft_id)
        before = self.owner_client.get(draft_url).json()["revision_digest"]
        metadata = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{draft_id}/metadata/",
            {"title": "Second fictional revision"}, etag=cloned["ETag"])
        self.assertEqual(metadata.status_code, 200, metadata.content[:300])
        after_metadata = self.owner_client.get(draft_url).json()["revision_digest"]
        self.assertNotEqual(before, after_metadata)
        self.assertEqual(self.owner_client.get(BASE +
            f"cases/{self.case.pk}/revisions/{draft_id}/validate/").json()["revision_digest"],
            after_metadata)
        draft_step = CaseStep.objects.get(revision_id=draft_id, stable_key="intro")
        draft_step.narrative = "Updated fictional step story"
        draft_step.save(update_fields=["narrative"])
        after_graph = self.owner_client.get(draft_url).json()["revision_digest"]
        self.assertNotEqual(after_metadata, after_graph)
        self.assertEqual(self.owner_client.get(self.url()).json()["revision_digest"], published_digest)
        self.assertEqual(CaseAttempt.objects.count(), 0)
        self.assertEqual(StudyActivity.objects.count(), 0)

    def test_information_step_rejects_hidden_choice_conditioned_edge(self):
        from .case_graph import validate_case_revision_graph
        question = CaseQuestion.objects.create(
            step=self.first, prompt="Synthetic hidden decision",
            is_active=False,
        )
        hidden_choice = CaseChoice.objects.create(
            question=question, text="Hidden synthetic branch", is_active=True,
        )
        CaseTransition.objects.create(
            revision=self.revision, source_step=self.first,
            choice=hidden_choice, target_step=self.end,
            outcome=CaseTransition.Outcome.CONTINUE, is_active=True,
        )
        issues = validate_case_revision_graph(self.revision)
        self.assertIn(
            f"step:{self.first.pk}:information_has_choice_transition", issues,
        )
        self.assertEqual(self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/simulate/",
            {"choice_ids": []}).status_code, 409)

    def test_graph_contract_accepts_800_questions_and_rejects_801(self):
        from .cms_case_graph_editor import _graph_contract
        from .cms_policy import CMSFailure
        def candidate(count):
            return {
                "entry_step_key": "intro", "rubric_version": 0,
                "steps": [{"key": "intro", "kind": "information",
                           "title": "Synthetic introduction",
                           "narrative": "Fictional draft", "is_active": True}],
                "questions": [{"key": f"q{n}", "step_key": "intro",
                               "prompt": "Fictional question", "explanation": "",
                               "dimension_key": None, "is_active": True}
                              for n in range(count)],
                "choices": [], "transitions": [], "scoring_dimensions": [],
            }
        self.assertEqual(len(_graph_contract(candidate(800))["questions"]), 800)
        with self.assertRaises(CMSFailure):
            _graph_contract(candidate(801))

    def test_case_archive_blocks_new_attempts_but_resumes_prior_in_progress(self):
        from rest_framework.exceptions import ValidationError
        from .services import start_or_resume_case_attempt
        attempt, created = start_or_resume_case_attempt(user=self.normal, clinical_case=self.case)
        self.assertTrue(created)
        self.case.is_active = False
        self.case.save(update_fields=["is_active"])
        resumed, created = start_or_resume_case_attempt(user=self.normal, clinical_case=self.case)
        self.assertFalse(created)
        self.assertEqual(resumed.pk, attempt.pk)
        with self.assertRaises(ValidationError):
            start_or_resume_case_attempt(user=self.owner, clinical_case=self.case)
        self.assertEqual(CaseAttempt.objects.count(), 1)

    def test_invalid_draft_stays_private_and_does_not_change_published_history(self):
        draft = CaseRevision.objects.create(
            case=self.case, version=2, status=CaseRevision.Status.DRAFT,
            title="Synthetic draft only",
        )
        CaseStep.objects.create(
            case=self.case, revision=draft, stable_key="orphan",
            node_kind=CaseStep.NodeKind.INFORMATION, narrative="Unreachable", sort_order=0,
        )
        result = self.owner_client.get(self.url(revision=draft.pk))
        self.assertEqual(result.status_code, 200, result.content[:300])
        self.assertFalse(result.json()["valid"])
        self.assertIn("entry_step_missing", result.json()["issues"])
        self.case.refresh_from_db()
        self.assertEqual(self.case.current_revision_id, self.revision.pk)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, CaseRevision.Status.PUBLISHED)

    def test_mfa_scope_wrong_case_and_mutating_method_are_denied(self):
        scoped = self.user("p12-view-only", staff=True, caps=("cms_enter", "cms_cases_view"))
        scoped_client = self.sign_in(scoped)
        self.assertEqual(scoped_client.get(self.url()).status_code, 403)
        self.assertEqual(self.owner_client.get(self.url(case=self.case.pk + 999)).status_code, 404)
        self.assertEqual(self.owner_client.get(self.url(), {"unsupported": "1"}).status_code, 400)
        self.assertEqual(self.post(self.owner_client, self.url()[len(BASE):]).status_code, 405)

    def test_clone_to_draft_preserves_published_revision_and_pinned_attempt(self):
        attempt = CaseAttempt.objects.create(
            user=self.normal, case=self.case, revision=self.revision,
            current_step=self.first, status=CaseAttempt.Status.IN_PROGRESS,
        )
        original = list(self.revision.steps.values_list("pk", "stable_key", "narrative"))
        tag = self.owner_client.get(self.url())["ETag"]
        result = self.post(
            self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/",
            etag=tag,
        )
        self.assertEqual(result.status_code, 201, result.content[:400])
        draft = CaseRevision.objects.get(pk=result.json()["revision_id"])
        self.assertEqual(draft.status, CaseRevision.Status.DRAFT)
        self.assertEqual(draft.version, self.revision.version + 1)
        self.assertEqual(draft.steps.count(), 2)
        self.assertEqual(draft.transitions.count(), 1)
        self.assertNotIn(self.first.pk, set(draft.steps.values_list("pk", flat=True)))
        self.assertEqual(draft.entry_step.stable_key, self.first.stable_key)
        self.assertEqual(list(self.revision.steps.values_list("pk", "stable_key", "narrative")), original)
        self.case.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.case.current_revision_id, self.revision.pk)
        self.assertEqual(attempt.revision_id, self.revision.pk)
        self.assertEqual(attempt.current_step_id, self.first.pk)
        self.assertEqual(CaseAttempt.objects.count(), 1)
        self.assertEqual(self.post(
            self.owner_client, f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/",
            etag=tag,
        ).status_code, 409)

    def test_draft_metadata_update_requires_etag_and_never_edits_published(self):
        source_tag = self.owner_client.get(self.url())["ETag"]
        clone = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/", etag=source_tag)
        self.assertEqual(clone.status_code, 201, clone.content[:400])
        draft_id = clone.json()["revision_id"]
        url = f"cases/{self.case.pk}/revisions/{draft_id}/metadata/"
        self.assertEqual(self.post(self.owner_client, url, {"title": "New draft"}).status_code, 428)
        response = self.post(self.owner_client, url,
            {"title": "P12 fictional edit"}, etag=clone["ETag"])
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(CaseRevision.objects.get(pk=draft_id).title, "P12 fictional edit")
        self.assertEqual(CaseRevision.objects.get(pk=self.revision.pk).title, "First fictional revision")
        self.assertEqual(self.post(self.owner_client, url,
            {"title": "Stale edit"}, etag=clone["ETag"]).status_code, 412)
        self.assertEqual(self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/metadata/",
            {"title": "Illegal published edit"}, etag=source_tag).status_code, 409)

    def test_validation_reports_review_and_rights_blockers_without_mutation(self):
        published = self.owner_client.get(
            BASE + f"cases/{self.case.pk}/revisions/{self.revision.pk}/validate/")
        self.assertEqual(published.status_code, 200, published.content[:300])
        tag = self.owner_client.get(self.url())["ETag"]
        cloned = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/", etag=tag)
        self.assertEqual(cloned.status_code, 201)
        draft_id = cloned.json()["revision_id"]
        before_attempts = CaseAttempt.objects.count()
        before_activities = StudyActivity.objects.count()
        response = self.owner_client.get(BASE + f"cases/{self.case.pk}/revisions/{draft_id}/validate/")
        self.assertEqual(response.status_code, 200, response.content[:500])
        data = response.json()
        self.assertTrue(data["graph_valid"])
        self.assertFalse(data["publication_eligible"])
        self.assertIn("SCIENTIFIC_REVIEW_NOT_LINKED", data["publication_blockers"])
        self.assertIn("SOURCE_RIGHTS_REVIEW_NOT_LINKED", data["publication_blockers"])
        self.assertFalse(data["publication_available"])
        self.assertEqual(CaseAttempt.objects.count(), before_attempts)
        self.assertEqual(StudyActivity.objects.count(), before_activities)
        self.assertEqual(CaseRevision.objects.get(pk=draft_id).status, CaseRevision.Status.DRAFT)
        viewer = self.user("p12-validate-viewer", staff=True,
            caps=("cms_enter", "cms_cases_view"))
        self.assertEqual(self.sign_in(viewer).get(
            BASE + f"cases/{self.case.pk}/revisions/{draft_id}/validate/").status_code, 403)
        self.assertEqual(self.owner_client.get(
            BASE + f"cases/{self.case.pk+993}/revisions/{draft_id}/validate/").status_code, 404)

    def test_edit_without_case_view_capability_is_denied(self):
        clone = self.post(
            self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/",
            etag=self.owner_client.get(self.url())["ETag"],
        )
        self.assertEqual(clone.status_code, 201)
        editor = self.user("p12-editor-no-view", staff=True,
            caps=("cms_enter", "cms_cases_edit"))
        client = self.sign_in(editor)
        path = f"cases/{self.case.pk}/revisions/{clone.json()['revision_id']}/metadata/"
        result = self.post(client, path, {"title": "Unauthorized change"}, etag=clone["ETag"])
        self.assertEqual(result.status_code, 403, result.content[:200])
        self.assertEqual(CaseRevision.objects.get(pk=clone.json()["revision_id"]).title, self.revision.title)


    def test_seed_managed_draft_metadata_is_immutable(self):
        """A seed-owned draft must not bypass the graph editor's ownership guard."""
        source_tag = self.owner_client.get(self.url())["ETag"]
        clone = self.post(
            self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/",
            etag=source_tag,
        )
        self.assertEqual(clone.status_code, 201)
        draft_id = clone.json()["revision_id"]
        draft = CaseRevision.objects.get(pk=draft_id)
        draft.seed_managed = True
        draft.save(update_fields=["seed_managed"])
        endpoint = f"cases/{self.case.pk}/revisions/{draft_id}/metadata/"
        result = self.post(self.owner_client, endpoint, {"title": "Forbidden rewrite"}, etag=clone["ETag"])
        self.assertEqual(result.status_code, 409, result.content[:300])
        draft.refresh_from_db()
        self.assertEqual(draft.title, self.revision.title)

    def test_mutation_denied_for_view_only_staff_and_forged_revision_case(self):
        viewer = self.user("p12-view-actor", staff=True,
            caps=("cms_enter", "cms_cases_view", "cms_cases_preview"))
        viewer_client = self.sign_in(viewer)
        tag = self.owner_client.get(self.url())["ETag"]
        clone_path = f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/"
        self.assertEqual(self.post(viewer_client, clone_path, etag=tag).status_code, 403)
        self.assertEqual(self.post(self.owner_client,
            f"cases/{self.case.pk+234}/revisions/{self.revision.pk}/clone/", etag=tag).status_code, 404)
        self.assertEqual(self.post(self.owner_client, clone_path,
            {"unexpected": True}, etag=tag).status_code, 400)
        self.assertEqual(CaseRevision.objects.filter(case=self.case).count(), 1)

    def test_atomic_graph_replacement_builds_valid_branch_and_keeps_pinned_attempt(self):
        attempt = CaseAttempt.objects.create(
            user=self.normal, case=self.case, revision=self.revision,
            current_step=self.first, status=CaseAttempt.Status.IN_PROGRESS,
        )
        tag = self.owner_client.get(self.url())["ETag"]
        cloned = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/", etag=tag)
        self.assertEqual(cloned.status_code, 201, cloned.content[:300])
        draft_id = cloned.json()["revision_id"]
        graph = {
            "entry_step_key": "start", "rubric_version": 1,
            "scoring_dimensions": [
                {"key": "reasoning", "label": "Fictional reasoning", "description": "Learning only", "is_active": True},
            ],
            "steps": [
                {"key": "start", "kind": "decision", "title": "Fictional decision",
                 "narrative": "Fictional scenario", "is_active": True},
                {"key": "end", "kind": "terminal", "title": "Conclusion",
                 "narrative": "Fictional feedback", "is_active": True},
            ],
            "questions": [
                {"key": "question1", "step_key": "start", "prompt": "Choose a learning route?",
                 "explanation": "Fictional", "dimension_key": "reasoning", "is_active": True},
            ],
            "choices": [
                {"key": "choice1", "question_key": "question1", "text": "Option A",
                 "score_value": 2, "feedback": "Fictional", "is_active": True},
                {"key": "choice2", "question_key": "question1", "text": "Option B",
                 "score_value": 1, "feedback": "Fictional", "is_active": True},
            ],
            "transitions": [
                {"source_key": "start", "choice_key": "choice1", "target_key": "end",
                 "outcome": "continue", "is_active": True},
                {"source_key": "start", "choice_key": "choice2", "target_key": None,
                 "outcome": "complete", "is_active": True},
            ],
        }
        path = f"cases/{self.case.pk}/revisions/{draft_id}/graph/edit/"
        result = self.post(self.owner_client, path, graph, etag=cloned["ETag"])
        self.assertEqual(result.status_code, 200, result.content[:400])
        self.assertTrue(result.json()["valid"], result.json())
        self.assertEqual(result.json()["issues"], [])
        revised = self.owner_client.get(self.url(revision=draft_id))
        self.assertEqual(revised.status_code, 200)
        self.assertEqual(len(revised.json()["choices"]), 2)
        self.assertEqual(revised.json()["rubric_version"], 1)
        draft = CaseRevision.objects.get(pk=draft_id)
        self.assertEqual(draft.steps.count(), 2)
        self.assertEqual(draft.scoring_dimensions.count(), 1)
        self.assertEqual(draft.transitions.count(), 2)
        self.assertEqual(self.revision.steps.count(), 2)
        attempt.refresh_from_db()
        self.assertEqual(attempt.current_step_id, self.first.pk)
        self.assertEqual(attempt.revision_id, self.revision.pk)
        self.case.refresh_from_db()
        self.assertEqual(self.case.current_revision_id, self.revision.pk)
        self.assertEqual(StudyActivity.objects.count(), 0)
        self.assertEqual(self.post(self.owner_client, path, graph, etag=cloned["ETag"]).status_code, 412)

    def test_graph_rejects_forgery_and_does_not_destroy_draft_on_invalid_payload(self):
        tag = self.owner_client.get(self.url())["ETag"]
        cloned = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/", etag=tag)
        self.assertEqual(cloned.status_code, 201)
        draft_id = cloned.json()["revision_id"]
        path = f"cases/{self.case.pk}/revisions/{draft_id}/graph/edit/"
        bad = {"entry_step_key": "missing", "rubric_version": 0, "steps": [
            {"key": "start", "kind": "information", "title": "", "narrative": "Fictional", "is_active": True}
        ], "questions": [], "choices": [], "transitions": [
            {"source_key": "start", "choice_key": None, "target_key": "foreign",
             "outcome": "continue", "is_active": True}
        ], "scoring_dimensions": []}
        result = self.post(self.owner_client, path, bad, etag=cloned["ETag"])
        self.assertEqual(result.status_code, 400, result.content[:400])
        self.assertEqual(CaseRevision.objects.get(pk=draft_id).steps.count(), 2)
        self.assertEqual(self.post(self.owner_client, path,
            {"steps": [{"id": self.first.pk}]}, etag=cloned["ETag"]).status_code, 400)
        self.assertEqual(self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/graph/edit/",
            bad, etag=tag).status_code, 409)
        viewer = self.user("p12-graph-viewer", staff=True,
            caps=("cms_enter", "cms_cases_view", "cms_cases_preview"))
        viewer_client = self.sign_in(viewer)
        self.assertEqual(self.post(viewer_client, path, bad, etag=cloned["ETag"]).status_code, 403)
        self.assertEqual(CaseRevision.objects.get(pk=draft_id).steps.count(), 2)

    def test_graph_draft_can_be_temporarily_incomplete_and_validator_reports_it(self):
        tag = self.owner_client.get(self.url())["ETag"]
        cloned = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/", etag=tag)
        self.assertEqual(cloned.status_code, 201)
        draft_id = cloned.json()["revision_id"]
        graph = {"entry_step_key": "intro", "rubric_version": 0, "steps": [
            {"key": "intro", "kind": "information", "title": "Start",
             "narrative": "Fictional unfinished", "is_active": True},
        ], "questions": [], "choices": [], "transitions": [], "scoring_dimensions": []}
        result = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{draft_id}/graph/edit/", graph, etag=cloned["ETag"])
        self.assertEqual(result.status_code, 200, result.content[:400])
        self.assertFalse(result.json()["valid"])
        self.assertTrue(any("information_requires_one_automatic_transition" in issue
                            for issue in result.json()["issues"]))
        self.assertEqual(self.case.current_revision_id, self.revision.pk)

    def test_simulate_decision_path_never_writes_learner_state(self):
        self.first.node_kind = CaseStep.NodeKind.DECISION
        self.first.save(update_fields=["node_kind"])
        CaseTransition.objects.filter(revision=self.revision).delete()
        q = CaseQuestion.objects.create(step=self.first, prompt="Fictional question?")
        c = CaseChoice.objects.create(question=q, text="Fictional answer", score_value=3)
        CaseTransition.objects.create(revision=self.revision, source_step=self.first,
                                      choice=c, target_step=self.end, outcome="continue")
        attempt = CaseAttempt.objects.create(user=self.normal, case=self.case,
            revision=self.revision, current_step=self.first, status=CaseAttempt.Status.IN_PROGRESS)
        path = f"cases/{self.case.pk}/revisions/{self.revision.pk}/simulate/"
        original = tuple(m.objects.count() for m in
            (CaseAttempt, CaseAttemptEvent, CaseAttemptAnswer, StudyActivity))
        answer = self.post(self.owner_client, path, {"choice_ids": [c.pk]})
        self.assertEqual(answer.status_code, 200, answer.content[:400])
        self.assertTrue(answer.json()["completed"])
        self.assertTrue(answer.json()["preview_only"])
        self.assertEqual(answer.json()["awarded_score"], 3)
        self.assertEqual([r["step_id"] for r in answer.json()["trace"]], [self.first.pk, self.end.pk])
        self.assertEqual(original, tuple(m.objects.count() for m in
            (CaseAttempt, CaseAttemptEvent, CaseAttemptAnswer, StudyActivity)))
        attempt.refresh_from_db()
        self.assertEqual(attempt.state_version, 0)
        self.assertEqual(attempt.current_step_id, self.first.pk)
        self.assertEqual(self.post(self.owner_client, path, {"choice_ids": [7777777]}).status_code, 400)
        self.assertEqual(self.post(self.owner_client, path, {"choice_ids": [c.pk, c.pk]}).status_code, 400)
        self.assertEqual(self.post(self.owner_client, path, {"choice_ids": ["1"]}).status_code, 400)

    def test_simulation_rejects_invalid_revision_and_missing_scope(self):
        path = f"cases/{self.case.pk}/revisions/{self.revision.pk}/simulate/"
        response = self.post(self.owner_client, path, {"choice_ids": []})
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(len(response.json()["trace"]), 2)
        viewer = self.user("p12-simulation-viewer", staff=True, caps=("cms_enter", "cms_cases_view"))
        self.assertEqual(self.post(self.sign_in(viewer), path, {"choice_ids": []}).status_code, 403)
        draft = CaseRevision.objects.create(case=self.case, version=2,
            status=CaseRevision.Status.DRAFT)
        self.assertEqual(self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{draft.pk}/simulate/", {"choice_ids": []}).status_code, 409)

    def test_branch_dead_end_is_reported_even_if_another_branch_completes(self):
        self.first.node_kind = CaseStep.NodeKind.DECISION
        self.first.save(update_fields=["node_kind"])
        CaseTransition.objects.filter(revision=self.revision).delete()
        decision = CaseQuestion.objects.create(step=self.first, prompt="Fictional branch?")
        good = CaseChoice.objects.create(question=decision, text="Good")
        bad = CaseChoice.objects.create(question=decision, text="Dead-end")
        dead = CaseStep.objects.create(case=self.case, revision=self.revision,
            stable_key="dead", node_kind=CaseStep.NodeKind.INFORMATION,
            title="Unfinished learning route", narrative="Fictional", sort_order=2)
        orphan = CaseStep.objects.create(case=self.case, revision=self.revision,
            stable_key="orphan", node_kind=CaseStep.NodeKind.TERMINAL,
            title="Unreachable", narrative="Fictional", sort_order=3)
        CaseTransition.objects.create(revision=self.revision, source_step=self.first,
            choice=good, target_step=self.end, outcome="continue")
        CaseTransition.objects.create(revision=self.revision, source_step=self.first,
            choice=bad, target_step=dead, outcome="continue")
        response = self.owner_client.get(self.url())
        self.assertEqual(response.status_code, 200)
        issues = response.json()["issues"]
        self.assertIn(f"step:{orphan.pk}:unreachable", issues)
        self.assertIn(f"step:{dead.pk}:dead_end", issues)
        self.assertNotIn("entry_has_no_completion_path", issues)

    def test_pinned_attempt_can_finish_old_revision_after_synthetic_switch(self):
        from .services import start_or_resume_case_attempt, advance_case_attempt
        old, created = start_or_resume_case_attempt(user=self.normal, clinical_case=self.case)
        self.assertTrue(created)
        self.assertEqual(old.revision_id, self.revision.pk)
        clone = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/",
            etag=self.owner_client.get(self.url())["ETag"])
        self.assertEqual(clone.status_code, 201, clone.content[:300])
        draft = CaseRevision.objects.get(pk=clone.json()["revision_id"])
        # Synthetic-only activation, not a public CMS publish operation.
        draft.status = CaseRevision.Status.PUBLISHED
        draft.save(update_fields=["status"])
        self.case.current_revision = draft
        self.case.save(update_fields=["current_revision"])
        first, first_event, was_retry = advance_case_attempt(
            user=self.normal, attempt=old, step_id=self.first.pk,
            choice_id=None, state_version=0)
        self.assertFalse(was_retry)
        self.assertEqual(first.revision_id, self.revision.pk)
        self.assertEqual(first.current_step_id, self.end.pk)
        done, final_event, was_retry = advance_case_attempt(
            user=self.normal, attempt=first, step_id=self.end.pk,
            choice_id=None, state_version=1)
        self.assertFalse(was_retry)
        self.assertEqual(done.status, CaseAttempt.Status.COMPLETED)
        self.assertEqual(done.revision_id, self.revision.pk)
        self.assertEqual([r.step_id for r in done.events.order_by("state_version_before")],
                         [self.first.pk, self.end.pk])
        self.assertEqual(first_event.step.revision_id, self.revision.pk)
        self.assertEqual(final_event.step.revision_id, self.revision.pk)
        newer, started = start_or_resume_case_attempt(user=self.normal, clinical_case=self.case)
        self.assertTrue(started)
        self.assertEqual(newer.revision_id, draft.pk)
        self.assertNotEqual(newer.current_step_id, self.first.pk)
        self.assertEqual(CaseAttempt.objects.filter(case=self.case).count(), 2)

    def test_new_case_starts_as_private_inactive_draft_and_is_discoverable(self):
        collection = "cases/"
        listed = self.owner_client.get(BASE + collection)
        self.assertEqual(listed.status_code, 200, listed.content[:300])
        self.assertTrue(any(row["case_id"] == self.case.pk for row in listed.json()["results"]))
        data = {"slug": "p12-new-fictional-case", "title": "A new fictional learning case",
                "patient_summary": "Synthetic narrative only",
                "educational_objective": "Demonstrate branching",
                "difficulty": "introductory"}
        created = self.post(self.owner_client, collection, data)
        self.assertEqual(created.status_code, 201, created.content[:400])
        fresh = ClinicalCase.objects.get(pk=created.json()["case_id"])
        draft = CaseRevision.objects.get(pk=created.json()["revision_id"])
        self.assertFalse(fresh.is_active)
        self.assertIsNone(fresh.current_revision_id)
        self.assertEqual(fresh.structure_mode, ClinicalCase.StructureMode.BRANCHING)
        self.assertEqual(draft.status, CaseRevision.Status.DRAFT)
        self.assertEqual(draft.version, 1)
        self.assertEqual(draft.case_id, fresh.pk)
        preview = self.owner_client.get(self.url(revision=draft.pk, case=fresh.pk))
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["valid"])
        self.assertEqual(self.post(self.owner_client, collection, data).status_code, 409)
        data["title"] = ""
        self.assertEqual(self.post(self.owner_client, collection, data).status_code, 400)
        self.assertEqual(CaseAttempt.objects.count(), 0)
        self.assertEqual(StudyActivity.objects.count(), 0)
        view_only = self.user("p12-new-case-readonly", staff=True, caps=(
            "cms_enter", "cms_cases_view", "cms_cases_preview"))
        self.assertEqual(self.post(self.sign_in(view_only), collection, data).status_code, 403)

    def test_revision_history_lists_versions_without_learner_identity(self):
        attempt = CaseAttempt.objects.create(
            user=self.normal, case=self.case, revision=self.revision,
            current_step=self.first, status=CaseAttempt.Status.IN_PROGRESS)
        clone = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/",
            etag=self.owner_client.get(self.url())["ETag"])
        self.assertEqual(clone.status_code, 201)
        response = self.owner_client.get(BASE + f"cases/{self.case.pk}/revisions/")
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()["count"], 2)
        rows = response.json()["results"]
        self.assertEqual([r["version"] for r in rows], [2, 1])
        self.assertEqual([r["status"] for r in rows], ["draft", "published"])
        self.assertEqual(rows[1]["attempt_count"], 1)
        self.assertEqual(rows[0]["attempt_count"], 0)
        self.assertEqual(rows[0]["revision_id"], clone.json()["revision_id"])
        self.assertNotIn("user", str(response.json()).lower())
        self.assertEqual(self.owner_client.get(BASE + f"cases/{self.case.pk+999}/revisions/").status_code, 404)
        attempt.refresh_from_db()
        self.assertEqual(attempt.revision_id, self.revision.pk)

    def test_cycle_is_visible_but_cannot_be_simulated_or_published(self):
        tag = self.owner_client.get(self.url())["ETag"]
        clone = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{self.revision.pk}/clone/", etag=tag)
        self.assertEqual(clone.status_code, 201)
        draft_id = clone.json()["revision_id"]
        graph = {"entry_step_key": "a", "rubric_version": 0,
            "scoring_dimensions": [], "questions": [], "choices": [],
            "steps": [
                {"key": "a", "kind": "information", "title": "A", "narrative": "Synthetic", "is_active": True},
                {"key": "b", "kind": "information", "title": "B", "narrative": "Synthetic", "is_active": True},
            ], "transitions": [
                {"source_key": "a", "choice_key": None, "target_key": "b", "outcome": "continue", "is_active": True},
                {"source_key": "b", "choice_key": None, "target_key": "a", "outcome": "continue", "is_active": True},
            ]}
        saved = self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{draft_id}/graph/edit/", graph, etag=clone["ETag"])
        self.assertEqual(saved.status_code, 200, saved.content[:400])
        self.assertFalse(saved.json()["valid"])
        self.assertIn("cycle_detected", saved.json()["issues"])
        self.assertEqual(self.post(self.owner_client,
            f"cases/{self.case.pk}/revisions/{draft_id}/simulate/",
            {"choice_ids": []}).status_code, 409)
        self.assertEqual(CaseRevision.objects.get(pk=draft_id).status, CaseRevision.Status.DRAFT)
        self.assertEqual(self.case.current_revision_id, self.revision.pk)
