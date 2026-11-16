"""W13 PostgreSQL 17 migration rehearsal in a disposable, localhost-only cluster.

No connection to the canonical Django database is ever opened. The cluster is
created under the OS temporary directory and is stopped in finally.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
BIN = Path(os.environ.get("CMS_QA_POSTGRES_BIN", r"C:\Program Files\PostgreSQL\17\bin"))
if os.name != "nt" or not PYTHON.is_file():
    raise SystemExit("This local PostgreSQL rehearsal requires the project's Windows venv")
for program in ("initdb.exe", "pg_ctl.exe", "createdb.exe"):
    if not (BIN / program).is_file():
        raise SystemExit(f"Disposable PostgreSQL binary unavailable: {program}")


def run(args, env, *, expect_success=True, timeout=180):
    pg_control = Path(str(args[0])).name.lower() == "pg_ctl.exe"
    proc = subprocess.run([str(arg) for arg in args], cwd=BACKEND, env=env,
                          stdout=subprocess.DEVNULL if pg_control else subprocess.PIPE,
                          stderr=subprocess.DEVNULL if pg_control else subprocess.PIPE,
                          text=True, errors="replace", timeout=timeout)
    if (proc.returncode == 0) != expect_success:
        raise RuntimeError("Unexpected PostgreSQL migration result "
                           + " ".join(map(str, args)) + "\n"
                           + ((proc.stdout or "") + (proc.stderr or ""))[-2200:])
    return proc


checks = []
with tempfile.TemporaryDirectory(prefix="atlas-w13-pg-migrate-") as directory:
    owned = Path(directory)
    assert owned.parent.resolve() == Path(tempfile.gettempdir()).resolve()
    assert owned.name.startswith("atlas-w13-pg-migrate-")
    data, log = owned / "cluster", owned / "cluster.log"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ)
    env.update({
        "DB_ENGINE": "postgres", "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": str(port), "POSTGRES_DB": "atlas_w13_upgrade_synthetic",
        "POSTGRES_USER": "w13_upgrade", "POSTGRES_PASSWORD": "synthetic-disposable-only",
        "SQLITE_PATH": str(owned / "unused.sqlite3"),
        "SQLITE_TEST_PATH": str(owned / "unused-test.sqlite3"),
        "PYTHONDONTWRITEBYTECODE": "1", "DEBUG": "1",
    })
    started = False
    try:
        print("W13_PG:init", flush=True)
        run([BIN / "initdb.exe", "-D", data, "-U", "w13_upgrade", "-A", "trust", "--no-instructions"], env)
        run([BIN / "pg_ctl.exe", "-D", data, "-l", log,
             "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"], env)
        started = True
        run([BIN / "createdb.exe", "-h", "127.0.0.1", "-p", str(port),
             "-U", "w13_upgrade", "atlas_w13_upgrade_synthetic"], env)
        run([PYTHON, "manage.py", "migrate", "atlas", "0059", "--noinput", "--verbosity=0"], env)
        import psycopg
        def connect():
            return psycopg.connect(
                host="127.0.0.1", port=port, dbname="atlas_w13_upgrade_synthetic",
                user="w13_upgrade", password="synthetic-disposable-only")
        digest = "a" * 64
        with connect() as db:
            db.execute(
                "INSERT INTO atlas_learningevidencerevision "
                "(kind,target_pk,sequence,content_digest,created_at,actor_id) "
                "VALUES (%s,%s,%s,%s,now(),NULL)",
                ("flashcard", 787001, 1, digest),
            )
        run([PYTHON, "manage.py", "migrate", "atlas", "0060", "--noinput", "--verbosity=0"], env)
        with connect() as db:
            result = db.execute(
                "SELECT content_digest,fingerprint_version,change_reason "
                "FROM atlas_learningevidencerevision WHERE target_pk=787001"
            ).fetchone()
        assert result == (digest, "claim-text-v1", ""), result
        checks.append("0059->0060 preserves explanation-only legacy digest unreviewed")
        with connect() as db:
            db.execute(
                "INSERT INTO atlas_learningevidencerevision "
                "(kind,target_pk,sequence,content_digest,fingerprint_version,"
                "change_reason,created_at,actor_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,now(),NULL)",
                ("flashcard", 787002, 1, "b" * 64, "claim-context-v2",
                 "Synthetic evidence recheck"),
            )
        refused = run([PYTHON, "manage.py", "migrate", "atlas", "0059",
                       "--noinput", "--verbosity=0"], env, expect_success=False)
        assert "Unsafe W13 rollback" in (refused.stdout + refused.stderr)
        with connect() as db:
            assert db.execute(
                "SELECT fingerprint_version FROM atlas_learningevidencerevision "
                "WHERE target_pk=787002").fetchone()[0] == "claim-context-v2"
            assert db.execute(
                "SELECT COUNT(*) FROM django_migrations WHERE app='atlas' "
                "AND name='0060_w13_claim_context_fingerprint'").fetchone()[0] == 1
        checks.append("Unsafe downgrade with v2 revision refused; all rows intact")
        fresh = run([PYTHON, "manage.py", "makemigrations", "--check",
                     "--dry-run"], env)
        checks.append("Migration state matches current models")
        print(json.dumps({"kind": "W13_POSTGRESQL_17_UPGRADE",
                          "status": "PASS", "canonical_database_opened": False,
                          "checks": checks, "exit_code": 0}), flush=True)
    finally:
        if started:
            stopped = subprocess.run([str(BIN / "pg_ctl.exe"), "-D", str(data),
                                      "-m", "immediate", "-w", "stop"], cwd=BACKEND,
                                     env=env, capture_output=True, text=True, timeout=60)
            print("W13_PG:stopped", stopped.returncode == 0, flush=True)
            if stopped.returncode != 0:
                raise RuntimeError("Disposable PostgreSQL cluster failed to stop")
