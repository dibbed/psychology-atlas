"""Disposable v0059 -> v0060 claim-context migration and fail-closed rollback QA.

Uses ONLY two fresh temporary SQLite files. Never opens the operational database.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe" if os.name == "nt" else Path(sys.executable)
RESULT = {"kind": "W13_CLAIM_FINGERPRINT_SQLITE_MIGRATION",
          "canonical_database_opened": False, "checks": []}


def run(arguments, env, *, expect_success=True):
    call = subprocess.run([str(PYTHON), "manage.py", *arguments], cwd=BACKEND,
                          env=env, text=True, capture_output=True, timeout=240)
    if (call.returncode == 0) != expect_success:
        raise RuntimeError("Migration command unexpected status: "
                           + " ".join(arguments) + "\n"
                           + (call.stdout + call.stderr)[-1700:])
    return call


@contextmanager
def temp_sqlite(path):
    database = sqlite3.connect(path)
    try:
        yield database
        database.commit()
    finally:
        database.close()


def integrity(path):
    with temp_sqlite(path) as database:
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []


def stage_env(temporary):
    path = (Path(temporary) / "only-synthetic-test.sqlite3").resolve()
    assert path.parent.parent == Path(tempfile.gettempdir()).resolve()
    assert path.parent.name.startswith("atlas-w13-migrate-")
    assert not path.exists()
    env = dict(os.environ)
    env.update({"DB_ENGINE": "sqlite", "SQLITE_PATH": str(path),
                "SQLITE_TEST_PATH": str(path.parent / "unused-tests.sqlite3"),
                "PYTHONDONTWRITEBYTECODE": "1", "DEBUG": "1"})
    return path, env


with tempfile.TemporaryDirectory(prefix="atlas-w13-migrate-") as directory:
    path, env = stage_env(directory)
    run(["migrate", "atlas", "0059", "--noinput", "--verbosity=0"], env)
    digest = hashlib.sha256(b"synthetic-v1-evidence").hexdigest()
    with temp_sqlite(path) as database:
        database.execute(
            "INSERT INTO atlas_learningevidencerevision"
            "(kind,target_pk,sequence,content_digest,created_at,actor_id)"
            "VALUES(?,?,?,?,datetime('now'),NULL)",
            ("flashcard", 789001, 1, digest),
        )
    run(["migrate", "atlas", "0060", "--noinput", "--verbosity=0"], env)
    with temp_sqlite(path) as database:
        first = database.execute(
            "SELECT content_digest,fingerprint_version,change_reason "
            "FROM atlas_learningevidencerevision WHERE target_pk=789001"
        ).fetchone()
        assert first == (digest, "claim-text-v1", ""), first
    RESULT["checks"].append("0059->0060 retains immutable v1 digest and unreviewed legacy marker")
    integrity(path)
    run(["migrate", "atlas", "0059", "--noinput", "--verbosity=0"], env)
    with temp_sqlite(path) as database:
        assert database.execute(
            "SELECT content_digest FROM atlas_learningevidencerevision"
        ).fetchone()[0] == digest
    run(["migrate", "atlas", "0060", "--noinput", "--verbosity=0"], env)
    RESULT["checks"].append("Legacy-only rollback/reapply safely preserves old SHA")
    with temp_sqlite(path) as database:
        database.execute(
            "INSERT INTO atlas_learningevidencerevision"
            "(kind,target_pk,sequence,content_digest,fingerprint_version,"
            "change_reason,created_at,actor_id)"
            "VALUES(?,?,?,?,?,?,datetime('now'),NULL)",
            ("flashcard", 789002, 1, digest, "claim-context-v2",
             "Fictional source recheck"),
        )
    declined = run(["migrate", "atlas", "0059", "--noinput", "--verbosity=0"], env,
                   expect_success=False)
    assert "Unsafe W13 rollback" in (declined.stdout + declined.stderr)
    with temp_sqlite(path) as database:
        assert database.execute(
            "SELECT fingerprint_version FROM atlas_learningevidencerevision "
            "WHERE target_pk=789002"
        ).fetchone()[0] == "claim-context-v2"
        assert database.execute(
            "SELECT COUNT(*) FROM django_migrations WHERE app='atlas' "
            "AND name='0060_w13_claim_context_fingerprint'"
        ).fetchone()[0] == 1
    integrity(path)
    RESULT["checks"].append("Downgrade with v2 evidence rejected; schema and rows intact")

with tempfile.TemporaryDirectory(prefix="atlas-w13-migrate-") as directory:
    path, env = stage_env(directory)
    run(["migrate", "--noinput", "--verbosity=0"], env)
    run(["makemigrations", "--check", "--dry-run"], env)
    with temp_sqlite(path) as database:
        columns = {row[1] for row in database.execute(
            "PRAGMA table_info('atlas_learningevidencerevision')")}
        assert {"fingerprint_version", "change_reason"} <= columns
        assert database.execute(
            "SELECT COUNT(*) FROM atlas_learningevidencerevision").fetchone()[0] == 0
        indexes = database.execute(
            "PRAGMA index_list('atlas_learningevidencerevision')").fetchall()
        assert any(row[2] for row in indexes), indexes
    integrity(path)
    RESULT["checks"].append("Fresh current schema: migration drift none, FK/index/integrity OK")

RESULT["status"] = "PASS"
print(json.dumps(RESULT, ensure_ascii=False))
