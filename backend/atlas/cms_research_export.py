"""Purpose-bound, projection-only research exports on the existing private artifact/job protocol.

Selection is snapshotted at request time. Raw archives, payload, source/rights documents
and mapping proposals are never export fields, regardless of role.
"""
import hashlib
import json
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from . import cms_artifacts
from .cms_audit import attribution
from .cms_job_models import AdminArtifact, AdminJob, ResearchRecordDecision
from .cms_jobs import checkpoint_job, enqueue_job, job_scope
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_sessions import current_session
from .models import ResearchRecord

SCHEMA = "psychology-atlas-research-export-v1"
MANIFEST_SCHEMA = "psychology-atlas-research-selection-v1"
MAX_BYTES = 1024 * 1024
MAX_RECORDS = 5000
PUBLIC_FIELDS = frozenset({"id", "dataset_id", "section", "external_id",
    "review_status", "verification_status", "staging_state"})
SENSITIVE_FIELDS = frozenset({"name_en", "name_fa"})
ALLOWED_FIELDS = PUBLIC_FIELDS | SENSITIVE_FIELDS
EXPORT_RESOURCE = "research_dataset_export"
SENSITIVE_RESOURCE = "research_dataset_export_sensitive"


def require_export(actor):
    for capability in ("cms_enter", "cms_research_view", "cms_research_export"):
        require(actor, capability)


def selection(value):
    if (type(value) is not dict
            or set(value) != {"target_kind", "target_id", "projection", "request_key"}
            or type(value["target_kind"]) is not str or value["target_kind"] not in {"dataset", "record"}
            or type(value["target_id"]) is not int or not 0 < value["target_id"] < 2**63
            or type(value["projection"]) is not list or not 1 <= len(value["projection"]) <= len(ALLOWED_FIELDS)
            or any(type(field) is not str or field not in ALLOWED_FIELDS for field in value["projection"])
            or len(set(value["projection"])) != len(value["projection"])
            or type(value["request_key"]) is not str):
        raise CMSFailure("INVALID_FIELDS", 400)
    try:
        key = uuid.UUID(value["request_key"])
    except (ValueError, TypeError, AttributeError):
        raise CMSFailure("INVALID_FIELDS", 400)
    if not key.int or str(key) != value["request_key"]:
        raise CMSFailure("INVALID_FIELDS", 400)
    return key


def encoded(value):
    chunks, size = [], 0
    try:
        for part in json.JSONEncoder(ensure_ascii=False, allow_nan=False, sort_keys=True,
                                     separators=(",", ":")).iterencode(value):
            piece = part.encode("utf-8")
            size += len(piece)
            if size > MAX_BYTES:
                raise CMSFailure("JSON_LIMIT", 400)
            chunks.append(piece)
    except (TypeError, ValueError):
        raise CMSFailure("INVALID_EXPORT_DATA", 409)
    return b"".join(chunks)


def _dataset_and_rows(actor, request):
    from .cms_artifacts import get_dataset, get_record
    kind, identifier = request["target_kind"], request["target_id"]
    if kind == "dataset":
        dataset = get_dataset(actor, identifier, lock=True)
        records = ResearchRecord.objects.filter(dataset_id=dataset.pk)
    else:
        record = get_record(actor, identifier, lock=True)
        dataset = get_dataset(actor, record.dataset_id, lock=True)
        records = ResearchRecord.objects.filter(pk=record.pk)
    if dataset.records.count() != dataset.ingestion_audit.get("list_record_total", dataset.records.count()):
        raise CMSFailure("INTAKE_INCOMPLETE", 409)
    total = records.count()
    if not 1 <= total <= MAX_RECORDS:
        raise CMSFailure("EXPORT_LIMIT", 400)
    latest = ResearchRecordDecision.objects.filter(record_id=OuterRef("pk")).order_by("-sequence").values("action")[:1]
    rows = records.select_for_update().annotate(
        staging_state=Coalesce(Subquery(latest), Value("unmapped"))
    ).order_by("pk").values(
        "id", "dataset_id", "section", "external_id", "review_status", "verification_status",
        "name_en", "name_fa", "staging_state")
    projection = request["projection"]
    return dataset, [{field: row[field] for field in projection} for row in rows]


def _manifest(actor, data):
    dataset, rows = _dataset_and_rows(actor, data)
    snapshot = {"schema_version": SCHEMA, "target": {"kind": data["target_kind"], "id": data["target_id"]},
        "dataset": {"id": dataset.pk, "source_sha256": dataset.source_sha256,
                    "dataset_name": dataset.dataset_name, "dataset_version": dataset.dataset_version},
        "projection": data["projection"], "records": rows}
    # Both request manifest and output are bounded by the same limit.
    encoded(snapshot)
    return dataset, {"schema_version": MANIFEST_SCHEMA, "selection": data, "snapshot": snapshot}


def _artifact(actor, identifier, kind, raw, dataset, resource_type, version):
    return AdminArtifact(id=identifier, kind=kind, domain="research", owner=actor,
        owner_ref=attribution(actor.pk), resource_type=resource_type,
        resource_id=dataset.pk, resource_version=dataset.source_sha256,
        filename="research-selection.json" if kind == "research_request_json" else "research-export.json",
        storage_key=identifier.hex + ".json", size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(), expires_at=timezone.now() + timedelta(days=7))


def _document(raw):
    doc = cms_artifacts.bounded_json(raw, protect_assessment=False)[1]
    if (type(doc) is not dict or set(doc) != {"schema_version", "selection", "snapshot"}
            or doc["schema_version"] != MANIFEST_SCHEMA or type(doc["snapshot"]) is not dict
            or doc["snapshot"].get("schema_version") != SCHEMA):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    return doc


def enqueue_export(actor_id, session_id, data, request_id):
    key = selection(data)
    with policy_lock():
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require_export(actor)
        if set(data["projection"]) & SENSITIVE_FIELDS and "cms_research_raw_read" not in effective_permissions(actor):
            raise CMSFailure("PERMISSION_DENIED")
        prior = AdminJob.objects.filter(actor_ref=attribution(actor.pk), request_key=key).first()
        if prior:
            if (prior.kind != "research_export"
                    or _document(cms_artifacts.artifact_bytes(prior.artifact))["selection"] != data):
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            job_scope(actor, prior)
            return prior
        dataset, manifest = _manifest(actor, data)
        raw = encoded(manifest)
        identifier = uuid.uuid5(key, attribution(actor.pk) + ":research-export-request")
        artifact = AdminArtifact.objects.select_for_update().filter(pk=identifier).first()
        if artifact is None:
            bound_type = SENSITIVE_RESOURCE if set(data["projection"]) & SENSITIVE_FIELDS else EXPORT_RESOURCE
            artifact = _artifact(actor, identifier, "research_request_json", raw, dataset,
                                 bound_type, key)
            artifact.save(force_insert=True)
            AdminAuditEvent.objects.create(actor=actor, action="research.export_requested",
                outcome="success", target_key=str(artifact.pk), reason="RESEARCH_EXPORT",
                request_id=request_id)
        elif (artifact.owner_id != actor.pk or artifact.kind != "research_request_json"
                or artifact.resource_id != dataset.pk or artifact.sha256 != hashlib.sha256(raw).hexdigest()):
            raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
    # A prepared DB intent survives the next filesystem write or job enqueue failure.
    with policy_lock():
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require_export(actor)
        artifact = AdminArtifact.objects.select_for_update().get(pk=identifier)
        cms_artifacts.artifact_scope(actor, artifact)
        if artifact.state not in {"quarantine", "ready"} or artifact.expires_at <= timezone.now():
            raise CMSFailure("ARTIFACT_NOT_READY", 409)
        cms_artifacts.store_generated(artifact, raw)
        artifact.state, artifact.validation_code = "ready", "RESEARCH_SELECTION"
        artifact.save(update_fields=["state", "validation_code"])
        return enqueue_job(actor_id, session_id, artifact.pk, key, request_id, kind="research_export")


def _source(job):
    document = _document(cms_artifacts.artifact_bytes(job.artifact))
    if (document["selection"]["request_key"] != str(job.request_key)
            or document["snapshot"]["dataset"]["id"] != job.artifact.resource_id
            or document["snapshot"]["dataset"]["source_sha256"] != job.artifact.resource_version
            or document["snapshot"]["target"] != {"kind": document["selection"]["target_kind"],
                                                      "id": document["selection"]["target_id"]}
            or document["snapshot"]["projection"] != document["selection"]["projection"]
            or len(document["snapshot"]["records"]) > MAX_RECORDS
            or not all(type(row) is dict and set(row) == set(document["selection"]["projection"])
                       for row in document["snapshot"]["records"])):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    return encoded(document["snapshot"])


def process_export(job_id, token):
    state = {}

    def prepare(job):
        if job.checkpoint.get("complete") is True:
            state["result"] = reconcile_export(job)
            return
        raw = _source(job)
        identifier = uuid.uuid5(job.pk, "research-output")
        if job.output_artifact_id:
            output = AdminArtifact.objects.select_for_update().get(pk=job.output_artifact_id)
            if (output.pk != identifier or output.kind != "research_export_json"
                    or output.domain != "research" or output.owner_id != job.actor_id
                    or output.resource_id != job.artifact.resource_id
                    or output.resource_type != job.artifact.resource_type
                    or output.resource_version != job.artifact.resource_version
                    or output.sha256 != hashlib.sha256(raw).hexdigest() or output.size != len(raw)
                    or output.state != "quarantine" or output.expires_at <= timezone.now()):
                raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        else:
            from .cms_artifacts import get_dataset
            dataset = get_dataset(job.actor, job.artifact.resource_id)
            output = _artifact(job.actor, identifier, "research_export_json", raw, dataset,
                               job.artifact.resource_type, job.pk)
            output.save(force_insert=True)
            job.output_artifact = output
        job.checkpoint = {"output_prepared": True, "sha256": output.sha256, "size": output.size}
        state["raw"] = raw
        state["result"] = {"records": len(_document(cms_artifacts.artifact_bytes(job.artifact))["snapshot"]["records"]),
                           "artifact_id": str(identifier)}

    checkpoint_job(job_id, token, prepare)
    if "raw" not in state:
        return state["result"]

    def finish(job):
        output = AdminArtifact.objects.select_for_update().get(pk=job.output_artifact_id)
        raw = state["raw"]
        if (output.pk != uuid.uuid5(job.pk, "research-output")
                or output.state != "quarantine" or output.expires_at <= timezone.now()
                or output.resource_type != job.artifact.resource_type
                or output.sha256 != hashlib.sha256(raw).hexdigest() or output.size != len(raw)):
            raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
        cms_artifacts.store_generated(output, raw)
        output.state, output.validation_code = "ready", "RESEARCH_EXPORT"
        output.version += 1
        output.save(update_fields=("state", "validation_code", "version"))
        job.checkpoint = {**job.checkpoint, "complete": True,
                          "input_sha256": job.artifact.sha256, "result": state["result"]}
        job.progress_done = job.progress_total = state["result"]["records"]
        AdminAuditEvent.objects.create(actor_id=job.actor_id, action="research.exported",
            outcome="success", target_key=str(job.pk), reason="RESEARCH_EXPORT",
            request_id=uuid.uuid4())

    checkpoint_job(job_id, token, finish)
    return state["result"]


def reconcile_export(job):
    result, output = job.checkpoint.get("result"), job.output_artifact
    if (job.kind != "research_export" or job.checkpoint.get("complete") is not True
            or type(result) is not dict or set(result) != {"records", "artifact_id"}
            or type(result["records"]) is not int or not 1 <= result["records"] <= MAX_RECORDS
            or job.checkpoint.get("input_sha256") != job.artifact.sha256
            or output is None or output.pk != uuid.uuid5(job.pk, "research-output")
            or str(output.pk) != result["artifact_id"]
            or output.kind != "research_export_json" or output.domain != "research"
            or output.resource_id != job.artifact.resource_id
            or output.resource_type != job.artifact.resource_type
            or output.resource_version != job.artifact.resource_version
            or output.sha256 != job.checkpoint.get("sha256")
            or output.size != job.checkpoint.get("size")
            or output.state not in {"ready", "revoked", "expired"}):
        raise CMSFailure("CHECKPOINT_INTEGRITY", 409)
    if output.purged_at is None:
        cms_artifacts.artifact_bytes(output)
    return result
