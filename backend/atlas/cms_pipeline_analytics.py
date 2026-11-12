"""P19 owner-only analytical denominators from actual CMS rows.

Recorded statuses are not evidence of scientific approval, rights clearance,
public exposure, or production readiness. No identifiers or private payloads.
"""
from collections import defaultdict
import csv
import re

from django.http import HttpResponse
from django.db.models import Count, F
from django.utils import timezone
from rest_framework.response import Response

from .cms_content import REGISTRY
from .cms_content_models import ContentRevision, ContentState
from .cms_domains import domain_for
from .cms_governance_models import GovernanceDecision, GovernanceRecord
from .cms_job_models import AdminJob
from .cms_policy import CMSFailure, policy_lock, require
from .cms_review_models import ReviewDecision, ReviewTask
from .cms_source_models import SourceState
from .cms_views import AdminAPIView
from .models import SourceReference


def _statuses(model, field, choices):
    result = {name: 0 for name in choices}
    queryset = model.objects.all() if hasattr(model, "objects") else model
    for row in queryset.values(field).annotate(total=Count("pk")):
        name = row[field]
        result[name if name in result else "other"] = result.get(
            name if name in result else "other", 0) + row["total"]
    return result


def _content_counts():
    by_domain = defaultdict(lambda: {"states": 0, "with_current_revision": 0})
    revision_status = {name: 0 for name in ContentRevision.Status.values}
    publication = {name: 0 for name in ContentState.Publication.values}
    total = current_count = 0
    for row in ContentState.objects.values(
            "kind", "publication", "current_revision__status"
    ).annotate(total=Count("pk")):
        count = row["total"]
        total += count
        domain = domain_for(row["kind"]) if row["kind"] in REGISTRY else "unmapped"
        by_domain[domain]["states"] += count
        recorded_marker = row["publication"]
        publication[recorded_marker if recorded_marker in publication else "other"] = (
            publication.get(recorded_marker if recorded_marker in publication else "other", 0) + count
        )
        status = row["current_revision__status"]
        if status is not None:
            current_count += count
            by_domain[domain]["with_current_revision"] += count
            revision_status[status if status in revision_status else "other"] = (
                revision_status.get(status if status in revision_status else "other", 0) + count
            )
    pointer_mismatch = ContentState.objects.filter(current_revision__isnull=False).exclude(
        current_revision__state_id=F("pk")).count()
    return {
        "states_total": total,
        "states_with_current_revision": current_count,
        "states_without_current_revision": total - current_count,
        "revisions_total": ContentRevision.objects.count(),
        "current_revision_statuses": revision_status,
        "recorded_publication_markers": publication,
        "pointer_state_mismatches": pointer_mismatch,
        "by_domain": dict(sorted(by_domain.items())),
        "denominator": "all_content_state_rows_including_unpublished_and_legacy",
        "current_revision_denominator": "states_with_current_revision_only",
        "revision_count_denominator": "all_retained_content_revision_rows",
        "publication_markers_are_authorization": False,
    }


def _governance_counts():
    return {
        kind: {
            "total": GovernanceRecord.objects.filter(kind=kind).count(),
            "by_status": _statuses(
                GovernanceRecord.objects.filter(kind=kind), "status",
                ("submitted", "in_review", "approved", "rejected", "revoked"),
            ),
            "decisions_total": GovernanceDecision.objects.filter(record__kind=kind).count(),
            "status_not_verified_clearance": True,
        }
        for kind in ("rights", "terminology")
    }


class PipelineAnalyticsView(AdminAPIView):
    capability = "cms_owner"

    def get(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_owner")
            return Response({
                "scope": "owner_recorded_pipeline_counts_only",
                "measured_at": timezone.now().isoformat(),
                "content": _content_counts(),
                "reviews": {
                    "tasks_total": ReviewTask.objects.count(),
                    "tasks_by_status": _statuses(
                        ReviewTask, "status", ("queued", "assigned", "approved", "rejected", "cancelled")),
                    "decisions_total": ReviewDecision.objects.count(),
                    "task_status_not_verified_approval": True,
                },
                "governance": _governance_counts(),
                "jobs": {
                    "total": AdminJob.objects.count(),
                    "by_status": _statuses(AdminJob, "status",
                        ("queued", "running", "succeeded", "failed", "cancelled", "reconciling")),
                },
                "sources": {
                    "canonical_references_total": SourceReference.objects.count(),
                    "versioned_source_states_total": SourceState.objects.count(),
                    "archived_states_total": SourceState.objects.filter(archived=True).count(),
                    "deleted_states_total": SourceState.objects.filter(deleted=True).count(),
                    "denominator": "references_and_state_rows_are_distinct_populations",
                },
                "publication_authorized": False,
                "scientific_rights_attested": False,
                "complete_release_readiness_proven": False,
                "notice": "RECORDED_COUNTS_ONLY_NOT_REVIEW_OR_RIGHTS_VERIFICATION_NO_PUBLIC_ANALYTICS",
            })

# Export only the already-authorized aggregate response. There must never be a
# separate field-lookup or arbitrary exporter that could reach private models.
_CSV_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


def _safe_csv_key(value):
    # Status and domain names must be code-owned tokens, not spreadsheet
    # formulas or user-provided labels that may start with =, +, -, or @.
    return value if type(value) is str and _CSV_KEY.fullmatch(value) else "other"


def _aggregate_csv(report):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cms-pipeline-recorded-counts.csv"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    writer = csv.writer(response, lineterminator="\r\n")
    writer.writerow(("section", "metric", "category", "value", "denominator"))

    def add(section, metric, value, denominator, category=""):
        if type(value) is bool:
            value = "true" if value else "false"
        elif type(value) is not int or value < 0:
            # Never let arbitrary report values become a CSV export surface.
            raise ValueError("Invalid count for aggregate export")
        writer.writerow((section, metric, _safe_csv_key(category) if category else "",
                         value, denominator))

    content = report["content"]
    for name in ("states_total", "states_with_current_revision",
                 "states_without_current_revision", "revisions_total",
                 "pointer_state_mismatches"):
        denominator = ("all_retained_content_revision_rows" if name == "revisions_total"
                       else "all_content_state_rows")
        add("content", name, content[name], denominator)
    for domain, counts in sorted(content["by_domain"].items()):
        add("content_by_domain", "states", counts["states"], "all_content_state_rows", domain)
        add("content_by_domain", "with_current_revision", counts["with_current_revision"],
            "all_content_state_rows", domain)
    for status, count in sorted(content["current_revision_statuses"].items()):
        add("current_revision_status", "status", count,
            "content_states_with_current_revision_only", status)
    for status, count in sorted(content["recorded_publication_markers"].items()):
        add("publication_marker", "status", count, "all_content_state_rows", status)

    reviews = report["reviews"]
    add("reviews", "tasks_total", reviews["tasks_total"], "all_review_task_rows")
    add("reviews", "decisions_total", reviews["decisions_total"], "all_review_decision_rows")
    for status, count in sorted(reviews["tasks_by_status"].items()):
        add("review_task_status", "status", count, "all_review_task_rows", status)

    for kind, stats in sorted(report["governance"].items()):
        add("governance", "records_total", stats["total"], "all_governance_records_of_kind", kind)
        add("governance", "decisions_total", stats["decisions_total"],
            "all_governance_decisions_of_kind", kind)
        for status, count in sorted(stats["by_status"].items()):
            add("governance_status", "status", count, "all_governance_records_of_kind",
                kind + "_" + _safe_csv_key(status))

    jobs = report["jobs"]
    add("jobs", "total", jobs["total"], "all_admin_jobs")
    for status, count in sorted(jobs["by_status"].items()):
        add("job_status", "status", count, "all_admin_jobs", status)
    sources = report["sources"]
    for name in ("canonical_references_total", "versioned_source_states_total",
                 "archived_states_total", "deleted_states_total"):
        add("sources", name, sources[name],
            "all_source_reference_rows" if name == "canonical_references_total"
            else "all_versioned_source_state_rows")
    # Explicitly distinguish the absence of clearance from recorded approved
    # statuses; no individual person, rights artifact or editorial text.
    for name in ("publication_authorized", "scientific_rights_attested",
                 "complete_release_readiness_proven"):
        add("safety", name, report[name], "not_a_publication_authorization")
    writer.writerow(("report", "measured_at", "", report["measured_at"],
                     "best_effort_multiple_queries_not_atomic_snapshot"))
    return response


class PipelineAnalyticsCSVExportView(PipelineAnalyticsView):
    """Owner-only GET; inherit the exact same live policy and count computation."""

    def get(self, request):
        # The parent checks closed query shape and live owner policy. A single
        # report object powers both the JSON and CSV presentations.
        report = super().get(request).data
        return _aggregate_csv(report)
