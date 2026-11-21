"""Bounded, read-only public-root witness for sealed CMS candidate previews.

Never calls a public serializer with draft data, never edits canonical rows,
never grants scientific or rights permission and never predicts post-Apply
visibility. The source of *current* public root eligibility is exactly the
same Django queryset used by the corresponding public read API, Search and
Graph. Indirect roots are represented explicitly as unknown when unresolved.
"""

from .cms_domains import DOMAIN_SPECS
from .cms_policy import CMSFailure


# A root path navigates *typed* foreign keys from a selected proposal to an
# existing canonical public root. Empty path means the selected canonical
# itself would be the root. A relation edit may affect both its old and new
# roots; inspect both. Network-only records have no direct public network
# reader in the current atlas URL surface and therefore must stay unresolved.
_PUBLIC_ROOT_PATHS = {
    "brain-anatomical-entity": ((),),
    "brain-anatomical-alias": (("entity",),),
    "brain-anatomical-entity-source": (("entity",),),
    "brain-hierarchy-link": (("child",), ("parent",)),
    "brain-hierarchy-link-source": (
        ("relationship", "child"), ("relationship", "parent"),
    ),
    "brain-network": (),
    "brain-network-alias": (),
    "brain-network-source": (),
    "brain-external-identifier": (("entity",),),
    "brain-network-membership": (("entity",),),
    "brain-network-membership-source": (("relationship", "entity"),),
    "brain-functional-association": (("entity",),),
    "brain-functional-association-source": (("relationship", "entity"),),
    "assessment-instrument": ((),),
    "assessment-alias": (("instrument",), ("version", "instrument")),
    "assessment-version": (("instrument",),),
    "assessment-language-form": (("version", "instrument"),),
    "assessment-validation-study": (("version", "instrument"),),
    "assessment-psychometric-evidence": (("study", "version", "instrument"),),
    "assessment-access": (("version", "instrument"),),
    "assessment-relation": (("version", "instrument"),),
    "assessment-source": (
        ("instrument",), ("version", "instrument"),
        ("language_form", "version", "instrument"),
        ("relation", "version", "instrument"),
    ),
}


def _root_of_path(model, canonical, payload, path, *, projected):
    if not path:
        return canonical.pk if canonical is not None else None
    instance = canonical
    for index, field_name in enumerate(path):
        field = model._meta.get_field(field_name)
        if not field.is_relation or not field.many_to_one:
            raise CMSFailure("PUBLIC_ROOT_TYPE_UNVERIFIABLE", 409)
        if index == 0 and projected and field_name in payload:
            pk = payload[field_name]
        elif index == 0 and projected and field.attname in payload:
            pk = payload[field.attname]
        elif instance is not None:
            pk = getattr(instance, field.attname, None)
        else:
            return None
        # Even a valid proposal can have an optional parent. Don't infer an
        # ancestor from a hidden/invalid identifier.
        if type(pk) is not int or not 0 < pk < 2**63:
            return None
        model = field.remote_field.model
        if index + 1 < len(path):
            instance = model.objects.filter(pk=pk).first()
            if instance is None:
                return None
        else:
            return pk
    return None


def _root_candidates(kind, state):
    if kind not in _PUBLIC_ROOT_PATHS:
        raise CMSFailure("PUBLIC_ROOT_TYPE_UNVERIFIABLE", 409)
    paths = _PUBLIC_ROOT_PATHS[kind]
    if not paths:
        return (), "indirect_root_unmapped"
    model = DOMAIN_SPECS[kind]["model"]
    canonical = None
    if state.canonical_pk is not None:
        canonical = model.objects.select_for_update().filter(
            pk=state.canonical_pk,
        ).first()
        if canonical is None:
            raise CMSFailure("PUBLIC_ROOT_BASE_STALE", 409)
    payload = state.current_revision.payload
    ids = set()
    for path in paths:
        current = _root_of_path(model, canonical, payload, path, projected=True)
        if current is not None:
            ids.add(current)
        if canonical is not None:
            historical = _root_of_path(model, canonical, {}, path, projected=False)
            if historical is not None:
                ids.add(historical)
    if len(ids) > 8:
        raise CMSFailure("PUBLIC_ROOT_LIMIT_EXCEEDED", 409)
    if not ids:
        return (), "root_not_created" if paths == ((),) else "root_unresolved"
    return tuple(sorted(ids)), "resolved"


def public_root_witnesses(domain, items, states):
    """Check public root selectors once per domain and disclose aggregates only.

    Each item has the same revision/selection identity already rechecked by the
    caller. Return only bounded counts, never root IDs, public article data,
    draft names, aliases, source/evidence, or learner records.
    """
    if len(items) != len(states) or len(items) > 20:
        raise CMSFailure("PUBLIC_ROOT_LIMIT_EXCEEDED", 409)
    if domain == "learning":
        return [{
            "schema": "cms-current-public-root-v1",
            "status": "learning_candidate_inactive",
            "root_type": None,
            "root_count": 0,
            "visible_count": 0,
            "candidate_public": False,
            "post_apply_projection_available": False,
        } for _ in items]
    if domain not in ("brain", "assessment"):
        raise CMSFailure("PUBLIC_ROOT_DOMAIN_UNVERIFIABLE", 409)

    roots = []
    candidates = set()
    for item, state in zip(items, states):
        if state is None or item["kind"] != state.kind:
            raise CMSFailure("PUBLIC_ROOT_REVISION_UNVERIFIABLE", 409)
        ids, status = _root_candidates(item["kind"], state)
        roots.append((ids, status))
        candidates.update(ids)
    if len(candidates) > 160:
        raise CMSFailure("PUBLIC_ROOT_LIMIT_EXCEEDED", 409)

    visible = set()
    if candidates:
        if domain == "brain":
            from .brain_publication import public_anatomy
            visible = set(public_anatomy().filter(
                pk__in=candidates).values_list("pk", flat=True))
        else:
            from .assessment_views import public_sets
            visible = set(public_sets()["instruments"].filter(
                pk__in=candidates).values_list("pk", flat=True))
    root_type = ("brain_anatomical_entity" if domain == "brain"
                 else "assessment_instrument")
    report = []
    for identifiers, reason in roots:
        count = len(identifiers)
        visible_count = sum(identifier in visible for identifier in identifiers)
        status = reason
        if identifiers:
            status = ("visible_public_root" if visible_count == count
                      else "hidden_public_root" if visible_count == 0
                      else "mixed_public_roots")
        report.append({
            "schema": "cms-current-public-root-v1",
            "status": status,
            "root_type": root_type,
            "root_count": count,
            "visible_count": visible_count,
            "candidate_public": False,
            "post_apply_projection_available": False,
            "selector": ("public_anatomy" if domain == "brain"
                         else "public_sets.instruments"),
            "scope": "current_public_canonical_only_not_draft_or_after_apply",
        })
    return report
