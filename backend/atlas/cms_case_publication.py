"""P16 CaseRevision release gate.

A reviewed source/rights/science dossier is a human assertion bound to exact
case graph bytes and source state, NOT an automatic proof of scientific truth.
Every step is serialized under policy_lock; no browser-provided manifest.
"""
import hashlib
import json
import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .brain_publication import source_is_resolved
from .case_graph import validate_case_revision_graph
from .cms_audit import attribution
from .cms_case_editor import _lock_revision, revision_etag
from .cms_case_fingerprint import case_revision_fingerprint
from .cms_case_publication_models import CasePublicationPlan, CasePublicationReceipt, CasePublicationReview
from .cms_governance import source_snapshot
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_review import current_policy, reviewer_conflict
from .cms_sessions import consume_step_up, current_session
from .models import CaseAttempt, CaseRevision, SourceReference

KINDS = ("source", "scientific", "rights")
RIGHTS_FIELDS = {"rightsholder", "holder_basis", "permission_statement", "territory",
                 "review_on", "expires_on", "material", "intended_use"}
PERMISSIONS = {"source": "cms_review_decide_cases_source",
               "scientific": "cms_review_decide_cases_scientific",
               "rights": "cms_review_decide_cases_rights"}


def _digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _candidate(case, revision):
    if (revision.status != CaseRevision.Status.DRAFT or revision.seed_managed
            or case.seed_managed or case.current_revision_id == revision.pk
            or CaseAttempt.objects.filter(revision=revision).exists()):
        raise CMSFailure("REVISION_NOT_PUBLISHABLE", 409)
    if (not revision.title.strip() or not revision.patient_summary.strip()
            or not revision.educational_objective.strip()):
        raise CMSFailure("REQUIRED_CASE_METADATA_MISSING", 409)
    if validate_case_revision_graph(revision):
        raise CMSFailure("CASE_GRAPH_INVALID", 409)


def _evidence(data):
    if (type(data) is not list or not 1 <= len(data) <= 20
            or any(type(e) is not dict or set(e) != {"source_id", "locator"}
                   or type(e["source_id"]) is not int or e["source_id"] < 1
                   or type(e["locator"]) is not str or not 1 <= len(e["locator"].strip()) <= 1000
                   for e in data)):
        raise CMSFailure("INVALID_EVIDENCE", 400)
    result = sorted([{"source_id": e["source_id"], "locator": e["locator"].strip()} for e in data],
                    key=lambda e: (e["source_id"], e["locator"]))
    if len(set((e["source_id"], e["locator"]) for e in result)) != len(result):
        raise CMSFailure("INVALID_EVIDENCE", 400)
    _source_dependency(result)
    return result


def _source_dependency(evidence, *, lock=True):
    ids = sorted({e["source_id"] for e in evidence})
    state = source_snapshot(ids, lock=lock)
    if state["missing_source_ids"] or state["unavailable_source_ids"]:
        raise CMSFailure("SOURCE_UNAVAILABLE", 409)
    sources = list(SourceReference.objects.filter(pk__in=ids))
    if len(sources) != len(ids) or not all(source_is_resolved(source) for source in sources):
        raise CMSFailure("SOURCE_UNRESOLVED", 409)
    return state["source_digest"]


def _rights(data):
    if type(data) is not dict or set(data) != RIGHTS_FIELDS:
        raise CMSFailure("INVALID_RIGHTS_SCOPE", 400)
    for field, limit in (("rightsholder", 1000), ("holder_basis", 2000),
                         ("permission_statement", 4000), ("territory", 255)):
        if type(data[field]) is not str or not 1 <= len(data[field].strip()) <= limit:
            raise CMSFailure("INVALID_RIGHTS_SCOPE", 400)
    if data["material"] != "text" or data["intended_use"] != "public_display":
        raise CMSFailure("INVALID_RIGHTS_SCOPE", 400)
    today = timezone.localdate()
    for field in ("review_on", "expires_on"):
        value = data[field]
        if value is not None:
            if type(value) is not str:
                raise CMSFailure("INVALID_RIGHTS_DATES", 400)
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                raise CMSFailure("INVALID_RIGHTS_DATES", 400)
            if parsed.isoformat() != value or parsed <= today:
                raise CMSFailure("INVALID_RIGHTS_DATES", 400)
    if data["review_on"] is None:
        raise CMSFailure("RIGHTS_REVIEW_DATE_REQUIRED", 400)
    return {k: data[k].strip() if isinstance(data[k], str) and k not in
            ("review_on", "expires_on") else data[k] for k in RIGHTS_FIELDS}


def _actor(actor_id, session_id, capability):
    actor = get_user_model().objects.get(pk=actor_id)
    current_session(session_id, actor)
    require(actor, "cms_cases_view")
    require(actor, capability)
    return actor


def _author_ids(case, revision):
    return set(AdminAuditEvent.objects.filter(
        target_kind="clinical-case", target_id=case.pk, new_revision=revision.version,
        action__in=("case.draft_created", "case.draft_cloned", "case.draft_updated", "case.graph_updated"),
        actor_id__isnull=False).values_list("actor_id", flat=True))


def _reviewer_check(actor, case, revision, policy, acknowledgement):
    if acknowledgement is not True:
        raise CMSFailure("REVIEW_ACK_REQUIRED", 400)
    if actor.pk in _author_ids(case, revision):
        class Subject:
            authors = [actor.pk]
        reviewer_conflict(actor, Subject(), policy)


def _review_status(revision, lock=True):
    policy = current_policy()
    digest = case_revision_fingerprint(revision)
    latest = {}
    for row in CasePublicationReview.objects.filter(revision=revision).order_by("-pk"):
        latest.setdefault(row.kind, row)
    blockers = []
    for kind in KINDS:
        review = latest.get(kind)
        if review is None or review.outcome != "approved":
            blockers.append(kind.upper() + "_REVIEW_REQUIRED")
            continue
        if review.revision_digest != digest:
            blockers.append(kind.upper() + "_CONTENT_CHANGED")
        if review.policy_version != policy.version or review.policy_mode != policy.mode:
            blockers.append("POLICY_CHANGED")
        reviewer = get_user_model().objects.filter(pk=review.actor_id, is_active=True, is_staff=True).first()
        required = {"cms_enter", "cms_cases_view", PERMISSIONS[kind]}
        if kind == "rights":
            required.add("cms_rights_decide")
        if reviewer is None or not required <= effective_permissions(reviewer):
            blockers.append("REVIEWER_PERMISSION_CHANGED")
        try:
            if _source_dependency(review.evidence, lock=lock) != review.source_digest:
                blockers.append("SOURCE_DEPENDENCY_CHANGED")
        except CMSFailure:
            blockers.append("SOURCE_UNAVAILABLE")
        if kind == "rights":
            try:
                rights = review.rights
                if (rights.get("review_on") is None or date.fromisoformat(rights["review_on"]) <= timezone.localdate()
                        or (rights.get("expires_on") and date.fromisoformat(rights["expires_on"]) <= timezone.localdate())):
                    blockers.append("RIGHTS_EXPIRED_OR_REVIEW_OVERDUE")
            except (ValueError, TypeError, KeyError, AttributeError):
                blockers.append("RIGHTS_SCOPE_INVALID")
    if policy.mode == "two_person" and len(latest) == 3:
        if len({item.actor_id for item in latest.values()}) < 2:
            blockers.append("TWO_PERSON_REQUIRED")
        if any(item.actor_id in _author_ids(revision.case, revision) for item in latest.values()):
            blockers.append("TWO_PERSON_REQUIRED")
    return sorted(set(blockers)), latest


def review_revision(actor_id, session_id, case_id, revision_id, expected, data, request_id):
    kind = data.get("kind")
    if kind not in KINDS or set(data) - {"kind", "outcome", "evidence", "rights", "self_review_ack"}:
        raise CMSFailure("INVALID_FIELDS", 400)
    outcome = data.get("outcome")
    if outcome not in ("approved", "revoked"):
        raise CMSFailure("INVALID_DECISION", 400)
    with policy_lock() as role:
        actor = _actor(actor_id, session_id, PERMISSIONS[kind])
        if kind == "rights":
            require(actor, "cms_rights_decide" if outcome == "approved" else "cms_rights_revoke")
        case, revision = _lock_revision(case_id, revision_id)
        if revision_etag(revision) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        policy = current_policy()
        _reviewer_check(actor, case, revision, policy, data.get("self_review_ack"))
        rights = _rights(data.get("rights")) if kind == "rights" and outcome == "approved" else {}
        if outcome == "approved":
            _candidate(case, revision)
            evidence = _evidence(data.get("evidence"))
            if kind != "rights" and data.get("rights") not in (None, {}):
                raise CMSFailure("INVALID_FIELDS", 400)
            if kind in ("scientific", "rights"):
                existing_blockers, latest = _review_status(revision)
                if "source" not in latest or latest["source"].outcome != "approved":
                    raise CMSFailure("SOURCE_REVIEW_REQUIRED", 409)
                if any(b in existing_blockers for b in ("SOURCE_CONTENT_CHANGED", "SOURCE_DEPENDENCY_CHANGED", "SOURCE_UNAVAILABLE", "POLICY_CHANGED")):
                    raise CMSFailure("SOURCE_REVIEW_STALE", 409)
        else:
            if data.get("evidence") not in (None, []) or data.get("rights") not in (None, {}):
                raise CMSFailure("INVALID_FIELDS", 400)
            if not CasePublicationReview.objects.filter(revision=revision, kind=kind).exists():
                raise CMSFailure("REVIEW_NOT_FOUND", 404)
            evidence = []
        decision = CasePublicationReview.objects.create(
            revision=revision, kind=kind, outcome=outcome,
            revision_digest=case_revision_fingerprint(revision),
            source_digest=_source_dependency(evidence) if evidence else _digest({}),
            evidence=evidence, rights=rights, policy_version=policy.version,
            policy_mode=policy.mode, actor=actor, actor_ref=attribution(actor.pk),
            self_review=actor.pk in _author_ids(case, revision),
        )
        if outcome == "revoked" and case.current_revision_id == revision.pk and case.is_active:
            case.is_active = False
            case.save(update_fields=["is_active", "updated_at"])
            last = CasePublicationPlan.objects.filter(revision=revision, status="applied").order_by("-created_at").first()
            if last:
                _withdraw_applied(last, actor, request_id)
        AdminAuditEvent.objects.create(actor=actor, action="case.review_decided",
            outcome="success", target_kind="clinical-case", target_id=case.pk,
            new_revision=revision.version, request_id=request_id, reason="CONTENT_UPDATE")
        return decision


def _manifest(case, revision, latest):
    policy = current_policy()
    return {
        "schema": "case-publication-v1", "case_id": case.pk, "revision_id": revision.pk,
        "revision_version": revision.version,
        "revision_digest": case_revision_fingerprint(revision),
        "previous_revision_id": case.current_revision_id,
        "policy_version": policy.version, "policy_mode": policy.mode,
        "review_ids": {kind: latest[kind].pk for kind in KINDS},
        "source_digests": {kind: latest[kind].source_digest for kind in KINDS},
        "action": "activate_case_revision",
    }


def _reinstatement_ready(case, revision):
    """A withdrawn revision may return only as itself, never as a new draft."""
    if (revision.seed_managed or case.seed_managed
            or revision.status != CaseRevision.Status.PUBLISHED
            or case.current_revision_id != revision.pk or case.is_active):
        raise CMSFailure("REVISION_NOT_REINSTATEABLE", 409)


def _reinstatement_manifest(case, revision, latest, withdrawn):
    policy = current_policy()
    receipt = withdrawn.receipts.filter(event_type="withdrawn").first()
    if receipt is None:
        raise CMSFailure("REINSTATEMENT_SOURCE_CHANGED", 409)
    return {
        "schema": "case-publication-v1", "case_id": case.pk, "revision_id": revision.pk,
        "revision_version": revision.version,
        "revision_digest": case_revision_fingerprint(revision),
        "previous_revision_id": case.current_revision_id,
        "policy_version": policy.version, "policy_mode": policy.mode,
        "review_ids": {kind: latest[kind].pk for kind in KINDS},
        "source_digests": {kind: latest[kind].source_digest for kind in KINDS},
        "action": "reinstate_case_revision",
        "reinstates_plan_id": str(withdrawn.pk),
        "reinstates_withdrawal_receipt_id": receipt.pk,
    }


def freeze_revision(actor_id, session_id, case_id, revision_id, expected, request_id):
    with policy_lock():
        actor = _actor(actor_id, session_id, "cms_publication_freeze_cases")
        case, revision = _lock_revision(case_id, revision_id)
        if revision_etag(revision) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        _candidate(case, revision)
        blockers, latest = _review_status(revision)
        if blockers:
            failure = CMSFailure("PUBLICATION_BLOCKED", 409)
            failure.detail["blockers"] = blockers
            raise failure
        manifest = _manifest(case, revision, latest)
        plan = CasePublicationPlan.objects.create(revision=revision,
            previous_revision_id=case.current_revision_id, manifest=manifest,
            manifest_digest=_digest(manifest), created_by=actor)
        AdminAuditEvent.objects.create(actor=actor, action="case.publication_frozen",
            outcome="success", target_kind="clinical-case", target_id=case.pk,
            new_revision=revision.version, request_id=request_id, reason="CONTENT_UPDATE")
        return plan


def _verify_plan(plan):
    case, revision = _lock_revision(plan.revision.case_id, plan.revision_id)
    reinstatement = plan.manifest.get("action") == "reinstate_case_revision"
    withdrawn = None
    if reinstatement:
        _reinstatement_ready(case, revision)
        try:
            withdrawn_id = uuid.UUID(str(plan.manifest.get("reinstates_plan_id")))
        except (TypeError, ValueError, AttributeError):
            raise CMSFailure("REINSTATEMENT_SOURCE_CHANGED", 409)
        withdrawn = CasePublicationPlan.objects.filter(
            pk=withdrawn_id, revision=revision, status="withdrawn").first()
        if withdrawn is None:
            raise CMSFailure("REINSTATEMENT_SOURCE_CHANGED", 409)
    else:
        _candidate(case, revision)
    blockers, latest = _review_status(revision)
    if blockers:
        failure = CMSFailure("PUBLICATION_BLOCKED", 409)
        failure.detail["blockers"] = blockers
        raise failure
    approver = get_user_model().objects.filter(pk=plan.approved_by_id, is_active=True, is_staff=True).first() if plan.approved_by_id else None
    if plan.status == "approved" and (approver is None or
            not {"cms_enter", "cms_cases_view", "cms_publication_approve_cases"} <= effective_permissions(approver)):
        raise CMSFailure("APPROVER_PERMISSION_CHANGED", 409)
    manifest = (_reinstatement_manifest(case, revision, latest, withdrawn)
                if reinstatement else _manifest(case, revision, latest))
    if _digest(manifest) != plan.manifest_digest or manifest != plan.manifest:
        raise CMSFailure("MANIFEST_STALE", 412)
    return case, revision


def approve_plan(actor_id, session_id, plan_id, expected_digest, acknowledgement, request_id):
    with policy_lock():
        actor = _actor(actor_id, session_id, "cms_publication_approve_cases")
        plan = CasePublicationPlan.objects.select_for_update().select_related("revision").filter(pk=plan_id).first()
        if plan is None:
            raise CMSFailure("NOT_FOUND", 404)
        if expected_digest != plan.manifest_digest:
            raise CMSFailure("MANIFEST_STALE", 412)
        if plan.status != "frozen":
            raise CMSFailure("INVALID_TRANSITION", 409)
        policy = current_policy()
        if acknowledgement is not True:
            raise CMSFailure("REVIEW_ACK_REQUIRED", 400)
        if (policy.mode == "two_person" and actor.pk == plan.created_by_id) or (
                policy.mode == "solo_owner" and actor.pk == plan.created_by_id
                and "cms_owner" not in effective_permissions(actor)):
            raise CMSFailure("TWO_PERSON_REQUIRED", 409)
        case, revision = _verify_plan(plan)
        plan.status, plan.approved_by, plan.approved_at = "approved", actor, timezone.now()
        plan.save(update_fields=["status", "approved_by", "approved_at"])
        AdminAuditEvent.objects.create(actor=actor, action="case.publication_approved",
            outcome="success", target_kind="clinical-case", target_id=case.pk,
            new_revision=revision.version, request_id=request_id, reason="CONTENT_UPDATE")
        return plan


def _receipt(plan, actor, operation, previous, key):
    return CasePublicationReceipt.objects.create(
        plan=plan, event_type=operation, revision=plan.revision,
        previous_revision_id=previous, manifest_digest=plan.manifest_digest,
        actor=actor, actor_ref=attribution(actor.pk),
        idempotency_key=key,
    )


def apply_plan(actor_id, session_id, plan_id, expected_digest, key, request_id):
    try:
        key = uuid.UUID(key)
    except (AttributeError, TypeError, ValueError):
        raise CMSFailure("INVALID_IDEMPOTENCY_KEY", 400)
    with policy_lock():
        actor = _actor(actor_id, session_id, "cms_publication_apply_cases")
        plan = CasePublicationPlan.objects.select_for_update().select_related("revision").filter(pk=plan_id).first()
        if plan is None:
            raise CMSFailure("NOT_FOUND", 404)
        if expected_digest != plan.manifest_digest:
            raise CMSFailure("MANIFEST_STALE", 412)
        existing = plan.receipts.filter(event_type="applied").first()
        if existing:
            if plan.status == "withdrawn":
                raise CMSFailure("ALREADY_WITHDRAWN", 409)
            if existing.idempotency_key != key:
                raise CMSFailure("ALREADY_APPLIED", 409)
            return existing, False
        if plan.status != "approved":
            raise CMSFailure("APPROVAL_REQUIRED", 409)
        case, revision = _verify_plan(plan)
        consume_step_up(session_id, actor, "case_publish", revision.pk,
                        {"manifest_digest":plan.manifest_digest})
        if plan.approved_by_id == actor.pk and current_policy().mode == "two_person":
            raise CMSFailure("TWO_PERSON_REQUIRED", 409)
        previous = case.current_revision_id
        if revision.status != CaseRevision.Status.PUBLISHED:
            # A reinstatement restores the original publication timestamp; it
            # must not rewrite the historical record of when the text went live.
            revision.status, revision.published_at = CaseRevision.Status.PUBLISHED, timezone.now()
            revision.save(update_fields=["status", "published_at", "updated_at"])
        for name in ("title", "patient_summary", "educational_objective", "difficulty", "primary_disorder_id"):
            setattr(case, name, getattr(revision, name))
        case.current_revision = revision
        case.is_active = True
        case.save(update_fields=["title", "patient_summary", "educational_objective",
                                 "difficulty", "primary_disorder", "current_revision",
                                 "is_active", "updated_at"])
        plan.status, plan.applied_at = "applied", timezone.now()
        plan.save(update_fields=["status", "applied_at"])
        receipt = _receipt(plan, actor, "applied", previous, key)
        AdminAuditEvent.objects.create(actor=actor, action="case.publication_applied",
            outcome="success", target_kind="clinical-case", target_id=case.pk,
            new_revision=revision.version, request_id=request_id, reason="CONTENT_UPDATE")
        return receipt, True


def _withdraw_applied(plan, actor, request_id, key=None):
    if plan.receipts.filter(event_type="withdrawn").exists():
        return plan.receipts.get(event_type="withdrawn")
    receipt = _receipt(plan, actor, "withdrawn", plan.previous_revision_id, key or uuid.uuid4())
    plan.status = "withdrawn"
    plan.save(update_fields=["status"])
    AdminAuditEvent.objects.create(actor=actor, action="case.publication_withdrawn",
        outcome="success", target_kind="clinical-case", target_id=plan.revision.case_id,
        new_revision=plan.revision.version, request_id=request_id, reason="CONTENT_UPDATE")
    return receipt


def withdraw_plan(actor_id, session_id, plan_id, expected_digest, key, request_id):
    try:
        key = uuid.UUID(key)
    except (AttributeError, TypeError, ValueError):
        raise CMSFailure("INVALID_IDEMPOTENCY_KEY", 400)
    with policy_lock():
        actor = _actor(actor_id, session_id, "cms_publication_withdraw_cases")
        plan = CasePublicationPlan.objects.select_for_update().select_related("revision").filter(pk=plan_id).first()
        if plan is None:
            raise CMSFailure("NOT_FOUND", 404)
        if expected_digest != plan.manifest_digest:
            raise CMSFailure("MANIFEST_STALE", 412)
        receipt = plan.receipts.filter(event_type="withdrawn").first()
        if receipt:
            if receipt.idempotency_key != key:
                raise CMSFailure("ALREADY_WITHDRAWN", 409)
            return receipt, False
        if plan.status != "applied":
            raise CMSFailure("INVALID_TRANSITION", 409)
        case, revision = _lock_revision(plan.revision.case_id, plan.revision_id)
        if case.current_revision_id != revision.pk:
            raise CMSFailure("NOT_CURRENT_REVISION", 409)
        consume_step_up(session_id, actor, "case_withdraw", revision.pk,
                        {"manifest_digest":plan.manifest_digest})
        case.is_active = False
        case.save(update_fields=["is_active", "updated_at"])
        return _withdraw_applied(plan, actor, request_id, key), True


def reinstate_plan(actor_id, session_id, plan_id, expected_digest, request_id):
    """Freeze a fresh, separately approved plan for a withdrawn revision.

    Reinstatement never reuses the earlier approval: it creates a new frozen
    plan bound to the withdrawal receipt, which must pass approve + MFA apply.
    """
    with policy_lock():
        actor = _actor(actor_id, session_id, "cms_publication_reinstate_cases")
        prior = CasePublicationPlan.objects.select_for_update().select_related("revision").filter(pk=plan_id).first()
        if prior is None:
            raise CMSFailure("NOT_FOUND", 404)
        if expected_digest != prior.manifest_digest:
            raise CMSFailure("MANIFEST_STALE", 412)
        if prior.status != "withdrawn":
            raise CMSFailure("INVALID_TRANSITION", 409)
        case, revision = _lock_revision(prior.revision.case_id, prior.revision_id)
        _reinstatement_ready(case, revision)
        blockers, latest = _review_status(revision)
        if blockers:
            failure = CMSFailure("PUBLICATION_BLOCKED", 409)
            failure.detail["blockers"] = blockers
            raise failure
        manifest = _reinstatement_manifest(case, revision, latest, prior)
        manifest_digest = _digest(manifest)
        existing = CasePublicationPlan.objects.filter(
            manifest_digest=manifest_digest,
            status__in=("frozen", "approved", "applied")).first()
        if existing is not None:
            return existing, False
        plan = CasePublicationPlan.objects.create(revision=revision,
            previous_revision_id=case.current_revision_id, manifest=manifest,
            manifest_digest=manifest_digest, created_by=actor)
        AdminAuditEvent.objects.create(actor=actor, action="case.publication_reinstatement_frozen",
            outcome="success", target_kind="clinical-case", target_id=case.pk,
            new_revision=revision.version, request_id=request_id, reason="CONTENT_UPDATE")
        return plan, True


def detail_plan(actor_id, session_id, plan_id):
    with policy_lock():
        actor = _actor(actor_id, session_id, "cms_publication_verify_cases")
        plan = CasePublicationPlan.objects.select_related("revision").filter(pk=plan_id).first()
        if plan is None:
            raise CMSFailure("NOT_FOUND", 404)
        receipts = list(plan.receipts.order_by("pk").values(
            "id", "event_type", "manifest_digest", "previous_revision_id", "revision_id", "created_at"))
        return {"id": str(plan.pk), "case_id": plan.revision.case_id,
            "revision_id": plan.revision_id, "manifest_digest": plan.manifest_digest,
            "manifest": plan.manifest, "status": plan.status,
            "approved_at": plan.approved_at, "applied_at": plan.applied_at,
            "receipts": receipts}


def current_publication_allowed(case):
    """Fail closed on stale P16-reviewed current case, without changing legacy pins.

    Read-only and uncached: source/rights revisions and expiry must take effect
    on the very next public request. An in-progress learner attempt remains
    pinned to its earlier historical revision.
    """
    if not case.current_revision_id:
        return False
    revisions = CasePublicationPlan.objects.filter(
        revision_id=case.current_revision_id).select_related("revision").order_by("-created_at", "-pk")
    plans = list(revisions)
    if not plans:
        return True  # Historical seed publication has separate legacy gates.
    for plan in plans:
        if plan.status != "applied":
            continue
        if (plan.manifest_digest != _digest(plan.manifest)
                or plan.manifest.get("revision_id") != case.current_revision_id):
            continue
        try:
            blockers, latest = _review_status(plan.revision, lock=False)
            if blockers:
                continue
            if (plan.manifest.get("revision_digest") != case_revision_fingerprint(plan.revision)
                    or any(plan.manifest.get("review_ids", {}).get(kind) != latest[kind].pk
                           for kind in KINDS)):
                continue
            approver = get_user_model().objects.filter(pk=plan.approved_by_id,
                is_active=True,is_staff=True).first()
            if approver is None or not {"cms_enter","cms_cases_view","cms_publication_approve_cases"} <= effective_permissions(approver):
                continue
            return True
        except (CMSFailure, KeyError):
            continue
    return False


def blocked_current_case_ids():
    """Exclude stale P16 records from public list/detail/start selectors."""
    from django.db.models import F
    plans = CasePublicationPlan.objects.filter(
        revision__case__current_revision_id=F("revision_id"),
    ).select_related("revision", "revision__case").order_by("-created_at", "-pk")
    cases = {}
    for plan in plans:
        cases.setdefault(plan.revision.case_id, plan.revision.case)
    return [case_id for case_id, case in cases.items()
            if not current_publication_allowed(case)]


def review_details(actor_id, session_id, case_id, revision_id):
    with policy_lock():
        _actor(actor_id, session_id, "cms_cases_validate")
        case, revision = _lock_revision(case_id, revision_id)
        blockers, latest = _review_status(revision)
        return {"case_id": case.pk, "revision_id": revision.pk,
            "revision_digest": case_revision_fingerprint(revision),
            "review_blockers": blockers,
            "plans": [{"id": str(plan.pk), "status": plan.status,
                       "manifest_digest": plan.manifest_digest, "created_at": plan.created_at}
                      for plan in CasePublicationPlan.objects.filter(revision=revision)
                      .order_by("-created_at", "-pk")[:30]],
            "reviews": {kind: {"id": row.pk, "outcome": row.outcome,
                               "revision_digest": row.revision_digest,
                               "actor_ref": row.actor_ref, "created_at": row.created_at,
                               "policy_version": row.policy_version}
                        for kind, row in latest.items()}}
