"""Temporary, isolated Linux/PostgreSQL compilation experiment for v0.9.3."""
import json
import os
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.db import connection, transaction
from django.test.runner import DiscoverRunner
from rest_framework.test import APIClient
from atlas.tests_v092c_brain_publication import PublishedCorpusTests

runner = DiscoverRunner(verbosity=0, interactive=False)
runner.setup_test_environment()
started = perf_counter()
databases = runner.setup_databases()
print(json.dumps({"database_setup_s": perf_counter() - started}), flush=True)
try:
    started = perf_counter()
    preceding = runner.build_suite(["atlas.tests_v092c_brain_publication.ControlledPublicationFailureTests"])
    result = runner.run_suite(preceding)
    assert result.wasSuccessful()
    print(json.dumps({"preceding_tests_s": perf_counter() - started}), flush=True)
    # Reproduce the empty statistics observed while the real fixture is uncommitted.
    with connection.cursor() as cursor:
        for table in ("atlas_brainanatomicalentity", "atlas_brainhierarchylink", "atlas_sourcereference",
                      "atlas_brainanatomicalentitysource", "atlas_brainhierarchylinksource", "atlas_brainanatomicalalias"):
            cursor.execute("ANALYZE " + table)
    started = perf_counter()
    PublishedCorpusTests.setUpClass()
    print(json.dumps({"corpus_setup_s": perf_counter() - started}), flush=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version(), pg_jit_available()")
            print(json.dumps({"postgres": cursor.fetchone()}), flush=True)
            cursor.execute("SET LOCAL jit = off")
        for path in ("/api/brain-anatomy/", "/api/brain-anatomy/ca1-field/"):
            queries = []
            def capture(execute, sql, params, many, context):
                started = perf_counter()
                try:
                    return execute(sql, params, many, context)
                finally:
                    if sql.lstrip().upper().startswith("SELECT"):
                        queries.append((sql, params, perf_counter() - started))
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '20s'")
                    with connection.execute_wrapper(capture):
                        response = APIClient().get(path)
                    assert response.status_code == 200
            except Exception as error:
                print(json.dumps({"path": path, "api_error": type(error).__name__}), flush=True)
            print(json.dumps({"path": path, "jit_off_query_s": [q[2] for q in queries]}), flush=True)
            plans = []
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL jit = on")
                for sql, params, _ in queries:
                    cursor.execute("EXPLAIN (FORMAT JSON) " + sql, params)
                    plan = cursor.fetchone()[0][0]
                    plans.append((plan["Plan"]["Total Cost"], sql, params, plan.get("JIT")))
                cursor.execute("SET LOCAL jit = off")
            cost, sql, params, jit = max(plans, key=lambda p: p[0])
            print(json.dumps({"path": path, "max_cost": cost, "jit_plan": jit}), flush=True)
            for mode in ("original", "materialized"):
                started = perf_counter()
                try:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute("SET LOCAL statement_timeout = '30s'")
                        cursor.execute("SET LOCAL jit = off")
                        candidate = sql if mode == "original" else sql.replace("checked_links(id) AS (", "checked_links(id) AS MATERIALIZED (")
                        cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + candidate, params)
                        plan = cursor.fetchone()[0][0]
                        print(json.dumps({"path": path, "variant": mode, "wall_s": perf_counter() - started,
                            "planning_ms": plan["Planning Time"], "execution_ms": plan["Execution Time"],
                            "actual_rows": plan["Plan"]["Actual Rows"], "jit_detail": plan.get("JIT")}), flush=True)
                except Exception as error:
                    print(json.dumps({"path": path, "variant": mode, "wall_s": perf_counter() - started,
                        "error": type(error).__name__, "sqlstate": getattr(error.__cause__, "sqlstate", None)}), flush=True)
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL jit = off")
    finally:
        PublishedCorpusTests.tearDownClass()
finally:
    started = perf_counter()
    runner.teardown_databases(databases)
    print(json.dumps({"database_teardown_s": perf_counter() - started}), flush=True)
    runner.teardown_test_environment()
