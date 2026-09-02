from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

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
    Symptom,
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
    Symptom,
)


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
