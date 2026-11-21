"""P11 Assessment CMS metadata-only typed proposals, no assessment items.

Staged registry; activate through cms_domains only after the P10 full-backend
gate has completed, so P10 verification remains tied to an exact source tree.
An assessment is a cited research identity and a scoped rights record, not a
test engine, score generator or diagnostic determination.
"""
from . import models as atlas

# Explicit, independently versioned identity, evidence and access rights.
# The full/protected questionnaire, official translated items, answer keys,
# scoring algorithms and manuals are NOT in these model field allowlists.
FIELDS = {
    "assessment-instrument": (atlas.AssessmentInstrument, "خانوادهٔ ابزار سنجش",
        ("slug", "name_en", "name_fa", "description", "construct_overview", "rightsholder"),
        ("slug",)),
    "assessment-version": (atlas.AssessmentVersion, "نسخهٔ ابزار سنجش",
        ("instrument", "key", "label", "form_kind", "publication_year", "derived_from",
         "construct", "intended_use", "administration", "informant", "population", "limitations"),
        ("instrument", "key")),
    "assessment-language-form": (atlas.AssessmentLanguageForm, "فرم زبانی و اقتباس",
        ("version", "key", "language", "label", "form_kind", "owner",
         "authorization_status", "authorization_source", "authorization_note"),
        ("version", "key", "language")),
    "assessment-validation-study": (atlas.AssessmentValidationStudy, "مطالعهٔ اعتبارسنجی",
        ("key", "version", "language_form", "source", "source_note", "design",
         "population", "sample_context", "sample_size", "administration", "informant",
         "method", "comparator", "limitations"),
        ("key", "version", "language_form", "source")),
    "assessment-psychometric-evidence": (atlas.AssessmentPsychometricEvidence, "یافتهٔ روان‌سنجی",
        ("key", "study", "measurement_property", "statistic", "method", "value_text",
         "units", "uncertainty", "finding", "limitations", "extraction_locator"),
        ("key", "study")),
    "assessment-alias": (atlas.AssessmentAlias, "نام جایگزین ابزار",
        ("instrument", "version", "text", "language", "alias_type", "source", "source_note"),
        ("instrument", "version", "text", "language")),
    "assessment-access": (atlas.AssessmentAccess, "مجوز و دسترسی دقیق ابزار",
        ("key", "version", "language_form", "material_type", "use", "jurisdiction", "owner",
         "availability", "license_status", "terms", "source", "source_note",
         "verified_on", "expires_on"),
        ("key", "version", "language_form", "material_type", "use")),
    "assessment-relation": (atlas.AssessmentRelation, "رابطهٔ ادعایی ابزار",
        ("key", "version", "language_form", "predicate", "concept", "symptom",
         "disorder", "claim", "context", "limitations"),
        ("key", "version", "language_form", "predicate", "concept", "symptom", "disorder")),
    "assessment-source": (atlas.AssessmentSource, "منبع ادعای سنجش",
        ("instrument", "version", "language_form", "relation", "source", "note"),
        ("instrument", "version", "language_form", "relation", "source")),
}

# Legacy claim-level source memberships. A study, alias and access proposal
# already have direct source references, so never synthesize a link for them.
SOURCE_LINKS = {
    atlas.AssessmentInstrument: ((atlas.AssessmentSource, "instrument"),),
    atlas.AssessmentVersion: ((atlas.AssessmentSource, "version"),),
    atlas.AssessmentLanguageForm: ((atlas.AssessmentSource, "language_form"),),
    atlas.AssessmentRelation: ((atlas.AssessmentSource, "relation"),),
}


def build_specs():
    # Late import prevents the domain-module import-order cycle.
    from .cms_domains import ProposalSerializer, _spec
    result = {}
    for kind, (model, label, fields, identities) in FIELDS.items():
        for name in fields:
            field = model._meta.get_field(name)
            if not field.editable or name in {"is_active", "seed_managed", "review_status",
                                           "raw_document", "source_payload", "search_text"}:
                raise RuntimeError("Assessment CMS field is not safely editable: " + kind + "." + name)
        meta = type("Meta", (), {"model": model, "fields": fields})
        serializer = type(model.__name__ + "CMSProposal", (ProposalSerializer,), {"Meta": meta})
        spec = _spec(serializer, label)
        spec["domain"] = "assessment"
        for field in identities:
            spec["field_policy"][field] = {
                "create_only": True,
                "readonly_reason": "EXACT_ASSESSMENT_IDENTITY; new edition, claim or rights-scope requires a new private proposal",
            }
        result[kind] = spec
    return result
