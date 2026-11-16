"""Read-only exact private P17 candidate projection, never a public renderer.

A sealed private dossier pins a chosen revision. This endpoint intentionally
does not turn private drafts, unlicensed text, or staging into a public payload.
The future public manifest/apply workflow must supply separate rights/science
authorization before any public projection is possible.
"""
from django.contrib.auth import get_user_model

from .cms_content import scoped_states
from .cms_content_models import ContentState
from .cms_learning_fingerprint import KIND_MODELS
from .cms_policy import CMSFailure, policy_lock, require
from .cms_publication_preparation import _owned_dossier, verify_preparation
from .cms_sessions import current_session


# Explicitly limited to short identity fields already present on the exact
# selected version. Source metadata, raw notes and other texts are not copied.
_DISPLAY_FIELDS = ("slug", "key", "name_en", "name_fa", "label", "title")


def private_candidate_projection(actor_id, session_id, dossier_id):
    """Project exactly the sealed candidates under a live, scoped admin session."""
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        row, selection = _owned_dossier(actor, session_id, dossier_id)
        require(actor, "cms_" + selection.domain + "_preview")
        current = verify_preparation(actor_id, session_id, row.pk)
        if not current["snapshot_current"]:
            raise CMSFailure("CANDIDATE_PREVIEW_STALE", 409)
        items = []
        for bound in row.dossier["selection_snapshot"]["items"]:
            kind, identifier = bound["kind"], bound["resource_id"]
            if selection.domain == "learning":
                model = KIND_MODELS.get(kind)
                if model is None:
                    raise CMSFailure("CANDIDATE_PREVIEW_UNVERIFIABLE", 409)
                candidate = model.objects.select_for_update().filter(
                    pk=identifier, is_active=False, archived_at__isnull=True,
                    seed_managed=False,
                ).first()
                if candidate is None:
                    raise CMSFailure("CANDIDATE_PREVIEW_STALE", 409)
                display = {
                    name: getattr(candidate, name)[:160]
                    for name in _DISPLAY_FIELDS if isinstance(getattr(candidate, name, None), str)
                    and getattr(candidate, name)
                }
                version = None
                revision_id = None
                fingerprint = bound["content_digest"]
            else:
                # Exact ContentState UUID, not any canonical object whose current
                # text happens to resemble the selected editorial candidate.
                states = scoped_states(actor, ContentState.objects.select_for_update(
                    of=("self",)).select_related("current_revision").filter(
                    pk=identifier, kind=kind,
                ))
                state = states.first()
                if (state is None or str(state.current_revision_id) != str(bound["revision_id"])
                        or state.version != bound["version"]):
                    raise CMSFailure("CANDIDATE_PREVIEW_STALE", 409)
                revision = state.current_revision
                # A typed, fixed allowlist. No general serialization of payload,
                # source documents, study answers, audit or user-owned data.
                display = {
                    name: revision.payload[name][:160]
                    for name in _DISPLAY_FIELDS
                    if isinstance(revision.payload.get(name), str) and revision.payload[name]
                }
                version = state.version
                revision_id = revision.pk
                fingerprint = bound["proposal_digest"]
            items.append({
                "kind": kind, "resource_id": identifier,
                "revision_id": revision_id, "version": version,
                "fingerprint": fingerprint, "display": display,
                "visibility": "authorized_private_draft_only",
            })
        current_session(session_id, actor)
        require(actor, "cms_" + selection.domain + "_preview")
        _owned_dossier(actor, session_id, row.pk)
        return {
            "schema": "cms-private-candidate-projection-v1",
            "scope": "authorized_private_candidate_only",
            "domain": selection.domain, "selection_id": str(selection.pk),
            "selection_digest": selection.selection_digest,
            "dossier_id": str(row.pk), "dossier_digest": row.dossier_digest,
            "snapshot_current": True, "items": items,
            "public_projection": {
                "available": False, "payload": None,
                "reason": "INDEPENDENT_SCIENCE_RIGHTS_AND_PUBLIC_MANIFEST_REQUIRED",
            },
            "published": False, "approved": False, "publication_available": False,
        }
