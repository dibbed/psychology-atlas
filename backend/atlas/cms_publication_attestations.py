"""W16-03 exact-manifest attestation registry, never authority to publish.

An attestation records an authenticated staff review statement about a sealed,
still-current selection and its cited sources. It does *not* decide whether
material is legally reusable, and cannot make private content public.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError

from .cms_audit import attribution
from .cms_content import digest
from .cms_content_models import ContentState
from .cms_domains import DOMAIN_SPECS, dependency_snapshot
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_publication_manifest import _validated_manifest
from .cms_publication_plan_models import PublicationFrozenManifest, PublicationManifestAttestation
from .cms_publication_selection import _resolve, _uuid, MAX_RIGHTS_SOURCES
from .cms_review_models import ReviewPolicy
from .cms_sessions import current_session


KINDS = ("source", "scientific", "rights")
_MATERIALS = {"metadata", "text", "translation", "item", "instruction", "manual", "questionnaire"}
_PUBLIC_STATUS = "attestations_recorded_not_publication_clearance"


def _context(actor, session_id, plan_id, *, kind=None, permission=None):
    current_session(session_id, actor)
    plan = PublicationFrozenManifest.objects.select_for_update().select_related(
        "dossier", "dossier__selection",
    ).filter(pk=plan_id).first()
    if plan is None:
        raise CMSFailure("NOT_FOUND", 404)
    _validated_manifest(plan)
    domain = plan.manifest["domain"]
    if domain not in {"brain", "assessment", "learning"}:
        raise CMSFailure("NOT_FOUND", 404)
    require(actor, "cms_" + domain + "_view")
    require(actor, "cms_publication_" + (permission or "verify") + "_" + domain)
    if kind is not None:
        require(actor, "cms_review_decide_" + domain + "_" + kind)
    return plan


def _current_sources(actor, session_id, plan):
    """Revalidate all selected source/review/right snapshots before a decision.

    The reviewer need not be the original dossier owner. Each candidate is
    independently scoped to that reviewer's domain and its exact immutable
    selection identity. This protects against a stale or foreign plan reuse.
    """
    selected = plan.dossier.selection
    ids = set()
    right_budget = {"remaining": MAX_RIGHTS_SOURCES}
    for snap in selected.selection["items"]:
        field = "content_digest" if selected.domain == "learning" else "proposal_digest"
        desired = {"kind": snap["kind"], "resource_id": snap["resource_id"],
                   "expected_digest": snap[field]}
        current = _resolve(
            actor, selected.domain, desired,
            enforce_digest=False,
            include_editorial_review=selected.domain != "learning",
            include_rights=True, rights_budget=right_budget,
        )
        if current != snap:
            raise CMSFailure("ATTESTATION_CANDIDATE_STALE", 409)
        if selected.domain == "learning":
            # Learning evidence stream seals sources independently of Quiz
            # choices/answer keys. Do not serialize evidence values.
            from .cms_learning_evidence import _latest
            from .cms_learning_fingerprint import KIND_MODELS, MAX_QUESTIONS
            kind, resource_id = snap["kind"], snap["resource_id"]
            item = KIND_MODELS[kind].objects.select_for_update().get(pk=resource_id)
            targets = list(item.questions.order_by("pk")[:MAX_QUESTIONS + 1]) if kind == "quiz" else [item]
            if len(targets) > MAX_QUESTIONS:
                raise CMSFailure("ATTESTATION_SOURCE_LIMIT", 409)
            for target in targets:
                revision = _latest("quiz-question" if kind == "quiz" else {
                    "flashcard": "flashcard", "daily_challenge": "daily",
                    "distortion_practice": "distortions",
                }[kind], target.pk)
                if revision is not None:
                    ids.update(revision.links.values_list("source_id", flat=True))
        else:
            state = ContentState.objects.select_for_update(of=("self",)).select_related(
                "current_revision").filter(pk=snap["resource_id"],
                                           kind=snap["kind"]).first()
            if state is None:
                raise CMSFailure("ATTESTATION_CANDIDATE_STALE", 409)
            canonical = (DOMAIN_SPECS[state.kind]["model"].objects.select_for_update().filter(
                pk=state.canonical_pk).first() if state.canonical_pk is not None else None)
            try:
                closure = dependency_snapshot(state.kind, canonical,
                                              state.current_revision.payload, lock=True)
            except ModelValidationError:
                raise CMSFailure("ATTESTATION_SOURCE_UNVERIFIABLE", 409)
            ids.update(item["id"] for item in closure["sources"])
    if len(ids) > MAX_RIGHTS_SOURCES:
        raise CMSFailure("ATTESTATION_SOURCE_LIMIT", 409)
    return sorted(ids)


def _receipt(row, *, recovered=False):
    return {
        "id": row.pk,
        "plan_id": str(row.plan_id),
        "manifest_digest": row.manifest_digest,
        "kind": row.kind,
        "outcome": row.outcome,
        "recovered": recovered,
        "approved": False,
        "publication_available": False,
        "notice": "ATTESTATION_NOT_SCIENCE_RIGHTS_CLEARANCE_OR_PUBLIC_APPLY",
    }


def _latest_states(plan):
    latest = {}
    for row in plan.attestations.order_by("-pk"):
        if row.kind not in latest:
            latest[row.kind] = row
    policy = ReviewPolicy.objects.select_for_update().get(pk=1)
    eligible = {}
    for kind, row in latest.items():
        reviewer = get_user_model().objects.filter(
            pk=row.actor_id, is_active=True, is_staff=True).first() if row.actor_id else None
        rights = {
            "cms_enter", "cms_" + plan.manifest["domain"] + "_view",
            "cms_publication_approve_" + plan.manifest["domain"],
            "cms_review_decide_" + plan.manifest["domain"] + "_" + kind,
        }
        eligible[kind] = bool(
            row.outcome == "attested" and reviewer and
            plan.manifest.get("review_policy") == {
                "version": policy.version, "mode": policy.mode,
            } and
            rights <= effective_permissions(reviewer) and
            row.manifest_digest == plan.manifest_digest and
            row.policy_version == policy.version and row.policy_mode == policy.mode and
            (row.actor_id != plan.actor_id or
             (policy.mode == "solo_owner" and "cms_owner" in effective_permissions(reviewer)))
        )
    return latest, eligible


def read_attestations(actor_id, session_id, plan_id):
    with policy_lock() as role_policy:
        actor = get_user_model().objects.get(pk=actor_id)
        plan = _context(actor, session_id, plan_id, permission="verify")
        latest, eligible = _latest_states(plan)
        snapshot_current = bool(plan.manifest["policy_version"] == role_policy.version)
        if snapshot_current:
            try:
                _current_sources(actor, session_id, plan)
            except CMSFailure as error:
                # Historical decisions remain available as safe status counts,
                # never silently treated as still valid after source/review drift.
                if error.status_code not in (403, 404, 409):
                    raise
                snapshot_current = False
        return {
            "schema": "cms-private-manifest-attestation-status-v1",
            "plan_id": str(plan.pk),
            "manifest_digest": plan.manifest_digest,
            "status": _PUBLIC_STATUS,
            "states": {kind: latest[kind].outcome if kind in latest else "absent"
                       for kind in KINDS},
            "attestations_current": bool(snapshot_current and
                                        all(eligible.get(kind) for kind in KINDS)),
            "snapshot_current": snapshot_current,
            "scope": "independent_private_review_records_only",
            "approved": False,
            "publication_available": False,
            "public_projection": None,
        }


def record_attestation(actor_id, session_id, plan_id, data, request_id):
    if type(data) is not dict or set(data) != {
        "kind", "outcome", "manifest_digest", "request_key",
        "evidence_source_ids", "rights_scope", "evidence_reference",
        "self_review_ack",
    }:
        raise CMSFailure("INVALID_INPUT", 400)
    kind, outcome = data["kind"], data["outcome"]
    if type(kind) is not str or kind not in KINDS or type(outcome) is not str or outcome not in {"attested", "revoked"}:
        raise CMSFailure("INVALID_INPUT", 400)
    key = _uuid(data["request_key"])
    expected = data["manifest_digest"]
    if type(expected) is not str or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise CMSFailure("INVALID_INPUT", 400)
    evidence = data["evidence_source_ids"]
    scope = data["rights_scope"]
    reference = data["evidence_reference"]
    if (type(evidence) is not list or len(evidence) > MAX_RIGHTS_SOURCES or
            any(type(x) is not int or x <= 0 for x in evidence) or
            evidence != sorted(set(evidence)) or type(scope) is not list or
            any(type(x) is not str or x not in _MATERIALS for x in scope) or
            len(scope) != len(set(scope)) or
            type(reference) is not str or len(reference) > 400 or
            data["self_review_ack"] is not True):
        raise CMSFailure("INVALID_INPUT", 400)
    if outcome == "attested":
        if not reference.strip():
            raise CMSFailure("EVIDENCE_REQUIRED", 400)
        required_scope = {"metadata", "text", "translation"} if kind == "rights" else set()
        if kind == "rights" and (not required_scope <= set(scope) or len(scope) > 7):
            raise CMSFailure("RIGHTS_SCOPE_REQUIRED", 400)
        if kind != "rights" and scope:
            raise CMSFailure("INVALID_INPUT", 400)
    elif evidence or scope or reference:
        raise CMSFailure("INVALID_INPUT", 400)

    with policy_lock() as role_policy:
        review_policy = ReviewPolicy.objects.select_for_update().get(pk=1)
        actor = get_user_model().objects.get(pk=actor_id)
        plan = _context(actor, session_id, plan_id, kind=kind, permission="approve")
        if expected != plan.manifest_digest:
            raise CMSFailure("MANIFEST_STALE", 412)
        previous = PublicationManifestAttestation.objects.filter(request_key=key).first()
        if previous is not None:
            if previous.actor_id != actor.pk or previous.plan_id != plan.pk:
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            if (previous.kind != kind or previous.outcome != outcome or
                    previous.manifest_digest != expected or
                    previous.evidence_source_ids != evidence or
                    previous.rights_scope != scope or
                    previous.evidence_reference != reference):
                raise CMSFailure("IDEMPOTENCY_CONFLICT", 409)
            return previous, False
        if review_policy.mode == "two_person" and actor.pk == plan.actor_id:
            raise CMSFailure("TWO_PERSON_REQUIRED", 409)
        if review_policy.mode == "solo_owner" and actor.pk == plan.actor_id and "cms_owner" not in effective_permissions(actor):
            raise CMSFailure("REVIEWER_CONFLICT", 409)
        if (role_policy.version != plan.manifest["policy_version"] or
                plan.manifest.get("review_policy") != {
                    "version": review_policy.version, "mode": review_policy.mode,
                }):
            raise CMSFailure("ATTESTATION_POLICY_STALE", 409)
        # Cached status is not authority: always compare exact live decisions,
        # rights and candidate/source identities under the same policy lock.
        if outcome == "attested":
            linked = _current_sources(actor, session_id, plan)
            if not linked or evidence != linked:
                raise CMSFailure("ATTESTATION_SOURCE_MISMATCH", 409)
        if outcome == "revoked":
            prior = plan.attestations.filter(kind=kind).order_by("-pk").first()
            if prior is None:
                raise CMSFailure("ATTESTATION_NOT_FOUND", 409)
        current_session(session_id, actor)
        require(actor, "cms_publication_approve_" + plan.manifest["domain"])
        require(actor, "cms_review_decide_" + plan.manifest["domain"] + "_" + kind)
        row = PublicationManifestAttestation.objects.create(
            plan=plan, request_key=key, manifest_digest=expected, kind=kind,
            outcome=outcome, evidence_source_ids=evidence,
            rights_scope=scope, evidence_reference=reference,
            actor=actor, actor_ref=attribution(actor.pk),
            policy_version=review_policy.version, policy_mode=review_policy.mode,
            self_review=actor.pk == plan.actor_id,
        )
        AdminAuditEvent.objects.create(
            actor=actor, action="publication.attestation_recorded",
            outcome="success", target_kind="publication-manifest-attestation",
            target_key=str(row.pk), reason="CONTENT_UPDATE",
            policy_version=role_policy.version, request_id=request_id,
        )
        return row, True
