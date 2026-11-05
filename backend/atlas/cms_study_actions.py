"""Purpose/MFA-bound interventions around the existing learner lifecycle services."""
import hashlib
import json
import re
import uuid

from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.crypto import salted_hmac
from rest_framework.response import Response

from .cms_audit import attribution
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_privacy import PrivacyParser
from .cms_sessions import consume_step_up, current_session
from .cms_study_operation_models import StudyOperationReceipt
from .cms_views import AdminAPIView
from .models import StudyPlan, StudyBlock, StudySession
from .study_planning import StudyPlanningError, transition_study_plan
from .study_scheduler import reschedule_study_block, skip_study_block, unlock_study_block
from .study_sessions import StudySessionError, abandon_session

MODELS = {"plan": StudyPlan, "block": StudyBlock, "session": StudySession}
ACTIONS = {"plan": {"pause", "resume"}, "block": {"reschedule", "skip", "unlock"}, "session": {"abandon"}}
PLAN_FIELDS = ("status", "start_date", "target_date", "generation_version", "updated_at")
FIELDS = {
    "plan": ("id", "user_id", *PLAN_FIELDS),
    "block": ("id", "plan_id", "scope_id", "status", "origin", "block_kind", "scheduled_date", "sequence",
        "locked_by_user", "updated_at", "disorder_id", "concept_id", "therapy_id", "theory_id",
        "psychologist_id", "timeline_event_id", "quiz_id", "clinical_case_id"),
    "session": ("id", "user_id", "plan_id", "primary_block_id", "status", "started_at", "completed_at",
        "abandoned_at", "actual_seconds", "planned_minutes", "updated_at"),
}
REQUIRED = {"cms_user_view", "cms_study_view", "cms_study_correct"}


def snapshots(kind, rows):
    fields = FIELDS[kind] + (() if kind == "plan" else tuple("plan__"+field for field in PLAN_FIELDS))
    result = {}
    for state in rows.values(*fields):
        raw = json.dumps(state, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"))
        tag = '"'+hashlib.sha256(raw.encode()).hexdigest()+'"'
        actions = []
        if kind == "plan":
            actions = ["pause"] if state["status"] == "active" else ["resume"] if state["status"] == "paused" else []
        elif kind == "block" and state["status"] == "pending" and state["plan__status"] == "active":
            actions = ["reschedule", "skip"]
            if state["origin"] == "generated" and state["locked_by_user"]:
                actions.append("unlock")
        elif kind == "session" and state["status"] == "in_progress":
            actions = ["abandon"]
        result[state["id"]] = {"kind": kind, "etag": tag, "actions": actions}
    return result


def add_operations(actor, scope, selected, results):
    kind = {"study_plans": "plan", "study_blocks": "block", "study_sessions": "session"}.get(scope)
    if kind and REQUIRED <= effective_permissions(actor):
        operations = snapshots(kind, selected)
        for row in results:
            row["operations"] = operations[row["id"]]


def operation_request(data):
    fields = {"kind", "target_id", "action", "etag", "purpose", "case_ref", "reason", "request_key"}
    if (type(data) is not dict or type(data.get("kind")) is not str or data["kind"] not in MODELS
            or type(data.get("action")) is not str or data["action"] not in ACTIONS[data["kind"]]
            or set(data) != fields | ({"scheduled_date"} if data["action"] == "reschedule" else set())
            or type(data.get("target_id")) is not int or not 0 < data["target_id"] < 2**63
            or data.get("purpose") != "SUPPORT_REQUEST" or data.get("reason") != "STUDY_SUPPORT"
            or type(data.get("etag")) is not str or not re.fullmatch(r'"[0-9a-f]{64}"', data["etag"])):
        raise CMSFailure("INVALID_INPUT", 400)
    for field in ("case_ref", "request_key"):
        try:
            value = uuid.UUID(data[field]) if type(data[field]) is str else None
        except ValueError:
            value = None
        if value is None or not value.int or str(value) != data[field]:
            raise CMSFailure("INVALID_INPUT", 400)
    if data["action"] == "reschedule" and (type(data["scheduled_date"]) is not str
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["scheduled_date"])):
        raise CMSFailure("INVALID_INPUT", 400)
    return data


def _locked_target(subject, kind, identifier):
    rows = MODELS[kind].objects
    owner = "plan__user" if kind == "block" else "user"
    locator = rows.filter(pk=identifier, **{owner: subject}).values("pk", *(('plan_id',) if kind != "plan" else ())).first()
    if locator is None:
        raise CMSFailure("NOT_FOUND", 404)
    plan_id = identifier if kind == "plan" else locator["plan_id"]
    # Match learner order: plan before block/session; never lock a joined nullable relation.
    if not StudyPlan.objects.select_for_update().filter(pk=plan_id, user=subject).exists():
        raise CMSFailure("NOT_FOUND", 404)
    row = rows.select_for_update().filter(pk=identifier, **{owner: subject}).first()
    if row is None or kind != "plan" and row.plan_id != plan_id:
        raise CMSFailure("NOT_FOUND", 404)
    return row


def _result(receipt):
    return {"receipt_id": receipt.pk, "kind": receipt.kind, "resource_id": receipt.resource_id,
        "action": receipt.action, "etag": receipt.after_etag, "learning_evidence_created": False}


def operate(actor_id, session_id, subject_id, data, expected, request_id):
    data = operation_request(data)
    if expected is None:
        raise CMSFailure("PRECONDITION_REQUIRED", 428)
    if expected != data["etag"]:
        raise CMSFailure("STALE_REVISION", 412)
    digest = salted_hmac("cms-study-intent-v1", json.dumps([subject_id, data], sort_keys=True), algorithm="sha256").hexdigest()
    with policy_lock() as policy:
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        for cap in REQUIRED:
            require(actor, cap)
        old = StudyOperationReceipt.objects.filter(request_key=data["request_key"]).first()
        if old:
            if old.actor_ref != attribution(actor.pk) or old.request_digest != digest:
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            return _result(old)
        subject = User.objects.filter(pk=subject_id).first()
        if subject is None:
            raise CMSFailure("NOT_FOUND", 404)
        kind, identifier = data["kind"], data["target_id"]
        row = _locked_target(subject, kind, identifier)
        current_session(session_id, actor)
        for cap in REQUIRED:
            require(actor, cap)
        rows = MODELS[kind].objects.filter(pk=row.pk)
        snapshot = snapshots(kind, rows)[row.pk]
        if snapshot["etag"] != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if data["action"] not in snapshot["actions"]:
            raise CMSFailure("STUDY_NOT_ACTIONABLE", 409)
        consume_step_up(session_id, actor, "study_correct", subject_id, data)
        try:
            if kind == "plan":
                transition_study_plan(subject, identifier, "activate" if data["action"] == "resume" else "pause")
            elif kind == "session":
                abandon_session(subject, identifier)
            elif data["action"] == "reschedule":
                reschedule_study_block(subject, identifier, {"scheduled_date": data["scheduled_date"]})
            else:
                (skip_study_block if data["action"] == "skip" else unlock_study_block)(subject, identifier)
        except (StudyPlanningError, StudySessionError) as exc:
            raise CMSFailure(exc.code.upper(), exc.status_code)
        after = snapshots(kind, rows)[row.pk]["etag"]
        receipt = StudyOperationReceipt.objects.create(actor=actor, actor_ref=attribution(actor.pk), kind=kind,
            resource_id=identifier, action=data["action"], request_key=data["request_key"], request_digest=digest,
            before_etag=expected, after_etag=after)
        AdminAuditEvent.objects.create(actor=actor, action="study.operated", outcome="success", target_kind="user",
            target_id=subject_id, target_key=str(receipt.request_key), reason="STUDY_SUPPORT",
            request_id=request_id, policy_version=policy.version)
        return _result(receipt)


class StudyOperationView(AdminAPIView):
    capability = "cms_study_correct"
    parser_classes = (PrivacyParser,)

    def post(self, request, user_id):
        if request.query_params or not 0 < user_id < 2**63:
            raise CMSFailure("INVALID_INPUT", 400)
        result = operate(request.user.pk, request.cms_session.pk, user_id, request.data,
            request.headers.get("If-Match"), self.request_id)
        return Response(result, headers={"ETag": result["etag"]})
