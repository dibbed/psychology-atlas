"""P08 additive typed anchors for therapy/technique. Preserves all canonical and user-owned data."""
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models

NEW_MODELS = {
    "therapy-family": "TherapyFamily",
    "therapy-classification": "TherapyClassification",
    "therapy": "Therapy",
    "technique": "Technique",
    "therapy-classification-link": "TherapyClassificationLink",
    "therapy-disorder": "TherapyDisorder",
    "therapy-technique": "TherapyTechnique",
    "therapy-concept": "TherapyConcept",
    "technique-concept": "TechniqueConcept",
    "therapy-alias": "TherapyAlias",
    "technique-alias": "TechniqueAlias",
    "therapy-source": "TherapySource",
    "technique-source": "TechniqueSource",
    "therapy-technique-source": "TherapyTechniqueSource",
    "therapy-disorder-source": "TherapyDisorderSource",
    "therapy-concept-source": "TherapyConceptSource",
    "technique-concept-source": "TechniqueConceptSource",
}
P07_KINDS = (
    "category", "disorder", "symptom", "disorder-symptom", "differential-relationship", "disorder-source",
    "concept", "concept-relationship", "concept-alias", "concept-relationship-source", "concept-symptom",
    "concept-symptom-source", "disorder-concept", "concept-source", "dsm-corpus", "dsm-record", "dsm-record-relation",
)
KINDS = (*P07_KINDS, *NEW_MODELS)

# Schema-vintage authoring includes only canonical editorial fields, not review/visibility.
EXCLUDE = {"id", "created_at", "updated_at", "review_status", "is_active", "seed_managed"}
IDENTITY = {"slug", "key", "master_id"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), cls=DjangoJSONEncoder).encode()).hexdigest()


def backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    State = apps.get_model("atlas", "ContentState")
    Revision = apps.get_model("atlas", "ContentRevision")
    for kind, model_name in NEW_MODELS.items():
        Model = apps.get_model("atlas", model_name)
        fields = [f for f in Model._meta.concrete_fields if f.name not in {"id", "created_at", "updated_at"}]
        payload_fields = [f for f in fields if f.name not in EXCLUDE | IDENTITY]
        for obj in Model.objects.using(alias).order_by("pk").iterator():
            if State.objects.using(alias).filter(kind=kind, canonical_pk=obj.pk).exists():
                continue
            snapshot = {f.attname: getattr(obj, f.attname) for f in fields}
            payload = {f.name: getattr(obj, f.attname) for f in payload_fields}
            payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
            state = State.objects.using(alias).create(
                kind=kind, canonical_pk=obj.pk, canonical_digest=digest(snapshot),
                legacy_origin=True, publication="current" if getattr(obj, "is_active", True) else "never_published")
            rev = Revision.objects.using(alias).create(
                state_id=state.pk, sequence=0, base_version=0, base_digest=state.canonical_digest,
                payload=payload, payload_digest=digest(payload), dependency_digest=digest({}),
                status="legacy", intent="edit")
            State.objects.using(alias).filter(pk=state.pk).update(current_revision_id=rev.pk)


def reverse_guard(apps, schema_editor):
    State = apps.get_model("atlas", "ContentState")
    if State.objects.using(schema_editor.connection.alias).filter(kind__in=NEW_MODELS).exists():
        raise RuntimeError("P08 retained therapy/technique history cannot be reversed without a verified backup.")


class Migration(migrations.Migration):
    dependencies = [("atlas", "0044_v100_p07_content_domains")]
    operations = [
        migrations.RemoveConstraint(model_name="contentstate", name="ck_cms_content_kind"),
        migrations.AlterField(model_name="contentstate", name="kind",
            field=models.CharField(max_length=48, choices=[(kind, kind.replace("-", " ").title()) for kind in KINDS])),
        migrations.AddConstraint(model_name="contentstate", constraint=models.CheckConstraint(
            condition=models.Q(kind__in=KINDS), name="ck_cms_content_kind")),
        migrations.RunPython(backfill, reverse_guard),
    ]
