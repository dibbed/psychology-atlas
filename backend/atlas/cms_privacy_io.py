"""Purpose-bound personal exports on the existing immutable artifact/lease protocol."""
import hashlib
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .cms_artifacts import artifact_bytes, bounded_json, store_generated
from .cms_audit import attribution
from .cms_job_models import AdminArtifact, AdminJob
from .cms_jobs import checkpoint_job, enqueue_job, job_scope
from .cms_models import AccountSecurityState, AdminAuditEvent, RolePolicy
from .cms_policy import CMSFailure, policy_lock
from .cms_privacy import SCOPES, PrivacyParser, require_privacy, text_units
from .cms_sessions import consume_step_up, current_session
from .cms_views import AdminAPIView, payload

MAX_BYTES = 1024 * 1024
MAX_RECORDS = 5000
MANIFEST_SCHEMA = "psychology-atlas-privacy-request-v1"
SCHEMA = "psychology-atlas-personal-export-v1"
IDENTITY_FIELDS = ("id", "username", "email", "first_name", "last_name", "is_active", "date_joined")


def export_request(data):
    if type(data) is not dict or set(data) != {"purpose", "case_ref", "request_key"} or data["purpose"] != "DATA_SUBJECT_REQUEST":
        raise CMSFailure("INVALID_INPUT", 400)
    for field in ("case_ref", "request_key"):
        try:
            value = uuid.UUID(data[field]) if type(data[field]) is str else None
        except ValueError:
            value = None
        if value is None or not value.int or str(value) != data[field]:
            raise CMSFailure("INVALID_INPUT", 400)
    return data


def subject_version(subject_id):
    if not User.objects.filter(pk=subject_id).exists():
        raise CMSFailure("NOT_FOUND", 404)
    return AccountSecurityState.objects.filter(user_id=subject_id).values_list("security_version", flat=True).first() or 0


def artifact_binding(artifact):
    if (artifact.domain != "privacy" or artifact.resource_type != "personal_data"
            or artifact.resource_id is None or str(subject_version(artifact.resource_id)) != artifact.resource_version):
        raise CMSFailure("NOT_FOUND", 404)


def encoded(document):
    chunks, size = [], 0
    try:
        for chunk in DjangoJSONEncoder(ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).iterencode(document):
            raw = chunk.encode("utf-8")
            size += len(raw)
            if size > MAX_BYTES:
                raise CMSFailure("PRIVACY_LIMIT", 400)
            chunks.append(raw)
    except ValueError:
        raise CMSFailure("PRIVACY_DATA_INVALID", 409)
    return b"".join(chunks)


def make_artifact(actor, identifier, raw, kind, subject_id, version):
    return AdminArtifact(id=identifier, kind=kind, domain="privacy", owner=actor, owner_ref=attribution(actor.pk),
        resource_type="personal_data", resource_id=subject_id, resource_version=str(version),
        filename="personal-request.json" if kind == "privacy_request_json" else "personal-export.json",
        storage_key=identifier.hex + ".json", size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
        expires_at=timezone.now() + timedelta(hours=24))


def enqueue_export(actor_id, session_id, subject_id, data, request_id):
    data = export_request(data)
    key = uuid.UUID(data["request_key"])
    with policy_lock() as policy:
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require_privacy(actor, "export")
        version = subject_version(subject_id)
        raw = encoded({"schema_version": MANIFEST_SCHEMA, "subject_id": subject_id, "security_version": version, **data})
        checksum = hashlib.sha256(raw).hexdigest()
        old = AdminJob.objects.filter(actor_ref=attribution(actor.pk), request_key=key).first()
        if old:
            job_scope(actor, old)
            if old.kind != "privacy_export" or old.artifact.sha256 != checksum:
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            return old
        identifier = uuid.uuid5(key, attribution(actor.pk) + ":privacy-request")
        artifact = AdminArtifact.objects.select_for_update().filter(pk=identifier).first()
        if artifact is None:
            consume_step_up(session_id, actor, "privacy_export", subject_id, data)
            artifact = make_artifact(actor, identifier, raw, "privacy_request_json", subject_id, version)
            artifact.save(force_insert=True)
            AdminAuditEvent.objects.create(actor=actor, action="privacy.export_requested", outcome="success", target_kind="user",
                target_id=subject_id, target_key=salted_hmac("cms-privacy-case-v1", data["case_ref"], algorithm="sha256").hexdigest(),
                reason="PRIVACY_REQUEST", request_id=request_id, policy_version=policy.version)
        elif (artifact.owner_id != actor.pk or artifact.kind != "privacy_request_json" or artifact.sha256 != checksum):
            raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
    # A consumed proof authorizes this exact durable quarantine intent, including same-key recovery.
    with policy_lock():
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require_privacy(actor, "export")
        artifact = AdminArtifact.objects.select_for_update().get(pk=identifier)
        artifact_binding(artifact)
        if artifact.state not in {"quarantine", "ready"} or artifact.expires_at <= timezone.now():
            raise CMSFailure("ARTIFACT_NOT_READY", 409)
        store_generated(artifact, raw)
        artifact.state, artifact.validation_code = "ready", "PRIVACY_REQUEST"
        artifact.save(update_fields=["state", "validation_code"])
        return enqueue_job(actor_id, session_id, identifier, key, request_id, kind="privacy_export")


def manifest(job):
    document = bounded_json(artifact_bytes(job.artifact), protect_assessment=False)[1]
    if (type(document) is not dict or set(document) != {"schema_version", "subject_id", "security_version", "purpose", "case_ref", "request_key"}
            or document["schema_version"] != MANIFEST_SCHEMA or document["subject_id"] != job.artifact.resource_id
            or str(document["security_version"]) != job.artifact.resource_version or document["request_key"] != str(job.request_key)):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    export_request({key: document[key] for key in ("purpose", "case_ref", "request_key")})
    artifact_binding(job.artifact)
    return document


def personal_document(job):
    request = manifest(job)
    subject_id = request["subject_id"]
    subject = User.objects.filter(pk=subject_id)
    units = text_units(subject, IDENTITY_FIELDS)
    if units > MAX_BYTES:
        raise CMSFailure("PRIVACY_LIMIT", 400)
    identity = subject.values(*IDENTITY_FIELDS).get()
    data, count = {}, 1
    for scope, (model, owner, fields) in SCOPES.items():
        rows = model.objects.filter(**{owner: subject_id}).order_by("pk")
        count += rows.count()
        if count > MAX_RECORDS:
            raise CMSFailure("PRIVACY_LIMIT", 400)
        units += text_units(rows, fields)
        if units > MAX_BYTES:
            raise CMSFailure("PRIVACY_LIMIT", 400)
        data[scope] = list(rows.values(*fields))
    raw = encoded({"schema_version": SCHEMA, "purpose": request["purpose"], "requested_at": job.artifact.created_at,
        "identity": identity, "data": data,
        "exclusions": ["credentials_and_sessions", "other_users", "canonical_content_and_answer_keys", "retained_governance"]})
    return raw, count


def effect_authority(job):
    from .cms_jobs import _authority
    _authority(job, RolePolicy.objects.get(pk=1))
    if job.lease_expires_at is None or job.lease_expires_at <= timezone.now():
        raise CMSFailure("LEASE_LOST", 409)


def process_export(job_id, token):
    prepared = {}

    def prepare(job):
        if job.checkpoint.get("complete") is True:
            prepared["result"] = reconcile_export(job)
            return
        raw, count = personal_document(job)
        identifier = uuid.uuid5(job.pk, "privacy-output")
        if job.output_artifact_id:
            output = AdminArtifact.objects.select_for_update().get(pk=job.output_artifact_id)
            if (output.pk != identifier or output.kind != "privacy_export_json" or output.owner_id != job.actor_id
                    or output.resource_id != job.artifact.resource_id or output.resource_version != job.artifact.resource_version
                    or output.domain != "privacy" or output.resource_type != "personal_data"
                    or output.state != "quarantine" or output.sha256 != hashlib.sha256(raw).hexdigest()
                    or output.size != len(raw) or output.expires_at <= timezone.now()):
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        else:
            output = make_artifact(job.actor, identifier, raw, "privacy_export_json", job.artifact.resource_id, job.artifact.resource_version)
            output.save(force_insert=True)
            job.output_artifact = output
        effect_authority(job)
        job.checkpoint = {"output_prepared": True, "sha256": output.sha256, "size": output.size}
        prepared.update(raw=raw, result={"records": count, "artifact_id": str(identifier)})

    # Public learner writers do not take RolePolicy: all projections need one database snapshot.
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        checkpoint_job(job_id, token, prepare)
    if "raw" not in prepared:
        return prepared["result"]

    def store(job):
        if job.checkpoint.get("complete") is True:
            prepared["result"] = reconcile_export(job)
            return
        output = AdminArtifact.objects.select_for_update().get(pk=job.output_artifact_id)
        artifact_binding(output)
        raw = prepared["raw"]
        if (output.pk != uuid.uuid5(job.pk, "privacy-output") or output.state != "quarantine"
                or output.sha256 != hashlib.sha256(raw).hexdigest() or output.size != len(raw)
                or output.expires_at <= timezone.now()):
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        store_generated(output, raw)
        effect_authority(job)
        output.state, output.validation_code = "ready", "PERSONAL_EXPORT"
        output.version += 1
        output.save(update_fields=["state", "validation_code", "version"])
        job.checkpoint = {**job.checkpoint, "complete": True, "input_sha256": job.artifact.sha256, "result": prepared["result"]}
        job.progress_done = job.progress_total = prepared["result"]["records"]
        AdminAuditEvent.objects.create(actor_id=job.actor_id, action="privacy.exported", outcome="success",
            target_key=str(job.pk), reason="PRIVACY_REQUEST", request_id=uuid.uuid4())
        effect_authority(job)

    checkpoint_job(job_id, token, store)
    return prepared["result"]


def reconcile_export(job):
    result, output = job.checkpoint.get("result"), job.output_artifact
    if (job.checkpoint.get("complete") is not True or type(result) is not dict or set(result) != {"records", "artifact_id"}
            or type(result["records"]) is not int or not 1 <= result["records"] <= MAX_RECORDS
            or job.checkpoint.get("input_sha256") != job.artifact.sha256 or output is None
            or str(output.pk) != result["artifact_id"] or output.pk != uuid.uuid5(job.pk, "privacy-output")
            or output.kind != "privacy_export_json" or output.domain != "privacy" or output.owner_id != job.actor_id
            or output.resource_id != job.artifact.resource_id or output.resource_version != job.artifact.resource_version
            or output.resource_type != "personal_data" or output.sha256 != job.checkpoint.get("sha256")
            or output.size != job.checkpoint.get("size") or output.state not in {"ready", "revoked", "expired"}):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    if output.purged_at is None:
        artifact_bytes(output)
    return result


class PrivacyExportView(AdminAPIView):
    capability = "cms_privacy_export"
    parser_classes = (PrivacyParser,)

    def post(self, request, user_id):
        from .cms_learning_io_views import queued
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return queued(enqueue_export(request.user.pk, request.cms_session.pk, user_id,
            payload(request, {"purpose", "case_ref", "request_key"}), self.request_id))
