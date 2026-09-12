from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

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
) + V06_GRAPH_MODELS


def invalidate_graph_caches(*_args, **_kwargs):
    cache.delete("atlas_graph")


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
