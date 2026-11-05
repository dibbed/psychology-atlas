"""DB polling is the queue; every committed effect is fenced by the current lease."""
import uuid
import time
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import OperationalError
from django.db.models import Q
from django.utils import timezone

from .cms_audit import attribution
from .cms_content import digest
from .cms_job_models import AdminJob
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_sessions import current_session

LEASE_SECONDS = 120
MAX_ATTEMPTS = 3
JOB_INPUT_KINDS = {"research_intake": {"research_json", "dsm_json", "assessment_json"},
                   "learning_import": {"learning_json"}, "learning_export": {"learning_json"},
                   "privacy_export": {"privacy_request_json"}}
MANUAL_RETRY = {"TRANSIENT_DATABASE", "WORKER_INTERRUPTED", "UNAUTHENTICATED", "PERMISSION_DENIED", "POLICY_CHANGED", "INTERNAL_ERROR"}


def audit(job, action, request_id=None, code="", actor_id=None):
    AdminAuditEvent.objects.create(actor_id=job.actor_id if actor_id is None else actor_id, action=action, target_key=str(job.pk),
        outcome="failed" if action == "job.failed" else "success", reason="JOB_OPERATION",
        request_id=request_id or uuid.uuid4(), error_code=code)


def require_intake(actor):
    for cap in ("cms_enter", "cms_research_view", "cms_research_intake"):
        require(actor, cap)


def action_scope(actor, artifact, kind):
    from .cms_artifacts import _edit_scope
    if kind in {"learning_import", "learning_export"}:
        from .cms_learning_io import require_transfer
        require_transfer(actor, kind)
        expected_type = "learning_export_manifest" if kind == "learning_export" else ""
        if artifact.kind != "learning_json" or artifact.domain != "learning" or artifact.resource_type != expected_type:
            raise CMSFailure("INVALID_JOB_INPUT", 409)
    elif kind == "privacy_export":
        from .cms_privacy import require_privacy
        from .cms_privacy_io import artifact_binding
        require_privacy(actor, "export")
        if artifact.kind != "privacy_request_json" or artifact.domain != "privacy" or artifact.resource_type != "personal_data":
            raise CMSFailure("INVALID_JOB_INPUT", 409)
        artifact_binding(artifact)
    elif kind == "research_intake":
        require_intake(actor)
    elif kind == "artifact_cleanup":
        require(actor, "cms_enter")
        require(actor, "cms_artifact_upload")
        _edit_scope(actor, artifact)
    else:
        raise CMSFailure("INVALID_JOB_KIND", 400)


def artifact_digest(artifact, kind):
    value = {"artifact_id": str(artifact.pk), "sha256": artifact.sha256, "version": artifact.version}
    if kind != "research_intake":
        value["kind"] = kind
    return digest(value)


def job_scope(actor, job):
    if job.actor_id != actor.pk and "cms_owner" not in effective_permissions(actor):
        raise CMSFailure("NOT_FOUND", 404)
    from .cms_artifacts import get_artifact
    action_scope(actor, get_artifact(actor, job.artifact_id), job.kind)


def visible_jobs(actor, rows):
    from .cms_artifacts import KINDS, learning_artifact_filter
    require(actor, "cms_enter")
    held = effective_permissions(actor)
    scope = Q(pk__in=[])
    allowed = False
    if {"cms_user_view", "cms_privacy_export"} <= held:
        private = Q(artifact__domain="privacy", artifact__kind__in=("privacy_request_json", "privacy_export_json"),
                    artifact__resource_type="personal_data")
        scope |= private & Q(kind="privacy_export", artifact__kind="privacy_request_json")
        if "cms_artifact_upload" in held:
            scope |= private & Q(kind="artifact_cleanup")
        allowed = True
    if {"cms_learning_view", "cms_learning_export"} <= held:
        scope |= Q(kind="learning_export", artifact__kind="learning_json", artifact__domain="learning",
                   artifact__resource_type="learning_export_manifest")
        allowed = True
    if {"cms_learning_view", "cms_learning_create", "cms_learning_edit", "cms_artifact_upload"} <= held:
        scope |= Q(kind="learning_import", artifact__kind="learning_json", artifact__domain="learning", artifact__resource_type="")
        allowed = True
    if "cms_artifact_upload" in held:
        learning, granted = learning_artifact_filter(held, prefix="artifact__")
        scope |= Q(kind="artifact_cleanup") & learning
        allowed |= granted
    for kind, domain in KINDS.items():
        if domain == "learning":
            continue
        write = "cms_research_intake" if domain == "research" else f"cms_{domain}_edit"
        if {f"cms_{domain}_view", write} <= held:
            base = Q(artifact__kind=kind, artifact__domain=domain)
            if {"cms_research_view", "cms_research_intake"} <= held:
                scope |= base & Q(kind="research_intake")
                allowed = True
            if "cms_artifact_upload" in held:
                scope |= base & Q(kind="artifact_cleanup")
                allowed = True
    if "cms_artifact_upload" in held:
        from .cms_capabilities import GOVERNANCE_DOMAINS
        for domain in GOVERNANCE_DOMAINS:
            if {f"cms_{domain}_view", f"cms_{domain}_edit"} <= held:
                scope |= Q(kind="artifact_cleanup", artifact__kind="evidence_json", artifact__domain=domain)
                allowed = True
    if not allowed:
        raise CMSFailure("PERMISSION_DENIED")
    rows = rows.filter(scope)
    if "cms_owner" not in held:
        rows = rows.filter(actor_id=actor.pk, artifact__owner_id=actor.pk)
    return rows


def get_job(actor, job_id, lock=False):
    rows = AdminJob.objects.select_for_update() if lock else AdminJob.objects
    job = rows.filter(pk=job_id).first()
    if job is None:
        raise CMSFailure("NOT_FOUND", 404)
    job_scope(actor, job)
    return job


def job_data(job):
    allowed = {"dataset_id", "records", "duplicate", "artifact_id", "cleaned", "items", "created"}
    return {"id": str(job.pk), "kind": job.kind, "status": job.status, "version": job.version,
        "attempt": job.attempt, "progress_done": job.progress_done, "progress_total": job.progress_total,
        "cancel_requested": job.cancel_requested, "error_code": job.error_code,
        "artifact_id": str(job.artifact_id), "output_artifact_id": str(job.output_artifact_id) if job.output_artifact_id else None,
        "result": {k: v for k, v in job.result.items() if k in allowed},
        "created_at": job.created_at.isoformat(), "updated_at": job.updated_at.isoformat(),
        "retry_available": job.status == "failed" and job.attempt < MAX_ATTEMPTS and job.error_code in MANUAL_RETRY}


def enqueue_job(actor_id, session_id, artifact_id, request_key, request_id, *, kind="research_intake", expected=None):
    from .cms_artifacts import get_artifact
    try:
        key = uuid.UUID(str(request_key))
        artifact_id = uuid.UUID(str(artifact_id))
    except (ValueError, TypeError, AttributeError):
        raise CMSFailure("INVALID_INPUT", 400)
    with policy_lock() as policy:
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        artifact = get_artifact(actor, artifact_id, lock=True)
        action_scope(actor, artifact, kind)
        if kind == "artifact_cleanup":
            from .cms_artifacts import cleanup_eligible
            if type(expected) is not int or artifact.version != expected:
                raise CMSFailure("STALE_REVISION", 412)
            cleanup_eligible(artifact)
        elif artifact.kind not in JOB_INPUT_KINDS[kind] or artifact.state != "ready" or artifact.expires_at <= timezone.now():
            raise CMSFailure("ARTIFACT_NOT_READY", 409)
        fingerprint = artifact_digest(artifact, kind)
        actor_ref = attribution(actor.pk)
        old = AdminJob.objects.filter(actor_ref=actor_ref, request_key=key).first()
        if old:
            if old.payload_digest != fingerprint:
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            return old
        job = AdminJob.objects.create(kind=kind, actor=actor, actor_ref=actor_ref, session_id=session_id,
            policy_version=policy.version, artifact=artifact, request_key=key, payload_digest=fingerprint,
            available_at=timezone.now())
        audit(job, "job.enqueued", request_id)
        return job


def _authority(job, policy):
    from .cms_artifacts import get_artifact
    actor = User.objects.filter(pk=job.actor_id).first()
    if actor is None or job.session_id is None:
        raise CMSFailure("UNAUTHENTICATED")
    current_session(job.session_id, actor)
    if job.policy_version != policy.version:
        raise CMSFailure("POLICY_CHANGED", 409)
    artifact = get_artifact(actor, job.artifact_id, lock=True)
    action_scope(actor, artifact, job.kind)
    if job.kind == "artifact_cleanup":
        from .cms_artifacts import cleanup_eligible
        cleanup_eligible(artifact)
    elif artifact.kind not in JOB_INPUT_KINDS[job.kind] or artifact.state != "ready" or artifact.expires_at <= timezone.now():
        raise CMSFailure("ARTIFACT_NOT_READY", 409)
    if job.payload_digest != artifact_digest(artifact, job.kind):
        raise CMSFailure("ARTIFACT_CHANGED", 409)


def checkpoint_job(job_id, lease_token, effect):
    cancelled = False
    with policy_lock() as policy:
        job = AdminJob.objects.select_for_update().get(pk=job_id)
        now = timezone.now()
        if job.status != "running" or job.lease_token != lease_token or job.lease_expires_at is None or job.lease_expires_at <= now:
            raise CMSFailure("LEASE_LOST", 409)
        if job.cancel_requested:
            job.status, job.lease_token, job.lease_expires_at = "cancelled", None, None
            cancelled = True
            audit(job, "job.cancelled")
        else:
            _authority(job, policy)
            effect(job)
            if (type(job.progress_done) is not int or job.progress_done < 0 or
                    job.progress_total is not None and (type(job.progress_total) is not int or job.progress_total < job.progress_done)):
                raise CMSFailure("INVALID_JOB_PROGRESS", 409)
            job.heartbeat_at = now
            if job.status == "running":
                job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            else:
                job.lease_token, job.lease_expires_at = None, None
        job.version += 1
        job.save()
    if cancelled:
        raise CMSFailure("JOB_CANCELLED", 409)
    return job


def claim_job():
    with policy_lock():
        now = timezone.now()
        eligible = Q(status="queued", available_at__lte=now) | Q(status="running", lease_expires_at__lte=now)
        job = AdminJob.objects.select_for_update().filter(eligible).order_by("available_at", "created_at", "id").first()
        if job is None:
            return None
        if job.schema_version != 1:
            job.status, job.error_code = "failed", "INVALID_JOB_SCHEMA"
            job.lease_token, job.lease_expires_at = None, None
            job.version += 1
            job.save()
            audit(job, "job.failed", code=job.error_code)
            return job
        if job.status == "running" and (job.checkpoint.get("complete") is True or job.kind == "artifact_cleanup" and job.checkpoint.get("cleanup_prepared") is True):
            from .cms_artifacts import reconcile_intake, reconcile_cleanup
            try:
                if job.kind in {"learning_import", "learning_export"}:
                    from .cms_learning_io import reconcile_learning
                    result = reconcile_learning(job)
                elif job.kind == "privacy_export":
                    from .cms_privacy_io import reconcile_export
                    result = reconcile_export(job)
                else:
                    result = (reconcile_cleanup if job.kind == "artifact_cleanup" else reconcile_intake)(job)
            except CMSFailure:
                job.status, job.error_code = "failed", "CHECKPOINT_INTEGRITY"
                job.lease_token, job.lease_expires_at = None, None
                job.version += 1
                job.save()
                audit(job, "job.failed", code=job.error_code)
                return job
            if result is not None:
                job.status, job.result, job.error_code = "succeeded", result, ""
                job.lease_token, job.lease_expires_at = None, None
                job.version += 1
                job.save()
                audit(job, "job.reconciled")
                audit(job, "job.succeeded")
                return job
        if job.cancel_requested:
            job.status, job.error_code = "cancelled", ""
            job.lease_token, job.lease_expires_at = None, None
            job.version += 1
            job.save()
            audit(job, "job.cancelled")
            return job
        if job.attempt >= MAX_ATTEMPTS:
            job.status, job.error_code = "failed", "MAX_ATTEMPTS"
            job.lease_token, job.lease_expires_at = None, None
            job.version += 1
            job.save()
            audit(job, "job.failed", code=job.error_code)
            return job
        if job.status == "running":
            # The handler resumes committed archive offsets, never arbitrary external effects.
            audit(job, "job.reconciled")
        job.status, job.lease_token = "running", uuid.uuid4()
        job.attempt += 1
        job.version += 1
        job.heartbeat_at, job.lease_expires_at = now, now + timedelta(seconds=LEASE_SECONDS)
        job.save()
        audit(job, "job.claimed")
        return job


def _failed(job_id, token, code, transient=False):
    with policy_lock():
        job = AdminJob.objects.select_for_update().get(pk=job_id)
        if (job.status != "running" or job.lease_token != token or
                job.lease_expires_at is None or job.lease_expires_at <= timezone.now()):
            return
        job.error_code = code
        if job.checkpoint.get("complete") is True or job.kind == "artifact_cleanup" and job.checkpoint.get("cleanup_prepared") is True:
            # Already committed effects must remain eligible for receipt reconciliation.
            job.lease_expires_at = timezone.now() - timedelta(microseconds=1)
            job.version += 1
            job.save()
            audit(job, "job.failed", code=code)
            return
        job.status = "cancelled" if job.cancel_requested else "queued" if transient and job.attempt < MAX_ATTEMPTS else "failed"
        job.available_at = timezone.now() + timedelta(seconds=2 ** job.attempt)
        job.lease_token, job.lease_expires_at = None, None
        job.version += 1
        job.save()
        audit(job, "job.cancelled" if job.status == "cancelled" else "job.failed", code=code)


def transient_database(error):
    sqlstate = getattr(error.__cause__, "sqlstate", None)
    return sqlstate in {"40001", "40P01", "55P03"} or "database is locked" in str(error).lower()


def run_once():
    for attempt in range(3):
        try:
            job = claim_job()
            break
        except OperationalError as error:
            if not transient_database(error):
                raise CMSFailure("WORKER_DATABASE_FAILURE", 503)
            if attempt == 2:
                raise CMSFailure("WORKER_UNAVAILABLE", 503)
            time.sleep(0.1 * (2 ** attempt))
    if job is None or job.status != "running":
        return job
    try:
        checkpoint_job(job.pk, job.lease_token, lambda row: None)
        if job.kind in {"learning_import", "learning_export"}:
            from .cms_learning_io import process_learning
            result = process_learning(job.pk, job.lease_token)
        elif job.kind == "privacy_export":
            from .cms_privacy_io import process_export
            result = process_export(job.pk, job.lease_token)
        elif job.kind == "artifact_cleanup":
            from .cms_artifacts import process_cleanup
            result = process_cleanup(job.pk, job.lease_token)
        else:
            from .cms_artifacts import process_intake
            result = process_intake(job.pk, job.lease_token)
        current = AdminJob.objects.get(pk=job.pk)
        if current.status != "running":
            return current
        def complete(row):
            row.status = "succeeded"
            row.result = result or {}
            row.error_code = ""
            audit(row, "job.succeeded")
        checkpoint_job(job.pk, job.lease_token, complete)
    except CMSFailure as error:
        code = str(error.detail["code"])
        if code not in {"LEASE_LOST", "JOB_CANCELLED"}:
            _failed(job.pk, job.lease_token, code)
    except OperationalError as error:
        transient = transient_database(error)
        _failed(job.pk, job.lease_token, "TRANSIENT_DATABASE" if transient else "INTERNAL_ERROR", transient)
    except Exception:
        # Raw parser/storage exceptions can include private text and paths.
        _failed(job.pk, job.lease_token, "INTERNAL_ERROR")
    return AdminJob.objects.get(pk=job.pk)


def mutate_job(actor_id, session_id, job_id, expected, action, request_id):
    with policy_lock() as policy:
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        job = get_job(actor, job_id, lock=True)
        if type(expected) is not int or job.version != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if action == "cancel":
            if job.status not in {"queued", "running"}:
                raise CMSFailure("INVALID_TRANSITION", 409)
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "cancelled"
            audit(job, "job.cancelled" if job.status == "cancelled" else "job.cancel_requested", request_id, actor_id=actor.pk)
        elif action == "retry":
            if job.actor_id != actor.pk or job.status != "failed" or job.attempt >= MAX_ATTEMPTS or job.error_code not in MANUAL_RETRY:
                raise CMSFailure("INVALID_TRANSITION", 409)
            job.session_id, job.policy_version = session_id, policy.version
            _authority(job, policy)
            job.status, job.error_code = "queued", ""
            job.lease_token, job.lease_expires_at = None, None
            job.available_at = timezone.now()
            job.cancel_requested = False
            audit(job, "job.retried", request_id, actor_id=actor.pk)
        else:
            raise CMSFailure("NOT_FOUND", 404)
        job.version += 1
        job.save()
        return job
