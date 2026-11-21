"""Synthetic authoring transfers through real MFA, private artifacts and leased jobs."""
import copy
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from .cms_case_editor import revision_etag
from .cms_job_models import AdminArtifact, AdminJob
from .cms_jobs import claim_job, run_once
from .cms_models import AdminAuditEvent, AdminSession, RolePolicy
from .cms_policy import CMSFailure
from .models import (Category, Concept, Disorder, Quiz, QuizQuestion, QuizChoice, QuizAttempt, QuizAttemptAnswer,
    Flashcard, UserFlashcardProgress, DailyChallenge, DailyChallengeAttempt,
    CognitiveDistortionPracticeItem, CognitiveDistortionPracticeAttempt,
    StudyActivity, UserProgress, UserConceptProgress)
from .tests_v100_p01 import BASE
from .tests_v100_p06_artifacts import ArtifactFixture

TRANSFER = "learning/transfer/"
SCHEMA = "psychology-atlas-learning-authoring-v1"


def bundle():
    return {"schema_version": SCHEMA, "items": [
        {"kind": "quiz", "key": "quiz-one", "fields": {"slug": "io-new-quiz", "title": "Synthetic quiz",
            "description": "Fictional only", "disorder_slug": "io-disorder", "questions": [{
                "prompt": "Synthetic question", "explanation": "Fictional only", "choices": [
                    {"text": "Synthetic right", "is_correct": True},
                    {"text": "Synthetic wrong", "is_correct": False}]}]}},
        {"kind": "flashcard", "key": "card-one", "fields": {"slug": "io-new-card",
            "front": "Synthetic front", "back": "Synthetic back", "hint": "", "difficulty": "basic",
            "concept_slug": "io-distortion", "disorder_slug": "io-disorder"}},
        {"kind": "daily", "key": "daily-one", "fields": {"prompt": "Synthetic daily",
            "explanation": "Fictional only", "concept_slug": "io-distortion", "disorder_slug": None,
            "choices": [{"text": "Synthetic right", "is_correct": True},
                        {"text": "Synthetic wrong", "is_correct": False}]}},
        {"kind": "distortions", "key": "practice-one", "fields": {"slug": "io-new-practice",
            "prompt": "Synthetic practice", "explanation": "Fictional only", "difficulty": "basic",
            "target_concept_slug": "io-distortion", "choices": [
                {"concept_slug": "io-distortion", "text": "Synthetic right", "is_correct": True},
                {"concept_slug": "io-other", "text": "Synthetic wrong", "is_correct": False}]}},
    ]}


class LearningTransferFixture(ArtifactFixture):
    def setUp(self):
        super().setUp()
        category = Category.objects.create(slug="io-category", name_en="Synthetic category")
        self.disorder = Disorder.objects.create(category=category, slug="io-disorder", name_en="Synthetic disorder")
        self.concept = Concept.objects.create(slug="io-distortion", name_en="Synthetic distortion",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        self.other = Concept.objects.create(slug="io-other", name_en="Synthetic other",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        from .services import submit_quiz
        from .learning import review_flashcard
        self.historical_quiz = Quiz.objects.create(slug="io-history-quiz", title="Synthetic historical quiz",
            disorder=self.disorder)
        q = self.historical_quiz.questions.create(prompt="Synthetic historical question")
        c = q.choices.create(text="Synthetic right", is_correct=True)
        q.choices.create(text="Synthetic wrong", is_correct=False)
        submit_quiz(user=self.normal, quiz=self.historical_quiz,
                    answers=[{"question_id": q.pk, "choice_id": c.pk}])
        self.historical_card = Flashcard.objects.create(slug="io-history-card", front="Synthetic", back="Synthetic",
            concept=self.concept, disorder=self.disorder)
        review_flashcard(user=self.normal, flashcard=self.historical_card, rating="good")
        self.historical_daily = DailyChallenge.objects.create(prompt="Synthetic historical daily")
        c = self.historical_daily.choices.create(text="Synthetic right", is_correct=True)
        self.historical_daily.choices.create(text="Synthetic wrong", is_correct=False)
        self.historical_practice = CognitiveDistortionPracticeItem.objects.create(slug="io-history-practice",
            prompt="Synthetic historical practice", target_concept=self.concept)
        pc = self.historical_practice.choices.create(concept=self.concept, text="Synthetic right", is_correct=True)
        self.historical_practice.choices.create(concept=self.other, text="Synthetic wrong", is_correct=False)
        learner = APIClient()
        learner.force_authenticate(self.normal)
        self.assertEqual(learner.post("/api/daily-challenge/", {"choice_id": c.pk}, format="json").status_code, 200)
        self.assertEqual(learner.post("/api/cognitive-distortions/practice/io-history-practice/submit/",
            {"choice_id": pc.pk}, format="json").status_code, 201)
        self.history_models = (QuizAttempt, QuizAttemptAnswer, StudyActivity, UserFlashcardProgress,
            DailyChallengeAttempt, CognitiveDistortionPracticeAttempt, UserProgress, UserConceptProgress)
        self.before = self.history()
        self.assertTrue(all(self.before.values()), {name: len(rows) for name, rows in self.before.items()})
        for item in (self.historical_quiz, self.historical_card, self.historical_daily, self.historical_practice):
            item.is_active = False
            item.seed_managed = False
            item.save(update_fields=["is_active", "seed_managed"])

    def history(self):
        return {model.__name__: list(model.objects.order_by("pk").values()) for model in self.history_models}

    def ready_bundle(self, document=None, client=None):
        client = client or self.client
        artifact = self.created(document or bundle(), kind="learning_json", client=client)
        response = self.post(client, f"artifacts/{artifact['id']}/validate/", etag=f'"{artifact["version"]}"')
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()["artifact"]["state"], "ready", response.content[:300])
        return response.json()["artifact"]

    def import_job(self, artifact, key=None, client=None):
        return self.post(client or self.client, TRANSFER + "import/",
            {"artifact_id": artifact["id"], "request_key": str(key or uuid.uuid4())})

    def export_job(self, items, key=None, client=None):
        manifest = [{"kind": kind, "resource_id": item.pk, "etag": f'"{revision_etag(item)}"'}
                    for kind, item in items]
        return self.post(client or self.client, TRANSFER + "export/",
                         {"items": manifest, "request_key": str(key or uuid.uuid4())})

    def download_learning(self, artifact_id, client=None):
        return (client or self.client).get(BASE + f"artifacts/{artifact_id}/download/?purpose=learning_authoring")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningTransferTests(LearningTransferFixture, TransactionTestCase):
    def test_import_route_is_closed_and_requires_an_artifact(self):
        response = self.post(self.client, TRANSFER + "import/", {"request_key": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 400, response.content[:300])

    def test_transfer_request_byte_limit_is_enforced_before_unbounded_json_parser(self):
        token = self.csrf(self.client)
        raw = b'{"items":[],"request_key":"' + b"X" * (1024 * 1024) + b'"}'
        with patch("rest_framework.parsers.JSONParser.parse", side_effect=AssertionError("Unbounded request parse")):
            response = self.client.post(BASE + TRANSFER + "export/", raw, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "JSON_LIMIT")
        self.assertEqual(AdminJob.objects.count(), 0)

    def test_all_four_import_create_private_drafts_once_without_touching_history(self):
        artifact = self.ready_bundle()
        key = uuid.uuid4()
        queued = self.import_job(artifact, key)
        self.assertEqual(queued.status_code, 202, queued.content[:300])
        self.assertEqual(self.import_job(artifact, key).json()["job"]["id"], queued.json()["job"]["id"])
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        self.assertEqual(job.kind, "learning_import")
        self.assertEqual(len(job.result["created"]), 4)
        models = {"quiz": Quiz, "flashcard": Flashcard, "daily": DailyChallenge,
                  "distortions": CognitiveDistortionPracticeItem}
        for row in job.result["created"]:
            item = models[row["kind"]].objects.get(pk=row["resource_id"])
            self.assertFalse(item.is_active)
            self.assertFalse(item.seed_managed)
            self.assertIsNone(item.archived_at)
        self.assertEqual(self.history(), self.before)
        self.assertIsNone(run_once())
        self.assertEqual(self.import_job(artifact, key).json()["job"]["id"], str(job.pk))
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.imported").count(), 1)
        self.assertNotIn("Synthetic question", json.dumps(job.result))
        self.assertEqual(Quiz.objects.count(), 2)

    def test_export_only_actor_can_select_export_and_download_without_edit_or_upload(self):
        card = Flashcard.objects.create(slug="io-export-card", front="Synthetic front", back="Synthetic back",
            concept=self.concept, is_active=False, seed_managed=False)
        user = self.user("io-exporter", staff=True,
            caps=("cms_enter", "cms_learning_view", "cms_learning_export", "cms_artifact_download"))
        client = self.sign_in(user)
        selection = client.get(BASE + TRANSFER + "selection/?kind=flashcard")
        self.assertEqual(selection.status_code, 200, selection.content[:300])
        self.assertEqual([row["resource_id"] for row in selection.json()["results"]], [card.pk])
        queued = self.export_job([("flashcard", card)], client=client)
        self.assertEqual(queued.status_code, 202, queued.content[:300])
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        self.assertEqual(client.get(BASE + f"jobs/{job.pk}/").status_code, 200)
        self.assertEqual(client.get(BASE + "jobs/").status_code, 200)
        output = job.output_artifact
        self.assertEqual((output.kind, output.domain, output.state), ("learning_export_json", "learning", "ready"))
        download = self.download_learning(output.pk, client)
        self.assertEqual(download.status_code, 200, download.content[:300])
        document = json.loads(download.content)
        self.assertEqual(document["schema_version"], SCHEMA)
        self.assertEqual(document["items"][0]["fields"]["concept_slug"], self.concept.slug)
        self.assertEqual(set(document["items"][0]["fields"]),
                         {"slug", "front", "back", "hint", "difficulty", "concept_slug", "disorder_slug"})
        self.assertEqual(self.history(), self.before)
        user.user_permissions.remove(*user.user_permissions.filter(codename="cms_learning_export"))
        self.assertEqual(self.download_learning(output.pk, client).status_code, 403)
        self.assertEqual(client.get(BASE + f"jobs/{job.pk}/").status_code, 403)

    def test_unknown_or_restricted_bundle_fields_never_become_ready(self):
        documents = []
        for field in ("is_active", "archived_at", "user_id", "attempts", "scoring_key"):
            document = bundle()
            document["items"][0]["fields"][field] = True
            documents.append(document)
        duplicate = bundle()
        duplicate["items"].append(copy.deepcopy(duplicate["items"][0]))
        documents.append(duplicate)
        for document in documents:
            with self.subTest(fields=list(document["items"][0]["fields"])):
                artifact = self.created(document, kind="learning_json")
                response = self.validate(artifact)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["artifact"]["state"], "rejected")
                self.assertEqual(self.import_job(response.json()["artifact"]).status_code, 409)
        self.assertEqual(self.history(), self.before)

    def test_export_rejects_aggregate_graph_before_materializing_related_rows(self):
        quizzes = []
        for index in range(3):
            quiz = Quiz.objects.create(slug=f"io-large-quiz-{index}", title="Synthetic bounded quiz",
                                       is_active=False, seed_managed=False)
            questions = QuizQuestion.objects.bulk_create([QuizQuestion(quiz=quiz, prompt="Synthetic question",
                sort_order=number) for number in range(100)])
            QuizChoice.objects.bulk_create([QuizChoice(question=question, text="Synthetic choice", is_correct=correct)
                for question in questions for correct in (True, False)])
            quizzes.append(("quiz", quiz))
        self.assertEqual(self.export_job(quizzes).status_code, 202)
        with patch("atlas.cms_learning_io.prefetch_related_objects", side_effect=AssertionError("Unbounded graph fetch")):
            job = run_once()
        self.assertEqual((job.status, job.error_code), ("failed", "JSON_LIMIT"))
        self.assertIsNone(job.output_artifact_id)
        self.assertEqual(self.history(), self.before)

    def test_export_rejects_excess_text_before_materializing_related_rows(self):
        quiz = Quiz.objects.create(slug="io-excess-text", title="Synthetic bounded quiz",
                                   is_active=False, seed_managed=False)
        question = quiz.questions.create(prompt="Synthetic question")
        question.choices.create(text="X" * (1024 * 1024 + 1), is_correct=True)
        question.choices.create(text="Synthetic wrong", is_correct=False)
        self.assertEqual(self.export_job([("quiz", quiz)]).status_code, 202)
        with patch("atlas.cms_learning_io.prefetch_related_objects", side_effect=AssertionError("Unbounded text fetch")):
            job = run_once()
        self.assertEqual((job.status, job.error_code), ("failed", "JSON_LIMIT"))
        self.assertIsNone(job.output_artifact_id)

    def assert_no_imported_content(self):
        self.assertFalse(Quiz.objects.filter(slug="io-new-quiz").exists())
        self.assertFalse(Flashcard.objects.filter(slug="io-new-card").exists())
        self.assertFalse(DailyChallenge.objects.filter(prompt="Synthetic daily").exists())
        self.assertFalse(CognitiveDistortionPracticeItem.objects.filter(slug="io-new-practice").exists())
        self.assertEqual(self.history(), self.before)

    def test_late_slug_conflict_rolls_back_earlier_items_and_preserves_existing_values(self):
        existing = Flashcard.objects.create(slug="io-new-card", front="Original private front", back="Original back",
                                            is_active=False, seed_managed=False)
        before = list(Flashcard.objects.filter(pk=existing.pk).values())
        self.assertEqual(self.import_job(self.ready_bundle()).status_code, 202)
        job = run_once()
        self.assertEqual((job.status, job.error_code), ("failed", "FLASHCARD_SLUG_EXISTS"))
        self.assertFalse(Quiz.objects.filter(slug="io-new-quiz").exists())
        self.assertFalse(DailyChallenge.objects.filter(prompt="Synthetic daily").exists())
        self.assertEqual(list(Flashcard.objects.filter(pk=existing.pk).values()), before)
        self.assertEqual(AdminAuditEvent.objects.filter(action="quiz.draft_created").count(), 0)
        self.assertEqual(self.history(), self.before)

    def test_import_audit_failure_rolls_back_then_real_retry_creates_once(self):
        self.assertEqual(self.import_job(self.ready_bundle()).status_code, 202)
        create = AdminAuditEvent.objects.create

        def fail_receipt(**kwargs):
            if kwargs.get("action") == "learning.imported":
                raise DatabaseError("Synthetic audit rollback")
            return create(**kwargs)

        with patch("atlas.cms_learning_io.AdminAuditEvent.objects.create", side_effect=fail_receipt):
            job = run_once()
        self.assertEqual((job.status, job.error_code), ("failed", "INTERNAL_ERROR"))
        self.assert_no_imported_content()
        response = self.post(self.client, f"jobs/{job.pk}/retry/", etag=f'"{job.version}"')
        self.assertEqual(response.status_code, 200, response.content[:300])
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        self.assertEqual(len(job.result["created"]), 4)
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.imported").count(), 1)
        self.assertEqual(self.history(), self.before)

    def test_import_requires_every_current_capability_not_cached_grants(self):
        caps = ("cms_enter", "cms_learning_view", "cms_learning_create", "cms_learning_edit", "cms_artifact_upload")
        for missing in caps:
            with self.subTest(missing=missing):
                user = self.user("io-missing-" + missing, staff=True, caps=caps)
                client = self.sign_in(user)
                artifact = self.ready_bundle(client=client)
                user.user_permissions.remove(*user.user_permissions.filter(codename=missing))
                self.assertEqual(self.import_job(artifact, client=client).status_code, 403)
        self.assertEqual(AdminJob.objects.count(), 0)
        self.assert_no_imported_content()

    def test_import_foreign_artifact_and_output_upload_are_denied(self):
        artifact = self.ready_bundle()
        user = self.user("io-foreign", staff=True, caps=("cms_enter", "cms_learning_view", "cms_learning_create",
                                                       "cms_learning_edit", "cms_artifact_upload"))
        client = self.sign_in(user)
        self.assertEqual(self.import_job(artifact, client=client).status_code, 404)
        self.assertEqual(self.upload(bundle(), kind="learning_export_json").status_code, 400)
        self.assertEqual(AdminJob.objects.count(), 0)

    def test_validation_limits_answer_keys_and_natural_references(self):
        cases = []
        invalid = bundle()
        invalid["items"][0]["fields"]["questions"][0]["choices"][1]["is_correct"] = True
        cases.append(invalid)
        missing = bundle()
        missing["items"][1]["fields"]["concept_slug"] = "io-nonexistent"
        cases.append(missing)
        identity = bundle()
        duplicate = copy.deepcopy(identity["items"][0])
        duplicate["key"] = "another-key"
        identity["items"].append(duplicate)
        cases.append(identity)
        historical_id = bundle()
        historical_id["items"][0]["fields"]["questions"][0]["id"] = self.historical_quiz.questions.first().pk
        cases.append(historical_id)
        for document in cases:
            artifact = self.created(document, kind="learning_json")
            self.assertEqual(self.validate(artifact).json()["artifact"]["state"], "rejected")
        self.concept.is_active = False
        self.concept.save(update_fields=["is_active"])
        artifact = self.created(bundle(), kind="learning_json")
        self.assertEqual(self.validate(artifact).json()["artifact"]["validation_code"], "INVALID_REFERENCE")
        self.assert_no_imported_content()

    def test_input_byte_depth_and_aggregate_question_limits(self):
        oversized = b" " * (1024 * 1024) + b"{}"
        artifact = self.created(raw=oversized, kind="learning_json")
        self.assertEqual(self.validate(artifact).json()["artifact"]["validation_code"], "JSON_LIMIT")
        deep = {}
        for _ in range(10):
            deep = {"nested": deep}
        artifact = self.created({"unexpected": deep}, kind="learning_json")
        self.assertEqual(self.validate(artifact).json()["artifact"]["validation_code"], "JSON_LIMIT")
        document = bundle()
        question = document["items"][0]["fields"]["questions"][0]
        document["items"] = [{"kind": "quiz", "key": f"quiz-{index}", "fields": {
            **document["items"][0]["fields"], "slug": f"io-cap-{index}",
            "questions": [copy.deepcopy(question) for _ in range(100)]}} for index in range(3)]
        artifact = self.created(document, kind="learning_json")
        self.assertEqual(self.validate(artifact).json()["artifact"]["validation_code"], "JSON_LIMIT")
        self.assert_no_imported_content()

    def test_all_historical_kinds_and_public_seeded_archived_targets_cannot_export(self):
        for kind, item in (("quiz", self.historical_quiz), ("flashcard", self.historical_card),
                           ("daily", self.historical_daily), ("distortions", self.historical_practice)):
            with self.subTest(kind=kind):
                self.assertEqual(self.export_job([(kind, item)]).status_code, 409)
        for state in ({"is_active": True}, {"seed_managed": True}, {"archived_at": timezone.now()}):
            card = Flashcard.objects.create(slug="io-protected-" + next(iter(state)), front="Synthetic", back="Synthetic",
                is_active=False, seed_managed=False)
            Flashcard.objects.filter(pk=card.pk).update(**state)
            card.refresh_from_db()
            self.assertEqual(self.export_job([("flashcard", card)]).status_code, 409)
        self.assertEqual(AdminJob.objects.count(), 0)
        self.assertEqual(AdminArtifact.objects.count(), 0)
        self.assertEqual(self.history(), self.before)

    def test_stale_manifest_is_rechecked_at_execution(self):
        card = Flashcard.objects.create(slug="io-stale-card", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        tag = f'"{revision_etag(card)}"'
        self.assertEqual(self.export_job([("flashcard", card)]).status_code, 202)
        response = self.post(self.client, f"learning/flashcards/{card.pk}/metadata/", {"front": "Synthetic concurrent edit"}, etag=tag)
        self.assertEqual(response.status_code, 200)
        job = run_once()
        self.assertEqual((job.status, job.error_code), ("failed", "STALE_REVISION"))
        self.assertIsNone(job.output_artifact_id)

    def test_expired_lease_fences_old_worker_and_new_claim_imports_once(self):
        from .cms_learning_io import process_learning
        self.assertEqual(self.import_job(self.ready_bundle()).status_code, 202)
        old = claim_job()
        AdminJob.objects.filter(pk=old.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(CMSFailure) as failure:
            process_learning(old.pk, old.lease_token)
        self.assertEqual(str(failure.exception.detail["code"]), "LEASE_LOST")
        self.assert_no_imported_content()
        job = run_once()
        self.assertEqual((job.status, job.attempt), ("succeeded", 2))
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.imported").count(), 1)

    def test_post_commit_import_failure_reconciles_without_replaying_drafts(self):
        from .cms_jobs import audit
        self.assertEqual(self.import_job(self.ready_bundle()).status_code, 202)

        def crash_at_final_status(job, action, *args, **kwargs):
            if action == "job.succeeded":
                raise RuntimeError("Synthetic lost completion after content commit")
            return audit(job, action, *args, **kwargs)

        with patch("atlas.cms_jobs.audit", side_effect=crash_at_final_status):
            first = run_once()
        self.assertEqual(first.status, "running")
        self.assertTrue(first.checkpoint["complete"])
        created = first.checkpoint["result"]["created"]
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        self.assertEqual(job.result["created"], created)
        self.assertEqual(Quiz.objects.count(), 2)
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.imported").count(), 1)
        self.assertEqual(self.history(), self.before)

    def test_cancel_after_export_intent_prevents_file_and_download(self):
        from .cms_artifacts import _path, cleanup_eligible
        from .cms_jobs import checkpoint_job
        card = Flashcard.objects.create(slug="io-cancel-card", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        self.assertEqual(self.export_job([("flashcard", card)]).status_code, 202)
        sent = []

        def cancel_after_prepare(job_id, token, effect):
            result = checkpoint_job(job_id, token, effect)
            current = AdminJob.objects.get(pk=job_id)
            if current.output_artifact_id and not current.checkpoint.get("complete") and not sent:
                sent.append(True)
                output = current.output_artifact
                output.expires_at = timezone.now() - timedelta(seconds=1)
                output.save(update_fields=["expires_at"])
                with self.assertRaises(CMSFailure) as held:
                    cleanup_eligible(output)
                self.assertEqual(str(held.exception.detail["code"]), "ARTIFACT_RETENTION_HOLD")
                self.assertEqual(self.post(self.client, f"jobs/{job_id}/cancel/", etag=f'"{current.version}"').status_code, 200)
            return result

        with patch("atlas.cms_learning_io.checkpoint_job", side_effect=cancel_after_prepare):
            job = run_once()
        self.assertEqual(job.status, "cancelled")
        self.assertEqual(job.output_artifact.state, "quarantine")
        self.assertFalse(_path(job.output_artifact).exists())
        self.assertEqual(self.download_learning(job.output_artifact_id).status_code, 409)
        self.assertEqual(self.history(), self.before)

    def test_export_file_survives_rollback_as_quarantine_and_retry_does_not_rewrite_it(self):
        from .cms_artifacts import _path
        card = Flashcard.objects.create(slug="io-output-rollback", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        self.assertEqual(self.export_job([("flashcard", card)]).status_code, 202)
        create = AdminAuditEvent.objects.create

        def fail_export_audit(**kwargs):
            if kwargs.get("action") == "learning.exported":
                raise DatabaseError("Synthetic export receipt rollback")
            return create(**kwargs)

        with patch("atlas.cms_learning_io.AdminAuditEvent.objects.create", side_effect=fail_export_audit):
            first = run_once()
        self.assertEqual(first.status, "failed")
        output = first.output_artifact
        self.assertEqual(output.state, "quarantine")
        modified = _path(output).stat().st_mtime_ns
        self.assertEqual(self.download_learning(output.pk).status_code, 409)
        self.assertEqual(self.post(self.client, f"artifacts/{output.pk}/validate/", etag=f'"{output.version}"').status_code, 409)
        output.refresh_from_db()
        self.assertEqual(output.state, "quarantine")
        self.assertEqual(self.post(self.client, f"jobs/{first.pk}/retry/", etag=f'"{first.version}"').status_code, 200)
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        self.assertEqual(job.output_artifact_id, output.pk)
        self.assertEqual(_path(output).stat().st_mtime_ns, modified)
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.exported").count(), 1)
        self.assertEqual(self.history(), self.before)

    def test_queued_import_revalidates_actor_session_policy_and_artifact(self):
        caps = ("cms_enter", "cms_learning_view", "cms_learning_create", "cms_learning_edit", "cms_artifact_upload")
        for scenario, expected in (("permission", "PERMISSION_DENIED"), ("session", "UNAUTHENTICATED"),
                                   ("policy", "POLICY_CHANGED"), ("revoke", "ARTIFACT_NOT_READY"),
                                   ("expiry", "ARTIFACT_NOT_READY")):
            with self.subTest(scenario=scenario):
                user = self.user("io-execution-" + scenario, staff=True, caps=caps)
                client = self.sign_in(user)
                artifact = self.ready_bundle(client=client)
                self.assertEqual(self.import_job(artifact, client=client).status_code, 202)
                if scenario == "permission":
                    user.user_permissions.remove(*user.user_permissions.filter(codename="cms_learning_edit"))
                elif scenario == "session":
                    AdminSession.objects.filter(pk=client.session["cms_session_id"]).update(revoked_at=timezone.now())
                elif scenario == "policy":
                    policy = RolePolicy.objects.get(pk=1)
                    policy.version += 1
                    policy.save()
                elif scenario == "revoke":
                    self.assertEqual(self.post(self.client, f"artifacts/{artifact['id']}/revoke/",
                        etag=f'"{artifact["version"]}"').status_code, 200)
                else:
                    AdminArtifact.objects.filter(pk=artifact["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
                job = run_once()
                self.assertEqual((job.status, job.error_code), ("failed", expected))
                self.assert_no_imported_content()

    def test_same_request_key_conflicts_never_create_a_second_job_or_manifest(self):
        artifact = self.ready_bundle()
        key = uuid.uuid4()
        self.assertEqual(self.import_job(artifact, key).status_code, 202)
        changed = bundle()
        changed["items"][0]["fields"]["title"] = "Synthetic changed title"
        second = self.ready_bundle(changed)
        self.assertEqual(self.import_job(second, key).status_code, 409)
        card = Flashcard.objects.create(slug="io-key-card", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        before = AdminArtifact.objects.count()
        self.assertEqual(self.export_job([("flashcard", card)], key).status_code, 409)
        self.assertEqual(AdminArtifact.objects.count(), before)
        self.assertEqual(AdminJob.objects.count(), 1)

    def test_export_all_four_contains_closed_content_only_and_preserves_canonical_rows(self):
        from .cms_jobs import job_data
        from .cms_learning_io import FIELDS, KINDS
        self.assertEqual(self.import_job(self.ready_bundle()).status_code, 202)
        imported = run_once()
        items = [(row["kind"], KINDS[row["kind"]].objects.get(pk=row["resource_id"])) for row in imported.result["created"]]
        before = {kind: list(model.objects.order_by("pk").values()) for kind, model in KINDS.items()}
        self.assertEqual(self.export_job(items).status_code, 202)
        job = run_once()
        self.assertEqual(job.status, "succeeded", job.error_code)
        download = self.download_learning(job.output_artifact_id)
        self.assertEqual(download.status_code, 200)
        document = json.loads(download.content)
        self.assertEqual(set(document), {"schema_version", "items"})
        self.assertEqual({row["kind"] for row in document["items"]}, set(KINDS))
        for row in document["items"]:
            self.assertEqual(set(row), {"kind", "key", "fields"})
            self.assertEqual(set(row["fields"]), FIELDS[row["kind"]])
        self.assertNotIn("Synthetic question", json.dumps(job_data(job)))
        audit = json.dumps(list(AdminAuditEvent.objects.values()), default=str)
        self.assertNotIn("Synthetic question", audit)
        self.assertNotIn("Synthetic front", audit)
        self.assertEqual({kind: list(model.objects.order_by("pk").values()) for kind, model in KINDS.items()}, before)
        self.assertEqual(self.history(), self.before)

    def test_download_rechecks_permissions_after_bytes_and_obeys_expiry_and_revocation(self):
        from .cms_artifacts import artifact_bytes
        card = Flashcard.objects.create(slug="io-download-card", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        user = self.user("io-download", staff=True,
            caps=("cms_enter", "cms_learning_view", "cms_learning_export", "cms_artifact_download"))
        client = self.sign_in(user)
        self.assertEqual(self.export_job([("flashcard", card)], client=client).status_code, 202)
        job = run_once()
        output = job.output_artifact

        def revoke_after_read(artifact):
            raw = artifact_bytes(artifact)
            user.user_permissions.remove(*user.user_permissions.filter(codename="cms_learning_export"))
            return raw

        with patch("atlas.cms_artifact_views.service.artifact_bytes", side_effect=revoke_after_read):
            response = self.download_learning(output.pk, client)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"Synthetic", response.content)
        self.grant(user, "cms_learning_export")
        for cap in ("cms_learning_view", "cms_artifact_download"):
            user.user_permissions.remove(*user.user_permissions.filter(codename=cap))
            self.assertEqual(self.download_learning(output.pk, client).status_code, 403)
            self.grant(user, cap)
        AdminArtifact.objects.filter(pk=output.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.download_learning(output.pk, client).status_code, 409)
        AdminArtifact.objects.filter(pk=output.pk).update(expires_at=timezone.now() + timedelta(days=1))
        response = self.post(self.client, f"artifacts/{output.pk}/revoke/", etag=f'"{output.version}"')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.download_learning(output.pk, client).status_code, 409)

    def test_manifest_enqueue_failure_retains_one_quarantine_intent_for_same_key_retry(self):
        from .cms_artifacts import _path
        card = Flashcard.objects.create(slug="io-manifest-retry", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        key = uuid.uuid4()
        with patch("atlas.cms_learning_io.enqueue_job", side_effect=DatabaseError("Synthetic enqueue rollback")):
            self.assertEqual(self.export_job([("flashcard", card)], key).status_code, 503)
        self.assertEqual(AdminJob.objects.count(), 0)
        manifest = AdminArtifact.objects.get(resource_type="learning_export_manifest")
        self.assertEqual(manifest.state, "quarantine")
        self.assertTrue(_path(manifest).is_file())
        self.assertEqual(self.download_learning(manifest.pk).status_code, 409)
        self.assertEqual(self.post(self.client, f"artifacts/{manifest.pk}/validate/", etag=f'"{manifest.version}"').status_code, 409)
        manifest.refresh_from_db()
        self.assertEqual(manifest.state, "quarantine")
        self.assertEqual(self.export_job([("flashcard", card)], key).status_code, 202)
        self.assertEqual(AdminArtifact.objects.filter(resource_type="learning_export_manifest").count(), 1)
        self.assertEqual(run_once().status, "succeeded")

    def test_partial_staged_output_and_lost_final_status_resume_without_duplicate_files(self):
        from .cms_artifacts import _path
        from .cms_jobs import checkpoint_job, audit
        card = Flashcard.objects.create(slug="io-partial-output", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        self.assertEqual(self.export_job([("flashcard", card)]).status_code, 202)
        paused = []

        def stop_after_intent(job_id, token, effect):
            result = checkpoint_job(job_id, token, effect)
            current = AdminJob.objects.get(pk=job_id)
            if current.output_artifact_id and not current.checkpoint.get("complete") and not paused:
                paused.append(True)
                _path(current.output_artifact).with_suffix(".pending").write_bytes(b"Synthetic incomplete file")
                raise RuntimeError("Synthetic worker interruption after intent")
            return result

        with patch("atlas.cms_learning_io.checkpoint_job", side_effect=stop_after_intent):
            first = run_once()
        self.assertEqual(first.status, "failed")
        output_id = first.output_artifact_id
        self.assertEqual(self.download_learning(output_id).status_code, 409)
        self.assertEqual(self.post(self.client, f"jobs/{first.pk}/retry/", etag=f'"{first.version}"').status_code, 200)

        def lose_final_status(job, action, *args, **kwargs):
            if action == "job.succeeded":
                raise RuntimeError("Synthetic lost status after export commit")
            return audit(job, action, *args, **kwargs)

        with patch("atlas.cms_jobs.audit", side_effect=lose_final_status):
            committed = run_once()
        self.assertTrue(committed.checkpoint["complete"])
        self.assertEqual(committed.status, "running")
        final = run_once()
        self.assertEqual(final.status, "succeeded", final.error_code)
        self.assertEqual(final.output_artifact_id, output_id)
        self.assertFalse(_path(final.output_artifact).with_suffix(".pending").exists())
        self.assertEqual(AdminArtifact.objects.filter(kind="learning_export_json").count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.exported").count(), 1)
        self.assertEqual(self.history(), self.before)

    def test_live_input_retention_hold_and_cancelled_import_does_not_run(self):
        from .cms_artifacts import cleanup_eligible
        artifact = self.ready_bundle()
        queued = self.import_job(artifact).json()["job"]
        original = AdminArtifact.objects.get(pk=artifact["id"])
        original.expires_at = timezone.now() - timedelta(seconds=1)
        original.save(update_fields=["expires_at"])
        with self.assertRaises(CMSFailure) as failure:
            cleanup_eligible(original)
        self.assertEqual(str(failure.exception.detail["code"]), "ARTIFACT_RETENTION_HOLD")
        self.assertEqual(self.post(self.client, f"jobs/{queued['id']}/cancel/", etag=f'"{queued["version"]}"').status_code, 200)
        self.assertIsNone(run_once())
        self.assert_no_imported_content()

    def test_generated_files_cleanup_is_visible_and_uses_the_existing_native_job(self):
        from .cms_artifacts import _path, cleanup_supported
        if not cleanup_supported():
            self.skipTest("The native private-file cleanup adapter is Windows-only")
        card = Flashcard.objects.create(slug="io-cleanup-card", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        user = self.user("io-cleanup-exporter", staff=True, caps=("cms_enter", "cms_learning_view",
            "cms_learning_export", "cms_artifact_download", "cms_artifact_upload"))
        client = self.sign_in(user)
        self.assertEqual(self.export_job([("flashcard", card)], client=client).status_code, 202)
        exported = run_once()
        self.assertEqual(exported.status, "succeeded", exported.error_code)
        for artifact in (exported.output_artifact, exported.artifact):
            with self.subTest(kind=artifact.kind):
                AdminArtifact.objects.filter(pk=artifact.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
                response = self.post(client, f"artifacts/{artifact.pk}/cleanup/", etag=f'"{artifact.version}"')
                self.assertEqual(response.status_code, 202, response.content[:300])
                job_id = response.json()["job"]["id"]
                listing = client.get(BASE + "jobs/")
                self.assertEqual(listing.status_code, 200)
                self.assertIn(job_id, [row["id"] for row in listing.json()["results"]])
                cleaned = run_once()
                self.assertEqual((cleaned.kind, cleaned.status), ("artifact_cleanup", "succeeded"), cleaned.error_code)
                artifact.refresh_from_db()
                self.assertIsNotNone(artifact.purged_at)
                self.assertFalse(_path(artifact).exists())
                self.assertEqual(self.download_learning(artifact.pk, client).status_code, 409)
        self.assertEqual(self.history(), self.before)

    def test_revoked_export_authority_hides_generated_metadata_even_with_edit_and_upload(self):
        card = Flashcard.objects.create(slug="io-hidden-metadata", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        user = self.user("io-metadata-exporter", staff=True, caps=("cms_enter", "cms_learning_view", "cms_learning_edit",
            "cms_learning_export", "cms_artifact_download", "cms_artifact_upload"))
        client = self.sign_in(user)
        self.assertEqual(self.export_job([("flashcard", card)], client=client).status_code, 202)
        job = run_once()
        user.user_permissions.remove(*user.user_permissions.filter(codename="cms_learning_export"))
        artifacts = client.get(BASE + "artifacts/")
        self.assertEqual(artifacts.status_code, 200)
        self.assertEqual(artifacts.json()["results"], [])
        jobs = client.get(BASE + "jobs/")
        self.assertEqual(jobs.status_code, 200)
        self.assertNotIn(str(job.pk), [row["id"] for row in jobs.json()["results"]])
        self.assertEqual(client.get(BASE + f"artifacts/{job.artifact_id}/").status_code, 403)
        self.assertEqual(self.download_learning(job.output_artifact_id, client).status_code, 403)

    def test_lease_expiring_during_storage_cannot_commit_ready_output(self):
        from .cms_artifacts import _path
        from .cms_learning_io import _store
        card = Flashcard.objects.create(slug="io-storage-deadline", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        queued = self.export_job([("flashcard", card)]).json()["job"]
        clock = []
        real_now = timezone.now

        def store_then_expire(artifact, raw):
            _store(artifact, raw)
            clock.append(AdminJob.objects.get(pk=queued["id"]).lease_expires_at + timedelta(seconds=1))

        with patch("atlas.cms_learning_io._store", side_effect=store_then_expire), patch(
                "atlas.cms_learning_io.timezone.now", side_effect=lambda: clock[-1] if clock else real_now()):
            first = run_once()
        self.assertEqual(first.status, "running")
        self.assertFalse(first.checkpoint.get("complete"))
        output = first.output_artifact
        self.assertEqual(output.state, "quarantine")
        self.assertEqual(self.download_learning(output.pk).status_code, 409)
        modified = _path(output).stat().st_mtime_ns
        AdminJob.objects.filter(pk=first.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        final = run_once()
        self.assertEqual(final.status, "succeeded", final.error_code)
        self.assertEqual(final.output_artifact_id, output.pk)
        self.assertEqual(_path(output).stat().st_mtime_ns, modified)
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.exported").count(), 1)

    def test_export_exact_byte_limit_includes_json_escaping(self):
        cards = [("flashcard", Flashcard.objects.create(slug=f"io-escaped-{index}", front="\x01" * 19000,
            back="\x01" * 19000, hint="\x01" * 19000, is_active=False, seed_managed=False)) for index in range(4)]
        self.assertEqual(self.export_job(cards).status_code, 202)
        job = run_once()
        self.assertEqual((job.status, job.error_code), ("failed", "JSON_LIMIT"))
        self.assertIsNone(job.output_artifact_id)


class LearningTransferMigrationTests(TransactionTestCase):
    def tearDown(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_0051_preserves_existing_job_and_artifact_values(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        old, new = ("atlas", "0050_v100_p13_learning_archive"), ("atlas", "0051_v100_p13_learning_io")
        executor = MigrationExecutor(connection)
        executor.migrate([old])
        apps = executor.loader.project_state([old]).apps
        artifact = apps.get_model("atlas", "AdminArtifact").objects.create(kind="research_json", domain="research",
            owner_ref="Synthetic", filename="synthetic-migration.json", storage_key=uuid.uuid4().hex + ".json",
            sha256="0" * 64, size=2, state="quarantine", expires_at=timezone.now() + timedelta(days=1))
        job = apps.get_model("atlas", "AdminJob").objects.create(kind="research_intake", actor_ref="Synthetic",
            artifact_id=artifact.pk, request_key=uuid.uuid4(), payload_digest="0" * 64,
            policy_version=1, available_at=timezone.now(), status="failed", error_code="INTERNAL_ERROR")
        before_artifact = apps.get_model("atlas", "AdminArtifact").objects.values().get(pk=artifact.pk)
        before_job = apps.get_model("atlas", "AdminJob").objects.values().get(pk=job.pk)
        executor = MigrationExecutor(connection)
        executor.migrate([new])
        apps = executor.loader.project_state([new]).apps
        self.assertEqual(apps.get_model("atlas", "AdminArtifact").objects.values().get(pk=artifact.pk), before_artifact)
        after = apps.get_model("atlas", "AdminJob").objects.values().get(pk=job.pk)
        self.assertIsNone(after.pop("output_artifact_id"))
        self.assertEqual(after, before_job)

    def test_reverse_after_new_transfer_rows_fails_closed_without_losing_intent(self):
        from django.db import connection, IntegrityError
        from django.db.migrations.executor import MigrationExecutor
        identifier = uuid.uuid4()
        artifact = AdminArtifact.objects.create(id=identifier, kind="learning_json", domain="learning",
            resource_type="learning_export_manifest", owner_ref="Synthetic", filename="synthetic-migration.json",
            storage_key=identifier.hex + ".json", sha256="0" * 64, size=2,
            expires_at=timezone.now() + timedelta(days=1))
        output = AdminArtifact.objects.create(kind="learning_export_json", domain="learning", resource_type="learning_export",
            owner_ref="Synthetic", filename="synthetic-output.json", storage_key=uuid.uuid4().hex + ".json",
            sha256="0" * 64, size=2, expires_at=timezone.now() + timedelta(days=1))
        job = AdminJob.objects.create(kind="learning_export", actor_ref="Synthetic", artifact=artifact, output_artifact=output,
            request_key=uuid.uuid4(), payload_digest="0" * 64, policy_version=1, available_at=timezone.now(), status="failed")
        with self.assertRaises(IntegrityError):
            MigrationExecutor(connection).migrate([("atlas", "0050_v100_p13_learning_archive")])
        restored = AdminJob.objects.get(pk=job.pk)
        self.assertEqual(restored.output_artifact_id, output.pk)
        self.assertEqual(restored.artifact_id, artifact.pk)
        self.assertTrue(AdminArtifact.objects.filter(pk=output.pk).exists())


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningTransferConcurrencyTests(LearningTransferFixture, TransactionTestCase):
    def test_identical_import_enqueues_converge_under_real_policy_lock(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        from .cms_jobs import enqueue_job
        artifact = self.ready_bundle()
        barrier, key = Barrier(2), uuid.uuid4()

        def enqueue():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                job = enqueue_job(self.owner.pk, self.sid, artifact["id"], key, uuid.uuid4(), kind="learning_import")
                return str(job.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: enqueue(), range(2)))
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(AdminJob.objects.count(), 1)
        self.assertEqual(run_once().status, "succeeded")
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.imported").count(), 1)
        self.assertEqual(self.history(), self.before)

    def test_two_workers_claim_and_apply_one_learning_import(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        self.assertEqual(self.import_job(self.ready_bundle()).status_code, 202)
        barrier = Barrier(2)

        def work():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                job = run_once()
                return job.status if job else None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: work(), range(2)))
        self.assertEqual(results.count("succeeded"), 1)
        self.assertEqual(Quiz.objects.count(), 2)
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.imported").count(), 1)
        self.assertEqual(self.history(), self.before)

    def _work_after_policy_wait(self, waited):
        from django.db import close_old_connections, connection

        def observe(execute, sql, params, many, context):
            if "pg_advisory_xact_lock" in sql:
                waited.set()
            return execute(sql, params, many, context)

        close_old_connections()
        try:
            with connection.execute_wrapper(observe):
                job = run_once()
                return job.status, job.error_code, job.output_artifact_id
        finally:
            close_old_connections()

    def test_manifest_is_stale_after_real_editor_commits_during_policy_wait(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from .cms_flashcard_editor import update_card
        from .cms_policy import policy_lock
        card = Flashcard.objects.create(slug="io-pg-stale", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        self.assertEqual(self.export_job([("flashcard", card)]).status_code, 202)
        waited = Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with policy_lock():
                future = pool.submit(self._work_after_policy_wait, waited)
                self.assertTrue(waited.wait(5))
                self.assertFalse(future.done())
                update_card(self.owner.pk, self.sid, card.pk, revision_etag(card), {"front": "Synthetic fresh version"}, uuid.uuid4())
            status, error, output = future.result(timeout=20)
        self.assertEqual((status, error, output), ("failed", "STALE_REVISION", None))
        self.assertEqual(self.history(), self.before)

    def test_export_authority_is_revoked_during_policy_wait_without_bytes(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from .cms_policy import policy_lock, mutate_role
        card = Flashcard.objects.create(slug="io-pg-revoked", front="Synthetic", back="Synthetic",
                                       is_active=False, seed_managed=False)
        caps = ("cms_enter", "cms_learning_view", "cms_learning_export", "cms_artifact_download")
        user = self.user("io-pg-exporter", staff=True, caps=caps)
        client = self.sign_in(user)
        self.assertEqual(self.export_job([("flashcard", card)], client=client).status_code, 202)
        waited = Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with policy_lock() as policy:
                future = pool.submit(self._work_after_policy_wait, waited)
                self.assertTrue(waited.wait(5))
                self.assertFalse(future.done())
                mutate_role(self.owner.pk, "user", user.pk,
                    {"permissions": [cap for cap in caps if cap != "cms_learning_export"]}, policy.version, self.sid)
            status, error, output = future.result(timeout=20)
        self.assertEqual(status, "failed")
        self.assertIn(error, {"UNAUTHENTICATED", "POLICY_CHANGED", "PERMISSION_DENIED"})
        self.assertIsNone(output)
        self.assertFalse(AdminArtifact.objects.filter(kind="learning_export_json").exists())
