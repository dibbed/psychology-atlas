"""Preserve the real legacy corpus through disposable SQLite migration paths."""
import argparse
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


def snapshot(database):
    with closing(sqlite3.connect(database)) as connection:
        tables = [name for name, in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'django_migrations' ORDER BY name")]
        snapshots = {}
        for table in tables:
            rows = sorted(connection.execute('SELECT * FROM "' + table.replace('"', '""') + '"').fetchall(), key=repr)
            snapshots[table] = dict(rows=len(rows), sha256=hashlib.sha256(repr(rows).encode()).hexdigest(), values=rows)
        return snapshots


def preserved(before, after):
    # Django post_migrate adds content-type/permission metadata; every existing row must remain byte-equivalent.
    for table, rows in before.items():
        if table in {"django_content_type", "auth_permission"}:
            if not set(rows["values"]).issubset(set(after[table]["values"])):
                return False
        elif rows != after[table]:
            return False
    return True


def migrate(database, target=None):
    env = dict(os.environ, DB_ENGINE="sqlite", SQLITE_PATH=str(database), DEBUG="1")
    command = [sys.executable, str(ROOT / "backend/manage.py"), "migrate"]
    if target:
        command += ["atlas", target]
    run = subprocess.run(command + ["--noinput"], env=env, capture_output=True, text=True, timeout=180)
    if run.returncode:
        raise RuntimeError(run.stderr[-3000:])


def verify(original):
    result = {}
    with tempfile.TemporaryDirectory(prefix="assessment-real-migration-") as temporary:
        for name,target in (("current_main", "0036_v092_brain_identifier_review"), ("released_v084", "0032_v084_study_sessions")):
            database = Path(temporary) / (name + ".sqlite3")
            with closing(sqlite3.connect(Path(original).resolve().as_uri() + "?mode=ro", uri=True)) as source, closing(sqlite3.connect(database)) as copy:
                source.backup(copy)
            migrate(database, target)
            before = snapshot(database)
            migrate(database)
            after = snapshot(database)
            assert preserved(before, after), name
            with closing(sqlite3.connect(database)) as connection:
                assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            migrate(database, target)
            reversed_snapshot = snapshot(database)
            assert set(reversed_snapshot) == set(before) and preserved(before, reversed_snapshot), name + " reverse"
            result[name] = dict(legacy_tables=len(before), legacy_rows=sum(row["rows"] for row in before.values()),
                                upgrade="PASS", reverse="PASS", integrity="ok", foreign_key_issues=0)
        fresh = Path(temporary) / "fresh.sqlite3"
        migrate(fresh)
        with closing(sqlite3.connect(fresh)) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        result["zero_to_latest"] = dict(status="PASS", integrity="ok", foreign_key_issues=0)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("output")
    args = parser.parse_args()
    result = verify(args.database)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
