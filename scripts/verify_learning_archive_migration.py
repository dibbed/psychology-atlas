"""Rehearse the additive archive migration on a private TEMP copy only."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/data/psychology_atlas.sqlite3"


def snapshot(database, columns=None):
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        if columns is None:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'django_migrations'")]
            columns = {table: [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
                       for table in tables}
        rows = {table: set(connection.execute('SELECT ' + ','.join('"' + name + '"' for name in names)
                                             + ' FROM "' + table + '"').fetchall())
                for table, names in columns.items()}
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        return columns, rows


def main():
    original_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="atlas-archive-migration-") as directory:
        database = Path(directory) / "copy.sqlite3"
        with closing(sqlite3.connect(SOURCE.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(database)) as copy:
                source.backup(copy)
        columns, before = snapshot(database)
        env = dict(os.environ, DB_ENGINE="sqlite", SQLITE_PATH=str(database),
                   SQLITE_TEST_PATH=str(Path(directory) / "tests.sqlite3"), DEBUG="1")
        for target in ("0050_v100_p13_learning_archive", "0048_v100_p11_assessment_domains",
                       "0050_v100_p13_learning_archive"):
            run = subprocess.run([sys.executable, str(ROOT / "backend/manage.py"), "migrate", "atlas",
                                  target, "--noinput"], env=env, capture_output=True, text=True, timeout=180)
            if run.returncode:
                raise RuntimeError("Migration rehearsal failed: " + run.stderr[-1800:])
            _, after = snapshot(database, columns)
            for table, rows in before.items():
                if table in {"auth_permission", "django_content_type"}:
                    assert rows <= after[table], table
                else:
                    assert rows == after[table], table
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM atlas_learningarchivereceipt").fetchone() == (0,)
            for table in ("atlas_quiz", "atlas_flashcard", "atlas_dailychallenge", "atlas_cognitivedistortionpracticeitem"):
                assert connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE archived_at IS NOT NULL').fetchone() == (0,)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == original_hash
    print(json.dumps({"status": "PASS", "upgrade_reverse_reupgrade": True,
                      "preserved_tables": len(before), "source_sha256": original_hash,
                      "source_unchanged": True, "integrity": "ok", "foreign_key_issues": 0}))


if __name__ == "__main__":
    main()
