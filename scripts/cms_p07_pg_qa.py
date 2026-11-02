"""Isolated Windows PostgreSQL regression harness. Never target an existing database."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
BIN = Path(os.environ.get("CMS_QA_POSTGRES_BIN", r"C:\Program Files\PostgreSQL\17\bin"))
if os.name != "nt" or not PYTHON.is_file():
    raise SystemExit("This optional local PG harness is for the project's Windows venv only")
for executable in ("initdb.exe", "pg_ctl.exe", "createdb.exe"):
    if not (BIN / executable).is_file():
        raise SystemExit(f"Disposable PostgreSQL binary unavailable: {executable}")
TESTS = tuple(sys.argv[1:]) or (
    "atlas.tests_v100_p07_domains",
    "atlas.tests_v100_p07_content",
    "atlas.tests_v100_p07_integration",
    "atlas.tests_v100_p08_therapy",
    "atlas.tests_v100_p09_history",
    "atlas.tests_v100_p10_brain",
    "atlas.tests_v100_p11_assessment",
    "atlas.tests_v100_p02.RevisionConcurrencyTests",
    "atlas.tests_v100_p04.ReviewConcurrencyTests",
)
if any(not label.startswith("atlas.tests") or not all(part.isidentifier() for part in label.split(".")) for label in TESTS):
    raise SystemExit("Pass only dotted atlas.tests module/class/method labels")
result = {"kind": "CMS_DISPOSABLE_POSTGRESQL", "tests": list(TESTS),
          "database": "fresh temporary cluster", "canonical_database_opened": False}
with tempfile.TemporaryDirectory(prefix="atlas-p07-pg-") as directory:
    owned = Path(directory)
    assert owned.name.startswith("atlas-p07-pg-") and owned.parent.resolve() == Path(tempfile.gettempdir()).resolve()
    data = owned / "pgdata"
    log = owned / "postgres.log"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update({"DB_ENGINE": "postgres", "POSTGRES_HOST": "127.0.0.1",
                "POSTGRES_PORT": str(port), "POSTGRES_DB": "atlas_p07_disposable",
                "POSTGRES_USER": "p07_disposable", "POSTGRES_PASSWORD": "disposable-local-only",
                "DEBUG": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
    def run(args, *, timeout=150, env_override=None):
        # pg_ctl spawns a server that inherits pipes on Windows. Capturing pg_ctl
        # stdout can hang communicate() after pg_ctl exits until the server stops.
        pg_ctl = Path(str(args[0])).name.lower() == "pg_ctl.exe"
        proc = subprocess.run([str(a) for a in args], cwd=BACKEND, env=env_override or env,
                              stdout=subprocess.DEVNULL if pg_ctl else subprocess.PIPE,
                              stderr=subprocess.DEVNULL if pg_ctl else subprocess.PIPE,
                              text=True, errors="replace", timeout=timeout)
        if proc.returncode:
            print("COMMAND_FAIL", Path(str(args[0])).name, "exit", proc.returncode, flush=True)
            print(((proc.stdout or "") + "\n" + (proc.stderr or ""))[-7500:], flush=True)
            raise RuntimeError("Disposable PG command failed")
        return proc
    started = False
    try:
        print("P07_PG_STEP:initdb", flush=True)
        run([BIN / "initdb.exe", "-D", data, "-U", "p07_disposable", "-A", "trust", "--no-instructions"], timeout=120)
        print("P07_PG_STEP:start", flush=True)
        run([BIN / "pg_ctl.exe", "-D", data, "-l", log, "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"], timeout=90)
        started = True
        run([BIN / "createdb.exe", "-h", "127.0.0.1", "-p", str(port), "-U", "p07_disposable", "atlas_p07_disposable"], timeout=30)
        print("P07_PG_STEP:tests", flush=True)
        tests = run([PYTHON, "manage.py", "test", *TESTS, "--noinput", "--verbosity=1"], timeout=1200)
        result.update({"status": "PASS", "port_was_localhost_only": True,
                       "test_stdout_tail": tests.stdout[-500:], "test_stderr_tail": tests.stderr[-850:]})
        print(json.dumps(result), flush=True)
    finally:
        if started:
            stopped = subprocess.run([str(BIN / "pg_ctl.exe"), "-D", str(data),
                                      "-m", "immediate", "-w", "stop"],
                                     cwd=BACKEND, env=env, capture_output=True, text=True, timeout=45)
            print("P07_PG_STEP:stopped", stopped.returncode == 0, flush=True)
