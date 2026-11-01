"""P10 bounded Brain editorial schema. Always proposal-only, never a publisher.

All 13 actual Brain domain models are explicit; this registry is not an
arbitrary Django model resolver. Existing public/pinned publication APIs remain
authoritative and must not consume unreviewed draft fields.
"""
from . import models as atlas

# kind -> (model, Persian label, editable fields, create-only identities)
FIELDS = {
    "brain-anatomical-entity": (atlas.BrainAnatomicalEntity, "ناحیهٔ آناتومی مغز",
        ("slug", "name_en", "name_fa", "description_en", "description_fa", "kind", "laterality"), ("slug",)),
    "brain-network": (atlas.BrainNetwork, "شبکهٔ مغزی",
        ("slug", "name_en", "name_fa", "description_en", "description_fa", "kind"), ("slug",)),
    "brain-anatomical-alias": (atlas.BrainAnatomicalAlias, "نام جایگزین آناتومی",
        ("entity", "text", "language", "alias_type", "source", "source_note"), ()),
    "brain-network-alias": (atlas.BrainNetworkAlias, "نام جایگزین شبکه",
        ("network", "text", "language", "alias_type", "source", "source_note"), ()),
    "brain-anatomical-entity-source": (atlas.BrainAnatomicalEntitySource, "منبع آناتومی",
        ("entity", "source", "note"), ()),
    "brain-network-source": (atlas.BrainNetworkSource, "منبع شبکهٔ مغزی",
        ("network", "source", "note"), ()),
    "brain-external-identifier": (atlas.BrainExternalIdentifier, "شناسهٔ خارجی مغز",
        ("namespace", "identifier", "source_version", "entity", "network", "url", "source", "source_note"),
        ("namespace", "identifier", "source_version")),
    "brain-hierarchy-link": (atlas.BrainHierarchyLink, "رابطهٔ سلسله‌مراتب مغز",
        ("child", "parent", "source_version", "explanation_en", "explanation_fa", "sort_order"),
        ("source_version",)),
    "brain-hierarchy-link-source": (atlas.BrainHierarchyLinkSource, "منبع سلسله‌مراتب",
        ("relationship", "source", "note"), ()),
    "brain-network-membership": (atlas.BrainNetworkMembership, "عضویت در شبکه",
        ("entity", "network", "qualifier", "evidence_key", "source_version", "method",
         "limitations", "explanation_en", "explanation_fa", "sort_order"),
        ("evidence_key", "source_version")),
    "brain-functional-association": (atlas.BrainFunctionalAssociation, "ارتباط کارکردی",
        ("entity", "network", "concept", "task_context", "population_context", "evidence_key",
         "source_version", "method", "limitations", "explanation_en", "explanation_fa", "sort_order"),
        ("evidence_key", "source_version")),
    "brain-network-membership-source": (atlas.BrainNetworkMembershipSource, "منبع عضویت شبکه",
        ("relationship", "source", "note"), ()),
    "brain-functional-association-source": (atlas.BrainFunctionalAssociationSource, "منبع ارتباط کارکردی",
        ("relationship", "source", "note"), ()),
}

SOURCE_LINKS = {
    atlas.BrainAnatomicalEntity: ((atlas.BrainAnatomicalEntitySource, "entity"),),
    atlas.BrainNetwork: ((atlas.BrainNetworkSource, "network"),),
    atlas.BrainHierarchyLink: ((atlas.BrainHierarchyLinkSource, "relationship"),),
    atlas.BrainNetworkMembership: ((atlas.BrainNetworkMembershipSource, "relationship"),),
    atlas.BrainFunctionalAssociation: ((atlas.BrainFunctionalAssociationSource, "relationship"),),
}


def build_specs():
    # Late import is intentional: cms_domains imports this registry.
    from .cms_domains import ProposalSerializer, _spec
    result = {}
    for kind, (model, label, fields, immutable) in FIELDS.items():
        meta = type("Meta", (), {"model": model, "fields": fields})
        serializer = type(model.__name__ + "CMSProposal", (ProposalSerializer,), {"Meta": meta})
        spec = _spec(serializer, label)
        spec["domain"] = "brain"
        for name in immutable:
            spec["field_policy"][name] = {
                "create_only": True,
                "readonly_reason": "CREATE_ONLY_IDENTITY; correction needs a new curated draft.",
            }
        result[kind] = spec
    return result
