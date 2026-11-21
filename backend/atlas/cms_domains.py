"""Typed P07 proposals and read-only helpers. Publication belongs to P16."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import unicodedata

from django.core.exceptions import ValidationError as ModelValidationError
from django.db import models
from django.db.models.functions import Lower, Trim
from rest_framework import serializers

from . import models as atlas
from .cms_policy import CMSFailure
from .cms_source_models import SourceState, SourceSuccessor


MAX_PAYLOAD_BYTES = 131072
MAX_DEPENDENCIES = 200
MAX_TREE_DEPTH = 128
PROTECTED_JSON_KEYS = frozenset({"raw_document", "source_payload", "source_sha256", "source_filename", "search_text"})
IDENTITIES = {"slug", "key", "master_id"}


def _json(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _digest(value):
    result = hashlib.sha256()
    for part in json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json).iterencode(value):
        result.update(part.encode())
    return result.hexdigest()


def _identity(value):
    return unicodedata.normalize("NFKC", value).strip()


class TypedReference(serializers.PrimaryKeyRelatedField):
    """ModelSerializer relation semantics with JSON-native IDs in proposal data."""
    def to_internal_value(self, data):
        if type(data) is not int or not 1 <= data <= 2**63 - 1:
            raise serializers.ValidationError("A positive integer reference is required.")
        return super().to_internal_value(data).pk

    def to_representation(self, value):
        return value if type(value) is int else super().to_representation(value)


class StructuredField(serializers.Field):
    """A closed JSON value grammar, bounded independently of request transport."""
    def __init__(self, root, **kwargs):
        self.value_root = root
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        expected = {"array": list, "object": dict}
        if self.value_root in expected and type(data) is not expected[self.value_root]:
            raise serializers.ValidationError("Expected " + self.value_root + ".")
        if self.value_root == "number-or-object" and type(data) not in (int, float, dict):
            raise serializers.ValidationError("Expected a number or structured estimate.")
        budget = [1000]

        def check(value, depth=0):
            budget[0] -= 1
            if depth > 6 or budget[0] < 0:
                raise serializers.ValidationError("Structured value is too deep or too large.")
            if type(value) is dict:
                if len(value) > 100:
                    raise serializers.ValidationError("At most 100 properties are allowed.")
                for key, child in value.items():
                    if (type(key) is not str or not key.strip() or len(key) > 160
                            or key in PROTECTED_JSON_KEYS):
                        raise serializers.ValidationError("Invalid or protected structured property.")
                    check(child, depth + 1)
            elif type(value) is list:
                if len(value) > 100:
                    raise serializers.ValidationError("At most 100 items are allowed.")
                for child in value:
                    check(child, depth + 1)
            elif type(value) is str:
                if len(value) > 2000:
                    raise serializers.ValidationError("Structured text is limited to 2000 characters.")
            elif type(value) is float:
                if not math.isfinite(value):
                    raise serializers.ValidationError("Finite numbers are required.")
            elif value is not None and type(value) not in (int, bool):
                raise serializers.ValidationError("Unsupported structured value.")

        check(data)
        if len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode()) > 65536:
            raise serializers.ValidationError("Structured value exceeds 64 KiB.")
        return deepcopy(data)

    def to_representation(self, value):
        return deepcopy(value)


class ProposalSerializer(serializers.ModelSerializer):
    serializer_related_field = TypedReference

    def get_validators(self):
        # full_clean below owns constraint checks, including sparse legacy proposals.
        return []

    def build_standard_field(self, field_name, model_field):
        field_class, kwargs = super().build_standard_field(field_name, model_field)
        if isinstance(model_field, models.JSONField):
            root = "number-or-object" if field_name == "prevalence_numeric" else ("array" if model_field.default is list else "object")
            return StructuredField, {"root": root, "required": False, "allow_null": model_field.null}
        if isinstance(model_field, models.TextField):
            kwargs["max_length"] = 20000
        if isinstance(model_field, models.PositiveSmallIntegerField):
            kwargs.update(min_value=0, max_value=32767)
        elif isinstance(model_field, models.PositiveIntegerField):
            kwargs.update(min_value=0, max_value=2147483647)
        if field_name in IDENTITIES:
            kwargs["validators"] = []
            if self.Meta.model in (atlas.Category, atlas.Disorder):
                kwargs["required"] = False
        return field_class, kwargs

    def get_fields(self):
        fields = super().get_fields()
        if self.Meta.model is atlas.Disorder:
            fields["category"].required = False
        return fields

    def to_internal_value(self, data):
        if not isinstance(data, dict) or not data or set(data) - self.fields.keys():
            raise serializers.ValidationError({"payload": "Nonempty typed fields are required; unknown/protected fields are refused."})
        data = dict(data)
        for name, value in data.items():
            field = self.fields[name]
            if value is None and field.allow_null:
                continue
            if isinstance(field, serializers.CharField) and type(value) is not str:
                raise serializers.ValidationError({name: "A string is required."})
            if isinstance(field, serializers.IntegerField) and type(value) is not int:
                raise serializers.ValidationError({name: "An integer is required."})
            if name in IDENTITIES and type(value) is str:
                data[name] = _identity(value)
                if name != "master_id":
                    data[name] = data[name].lower()
        return super().to_internal_value(data)

    def create(self, validated_data):
        raise TypeError("Proposal serializers never save canonical objects.")

    def update(self, instance, validated_data):
        raise TypeError("Proposal serializers never save canonical objects.")


class CategoryProposal(ProposalSerializer):
    class Meta:
        model = atlas.Category
        fields = ("slug", "name_en", "name_fa", "description", "sort_order")


class DisorderProposal(ProposalSerializer):
    class Meta:
        model = atlas.Disorder
        fields = ("slug", "category", "name_en", "name_fa", "short_description", "overview", "clinical_features",
            "risk_factors", "treatment_overview", "assessment_overview", "typical_onset", "course_note")


class SymptomProposal(ProposalSerializer):
    class Meta:
        model = atlas.Symptom
        fields = ("slug", "name_en", "name_fa", "description", "domain")


class DisorderSymptomProposal(ProposalSerializer):
    class Meta:
        model = atlas.DisorderSymptom
        fields = ("disorder", "symptom", "prominence", "note", "sort_order")


class DifferentialProposal(ProposalSerializer):
    class Meta:
        model = atlas.DifferentialRelationship
        fields = ("disorder", "related_disorder", "relationship_type", "explanation")


class DisorderSourceProposal(ProposalSerializer):
    class Meta:
        model = atlas.DisorderSource
        fields = ("disorder", "source", "note")


class ConceptProposal(ProposalSerializer):
    class Meta:
        model = atlas.Concept
        fields = ("slug", "name_en", "name_fa", "simple_definition", "academic_definition", "example", "counterexample",
            "recognition_cues", "common_confusions", "kind", "domain", "subtype")


class ConceptRelationshipProposal(ProposalSerializer):
    class Meta:
        model = atlas.ConceptRelationship
        fields = ("source_concept", "target_concept", "relationship_type", "explanation")


class ConceptAliasProposal(ProposalSerializer):
    class Meta:
        model = atlas.ConceptAlias
        fields = ("concept", "text", "language", "alias_type")


class ConceptRelationshipSourceProposal(ProposalSerializer):
    class Meta:
        model = atlas.ConceptRelationshipSource
        fields = ("relationship", "source", "note")


class ConceptSymptomProposal(ProposalSerializer):
    class Meta:
        model = atlas.ConceptSymptom
        fields = ("concept", "symptom", "relationship_type", "explanation", "sort_order")


class ConceptSymptomSourceProposal(ProposalSerializer):
    class Meta:
        model = atlas.ConceptSymptomSource
        fields = ("relationship", "source", "note")


class DisorderConceptProposal(ProposalSerializer):
    class Meta:
        model = atlas.DisorderConcept
        fields = ("disorder", "concept", "role", "explanation", "sort_order")


class ConceptSourceProposal(ProposalSerializer):
    class Meta:
        model = atlas.ConceptSource
        fields = ("concept", "source", "note")


class DSMCorpusProposal(ProposalSerializer):
    class Meta:
        model = atlas.DSMCorpus
        fields = ("key", "title", "version_name", "version_date", "language", "purpose", "copyright_note", "clinical_note",
            "official_status", "source_registry", "quality_audit", "stats", "study_guide", "urgent_warnings", "cultural_note",
            "periodic_review", "release_updates", "health_check", "metadata")


class DSMRecordProposal(ProposalSerializer):
    class Meta:
        model = atlas.DSMRecord
        fields = ("corpus", "master_id", "parent", "linked_disorder", "sort_index", "root_section", "chapter_number",
            "chapter_name_fa", "chapter_name_en", "group_name", "name_fa", "name_en", "source_type", "classification_status",
            "display_type", "specialization_level", "summary", "key_features", "assessment", "differential", "comorbidity",
            "course", "management", "assessment_tools", "context_considerations", "red_flags", "pitfalls", "nearby_titles",
            "official_updates", "homonym_info", "prevalence_numeric", "prevalence_policy", "coding", "source_keys", "quality",
            "exam_tip", "self_test", "structural_path")


class DSMRecordRelationProposal(ProposalSerializer):
    class Meta:
        model = atlas.DSMRecordRelation
        fields = ("source", "target", "relationship_type", "explanation")


def _spec(serializer, label):
    model = serializer.Meta.model
    fields = tuple(f.attname for f in model._meta.concrete_fields if f.name not in {"id", "created_at", "updated_at", "raw_document", "source_payload", "search_text"})
    policy = {}
    for f in model._meta.concrete_fields:
        reason = ""
        if f.name in IDENTITIES:
            reason = "CREATE_ONLY_IDENTITY; correction requires a successor draft/intake."
        elif f.name not in serializer.Meta.fields:
            reason = ("IMMUTABLE_RAW; use a new P06 intake and audited raw-read action." if f.name in {"raw_document", "source_payload"}
                else "WORKFLOW_ONLY; publication/withdrawal requires P16." if f.name == "is_active" else "SYSTEM_MANAGED")
        policy[f.name] = {"create_only": f.name in IDENTITIES, "readonly_reason": reason}
    return {"model": model, "serializer": serializer, "snapshot_fields": fields,
        "domain": "dsm" if model in (atlas.DSMCorpus, atlas.DSMRecord, atlas.DSMRecordRelation) else "core",
        "label": label, "field_policy": policy}


DOMAIN_SPECS = {
    "category": _spec(CategoryProposal, "دسته‌بندی"),
    "disorder": _spec(DisorderProposal, "اختلال"),
    "symptom": _spec(SymptomProposal, "نشانه"),
    "disorder-symptom": _spec(DisorderSymptomProposal, "نشانهٔ اختلال"),
    "differential-relationship": _spec(DifferentialProposal, "رابطهٔ افتراقی"),
    "disorder-source": _spec(DisorderSourceProposal, "منبع اختلال"),
    "concept": _spec(ConceptProposal, "مفهوم"),
    "concept-relationship": _spec(ConceptRelationshipProposal, "رابطهٔ مفاهیم"),
    "concept-alias": _spec(ConceptAliasProposal, "نام جایگزین مفهوم"),
    "concept-relationship-source": _spec(ConceptRelationshipSourceProposal, "منبع رابطهٔ مفاهیم"),
    "concept-symptom": _spec(ConceptSymptomProposal, "رابطهٔ مفهوم و نشانه"),
    "concept-symptom-source": _spec(ConceptSymptomSourceProposal, "منبع رابطهٔ مفهوم و نشانه"),
    "disorder-concept": _spec(DisorderConceptProposal, "رابطهٔ اختلال و مفهوم"),
    "concept-source": _spec(ConceptSourceProposal, "منبع مفهوم"),
    "dsm-corpus": _spec(DSMCorpusProposal, "مجموعهٔ DSM"),
    "dsm-record": _spec(DSMRecordProposal, "رکورد DSM"),
    "dsm-record-relation": _spec(DSMRecordRelationProposal, "رابطهٔ رکوردهای DSM"),
}
# The old canonical digests are persisted contracts, including field order and FK attnames.
DOMAIN_SPECS["category"]["snapshot_fields"] = ("slug", "name_en", "name_fa", "description", "sort_order", "is_active")
DOMAIN_SPECS["disorder"]["snapshot_fields"] = ("slug", "category_id", "name_en", "name_fa", "short_description", "overview",
    "clinical_features", "risk_factors", "treatment_overview", "assessment_overview", "typical_onset", "course_note", "data_origin", "is_active")
from .cms_therapy_domains import build_specs as _build_therapy_specs, SOURCE_LINKS as _THERAPY_SOURCE_LINKS
DOMAIN_SPECS.update(_build_therapy_specs())
from .cms_history_domains import build_specs as _build_history_specs, SOURCE_LINKS as _HISTORY_SOURCE_LINKS
DOMAIN_SPECS.update(_build_history_specs())
from .cms_brain_domains import build_specs as _build_brain_specs, SOURCE_LINKS as _BRAIN_SOURCE_LINKS
DOMAIN_SPECS.update(_build_brain_specs())
from .cms_assessment_domains import build_specs as _build_assessment_specs, SOURCE_LINKS as _ASSESSMENT_SOURCE_LINKS
DOMAIN_SPECS.update(_build_assessment_specs())
MODEL_KINDS = {spec["model"]: kind for kind, spec in DOMAIN_SPECS.items()}


def _entry(kind):
    if kind not in DOMAIN_SPECS:
        raise CMSFailure("NOT_FOUND", 404)
    return DOMAIN_SPECS[kind]


def entry_tuple(kind):
    spec = _entry(kind)
    return spec["model"], spec["serializer"], spec["snapshot_fields"]


def domain_for(kind):
    return _entry(kind)["domain"]


def schema_data(kind):
    spec = _entry(kind)
    writable = spec["serializer"]().fields
    fields = []
    for f in spec["model"]._meta.concrete_fields:
        form = writable.get(f.name)
        related = ("source" if f.related_model is atlas.SourceReference else MODEL_KINDS.get(f.related_model)) if f.is_relation else None
        field_type = ("reference" if f.is_relation else "structured" if isinstance(f, models.JSONField) else
            "choice" if f.choices else "boolean" if isinstance(f, models.BooleanField) else "integer" if isinstance(f, models.IntegerField) else
            "date" if isinstance(f, (models.DateField, models.DateTimeField)) else "text" if isinstance(f, models.TextField) else "string")
        row = {"name": f.name, "type": field_type, "required": bool(form and form.required),
            "choices": [{"value": value, "label": str(label)} for value, label in (f.choices or ())],
            "max_length": getattr(form, "max_length", None) or f.max_length, "related_kind": related,
            "allow_null": f.null, "allow_blank": f.blank, **spec["field_policy"][f.name]}
        if isinstance(form, StructuredField):
            row["structure"] = {"root": form.value_root, "max_items": 100, "max_depth": 6, "max_nodes": 1000, "max_text_length": 2000, "max_bytes": 65536,
                "key_policy": "nonempty strings, max160; protected raw/system keys forbidden", "value_types": ["string", "number", "boolean", "null", "array", "object"]}
        fields.append(row)
    return {"kind": kind, "domain": spec["domain"], "label": spec["label"], "fields": fields}


def _candidate(kind, payload, obj=None):
    model = _entry(kind)["model"]
    if obj is not None and type(obj) is not model:
        raise serializers.ValidationError({"object": "Wrong typed canonical object."})
    values = {f.attname: deepcopy(getattr(obj, f.attname)) for f in model._meta.concrete_fields
        if f.name not in {"raw_document", "source_payload", "search_text"}} if obj else {}
    candidate = model(**values)
    if obj:
        candidate._state.adding, candidate._state.db = False, obj._state.db
    for name, value in payload.items():
        setattr(candidate, model._meta.get_field(name).attname, deepcopy(value))
    return candidate


def _dsm_constraints(kind, candidate):
    if kind == "dsm-record":
        corpus_id, parent_id = candidate.corpus_id, candidate.parent_id
        seen = {candidate.pk} if candidate.pk else set()
        for _ in range(MAX_TREE_DEPTH):
            if parent_id is None:
                break
            if parent_id in seen:
                raise serializers.ValidationError({"parent": "DSM tree cycles are forbidden."})
            seen.add(parent_id)
            parent = atlas.DSMRecord.objects.only("parent_id", "corpus_id").get(pk=parent_id)
            if parent.corpus_id != corpus_id:
                raise serializers.ValidationError({"parent": "Parent must belong to the same corpus."})
            parent_id = parent.parent_id
        else:
            raise serializers.ValidationError({"parent": "DSM tree exceeds the validation depth limit."})
        if candidate.pk and atlas.DSMRecord.objects.filter(parent_id=candidate.pk).exclude(corpus_id=corpus_id).exists():
            raise serializers.ValidationError({"corpus": "Moving a parent would split its child corpus."})
        if candidate.pk:
            from django.db.models import Q
            if atlas.DSMRecordRelation.objects.filter(
                    Q(source_id=candidate.pk) & ~Q(target__corpus_id=corpus_id) |
                    Q(target_id=candidate.pk) & ~Q(source__corpus_id=corpus_id)).exists():
                raise serializers.ValidationError({"corpus": "Moving this endpoint would split a typed relation."})
        if type(candidate.source_keys) is not list or any(type(key) is not str or not key for key in candidate.source_keys):
            raise serializers.ValidationError({"source_keys": "A list of source-registry keys is required."})
        registry = atlas.DSMCorpus.objects.values_list("source_registry", flat=True).get(pk=corpus_id)
        if candidate.source_keys and (not isinstance(registry, dict) or set(candidate.source_keys) - registry.keys()):
            raise serializers.ValidationError({"source_keys": "Every source key must resolve in this corpus registry."})
    elif kind == "dsm-record-relation":
        endpoints = dict(atlas.DSMRecord.objects.filter(pk__in=(candidate.source_id, candidate.target_id)).values_list("pk", "corpus_id"))
        if endpoints[candidate.source_id] != endpoints[candidate.target_id]:
            raise serializers.ValidationError({"target": "DSM relation endpoints must belong to the same corpus."})


def validate_snapshot(kind, payload, obj=None):
    spec = _entry(kind)
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError):
        raise serializers.ValidationError({"payload": "A finite JSON-native proposal is required."})
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise serializers.ValidationError({"payload": "Proposal exceeds 128 KiB."})
    form = spec["serializer"](data=payload, partial=obj is not None)
    form.is_valid(raise_exception=True)
    data = {name: _json(value) for name, value in form.validated_data.items()}
    candidate = _candidate(kind, data, obj)
    for name in IDENTITIES & data.keys():
        if obj and _identity(data[name]).casefold() != _identity(getattr(obj, name)).casefold():
            raise serializers.ValidationError({name: "Identity is create-only; use a successor draft/intake."})
        if obj:
            data[name] = getattr(obj, name)
            setattr(candidate, name, data[name])
        rows = spec["model"].objects.alias(normalized_identity=Lower(Trim(name))).filter(normalized_identity=data[name].lower())
        if obj:
            rows = rows.exclude(pk=obj.pk)
        if name == "master_id":
            rows = rows.filter(corpus_id=candidate.corpus_id)
        if rows.exists():
            raise serializers.ValidationError({name: "Normalized identity already exists."})
    exclude = {f.name for f in spec["model"]._meta.concrete_fields if f.name not in spec["serializer"].Meta.fields or (obj is None and f.name not in data)}
    # Defaults still participate in typed uniqueness/check constraints; only missing required legacy identity/FKs are excluded.
    exclude -= {f.name for f in spec["model"]._meta.concrete_fields if f.has_default() and f.name in spec["serializer"].Meta.fields}
    try:
        candidate.full_clean(exclude=exclude)
    except ModelValidationError as exc:
        raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    for f in spec["model"]._meta.concrete_fields:
        if f.is_relation and f.related_model is atlas.SourceReference:
            source_id = getattr(candidate, f.attname)
            if SourceState.objects.filter(source_pk=source_id).filter(models.Q(archived=True) | models.Q(deleted=True)).exists():
                raise serializers.ValidationError({f.name: "Source is archived or deleted."})
    _dsm_constraints(kind, candidate)
    return data


def required_reference_capabilities(kind, payload):
    spec = _entry(kind)
    result = set()
    for name in spec["serializer"].Meta.fields:
        f = spec["model"]._meta.get_field(name)
        if f.is_relation and isinstance(payload, dict) and payload.get(name) is not None:
            result.add("cms_source_view" if f.related_model is atlas.SourceReference else "cms_" + domain_for(MODEL_KINDS[f.related_model]) + "_view")
    return sorted(result)


SOURCE_LINKS = {
    atlas.Disorder: ((atlas.DisorderSource, "disorder"),),
    atlas.Concept: ((atlas.ConceptSource, "concept"),),
    atlas.ConceptRelationship: ((atlas.ConceptRelationshipSource, "relationship"),),
    atlas.ConceptSymptom: ((atlas.ConceptSymptomSource, "relationship"),),
}


SOURCE_LINKS.update(_THERAPY_SOURCE_LINKS)
SOURCE_LINKS.update(_HISTORY_SOURCE_LINKS)
SOURCE_LINKS.update(_BRAIN_SOURCE_LINKS)
SOURCE_LINKS.update(_ASSESSMENT_SOURCE_LINKS)


def _rows(model, lock=False):
    rows = model.objects.order_by("pk")
    return rows.select_for_update() if lock else rows


def _safe_endpoint(kind, obj):
    # Unbounded text/structured content affects freshness through hashes, not copied documents.
    fields = _entry(kind)["snapshot_fields"]
    return {name: (_digest(getattr(obj, name)) if isinstance(obj._meta.get_field(name), (models.JSONField, models.TextField))
        else _json(getattr(obj, name))) for name in fields}


def _protected(obj):
    return {f.name: _digest(getattr(obj, f.name)) for f in obj._meta.concrete_fields
        if f.name in {"raw_document", "source_payload", "search_text"}}


def dependency_snapshot(kind, obj, payload=None, lock=False):
    spec = _entry(kind)
    if payload is not None and (not isinstance(payload, dict) or set(payload) - set(spec["serializer"].Meta.fields)):
        raise serializers.ValidationError({"payload": "Typed proposal fields required."})
    if payload:
        for name, value in payload.items():
            if spec["model"]._meta.get_field(name).is_relation and value is not None and (type(value) is not int or not 1 <= value <= 2**63 - 1):
                raise serializers.ValidationError({name: "A positive integer reference is required."})
    candidate = _candidate(kind, payload or {}, obj)
    queue, endpoints, links, source_ids, seen = [], [], [], set(), set()

    def refs(row):
        for f in row._meta.concrete_fields:
            if f.is_relation and getattr(row, f.attname) is not None:
                if f.related_model is atlas.SourceReference:
                    source_ids.add(getattr(row, f.attname))
                elif f.related_model in MODEL_KINDS:
                    queue.append((MODEL_KINDS[f.related_model], getattr(row, f.attname)))

    def source_links(row):
        for link_model, fk in SOURCE_LINKS.get(type(row), ()):
            rows = list(_rows(link_model, lock).filter(**{fk + "_id": row.pk})[:MAX_DEPENDENCIES + 1])
            for link in rows:
                links.append({"kind": MODEL_KINDS[link_model], "id": link.pk, "source": link.source_id, "note_digest": _digest(link.note)})
                source_ids.add(link.source_id)
            if len(links) > MAX_DEPENDENCIES:
                raise serializers.ValidationError({"dependencies": "Source closure exceeds 200 links."})

    refs(candidate)
    if obj:
        source_links(obj)
    while queue:
        endpoint_kind, pk = queue.pop(0)
        if (endpoint_kind, pk) in seen:
            continue
        if len(seen) >= MAX_DEPENDENCIES:
            raise serializers.ValidationError({"dependencies": "Typed endpoint closure exceeds 200 objects."})
        seen.add((endpoint_kind, pk))
        endpoint = _rows(_entry(endpoint_kind)["model"], lock).filter(pk=pk).first()
        if endpoint is None:
            raise serializers.ValidationError({"dependencies": "A typed endpoint no longer exists."})
        endpoints.append({"kind": endpoint_kind, "id": pk, "snapshot": _safe_endpoint(endpoint_kind, endpoint), "protected": _protected(endpoint)})
        refs(endpoint)
        source_links(endpoint)
    if len(source_ids) > MAX_DEPENDENCIES:
        raise serializers.ValidationError({"dependencies": "Source closure exceeds 200 sources."})
    sources = list(_rows(atlas.SourceReference, lock).filter(pk__in=source_ids))
    if len(sources) != len(source_ids):
        raise serializers.ValidationError({"dependencies": "A source no longer exists."})
    source_data = [{"id": row.pk, "fingerprint": _digest({f.attname: _json(getattr(row, f.attname)) for f in row._meta.concrete_fields
        if f.name not in {"created_at", "updated_at"}})} for row in sources]
    lifecycle = list(_rows(SourceState, lock).filter(source_pk__in=source_ids).values("source_pk", "version", "resource_version", "archived", "deleted"))
    successors = list(_rows(SourceSuccessor, lock).filter(source_pk__in=source_ids).values("source_pk", "successor_pk", "operation")[:MAX_DEPENDENCIES + 1])
    if len(successors) > MAX_DEPENDENCIES:
        raise serializers.ValidationError({"dependencies": "Source successor closure exceeds 200 objects."})
    return {"endpoints": sorted(endpoints, key=lambda e: (e["kind"], e["id"])),
        "source_links": sorted(links, key=lambda e: (e["kind"], e["id"])), "sources": source_data,
        "source_lifecycle": lifecycle, "successors": successors, "protected": _protected(obj) if obj else {}}


def preview_snapshot(kind, payload, obj=None):
    data = validate_snapshot(kind, payload, obj)
    return {"kind": kind, "domain": domain_for(kind), "candidate": data, "publication_available": False}
