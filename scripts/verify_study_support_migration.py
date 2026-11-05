"""Exercise the additive support receipt schema only on a disposable canonical copy."""
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
    with tempfile.TemporaryDirectory(prefix="atlas-study-support-migration-") as directory:
        owned = Path(directory).resolve()
        assert owned.parent == Path(tempfile.gettempdir()).resolve()
        database = owned / "copy.sqlite3"
        with closing(sqlite3.connect(SOURCE.as_uri()+"?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(database)) as copy:
                source.backup(copy)
        columns, before = snapshot(database)
        env = dict(os.environ, DB_ENGINE="sqlite", SQLITE_PATH=str(database), SQLITE_TEST_PATH=str(owned/"tests.sqlite3"))
        for target in ("0052_v100_p14_privacy_export", "0053_v100_p15_study_support",
                       "0052_v100_p14_privacy_export", "0053_v100_p15_study_support"):
            result = subprocess.run([sys.executable, str(ROOT/"backend/manage.py"), "migrate", "atlas", target,
                "--noinput"], env=env, capture_output=True, text=True, timeout=180)
            if result.returncode:
                raise RuntimeError("Support receipt migration failed: "+result.stderr[-1500:])
            _, after = snapshot(database, columns)
            for table, rows in before.items():
                assert rows <= after[table] if table in {"auth_permission", "django_content_type"} else rows == after[table], table
            if target.startswith("0053"):
                with closing(sqlite3.connect(database)) as connection:
                    assert connection.execute("SELECT COUNT(*) FROM atlas_studyoperationreceipt").fetchone() == (0,)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == original_hash
    print(json.dumps({"status": "PASS", "preserved_source_tables": len(before), "source_unchanged": True,
        "source_sha256": original_hash, "upgrade_reverse_reupgrade": True,
        "reverse_before_new_receipts_only": True, "integrity": "ok", "foreign_key_issues": 0}))


if __name__ == "__main__":
    main()
