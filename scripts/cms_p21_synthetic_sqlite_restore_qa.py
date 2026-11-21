"""P21 synthetic SQLite migration + backup/restore smoke, never production data.

Runs exclusively under a new TemporaryDirectory owned by this script.
This is NOT evidence of a production backup adapter, tested RPO/RTO or
a rehearsal on a representative copy of the canonical database.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from time import monotonic


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
CANONICAL = (BACKEND / "data" / "psychology_atlas.sqlite3").resolve()


def inspect(path):
    # Read-only SQLite URI guarantees this verifier cannot change any checked DB.
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchall()
        fk = db.execute("PRAGMA foreign_key_check").fetchall()
        tables = sorted(row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        counts, row_digests = {}, {}
        for table in tables:
            table_name = '"' + table.replace('"', '""') + '"'
            rows = [repr(tuple(row)) for row in db.execute("SELECT * FROM " + table_name)]
            counts[table] = len(rows)
            row_digests[table] = hashlib.sha256(
                "\n".join(sorted(rows)).encode("utf-8")).hexdigest()
        return {
            "integrity": integrity == [("ok",)],
            "foreign_keys_ok": not fk,
            "counts": counts,
            "row_digests": row_digests,
            "usernames": [row[0] for row in db.execute(
                "SELECT username FROM auth_user ORDER BY username")],
        }


def copy_online(source, destination):
    start = monotonic()
    # sqlite3.Connection context managers do not close file handles on Windows.
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst, pages=64)
    return round(monotonic() - start, 3)


def main():
    if os.name != "nt":
        raise SystemExit("This local acceptance script is for the existing Windows venv.")
    start = monotonic()
    with tempfile.TemporaryDirectory(prefix="atlas-p21-synthetic-restore-") as directory:
        owned = Path(directory).resolve()
        if not (owned.name.startswith("atlas-p21-synthetic-restore-")
                and owned.parent == Path(tempfile.gettempdir()).resolve()):
            raise RuntimeError("Synthetic workspace escaped its temporary root")
        original, backup, restored = (
            owned / "synthetic-origin.sqlite3", owned / "synthetic-backup.sqlite3",
            owned / "synthetic-restored.sqlite3")
        if not all(p.parent == owned and p.resolve() != CANONICAL for p in (original, backup, restored)):
            raise RuntimeError("Refusing to touch a non-temporary or canonical database path")
        os.environ["DB_ENGINE"] = "sqlite"
        os.environ["DEBUG"] = "1"
        os.environ["SQLITE_PATH"] = str(original)
        os.environ["SQLITE_TEST_PATH"] = str(owned / "synthetic-tests.sqlite3")
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
        sys.path.insert(0, str(BACKEND))

        import django
        django.setup()
        from django.conf import settings
        from django.contrib.auth.models import User
        from django.core.management import call_command
        from django.db import connection
        from atlas.cms_models import RolePolicy

        if (Path(settings.DATABASES["default"]["NAME"]).resolve() != original
                or connection.vendor != "sqlite"):
            raise RuntimeError("Refusing non-disposable Django database configuration")
        call_command("migrate", interactive=False, verbosity=0)
        RolePolicy.objects.get_or_create(pk=1)
        User.objects.create_user(username="p21-disposable-example", password="not-a-real-credential")
        connection.close()
        before = inspect(original)
        if not (before["integrity"] and before["foreign_keys_ok"]
                and before["counts"]["auth_user"] == 1
                and before["counts"]["django_migrations"] > 30
                and before["usernames"] == ["p21-disposable-example"]):
            raise RuntimeError("Fresh synthetic migrated database failed acceptance")

        backup_s = copy_online(original, backup)
        snapshot = inspect(backup)
        if snapshot != before:
            raise RuntimeError("Synthetic online backup is not row-equivalent")
        restore_s = copy_online(backup, restored)
        after = inspect(restored)
        if after != before:
            raise RuntimeError("Synthetic restored database is not row-equivalent")

        report = {
            "status": "PASS", "scope": "synthetic_fresh_sqlite_only",
            "canonical_database_opened": False, "original_generated_under_temp": True,
            "backup_and_restore_automated_only_in_temp": True,
            "fresh_install_migrations": before["counts"]["django_migrations"],
            "tables_checked": len(before["counts"]),
            "rows_compared_total": sum(before["counts"].values()),
            "sqlite_integrity_ok": after["integrity"],
            "foreign_keys_ok": after["foreign_keys_ok"],
            "counts_match_before_after": before["counts"] == after["counts"],
            "logical_row_digests_match": before["row_digests"] == after["row_digests"],
            "synthetic_user_still_present": after["usernames"] == before["usernames"],
            "backup_copy_seconds_local": backup_s,
            "restore_copy_seconds_local": restore_s,
            "total_seconds_local": round(monotonic() - start, 3),
            "real_backup_adapter_verified": False,
            "representative_production_restore_proven": False,
            "rpo_rto_validated": False,
            "production_release_gate_passed": False,
        }
        print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
