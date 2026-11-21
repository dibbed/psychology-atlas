"""Add typed P07 anchors without changing any retained Category/Disorder history."""
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models


KINDS = (
    "category", "disorder", "symptom", "disorder-symptom", "differential-relationship", "disorder-source",
    "concept", "concept-relationship", "concept-alias", "concept-relationship-source", "concept-symptom",
    "concept-symptom-source", "disorder-concept", "concept-source", "dsm-corpus", "dsm-record", "dsm-record-relation",
)

# Frozen historical fields; migrations must not import the evolving runtime registry.
DEFINITIONS = {
    'symptom': ('Symptom', ('slug', 'name_en', 'name_fa', 'description', 'domain')),
    'disorder-symptom': ('DisorderSymptom', ('disorder_id', 'symptom_id', 'prominence', 'note', 'sort_order')),
    'differential-relationship': ('DifferentialRelationship', ('disorder_id', 'related_disorder_id', 'relationship_type', 'explanation')),
    'disorder-source': ('DisorderSource', ('disorder_id', 'source_id', 'note')),
    'concept': ('Concept', ('slug', 'name_en', 'name_fa', 'simple_definition', 'academic_definition', 'example', 'counterexample', 'recognition_cues', 'common_confusions', 'kind', 'domain', 'subtype', 'is_active')),
    'concept-relationship': ('ConceptRelationship', ('source_concept_id', 'target_concept_id', 'relationship_type', 'explanation')),
    'concept-alias': ('ConceptAlias', ('concept_id', 'text', 'language', 'alias_type')),
    'concept-relationship-source': ('ConceptRelationshipSource', ('relationship_id', 'source_id', 'note')),
    'concept-symptom': ('ConceptSymptom', ('concept_id', 'symptom_id', 'relationship_type', 'explanation', 'sort_order')),
    'concept-symptom-source': ('ConceptSymptomSource', ('relationship_id', 'source_id', 'note')),
    'disorder-concept': ('DisorderConcept', ('disorder_id', 'concept_id', 'role', 'explanation', 'sort_order')),
    'concept-source': ('ConceptSource', ('concept_id', 'source_id', 'note')),
    'dsm-corpus': ('DSMCorpus', ('key', 'title', 'version_name', 'version_date', 'language', 'purpose', 'copyright_note', 'clinical_note', 'source_filename', 'source_sha256', 'official_status', 'source_registry', 'quality_audit', 'stats', 'study_guide', 'urgent_warnings', 'cultural_note', 'periodic_review', 'release_updates', 'health_check', 'metadata', 'is_active')),
    'dsm-record': ('DSMRecord', ('corpus_id', 'master_id', 'parent_id', 'linked_disorder_id', 'sort_index', 'root_section', 'chapter_number', 'chapter_name_fa', 'chapter_name_en', 'group_name', 'name_fa', 'name_en', 'source_type', 'classification_status', 'display_type', 'specialization_level', 'summary', 'key_features', 'assessment', 'differential', 'comorbidity', 'course', 'management', 'assessment_tools', 'context_considerations', 'red_flags', 'pitfalls', 'nearby_titles', 'official_updates', 'homonym_info', 'prevalence_numeric', 'prevalence_policy', 'coding', 'source_keys', 'quality', 'exam_tip', 'self_test', 'structural_path', 'is_active')),
    'dsm-record-relation': ('DSMRecordRelation', ('source_id', 'target_id', 'relationship_type', 'explanation')),
}

AUTHORABLE = {
    'symptom': ('name_en', 'name_fa', 'description', 'domain'),
    'disorder-symptom': ('disorder', 'symptom', 'prominence', 'note', 'sort_order'),
    'differential-relationship': ('disorder', 'related_disorder', 'relationship_type', 'explanation'),
    'disorder-source': ('disorder', 'source', 'note'),
    'concept': ('name_en', 'name_fa', 'simple_definition', 'academic_definition', 'example', 'counterexample', 'recognition_cues', 'common_confusions', 'kind', 'domain', 'subtype'),
    'concept-relationship': ('source_concept', 'target_concept', 'relationship_type', 'explanation'),
    'concept-alias': ('concept', 'text', 'language', 'alias_type'),
    'concept-relationship-source': ('relationship', 'source', 'note'),
    'concept-symptom': ('concept', 'symptom', 'relationship_type', 'explanation', 'sort_order'),
    'concept-symptom-source': ('relationship', 'source', 'note'),
    'disorder-concept': ('disorder', 'concept', 'role', 'explanation', 'sort_order'),
    'concept-source': ('concept', 'source', 'note'),
    'dsm-corpus': ('title', 'version_name', 'version_date', 'language', 'purpose', 'copyright_note', 'clinical_note', 'official_status', 'source_registry', 'quality_audit', 'stats', 'study_guide', 'urgent_warnings', 'cultural_note', 'periodic_review', 'release_updates', 'health_check', 'metadata'),
    'dsm-record': ('corpus', 'parent', 'linked_disorder', 'sort_index', 'root_section', 'chapter_number', 'chapter_name_fa', 'chapter_name_en', 'group_name', 'name_fa', 'name_en', 'source_type', 'classification_status', 'display_type', 'specialization_level', 'summary', 'key_features', 'assessment', 'differential', 'comorbidity', 'course', 'management', 'assessment_tools', 'context_considerations', 'red_flags', 'pitfalls', 'nearby_titles', 'official_updates', 'homonym_info', 'prevalence_numeric', 'prevalence_policy', 'coding', 'source_keys', 'quality', 'exam_tip', 'self_test', 'structural_path'),
    'dsm-record-relation': ('source', 'target', 'relationship_type', 'explanation'),
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), cls=DjangoJSONEncoder).encode()).hexdigest()


def backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    State = apps.get_model("atlas", "ContentState")
    Revision = apps.get_model("atlas", "ContentRevision")
    for kind, (model_name, fields) in DEFINITIONS.items():
        Model = apps.get_model("atlas", model_name)
        for obj in Model.objects.using(alias).order_by("pk").iterator():
            if State.objects.using(alias).filter(kind=kind, canonical_pk=obj.pk).exists():
                continue
            snapshot = {key: getattr(obj, key) for key in fields}
            payload = {key: getattr(obj, Model._meta.get_field(key).attname) for key in AUTHORABLE[kind]}
            payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
            state = State.objects.using(alias).create(kind=kind, canonical_pk=obj.pk, canonical_digest=fingerprint(snapshot),
                legacy_origin=True, publication="current" if getattr(obj, "is_active", True) else "never_published")
            revision = Revision.objects.using(alias).create(state_id=state.pk, sequence=0, base_version=0,
                base_digest=state.canonical_digest, payload=payload, payload_digest=fingerprint(payload),
                dependency_digest=fingerprint({}), status="legacy", intent="edit")
            State.objects.using(alias).filter(pk=state.pk).update(current_revision_id=revision.pk)


def guard_reverse(apps, schema_editor):
    alias = schema_editor.connection.alias
    State = apps.get_model("atlas", "ContentState")
    Revision = apps.get_model("atlas", "ContentRevision")
    Event = apps.get_model("atlas", "AdminAuditEvent")
    if (State.objects.using(alias).exclude(kind__in=("category", "disorder")).exists()
            or Revision.objects.using(alias).exclude(intent="edit").exists()
            or Event.objects.using(alias).filter(target_kind__in=KINDS[2:]).exists()):
        raise RuntimeError("P07 retained content/audit history cannot be represented by 0043; restore a verified backup instead.")


class Migration(migrations.Migration):
    dependencies = [("atlas", "0043_v100_p06_artifact_cleanup")]

    operations = [
        migrations.RemoveConstraint(model_name="contentstate", name="ck_cms_content_kind"),
        migrations.AlterField(model_name="contentstate", name="kind", field=models.CharField(max_length=48,
            choices=[(kind, kind.replace("-", " ").title()) for kind in KINDS])),
        migrations.AddConstraint(model_name="contentstate", constraint=models.CheckConstraint(condition=models.Q(kind__in=KINDS), name="ck_cms_content_kind")),
        migrations.AlterField(model_name="adminauditevent", name="target_kind", field=models.CharField(blank=True, max_length=48)),
        migrations.AddField(model_name="contentrevision", name="intent", field=models.CharField(max_length=16,
            choices=[("edit", "Edit"), ("archive", "Archive proposal")], default="edit")),
        migrations.AddConstraint(model_name="contentrevision", constraint=models.CheckConstraint(condition=models.Q(intent__in=("edit", "archive")), name="ck_cms_revision_intent")),
        migrations.RunPython(backfill, guard_reverse),
    ]
