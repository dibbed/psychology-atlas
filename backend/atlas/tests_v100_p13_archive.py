"""Archive lifecycle: real CMS sessions and immutable learner evidence."""
import uuid
from unittest.mock import patch

from django.core.exceptions import ValidationError as ModelValidationError
from django.db import DatabaseError
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from .models import (Quiz, QuizQuestion, QuizChoice, QuizAttempt, QuizAttemptAnswer,
    Flashcard, UserFlashcardProgress, DailyChallenge, DailyChallengeChoice, DailyChallengeAttempt,
    CognitiveDistortionPracticeItem, CognitiveDistortionPracticeChoice,
    CognitiveDistortionPracticeAttempt, Concept, StudyActivity)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningArchiveTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client_owner = self.sign_in(self.owner)
        self.quiz = Quiz.objects.create(slug="archive-synthetic", title="Synthetic quiz", is_active=True)
        self.body = {"reason": "CONTENT_ARCHIVE", "idempotency_key": str(uuid.uuid4())}

    def tag(self):
        return self.client_owner.get(BASE + f"learning/quizzes/{self.quiz.pk}/")["ETag"]

    def archive(self, client=None, tag=None, body=None):
        return self.post(client or self.client_owner, f"learning/archive/quiz/{self.quiz.pk}/",
                         body or self.body, etag=tag or self.tag())

    def authorize(self, tag, client=None, user=None, body=None):
        self.step_up(client or self.client_owner, user or self.owner, "learning_archive", self.quiz.pk,
                     {"kind": "quiz", "etag": int(tag.strip('"')), **(body or self.body)})

    def test_missing_step_up_denied_without_mutation(self):
        response = self.archive()
        self.assertEqual(response.status_code, 403, response.content[:300])
        self.quiz.refresh_from_db()
        self.assertTrue(self.quiz.is_active)

    def test_archive_preserves_historical_ids_and_same_key_retry(self):
        question = QuizQuestion.objects.create(quiz=self.quiz, prompt="Synthetic question")
        choice = QuizChoice.objects.create(question=question, text="Synthetic choice", is_correct=True)
        attempt = QuizAttempt.objects.create(user=self.normal, quiz=self.quiz, status="completed")
        answer = QuizAttemptAnswer.objects.create(attempt=attempt, question=question,
                                                  selected_choice=choice, is_correct=True)
        tag = self.tag()
        self.authorize(tag)
        response = self.archive(tag=tag)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["newly_archived"])
        self.assertFalse(response.json()["publication_available"])
        self.assertNotEqual(response["ETag"], tag)
        retry = self.archive(tag=tag)
        self.assertEqual(retry.status_code, 200, retry.content[:300])
        self.assertFalse(retry.json()["newly_archived"])
        self.assertEqual(retry.json()["receipt_id"], response.json()["receipt_id"])
        answer.refresh_from_db()
        self.assertEqual((answer.question_id, answer.selected_choice_id, answer.is_correct),
                         (question.pk, choice.pk, True))
        self.assertTrue(QuizAttempt.objects.filter(pk=attempt.pk).exists())
        learner = APIClient()
        learner.force_authenticate(self.normal)
        dashboard = learner.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["quizzes_completed"], 1)

    def test_private_detail_exposes_archive_state(self):
        response = self.client_owner.get(BASE + f"learning/quizzes/{self.quiz.pk}/")
        self.assertIn("archived_at", response.json())
        self.assertIsNone(response.json()["archived_at"])

    def learning_items(self):
        concept = Concept.objects.create(slug="archive-distortion", name_en="Synthetic distortion",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        other = Concept.objects.create(slug="archive-other", name_en="Synthetic other",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        card = Flashcard.objects.create(slug="archive-card", front="Synthetic front", back="Synthetic back")
        daily = DailyChallenge.objects.create(prompt="Synthetic daily")
        daily.choices.create(text="Synthetic right", is_correct=True)
        daily.choices.create(text="Synthetic wrong", is_correct=False)
        item = CognitiveDistortionPracticeItem.objects.create(slug="archive-practice",
            prompt="Synthetic practice", target_concept=concept)
        item.choices.create(concept=concept, text="Synthetic right", is_correct=True)
        item.choices.create(concept=other, text="Synthetic wrong", is_correct=False)
        return [("quiz", self.quiz, f"learning/quizzes/{self.quiz.pk}/"),
                ("flashcard", card, f"learning/flashcards/{card.pk}/"),
                ("daily", daily, f"learning/practice/daily/{daily.pk}/"),
                ("distortions", item, f"learning/practice/distortions/{item.pk}/")]

    def archive_fixture(self, kind, item, path):
        tag = self.client_owner.get(BASE + path)["ETag"]
        body = {"reason": "CONTENT_ARCHIVE", "idempotency_key": str(uuid.uuid4())}
        self.step_up(self.client_owner, self.owner, "learning_archive", item.pk,
                     {"kind": kind, "etag": int(tag.strip('"')), **body})
        response = self.post(self.client_owner, f"learning/archive/{kind}/{item.pk}/", body, etag=tag)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response

    def test_all_kinds_archived_and_editor_denied_even_after_active_resurrection(self):
        from .cms_learning_lifecycle_models import LearningArchiveReceipt
        from .cms_models import AdminAuditEvent
        for kind, item, path in self.learning_items():
            with self.subTest(kind=kind):
                result = self.archive_fixture(kind, item, path)
                item.refresh_from_db()
                self.assertIsNotNone(item.archived_at)
                self.assertFalse(item.is_active)
                detail = self.client_owner.get(BASE + path)
                self.assertIsNotNone(detail.json()["archived_at"])
                catalog = self.client_owner.get(BASE + path.rsplit(str(item.pk) + "/", 1)[0])
                self.assertTrue(any(row["archived_at"] for row in catalog.json()["results"]))
                # Even a direct import changing active cannot undo the lifecycle gate.
                type(item).objects.filter(pk=item.pk).update(is_active=True, seed_managed=False)
                if kind == "quiz":
                    edit, body = "metadata/", {"title": "Rewrite", "description": "", "disorder_id": None}
                elif kind == "flashcard":
                    edit, body = "metadata/", {"front": "Rewrite"}
                else:
                    edit, body = "edit/", {"prompt": "Rewrite", "explanation": "", "choices": []}
                self.assertEqual(self.post(self.client_owner, path + edit, body,
                    etag=result["ETag"]).status_code, 409)
        self.assertEqual(LearningArchiveReceipt.objects.count(), 4)
        self.assertEqual(AdminAuditEvent.objects.filter(action="learning.archived").count(), 4)

    def test_stale_tag_forged_binding_and_key_reuse_are_denied(self):
        tag = self.tag()
        self.authorize(tag)
        self.assertEqual(self.archive(tag=f'"{int(tag.strip(chr(34))) - 1}"').status_code, 412)
        forged = {**self.body, "idempotency_key": str(uuid.uuid4())}
        self.assertEqual(self.archive(tag=tag, body=forged).status_code, 403)
        result = self.archive(tag=tag)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.archive(tag=result["ETag"]).status_code, 409)
        other = Quiz.objects.create(slug="archive-key-target", title="Other quiz")
        self.assertEqual(self.post(self.client_owner, f"learning/archive/quiz/{other.pk}/",
            self.body, etag=tag).status_code, 409)

    def test_receipt_or_audit_failure_rolls_back_item_and_step_up(self):
        from .cms_learning_lifecycle_models import LearningArchiveReceipt
        from .cms_models import AdminAuditEvent
        tag = self.tag()
        self.authorize(tag)
        for target in ("LearningArchiveReceipt", "AdminAuditEvent"):
            with self.subTest(target=target):
                with patch(f"atlas.cms_learning_lifecycle.{target}.objects.create",
                           side_effect=DatabaseError("Synthetic rollback")):
                    self.assertEqual(self.archive(tag=tag).status_code, 503)
                self.quiz.refresh_from_db()
                self.assertTrue(self.quiz.is_active)
                self.assertIsNone(self.quiz.archived_at)
                self.assertEqual(self.tag(), tag)
                self.assertFalse(LearningArchiveReceipt.objects.exists())
                self.assertFalse(AdminAuditEvent.objects.filter(action="learning.archived").exists())
        self.assertEqual(self.archive(tag=tag).status_code, 200)

    def test_permissions_mfa_and_closed_payload(self):
        from .tests_v100_p01 import PASSWORD
        for held in [("cms_learning_view",), ("cms_learning_archive",)]:
            user = self.user("archive-" + held[0], staff=True, caps=("cms_enter", *held))
            client = self.sign_in(user)
            self.assertEqual(self.archive(client=client).status_code, 403)
        self.assertEqual(self.archive(client=Client(enforce_csrf_checks=True)).status_code, 403)
        password_only = Client(enforce_csrf_checks=True)
        self.post(password_only, "auth/login/", {"username": self.owner.username, "password": PASSWORD})
        self.assertEqual(self.archive(client=password_only).status_code, 403)
        for body in ({"reason": "OTHER", "idempotency_key": str(uuid.uuid4())},
                     {**self.body, "is_active": False},
                     {"reason": "CONTENT_ARCHIVE", "idempotency_key": "bad"},
                     {"reason": "CONTENT_ARCHIVE"}):
            self.assertEqual(self.archive(body=body).status_code, 400)
        self.assertEqual(self.post(self.client_owner, f"learning/archive/forged/{self.quiz.pk}/",
                                  self.body, etag=self.tag()).status_code, 404)

    def test_permission_revocation_after_lock_wait_and_after_successful_retry(self):
        from .cms_sessions import current_session
        user = self.user("archive-revoked", staff=True,
            caps=("cms_enter", "cms_learning_view", "cms_learning_archive"))
        client = self.sign_in(user)
        tag = self.tag()
        self.authorize(tag, client, user)
        calls = []
        def revoke_after_wait(*args, **kwargs):
            calls.append(True)
            if len(calls) == 2:
                user.user_permissions.clear()
                self.grant(user, "cms_enter", "cms_learning_view")
            return current_session(*args, **kwargs)
        with patch("atlas.cms_learning_lifecycle.current_session", side_effect=revoke_after_wait):
            self.assertEqual(self.archive(client=client, tag=tag).status_code, 403)
        self.quiz.refresh_from_db()
        self.assertIsNone(self.quiz.archived_at)
        self.grant(user, "cms_learning_archive")
        self.assertEqual(self.archive(client=client, tag=tag).status_code, 200)
        user.user_permissions.clear()
        self.grant(user, "cms_enter", "cms_learning_view")
        self.assertEqual(self.archive(client=client, tag=tag).status_code, 403)

    def test_archives_remain_unavailable_to_public_helpers_search_and_new_evidence(self):
        from .cms_public_rights import public_cache_safe, public_resources, public_visible
        from .learning import available_flashcards, review_flashcard, today_challenge
        from .services import submit_quiz
        from .views import available_quizzes, _practice_item_queryset
        fixtures = self.learning_items()
        q = QuizQuestion.objects.create(quiz=self.quiz, prompt="Synthetic question")
        c = QuizChoice.objects.create(question=q, text="Synthetic choice", is_correct=True)
        card = fixtures[1][1]
        progress = UserFlashcardProgress.objects.create(user=self.normal, flashcard=card,
            repetitions=4, interval_days=13, ease_factor=2.7)
        before = (progress.pk, progress.repetitions, progress.interval_days, progress.ease_factor)
        self.assertTrue(public_visible(self.quiz))
        self.assertTrue(public_cache_safe())
        for kind, item, path in fixtures:
            self.archive_fixture(kind, item, path)
            type(item).objects.filter(pk=item.pk).update(is_active=True)
        self.assertFalse(public_cache_safe())
        self.assertFalse(available_quizzes().exists())
        self.assertFalse(available_flashcards().exists())
        self.assertIsNone(today_challenge())
        self.assertFalse(_practice_item_queryset().exists())
        self.assertFalse(public_resources(Quiz).exists())
        self.assertFalse(public_resources(Flashcard).exists())
        self.assertFalse(public_visible(self.quiz))  # supplied instance was admitted before archive
        self.assertEqual(self.client_owner.get("/api/quizzes/" + self.quiz.slug + "/").status_code, 404)
        self.assertEqual(self.client_owner.get("/api/flashcards/" + card.slug + "/").status_code, 404)
        with self.assertRaises(ValidationError):
            submit_quiz(user=self.normal, quiz=self.quiz,
                answers=[{"question_id": q.pk, "choice_id": c.pk}])
        with self.assertRaises(ValueError):
            review_flashcard(user=self.normal, flashcard=card, rating="good")
        progress.refresh_from_db()
        self.assertEqual(before, (progress.pk, progress.repetitions, progress.interval_days, progress.ease_factor))
        self.assertFalse(QuizAttempt.objects.exists())
        self.assertFalse(StudyActivity.objects.exists())

    def test_today_scheduler_recommendations_and_publication_inventory_exclude_archives(self):
        from .models import StudyPlan, StudyPlanScope, StudyBlock
        from .study_scheduler import _block_target_active, _build_candidates
        from .study_today import _actionable_target_filter
        from .recommendations_v2 import build_candidates
        fixtures = self.learning_items()
        practice = fixtures[3][1]
        day = timezone.localdate()
        plan = StudyPlan.objects.create(user=self.normal, name="Synthetic plan", start_date=day)
        scopes = [StudyPlanScope.objects.create(plan=plan, quiz=self.quiz),
                  StudyPlanScope.objects.create(plan=plan, concept=practice.target_concept, include_practice=True)]
        blocks = [StudyBlock.objects.create(plan=plan, block_kind="quiz_practice", quiz=self.quiz,
            scheduled_date=day, estimated_minutes=10, snapshot_title="Synthetic quiz block"),
            StudyBlock.objects.create(plan=plan, block_kind="distortion_practice", concept=practice.target_concept,
            scheduled_date=day, estimated_minutes=10, snapshot_title="Synthetic practice block")]
        for kind, item, path in fixtures:
            self.archive_fixture(kind, item, path)
            # A seeded active flag still cannot restore a runnable target.
            type(item).objects.filter(pk=item.pk).update(is_active=True)
        for block in blocks:
            block.refresh_from_db()
            self.assertFalse(_block_target_active(block))
        self.assertFalse(StudyBlock.objects.filter(_actionable_target_filter(day, False)).exists())
        candidates, _ = build_candidates(self.normal, timezone.now(), today=day)
        self.assertFalse(any(c["type"] in {"quiz_retry", "distortion_practice", "due_review", "srs_start"}
                             or c["target"]["type"] == "quiz" for c in candidates))
        scheduled, _ = _build_candidates(plan, scopes, day, day)
        self.assertFalse(any(c.block_kind in {"quiz_practice", "distortion_practice"} for c in scheduled))
        learner = APIClient()
        learner.force_authenticate(self.normal)
        today = learner.get("/api/study/today/")
        self.assertEqual(today.status_code, 200, today.content[:300])
        self.assertEqual(today.json()["today_blocks"]["total"], 0)
        self.assertFalse(today.json()["daily_challenge"]["available"])
        self.assertEqual(today.json()["review"]["new"], 0)
        for _, item, _ in fixtures:
            type(item).objects.filter(pk=item.pk).update(is_active=False)
        inventory = self.client_owner.get(BASE + "publication/preflight/?domain=learning")
        self.assertEqual(inventory.status_code, 200)
        self.assertEqual(inventory.json()["results"], [])

    def test_daily_historical_read_retains_archived_pinned_challenge(self):
        _, daily, path = self.learning_items()[2]
        choice = daily.choices.first()
        attempt = DailyChallengeAttempt.objects.create(user=self.normal, challenge=daily,
            activity_date=timezone.localdate(), selected_choice=choice, is_correct=choice.is_correct)
        self.archive_fixture("daily", daily, path)
        learner = APIClient()
        learner.force_authenticate(self.normal)
        result = learner.get("/api/daily-challenge/")
        self.assertEqual(result.status_code, 200, result.content[:300])
        self.assertEqual(result.json()["attempt"]["selected_choice_id"], choice.pk)
        attempt.refresh_from_db()
        self.assertEqual((attempt.challenge_id, attempt.selected_choice_id), (daily.pk, choice.pk))

    def test_daily_and_distortion_admitted_before_archive_cannot_create_attempt(self):
        from .views import _practice_item_queryset
        fixtures = self.learning_items()
        learner = APIClient()
        learner.force_authenticate(self.normal)
        daily = fixtures[2][1]
        daily_choice = daily.choices.first()
        DailyChallenge.objects.filter(pk=daily.pk).update(archived_at=timezone.now())
        with patch("atlas.views.today_challenge", return_value=daily):
            response = learner.post("/api/daily-challenge/",
                {"choice_id": daily_choice.pk}, content_type="application/json")
        self.assertEqual(response.status_code, 404, response.content[:300])
        item = fixtures[3][1]
        admitted = list(_practice_item_queryset())
        CognitiveDistortionPracticeItem.objects.filter(pk=item.pk).update(archived_at=timezone.now())
        with patch("atlas.views._practice_item_queryset", return_value=admitted):
            response = learner.post(f"/api/cognitive-distortions/practice/{item.slug}/submit/",
                {"choice_id": item.choices.first().pk}, content_type="application/json")
        self.assertEqual(response.status_code, 404, response.content[:300])
        self.assertFalse(DailyChallengeAttempt.objects.exists())
        self.assertFalse(CognitiveDistortionPracticeAttempt.objects.exists())
        self.assertFalse(StudyActivity.objects.exists())

    def test_receipt_append_only_and_safe_actor_erasure(self):
        from .cms_learning_lifecycle_models import LearningArchiveReceipt
        self.authorize(self.tag())
        self.assertEqual(self.archive().status_code, 200)
        receipt = LearningArchiveReceipt.objects.get()
        with self.assertRaises(ModelValidationError):
            receipt.delete()
        with self.assertRaises(ModelValidationError):
            LearningArchiveReceipt.objects.update(kind="flashcard")
        actor_ref = receipt.actor_ref
        self.owner.delete()
        receipt.refresh_from_db()
        self.assertIsNone(receipt.actor_id)
        self.assertEqual(receipt.actor_ref, actor_ref)


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningArchiveConcurrencyTests(SecurityFixture, TransactionTestCase):
    """PostgreSQL: a learner admitted before archive waits, then fails closed."""
    def test_all_four_admitted_learner_writes_wait_for_archive(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import close_old_connections, connection, transaction
        from .cms_case_editor import revision_etag
        from .cms_learning_lifecycle import archive_learning
        from .learning import review_flashcard
        from .services import submit_quiz

        client = self.sign_in(self.owner)
        quiz = Quiz.objects.create(slug="archive-concurrent-quiz", title="Synthetic quiz")
        question = quiz.questions.create(prompt="Synthetic question")
        choice = question.choices.create(text="Synthetic answer", is_correct=True)
        card = Flashcard.objects.create(slug="archive-concurrent-card", front="Front", back="Back")
        daily = DailyChallenge.objects.create(prompt="Synthetic daily")
        daily_choice = daily.choices.create(text="Synthetic right", is_correct=True)
        daily.choices.create(text="Synthetic wrong", is_correct=False)
        concept = Concept.objects.create(slug="archive-concurrent-concept", name_en="Synthetic",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        other = Concept.objects.create(slug="archive-concurrent-other", name_en="Synthetic other",
            subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        practice = CognitiveDistortionPracticeItem.objects.create(slug="archive-concurrent-practice",
            prompt="Synthetic practice", target_concept=concept)
        practice_choice = practice.choices.create(concept=concept, text="Synthetic right", is_correct=True)
        practice.choices.create(concept=other, text="Synthetic wrong", is_correct=False)
        for kind, item in [("quiz", quiz), ("flashcard", card), ("daily", daily), ("distortions", practice)]:
            with self.subTest(kind=kind):
                expected = revision_etag(item)
                body = {"reason": "CONTENT_ARCHIVE", "idempotency_key": str(uuid.uuid4())}
                self.step_up(client, self.owner, "learning_archive", item.pk,
                             {"kind": kind, "etag": expected, **body})
                session_id = client.session["cms_session_id"]
                started = Event()

                def learner_write():
                    close_old_connections()
                    def observe_lock(execute, sql, params, many, context):
                        if "FOR UPDATE" in sql and item._meta.db_table in sql:
                            started.set()
                        return execute(sql, params, many, context)
                    try:
                        with connection.execute_wrapper(observe_lock):
                            if kind == "quiz":
                                submit_quiz(user=self.normal, quiz=item, answers=[{
                                    "question_id": question.pk, "choice_id": choice.pk}])
                            elif kind == "flashcard":
                                review_flashcard(user=self.normal, flashcard=item, rating="good")
                            else:
                                learner = APIClient()
                                learner.force_authenticate(self.normal)
                                url = ("/api/daily-challenge/" if kind == "daily" else
                                    f"/api/cognitive-distortions/practice/{item.slug}/submit/")
                                choice_id = daily_choice.pk if kind == "daily" else practice_choice.pk
                                response = learner.post(url, {"choice_id": choice_id}, format="json")
                                if response.status_code == 404:
                                    return "archived_denied"
                            return "unexpected_success"
                    except (ValidationError, ValueError):
                        return "archived_denied"
                    finally:
                        close_old_connections()

                with ThreadPoolExecutor(max_workers=1) as executor:
                    with transaction.atomic():
                        type(item).objects.select_for_update().get(pk=item.pk)
                        future = executor.submit(learner_write)
                        self.assertTrue(started.wait(5))
                        # The held canonical row forces the already-admitted learner to wait.
                        self.assertFalse(future.done())
                        archive_learning(self.owner.pk, session_id, kind, item.pk,
                                         expected, body, uuid.uuid4())
                    self.assertEqual(future.result(timeout=10), "archived_denied")
        self.assertFalse(QuizAttempt.objects.exists())
        self.assertFalse(UserFlashcardProgress.objects.exists())
        self.assertFalse(DailyChallengeAttempt.objects.exists())
        self.assertFalse(CognitiveDistortionPracticeAttempt.objects.exists())
        self.assertFalse(StudyActivity.objects.exists())


class LearningArchiveMigrationTests(TransactionTestCase):
    def tearDown(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_0049_upgrade_preserves_all_content_evidence_and_srs_values(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        old_tip = ("atlas", "0049_v100_p16_case_publication")
        new_tip = ("atlas", "0050_v100_p13_learning_archive")
        executor = MigrationExecutor(connection)
        executor.migrate([old_tip])
        old_apps = executor.loader.project_state([old_tip]).apps
        model = lambda name: old_apps.get_model("atlas", name)
        user = old_apps.get_model("auth", "User").objects.create(username="archive-migration", password="!")
        concept = model("Concept").objects.create(slug="archive-migration-concept", name_en="Synthetic")
        quiz = model("Quiz").objects.create(slug="archive-migration-quiz", title="Synthetic quiz")
        question = model("QuizQuestion").objects.create(quiz=quiz, prompt="Synthetic question")
        choice = model("QuizChoice").objects.create(question=question, text="Synthetic answer", is_correct=True)
        attempt = model("QuizAttempt").objects.create(user_id=user.pk, quiz=quiz,
            status="completed", score=100, correct_count=1, total_questions=1)
        model("QuizAttemptAnswer").objects.create(attempt=attempt, question=question,
            selected_choice=choice, is_correct=True)
        model("StudyActivity").objects.create(user_id=user.pk, quiz=quiz, activity_type="quiz_completed")
        card = model("Flashcard").objects.create(slug="archive-migration-card", front="Synthetic front", back="Synthetic back")
        model("UserFlashcardProgress").objects.create(user_id=user.pk, flashcard=card,
            repetitions=8, interval_days=21, ease_factor=2.4, lapses=2)
        daily = model("DailyChallenge").objects.create(prompt="Synthetic daily")
        daily_choice = model("DailyChallengeChoice").objects.create(challenge=daily, text="Synthetic", is_correct=True)
        model("DailyChallengeAttempt").objects.create(user_id=user.pk, challenge=daily,
            selected_choice=daily_choice, activity_date=timezone.localdate(), is_correct=True)
        practice = model("CognitiveDistortionPracticeItem").objects.create(
            slug="archive-migration-practice", prompt="Synthetic practice", target_concept=concept)
        practice_choice = model("CognitiveDistortionPracticeChoice").objects.create(item=practice,
            concept=concept, text="Synthetic", is_correct=True)
        model("CognitiveDistortionPracticeAttempt").objects.create(user_id=user.pk, item=practice,
            selected_choice=practice_choice, is_correct=True)
        names = ("Concept", "Quiz", "QuizQuestion", "QuizChoice", "QuizAttempt", "QuizAttemptAnswer",
            "StudyActivity", "Flashcard", "UserFlashcardProgress", "DailyChallenge", "DailyChallengeChoice",
            "DailyChallengeAttempt", "CognitiveDistortionPracticeItem", "CognitiveDistortionPracticeChoice",
            "CognitiveDistortionPracticeAttempt")
        before = {name: list(model(name).objects.order_by("pk").values()) for name in names}
        executor = MigrationExecutor(connection)
        executor.migrate([new_tip])
        apps = executor.loader.project_state([new_tip]).apps
        for name in names:
            rows = list(apps.get_model("atlas", name).objects.order_by("pk").values())
            for row in rows:
                if "archived_at" in row:
                    self.assertIsNone(row.pop("archived_at"))
            self.assertEqual(rows, before[name], name)
        self.assertEqual(apps.get_model("atlas", "LearningArchiveReceipt").objects.count(), 0)
