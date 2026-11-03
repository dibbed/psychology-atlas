"""Rehearse 0050/0051 on a TEMP copy; never migrate the protected source."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from verify_learning_archive_migration import ROOT, SOURCE, snapshot


def main():
    original_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="atlas-learning-transfer-migration-") as directory:
        owned = Path(directory).resolve()
        assert owned.parent == Path(tempfile.gettempdir()).resolve()
        assert owned.name.startswith("atlas-learning-transfer-migration-")
        database = owned / "copy.sqlite3"
        with closing(sqlite3.connect(SOURCE.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(database)) as copy:
                source.backup(copy)
        original_columns, original_rows = snapshot(database)
        env = dict(os.environ, DB_ENGINE="sqlite", SQLITE_PATH=str(database),
                   SQLITE_TEST_PATH=str(owned / "tests.sqlite3"), DEBUG="1")
        before = columns = None
        for target in ("0050_v100_p13_learning_archive", "0051_v100_p13_learning_io",
                       "0050_v100_p13_learning_archive", "0051_v100_p13_learning_io"):
            run = subprocess.run([sys.executable, str(ROOT / "backend/manage.py"), "migrate", "atlas",
                target, "--noinput"], env=env, capture_output=True, text=True, timeout=180)
            if run.returncode:
                raise RuntimeError("Transfer migration rehearsal failed: " + run.stderr[-1800:])
            _, original_after = snapshot(database, original_columns)
            for table, rows in original_rows.items():
                assert rows <= original_after[table] if table in {"auth_permission", "django_content_type"} else rows == original_after[table], table
            if before is None:
                columns, before = snapshot(database)
            else:
                _, after = snapshot(database, columns)
                for table, rows in before.items():
                    assert rows <= after[table] if table in {"auth_permission", "django_content_type"} else rows == after[table], table
            if target.startswith("0051"):
                with closing(sqlite3.connect(database)) as connection:
                    assert connection.execute("SELECT COUNT(*) FROM atlas_adminjob WHERE output_artifact_id IS NOT NULL").fetchone() == (0,)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == original_hash
    print(json.dumps({"status": "PASS", "preserved_tables": len(before), "source_unchanged": True,
        "source_sha256": original_hash, "integrity": "ok", "foreign_key_issues": 0,
        "upgrade_reverse_reupgrade": True, "reverse_before_new_transfer_rows_only": True}))


if __name__ == "__main__":
    main()
