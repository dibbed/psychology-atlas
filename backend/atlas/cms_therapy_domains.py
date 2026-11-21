"""P08 typed editorial proposals; scientific source claims remain review-only until P16.

The two user-owned TherapyBookmark/TherapyNote models are deliberately excluded.
The explicit field inventory reflects canonical Therapy/Technique models; neither
review_status nor is_active nor seed_managed is a proposal-editable field.
"""
from . import models as atlas
from .cms_domains import ProposalSerializer, _spec


FIELDS = {
    "therapy-family": (atlas.TherapyFamily, "خانوادهٔ درمان", ("slug", "name_en", "name_fa", "description", "sort_order")),
    "therapy-classification": (atlas.TherapyClassification, "طبقه‌بندی درمان", ("slug", "name_en", "name_fa", "kind", "description", "sort_order")),
    "therapy": (atlas.Therapy, "رویکرد درمانی", ("family", "slug", "name_en", "name_fa", "summary", "academic_definition", "historical_context", "core_principles", "typical_structure", "appropriate_contexts", "limitations", "safety_notes", "evidence_note")),
    "technique": (atlas.Technique, "تکنیک درمانی", ("slug", "name_en", "name_fa", "summary", "academic_definition", "application_notes", "limitations", "safety_notes")),
    "therapy-classification-link": (atlas.TherapyClassificationLink, "رابطهٔ طبقه‌بندی و درمان", ("therapy", "classification", "explanation", "sort_order")),
    "therapy-disorder": (atlas.TherapyDisorder, "رابطهٔ درمان و اختلال", ("therapy", "disorder", "clinical_role", "evidence_basis", "explanation", "evidence_note", "sort_order")),
    "therapy-technique": (atlas.TherapyTechnique, "رابطهٔ درمان و تکنیک", ("therapy", "technique", "role", "explanation", "sort_order")),
    "therapy-concept": (atlas.TherapyConcept, "رابطهٔ درمان و مفهوم", ("therapy", "concept", "relationship_type", "explanation", "sort_order")),
    "technique-concept": (atlas.TechniqueConcept, "رابطهٔ تکنیک و مفهوم", ("technique", "concept", "relationship_type", "explanation", "sort_order")),
    "therapy-alias": (atlas.TherapyAlias, "نام جایگزین درمان", ("therapy", "text", "language", "alias_type")),
    "technique-alias": (atlas.TechniqueAlias, "نام جایگزین تکنیک", ("technique", "text", "language", "alias_type")),
    "therapy-source": (atlas.TherapySource, "منبع رویکرد درمانی", ("therapy", "source", "note")),
    "technique-source": (atlas.TechniqueSource, "منبع تکنیک", ("technique", "source", "note")),
    "therapy-technique-source": (atlas.TherapyTechniqueSource, "منبع رابطهٔ درمان و تکنیک", ("relationship", "source", "note")),
    "therapy-disorder-source": (atlas.TherapyDisorderSource, "منبع رابطهٔ درمان و اختلال", ("relationship", "source", "note")),
    "therapy-concept-source": (atlas.TherapyConceptSource, "منبع رابطهٔ درمان و مفهوم", ("relationship", "source", "note")),
    "technique-concept-source": (atlas.TechniqueConceptSource, "منبع رابطهٔ تکنیک و مفهوم", ("relationship", "source", "note")),
}

SOURCE_LINKS = {
    atlas.Therapy: ((atlas.TherapySource, "therapy"),),
    atlas.Technique: ((atlas.TechniqueSource, "technique"),),
    atlas.TherapyTechnique: ((atlas.TherapyTechniqueSource, "relationship"),),
    atlas.TherapyDisorder: ((atlas.TherapyDisorderSource, "relationship"),),
    atlas.TherapyConcept: ((atlas.TherapyConceptSource, "relationship"),),
    atlas.TechniqueConcept: ((atlas.TechniqueConceptSource, "relationship"),),
}


def build_specs():
    specs = {}
    for kind, (model, label, fields) in FIELDS.items():
        # A distinct Meta class keeps DRF's typed serializer and model field
        # constraints. No dynamic model name or arbitrary requested field is accepted.
        meta = type("Meta", (), {"model": model, "fields": fields})
        serializer = type(model.__name__ + "CMSProposal", (ProposalSerializer,), {"Meta": meta})
        spec = _spec(serializer, label)
        spec["domain"] = "therapy"
        specs[kind] = spec
    return specs
