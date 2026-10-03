"""Read-only real-corpus reconciliation and anonymous API/query-budget smoke."""
from collections import Counter
import io
import json
from time import perf_counter

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from atlas import models as m
from atlas.brain_controlled_publication import MANIFEST_SHA, canonical_counts, verify_receipt


class Command(BaseCommand):
    help = "Verify the pinned publication receipt, actual reviewed corpus and anonymous public Brain API without writes."

    def handle(self, *args, **options):
        datasets = list(m.ResearchDataset.objects.filter(ingestion_audit__publication_manifest_sha256=MANIFEST_SHA))
        if len(datasets) != 1:
            raise CommandError("Exactly one controlled publication receipt is required.")
        verify_receipt(datasets[0])
        host = next((value.lstrip(".") for value in settings.ALLOWED_HOSTS if value and value != "*"), "localhost")
        client = Client(HTTP_HOST=host)
        probes = []
        for label, path, params, budget in (
            ("list", "/api/brain-anatomy/", {}, 4),
            ("detail", "/api/brain-anatomy/ca1-field/", {}, 11),
            ("search", "/api/brain-anatomy/", {"q": "Locus coeruleus"}, 4),
            ("parent", "/api/brain-anatomy/", {"parent": "frontal-lobe"}, 5),
            ("kind_laterality", "/api/brain-anatomy/", {"kind": "subcortical_structure", "laterality": "left"}, 5),
            ("persian", "/api/brain-anatomy/", {"q": "آمیگدال"}, 4),
            ("persian_alias", "/api/brain-anatomy/", {"q": "کورپوس کالوزوم"}, 4),
            ("pagination", "/api/brain-anatomy/", {"page": 2}, 4)):
            start = perf_counter()
            with CaptureQueriesContext(connection) as queries:
                response = client.get(path, params, secure=True)
            elapsed = round((perf_counter() - start) * 1000, 2)
            if response.status_code != 200 or len(queries) > budget:
                raise CommandError(f"Real API probe failed: {label}; status={response.status_code}, queries={len(queries)}, budget={budget}")
            data = response.json()
            probes.append(dict(probe=label, status=200, queries=len(queries), budget=budget,
                milliseconds=elapsed, results=data.get("count", 1)))
        if client.get("/api/brain-anatomy/not-an-approved-entity/", secure=True).status_code != 404:
            raise CommandError("Missing entity is not 404.")
        output = io.StringIO()
        call_command("audit_brain_atlas", as_json=True, stdout=output)
        audit = json.loads(output.getvalue())
        if audit["errors"] or audit["review_debt"] or audit["staging_issues"]:
            raise CommandError("Brain publication audit is not clear.")
        sqlite_checks = None
        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA integrity_check")
                integrity = cursor.fetchall()
                cursor.execute("PRAGMA foreign_key_check")
                foreign_keys = cursor.fetchall()
            if integrity != [("ok",)] or foreign_keys:
                raise CommandError("SQLite integrity/foreign-key check failed.")
            sqlite_checks = dict(integrity_check="ok", foreign_key_violations=0)
        report = dict(counts=canonical_counts(), source_registry_count=m.SourceReference.objects.count(),
            anatomy_by_kind=dict(Counter(m.BrainAnatomicalEntity.objects.values_list("kind", flat=True))),
            anatomy_by_laterality=dict(Counter(m.BrainAnatomicalEntity.objects.values_list("laterality", flat=True))),
            reviewed_persian_names=m.BrainAnatomicalEntity.objects.exclude(name_fa="").filter(review_status="reviewed").count(),
            reviewed_persian_aliases=m.BrainAnatomicalAlias.objects.filter(language="fa", review_status="reviewed").count(),
            anatomy_review_states=dict(Counter(m.BrainAnatomicalEntity.objects.values_list("review_status", flat=True))),
            anatomy_activity=dict(Counter(str(v) for v in m.BrainAnatomicalEntity.objects.values_list("is_active", flat=True))),
            api=probes, missing_detail_status=404, audit=audit, sqlite=sqlite_checks, canonical_writes=0)
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
