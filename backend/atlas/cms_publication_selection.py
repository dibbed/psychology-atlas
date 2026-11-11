"""P16 immutable review requests bound to private candidates and live dependencies.

Independent evidence, frozen publication manifests and public effects belong
to the subsequent publication workflow.
"""
import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .brain_publication import source_is_resolved
from .cms_audit import attribution
from .cms_content import canonical_snapshot, digest, scoped_states
from .cms_content_models import ContentState
from .cms_domains import DOMAIN_SPECS, dependency_snapshot
from .cms_governance import governance_dependency_snapshot, resource_binding, rights_eligibility
from .cms_learning_fingerprint import KIND_MODELS, draft_fingerprint
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_publication_preflight import EDITORIAL_STATUSES, editorial_proposal_fingerprint
from .cms_publication_selection_models import PublicationCandidateSelection
from .cms_review import approval_eligibility
from .cms_review_models import ReviewPolicy
from .cms_sessions import current_session
from .models import SourceReference, lock_brain_curation


DOMAINS = ("learning", "brain", "assessment")
MAX_ITEMS = 20
MAX_RIGHTS_SOURCES = 16


def _uuid(value):
    if type(value) is not str or len(value) != 36:
        raise CMSFailure("INVALID_INPUT", 400)
    try:
        parsed = uuid.UUID(value)
    except (TypeError, AttributeError, ValueError):
        raise CMSFailure("INVALID_INPUT", 400)
    if str(parsed) != value.lower():
        raise CMSFailure("INVALID_INPUT", 400)
    return parsed


def parse_selection(data):
    if type(data) is not dict or set(data) != {"domain", "entries", "request_key"}:
        raise CMSFailure("INVALID_INPUT", 400)
    domain, raw = data["domain"], data["entries"]
    if type(domain) is not str or domain not in DOMAINS or type(raw) is not list or not 1 <= len(raw) <= MAX_ITEMS:
        raise CMSFailure("INVALID_INPUT", 400)
    key = _uuid(data["request_key"])
    entries = []
    for item in raw:
        if type(item) is not dict or set(item) != {"kind", "resource_id", "expected_digest"}:
            raise CMSFailure("INVALID_INPUT", 400)
        kind, identifier, expected = item["kind"], item["resource_id"], item["expected_digest"]
        if (type(kind) is not str or type(expected) is not str or len(expected) != 64
                or any(character not in "0123456789abcdef" for character in expected)):
            raise CMSFailure("INVALID_INPUT", 400)
        if domain == "learning":
            if kind not in KIND_MODELS or type(identifier) is not int or not 0 < identifier < 2**63:
                raise CMSFailure("INVALID_INPUT", 400)
        else:
            if kind not in DOMAIN_SPECS or DOMAIN_SPECS[kind]["domain"] != domain:
                raise CMSFailure("INVALID_INPUT", 400)
            identifier = str(_uuid(identifier))
        entries.append({"kind": kind, "resource_id": identifier, "expected_digest": expected})
    entries.sort(key=lambda item: (item["kind"], str(item["resource_id"])))
    if len({(item["kind"], str(item["resource_id"])) for item in entries}) != len(entries):
        raise CMSFailure("INVALID_INPUT", 400)
    return domain, entries, key


def _permissions(actor, domain):
    for cap in ("cms_" + domain + "_view", "cms_publication_validate_" + domain,
                "cms_publication_select_" + domain):
        require(actor, cap)


def _source_rights_coverage(source_ids, *, budget=None):
    """Inspect source *metadata* rights, not rights in a proposed publication."""
    source_ids = sorted(set(source_ids))
    total = len(source_ids)
    base = {
        "scope": "source_metadata_public_display_only",
        "source_count": total,
        "permitted_count": 0,
        "unverified_count": total,
        "publication_rights_cleared": False,
    }
    if not source_ids:
        return {**base, "status": "no_sources"}
    if total > MAX_RIGHTS_SOURCES or (budget is not None and total > budget["remaining"]):
        # Never turn a truncated evidence sample into a positive clearance.
        return {**base, "status": "unverifiable"}
    if budget is not None:
        budget["remaining"] -= total
    permitted = 0
    registered = 0
    for source_id in source_ids:
        try:
            binding = resource_binding("source_reference", source_id, lock=True)
            gate = rights_eligibility(
                "source_reference", source_id, binding["resource_version"],
                "metadata", "public_display", lock=True,
            )
        except CMSFailure as error:
            if error.status_code == 404:
                return {**base, "status": "unverifiable"}
            raise
        if gate["registered"]:
            registered += 1
        if gate["registered"] and gate["permitted"]:
            permitted += 1
    status = "recorded" if permitted == total else (
        "not_established" if registered == 0 else "insufficient")
    return {**base, "status": status, "permitted_count": permitted,
            "unverified_count": total - permitted}


def _editorial_dependencies(state, *, include_rights=False, rights_budget=None):
    revision = state.current_revision
    if digest(revision.payload) != revision.payload_digest:
        raise CMSFailure("SELECTION_INTEGRITY_FAILED", 409)
    canonical = None
    if state.canonical_pk is not None:
        canonical = DOMAIN_SPECS[state.kind]["model"].objects.select_for_update().filter(
            pk=state.canonical_pk).first()
        if canonical is None:
            raise CMSFailure("NOT_FOUND", 404)
    try:
        closure = dependency_snapshot(state.kind, canonical, revision.payload, lock=True)
    except ValidationError:
        raise CMSFailure("DEPENDENCY_UNVERIFIABLE", 409)
    source_ids = [item["id"] for item in closure["sources"]]
    governance = governance_dependency_snapshot(source_ids, lock=True,
        resource_type=state.kind.replace("-", "_") if canonical is not None else None,
        resource_id=state.canonical_pk)
    policy = ReviewPolicy.objects.select_for_update().filter(pk=1).first()
    if policy is None:
        raise CMSFailure("REVIEW_POLICY_UNAVAILABLE", 503)
    base = digest(canonical_snapshot(state.kind, canonical)) if canonical is not None else digest({})
    issues = []
    if base != state.canonical_digest or base != revision.base_digest:
        issues.append("CANONICAL_BASE_CHANGED")
    if governance["missing_source_ids"] or any(row["archived"] or row["deleted"] for row in closure["source_lifecycle"]):
        issues.append("SOURCE_UNAVAILABLE")
    if not all(source_is_resolved(source) for source in SourceReference.objects.filter(pk__in=source_ids)):
        issues.append("SOURCE_UNRESOLVED")
    snapshot = {
        "digest": digest({"schema": "cms-live-editorial-dependencies-v1", "canonical": base,
            "closure": closure, "governance": governance,
            "review_policy": {"version": policy.version, "mode": policy.mode}}),
        "source_count": len(source_ids), "endpoint_count": len(closure["endpoints"]),
        "issues": issues,
    }
    if include_rights:
        return snapshot, _source_rights_coverage(source_ids, budget=rights_budget)
    return snapshot


def _editorial_review_gate(state):
    """Existing CMS source/science decisions; not P16 publication clearance."""
    policy = ReviewPolicy.objects.select_for_update().filter(pk=1).first()
    if policy is None:
        raise CMSFailure("REVIEW_POLICY_UNAVAILABLE", 503)
    canonical = None
    if state.canonical_pk is not None:
        canonical = DOMAIN_SPECS[state.kind]["model"].objects.select_for_update().filter(
            pk=state.canonical_pk).first()
        if canonical is None:
            return {"status": "unverifiable", "blockers": ["CANONICAL_UNAVAILABLE"]}
    try:
        gate = approval_eligibility(state, canonical, lock=True)
    except ValidationError:
        return {"status": "unverifiable", "blockers": ["EDITORIAL_REVIEW_UNVERIFIABLE"]}
    return {
        "status": "editorial_tasks_current" if gate["eligible"] else "blocked",
        "blockers": gate["blockers"],
    }


def _resolve(actor, domain, item, *, enforce_digest=True, include_editorial_review=False, include_rights=False, rights_budget=None):
    kind, identifier = item["kind"], item["resource_id"]
    if domain == "learning":
        model = KIND_MODELS[kind]
        candidate = model.objects.select_for_update().filter(
            pk=identifier, is_active=False, seed_managed=False, archived_at__isnull=True,
        ).first()
        if candidate is None:
            raise CMSFailure("NOT_FOUND", 404)
        preview = draft_fingerprint(kind, candidate)
        actual = preview["content_digest"]
        snapshot = {
            "kind": kind, "resource_id": identifier,
            "content_digest": actual,
            "dependency_ids": preview["dependency_ids"],
            "content_issues": preview["content_issues"],
        }
    else:
        lock_brain_curation(connection.alias)
        states = scoped_states(actor, ContentState.objects.select_for_update(of=("self",)).select_related(
            "current_revision").filter(
            pk=identifier, kind=kind, current_revision__status__in=EDITORIAL_STATUSES,
        ))
        state = states.first()
        if state is None:
            raise CMSFailure("NOT_FOUND", 404)
        preview = editorial_proposal_fingerprint(state)
        actual = preview["proposal_digest"]
        if include_rights:
            dependencies, rights = _editorial_dependencies(
                state, include_rights=True, rights_budget=rights_budget)
        else:
            dependencies = _editorial_dependencies(state)
        snapshot = {
            "kind": kind, "resource_id": str(state.pk),
            "revision_id": preview["revision_id"],
            "version": state.version, "proposal_digest": actual,
            "stored_dependency_digest": preview["dependency_digest"],
            "live_dependencies": dependencies,
            "source_rights_revalidation": "required_before_any_publication",
        }
        if include_rights:
            snapshot["source_rights_evidence"] = rights
        if include_editorial_review:
            snapshot["editorial_review"] = _editorial_review_gate(state)
    if enforce_digest and actual != item["expected_digest"]:
        raise CMSFailure("SELECTION_STALE", 412)
    return snapshot


def response_data(selection, *, recovered=False):
    return {
        "id": str(selection.pk), "domain": selection.domain,
        "selection_digest": selection.selection_digest,
        "status": "review_selection_only",
        "item_count": len(selection.selection["items"]),
        "publication_available": False,
        "approved": False,
        "recovered": recovered,
        "notice": "SELECTION_IS_NOT_A_PUBLICATION_MANIFEST",
    }


def select_candidates(actor_id, session_id, data, request_id):
    domain, entries, key = parse_selection(data)
    with policy_lock() as policy:
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        _permissions(actor, domain)
        request_digest = digest({"domain": domain, "entries": entries})
        existing = PublicationCandidateSelection.objects.filter(request_key=key).first()
        if existing:
            if existing.actor_id != actor.pk or existing.request_digest != request_digest or existing.domain != domain:
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            return existing, False
        snapshots = [_resolve(actor, domain, item) for item in entries]
        current_session(session_id, actor)
        _permissions(actor, domain)
        manifest = {
            "schema": "cms-review-selection-v2",
            "domain": domain,
            "policy_version": policy.version,
            "items": snapshots,
            "eligibility": "review_only",
            "authority": "no_scientific_rights_or_publication_approval",
        }
        selected = PublicationCandidateSelection.objects.create(
            domain=domain, request_key=key, request_digest=request_digest,
            selection=manifest, selection_digest=digest(manifest),
            policy_version=policy.version, actor=actor, actor_ref=attribution(actor.pk),
        )
        AdminAuditEvent.objects.create(
            actor=actor, action="publication.selection_created", outcome="success",
            target_kind="publication-selection", target_key=str(selected.pk),
            request_id=request_id, reason="CONTENT_UPDATE", policy_version=policy.version,
        )
        return selected, True


def _owned_selection(actor, session_id, selection_id):
    current_session(session_id, actor)
    result = PublicationCandidateSelection.objects.filter(pk=selection_id).first()
    if result is None or result.actor_id != actor.pk:
        raise CMSFailure("NOT_FOUND", 404)
    _permissions(actor, result.domain)
    manifest = result.selection
    if (type(manifest) is not dict
            or manifest.get("schema") not in {"cms-review-selection-v1", "cms-review-selection-v2"}
            or manifest.get("domain") != result.domain
            or manifest.get("policy_version") != result.policy_version
            or manifest.get("authority") != "no_scientific_rights_or_publication_approval"
            or type(manifest.get("items")) is not list
            or not 1 <= len(manifest["items"]) <= MAX_ITEMS
            or digest(manifest) != result.selection_digest):
        raise CMSFailure("SELECTION_INTEGRITY_FAILED", 409)
    return result


def read_selection(actor_id, session_id, selection_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        return _owned_selection(actor, session_id, selection_id)


def verify_selection(actor_id, session_id, selection_id):
    """Recheck persisted, actor-owned snapshots; never authorize publication."""
    with policy_lock() as policy:
        actor = get_user_model().objects.get(pk=actor_id)
        selected = _owned_selection(actor, session_id, selection_id)
        entries = selected.selection["items"]
        checks = []
        rights_budget = {"remaining": MAX_RIGHTS_SOURCES}
        for snapshot in entries:
            if type(snapshot) is not dict or snapshot.get("kind") is None:
                raise CMSFailure("SELECTION_INTEGRITY_FAILED", 409)
            field = "content_digest" if selected.domain == "learning" else "proposal_digest"
            expected = snapshot.get(field)
            if type(expected) is not str or len(expected) != 64:
                raise CMSFailure("SELECTION_INTEGRITY_FAILED", 409)
            candidate = {
                "kind": snapshot["kind"], "resource_id": snapshot.get("resource_id"),
                "expected_digest": expected,
            }
            state = "matching"
            issues = []
            dependency_state = "content_only" if selected.domain == "learning" else "baseline_missing"
            dependency_issues = []
            editorial_review = None
            source_rights_evidence = None
            try:
                current = _resolve(actor, selected.domain, candidate, enforce_digest=False,
                                   include_editorial_review=True, include_rights=True,
                                   rights_budget=rights_budget)
                editorial_review = current.get("editorial_review")
                source_rights_evidence = current.get("source_rights_evidence")
                if current[field] != expected:
                    state = "stale"
                if selected.domain == "learning":
                    issues = current["content_issues"]
                else:
                    live = current["live_dependencies"]
                    dependency_issues = live["issues"]
                    previous = snapshot.get("live_dependencies")
                    if previous is not None:
                        dependency_state = "matching" if previous == live else "stale"
                    if dependency_issues:
                        dependency_state = "invalid"
            except CMSFailure as error:
                code = str(error.detail.get("code", ""))
                if code == "NOT_FOUND":
                    state = "unavailable"
                elif code in {"PREVIEW_LIMIT", "DEPENDENCY_UNVERIFIABLE"}:
                    state = "unverifiable"
                else:
                    # Never conceal a new permission check, DB error, or unknown
                    # validation failure behind a seemingly successful report.
                    raise
                dependency_state = "invalid"
                dependency_issues = ["DEPENDENCY_UNAVAILABLE" if state == "unavailable" else "DEPENDENCY_UNVERIFIABLE"]
                if selected.domain != "learning":
                    editorial_review = {"status": "unverifiable",
                                        "blockers": ["EDITORIAL_CANDIDATE_UNAVAILABLE"]}
                    source_rights_evidence = {
                        "scope": "source_metadata_public_display_only",
                        "source_count": 0, "permitted_count": 0, "unverified_count": 0,
                        "publication_rights_cleared": False, "status": "unverifiable",
                    }
            item_result = {
                "kind": candidate["kind"], "resource_id": candidate["resource_id"],
                "snapshot_state": state, "content_issues": issues,
                "dependency_state": dependency_state, "dependency_issues": dependency_issues,
            }
            if selected.domain != "learning":
                item_result["editorial_review"] = editorial_review
                item_result["source_rights_evidence"] = source_rights_evidence
            checks.append(item_result)
        current_session(session_id, actor)
        _permissions(actor, selected.domain)
        policy_matches = policy.version == selected.policy_version
        all_current = policy_matches and all(item["snapshot_state"] == "matching"
            and item["dependency_state"] in {"matching", "content_only"} for item in checks)
        blockers = ["SOURCE_SCIENCE_RIGHTS_UNVERIFIED", "FROZEN_MANIFEST_AND_APPROVAL_REQUIRED"]
        if selected.domain in {"brain", "assessment"}:
            blockers.append("LIVE_SOURCE_RIGHTS_REVALIDATION_REQUIRED")
        if any(item["dependency_state"] == "baseline_missing" for item in checks):
            blockers.append("LIVE_DEPENDENCY_BASELINE_REQUIRED")
        if not policy_matches:
            blockers.append("POLICY_CHANGED")
        if not all_current:
            blockers.append("SELECTION_RECHECK_REQUIRED")
        if any(item["content_issues"] for item in checks):
            blockers.append("CONTENT_VALIDATION_REQUIRED")
        return {
            "id": str(selected.pk), "domain": selected.domain,
            "status": "review_selection_only",
            "selection_digest": selected.selection_digest,
            "item_count": len(checks), "items": checks,
            "policy_matches": policy_matches,
            "all_snapshots_current": all_current,
            "review_blockers": blockers,
            "verified_at": timezone.now().isoformat(),
            "publication_available": False, "approved": False,
        }
