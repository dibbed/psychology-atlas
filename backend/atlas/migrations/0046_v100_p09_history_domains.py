"""P09 add-only History CMS anchors; historical backfill never implies reviewed."""
import hashlib,json
from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations,models

NEW_MODELS = {
    "psychologist": "Psychologist",
    "psychologist-alias": "PsychologistAlias",
    "psychologist-source": "PsychologistSource",
    "psychologist-theory": "PsychologistTheory",
    "psychologist-theory-source": "PsychologistTheorySource",
    "psychologist-concept": "PsychologistConcept",
    "psychologist-concept-source": "PsychologistConceptSource",
    "psychologist-therapy": "PsychologistTherapy",
    "psychologist-therapy-source": "PsychologistTherapySource",
    "psychologist-psychologist": "PsychologistPsychologist",
    "psychologist-psychologist-source": "PsychologistPsychologistSource",
    "theory": "Theory",
    "theory-alias": "TheoryAlias",
    "theory-source": "TheorySource",
    "theory-concept": "TheoryConcept",
    "theory-concept-source": "TheoryConceptSource",
    "theory-therapy": "TheoryTherapy",
    "theory-therapy-source": "TheoryTherapySource",
    "theory-technique": "TheoryTechnique",
    "theory-technique-source": "TheoryTechniqueSource",
    "theory-theory": "TheoryTheory",
    "theory-theory-source": "TheoryTheorySource",
    "timeline-event": "TimelineEvent",
    "timeline-event-source": "TimelineEventSource",
    "timeline-psychologist": "TimelinePsychologist",
    "timeline-psychologist-source": "TimelinePsychologistSource",
    "timeline-theory": "TimelineTheory",
    "timeline-theory-source": "TimelineTheorySource",
    "timeline-therapy": "TimelineTherapy",
    "timeline-therapy-source": "TimelineTherapySource",
    "timeline-technique": "TimelineTechnique",
    "timeline-technique-source": "TimelineTechniqueSource",
    "timeline-concept": "TimelineConcept",
    "timeline-concept-source": "TimelineConceptSource",
}
P07_KINDS = (
 "category","disorder","symptom","disorder-symptom","differential-relationship","disorder-source",
 "concept","concept-relationship","concept-alias","concept-relationship-source","concept-symptom",
 "concept-symptom-source","disorder-concept","concept-source","dsm-corpus","dsm-record","dsm-record-relation",
)
P08_KINDS = (
 "therapy-family","therapy-classification","therapy","technique","therapy-classification-link",
 "therapy-disorder","therapy-technique","therapy-concept","technique-concept","therapy-alias",
 "technique-alias","therapy-source","technique-source","therapy-technique-source",
 "therapy-disorder-source","therapy-concept-source","technique-concept-source",
)
KINDS = (*P07_KINDS,*P08_KINDS,*NEW_MODELS)
SYSTEM = {"id","created_at","updated_at","review_status","is_active","seed_managed"}
IMMUTABLE_ID = {"slug","key","master_id"}

def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
   separators=(",",":"),cls=DjangoJSONEncoder).encode()).hexdigest()

def backfill(apps,schema_editor):
 alias=schema_editor.connection.alias
 State=apps.get_model("atlas","ContentState")
 Revision=apps.get_model("atlas","ContentRevision")
 for kind,name in NEW_MODELS.items():
  Model=apps.get_model("atlas",name)
  fields=[f for f in Model._meta.concrete_fields if f.name not in {"id","created_at","updated_at"}]
  payload_fields=[f for f in fields if f.name not in SYSTEM | IMMUTABLE_ID]
  for obj in Model.objects.using(alias).order_by("pk").iterator():
   if State.objects.using(alias).filter(kind=kind,canonical_pk=obj.pk).exists(): continue
   snapshot={f.attname:getattr(obj,f.attname) for f in fields}
   payload={f.name:getattr(obj,f.attname) for f in payload_fields}
   payload=json.loads(json.dumps(payload,cls=DjangoJSONEncoder))
   state=State.objects.using(alias).create(kind=kind,canonical_pk=obj.pk,
    canonical_digest=digest(snapshot),legacy_origin=True,
    publication="current" if getattr(obj,"is_active",True) else "never_published")
   revision=Revision.objects.using(alias).create(state_id=state.pk,sequence=0,base_version=0,
    base_digest=state.canonical_digest,payload=payload,payload_digest=digest(payload),
    dependency_digest=digest({}),status="legacy",intent="edit")
   State.objects.using(alias).filter(pk=state.pk).update(current_revision_id=revision.pk)

def guard_reverse(apps,schema_editor):
 State=apps.get_model("atlas","ContentState")
 if State.objects.using(schema_editor.connection.alias).filter(kind__in=NEW_MODELS).exists():
  raise RuntimeError("P09 retained chronology/attribution history cannot reverse; restore a verified backup.")

class Migration(migrations.Migration):
 dependencies=[("atlas","0045_v100_p08_therapy_domains")]
 operations=[
  migrations.RemoveConstraint(model_name="contentstate",name="ck_cms_content_kind"),
  migrations.AlterField(model_name="contentstate",name="kind",field=models.CharField(
   max_length=48,choices=[(kind,kind.replace("-"," ").title()) for kind in KINDS])),
  migrations.AddConstraint(model_name="contentstate",constraint=models.CheckConstraint(
   condition=models.Q(kind__in=KINDS),name="ck_cms_content_kind")),
  migrations.RunPython(backfill,guard_reverse),
 ]
