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
from .cms_publication_surface_parity import public_root_witnesses
from .cms_publication_preparation import _owned_dossier, verify_preparation
from .cms_sessions import current_session


# Explicitly limited to short identity fields already present on the exact
# selected version. Source metadata, raw notes and other texts are not copied.
_DISPLAY_FIELDS = ("slug", "key", "name_en", "name_fa", "label", "title")

# Reader topology is a private impact *hint* only, not a serializer or proof
# that a draft would be published. Unknown consumers must remain unknown.
# Names correspond to existing public view/search/graph consumer contracts.
_PUBLIC_READER_PATHS = {
    "brain-anatomical-entity": {
        "detail": "brain_anatomy_detail",
        "search": "global_search.brain_entities",
        "graph": "atlas_graph.brain_anatomy",
    },
    "brain-anatomical-alias": {
        "detail": "brain_anatomy_detail",
        "search": "global_search.brain_entities",
        "graph": "atlas_graph.brain_anatomy",
    },
    "brain-hierarchy-link": {
        "detail": "brain_anatomy_detail",
        "graph": "atlas_graph.brain_anatomy",
    },
    "brain-network": {
        "detail": "brain_network_detail", "graph": "atlas_graph.brain_network",
    },
    "brain-network-alias": {
        "detail": "brain_network_detail", "graph": "atlas_graph.brain_network",
    },
    "brain-anatomical-entity-source": {
        "detail": "brain_anatomy_detail",
        "search": "global_search.brain_entities",
        "graph": "atlas_graph.brain_anatomy",
    },
    "brain-network-source": {
        "detail": "brain_network_detail", "graph": "atlas_graph.brain_network",
    },
    "brain-external-identifier": {
        "detail": "brain_anatomy_or_network_detail",
    },
    "brain-hierarchy-link-source": {
        "detail": "brain_anatomy_detail", "graph": "atlas_graph.brain_anatomy",
    },
    "brain-network-membership": {
        "detail": "brain_anatomy_or_network_detail", "graph": "atlas_graph.brain_network",
    },
    "brain-functional-association": {
        "detail": "brain_anatomy_detail", "graph": "atlas_graph.brain_anatomy",
    },
    "brain-network-membership-source": {
        "detail": "brain_anatomy_or_network_detail", "graph": "atlas_graph.brain_network",
    },
    "brain-functional-association-source": {
        "detail": "brain_anatomy_detail", "graph": "atlas_graph.brain_anatomy",
    },
    "assessment-instrument": {
        "detail": "assessment_detail",
        "search": "global_search.assessments",
        "graph": "atlas_graph.assessment",
    },
    "assessment-alias": {
        "detail": "assessment_detail",
        "search": "global_search.assessments",
        "graph": "atlas_graph.assessment",
    },
    "assessment-version": {
        "detail": "assessment_detail",
        "search": "global_search.assessments",
    },
    "assessment-language-form": {"detail": "assessment_detail"},
    "assessment-validation-study": {"detail": "assessment_detail"},
    "assessment-psychometric-evidence": {"detail": "assessment_detail"},
    "assessment-access": {"detail": "assessment_detail"},
    "assessment-relation": {
        "detail": "assessment_detail", "graph": "atlas_graph.assessment",
    },
    "assessment-source": {
        "detail": "assessment_detail", "search": "global_search.assessments",
        "graph": "atlas_graph.assessment",
    },
    "quiz": {"detail": "learning_quiz_detail"},
    "flashcard": {"detail": "learning_flashcard_detail"},
    "daily_challenge": {"detail": "learning_daily_challenge"},
    "distortion_practice": {"detail": "learning_distortion_practice"},
}


# Actual URL patterns declared in atlas.urls. These are public *reader*
# destinations, not hypothetical endpoints or publication permissions.
# An absent consumer remains None; do not fabricate detail/search/graph/compare.
_ANATOMY = "/api/brain-anatomy/{slug}/"
_ASSESSMENT = "/api/assessments/{slug}/"
_SEARCH = "/api/search/"
_GRAPH = "/api/concept-map/"
_PUBLIC_SURFACE_ROUTES = {
    "brain-anatomical-entity": {
        "list": "/api/brain-anatomy/", "detail": _ANATOMY,
        "search": _SEARCH, "graph": _GRAPH,
    },
    "brain-anatomical-alias": {
        "detail": _ANATOMY, "search": _SEARCH, "graph": _GRAPH,
    },
    "brain-hierarchy-link": {"detail": _ANATOMY, "graph": _GRAPH},
    "brain-anatomical-entity-source": {
        "detail": _ANATOMY, "search": _SEARCH, "graph": _GRAPH,
    },
    "brain-hierarchy-link-source": {"detail": _ANATOMY, "graph": _GRAPH},
    # A BrainNetwork is nested under anatomical detail. There is no public
    # Brain Network list/detail or graph node dedicated to this model.
    "brain-network": {},
    "brain-network-alias": {},
    "brain-network-source": {},
    "brain-external-identifier": {"detail": _ANATOMY},
    "brain-network-membership": {"detail": _ANATOMY},
    "brain-network-membership-source": {"detail": _ANATOMY},
    "brain-functional-association": {"detail": _ANATOMY},
    "brain-functional-association-source": {"detail": _ANATOMY},
    "assessment-instrument": {
        "list": "/api/assessments/", "detail": _ASSESSMENT,
        "search": _SEARCH, "graph": _GRAPH,
    },
    "assessment-alias": {
        "detail": _ASSESSMENT, "search": _SEARCH, "graph": _GRAPH,
    },
    "assessment-version": {"detail": _ASSESSMENT, "search": _SEARCH},
    "assessment-language-form": {"detail": _ASSESSMENT},
    "assessment-validation-study": {"detail": _ASSESSMENT},
    "assessment-psychometric-evidence": {"detail": _ASSESSMENT},
    "assessment-access": {"detail": _ASSESSMENT},
    "assessment-relation": {"detail": _ASSESSMENT},
    "assessment-source": {
        "detail": _ASSESSMENT, "search": _SEARCH, "graph": _GRAPH,
    },
    "quiz": {"list": "/api/quizzes/", "detail": "/api/quizzes/{slug}/"},
    "flashcard": {"list": "/api/flashcards/"},
    "daily_challenge": {"detail": "/api/daily-challenge/"},
    "distortion_practice": {"list": "/api/cognitive-distortions/practice/"},
}


# Keep a stable five-surface shape for every kind; missing != existing.
_PUBLIC_SURFACE_ROUTES = {
    kind: {surface: routes.get(surface)
           for surface in ("list", "detail", "search", "graph", "compare")}
    for kind, routes in _PUBLIC_SURFACE_ROUTES.items()
}


def _real_reader_contract(kind):
    routes = _PUBLIC_SURFACE_ROUTES.get(kind)
    if routes is None:
        raise CMSFailure("CANDIDATE_READER_MAP_UNVERIFIABLE", 409)
    return {
        "scope": "existing_public_urls_no_post_apply_promise",
        "surfaces": {
            surface: {
                "status": "existing_reader" if routes.get(surface) else "not_implemented_for_kind",
                "route": routes.get(surface),
            } for surface in ("list", "detail", "search", "graph", "compare")
        },
        "public_candidate_payload_available": False,
    }


# Only names of fields consumed by real reader paths may leave the private
# diff. Values, source locators, evidence and proposed text never do.
_SAFE_FIELD_NAMES = frozenset((
    "slug", "key", "name_en", "name_fa", "label", "title", "kind",
    "laterality", "language", "alias_type", "text", "form_kind",
    "entity", "network", "instrument", "version", "child", "parent",
    "concept", "symptom", "disorder", "relationship", "predicate",
    "qualifier", "evidence_key", "source_version", "review_status",
    "authorization_status", "license_status", "availability",
    "measurement_property", "statistic", "publication_year",
    "administration", "informant", "population", "sort_order",
))
_SEARCH_FIELDS = {
    "brain-anatomical-entity": {"slug", "name_en", "name_fa"},
    "brain-anatomical-alias": {"text", "language", "alias_type"},
    "assessment-instrument": {"slug", "name_en", "name_fa"},
    "assessment-version": {"key", "label"},
    "assessment-alias": {"text", "language", "alias_type"},
}
_GRAPH_FIELDS = {
    "brain-anatomical-entity": {"slug", "name_en", "name_fa", "kind", "laterality"},
    "brain-anatomical-alias": {"text", "language", "alias_type", "entity"},
    "brain-network": {"slug", "name_en", "name_fa", "kind"},
    "brain-network-alias": {"text", "language", "alias_type", "network"},
    "brain-hierarchy-link": {"child", "parent", "sort_order"},
    "brain-network-membership": {"entity", "network", "qualifier"},
    "brain-functional-association": {"entity", "network", "concept"},
    "assessment-instrument": {"slug", "name_en", "name_fa"},
    "assessment-alias": {"text", "instrument", "version"},
    "assessment-relation": {"version", "concept", "symptom", "disorder", "predicate"},
}


def _candidate_footprint(kind, domain, *, state=None):
    """Actual field changes of one sealed draft, never a public apply promise."""
    from .cms_content import canonical_snapshot
    from .cms_domains import DOMAIN_SPECS

    if domain == "learning":
        # A Learning selection pins an existing inactive authoring item. No
        # publish activation, timing or learner attempt is simulated here.
        return {
            "change_intent": "potential_activation",
            "before_public_visibility": False,
            "change_footprint": {"changed_public_fields": [],
                                 "unmapped_or_private_changed_count": 0,
                                 "surface_field_names": {
                                     surface: [] for surface in ("detail", "search", "graph", "compare")}},
        }
    if state is None or kind not in DOMAIN_SPECS:
        raise CMSFailure("CANDIDATE_PREVIEW_UNVERIFIABLE", 409)
    revision = state.current_revision
    baseline = {}
    if state.canonical_pk is not None:
        obj = DOMAIN_SPECS[kind]["model"].objects.select_for_update().filter(
            pk=state.canonical_pk).first()
        if obj is None:
            raise CMSFailure("CANDIDATE_PREVIEW_STALE", 409)
        baseline = canonical_snapshot(kind, obj)
    changes = set()
    for field, value in revision.payload.items():
        # Canonical snapshots store relations as FK attnames, while a
        # proposal's typed serializer accepts the relation field name.
        base_field = field if field in baseline else field + "_id"
        if state.canonical_pk is None or base_field not in baseline or baseline[base_field] != value:
            changes.add(field)
    # Canonical snapshots use *_id for FK keys; normalize only these names,
    # never interpolate private values into response text.
    normalized = {
        field[:-3] if field.endswith("_id") else field for field in changes
    }
    safe = normalized & _SAFE_FIELD_NAMES
    search = safe & _SEARCH_FIELDS.get(kind, set())
    graph = safe & _GRAPH_FIELDS.get(kind, set())
    footprint = {
        "changed_public_fields": sorted(safe),
        "unmapped_or_private_changed_count": len(normalized - _SAFE_FIELD_NAMES),
        "surface_field_names": {
            "detail": sorted(safe),
            "search": sorted(search),
            "graph": sorted(graph),
            "compare": [],
        },
    }
    if state.canonical_pk is None:
        before_public = False
    elif kind == "brain-anatomical-entity":
        from .brain_publication import public_anatomy
        before_public = public_anatomy().filter(pk=state.canonical_pk).exists()
    elif kind == "assessment-instrument":
        from .assessment_views import public_sets
        before_public = public_sets()["instruments"].filter(pk=state.canonical_pk).exists()
    else:
        # Other canonical selectors have different source/ancestor gates.
        # Unknown is safer than claiming they were/weren't public.
        before_public = None
    return {
        "change_intent": "create" if state.canonical_pk is None else "update",
        "before_public_visibility": before_public,
        "change_footprint": footprint,
    }


def _private_impact(dossier_digest, selected_items, footprints, public_roots):
    """Expose exact revision-pinned reader topology, never public candidate data."""
    return {
        "schema": "cms-private-public-surface-impact-v1",
        "scope": "authorized_private_consumer_topology_only",
        "dossier_digest": dossier_digest,
        "public_effect": False,
        "items": [{
            "kind": item["kind"], "resource_id": item["resource_id"],
            "revision_id": item["revision_id"], "fingerprint": item["fingerprint"],
            **footprint,
            "current_public_anchor": public_root,
            "readers": {
                surface: (_PUBLIC_READER_PATHS.get(item["kind"], {}).get(surface)
                          if _PUBLIC_SURFACE_ROUTES[item["kind"]].get(surface) else None)
                for surface in ("detail", "search", "graph", "compare")
            },
            "public_reader_contract": _real_reader_contract(item["kind"]),
            "mapping_complete": False,
            "after_apply": "not_available_without_frozen_authority",
        } for item, footprint, public_root in zip(selected_items, footprints, public_roots)],
        "notice": "READER_TOPOLOGY_ONLY_NOT_A_PUBLIC_DIFF_OR_APPLY_MANIFEST",
    }


def private_candidate_projection(actor_id, session_id, dossier_id):
    """Project exactly the sealed candidates under a live, scoped admin session."""
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        row, selection = _owned_dossier(actor, session_id, dossier_id)
        require(actor, "cms_" + selection.domain + "_preview")
        current = verify_preparation(actor_id, session_id, row.pk)
        if not current["snapshot_current"]:
            raise CMSFailure("CANDIDATE_PREVIEW_STALE", 409)
        items, footprints, projected_states = [], [], []
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
                footprints.append(_candidate_footprint(kind, selection.domain))
                projected_states.append(None)
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
                footprints.append(_candidate_footprint(kind, selection.domain, state=state))
                projected_states.append(state)
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
            "impact_preview": _private_impact(
                row.dossier_digest, items, footprints,
                public_root_witnesses(selection.domain, items, projected_states),
            ),
            "public_projection": {
                "available": False, "payload": None,
                "reason": "INDEPENDENT_SCIENCE_RIGHTS_AND_PUBLIC_MANIFEST_REQUIRED",
            },
            "published": False, "approved": False, "publication_available": False,
        }
