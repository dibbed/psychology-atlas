"""Recommendation V2 feedback schema and integrity audit regression tests."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from .models import RecommendationFeedback


def _key(rec_type, target_type, target_id, reason_code, context_ref):
    serialized = json.dumps(
        ["rec-v2", rec_type, target_type, target_id, reason_code, context_ref],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "r2_" + hashlib.sha256(serialized).hexdigest()


class V083RecommendationFeedbackAuditTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="rec-audit", password="unused")
        self.now = timezone.now()
        self.fields = {
            "user": self.user,
            "recommendation_type": "quiz_retry",
            "target_type": "quiz",
            "target_id": 42,
            "reason_code": "recent_incorrect_quiz_answers",
            "context_ref": "attempt:91",
            "recommendation_key": _key(
                "quiz_retry", "quiz", 42, "recent_incorrect_quiz_answers", "attempt:91"
            ),
            "client_event_id": uuid.uuid4(),
            "created_at": self.now,
            "value": "dismissed",
            "suppressed_until": self.now + timedelta(days=7),
        }

    def test_audit_accepts_valid_event_without_writing(self):
        event = RecommendationFeedback.objects.create(**self.fields)
        before = list(RecommendationFeedback.objects.values())
        output = StringIO()
        call_command("audit_recommendation_feedback", stdout=output)
        self.assertIn("events=1 failures=0", output.getvalue())
        self.assertEqual(list(RecommendationFeedback.objects.values()), before)
        self.assertEqual(event.recommendation_key, "r2_abd11712d8ebc0fe25cdc9be158dc3e9a3688254150b80a01443633344eafcd2")

    def test_audit_reports_bad_identity_and_expiry_without_repair(self):
        event = RecommendationFeedback.objects.create(**self.fields)
        bad_expiry = self.now + timedelta(days=8)
        RecommendationFeedback.objects.filter(pk=event.pk).update(
            recommendation_key="r2_" + "0" * 64,
            suppressed_until=bad_expiry,
        )
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("audit_recommendation_feedback", stdout=output)
        self.assertIn(f"feedback:{event.pk}:invalid_key", output.getvalue())
        self.assertIn(f"feedback:{event.pk}:invalid_suppression", output.getvalue())
        event.refresh_from_db()
        self.assertEqual(event.suppressed_until, bad_expiry)

    def test_audit_rejects_target_mismatch_without_repair(self):
        event = RecommendationFeedback.objects.create(**self.fields)
        RecommendationFeedback.objects.filter(pk=event.pk).update(target_id=None)
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("audit_recommendation_feedback", stdout=output)
        self.assertIn(f"feedback:{event.pk}:invalid_target_id", output.getvalue())
        self.assertIsNone(RecommendationFeedback.objects.get(pk=event.pk).target_id)


class V083RecommendationFeedbackMigrationTests(TransactionTestCase):
    reset_sequences = True
    migrate_from = ("atlas", "0030_studyblock_ck_study_block_started_status_and_more")
    migrate_to = ("atlas", "0031_v083_recommendation_feedback")

    def tearDown(self):
        MigrationExecutor(connection).migrate([("atlas", "0032_v084_study_sessions")])
        super().tearDown()

    def test_historical_upgrade_preserves_canonical_state_without_backfill(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        apps = executor.loader.project_state([self.migrate_from]).apps
        User = apps.get_model("auth", "User")
        Atlas = lambda name: apps.get_model("atlas", name)

        user = User.objects.create(username="rec-migration", email="rec-migration@example.com", password="!")
        category = Atlas("Category").objects.create(slug="rec-migration", name_en="Migration")
        disorder = Atlas("Disorder").objects.create(category_id=category.pk, slug="rec-migration-disorder", name_en="Migration")
        concept = Atlas("Concept").objects.create(slug="rec-migration-concept", name_en="Migration", simple_definition="Definition")
        settings = Atlas("UserStudySettings").objects.create(user_id=user.pk, study_timezone="Asia/Tehran", default_daily_minutes=50, default_session_minutes=25)
        plan = Atlas("StudyPlan").objects.create(
            user_id=user.pk, name="Historical plan", status="active", start_date=date(2026, 9, 1),
            generation_version=2, generation_fingerprint="a" * 64,
            last_generation_summary={"version": 2, "scheduled_blocks": 1},
        )
        availability = Atlas("StudyPlanAvailability").objects.create(plan_id=plan.pk, weekday=0, available_minutes=45)
        scope = Atlas("StudyPlanScope").objects.create(plan_id=plan.pk, concept_id=concept.pk, priority=4, sort_order=0)
        block = Atlas("StudyBlock").objects.create(
            plan_id=plan.pk, scope_id=scope.pk, block_kind="concept_review", status="pending",
            scheduled_date=date(2026, 9, 3), estimated_minutes=25,
            snapshot_title="Historical block", concept_id=concept.pk, generation_version=2,
        )
        progress = Atlas("UserProgress").objects.create(user_id=user.pk, disorder_id=disorder.pk, progress_percent=40)
        Atlas("UserConceptProgress").objects.create(user_id=user.pk, concept_id=concept.pk, progress_percent=35)
        card = Atlas("Flashcard").objects.create(slug="rec-migration-card", front="Front", back="Back")
        srs = Atlas("UserFlashcardProgress").objects.create(user_id=user.pk, flashcard_id=card.pk, due_at=timezone.now())
        quiz = Atlas("Quiz").objects.create(slug="rec-migration-quiz", title="Quiz")
        question = Atlas("QuizQuestion").objects.create(quiz_id=quiz.pk, prompt="Question")
        choice = Atlas("QuizChoice").objects.create(question_id=question.pk, text="Answer")
        quiz_attempt = Atlas("QuizAttempt").objects.create(user_id=user.pk, quiz_id=quiz.pk, status="completed", completed_at=timezone.now())
        answer = Atlas("QuizAttemptAnswer").objects.create(attempt_id=quiz_attempt.pk, question_id=question.pk, selected_choice_id=choice.pk, is_correct=False)
        case = Atlas("ClinicalCase").objects.create(slug="rec-migration-case", title="Case", patient_summary="Summary")
        revision = Atlas("CaseRevision").objects.create(case_id=case.pk, version=1, title="Revision", patient_summary="Summary", content_hash="b" * 64)
        step = Atlas("CaseStep").objects.create(case_id=case.pk, revision_id=revision.pk, stable_key="intro", title="Intro", narrative="Narrative", sort_order=0)
        case_attempt = Atlas("CaseAttempt").objects.create(user_id=user.pk, case_id=case.pk, revision_id=revision.pk, status="completed", completed_at=timezone.now())
        event = Atlas("CaseAttemptEvent").objects.create(attempt_id=case_attempt.pk, step_id=step.pk, event_type="terminal_complete", outcome="complete", state_version_before=0, state_version_after=1)
        activity = Atlas("StudyActivity").objects.create(user_id=user.pk, activity_type="quiz_completed", quiz_id=quiz.pk)

        preserved = {
            name: list(Atlas(name).objects.order_by("pk").values())
            for name in (
                "UserStudySettings", "StudyPlan", "StudyPlanAvailability", "StudyPlanScope", "StudyBlock",
                "UserProgress", "UserConceptProgress", "UserFlashcardProgress", "QuizAttempt", "QuizAttemptAnswer",
                "CaseAttempt", "CaseAttemptEvent", "StudyActivity",
            )
        }
        self.assertEqual(len(preserved["StudyBlock"]), 1)
        self.assertEqual(len(preserved["CaseAttemptEvent"]), 1)
        self.assertEqual(len(preserved["QuizAttemptAnswer"]), 1)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        self.assertEqual(new_apps.get_model("auth", "User").objects.get(pk=user.pk).email, user.email)
        for name, before in preserved.items():
            self.assertEqual(list(new_apps.get_model("atlas", name).objects.order_by("pk").values()), before, name)
        self.assertEqual(new_apps.get_model("atlas", "RecommendationFeedback").objects.count(), 0)
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA integrity_check")
            self.assertEqual(cursor.fetchone()[0], "ok")
            cursor.execute("PRAGMA foreign_key_check")
            self.assertEqual(cursor.fetchall(), [])

    def test_fresh_install_creates_empty_feedback_table(self):
        with TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "fresh.sqlite3"
            environment = os.environ.copy()
            environment["SQLITE_PATH"] = str(database)
            result = subprocess.run(
                [sys.executable, "manage.py", "migrate", "--noinput", "--skip-checks", "--verbosity", "0"],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM atlas_recommendationfeedback").fetchone()[0], 0)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
