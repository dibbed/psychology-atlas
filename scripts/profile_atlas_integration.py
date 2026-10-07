"""Bounded read-only HTTP profiling on the existing reviewed atlas corpus."""
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
from django.core.cache import cache
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext


def profile(runs=5):
    if not 1 <= runs <= 10:
        raise ValueError("Use between 1 and 10 warm samples.")
    result = dict(vendor=connection.vendor, warm_samples=runs,
                  cold_definition="Atlas graph cache cleared; database and OS caches are not flushed.",
                  corpus={}, measurements={})
    endpoints = [
        ("graph", "/api/concept-map/", {}),
        ("brain_graph", "/api/concept-map/", {"node_type": "brain_anatomy"}),
        ("assessment_graph", "/api/concept-map/", {"node_type": "assessment"}),
        ("structural_graph", "/api/concept-map/", {"relation": "brain_part_of"}),
        ("search_assessment_acronym", "/api/search/", {"q": "PHQ-9"}),
        ("search_persian", "/api/search/", {"q": "پرسش‌نامه"}),
        ("search_brain", "/api/search/", {"q": "brain"}),
        ("search_legacy", "/api/search/", {"q": "corpus"}),
        ("brain_contribution", "/api/brain-anatomy/", {"q": "brain"}),
        ("assessment_contribution", "/api/assessments/", {"q": "PHQ-9"}),
    ]
    with override_settings(ALLOWED_HOSTS=["testserver"], REST_FRAMEWORK={"DEFAULT_THROTTLE_CLASSES": []}):
        client = Client()
        for name, url, params in endpoints:
            cache.delete("atlas_graph")
            samples = []
            for _ in range(runs + 1):
                start = perf_counter()
                with CaptureQueriesContext(connection) as captured:
                    response = client.get(url, params)
                elapsed = (perf_counter() - start) * 1000
                if response.status_code != 200:
                    raise RuntimeError(f"{name}: HTTP {response.status_code}")
                writes = [q["sql"] for q in captured.captured_queries
                          if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"))]
                if writes:
                    raise RuntimeError("Profiler observed a database write.")
                data = response.json()
                counts = ({key: data["meta"][key] for key in ("node_count", "edge_count", "node_types")}
                          if "meta" in data else {key: len(value) for key, value in data.items() if isinstance(value, list)})
                samples.append(dict(query_count=len(captured), ms=round(elapsed, 3),
                                    payload_bytes=len(response.content), result_counts=counts))
            result["measurements"][name] = dict(cold=samples[0], warm=samples[1:],
                warm_median_ms=round(statistics.median(sample["ms"] for sample in samples[1:]), 3))
            if name == "graph":
                result["corpus"] = data["meta"]
                hierarchy = next((edge for edge in data["edges"] if edge["kind"] == "brain_part_of"), None)
                if hierarchy:
                    path = {"from": hierarchy["target"], "to": hierarchy["source"]}
                    endpoints.extend([
                        ("path_without_structural", "/api/concept-map/path/", path),
                        ("path_with_structural", "/api/concept-map/path/", dict(path, include_structural="1")),
                    ])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--runs", type=int, choices=range(1, 11), default=5)
    args = parser.parse_args()
    result = profile(args.runs)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(vendor=result["vendor"], corpus={
        key: result["corpus"][key] for key in ("node_count", "edge_count", "node_types")
    }, measurements={
        name: dict(cold_queries=value["cold"]["query_count"], warm_queries=[s["query_count"] for s in value["warm"]],
                   cold_ms=value["cold"]["ms"], warm_median_ms=value["warm_median_ms"],
                   payload_bytes=value["cold"]["payload_bytes"])
        for name, value in result["measurements"].items()
    }), ensure_ascii=False))
