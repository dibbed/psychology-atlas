"""P16 durable review selections. Deliberately NO Freeze, Approve or Apply.

A selected group is an immutable *request to review* bound to private
candidate digests. It does not contain content, claim scientific approval,
resolve sources, or authorize public effects.
"""
import uuid

from django.contrib.auth import get_user_model
from .cms_audit import attribution
from .cms_content import digest, scoped_states
from .cms_content_models import ContentState
from .cms_domains import DOMAIN_SPECS
from .cms_learning_fingerprint import KIND_MODELS, draft_fingerprint
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_publication_preflight import EDITORIAL_STATUSES, editorial_proposal_fingerprint
from .cms_publication_selection_models import PublicationCandidateSelection
from .cms_sessions import current_session


DOMAINS = ("learning", "brain", "assessment")
MAX_ITEMS = 20


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


def _resolve(actor, domain, item):
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
        states = scoped_states(actor, ContentState.objects.select_for_update().select_related(
            "current_revision").filter(
            pk=identifier, kind=kind, current_revision__status__in=EDITORIAL_STATUSES,
        ))
        state = states.first()
        if state is None:
            raise CMSFailure("NOT_FOUND", 404)
        preview = editorial_proposal_fingerprint(state)
        actual = preview["proposal_digest"]
        snapshot = {
            "kind": kind, "resource_id": str(state.pk),
            "revision_id": preview["revision_id"],
            "version": state.version, "proposal_digest": actual,
            "stored_dependency_digest": preview["dependency_digest"],
            "source_rights_revalidation": "required_before_any_publication",
        }
    if actual != item["expected_digest"]:
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
            "schema": "cms-review-selection-v1",
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


def read_selection(actor_id, session_id, selection_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        result = PublicationCandidateSelection.objects.filter(pk=selection_id).first()
        if result is None or result.actor_id != actor.pk:
            raise CMSFailure("NOT_FOUND", 404)
        _permissions(actor, result.domain)
        return result
