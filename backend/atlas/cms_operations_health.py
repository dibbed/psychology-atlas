"""P18 owner-only conservative health reader. No shell, secrets or backup writes."""
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Count, Max, Min, Sum
from django.utils import timezone
from rest_framework.response import Response

from .cms_job_models import AdminArtifact, AdminJob
from .cms_policy import CMSFailure, policy_lock, require
from .cms_views import AdminAPIView


_STATES = ("queued", "running", "succeeded", "failed", "cancelled", "reconciling")


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
                "backup": {
                    "state": "unavailable",
                    "reason": "NO_APPROVED_BACKUP_ADAPTER_CONNECTED_TO_THIS_CMS_ENDPOINT",
                },
                "notice": "READ_ONLY_HEALTH_NO_ENV_SHELL_SQL_EDITOR_OR_RESTORE",
            })
