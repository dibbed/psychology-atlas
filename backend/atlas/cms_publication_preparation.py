"""P16 immutable preparation handoff for later independently-attested review.

This seals a live *private review* snapshot. It is explicitly NOT a public
publication manifest, evidence of legal/scientific permission, or an Apply path.
No proposed text, answers, source citations or reviewer identities are sent
to the client; no canonical record is modified.
"""
import uuid

from django.contrib.auth import get_user_model

from .cms_audit import attribution
from .cms_content import digest
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock
from .cms_publication_selection import _owned_selection, verify_selection, _uuid
from .cms_publication_preparation_models import PublicationPreparationDossier
from .cms_sessions import current_session


_SCHEMA = "cms-publication-preparation-v1"
_AUTHORITY = "private_preparation_only_no_scientific_rights_or_publication_approval"


def _payload(data):
    if type(data) is not dict or set(data) != {"request_key", "selection_digest"}:
        raise CMSFailure("INVALID_INPUT", 400)
    key = _uuid(data["request_key"])
    expected = data["selection_digest"]
    if (type(expected) is not str or len(expected) != 64
            or any(ch not in "0123456789abcdef" for ch in expected)):
        raise CMSFailure("INVALID_INPUT", 400)
    return key, expected


def _receipt(row, *, recovered=False):
    return {
        "id": str(row.pk),
        "selection_id": str(row.selection_id),
        "selection_digest": row.selection_digest,
        "domain": row.selection.domain,
        "dossier_digest": row.dossier_digest,
        "item_count": len(row.dossier["selection_snapshot"]["items"]),
        "status": "preparation_only",
        "recovered": recovered,
        "approved": False,
        "publication_available": False,
        "notice": "PREPARATION_IS_NOT_A_PUBLICATION_MANIFEST_OR_APPROVAL",
    }


def _owned_dossier(actor, session_id, dossier_id):
    current_session(session_id, actor)
    row = PublicationPreparationDossier.objects.select_related("selection").filter(
        pk=dossier_id).first()
    if row is None or row.actor_id != actor.pk:
        raise CMSFailure("NOT_FOUND", 404)
    selection = _owned_selection(actor, session_id, row.selection_id)
    data = row.dossier
    if (type(data) is not dict or data.get("schema") != _SCHEMA
            or data.get("authority") != {
                "status": _AUTHORITY, "publication_available": False,
                "approved": False,
            }
            or data.get("selection_id") != str(selection.pk)
            or data.get("domain") != selection.domain
            or data.get("selection_digest") != selection.selection_digest
            or data.get("policy_version") != selection.policy_version
            or data.get("selection_snapshot") != selection.selection
            or type(data.get("recheck_at_seal")) is not dict
            or type(data["recheck_at_seal"].get("items")) is not list
            or len(data["recheck_at_seal"]["items"]) != len(selection.selection["items"])
            or row.selection_digest != selection.selection_digest
            or digest(data) != row.dossier_digest):
        raise CMSFailure("DOSSIER_INTEGRITY_FAILED", 409)
    return row, selection


def prepare_selection(actor_id, session_id, selection_id, data, request_id):
    """Only seal still-current review baselines. Pending human gates stay open."""
    key, expected_digest = _payload(data)
    with policy_lock() as policy:
        actor = get_user_model().objects.get(pk=actor_id)
        selection = _owned_selection(actor, session_id, selection_id)
        existing = PublicationPreparationDossier.objects.filter(request_key=key).first()
        if existing:
            if existing.actor_id != actor.pk:
                raise CMSFailure("NOT_FOUND", 404)
            if (existing.selection_id != selection.pk
                    or existing.selection_digest != expected_digest):
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            _owned_dossier(actor, session_id, existing.pk)
            return existing, False
        if expected_digest != selection.selection_digest:
            raise CMSFailure("STALE_REVISION", 412)
        if policy.version != selection.policy_version:
            raise CMSFailure("PREPARATION_STALE", 409)
        # Under the same policy and candidate/source-writer lock, check the
        # entire selected batch again immediately before insertion.
        rechecked = verify_selection(actor_id, session_id, selection.pk)
        if (not rechecked["all_snapshots_current"]
                or rechecked["recheck_summary"]["content_issue_items"]
                or rechecked["recheck_summary"]["dependency_issue_items"]):
            raise CMSFailure("PREPARATION_NOT_CURRENT", 409)
        current_session(session_id, actor)
        # Nested verification rechecked domain capabilities; repeat admission
        # against the same live session immediately before committing.
        _owned_selection(actor, session_id, selection.pk)
        snapshot = {
            "schema": _SCHEMA,
            "selection_id": str(selection.pk),
            "selection_digest": selection.selection_digest,
            "domain": selection.domain,
            "policy_version": selection.policy_version,
            "selection_snapshot": selection.selection,
            "recheck_at_seal": {
                "items": rechecked["items"],
                "review_blockers": rechecked["review_blockers"],
                "recheck_summary": rechecked["recheck_summary"],
                "policy_matches": rechecked["policy_matches"],
                "all_snapshots_current": rechecked["all_snapshots_current"],
            },
            "authority": {
                "status": _AUTHORITY,
                "publication_available": False,
                "approved": False,
            },
        }
        dossier = PublicationPreparationDossier.objects.create(
            selection=selection, request_key=key,
            selection_digest=selection.selection_digest, dossier=snapshot,
            dossier_digest=digest(snapshot), actor=actor,
            actor_ref=attribution(actor.pk),
        )
        AdminAuditEvent.objects.create(
            actor=actor, action="publication.preparation_created",
            outcome="success", target_kind="publication-preparation",
            target_key=str(dossier.pk), request_id=request_id,
            reason="CONTENT_UPDATE", policy_version=policy.version,
        )
        return dossier, True


def list_preparations(actor_id, session_id, query):
    """Owner-scoped bounded historical inbox, NOT live readiness sampling."""
    from .cms_publication_selection import DOMAINS, _permissions

    if set(query) - {"domain", "page", "page_size"}:
        raise CMSFailure("INVALID_QUERY", 400)
    if len(query.getlist("domain")) != 1 or query["domain"] not in DOMAINS:
        raise CMSFailure("INVALID_QUERY", 400)
    domain = query["domain"]
    def number(name, default, maximum):
        values = query.getlist(name)
        if len(values) > 1:
            raise CMSFailure("INVALID_QUERY", 400)
        raw = values[0] if values else str(default)
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 6:
            raise CMSFailure("INVALID_QUERY", 400)
        parsed = int(raw)
        if not 1 <= parsed <= maximum:
            raise CMSFailure("INVALID_QUERY", 400)
        return parsed

    page = number("page", 1, 100000)
    page_size = number("page_size", 10, 20)
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        _permissions(actor, domain)
        records = PublicationPreparationDossier.objects.select_related("selection").filter(
            actor=actor, selection__domain=domain,
        ).order_by("-created_at", "-pk")
        count = records.count()
        if page > max(1, (count + page_size - 1) // page_size):
            raise CMSFailure("INVALID_QUERY", 400)
        rows = list(records[(page - 1) * page_size:page * page_size])
        items = []
        for row in rows:
            _owned_dossier(actor, session_id, row.pk)
            items.append(_receipt(row))
        current_session(session_id, actor)
        _permissions(actor, domain)
        return {
            "scope": "actor_owned_historical_private_preparation_receipts_only",
            "domain": domain, "count": count,
            "page": page, "page_size": page_size, "results": items,
            "publication_available": False, "approved": False,
            "notice": "HISTORICAL_LIST_NOT_A_CURRENT_READINESS_OR_HUMAN_SIGNOFF",
        }


def recheck_recent_preparations(actor_id, session_id, query):
    """Bounded live checks of recent actor-owned dossiers. No Apply authority."""
    from .cms_publication_selection import DOMAINS, _permissions

    if set(query) - {"domain", "limit", "ids"}:
        raise CMSFailure("INVALID_QUERY", 400)
    domains = query.getlist("domain")
    limits = query.getlist("limit")
    identifiers = query.getlist("ids")
    if (len(domains) != 1 or domains[0] not in DOMAINS
            or len(limits) > 1 or len(identifiers) > 1
            or (limits and identifiers)):
        raise CMSFailure("INVALID_QUERY", 400)
    explicit_ids = None
    if identifiers:
        raw_ids = identifiers[0].split(",")
        if not 1 <= len(raw_ids) <= 5:
            raise CMSFailure("INVALID_QUERY", 400)
        try:
            explicit_ids = [_uuid(value) for value in raw_ids]
        except CMSFailure:
            raise CMSFailure("INVALID_QUERY", 400)
        if len(set(explicit_ids)) != len(explicit_ids):
            raise CMSFailure("INVALID_QUERY", 400)
        limit = len(explicit_ids)
    else:
        raw_limit = limits[0] if limits else "3"
        if (not raw_limit.isascii() or not raw_limit.isdecimal()
                or len(raw_limit) > 2 or not 1 <= int(raw_limit) <= 5):
            raise CMSFailure("INVALID_QUERY", 400)
        limit = int(raw_limit)
    domain = domains[0]
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        _permissions(actor, domain)
        if explicit_ids is None:
            records = list(PublicationPreparationDossier.objects.filter(
                actor=actor, selection__domain=domain,
            ).order_by("-created_at", "-pk").values_list("pk", flat=True)[:limit])
        else:
            # A foreign or wrong-domain identity is never silently omitted:
            # the caller cannot infer another actor's receipt from a count.
            available = set(PublicationPreparationDossier.objects.filter(
                actor=actor, selection__domain=domain, pk__in=explicit_ids,
            ).values_list("pk", flat=True))
            if len(available) != len(explicit_ids):
                raise CMSFailure("NOT_FOUND", 404)
            records = explicit_ids
        results = []
        for dossier_id in records:
            current = verify_preparation(actor_id, session_id, dossier_id)
            # Return only safe aggregate and immutable receipt identifiers.
            # Full scoped detailed verification remains at its own endpoint.
            results.append({
                "id": current["id"],
                "selection_id": current["selection_id"],
                "dossier_digest": current["dossier_digest"],
                "snapshot_current": current["snapshot_current"],
                "content_issue_items": current["recheck_summary"]["content_issue_items"],
                "dependency_issue_items": current["recheck_summary"]["dependency_issue_items"],
                "review_blocker_count": len(current["review_blockers"]),
                "approved": False, "publication_available": False,
            })
        current_session(session_id, actor)
        _permissions(actor, domain)
        matched = sum(row["snapshot_current"] for row in results)
        return {
            "scope": "actor_owned_current_private_dossier_rechecks",
            "domain": domain, "limit": limit,
            "selection_mode": "explicit_ids" if explicit_ids is not None else "recent",
            "checked_count": len(results),
            "current_count": matched, "stale_count": len(results) - matched,
            "results": results, "approved": False,
            "publication_available": False,
            "notice": "CURRENT_VERSION_ONLY_NOT_INDEPENDENT_RIGHTS_OR_SCIENCE_CLEARANCE",
        }


def read_preparation(actor_id, session_id, dossier_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        row, _selection = _owned_dossier(actor, session_id, dossier_id)
        current_session(session_id, actor)
        return _receipt(row)


def verify_preparation(actor_id, session_id, dossier_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        row, selection = _owned_dossier(actor, session_id, dossier_id)
        current = verify_selection(actor_id, session_id, selection.pk)
        seal = row.dossier["recheck_at_seal"]
        current_matches = bool(
            current["all_snapshots_current"]
            and current["recheck_summary"]["content_issue_items"] == 0
            and current["recheck_summary"]["dependency_issue_items"] == 0
            and current["items"] == seal["items"]
            and current["policy_matches"] == seal["policy_matches"]
            and current["review_blockers"] == seal["review_blockers"]
        )
        current_session(session_id, actor)
        _owned_selection(actor, session_id, selection.pk)
        return {
            **_receipt(row),
            "snapshot_current": current_matches,
            "recheck_summary": current["recheck_summary"],
            "review_blockers": current["review_blockers"],
            "checked_at": current["verified_at"],
            "published": False,
            "approved": False,
            "publication_available": False,
        }
