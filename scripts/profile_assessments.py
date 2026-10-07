"""Measure real registry requests and PostgreSQL execution plans without writes."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from atlas.assessment_views import loaded_instruments, public_sets


def profile():
    endpoints = dict(list="/api/assessments/", detail="/api/assessments/patient-health-questionnaire/",
        search="/api/assessments/?q=depression", persian_search="/api/assessments/?q=پرسش‌نامه", acronym_search="/api/assessments/?q=PHQ-9",
        language_filter="/api/assessments/?language=fa", construct_filter="/api/assessments/?construct=depression",
        access_filter="/api/assessments/?access=public_access", language_license_filter="/api/assessments/?language=fa&license=unknown")
    result = dict(vendor=connection.vendor, measurements={})
    plan_queries = {}
    with override_settings(ALLOWED_HOSTS=["testserver"], REST_FRAMEWORK={"DEFAULT_THROTTLE_CLASSES": []}):
        client = Client()
        for name,url in endpoints.items():
            elapsed, queries = [], []
            for _ in range(5):
                start = perf_counter()
                with CaptureQueriesContext(connection) as captured:
                    response = client.get(url)
                if response.status_code != 200:
                    raise RuntimeError(f"{name}: HTTP {response.status_code}: {response.content[:400]!r}")
                elapsed.append((perf_counter() - start) * 1000)
                queries.append(len(captured))
            result["measurements"][name] = dict(query_counts=queries, median_ms=round(statistics.median(elapsed), 3),
                result_count=response.json().get("count"), payload_bytes=len(response.content))
            if name in {"list", "detail", "language_license_filter"}:
                plan_queries[name] = list(captured.captured_queries)
        if connection.vendor == "postgresql":
            sql, params = loaded_instruments(public_sets(), detail=True).filter(slug="patient-health-questionnaire").query.sql_with_params()
            with connection.cursor() as cursor:
                cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
                result["detail_main_query_plan"] = cursor.fetchone()[0]
                for name, queries in plan_queries.items():
                    result[name + "_query_plans"] = []
                    for query in queries:
                        if query["sql"].lstrip().upper().startswith("SELECT"):
                            cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query["sql"])
                            result[name + "_query_plans"].append(cursor.fetchone()[0])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    args = parser.parse_args()
    result = profile()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key,value in result.items() if key in {"vendor", "measurements"}}, ensure_ascii=False))
