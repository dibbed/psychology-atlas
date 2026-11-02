"""Intersect public selectors with explicit scoped reviews; legacy is no grant."""
from contextvars import ContextVar
from django.core.cache import cache
from django.db import connection
from django.db.models import CharField, Q, Value


RESOURCE_TYPES = {
    "SourceReference": "source_reference", "Category": "category", "Disorder": "disorder",
    "Symptom": "symptom", "Concept": "concept", "DSMRecord": "dsm_record",
    "Therapy": "therapy", "Technique": "technique", "Psychologist": "psychologist",
    "Theory": "theory", "TimelineEvent": "timeline_event", "ClinicalCase": "clinical_case",
    "Flashcard": "flashcard", "Quiz": "quiz", "BrainAnatomicalEntity": "brain_anatomical_entity",
    "BrainNetwork": "brain_network", "AssessmentInstrument": "assessment_instrument",
    "AssessmentVersion": "assessment_version", "AssessmentLanguageForm": "assessment_language_form",
    "AssessmentValidationStudy": "assessment_validation_study",
    "AssessmentPsychometricEvidence": "assessment_psychometric_evidence",
    "AssessmentAlias": "assessment_alias", "AssessmentAccess": "assessment_access",
}

_request_index = ContextVar("atlas_public_rights_index", default=None)


class PublicRightsContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request_index.set({})
        try:
            return self.get_response(request)
        finally:
            _request_index.reset(token)


def _public_index():
    from .cms_governance_models import GovernanceRecord
    from .cms_source_models import SourceState
    from .cms_learning_lifecycle_models import LearningArchiveReceipt
    holder = _request_index.get()
    token = (connection.atomic_blocks[-1] if connection.in_atomic_block else None, cache.get("atlas_public_rights_revision"))
    if holder is not None and holder.get("token") == token:
        return holder["index"]
    if holder is None and connection.in_atomic_block:
        local = getattr(connection, "_atlas_public_rights_index", None)
        if local and local[0] == token:
            return local[1]
    # A process-local cache cannot observe another worker's rights revocation.
    scopes = GovernanceRecord.objects.filter(kind="rights").order_by().values_list(
        "resource_type", "resource_id", "material", "intended_use")
    inactive = SourceState.objects.filter(Q(archived=True) | Q(deleted=True)).order_by().annotate(
        kind=Value("source_reference", output_field=CharField()),
        material=Value("__lifecycle__", output_field=CharField()),
        use=Value("public_display", output_field=CharField()),
    ).values_list("kind", "source_pk", "material", "use")
    archived = LearningArchiveReceipt.objects.order_by().annotate(
        material=Value("__archive__", output_field=CharField()),
        use=Value("public_display", output_field=CharField()),
    ).values_list("kind", "resource_id", "material", "use")
    rows = list(scopes.union(inactive, archived))
    index = {"scopes": {row for row in rows if row[2] not in {"__lifecycle__", "__archive__"}},
             "inactive_sources": {row[1] for row in rows if row[2] == "__lifecycle__"},
             "learning_archives": {(row[0], row[1]) for row in rows if row[2] == "__archive__"}}
    if holder is not None:
        holder.update(token=token, index=index)
    elif connection.in_atomic_block:
        connection._atlas_public_rights_index = (token, index)
    return index


def registered_scopes():
    return _public_index()["scopes"]


def public_cache_safe():
    index = _public_index()
    return not index["scopes"] and not index["inactive_sources"] and not index["learning_archives"]


def learning_archived(kind, pk):
    return (kind, pk) in _public_index()["learning_archives"]


def _eligible(resource_type, pk, material, intended_use):
    from .cms_governance import resource_binding, rights_eligibility
    from .cms_policy import CMSFailure
    try:
        version = resource_binding(resource_type, pk)["resource_version"]
        return rights_eligibility(resource_type, pk, version, material, intended_use)["eligible"]
    except CMSFailure:
        return False


def public_rights(queryset, resource_type, material="metadata", intended_use="public_display"):
    if queryset.model.__name__ in {"Quiz", "Flashcard", "DailyChallenge", "CognitiveDistortionPracticeItem"}:
        queryset = queryset.filter(archived_at__isnull=True)
    blocked = set(_public_index()["inactive_sources"]) if resource_type == "source_reference" else set()
    targets = {pk for kind, pk, content, use in registered_scopes()
               if (kind, content, use) == (resource_type, material, intended_use)}
    for pk in targets:
        if not _eligible(resource_type, pk, material, intended_use):
            blocked.add(pk)
    return queryset.exclude(pk__in=blocked) if blocked else queryset


def public_resources(model):
    """Public read overlay; never replace the canonical/scientific managers."""
    return public_rights(model.objects.all(), RESOURCE_TYPES[model.__name__])


def public_items(queryset):
    kind = RESOURCE_TYPES[queryset.model.__name__]
    return public_rights(public_rights(queryset, kind), kind, "item")


def public_visible(obj, material="metadata", intended_use="public_display"):
    if obj is None:
        return False
    kind = RESOURCE_TYPES.get(type(obj).__name__)
    if kind is None:
        return True
    if kind in {"quiz", "flashcard"} and obj.archived_at is not None:
        return False
    return scope_visible(kind, obj.pk, material, intended_use)


def scope_visible(kind, pk, material="metadata", intended_use="public_display"):
    if learning_archived(kind, pk):
        return False
    if kind == "source_reference" and pk in _public_index()["inactive_sources"]:
        return False
    if (kind, pk, material, intended_use) not in registered_scopes():
        return True
    return _eligible(kind, pk, material, intended_use)


def public_summary(obj, english, translated=""):
    if not public_visible(obj, "text"):
        return ""
    return (translated if public_visible(obj, "translation") else "") or english


class PublicReadMixin:
    def get_queryset(self):
        queryset = super().get_queryset()
        kind = RESOURCE_TYPES.get(queryset.model.__name__)
        return public_rights(queryset, kind) if kind else queryset
