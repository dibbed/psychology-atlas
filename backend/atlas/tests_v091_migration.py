"""Released v0.8.4 -> Brain foundation and zero -> latest migration checks."""

import os
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class BrainFoundationMigrationTests(TransactionTestCase):
    migrate_from = ("atlas", "0032_v084_study_sessions")
    migrate_to = ("atlas", "0033_v091_brain_foundation")

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_v084_upgrade_and_reverse_preserve_all_legacy_atlas_rows(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        Atlas = lambda name: old_apps.get_model("atlas", name)
        User = old_apps.get_model("auth", "User")

        user = User.objects.create(username="brain-migration-fixture", password="!")
        source = Atlas("SourceReference").objects.create(title="Synthetic migration fixture")
        dataset = Atlas("ResearchDataset").objects.create(
            key="fixture-dataset", source_filename="fixture.json", source_sha256="a" * 64,
            raw_document={"fixture": [1, 2]}, raw_text='{"fixture":[1,2]}',
        )
        Atlas("ResearchRecord").objects.create(
            dataset_id=dataset.pk, section="research_gaps", external_id="fixture-1",
            payload={"kept": ["verbatim"]}, source_ids=[source.pk],
        )
        category = Atlas("Category").objects.create(slug="fixture-category", name_en="Category")
        Atlas("Disorder").objects.create(category_id=category.pk, slug="fixture-disorder", name_en="Disorder")
        concept = Atlas("Concept").objects.create(
            slug="fixture-concept", name_en="Concept", simple_definition="Definition"
        )
        plan = Atlas("StudyPlan").objects.create(
            user_id=user.pk, name="Historical plan", status="active", start_date=date(2026, 9, 1)
        )
        scope = Atlas("StudyPlanScope").objects.create(plan_id=plan.pk, concept_id=concept.pk)
        block = Atlas("StudyBlock").objects.create(
            plan_id=plan.pk, scope_id=scope.pk, block_kind="concept_review", status="in_progress",
            scheduled_date=date(2026, 9, 2), estimated_minutes=25,
            snapshot_title="Historical block", concept_id=concept.pk, started_at=timezone.now(),
        )
        Atlas("StudySession").objects.create(
            user_id=user.pk, plan_id=plan.pk, primary_block_id=block.pk,
            block_id_at_start=block.pk, client_event_id=uuid.uuid4(),
            planned_minutes=25, started_at=timezone.now(),
        )
        case = Atlas("ClinicalCase").objects.create(
            slug="fixture-case", title="Case", patient_summary="Fixture"
        )
        revision = Atlas("CaseRevision").objects.create(
            case_id=case.pk, version=1, title="Revision", patient_summary="Fixture",
            content_hash="b" * 64,
        )
        Atlas("CaseAttempt").objects.create(
            user_id=user.pk, case_id=case.pk, revision_id=revision.pk,
            status="completed", completed_at=timezone.now(),
        )

        with connection.cursor() as cursor:
            old_tables = sorted(t for t in connection.introspection.table_names(cursor) if t.startswith("atlas_"))
            before = {}
            for table in old_tables:
                cursor.execute(f'SELECT * FROM "{table}"')
                before[table] = sorted(cursor.fetchall(), key=repr)

        MigrationExecutor(connection).migrate([self.migrate_to])
        with connection.cursor() as cursor:
            for table, rows in before.items():
                cursor.execute(f'SELECT * FROM "{table}"')
                self.assertEqual(sorted(cursor.fetchall(), key=repr), rows, table)
            for table in (
                "atlas_brainanatomicalentity", "atlas_brainnetwork", "atlas_brainhierarchylink",
            ):
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                self.assertEqual(cursor.fetchone()[0], 0)
            if connection.vendor == "sqlite":
                cursor.execute("PRAGMA integrity_check")
                self.assertEqual(cursor.fetchone()[0], "ok")
                cursor.execute("PRAGMA foreign_key_check")
                self.assertEqual(cursor.fetchall(), [])

        MigrationExecutor(connection).migrate([self.migrate_from])
        with connection.cursor() as cursor:
            for table, rows in before.items():
                cursor.execute(f'SELECT * FROM "{table}"')
                self.assertEqual(sorted(cursor.fetchall(), key=repr), rows, table)

    def test_fresh_install_creates_empty_brain_tables(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "fresh.sqlite3"
            with patch.dict(os.environ, {"DB_ENGINE": "postgres"}):
                environment = os.environ.copy()
            environment["DB_ENGINE"] = "sqlite"
            environment["SQLITE_PATH"] = str(database)
            self.assertEqual(environment["DB_ENGINE"], "sqlite")
            result = subprocess.run(
                [sys.executable, "manage.py", "migrate", "--noinput", "--skip-checks", "--verbosity", "0"],
                cwd=Path(__file__).resolve().parents[1], env=environment,
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with closing(sqlite3.connect(database)) as db:
                for table in (
                    "atlas_brainanatomicalentity", "atlas_brainnetwork", "atlas_brainhierarchylink",
                ):
                    self.assertEqual(db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0], 0)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
