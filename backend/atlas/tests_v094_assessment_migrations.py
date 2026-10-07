"""Portable legacy snapshots and disposable fresh install; no existing migration edits."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

LATEST = ("atlas", "0037_v094_assessments_atlas")


class AssessmentMigrationTests(TransactionTestCase):
    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def snapshot(self):
        with connection.cursor() as cursor:
            result = {}
            for table in sorted(connection.introspection.table_names(cursor)):
                if table.startswith("atlas_"):
                    cursor.execute("SELECT * FROM " + connection.ops.quote_name(table))
                    result[table] = sorted(cursor.fetchall(), key=repr)
            return result

    def upgrade(self, previous):
        executor = MigrationExecutor(connection)
        executor.migrate([previous])
        apps = executor.loader.project_state([previous]).apps
        category = apps.get_model("atlas", "Category").objects.create(slug="synthetic-migration-category", name_en="Synthetic migration category")
        apps.get_model("atlas", "Disorder").objects.create(slug="synthetic-preserved-disorder", name_en="Synthetic preserved disorder", category_id=category.pk)
        source = apps.get_model("atlas", "SourceReference").objects.create(title="Synthetic preserved bibliography")
        dataset = apps.get_model("atlas", "ResearchDataset").objects.create(key="synthetic-preserved-dataset", source_filename="synthetic.json", source_sha256="a" * 64,
            raw_text='{"synthetic":"preserved"}', raw_document={"synthetic": "preserved"})
        apps.get_model("atlas", "ResearchRecord").objects.create(dataset_id=dataset.pk, section="synthetic", external_id="preserved", payload={"value": "preserved"})
        if previous[1] == "0036_v092_brain_identifier_review":
            entity = apps.get_model("atlas", "BrainAnatomicalEntity").objects.create(slug="synthetic-preserved-brain", name_en="Synthetic preserved Brain", kind="structure", laterality="bilateral")
            apps.get_model("atlas", "BrainAnatomicalEntitySource").objects.create(entity_id=entity.pk, source_id=source.pk)
        before = self.snapshot()
        MigrationExecutor(connection).migrate([LATEST])
        after = self.snapshot()
        for table, rows in before.items():
            self.assertEqual(after[table], rows, table)
        self.assertEqual(len([table for table in after if table.startswith("atlas_assessment")]), 9)
        for table in after:
            if table.startswith("atlas_assessment"):
                self.assertEqual(after[table], [])
        MigrationExecutor(connection).migrate([previous])
        self.assertEqual(self.snapshot(), before)

    def test_released_v084_upgrade_and_reverse_preserve_legacy(self):
        self.upgrade(("atlas", "0032_v084_study_sessions"))

    def test_current_main_upgrade_and_reverse_preserve_legacy_and_brain(self):
        self.upgrade(("atlas", "0036_v092_brain_identifier_review"))

    def test_zero_to_latest_sqlite_integrity_and_foreign_keys(self):
        with tempfile.TemporaryDirectory(prefix="assessment-migration-") as directory:
            path = Path(directory) / "fresh.sqlite3"
            env = dict(os.environ, DB_ENGINE="sqlite", SQLITE_PATH=str(path), DEBUG="1")
            manage = Path(__file__).resolve().parents[1] / "manage.py"
            run = subprocess.run([sys.executable, str(manage), "migrate", "--noinput"], env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            with closing(sqlite3.connect(path)) as database:
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(database.execute("SELECT COUNT(*) FROM atlas_assessmentinstrument").fetchone()[0], 0)
                self.assertEqual(database.execute("SELECT name FROM django_migrations WHERE app='atlas' ORDER BY id DESC LIMIT 1").fetchone()[0], LATEST[1])
