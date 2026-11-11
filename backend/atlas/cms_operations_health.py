"""P18 owner-only conservative health reader. No shell, secrets or backup writes."""
from collections import defaultdict

from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Count, F, Max, Min, Sum
from django.utils import timezone
from rest_framework.response import Response

from .cms_case_publication_models import CasePublicationPlan, CasePublicationReceipt
from .cms_job_models import AdminArtifact, AdminJob
from .cms_source_models import SourceHistory, SourcePlan, SourcePlanReceipt, SourceSuccessor
from .cms_policy import CMSFailure, policy_lock, require
from .cms_views import AdminAPIView


_STATES = ("queued", "running", "succeeded", "failed", "cancelled", "reconciling")
_SOURCE_RESULT_SCAN_LIMIT = 200
_SOURCE_RESULT_ID_LIMIT = 64


def _receipt_ids(value):
    # Source Apply touches at most 51 source histories and 50 successor edges.
    # Reject malformed/oversized/duplicate IDs instead of trusting receipt JSON.
    if (type(value) is not list or len(value) > _SOURCE_RESULT_ID_LIMIT
            or any(type(item) is not int or item <= 0 for item in value)
            or len(set(value)) != len(value)):
        return None
    return set(value)


def _sample_source_result_drift():
    # One bounded snapshot of stored receipt results; no private IDs exposed.
    rows = list(SourcePlanReceipt.objects.order_by("-created_at", "-pk").values(
        "plan_id", "result")[:_SOURCE_RESULT_SCAN_LIMIT + 1])
    complete = len(rows) <= _SOURCE_RESULT_SCAN_LIMIT
    rows = rows[:_SOURCE_RESULT_SCAN_LIMIT]
    ids = [row["plan_id"] for row in rows]
    histories, successors = defaultdict(set), defaultdict(set)
    for plan_id, pk in SourceHistory.objects.filter(plan_id__in=ids).values_list("plan_id", "pk"):
        histories[plan_id].add(pk)
    for plan_id, pk in SourceSuccessor.objects.filter(plan_id__in=ids).values_list("plan_id", "pk"):
        successors[plan_id].add(pk)
    history_mismatches = successor_mismatches = 0
    for row in rows:
        result = row["result"] if type(row["result"]) is dict else {}
        history_mismatches += _receipt_ids(result.get("history_ids")) != histories[row["plan_id"]]
        successor_mismatches += _receipt_ids(result.get("successor_ids")) != successors[row["plan_id"]]
    return {
        "sampled_receipts": len(rows),
        "sample_complete": complete,
        "source_receipt_result_history_mismatches": history_mismatches,
        "source_receipt_result_successor_mismatches": successor_mismatches,
    }


class OperationsHealthView(AdminAPIView):
    capability = "cms_owner"

    def get(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_owner")
            now = timezone.now()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone()[0] != 1:
                    raise CMSFailure("DATABASE_HEALTH_FAILED", 503)
            migrations = MigrationRecorder.Migration.objects.filter(app="atlas")
            latest = migrations.order_by("-applied", "-pk").values("name", "applied").first()
            jobs = dict(AdminJob.objects.values_list("status").annotate(total=Count("pk")))
            heartbeat = AdminJob.objects.aggregate(latest=Max("heartbeat_at"))["latest"]
            oldest = AdminJob.objects.filter(status="queued").aggregate(oldest=Min("created_at"))["oldest"]
            artifacts = AdminArtifact.objects.filter(purged_at__isnull=True)
            bytes_total = artifacts.aggregate(total=Sum("size"))["total"] or 0
            # Structural consistency checks only: neither source rights nor
            # canonical public selectors can be certified by receipt counts.
            applied = CasePublicationPlan.objects.filter(status="applied")
            withdrawn = CasePublicationPlan.objects.filter(status="withdrawn")
            missing_apply = applied.exclude(receipts__event_type="applied").count()
            missing_withdraw = withdrawn.exclude(receipts__event_type="withdrawn").count()
            bad_digests = CasePublicationReceipt.objects.exclude(
                manifest_digest=F("plan__manifest_digest")).count()
            receipt_status = {
                "scope": "case_revision_structural_receipts_only",
                "case_plans_total": CasePublicationPlan.objects.count(),
                "case_plans_applied": applied.count(),
                "case_plans_withdrawn": withdrawn.count(),
                "case_receipts_total": CasePublicationReceipt.objects.count(),
                "case_plans_missing_applied_receipt": missing_apply,
                "case_plans_missing_withdrawn_receipt": missing_withdraw,
                "case_receipt_digest_mismatches": bad_digests,
                "total_observed_mismatches": missing_apply + missing_withdraw + bad_digests,
                "full_publication_integrity_proven": False,
                "repair_available": False,
                "notice": "STRUCTURAL_COUNTS_ONLY_NOT_LIVE_SOURCE_RIGHTS_OR_PUBLIC_ELIGIBILITY",
            }
            # A SourcePlan without receipt is normally an unapplied preview,
            # not evidence of a failed apply. Only contradictory persisted
            # receipt/history presence is counted as structural drift.
            source_receipts = SourcePlanReceipt.objects.all()
            source_histories = SourceHistory.objects.all()
            source_receipts_missing_history = source_receipts.filter(plan__history__isnull=True).count()
            source_histories_missing_receipt = source_histories.filter(plan__receipt__isnull=True).count()
            result_sample = _sample_source_result_drift()
            source_plan_receipts = {
                "scope": "source_plan_receipt_history_and_bounded_result_sample",
                "source_plans_total": SourcePlan.objects.count(),
                "source_plans_without_receipt": SourcePlan.objects.filter(receipt__isnull=True).count(),
                "source_receipts_total": source_receipts.count(),
                "source_histories_total": source_histories.count(),
                "source_receipts_without_history": source_receipts_missing_history,
                "source_histories_without_receipt": source_histories_missing_receipt,
                **result_sample,
                "total_observed_mismatches": (source_receipts_missing_history + source_histories_missing_receipt
                    + result_sample["source_receipt_result_history_mismatches"]
                    + result_sample["source_receipt_result_successor_mismatches"]),
                "full_source_integrity_proven": False,
                "repair_available": False,
                "notice": "STRUCTURAL_AND_BOUNDED_RESULT_IDS_ONLY_NOT_FULL_OR_LIVE_SOURCE_RIGHTS_PROOF",
            }
            return Response({
                "scope": "owner_operational_metadata",
                "as_of": now.isoformat(),
                "database": {
                    "connection": "ok", "vendor": connection.vendor,
                    "atlas_applied_migrations": migrations.count(),
                    "atlas_latest_applied": latest["name"] if latest else None,
                    "migration_state": "applied_only_not_schema_diff",
                },
                "jobs": {
                    "total": sum(jobs.values()),
                    "by_status": {status: jobs.get(status, 0) for status in _STATES},
                    "oldest_queued_at": oldest.isoformat() if oldest else None,
                    "stale_lease_count": AdminJob.objects.filter(
                        status="running", lease_expires_at__lt=now,
                    ).count(),
                },
                "worker": {
                    "alive_confirmed": False,
                    "latest_job_heartbeat": heartbeat.isoformat() if heartbeat else None,
                    "notice": "RECENT_JOB_HEARTBEAT_IS_NOT_A_WORKER_LIVENESS_PROOF",
                },
                "artifacts": {
                    "total": AdminArtifact.objects.count(),
                    "unpurged_bytes": bytes_total,
                    "unpurged_count": artifacts.count(),
                },
                "publication_receipts": receipt_status,
                "source_plan_receipts": source_plan_receipts,
                "backup": {
                    "state": "unavailable",
                    "reason": "NO_APPROVED_BACKUP_ADAPTER_CONNECTED_TO_THIS_CMS_ENDPOINT",
                },
                "notice": "READ_ONLY_HEALTH_NO_ENV_SHELL_SQL_EDITOR_OR_RESTORE",
            })
