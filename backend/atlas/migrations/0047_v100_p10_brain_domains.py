"""P10 add-only Brain CMS anchors; historical backfill never implies reviewed."""
import hashlib,json
from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations,models

NEW_MODELS = {
    "brain-anatomical-entity": "BrainAnatomicalEntity",
    "brain-network": "BrainNetwork",
    "brain-anatomical-alias": "BrainAnatomicalAlias",
    "brain-network-alias": "BrainNetworkAlias",
    "brain-anatomical-entity-source": "BrainAnatomicalEntitySource",
    "brain-network-source": "BrainNetworkSource",
    "brain-external-identifier": "BrainExternalIdentifier",
    "brain-hierarchy-link": "BrainHierarchyLink",
    "brain-hierarchy-link-source": "BrainHierarchyLinkSource",
    "brain-network-membership": "BrainNetworkMembership",
    "brain-functional-association": "BrainFunctionalAssociation",
    "brain-network-membership-source": "BrainNetworkMembershipSource",
    "brain-functional-association-source": "BrainFunctionalAssociationSource",
}
P09_KINDS = (
    "psychologist",
    "psychologist-alias",
    "psychologist-source",
    "psychologist-theory",
    "psychologist-theory-source",
    "psychologist-concept",
    "psychologist-concept-source",
    "psychologist-therapy",
    "psychologist-therapy-source",
    "psychologist-psychologist",
    "psychologist-psychologist-source",
    "theory",
    "theory-alias",
    "theory-source",
    "theory-concept",
    "theory-concept-source",
    "theory-therapy",
    "theory-therapy-source",
    "theory-technique",
    "theory-technique-source",
    "theory-theory",
    "theory-theory-source",
    "timeline-event",
    "timeline-event-source",
    "timeline-psychologist",
    "timeline-psychologist-source",
    "timeline-theory",
    "timeline-theory-source",
    "timeline-therapy",
    "timeline-therapy-source",
    "timeline-technique",
    "timeline-technique-source",
    "timeline-concept",
    "timeline-concept-source",
 )
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
KINDS = (*P07_KINDS,*P08_KINDS,*P09_KINDS,*NEW_MODELS)
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
  raise RuntimeError("P10 retained scientific Brain anchor history cannot reverse; restore a verified backup.")

class Migration(migrations.Migration):
 dependencies=[("atlas","0046_v100_p09_history_domains")]
 operations=[
  migrations.RemoveConstraint(model_name="contentstate",name="ck_cms_content_kind"),
  migrations.AlterField(model_name="contentstate",name="kind",field=models.CharField(
   max_length=48,choices=[(kind,kind.replace("-"," ").title()) for kind in KINDS])),
  migrations.AddConstraint(model_name="contentstate",constraint=models.CheckConstraint(
   condition=models.Q(kind__in=KINDS),name="ck_cms_content_kind")),
  migrations.RunPython(backfill,guard_reverse),
 ]
