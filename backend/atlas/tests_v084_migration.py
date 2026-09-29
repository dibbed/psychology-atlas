"""Historical 0031 -> 0032 and fresh-install StudySession migration checks."""

import os
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class StudySessionMigrationTests(TransactionTestCase):
    migrate_from = ("atlas", "0031_v083_recommendation_feedback")
    migrate_to = ("atlas", "0032_v084_study_sessions")

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_real_tip_upgrade_preserves_data_without_sessions(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        User = old_apps.get_model("auth", "User")
        Atlas = lambda name: old_apps.get_model("atlas", name)

        user = User.objects.create(username="session-migration", password="!")
        category = Atlas("Category").objects.create(slug="session-category", name_en="Category")
        disorder = Atlas("Disorder").objects.create(category_id=category.id, slug="session-disorder", name_en="Disorder")
        concept = Atlas("Concept").objects.create(slug="session-concept", name_en="Concept", simple_definition="Definition")
        Atlas("UserStudySettings").objects.create(user_id=user.id, default_daily_minutes=60, default_session_minutes=25)
        plan = Atlas("StudyPlan").objects.create(user_id=user.id, name="Historical", status="active", start_date=date(2026, 9, 1))
        Atlas("StudyPlanAvailability").objects.create(plan_id=plan.id, weekday=0, available_minutes=45)
        scope = Atlas("StudyPlanScope").objects.create(plan_id=plan.id, concept_id=concept.id, priority=4)
        Atlas("StudyBlock").objects.create(
            plan_id=plan.id, scope_id=scope.id, block_kind="concept_review", status="pending",
            scheduled_date=date(2026, 9, 3), estimated_minutes=25,
            snapshot_title="Historical", concept_id=concept.id,
        )
        Atlas("UserProgress").objects.create(user_id=user.id, disorder_id=disorder.id, progress_percent=20)
        Atlas("UserConceptProgress").objects.create(user_id=user.id, concept_id=concept.id, progress_percent=30)
        card = Atlas("Flashcard").objects.create(slug="session-card", front="Front", back="Back")
        Atlas("UserFlashcardProgress").objects.create(user_id=user.id, flashcard_id=card.id, due_at=timezone.now())
        quiz = Atlas("Quiz").objects.create(slug="session-quiz", title="Quiz")
        question = Atlas("QuizQuestion").objects.create(quiz_id=quiz.id, prompt="Question")
        choice = Atlas("QuizChoice").objects.create(question_id=question.id, text="Choice")
        quiz_attempt = Atlas("QuizAttempt").objects.create(user_id=user.id, quiz_id=quiz.id, status="completed", completed_at=timezone.now())
        Atlas("QuizAttemptAnswer").objects.create(attempt_id=quiz_attempt.id, question_id=question.id, selected_choice_id=choice.id, is_correct=False)
        case = Atlas("ClinicalCase").objects.create(slug="session-case", title="Case", patient_summary="Summary")
        revision = Atlas("CaseRevision").objects.create(case_id=case.id, version=1, title="Revision", patient_summary="Summary", content_hash="b" * 64)
        step = Atlas("CaseStep").objects.create(case_id=case.id, revision_id=revision.id, stable_key="intro", title="Intro", narrative="Narrative", sort_order=0)
        case_attempt = Atlas("CaseAttempt").objects.create(user_id=user.id, case_id=case.id, revision_id=revision.id, status="completed", completed_at=timezone.now())
        Atlas("CaseAttemptEvent").objects.create(attempt_id=case_attempt.id, step_id=step.id, event_type="terminal_complete", outcome="complete", state_version_before=0, state_version_after=1)
        Atlas("StudyActivity").objects.create(user_id=user.id, activity_type="quiz_completed", quiz_id=quiz.id)
        Atlas("RecommendationFeedback").objects.create(
            user_id=user.id, recommendation_key="r2_" + "0" * 64,
            recommendation_type="quiz_retry", target_type="quiz", target_id=quiz.id,
            reason_code="recent_incorrect_quiz_answers", context_ref=f"attempt:{quiz_attempt.id}",
            value="helpful", client_event_id=uuid.uuid4(),
        )

        names = (
            "Category", "Disorder", "Concept", "Flashcard", "Quiz", "QuizQuestion",
            "QuizChoice", "ClinicalCase", "CaseRevision", "CaseStep",
            "UserStudySettings", "StudyPlan", "StudyPlanAvailability", "StudyPlanScope",
            "StudyBlock", "RecommendationFeedback", "UserProgress", "UserConceptProgress",
            "UserFlashcardProgress", "QuizAttempt", "QuizAttemptAnswer", "CaseAttempt",
            "CaseAttemptEvent", "StudyActivity",
        )
        before_user = list(User.objects.order_by("pk").values())
        before = {name: list(Atlas(name).objects.order_by("pk").values()) for name in names}

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        self.assertEqual(list(new_apps.get_model("auth", "User").objects.order_by("pk").values()), before_user)
        for name in names:
            self.assertEqual(list(new_apps.get_model("atlas", name).objects.order_by("pk").values()), before[name], name)
        self.assertEqual(new_apps.get_model("atlas", "StudySession").objects.count(), 0)
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA integrity_check")
            self.assertEqual(cursor.fetchone()[0], "ok")
            cursor.execute("PRAGMA foreign_key_check")
            self.assertEqual(cursor.fetchall(), [])

    def test_fresh_install_has_empty_session_table(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "fresh.sqlite3"
            environment = os.environ.copy()
            environment["SQLITE_PATH"] = str(database)
            result = subprocess.run(
                [sys.executable, "manage.py", "migrate", "--noinput", "--skip-checks", "--verbosity", "0"],
                cwd=Path(__file__).resolve().parents[1], env=environment,
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM atlas_studysession").fetchone()[0], 0)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
