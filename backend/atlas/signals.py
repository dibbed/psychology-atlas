from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.contrib.auth.models import Group, User
from django.dispatch import receiver
from uuid import uuid4

from . import models as atlas_models
from .models import (
    Category,
    Concept,
    ConceptRelationship,
    ConceptSymptom,
    Disorder,
    DisorderConcept,
    DisorderSymptom,
    DSMCorpus,
    DSMRecord,
    DSMRecordRelation,
    SourceReference,
    Symptom,
    Technique,
    TechniqueConcept,
    TechniqueConceptSource,
    Therapy,
    TherapyClassification,
    TherapyClassificationLink,
    TherapyConcept,
    TherapyConceptSource,
    TherapyDisorder,
    TherapyDisorderSource,
    TherapyFamily,
    TherapyTechnique,
    TherapyTechniqueSource,
)


V06_GRAPH_MODELS = (
    atlas_models.Psychologist,
    atlas_models.Theory,
    atlas_models.TimelineEvent,
    atlas_models.PsychologistTheory,
    atlas_models.PsychologistTheorySource,
    atlas_models.PsychologistConcept,
    atlas_models.PsychologistConceptSource,
    atlas_models.PsychologistTherapy,
    atlas_models.PsychologistTherapySource,
    atlas_models.PsychologistPsychologist,
    atlas_models.PsychologistPsychologistSource,
    atlas_models.TheoryConcept,
    atlas_models.TheoryConceptSource,
    atlas_models.TheoryTherapy,
    atlas_models.TheoryTherapySource,
    atlas_models.TheoryTechnique,
    atlas_models.TheoryTechniqueSource,
    atlas_models.TheoryTheory,
    atlas_models.TheoryTheorySource,
    atlas_models.TimelinePsychologist,
    atlas_models.TimelinePsychologistSource,
    atlas_models.TimelineTheory,
    atlas_models.TimelineTheorySource,
    atlas_models.TimelineTherapy,
    atlas_models.TimelineTherapySource,
    atlas_models.TimelineTechnique,
    atlas_models.TimelineTechniqueSource,
    atlas_models.TimelineConcept,
    atlas_models.TimelineConceptSource,
)


V095_GRAPH_MODELS = (
    atlas_models.BrainAnatomicalEntity,
    atlas_models.BrainAnatomicalAlias,
    atlas_models.BrainAnatomicalEntitySource,
    atlas_models.BrainHierarchyLink,
    atlas_models.BrainHierarchyLinkSource,
    atlas_models.AssessmentInstrument,
    atlas_models.AssessmentVersion,
    atlas_models.AssessmentAlias,
    atlas_models.AssessmentSource,
)


GRAPH_MODELS = (
    Category,
    Concept,
    ConceptRelationship,
    ConceptSymptom,
    Disorder,
    DisorderConcept,
    DisorderSymptom,
    DSMCorpus,
    DSMRecord,
    DSMRecordRelation,
    SourceReference,
    Symptom,
    Technique,
    TechniqueConcept,
    TechniqueConceptSource,
    Therapy,
    TherapyClassification,
    TherapyClassificationLink,
    TherapyConcept,
    TherapyConceptSource,
    TherapyDisorder,
    TherapyDisorderSource,
    TherapyFamily,
    TherapyTechnique,
    TherapyTechniqueSource,
) + V06_GRAPH_MODELS + V095_GRAPH_MODELS

GRAPH_MODELS += (atlas_models.GovernanceRecord, atlas_models.GovernanceRevision, atlas_models.GovernanceDecision,
                atlas_models.SourceState, atlas_models.SourceSuccessor, atlas_models.ReviewPolicy,
                atlas_models.RolePolicy, atlas_models.LearningArchiveReceipt, User, Group)


def _clear_graph_cache():
    cache.set("atlas_graph_revision", uuid4().hex, timeout=None)
    cache.delete("atlas_graph")


def _clear_public_scope_cache():
    cache.set("atlas_public_rights_revision", uuid4().hex, timeout=None)
    cache.delete("atlas_public_rights_scopes")


def invalidate_graph_caches(*_args, **_kwargs):
    _clear_graph_cache()
    if _kwargs.get("sender") in (atlas_models.GovernanceRecord, atlas_models.SourceState,
                                atlas_models.LearningArchiveReceipt):
        _clear_public_scope_cache()
        transaction.on_commit(_clear_public_scope_cache, using=_kwargs.get("using"))
    # A concurrent reader may refill the old committed graph before this write commits.
    transaction.on_commit(_clear_graph_cache, using=_kwargs.get("using"))


for model in GRAPH_MODELS:
    post_save.connect(
        invalidate_graph_caches,
        sender=model,
        dispatch_uid=f"atlas.invalidate_graph_cache.save.{model._meta.label_lower}",
        weak=False,
    )
    post_delete.connect(
        invalidate_graph_caches,
        sender=model,
        dispatch_uid=f"atlas.invalidate_graph_cache.delete.{model._meta.label_lower}",
        weak=False,
    )


def invalidate_governance_authority(sender, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        invalidate_graph_caches(using=kwargs.get("using"))


for relationship in (User.user_permissions.through, User.groups.through, Group.permissions.through):
    m2m_changed.connect(invalidate_governance_authority, sender=relationship,
                        dispatch_uid=f"atlas.governance_authority.{relationship._meta.label_lower}", weak=False)
