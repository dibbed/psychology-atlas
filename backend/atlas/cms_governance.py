"""Exact scoped decisions with P04 authority and source-writer lock ordering."""
import json
import uuid
from copy import copy
from datetime import date

from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.db.models import F, Q
from django.utils import timezone

from . import models as canonical
from .cms_audit import REVIEW_REASONS, attribution
from .cms_content import digest
from .cms_governance_models import GovernanceDecision, GovernanceRecord, GovernanceRevision
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_review import current_policy, reviewer_conflict
from .cms_sessions import current_session


# Model, capability domain, EN/FA label fields, stable edition field, declared canonical parents.
REGISTRY = {
    "source_reference": (canonical.SourceReference, "source", "title", None, None, ()),
    "category": (canonical.Category, "core", "name_en", "name_fa", None, ()),
    "disorder": (canonical.Disorder, "core", "name_en", "name_fa", None, (("category", "category"),)),
    "symptom": (canonical.Symptom, "core", "name_en", "name_fa", None, ()),
    "concept": (canonical.Concept, "core", "name_en", "name_fa", None, ()),
    "dsm_record": (canonical.DSMRecord, "dsm", "name_en", "name_fa", "master_id", ()),
    "therapy": (canonical.Therapy, "therapy", "name_en", "name_fa", None, ()),
    "technique": (canonical.Technique, "therapy", "name_en", "name_fa", None, ()),
    "psychologist": (canonical.Psychologist, "history", "name_en", "name_fa", None, ()),
    "theory": (canonical.Theory, "history", "name_en", "name_fa", None, ()),
    "timeline_event": (canonical.TimelineEvent, "history", "title_en", "title_fa", None, ()),
    "clinical_case": (canonical.ClinicalCase, "cases", "title", None, None, ()),
    "flashcard": (canonical.Flashcard, "learning", "slug", None, None, ()),
    "quiz": (canonical.Quiz, "learning", "title", None, None, ()),
    "brain_anatomical_entity": (canonical.BrainAnatomicalEntity, "brain", "name_en", "name_fa", None, ()),
    "brain_network": (canonical.BrainNetwork, "brain", "name_en", "name_fa", None, ()),
    "assessment_instrument": (canonical.AssessmentInstrument, "assessment", "name_en", "name_fa", None, ()),
    "assessment_version": (canonical.AssessmentVersion, "assessment", "label", None, "key", (("instrument", "assessment_instrument"),)),
    "assessment_language_form": (canonical.AssessmentLanguageForm, "assessment", "label", None, "key", (("version", "assessment_version"),)),
    "assessment_validation_study": (canonical.AssessmentValidationStudy, "assessment", "key", None, "key", (("version", "assessment_version"), ("language_form", "assessment_language_form"), ("source", "source_reference"))),
    "assessment_psychometric_evidence": (canonical.AssessmentPsychometricEvidence, "assessment", "key", None, "key", (("study", "assessment_validation_study"),)),
    "assessment_alias": (canonical.AssessmentAlias, "assessment", "text", None, None, (("instrument", "assessment_instrument"), ("version", "assessment_version"), ("source", "source_reference"))),
    "assessment_access": (canonical.AssessmentAccess, "assessment", "key", None, "key", (("version", "assessment_version"), ("language_form", "assessment_language_form"), ("source", "source_reference"))),
}
REGISTRY.update({
    "disorder_symptom": (canonical.DisorderSymptom, "core", "id", None, None, (("disorder", "disorder"), ("symptom", "symptom"))),
    "differential_relationship": (canonical.DifferentialRelationship, "core", "id", None, None, (("disorder", "disorder"), ("related_disorder", "disorder"))),
    "disorder_source": (canonical.DisorderSource, "core", "id", None, None, (("disorder", "disorder"), ("source", "source_reference"))),
    "concept_relationship": (canonical.ConceptRelationship, "core", "id", None, None, (("source_concept", "concept"), ("target_concept", "concept"))),
    "concept_alias": (canonical.ConceptAlias, "core", "text", None, None, (("concept", "concept"),)),
    "concept_relationship_source": (canonical.ConceptRelationshipSource, "core", "id", None, None, (("relationship", "concept_relationship"), ("source", "source_reference"))),
    "concept_symptom": (canonical.ConceptSymptom, "core", "id", None, None, (("concept", "concept"), ("symptom", "symptom"))),
    "concept_symptom_source": (canonical.ConceptSymptomSource, "core", "id", None, None, (("relationship", "concept_symptom"), ("source", "source_reference"))),
    "disorder_concept": (canonical.DisorderConcept, "core", "id", None, None, (("disorder", "disorder"), ("concept", "concept"))),
    "concept_source": (canonical.ConceptSource, "core", "id", None, None, (("concept", "concept"), ("source", "source_reference"))),
    "dsm_corpus": (canonical.DSMCorpus, "dsm", "title", None, "key", ()),
    "dsm_record_relation": (canonical.DSMRecordRelation, "dsm", "id", None, None, (("source", "dsm_record"), ("target", "dsm_record"))),
})
REGISTRY.update({
    "therapy_family": (canonical.TherapyFamily, "therapy", "name_en", "name_fa", None, ()),
    "therapy_classification": (canonical.TherapyClassification, "therapy", "name_en", "name_fa", None, ()),
    "therapy_classification_link": (canonical.TherapyClassificationLink, "therapy", "id", None, None, (("therapy", "therapy"), ("classification", "therapy_classification"))),
    "therapy_disorder": (canonical.TherapyDisorder, "therapy", "id", None, None, (("therapy", "therapy"), ("disorder", "disorder"))),
    "therapy_technique": (canonical.TherapyTechnique, "therapy", "id", None, None, (("therapy", "therapy"), ("technique", "technique"))),
    "therapy_concept": (canonical.TherapyConcept, "therapy", "id", None, None, (("therapy", "therapy"), ("concept", "concept"))),
    "technique_concept": (canonical.TechniqueConcept, "therapy", "id", None, None, (("technique", "technique"), ("concept", "concept"))),
    "therapy_alias": (canonical.TherapyAlias, "therapy", "text", None, None, (("therapy", "therapy"),)),
    "technique_alias": (canonical.TechniqueAlias, "therapy", "text", None, None, (("technique", "technique"),)),
    "therapy_source": (canonical.TherapySource, "therapy", "id", None, None, (("therapy", "therapy"), ("source", "source_reference"))),
    "technique_source": (canonical.TechniqueSource, "therapy", "id", None, None, (("technique", "technique"), ("source", "source_reference"))),
    "therapy_technique_source": (canonical.TherapyTechniqueSource, "therapy", "id", None, None, (("relationship", "therapy_technique"), ("source", "source_reference"))),
    "therapy_disorder_source": (canonical.TherapyDisorderSource, "therapy", "id", None, None, (("relationship", "therapy_disorder"), ("source", "source_reference"))),
    "therapy_concept_source": (canonical.TherapyConceptSource, "therapy", "id", None, None, (("relationship", "therapy_concept"), ("source", "source_reference"))),
    "technique_concept_source": (canonical.TechniqueConceptSource, "therapy", "id", None, None, (("relationship", "technique_concept"), ("source", "source_reference"))),
})
# P09 exact static model inventory, not a query-supplied model resolver.
from .cms_history_domains import FIELDS as _HISTORY_FIELDS
_history_types = {entry[0]: resource_type for resource_type, entry in REGISTRY.items()}
_history_types.update({model: kind.replace("-", "_") for kind, (model, _, _) in _HISTORY_FIELDS.items()})
for _history_kind, (_history_model, _, _) in _HISTORY_FIELDS.items():
    _name = (_history_kind.replace("-", "_"))
    _en = "title_en" if _history_kind == "timeline-event" else (
        "name_en" if _history_kind in {"psychologist", "theory"} else
        "text" if _history_kind.endswith("-alias") else "id")
    _fa = "title_fa" if _history_kind == "timeline-event" else (
        "name_fa" if _history_kind in {"psychologist", "theory"} else None)
    _parents = tuple((field.name, _history_types[field.related_model])
        for field in _history_model._meta.concrete_fields if field.is_relation
        and field.related_model in _history_types)
    REGISTRY[_name] = (_history_model, "history", _en, _fa, None, _parents)
# P10 explicit Brain resource types. No user-selected model or field resolver.
from .cms_brain_domains import FIELDS as _BRAIN_FIELDS
_brain_types = {entry[0]: resource_type for resource_type, entry in REGISTRY.items()}
_brain_types.update({model: kind.replace("-", "_") for kind, (model, _, _, _) in _BRAIN_FIELDS.items()})
for _kind, (_model, _, _, _) in _BRAIN_FIELDS.items():
    _name = _kind.replace("-", "_")
    _english = "name_en" if _kind in {"brain-anatomical-entity", "brain-network"} else ("text" if _kind.endswith("-alias") else "id")
    _farsi = "name_fa" if _kind in {"brain-anatomical-entity", "brain-network"} else None
    _version = "source_version" if _kind in {"brain-external-identifier", "brain-hierarchy-link", "brain-network-membership", "brain-functional-association"} else None
    _parents = tuple((f.name, _brain_types[f.related_model]) for f in _model._meta.concrete_fields
        if f.is_relation and f.related_model in _brain_types)
    REGISTRY[_name] = (_model, "brain", _english, _farsi, _version, _parents)
# P11 Assessment rights and source claim types; explicit registry only.
REGISTRY.update({
    "assessment_relation": (canonical.AssessmentRelation, "assessment", "id", None, "key",
        (("version", "assessment_version"), ("language_form", "assessment_language_form"),
         ("concept", "concept"), ("symptom", "symptom"), ("disorder", "disorder"))),
    "assessment_source": (canonical.AssessmentSource, "assessment", "id", None, None,
        (("instrument", "assessment_instrument"), ("version", "assessment_version"),
         ("language_form", "assessment_language_form"), ("relation", "assessment_relation"),
         ("source", "source_reference"))),
})
MATERIALS = frozenset({"metadata", "image", "text", "translation", "item", "instruction", "questionnaire", "manual"})
USES = frozenset({"public_display", "digital", "commercial", "redistribution", "derivative", "translation", "owner_access", "metadata_listing"})
RIGHTS_STATUSES = frozenset({"unknown", "allowed", "restricted", "conflict"})
WORKFLOW_STATUSES = frozenset({"submitted", "in_review", "approved", "rejected", "revoked"})
COMPUTED_STATUSES = frozenset({"unknown", "allowed", "restricted", "conflict", "expired", "revoked", "stale", "not_effective", "review_overdue", "submitted", "in_review", "approved", "rejected"})
APPROVAL_REASONS = {"rights": "RIGHTS_SCOPE_VERIFIED", "terminology": "TERMINOLOGY_SELECTED"}
COMMON = {"resource_type", "resource_id", "resource_version", "evidence", "reason"}
RIGHTS_FIELDS = {"material", "intended_use", "status", "rightsholder", "holder_identification", "holder_evidence", "public_access", "reviewed_on", "effective_on", "expires_on", "review_on", "limitations", "territory", "conflict_note"}
TERM_FIELDS = {"name_en", "name_fa", "term_kind", "alternatives", "selection_note"}


def entry(resource_type):
    if type(resource_type) is not str or resource_type not in REGISTRY:
        raise CMSFailure("NOT_FOUND", 404)
    return REGISTRY[resource_type]


def snapshot(obj):
    values = {f.attname: getattr(obj, f.attname) for f in obj._meta.concrete_fields if f.name not in {"created_at", "updated_at"}}
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def source_snapshot(source_ids, lock=False):
    from .cms_source_models import SourceState, SourceSuccessor
    if not isinstance(source_ids, (list, tuple, set)) or len(source_ids) > 1000 or any(type(i) is not int or not 0 < i < 2**63 for i in source_ids):
        raise CMSFailure("INVALID_EVIDENCE", 400)
    ids = sorted(set(source_ids))
    if lock:
        canonical.lock_brain_curation(connection.alias)
    rows = canonical.SourceReference.objects.filter(pk__in=ids).order_by("pk")
    states = SourceState.objects.filter(source_pk__in=ids).order_by("source_pk")
    successors = SourceSuccessor.objects.filter(Q(source_pk__in=ids) | Q(successor_pk__in=ids)).order_by("pk")
    if lock:
        rows, states, successors = rows.select_for_update(), states.select_for_update(), successors.select_for_update()
    sources = list(rows)
    states, successors = list(states), list(successors)
    missing = sorted(set(ids) - {s.pk for s in sources})
    unavailable = sorted({s.source_pk for s in states if s.archived or s.deleted})
    value = {"sources": [snapshot(s) for s in sources], "states": [snapshot(s) for s in states], "successors": [snapshot(s) for s in successors]}
    return {"source_ids": ids, "missing_source_ids": missing, "unavailable_source_ids": unavailable, "source_digest": digest(value)}


def target_snapshot(resource_type, resource_id, lock=False):
    model, _, _, _, _, parents = entry(resource_type)
    if type(resource_id) is not int or not 0 < resource_id < 2**63:
        raise CMSFailure("NOT_FOUND", 404)
    rows = model.objects
    if lock:
        canonical.lock_brain_curation(connection.alias)
        rows = rows.select_for_update()
    obj = rows.filter(pk=resource_id).first()
    if obj is None:
        raise CMSFailure("NOT_FOUND", 404)
    value = {"canonical": snapshot(obj), "parents": {}}
    for field, parent_type in parents:
        parent_id = getattr(obj, field + "_id")
        if parent_id:
            value["parents"][field] = target_snapshot(parent_type, parent_id, lock)[1]
    if resource_type == "dsm_record":
        corpus = canonical.DSMCorpus.objects
        if lock:
            corpus = corpus.select_for_update()
        value["parents"]["corpus"] = snapshot(corpus.get(pk=obj.corpus_id))
    if resource_type == "source_reference":
        value["source_lifecycle"] = source_snapshot([obj.pk], lock)
    return obj, value


def resource_binding(resource_type, resource_id, lock=False):
    obj, value = target_snapshot(resource_type, resource_id, lock)
    _, domain, en, fa, version_field, _ = entry(resource_type)
    resource_digest = digest(value)
    resource_version = str(getattr(obj, version_field)) if version_field else resource_digest
    if resource_type == "assessment_alias":
        resource_version = obj.version.key if obj.version_id else obj.instrument.slug
    if resource_type == "dsm_record":
        corpus = value["parents"]["corpus"]
        resource_version = f"{corpus['key']}:{corpus['version_name']}:{obj.master_id}"
    if resource_type == "dsm_corpus":
        resource_version = f"{obj.key}:{obj.version_name}:{obj.source_sha256}"
    return {"resource_type": resource_type, "resource_id": obj.pk, "domain": domain,
        "resource_version": resource_version, "resource_digest": resource_digest,
        "name_en": str(getattr(obj, en)), "name_fa": str(getattr(obj, fa)) if fa else ""}


def decision_caps(record):
    return {"cms_enter", "cms_" + record.domain + "_view", "cms_" + record.kind + "_decide", "cms_review_decide_" + record.domain + "_" + record.kind}


def conflict(reviewer, record, policy):
    # P04's exact solo-owner/two-person semantics, with retained contributor identity.
    class Subject:
        authors = [reviewer.pk] if attribution(reviewer.pk) in record.contributors else []
    reviewer_conflict(reviewer, Subject(), policy)


def evidence_ids(payload):
    return sorted({e["source_id"] for e in payload.get("evidence", []) + payload.get("holder_evidence", []) if "source_id" in e})


def evidence_artifacts(payload):
    return sorted({e["artifact_id"] for e in payload.get("evidence", []) + payload.get("holder_evidence", []) if "artifact_id" in e})


def artifact_access(actor, payload):
    ids = evidence_artifacts(payload)
    if not ids:
        return
    from .cms_artifacts import get_artifact
    for artifact_id in ids:
        get_artifact(actor, uuid.UUID(artifact_id), download=True, lock=True)


def dependency(payload, binding, lock=False):
    sources = source_snapshot(evidence_ids(payload), lock)
    value = {"resource_digest": binding["resource_digest"], "evidence": payload.get("evidence", []),
        "holder_evidence": payload.get("holder_evidence", []), "sources": sources}
    ids = evidence_artifacts(payload)
    if ids:
        from .cms_artifacts import evidence_snapshot
        # Preserve historical P05 hashes when a proposal has no private file evidence.
        value["artifacts"] = evidence_snapshot(ids, binding["resource_type"], binding["resource_id"], binding["resource_version"], lock)
    return digest(value), sources


def _text(value, limit, required=False):
    if type(value) is not str or len(value) > limit or (required and not value.strip()):
        raise CMSFailure("INVALID_FIELDS", 400)
    return value.strip()


def _choice(value, choices):
    if type(value) is not str or value not in choices:
        raise CMSFailure("INVALID_FIELDS", 400)
    return value


def _date(value):
    if value is None:
        return None
    if type(value) is not str:
        raise CMSFailure("INVALID_DATES", 400)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise CMSFailure("INVALID_DATES", 400)
    if parsed.isoformat() != value:
        raise CMSFailure("INVALID_DATES", 400)
    return value


def _evidence(value, required):
    if not isinstance(value, list) or len(value) > 20 or (required and not value):
        raise CMSFailure("EVIDENCE_REQUIRED", 400)
    result = []
    for e in value:
        if not isinstance(e, dict) or set(e) not in ({"source_id", "locator"}, {"artifact_id", "locator"}):
            raise CMSFailure("INVALID_EVIDENCE", 400)
        item = {"locator": _text(e["locator"], 1000, True)}
        if "source_id" in e:
            if type(e["source_id"]) is not int or not 0 < e["source_id"] < 2**63:
                raise CMSFailure("INVALID_EVIDENCE", 400)
            item["source_id"] = e["source_id"]
        else:
            try:
                if type(e["artifact_id"]) is not str:
                    raise ValueError
                item["artifact_id"] = str(uuid.UUID(e["artifact_id"]))
            except (ValueError, TypeError, AttributeError):
                raise CMSFailure("INVALID_EVIDENCE", 400)
        result.append(item)
    return result


def validate_payload(kind, data, lock=False):
    fields = COMMON | (RIGHTS_FIELDS if kind == "rights" else TERM_FIELDS)
    if kind not in {"rights", "terminology"} or not isinstance(data, dict) or set(data) - fields:
        raise CMSFailure("INVALID_FIELDS", 400)
    binding = resource_binding(data.get("resource_type"), data.get("resource_id"), lock)
    version = _text(data.get("resource_version"), 500, True)
    if version != binding["resource_version"]:
        raise CMSFailure("RESOURCE_VERSION_CHANGED", 409)
    result = {"resource_type": binding["resource_type"], "resource_id": binding["resource_id"], "resource_version": version,
        "reason": _choice(data.get("reason", "CORRECTION_REQUIRED"), REVIEW_REASONS)}
    if kind == "rights":
        status = _choice(data.get("status", "unknown"), RIGHTS_STATUSES)
        established = status == "allowed"
        result.update({"status": status, "material": _choice(data.get("material"), MATERIALS),
            "intended_use": _choice(data.get("intended_use"), USES), "public_access": _choice(data.get("public_access", "unknown"), {"unknown", "public", "private"}),
            "rightsholder": _text(data.get("rightsholder", ""), 1000, established),
            "holder_identification": _text(data.get("holder_identification", ""), 1000, established),
            "holder_evidence": _evidence(data.get("holder_evidence", []), established),
            "limitations": _text(data.get("limitations", ""), 4000, established), "territory": _text(data.get("territory", ""), 255),
            "conflict_note": _text(data.get("conflict_note", ""), 4000, status == "conflict")})
        for field in ("reviewed_on", "effective_on", "expires_on", "review_on"):
            result[field] = _date(data.get(field))
        if established and not all(result[f] for f in ("reviewed_on", "effective_on")):
            raise CMSFailure("INVALID_DATES", 400)
        if result["reviewed_on"] and result["reviewed_on"] > timezone.localdate().isoformat():
            raise CMSFailure("INVALID_DATES", 400)
        if any(result[f] and (not result["effective_on"] or result[f] < result["effective_on"]) for f in ("expires_on", "review_on")):
            raise CMSFailure("INVALID_DATES", 400)
        result["evidence"] = _evidence(data.get("evidence", []), established)
    else:
        alternatives = data.get("alternatives", [])
        if not isinstance(alternatives, list) or len(alternatives) > 20:
            raise CMSFailure("INVALID_FIELDS", 400)
        alternatives = [_text(t, 500, True) for t in alternatives]
        if len(set(alternatives)) != len(alternatives):
            raise CMSFailure("INVALID_FIELDS", 400)
        result.update({"name_en": _text(data.get("name_en"), 500, True), "name_fa": _text(data.get("name_fa"), 500, True),
            "term_kind": _choice(data.get("term_kind"), {"display", "alias"}), "alternatives": alternatives,
            "selection_note": _text(data.get("selection_note"), 4000, True), "evidence": _evidence(data.get("evidence"), True)})
    dep, sources = dependency(result, binding, lock)
    if sources["missing_source_ids"]:
        raise CMSFailure("INVALID_EVIDENCE", 400)
    if sources["unavailable_source_ids"]:
        raise CMSFailure("SOURCE_UNAVAILABLE", 409)
    return result, binding, dep, sources


def freshness(record, lock=False):
    revision = record.current_revision
    if revision is None:
        return ["APPROVAL_REQUIRED"]
    blockers = []
    policy = current_policy()
    if (revision.policy_version, revision.policy_mode) != (policy.version, policy.mode):
        blockers.append("POLICY_CHANGED")
    if digest(revision.payload) != revision.payload_digest or revision.payload.get("resource_version") != record.resource_version:
        blockers.append("PAYLOAD_CHANGED")
    try:
        binding = resource_binding(record.resource_type, record.resource_id, lock)
        if binding["resource_version"] != record.resource_version:
            blockers.append("RESOURCE_VERSION_CHANGED")
        if binding["resource_digest"] != revision.resource_digest:
            blockers.append("RESOURCE_CHANGED")
        dep, sources = dependency(revision.payload, binding, lock)
        if dep != revision.dependency_digest:
            blockers.append("DEPENDENCY_CHANGED")
        if sources["missing_source_ids"]:
            blockers.append("EVIDENCE_MISSING")
        if sources["unavailable_source_ids"]:
            blockers.append("SOURCE_UNAVAILABLE")
    except CMSFailure as error:
        blockers.append("RESOURCE_MISSING" if error.status_code == 404 else str(error.detail["code"]))
    if record.status in {"in_review", "approved"}:
        if record.assignee is None:
            blockers.append("REVIEWER_UNAVAILABLE")
        elif not decision_caps(record) <= effective_permissions(record.assignee):
            blockers.append("REVIEWER_PERMISSION_CHANGED")
        else:
            try:
                conflict(record.assignee, record, policy)
            except CMSFailure as error:
                blockers.append(str(error.detail["code"]))
        if revision.assignee_ref != attribution(record.assignee_id):
            blockers.append("REVIEWER_CHANGED")
    if record.status == "approved":
        decision = record.decisions.filter(revision=revision, outcome="approve").order_by("-pk").first()
        if (decision is None or decision.outcome != "approve" or decision.revision_id != revision.pk
                or decision.actor_ref != attribution(record.assignee_id) or decision.assignee_ref != revision.assignee_ref
                or decision.revision_hash != revision.payload_digest or decision.dependency_digest != revision.dependency_digest
                or (decision.policy_version, decision.policy_mode) != (revision.policy_version, revision.policy_mode)
                or (attribution(record.assignee_id) in record.contributors and not decision.self_review)):
            blockers.append("DECISION_REQUIRED")
    return sorted(set(blockers))


def eligibility(record, lock=False):
    blockers = freshness(record, lock)
    if record.status == "revoked":
        return {"eligible": False, "status": "revoked", "blockers": sorted(set(blockers + ["RIGHTS_REVOKED"]))}
    if blockers:
        return {"eligible": False, "status": "stale", "blockers": blockers}
    if record.kind == "terminology":
        return {"eligible": record.status == "approved", "status": record.status,
            "blockers": [] if record.status == "approved" else ["APPROVAL_REQUIRED"]}
    payload = record.current_revision.payload
    today = timezone.localdate().isoformat()
    for field, compare, status, blocker in (("expires_on", "past", "expired", "RIGHTS_EXPIRED"), ("review_on", "past", "review_overdue", "RIGHTS_REVIEW_OVERDUE"), ("effective_on", "future", "not_effective", "RIGHTS_NOT_EFFECTIVE")):
        value = payload.get(field)
        if value and ((value < today) if compare == "past" else (value > today)):
            return {"eligible": False, "status": status, "blockers": [blocker]}
    status = payload["status"]
    if record.status != "approved":
        return {"eligible": False, "status": status if status != "allowed" else "unknown", "blockers": ["APPROVAL_REQUIRED"]}
    return {"eligible": status == "allowed", "status": status, "blockers": [] if status == "allowed" else ["RIGHTS_" + status.upper()]}


def effective_record(record):
    """Only a reviewer decision changes the public gate; editing/reopening retains it."""
    decision = record.decisions.filter(outcome__in=("approve", "revoked")).select_related("revision", "actor").order_by("-pk").first()
    if decision is None:
        return None
    effective = copy(record)
    effective.current_revision = decision.revision
    effective.resource_version = decision.revision.payload["resource_version"]
    effective.status = "revoked" if decision.outcome == "revoked" else "approved"
    effective.assignee = decision.actor
    effective.contributors = sorted(set(record.revisions.filter(sequence__lte=decision.revision.sequence,
        action__in=("create", "update")).values_list("actor_ref", flat=True)))
    return effective


def rights_eligibility(resource_type, resource_id, resource_version, material, intended_use, lock=False):
    entry(resource_type)
    if type(resource_id) is not int or not 0 < resource_id < 2**63 or type(resource_version) is not str or material not in MATERIALS or intended_use not in USES:
        raise CMSFailure("INVALID_FIELDS", 400)
    with policy_lock():
        rows = GovernanceRecord.objects.filter(kind="rights", resource_type=resource_type, resource_id=resource_id, material=material, intended_use=intended_use).select_related("current_revision", "assignee").order_by("pk")
        if lock:
            canonical.lock_brain_curation(connection.alias)
            rows = rows.select_for_update(of=("self",))
        records = [effective for record in rows if (effective := effective_record(record)) is not None]
        base = {"registered": bool(records), "record_ids": [str(r.pk) for r in records]}
        if not records:
            return {**base, "eligible": True, "permitted": False, "status": "legacy", "blockers": []}
        states = [eligibility(r, lock) if r.resource_version == resource_version else {"eligible": False, "status": "stale", "blockers": ["RESOURCE_VERSION_CHANGED"]} for r in records]
        statuses = {s["status"] for s in states}
        conflict_found = "conflict" in statuses or {"allowed", "restricted"} <= statuses
        allowed = all(s["eligible"] for s in states) and not conflict_found
        status = "conflict" if conflict_found else next((s for s in ("revoked", "stale", "expired", "review_overdue", "not_effective", "restricted", "unknown", "allowed") if s in statuses), "unknown")
        blockers = sorted({b for s in states for b in s["blockers"]} | ({"RIGHTS_CONFLICT"} if conflict_found else set()))
        return {**base, "eligible": allowed, "permitted": allowed, "status": status, "blockers": blockers}


def governance_dependency_snapshot(source_ids, lock=False, resource_type=None, resource_id=None):
    if (resource_type is None) != (resource_id is None):
        raise CMSFailure("INVALID_FIELDS", 400)
    if resource_type is not None:
        entry(resource_type)
        if type(resource_id) is not int or not 0 < resource_id < 2**63:
            raise CMSFailure("INVALID_FIELDS", 400)
    with policy_lock():
        sources = source_snapshot(source_ids, lock)
        # JSON containment differs on SQLite; typed scopes are selected first, evidence matched in Python.
        rows = GovernanceRecord.objects.select_related("current_revision", "assignee").order_by("pk")
        if lock:
            rows = rows.select_for_update(of=("self",))
        ids = set(sources["source_ids"])
        affected = []
        for record in rows:
            revision = record.current_revision
            effective = effective_record(record) if record.kind == "rights" else None
            exact = resource_type is not None and record.resource_type == resource_type and record.resource_id == resource_id
            source_target = record.resource_type == "source_reference" and record.resource_id in ids
            matched_ids = set(revision.source_ids) if revision is not None else set()
            if effective is not None:
                matched_ids.update(effective.current_revision.source_ids)
            if revision is None or not (exact or source_target or ids.intersection(matched_ids)):
                continue
            affected.append({"id": str(record.pk), "kind": record.kind, "resource_type": record.resource_type,
                "resource_id": record.resource_id, "resource_version": record.resource_version, "material": record.material,
                "intended_use": record.intended_use, "term_kind": record.term_kind, "version": record.version,
                "revision": revision.pk, "payload_digest": revision.payload_digest, "dependency_digest": revision.dependency_digest,
                "assignee_ref": attribution(record.assignee_id), "reviewer_caps": sorted(effective_permissions(record.assignee)),
                "policy": {"version": current_policy().version, "mode": current_policy().mode}, "computed": eligibility(record, lock),
                "effective_revision": effective.current_revision_id if effective else None,
                "effective_computed": eligibility(effective, lock) if effective else None})
        governance_digest = digest(affected)
        return {"source_ids": sources["source_ids"], "missing_source_ids": sources["missing_source_ids"],
            "source_digest": sources["source_digest"], "governance_digest": governance_digest,
            "digest": digest({"source_digest": sources["source_digest"], "governance_digest": governance_digest})}


def resolve(actor, kind, record_id, lock=False):
    if kind not in {"rights", "terminology"}:
        raise CMSFailure("NOT_FOUND", 404)
    rows = GovernanceRecord.objects.filter(kind=kind).select_related("current_revision", "assignee")
    if lock:
        rows = rows.select_for_update(of=("self",))
    record = rows.filter(pk=record_id).first()
    if record is None or "cms_" + record.domain + "_view" not in effective_permissions(actor):
        raise CMSFailure("NOT_FOUND", 404)
    if record.domain != entry(record.resource_type)[1]:
        raise CMSFailure("NOT_FOUND", 404)
    return record


def advance(record, actor, payload, action, reason, policy, binding=None, dep=None):
    old = record.current_revision
    new = GovernanceRevision.objects.create(record=record, sequence=record.version + 1, payload=payload,
        payload_digest=digest(payload), resource_digest=binding["resource_digest"] if binding else old.resource_digest,
        dependency_digest=dep if dep is not None else old.dependency_digest, source_ids=evidence_ids(payload),
        status=record.status, assignee_ref=attribution(record.assignee_id), policy_version=policy.version,
        policy_mode=policy.mode, actor=actor, actor_ref=attribution(actor.pk), action=action, reason=reason)
    changes = {"version": F("version") + 1, "current_revision": new, "status": record.status, "assignee": record.assignee,
        "contributors": record.contributors, "resource_version": payload["resource_version"]}
    if GovernanceRecord.objects.filter(pk=record.pk, version=record.version).update(**changes) != 1:
        raise CMSFailure("STALE_REVISION", 412)
    actions = {"create": "review.submitted", "update": "revision.created", "assign": "review.assigned", "decide": "review.decided", "revoke": "review.invalidated", "reopen": "review.reopened"}
    audit_reason = reason if reason in REVIEW_REASONS else {"create": "REVIEW_SUBMIT", "assign": "REVIEW_ASSIGN", "reopen": "REVIEW_REOPEN"}.get(action, "CORRECTION_REQUIRED")
    AdminAuditEvent.objects.create(actor=actor, action=actions[action], outcome="success", target_kind="", target_key=str(record.pk),
        base_revision=record.version, new_revision=new.sequence, reason=audit_reason, policy_version=policy.version,
        request_id=record._request_id)
    record.refresh_from_db()
    return record


def decision_record(record, actor, outcome, reason, policy, self_review=False):
    revision = record.current_revision
    return GovernanceDecision.objects.create(record=record, revision=revision, actor=actor, actor_ref=attribution(actor.pk),
        assignee_ref=attribution(record.assignee_id), outcome=outcome, reason=reason, self_review=self_review,
        revision_hash=revision.payload_digest, dependency_digest=revision.dependency_digest, policy_version=policy.version,
        policy_mode=policy.mode, supersedes=record.decisions.order_by("-pk").first())


def create_governance(actor_id, session_id, kind, data, request_id):
    with policy_lock():
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_enter")
        if not isinstance(data, dict):
            raise CMSFailure("INVALID_FIELDS", 400)
        domain = entry(data.get("resource_type"))[1]
        require(actor, "cms_" + domain + "_view")
        require(actor, "cms_" + domain + "_edit")
        payload, binding, dep, _ = validate_payload(kind, data, lock=True)
        artifact_access(actor, payload)
        record = GovernanceRecord.objects.create(kind=kind, domain=domain, resource_type=binding["resource_type"],
            resource_id=binding["resource_id"], resource_version=binding["resource_version"],
            material=payload.get("material", ""), intended_use=payload.get("intended_use", ""), term_kind=payload.get("term_kind", ""),
            contributors=[attribution(actor.pk)])
        record._request_id = request_id
        return advance(record, actor, payload, "create", payload["reason"], current_policy(), binding, dep)


def mutate_governance(actor_id, session_id, kind, record_id, expected, action, data, request_id):
    with policy_lock():
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_enter")
        record = resolve(actor, kind, record_id, lock=True)
        if type(expected) is not int or expected != record.version:
            exc = CMSFailure("STALE_REVISION", 412)
            exc.detail.update({"current_revision": record.version, "current_etag": f'"{record.version}"'})
            raise exc
        if not isinstance(data, dict):
            raise CMSFailure("INVALID_FIELDS", 400)
        record._request_id = request_id
        policy = current_policy()
        payload = record.current_revision.payload
        if action in {"update", "reopen"}:
            require(actor, "cms_" + record.domain + "_edit")
            if action == "update":
                mutable = (RIGHTS_FIELDS if kind == "rights" else TERM_FIELDS) | {"resource_version", "evidence", "reason"}
                mutable -= {"material", "intended_use", "term_kind"}
                if not data or set(data) - mutable:
                    raise CMSFailure("INVALID_FIELDS", 400)
                if record.status not in {"submitted", "in_review", "rejected"}:
                    raise CMSFailure("INVALID_TRANSITION", 409)
                payload = {**payload, **data}
            elif data or record.status not in {"in_review", "approved", "rejected", "revoked", "submitted"}:
                raise CMSFailure("INVALID_TRANSITION", 409)
            else:
                payload = {**payload, "resource_version": resource_binding(record.resource_type, record.resource_id, True)["resource_version"]}
            payload, binding, dep, _ = validate_payload(kind, payload, lock=True)
            artifact_access(actor, payload)
            record.status, record.assignee = "submitted", None
            if action == "update":
                record.contributors = sorted(set(record.contributors) | {attribution(actor.pk)})
            result = advance(record, actor, payload, action, payload["reason"] if action == "update" else "REVIEW_REOPEN", policy, binding, dep)
            if action == "reopen":
                decision_record(result, actor, "reopened", "REVIEW_REOPEN", policy)
            return result
        if action not in {"assign", "decide", "revoke"}:
            raise CMSFailure("NOT_FOUND", 404)
        required = decision_caps(record)
        if action == "revoke":
            if kind != "rights":
                raise CMSFailure("NOT_FOUND", 404)
            required = (required - {"cms_rights_decide"}) | {"cms_rights_revoke"}
        for cap in required:
            require(actor, cap)
        if action == "revoke":
            if set(data) != {"reason"} or data.get("reason") not in REVIEW_REASONS:
                raise CMSFailure("INVALID_REASON", 400)
            if record.status == "revoked":
                raise CMSFailure("INVALID_TRANSITION", 409)
            canonical.lock_brain_curation(connection.alias)
            record.status = "revoked"
            result = advance(record, actor, payload, action, data["reason"], policy)
            decision_record(result, actor, "revoked", data["reason"], policy)
            return result
        if record.status not in {"submitted", "in_review"}:
            raise CMSFailure("INVALID_TRANSITION", 409)
        blockers = freshness(record, lock=True)
        if blockers:
            exc = CMSFailure("STALE_DECISION", 409)
            exc.detail["blockers"] = blockers
            raise exc
        if action == "assign":
            if set(data) != {"reviewer_id"} or type(data.get("reviewer_id")) is not int:
                raise CMSFailure("INVALID_REVIEWER", 400)
            reviewer = User.objects.filter(pk=data["reviewer_id"], is_active=True, is_staff=True).first()
            if reviewer is None or not decision_caps(record) <= effective_permissions(reviewer):
                raise CMSFailure("INVALID_REVIEWER", 400)
            conflict(reviewer, record, policy)
            record.assignee, record.status = reviewer, "in_review"
            result = advance(record, actor, payload, action, "REVIEW_ASSIGN", policy)
            decision_record(result, actor, "assigned", "REVIEW_ASSIGN", policy)
            return result
        if set(data) != {"outcome", "reason", "self_review_ack"}:
            raise CMSFailure("INVALID_FIELDS", 400)
        if record.status != "in_review" or record.assignee_id != actor.pk:
            raise CMSFailure("REVIEWER_CONFLICT", 409)
        conflict(actor, record, policy)
        self_review = attribution(actor.pk) in record.contributors
        if type(data["self_review_ack"]) is not bool or (self_review and not data["self_review_ack"]):
            raise CMSFailure("SELF_REVIEW_ACK_REQUIRED", 400)
        outcome = _choice(data["outcome"], {"approve", "reject"})
        reason = _choice(data["reason"], {APPROVAL_REASONS[kind]} if outcome == "approve" else REVIEW_REASONS)
        if outcome == "approve":
            _, _, _, sources = validate_payload(kind, payload, lock=True)
            artifact_access(actor, payload)
            if kind == "rights" and payload["status"] == "allowed":
                dates = eligibility(record, lock=True)
                if dates["status"] in {"expired", "review_overdue", "not_effective"}:
                    exc = CMSFailure("RIGHTS_NOT_ELIGIBLE", 409)
                    exc.detail["blockers"] = dates["blockers"]
                    raise exc
        record.status = "approved" if outcome == "approve" else "rejected"
        result = advance(record, actor, payload, action, reason, policy)
        decision_record(result, actor, outcome, reason, policy, self_review)
        return result


def record_data(record):
    revision = record.current_revision
    computed = eligibility(record)
    result = {"id": str(record.pk), "kind": record.kind, "domain": record.domain,
        "resource_type": record.resource_type, "resource_id": record.resource_id, "resource_version": record.resource_version,
        "material": record.material, "intended_use": record.intended_use, "term_kind": record.term_kind,
        "version": record.version, "status": record.status, "computed_status": computed["status"], "payload": revision.payload,
        "resource_digest": revision.resource_digest, "dependency_digest": revision.dependency_digest,
        "assignee_id": record.assignee_id, "policy_version": revision.policy_version, "policy_mode": revision.policy_mode,
        "blockers": computed["blockers"], "eligible": computed["eligible"]}
    if record.kind == "terminology":
        p = revision.payload
        result["preview"] = {"dir": "rtl", "name_en_dir": "ltr", "name_en": p["name_en"], "name_fa": p["name_fa"], "term_kind": p["term_kind"], "alternatives": p["alternatives"]}
        candidates = GovernanceRecord.objects.filter(kind="terminology", domain=record.domain,
            current_revision__payload__name_fa=p["name_fa"]).exclude(pk=record.pk).exclude(resource_type=record.resource_type, resource_id=record.resource_id).order_by("pk")
        result["candidate_conflicts"] = [{"id": str(c.pk), "resource_type": c.resource_type, "resource_id": c.resource_id, "term_kind": c.term_kind} for c in candidates[:20]]
        result["candidate_conflicts_more"] = candidates.count() > 20
    return result
