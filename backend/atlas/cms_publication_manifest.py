"""W16-02 review-manifest Freeze and safe dry-run; no public writers.

Every field is re-derived server-side from a still-current, sealed dossier
under the single P16 policy+candidate/source lock. The manifest intentionally
does NOT contain publishable content or confer rights/science authority.
"""
from django.contrib.auth import get_user_model

from .cms_audit import attribution
from .cms_content import digest
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_publication_candidate_preview import private_candidate_projection
from .cms_publication_plan_models import PublicationFrozenManifest
from .cms_publication_preparation import _owned_dossier, verify_preparation
from .cms_publication_selection import _uuid
from .cms_sessions import current_session


_SCHEMA = "cms-frozen-review-manifest-v1"


def _access(actor, session_id, dossier_id, *, ability):
    current_session(session_id, actor)
    # Independent W16-02 ability, not broader edit/publish permission.
    # Enforce before the dossier lookup, but never reveal foreign IDs.
    dossier, selection = _owned_dossier(actor, session_id, dossier_id)
    require(actor, "cms_publication_" + ability + "_" + selection.domain)
    return dossier, selection


def _sealed_review_policy():
    from .cms_review_models import ReviewPolicy
    row = ReviewPolicy.objects.select_for_update().get(pk=1)
    return {"version": row.version, "mode": row.mode}


def _manifest(actor_id, session_id, dossier_id):
    actor = get_user_model().objects.get(pk=actor_id)
    dossier, selection = _access(actor, session_id, dossier_id, ability="freeze")
    current = verify_preparation(actor_id, session_id, dossier.pk)
    if not current["snapshot_current"]:
        raise CMSFailure("MANIFEST_DOSSIER_STALE", 409)
    if (current["recheck_summary"]["content_issue_items"]
            or current["recheck_summary"]["dependency_issue_items"]):
        raise CMSFailure("MANIFEST_DOSSIER_INVALID", 409)

    # The read-only W17 service validates exact version/permissions and pins
    # known public routes and canonical root selectors before Freeze.
    preview = private_candidate_projection(actor_id, session_id, dossier.pk)
    if preview["dossier_digest"] != dossier.dossier_digest:
        raise CMSFailure("MANIFEST_DOSSIER_STALE", 409)
    impact = preview["impact_preview"]
    if len(impact["items"]) != len(selection.selection["items"]):
        raise CMSFailure("MANIFEST_ITEM_COUNT_STALE", 409)
    actions = []
    for selected, draft, row in zip(selection.selection["items"],
                                    preview["items"], impact["items"]):
        if (draft["kind"] != selected["kind"]
                or draft["resource_id"] != selected["resource_id"]
                or row["fingerprint"] != draft["fingerprint"]):
            raise CMSFailure("MANIFEST_ITEM_MISMATCH", 409)
        action = row["change_intent"]
        actions.append({
            "kind": draft["kind"],
            "resource_id": draft["resource_id"],
            "revision_id": draft["revision_id"],
            "version": draft["version"],
            "fingerprint": draft["fingerprint"],
            "action": "activate" if action == "potential_activation" else action,
            "changed_public_fields": row["change_footprint"]["changed_public_fields"],
            "unmapped_or_private_changed_count":
                row["change_footprint"]["unmapped_or_private_changed_count"],
            "current_public_anchor": row["current_public_anchor"],
            "public_reader_contract": row["public_reader_contract"],
            "post_apply_projection_available": False,
        })

    # Private content values, answer keys, protected source locators and any
    # arbitrary proposal properties are intentionally absent.
    manifest = {
        "schema": _SCHEMA,
        "authority": "frozen_review_only_no_publication",
        "domain": selection.domain,
        "selection_id": str(selection.pk),
        "selection_digest": selection.selection_digest,
        "dossier_id": str(dossier.pk),
        "dossier_digest": dossier.dossier_digest,
        "policy_version": selection.policy_version,
        "review_policy": _sealed_review_policy(),
        "item_count": len(actions),
        "actions": actions,
        "review_blocker_count": len(current["review_blockers"]),
        "closure_status": "sealed_current" ,
        "source_rights_scope": "source_metadata_only_not_material_publish_rights",
        "public_projection": None,
        "approved": False,
        "publication_available": False,
    }
    if current["review_blockers"]:
        manifest["review_readiness"] = "independent_review_required"
    else:
        manifest["review_readiness"] = "editorial_evidence_current_not_publication_approval"
    current_session(session_id, actor)
    _access(actor, session_id, dossier.pk, ability="freeze")
    return manifest


def dry_run_manifest(actor_id, session_id, dossier_id):
    with policy_lock():
        manifest = _manifest(actor_id, session_id, dossier_id)
        return {**manifest, "manifest_digest": digest(manifest)}


def _validated_manifest(plan):
    """Server-side manifest verification reusable by an independent reviewer."""
    selection = plan.dossier.selection
    if (plan.dossier.selection_digest != selection.selection_digest
            or digest(plan.dossier.dossier) != plan.dossier.dossier_digest
            or digest(selection.selection) != selection.selection_digest):
        raise CMSFailure("FROZEN_MANIFEST_INTEGRITY_FAILED", 409)
    manifest = plan.manifest
    if (type(manifest) is not dict or manifest.get("schema") != _SCHEMA
            or manifest.get("authority") != "frozen_review_only_no_publication"
            or manifest.get("dossier_id") != str(plan.dossier_id)
            or manifest.get("dossier_digest") != plan.dossier.dossier_digest
            or manifest.get("selection_id") != str(selection.pk)
            or manifest.get("selection_digest") != selection.selection_digest
            or manifest.get("policy_version") != selection.policy_version
            or type(manifest.get("review_policy")) is not dict
            or set(manifest["review_policy"]) != {"version", "mode"}
            or type(manifest["review_policy"]["version"]) is not int
            or manifest["review_policy"]["mode"] not in {"solo_owner", "two_person"}
            or manifest.get("domain") != selection.domain
            or type(manifest.get("actions")) is not list
            or not 1 <= len(manifest["actions"]) <= 20
            or len(manifest["actions"]) != len(selection.selection["items"])
            or manifest.get("public_projection", object()) is not None
            or manifest.get("approved") is not False
            or manifest.get("publication_available") is not False
            or digest(manifest) != plan.manifest_digest):
        raise CMSFailure("FROZEN_MANIFEST_INTEGRITY_FAILED", 409)
    expected = selection.selection["items"]
    for action, bound in zip(manifest["actions"], expected):
        fingerprint = "content_digest" if selection.domain == "learning" else "proposal_digest"
        if (type(action) is not dict or action.get("kind") != bound.get("kind")
                or action.get("resource_id") != bound.get("resource_id")
                or action.get("fingerprint") != bound.get(fingerprint)
                or action.get("revision_id") != bound.get("revision_id")
                or action.get("version") != bound.get("version")):
            raise CMSFailure("FROZEN_MANIFEST_INTEGRITY_FAILED", 409)
    return plan


def _owned_plan(actor, session_id, plan_id):
    plan = PublicationFrozenManifest.objects.select_related(
        "dossier", "dossier__selection").filter(pk=plan_id).first()
    if plan is None or plan.actor_id != actor.pk:
        raise CMSFailure("NOT_FOUND", 404)
    _access(actor, session_id, plan.dossier_id, ability="verify")
    return _validated_manifest(plan)


def _receipt(plan, *, recovered=False):
    return {
        "id": str(plan.pk),
        "dossier_id": str(plan.dossier_id),
        "dossier_digest": plan.manifest["dossier_digest"],
        "selection_id": plan.manifest["selection_id"],
        "domain": plan.manifest["domain"],
        "manifest_digest": plan.manifest_digest,
        "item_count": plan.manifest["item_count"],
        "status": "frozen_review_only",
        "recovered": recovered,
        "approved": False,
        "publication_available": False,
        "public_projection": None,
        "actions": plan.manifest["actions"],
        "notice": "FROZEN_REVIEW_MANIFEST_NOT_A_SCIENCE_RIGHTS_APPROVAL_OR_APPLY",
    }


def freeze_manifest(actor_id, session_id, dossier_id, data, request_id):
    if type(data) is not dict or set(data) != {"request_key", "dossier_digest"}:
        raise CMSFailure("INVALID_INPUT", 400)
    key = _uuid(data["request_key"])
    expected = data["dossier_digest"]
    if (type(expected) is not str or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)):
        raise CMSFailure("INVALID_INPUT", 400)
    with policy_lock() as policy:
        actor = get_user_model().objects.get(pk=actor_id)
        dossier, selection = _access(actor, session_id, dossier_id, ability="freeze")
        if dossier.dossier_digest != expected:
            raise CMSFailure("MANIFEST_DOSSIER_STALE", 412)
        original = PublicationFrozenManifest.objects.select_related(
            "dossier", "dossier__selection").filter(request_key=key).first()
        if original is not None:
            if original.actor_id != actor.pk:
                raise CMSFailure("NOT_FOUND", 404)
            if original.dossier_id != dossier.pk:
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            _owned_plan(actor, session_id, original.pk)
            return original, False
        if PublicationFrozenManifest.objects.filter(dossier=dossier).exists():
            raise CMSFailure("MANIFEST_ALREADY_FROZEN", 409)
        manifest = _manifest(actor_id, session_id, dossier.pk)
        if manifest["policy_version"] != policy.version:
            raise CMSFailure("MANIFEST_POLICY_STALE", 409)
        row = PublicationFrozenManifest.objects.create(
            dossier=dossier, request_key=key, manifest=manifest,
            manifest_digest=digest(manifest),
            actor=actor, actor_ref=attribution(actor.pk),
        )
        AdminAuditEvent.objects.create(
            actor=actor, action="publication.review_manifest_frozen",
            outcome="success", target_kind="publication-frozen-manifest",
            target_key=str(row.pk), request_id=request_id,
            reason="CONTENT_UPDATE", policy_version=policy.version,
        )
        return row, True


def read_manifest(actor_id, session_id, plan_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        plan = _owned_plan(actor, session_id, plan_id)
        return _receipt(plan)
