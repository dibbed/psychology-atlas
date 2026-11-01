"""P04 review workflow. Decisions authorize an exact proposal, never a public write."""
from django.contrib.auth.models import User
from django.db.models import F
from rest_framework.exceptions import ValidationError

from .brain_publication import source_is_resolved
from .cms_audit import POLICY_REASONS, REVIEW_REASONS, attribution
from .cms_content import canonical_snapshot, capability, dependencies, digest, kind_entry, resolve, require_references
from .cms_domains import dependency_snapshot, domain_for, required_reference_capabilities, validate_snapshot
from .cms_content_models import ContentRevision, ContentState
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_review_models import ReviewDecision, ReviewPolicy, ReviewPolicyRevision, ReviewTask
from .cms_sessions import consume_step_up, current_session
from .models import Category, DisorderSource, ScientificReviewStatus, SourceReference, lock_brain_curation
from django.db import connection


def policy_data(policy):
    return {"scope": "core", "mode": policy.mode, "version": policy.version}


def current_policy():
    return ReviewPolicy.objects.get(pk=1)


def review_capability(review_type, kind="category"):
    if review_type not in ReviewTask.Type.values:
        raise CMSFailure("INVALID_REVIEW_TYPE", 400)
    return "cms_review_decide_%s_%s" % (domain_for(kind), review_type)


def subject_hash(subject):
    value = {"id": subject.pk, "payload": subject.payload, "base": subject.base_digest, "schema": subject.schema_version}
    if subject.schema_version >= 2 or subject.intent != "edit":
        value.update({"kind": subject.state.kind, "intent": subject.intent, "dependency": subject.dependency_digest})
    return digest(value)


def checked_evidence(kind, payload, evidence):
    fields = set(kind_entry(kind)[1]().fields)
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 20:
        raise CMSFailure("EVIDENCE_REQUIRED", 400)
    result = []
    for item in evidence:
        if (not isinstance(item, dict) or set(item) != {"source_id", "locator", "fields"}
                or type(item["source_id"]) is not int or not 1 <= item["source_id"] <= 2**63 - 1
                or not isinstance(item["locator"], str) or not 1 <= len(item["locator"].strip()) <= 1000
                or not isinstance(item["fields"], list) or not item["fields"]
                or any(type(k) is not str or k not in fields for k in item["fields"])):
            raise CMSFailure("INVALID_EVIDENCE", 400)
        result.append({"source_id": item["source_id"], "locator": item["locator"].strip(), "fields": sorted(set(item["fields"]))})
    covered = {k for item in result for k in item["fields"]}
    if any(value and key not in covered for key, value in payload.items()):
        raise CMSFailure("EVIDENCE_COVERAGE_REQUIRED", 400)
    if SourceReference.objects.filter(pk__in={item["source_id"] for item in result}).count() != len({item["source_id"] for item in result}):
        raise CMSFailure("INVALID_EVIDENCE", 400)
    from .cms_source_models import SourceState
    from django.db.models import Q
    if SourceState.objects.filter(source_pk__in={item["source_id"] for item in result}).filter(Q(archived=True) | Q(deleted=True)).exists():
        raise CMSFailure("SOURCE_UNAVAILABLE", 400)
    return result


def dependency_hash(kind, obj, evidence, lock=False, payload=None, intent="edit", schema_version=1):
    # The existing source writer uses this lock; publication must reuse this check under the same boundary.
    if lock:
        lock_brain_curation(connection.alias)
    links = DisorderSource.objects.filter(disorder=obj).order_by("pk") if kind == "disorder" and obj is not None else DisorderSource.objects.none()
    if lock:
        links = links.select_for_update()
    links = list(links.values("id", "source_id", "note"))
    source_ids = {item["source_id"] for item in evidence} | {item["source_id"] for item in links}
    sources = SourceReference.objects.filter(pk__in=source_ids).order_by("pk")
    if lock:
        sources = sources.select_for_update()
        if kind == "disorder" and obj is not None:
            Category.objects.select_for_update().get(pk=obj.category_id)
    sources = list(sources)
    snapshot = [{field.name: getattr(source, field.name) for field in source._meta.concrete_fields
        if field.name not in {"created_at", "updated_at"}} for source in sources]
    from .cms_governance import governance_dependency_snapshot
    from .cms_source_models import SourceState, SourceSuccessor
    lifecycle = list(SourceState.objects.filter(source_pk__in=source_ids).order_by("source_pk").values(
        "source_pk", "version", "resource_version", "archived", "deleted"))
    successors = list(SourceSuccessor.objects.filter(source_pk__in=source_ids).order_by("pk").values(
        "source_pk", "successor_pk", "operation"))
    governance = governance_dependency_snapshot(source_ids, lock=lock,
        resource_type=kind.replace("-", "_") if obj is not None else None, resource_id=obj.pk if obj is not None else None)
    value = {"parent": dependencies(kind, obj), "source_links": links, "sources": snapshot, "evidence": evidence,
        "source_lifecycle": lifecycle, "successors": successors, "governance": governance}
    if schema_version >= 2:
        value.update({"typed": dependency_snapshot(kind, obj, payload, lock), "intent": intent})
    return digest(value), sources


def latest_tasks(state):
    latest = ReviewTask.objects.filter(subject__state=state).order_by("-subject__sequence").first()
    return list(ReviewTask.objects.filter(subject=latest.subject).select_related("subject", "assignee").order_by("review_type")) if latest else []


def freshness(state, obj, tasks, policy, lock=False):
    if not tasks:
        return ["REVIEW_REQUIRED"]
    subject = tasks[0].subject
    blockers = []
    if any(t.policy_version != policy.version or t.policy_mode != policy.mode for t in tasks):
        blockers.append("POLICY_CHANGED")
    canonical = digest(canonical_snapshot(state.kind, obj)) if obj else digest({})
    if canonical != subject.base_digest or canonical != state.canonical_digest:
        blockers.append("CANONICAL_RECONCILIATION_REQUIRED")
    if subject.schema_version >= 2:
        try:
            validate_snapshot(state.kind, subject.payload, obj)
        except ValidationError:
            blockers.append("SNAPSHOT_INVALID")
    try:
        dependency, sources = dependency_hash(state.kind, obj, tasks[0].evidence, lock, subject.payload, subject.intent, subject.schema_version)
    except ValidationError:
        return sorted(set([*blockers, "DEPENDENCY_CHANGED"]))
    if not {item["source_id"] for item in tasks[0].evidence} <= {source.pk for source in sources}:
        blockers.append("EVIDENCE_MISSING")
    if any(t.dependency_digest != dependency for t in tasks):
        blockers.append("DEPENDENCY_CHANGED")
    if (subject.payload_digest != digest(subject.payload) or any(t.revision_hash != subject_hash(subject) for t in tasks)
            or state.current_revision.payload_digest != subject.payload_digest
            or state.current_revision.payload != subject.payload or state.current_revision.intent != subject.intent):
        blockers.append("PAYLOAD_CHANGED")
    if state.current_revision.status not in {"submitted", "in_review", "approved"}:
        blockers.append("REVIEW_NOT_CURRENT")
    for task in tasks:
        if task.status == "approved" and task.assignee is not None:
            if not {"cms_enter", capability(state.kind, "view"), review_capability(task.review_type, state.kind),
                    *required_reference_capabilities(state.kind, subject.payload)} <= effective_permissions(task.assignee):
                blockers.append("REVIEWER_PERMISSION_CHANGED")
        elif task.status == "approved":
            blockers.append("REVIEWER_UNAVAILABLE")
        if task.status == "approved":
            decision = task.decisions.order_by("-pk").first()
            if (decision is None or decision.outcome != "approve" or decision.actor_id != task.assignee_id
                    or decision.revision_hash != task.revision_hash or decision.dependency_digest != task.dependency_digest
                    or decision.policy_version != task.policy_version or decision.evidence != task.evidence):
                blockers.append("DECISION_REQUIRED")
            if task.assignee is not None:
                try:
                    reviewer_conflict(task.assignee, task, policy)
                except CMSFailure as error:
                    blockers.append(str(error.detail["code"]))
    return sorted(set(blockers))


def approval_eligibility(state, obj, lock=False):
    tasks = latest_tasks(state)
    blockers = freshness(state, obj, tasks, current_policy(), lock)
    if state.current_revision.status != "approved" or len(tasks) != 2 or any(t.status != "approved" for t in tasks):
        blockers.append("APPROVAL_REQUIRED")
    return {"eligible": not blockers, "blockers": sorted(set(blockers))}


def review_data(state, obj):
    from .cms_content import revision_data
    tasks = latest_tasks(state)
    policy = current_policy()
    blockers = freshness(state, obj, tasks, policy)
    status = ScientificReviewStatus.UNREVIEWED
    if not blockers:
        if all(t.status == "approved" for t in tasks) and state.current_revision.status == "approved":
            status = ScientificReviewStatus.REVIEWED
        elif any(t.review_type == "source" and t.status == "approved" for t in tasks):
            status = ScientificReviewStatus.SOURCE_CHECKED
    # Match the existing public selectors; review of a proposal does not change these gates.
    public = None
    gate = "canonical_domain_selector"
    if obj is not None and hasattr(obj, "is_active"):
        public = bool(obj.is_active and (state.kind != "category" or obj.disorders.filter(is_active=True).exists()))
        gate = "is_active + active_disorder" if state.kind == "category" else "is_active"
    return {"record": revision_data(state, obj), "policy": policy_data(policy), "scientific_status": status,
        "approval": approval_eligibility(state, obj), "canonical_public_eligible": public,
        "public_gate": gate, "evidence": tasks[0].evidence if tasks else [],
        "tasks": [{"id": t.pk, "review_type": t.review_type, "status": t.status, "version": t.version,
            "assignee_id": t.assignee_id, "assignee": t.assignee.username if t.assignee else None,
            "subject_revision": t.subject_id, "revision_hash": t.revision_hash, "dependency_digest": t.dependency_digest,
            "policy_version": t.policy_version} for t in tasks]}


def context(actor_id, session_id, kind, target_id, expected, capability):
    actor = User.objects.get(pk=actor_id)
    current_session(session_id, actor)
    kind_entry(kind)
    require(actor, "cms_%s_%s" % (domain_for(kind), capability.removeprefix("cms_core_")))
    state, obj = resolve(actor, kind, target_id, lock=True)
    if state.version != expected:
        raise CMSFailure("STALE_REVISION", 412)
    return actor, state, obj


def advance(state, actor, status, dependency):
    old = state.current_revision
    new = ContentRevision.objects.create(state=state, sequence=state.version + 1, base_version=state.version,
        base_digest=old.base_digest, payload=old.payload, payload_digest=old.payload_digest,
        dependency_digest=dependency, schema_version=old.schema_version, intent=old.intent, status=status, actor=actor)
    if ContentState.objects.filter(pk=state.pk, version=state.version).update(version=F("version") + 1, current_revision=new) != 1:
        raise CMSFailure("STALE_REVISION", 412)
    state.refresh_from_db()
    return new


def audit(actor, state, action, reason, request_id, policy):
    AdminAuditEvent.objects.create(actor=actor, action=action, outcome="success", target_kind=state.kind,
        target_key=str(state.pk), base_revision=state.version - 1, new_revision=state.version,
        reason=reason, request_id=request_id, policy_version=policy.version)


def submit_review(actor_id, session_id, kind, target_id, expected, evidence, request_id):
    with policy_lock():
        actor, state, obj = context(actor_id, session_id, kind, target_id, expected, "cms_core_submit")
        if state.current_revision.status != "draft":
            raise CMSFailure("INVALID_TRANSITION", 409)
        subject = state.current_revision
        require_references(actor, kind, subject.payload)
        validate_snapshot(kind, subject.payload, obj)
        if (digest(canonical_snapshot(kind, obj)) if obj else digest({})) != state.canonical_digest:
            raise CMSFailure("CANONICAL_RECONCILIATION_REQUIRED", 409)
        evidence = checked_evidence(kind, subject.payload, evidence)
        dependency, sources = dependency_hash(kind, obj, evidence, lock=True, payload=subject.payload, intent=subject.intent, schema_version=subject.schema_version)
        if not {item["source_id"] for item in evidence} <= {source.pk for source in sources}:
            raise CMSFailure("INVALID_EVIDENCE", 400)
        policy = current_policy()
        authors = list(state.revisions.filter(status="draft", actor__isnull=False).values_list("actor_id", flat=True).distinct())
        for review_type in ReviewTask.Type.values:
            ReviewTask.objects.create(subject=subject, review_type=review_type, revision_hash=subject_hash(subject),
                dependency_digest=dependency, evidence=evidence, authors=authors, policy_version=policy.version, policy_mode=policy.mode)
        advance(state, actor, "submitted", dependency)
        audit(actor, state, "review.submitted", "REVIEW_SUBMIT", request_id, policy)
        return state


def reviewer_conflict(reviewer, task, policy):
    if reviewer.pk in task.authors:
        if policy.mode == "two_person":
            raise CMSFailure("TWO_PERSON_REQUIRED", 409)
        if "cms_owner" not in effective_permissions(reviewer):
            raise CMSFailure("REVIEWER_CONFLICT", 409)


def task_context(actor_id, session_id, kind, target_id, expected, task_id, task_version):
    actor, state, obj = context(actor_id, session_id, kind, target_id, expected, "cms_core_view")
    tasks = latest_tasks(state)
    task = next((t for t in tasks if type(task_id) is int and t.pk == task_id), None)
    if task is None:
        raise CMSFailure("NOT_FOUND", 404)
    require(actor, review_capability(task.review_type, kind))
    if type(task_version) is not int or task.version != task_version:
        raise CMSFailure("STALE_DECISION", 412)
    if state.current_revision.status not in {"submitted", "in_review"} or task.status not in {"queued", "assigned"}:
        raise CMSFailure("INVALID_TRANSITION", 409)
    policy = current_policy()
    blockers = freshness(state, obj, tasks, policy, lock=True)
    if blockers:
        error = CMSFailure("STALE_DECISION", 409)
        error.detail["blockers"] = blockers
        raise error
    return actor, state, obj, task, tasks, policy


def decision_record(actor, state, task, outcome, reason, policy, fields=(), self_review=False):
    previous = task.decisions.order_by("-pk").first()
    return ReviewDecision.objects.create(task=task, revision=state.current_revision, actor=actor,
        actor_ref=attribution(actor.pk), assignee_ref=attribution(task.assignee_id), outcome=outcome, reason=reason,
        fields=list(fields), evidence=task.evidence, revision_hash=task.revision_hash,
        dependency_digest=task.dependency_digest, policy_version=policy.version, policy_mode=policy.mode,
        self_review=self_review, supersedes=previous)


def assign_review(actor_id, session_id, kind, target_id, expected, task_id, task_version, reviewer_id, request_id):
    with policy_lock():
        actor, state, _, task, _, policy = task_context(actor_id, session_id, kind, target_id, expected, task_id, task_version)
        if type(reviewer_id) is not int:
            raise CMSFailure("INVALID_REVIEWER", 400)
        reviewer = User.objects.filter(pk=reviewer_id, is_active=True, is_staff=True).first()
        if reviewer is None or not {"cms_enter", capability(state.kind, "view"), review_capability(task.review_type, state.kind),
                *required_reference_capabilities(kind, state.current_revision.payload)} <= effective_permissions(reviewer):
            raise CMSFailure("INVALID_REVIEWER", 400)
        reviewer_conflict(reviewer, task, policy)
        task.assignee, task.status, task.version = reviewer, "assigned", task.version + 1
        task.save(update_fields=("assignee", "status", "version"))
        advance(state, actor, "in_review", task.dependency_digest)
        decision_record(actor, state, task, "assigned", "REVIEW_ASSIGN", policy)
        audit(actor, state, "review.assigned", "REVIEW_ASSIGN", request_id, policy)
        return state


def decide_review(actor_id, session_id, kind, target_id, expected, task_id, task_version, outcome, reason, fields, self_review_ack, request_id):
    with policy_lock():
        actor, state, _, task, tasks, policy = task_context(actor_id, session_id, kind, target_id, expected, task_id, task_version)
        if state.current_revision.status != "in_review" or task.status != "assigned" or task.assignee_id != actor.pk:
            raise CMSFailure("REVIEWER_CONFLICT", 409)
        reviewer_conflict(actor, task, policy)
        self_review = actor.pk in task.authors
        if type(self_review_ack) is not bool or (self_review and not self_review_ack):
            raise CMSFailure("SELF_REVIEW_ACK_REQUIRED", 400)
        if type(outcome) is not str or outcome not in {"approve", "reject"}:
            raise CMSFailure("INVALID_DECISION", 400)
        if not isinstance(fields, list) or any(type(k) is not str or k not in kind_entry(kind)[1]().fields for k in fields):
            raise CMSFailure("INVALID_FIELDS", 400)
        if outcome == "reject":
            if type(reason) is not str or reason not in REVIEW_REASONS or not fields:
                raise CMSFailure("REJECTION_REASON_REQUIRED", 400)
            status, task.status = "changes_requested", "rejected"
            ReviewTask.objects.filter(subject=task.subject).exclude(pk=task.pk).update(status="cancelled", version=F("version") + 1)
        else:
            required_reason = "SOURCE_VERIFIED" if task.review_type == "source" else "SCIENCE_VERIFIED"
            if reason != required_reason or fields:
                raise CMSFailure("INVALID_REASON", 400)
            if task.review_type == "source":
                _, sources = dependency_hash(kind, None, task.evidence)
                if ({item["source_id"] for item in task.evidence} != {source.pk for source in sources}
                        or not all(source_is_resolved(source) for source in sources)):
                    raise CMSFailure("SOURCE_UNRESOLVED", 409)
            elif not any(t.review_type == "source" and t.status == "approved" for t in tasks):
                raise CMSFailure("SOURCE_CHECK_REQUIRED", 409)
            task.status = "approved"
            status = "approved" if task.review_type == "scientific" else "in_review"
        task.version += 1
        task.save(update_fields=("status", "version"))
        advance(state, actor, status, task.dependency_digest)
        decision_record(actor, state, task, outcome, reason, policy, fields, self_review)
        audit(actor, state, "review.decided", reason, request_id, policy)
        return state


def reopen_review(actor_id, session_id, kind, target_id, expected, request_id):
    with policy_lock():
        actor, state, obj = context(actor_id, session_id, kind, target_id, expected, "cms_core_edit")
        require(actor, capability(kind, "submit"))
        if state.current_revision.status not in {"submitted", "in_review", "approved"}:
            raise CMSFailure("INVALID_TRANSITION", 409)
        tasks = latest_tasks(state)
        policy = current_policy()
        blockers = freshness(state, obj, tasks, policy, lock=True)
        reason = next((b for b in ("POLICY_CHANGED", "DEPENDENCY_CHANGED", "PAYLOAD_CHANGED") if b in blockers), "REVIEW_REOPEN")
        approved = state.current_revision.status == "approved"
        if approved:
            advance(state, actor, "superseded", tasks[0].dependency_digest)
            audit(actor, state, "review.invalidated", reason, request_id, policy)
        for task in tasks:
            task.status, task.version = "cancelled", task.version + 1
            task.save(update_fields=("status", "version"))
            decision_record(actor, state, task, "invalidated" if approved else "reopened", reason, policy)
        advance(state, actor, "draft", dependencies(kind, obj, state.current_revision.payload, True))
        audit(actor, state, "review.reopened", reason, request_id, policy)
        return state


def change_review_policy(actor_id, session_id, expected, data, request_id):
    with policy_lock():
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_owner")
        require(actor, "cms_settings_edit")
        policy = ReviewPolicy.objects.select_for_update().get(pk=1)
        if policy.version != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if (type(data.get("mode")) is not str or data["mode"] not in {"solo_owner", "two_person"}
                or type(data.get("reason")) is not str or data["reason"] not in POLICY_REASONS):
            raise CMSFailure("INVALID_POLICY", 400)
        if data["mode"] == policy.mode:
            raise CMSFailure("POLICY_UNCHANGED", 409)
        consume_step_up(session_id, actor, "review_policy", 1, data)
        ReviewPolicyRevision.objects.create(version=policy.version + 1, previous_mode=policy.mode,
            mode=data["mode"], actor=actor, reason=data["reason"])
        AdminAuditEvent.objects.create(actor=actor, action="review.policy", outcome="success", target_kind="",
            target_key="1", base_revision=policy.version, new_revision=policy.version + 1,
            diff=["mode"], reason=data["reason"], policy_version=policy.version, request_id=request_id)
        policy.mode, policy.version = data["mode"], policy.version + 1
        policy.save(update_fields=("mode", "version"))
        return policy
