"""P05 source plans. Preview and apply share the same guarded, per-object validator."""
from copy import copy
from itertools import combinations
import re

from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import connection, transaction, IntegrityError
from django.db.models import Q
from django.db.models.deletion import ProtectedError

from .assessment_models import protect_assessment_source
from .brain_source_resolution import canonical_url, normalized_doi, normalized_text
from .cms_audit import attribution
from .cms_content import digest
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_source_models import SourceHistory, SourcePlan, SourcePlanReceipt, SourceState, SourceSuccessor
from .cms_sessions import current_session
from .models import SourceReference, lock_brain_curation


SOURCE_FIELDS = frozenset({"title", "organization", "citation", "url", "publication_year", "source_type",
    "authors", "doi", "pmid", "verification_status", "resource_version"})
SOURCE_AUDIT_ACTIONS = frozenset({"source.preview", "source.created", "source.updated", "source.archived",
    "source.deleted", "source.merged", "source.split", "source.successor"})
SOURCE_AUDIT_REASONS = frozenset("SOURCE_" + op.upper() for op in
    ("create", "update", "archive", "delete", "merge", "split", "successor"))
OPERATIONS = {"create": "create", "update": "edit", "archive": "archive", "delete": "delete_unused",
    "merge": "edit", "split": "edit", "successor": "edit"}
ACTION = {"create": "created", "update": "updated", "archive": "archived", "delete": "deleted",
    "merge": "merged", "split": "split", "successor": "successor"}
VERSION_PINS = ("resource_version", "source_version", "version", "dataset_version")
CORE_MODELS = {"DisorderSource", "ConceptSource", "ConceptRelationshipSource", "ConceptSymptomSource"}
THERAPY_MODELS = {"TherapySource", "TechniqueSource", "TherapyTechniqueSource", "TherapyDisorderSource",
    "TherapyConceptSource", "TechniqueConceptSource"}
HISTORY_MODELS = {"PsychologistSource", "TheorySource", "TimelineEventSource", "PsychologistTheorySource",
    "PsychologistConceptSource", "PsychologistTherapySource", "PsychologistPsychologistSource", "TheoryConceptSource",
    "TheoryTherapySource", "TheoryTechniqueSource", "TheoryTheorySource", "TimelinePsychologistSource",
    "TimelineTheorySource", "TimelineTherapySource", "TimelineTechniqueSource", "TimelineConceptSource"}
BRAIN_MODELS = {"BrainAnatomicalAlias", "BrainNetworkAlias", "BrainExternalIdentifier", "BrainAnatomicalEntitySource",
    "BrainNetworkSource", "BrainHierarchyLinkSource", "BrainNetworkMembershipSource", "BrainFunctionalAssociationSource"}
ASSESSMENT_MODELS = {"AssessmentLanguageForm", "AssessmentValidationStudy", "AssessmentAlias", "AssessmentAccess", "AssessmentSource"}
MUTABLE_MODELS = CORE_MODELS | THERAPY_MODELS | HISTORY_MODELS | BRAIN_MODELS | ASSESSMENT_MODELS


def domain_for(model):
    name = model if isinstance(model, str) else model.__name__
    for domain, names in (("core", CORE_MODELS), ("therapy", THERAPY_MODELS), ("history", HISTORY_MODELS),
                          ("brain", BRAIN_MODELS), ("assessment", ASSESSMENT_MODELS)):
        if name in names:
            return domain
    return None


def _json(value):
    if value is None or isinstance(value, (str, int, float, bool, dict, list)):
        return value
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _row_snapshot(row):
    return {f.attname: _json(getattr(row, f.attname)) for f in row._meta.concrete_fields
        if f.name not in {"created_at", "updated_at"}}


def provenance_versions(source):
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    return {name: str(metadata[name]) for name in VERSION_PINS
        if name in metadata and type(metadata[name]) in (str, int) and str(metadata[name]).strip()}


def source_snapshot(source):
    state = SourceState.objects.filter(source_pk=source.pk).first()
    pins = provenance_versions(source)
    return {**_row_snapshot(source), "resource_version": (state.resource_version if state and state.resource_version
        else next(iter(pins.values()), "")), "provenance_versions": pins, "version": state.version if state else 0,
        "archived": state.archived if state else False, "deleted": state.deleted if state else False}


def _owners(row, source_field, lock=False):
    """Fingerprint claim context, including its parents and checked study findings."""
    result, seen = [], set()
    queue = [row]
    while queue:
        current = queue.pop()
        key = (current._meta.label_lower, current.pk)
        if key in seen:
            continue
        seen.add(key)
        if current is not row:
            result.append({"model": type(current).__name__, "id": _json(current.pk), "snapshot": _row_snapshot(current)})
        for field in current._meta.concrete_fields:
            target = field.remote_field.model if field.is_relation else None
            if not target or target is SourceReference or target._meta.app_label != "atlas":
                continue
            target_id = getattr(current, field.attname)
            rows = target.objects.filter(pk=target_id)
            if lock:
                rows = rows.select_for_update()
            parent = rows.first() if target_id else None
            if parent is not None:
                queue.append(parent)
        if type(current).__name__ == "AssessmentValidationStudy":
            findings = current.findings.order_by("pk")
            if lock:
                findings = findings.select_for_update()
            queue.extend(findings)
    return sorted(result, key=lambda x: (x["model"], str(x["id"])))


def _query(model, lock=False):
    rows = model.objects.order_by("pk")
    return rows.select_for_update() if lock else rows


def _bibliographic_paths(value, source, external_ids=(), path="", canonical_ids=False):
    """Recognize explicit references, not arbitrary integers or relationship endpoint IDs."""
    paths = []
    if isinstance(value, dict):
        title, url = value.get("title", value.get("عنوان")), value.get("url", value.get("نشانی"))
        match = isinstance(title, str) and normalized_text(title) == normalized_text(source.title)
        match &= isinstance(url, str) and url.strip() == source.url.strip()
        for field, norm in (("doi", normalized_doi), ("pmid", lambda v: v.strip())):
            if isinstance(value.get(field), str) and getattr(source, field):
                match |= bool(norm(value[field])) and norm(value[field]) == norm(getattr(source, field))
        if match:
            paths.append(path or "/")
        for key, item in value.items():
            here = path + "/" + str(key)
            if key in {"source_pk", "source_reference_id"} or canonical_ids and key == "source_id":
                if type(item) in (int, str) and str(item) == str(source.pk):
                    paths.append(here)
            if key in {"source_ids", "sources", "source_keys", "منابع_پایه", "key_works", "major_publications"}:
                values = item if isinstance(item, list) else [item]
                wanted = {str(source.pk)} if canonical_ids else set(external_ids)
                if any(type(v) in (int, str) and str(v) in wanted for v in values):
                    paths.append(here)
            paths.extend(_bibliographic_paths(item, source, external_ids, here, canonical_ids))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_bibliographic_paths(item, source, external_ids, path + "/" + str(index), canonical_ids))
    return sorted(set(paths))


def _impact(source, lock=False):
    canonical, review, archives, contexts = [], [], [], []
    for relation in sorted(SourceReference._meta.related_objects, key=lambda r: (r.related_model.__name__, r.field.name)):
        model, field = relation.related_model, relation.field.name
        rows = _query(model, lock).filter(**{field + "_id": source.pk})
        for row in rows:
            known = model.__name__ in MUTABLE_MODELS
            owners = _owners(row, field, lock) if known else []
            snapshot = _row_snapshot(row)
            checked = snapshot.get("review_status") not in (None, "", "unreviewed") or any(
                owner["snapshot"].get("review_status") not in (None, "", "unreviewed") for owner in owners)
            domain = domain_for(model) or getattr(row, "domain", None)
            canonical.append({"key": f"{model.__name__}:{row.pk}:{field}", "model": model.__name__, "id": _json(row.pk),
                "field": field, "source_id": source.pk, "domain": domain, "owners": [{"model": o["model"], "id": o["id"],
                    "review_status": o["snapshot"].get("review_status"), "is_active": o["snapshot"].get("is_active")} for o in owners],
                "claim": {f: snapshot[f] for f in ("note", "source_note", "authorization_note") if f in snapshot} if known else {},
                "protected": checked, "mutable": known})
            contexts.append({"key": canonical[-1]["key"], "row": snapshot, "owners": owners})

    def archive(row, field, paths, domain, bucket=archives, detail=None):
        if not paths:
            return
        item = {"key": f"{type(row).__name__}:{row.pk}:{field}", "model": type(row).__name__, "id": _json(row.pk),
            "field": field, "paths": paths, "source_id": source.pk, "domain": domain, "mutable": False}
        dataset = row if type(row).__name__ == "ResearchDataset" else getattr(row, "dataset", None)
        if dataset is not None and isinstance(dataset.ingestion_audit, dict) and "cms_owner_ref" in dataset.ingestion_audit:
            item["private"] = True
        if detail:
            item.update(detail)
        bucket.append(item)
        contexts.append({"key": item["key"], "row": _row_snapshot(row)})

    # Decisions are immutable provenance; task JSON also remains owned by the review service.
    from .cms_domains import DOMAIN_SPECS, domain_for as content_domain
    for name in ("ReviewTask", "ReviewDecision"):
        model = apps.get_model("atlas", name)
        for row in _query(model, lock).select_related("subject__state" if name == "ReviewTask" else "task__subject__state"):
            evidence = row.evidence if isinstance(row.evidence, list) else []
            matches = [e for e in evidence if isinstance(e, dict) and e.get("source_id") == source.pk]
            if matches:
                subject = row.subject if name == "ReviewTask" else row.task.subject
                archive(row, "evidence", _bibliographic_paths(evidence, source, canonical_ids=True), content_domain(subject.state.kind), review,
                    {"evidence": matches, "retained": True})

    corpus_model, record_model = apps.get_model("atlas", "DSMCorpus"), apps.get_model("atlas", "DSMRecord")
    external_by_corpus = {}
    for corpus in _query(corpus_model, lock):
        registry = corpus.source_registry if isinstance(corpus.source_registry, dict) else {}
        keys = {str(key) for key, value in registry.items() if _bibliographic_paths(value, source)}
        external_by_corpus[corpus.pk] = keys
        for field in ("source_registry", "metadata", "raw_document"):
            archive(corpus, field, _bibliographic_paths(getattr(corpus, field), source, keys), "dsm")
        if keys:
            for record in _query(record_model, lock).filter(corpus=corpus):
                if set(str(v) for v in record.source_keys or []) & keys:
                    archive(record, "source_keys", ["/"], "dsm")
                    archive(record, "source_payload", ["/"], "dsm")

    research = apps.get_model("atlas", "ResearchRecord")
    records = list(_query(research, lock))
    external_by_dataset = {}
    for row in records:
        if row.section == "sources" and row.promoted_model == "atlas.sourcereference" and row.promoted_pk == source.pk:
            external_by_dataset.setdefault(row.dataset_id, set()).add(str(row.external_id))
    dataset_ids = set()
    for row in records:
        external_ids = external_by_dataset.get(row.dataset_id, set())
        source_row = row.section == "sources" and row.promoted_model == "atlas.sourcereference" and row.promoted_pk == source.pk
        linked = bool(set(str(v) for v in row.source_ids or []) & external_ids)
        paths = _bibliographic_paths(row.payload, source, external_ids)
        if source_row or linked or paths:
            dataset_ids.add(row.dataset_id)
            archive(row, "payload", paths or ["/"], "research")
            if linked:
                archive(row, "source_ids", ["/"], "research")
            if source_row:
                archive(row, "promoted_pk", ["/"], "research")
    for dataset in _query(apps.get_model("atlas", "ResearchDataset"), lock):
        external_ids = external_by_dataset.get(dataset.pk, set())
        for field in ("metadata", "ingestion_audit", "raw_document"):
            paths = _bibliographic_paths(getattr(dataset, field), source, external_ids)
            archive(dataset, field, paths or (["/"] if dataset.pk in dataset_ids else []), "research")

    # Derived source mappings are immutable retained provenance, not canonical FK rewrites.
    decisions = apps.get_model("atlas", "ResearchRecordDecision")
    for row in _query(decisions, lock).select_related("record__dataset"):
        if source.pk in row.mapping.get("source_ids", []):
            archive(row, "mapping", ["/source_ids"], "research", detail={
                "private": isinstance(row.record.dataset.ingestion_audit, dict) and "cms_owner_ref" in row.record.dataset.ingestion_audit})
            contexts.append({"key": f"ResearchRecord:{row.record_id}", "row": _row_snapshot(row.record)})

    # Governance revisions can reference a source exclusively through JSON, without any source FK.
    for row in _query(apps.get_model("atlas", "ContentRevision"), lock).select_related("state"):
        spec = DOMAIN_SPECS.get(row.state.kind)
        if spec is None:
            continue
        external_ids = set()
        if row.state.kind == "dsm-record":
            corpus_id = row.payload.get("corpus")
            if corpus_id is None and row.state.canonical_pk is not None:
                corpus_id = record_model.objects.filter(pk=row.state.canonical_pk).values_list("corpus_id", flat=True).first()
            external_ids = external_by_corpus.get(corpus_id, set())
        paths = _bibliographic_paths(row.payload, source, external_ids)
        for field in spec["model"]._meta.concrete_fields:
            if field.is_relation and field.related_model is SourceReference:
                if row.payload.get(field.name, row.payload.get(field.attname)) == source.pk:
                    paths.append("/" + field.name)
        archive(row, "payload", sorted(set(paths)), spec["domain"])
        if paths:
            contexts.append({"key": f"ContentState:{row.state_id}", "row": _row_snapshot(row.state)})

    # Governance revisions can reference a source exclusively through JSON, without any source FK.
    try:
        governance = apps.get_model("atlas", "GovernanceRevision")
    except LookupError:
        governance = None
    if governance is not None:
        for row in _query(governance, lock).select_related("record"):
            paths = _bibliographic_paths(row.payload, source, canonical_ids=True)
            linked = source.pk in row.source_ids or str(source.pk) in row.source_ids
            target = row.record.resource_type == "source_reference" and row.record.resource_id == source.pk
            if linked or paths or target:
                archive(row, "payload", paths or (["/resource_id"] if target else ["/"]), row.record.domain, review)
                if linked:
                    archive(row, "source_ids", ["/"], row.record.domain, review)
                contexts.append({"key": f"GovernanceRecord:{row.record_id}", "row": _row_snapshot(row.record)})
                for decision in _query(apps.get_model("atlas", "GovernanceDecision"), lock).filter(record_id=row.record_id):
                    contexts.append({"key": f"GovernanceDecision:{decision.pk}", "row": _row_snapshot(decision)})

    for row in _query(apps.get_model("atlas", "AdminArtifact"), lock).filter(resource_type="source_reference", resource_id=source.pk):
        archive(row, "resource_id", ["/resource_id"], "source", detail={"private": True})

    successors = [{"id": row.pk, "source_id": row.source_pk, "successor_id": row.successor_pk,
        "operation": row.operation, "plan_id": str(row.plan_id)} for row in
        _query(SourceSuccessor, lock).filter(Q(source_pk=source.pk) | Q(successor_pk=source.pk))]
    protection = [{"code": "SOURCE_PROTECTED", "key": item["key"], "message": "Checked claims retain their provenance."}
        for item in canonical if item["protected"]]
    try:
        protect_assessment_source(source.pk, connection.alias)
    except ValidationError:
        if not protection:
            protection.append({"code": "SOURCE_PROTECTED", "key": "", "message": "Checked Assessment claims retain their provenance."})
    public = {"canonical": canonical, "review": review, "archives": archives, "successors": successors,
        "counts": {"canonical": len(canonical), "review": len(review), "archives": len(archives), "successors": len(successors)},
        "protection": protection}
    return public, {"contexts": sorted(contexts, key=lambda x: x["key"]), "successors": successors}


def source_impact(source):
    return _impact(source)[0]


def source_fingerprint(source):
    return digest({"source": source_snapshot(source), "dependencies": _impact(source)[1]})


def required_views(impact):
    domains = {item.get("domain") for group in ("canonical", "review", "archives") for item in impact[group]}
    # Unknown adapters fail closed instead of exposing their payloads to a source-only reader.
    private = any(item.get("private") for group in ("canonical", "review", "archives") for item in impact[group])
    return sorted({"cms_source_view"} | ({"cms_owner"} if private else set()) |
        {"cms_" + domain + "_view" if domain else "cms_owner" for domain in domains})


def require_impact_scope(actor, impact):
    if not set(required_views(impact)) <= effective_permissions(actor):
        raise CMSFailure("SOURCE_IMPACT_SCOPE_DENIED")


def source_data(source, actor=None, impact=None, include_impact=True):
    snapshot = source_snapshot(source)
    if include_impact:
        impact = source_impact(source) if impact is None else impact
        visible = actor is None or set(required_views(impact)) <= effective_permissions(actor)
    else:
        visible = None
    return {"id": source.pk, **{k: snapshot[k] for k in SOURCE_FIELDS}, "provenance_versions": snapshot["provenance_versions"],
        "version": snapshot["version"], "archived": snapshot["archived"], "usage_count": sum(impact["counts"].values()) if visible else None,
        "impact_available": visible}


def normalized_pmid(value):
    value = re.sub(r"^(?:pmid:\s*|https?://pubmed\.ncbi\.nlm\.nih\.gov/)", "", value.strip(), flags=re.I).rstrip("/")
    if value and (not value.isascii() or not value.isdigit()):
        raise CMSFailure("INVALID_INPUT", 400)
    return value


def _changes(changes):
    if not isinstance(changes, dict) or set(changes) - SOURCE_FIELDS:
        raise CMSFailure("INVALID_FIELDS", 400)
    values = {}
    for field, value in changes.items():
        if field == "publication_year":
            if value is not None and (type(value) is not int or not 1 <= value <= 9999):
                raise CMSFailure("INVALID_INPUT", 400)
        elif field == "authors":
            if not isinstance(value, list) or len(value) > 100 or any(not isinstance(a, str) or not 1 <= len(a.strip()) <= 500 for a in value):
                raise CMSFailure("INVALID_INPUT", 400)
            value = [author.strip() for author in value]
        else:
            maximum = 120 if field == "resource_version" else SourceReference._meta.get_field(field).max_length or 20000
            if not isinstance(value, str) or len(value) > maximum:
                raise CMSFailure("INVALID_INPUT", 400)
            value = value.strip()
        if field == "doi":
            value = normalized_doi(value)
            if value and not re.fullmatch(r"10\.\d{4,9}/[^\s]+", value, re.ASCII):
                raise CMSFailure("INVALID_INPUT", 400)
        elif field == "pmid":
            value = normalized_pmid(value)
        elif field == "url":
            try:
                SourceReference()._validate_url(value)
                value = canonical_url(value)
            except (ValidationError, ValueError):
                raise CMSFailure("INVALID_INPUT", 400)
        values[field] = value
    return values


def _id(value):
    return type(value) is int and 1 <= value <= 2**63 - 1


def _request(data):
    if not isinstance(data, dict) or set(data) - {"operation", "source_id", "changes", "candidates", "field_choices", "mapping"}:
        raise CMSFailure("INVALID_FIELDS", 400)
    operation, source_id = data.get("operation"), data.get("source_id")
    if not isinstance(operation, str) or operation not in OPERATIONS or (source_id is not None and not _id(source_id)):
        raise CMSFailure("INVALID_INPUT", 400)
    candidates, mapping, choices = data.get("candidates", []), data.get("mapping", []), data.get("field_choices", {})
    if (not isinstance(candidates, list) or len(candidates) > 50 or any(not _id(pk) for pk in candidates)
            or len(set(candidates)) != len(candidates) or source_id in candidates):
        raise CMSFailure("INVALID_INPUT", 400)
    changes = _changes(data.get("changes", {}))
    if (operation == "create" and (source_id is not None or not changes.get("title"))
            or operation != "create" and source_id is None
            or operation not in {"merge", "split", "successor"} and candidates
            or operation in {"archive", "delete", "split", "successor"} and changes
            or operation == "merge" and not candidates or operation == "split" and len(candidates) < 2
            or operation == "successor" and len(candidates) != 1):
        raise CMSFailure("INVALID_INPUT", 400)
    if (not isinstance(choices, dict) or set(choices) - SOURCE_FIELDS or any(not _id(pk) for pk in choices.values())
            or operation != "merge" and choices):
        raise CMSFailure("INVALID_FIELD_CHOICES", 400)
    if not isinstance(mapping, list) or len(mapping) > 2000 or operation not in {"merge", "split"} and mapping:
        raise CMSFailure("INVALID_MAPPING", 400)
    keys = set()
    for item in mapping:
        if (not isinstance(item, dict) or set(item) not in ({"key", "action"}, {"key", "action", "target_id"})
                or not isinstance(item.get("key"), str) or len(item["key"]) > 200 or item["key"] in keys
                or item.get("action") not in {"move", "retain"}
                or item["action"] == "move" and not _id(item.get("target_id"))
                or item["action"] == "retain" and "target_id" in item):
            raise CMSFailure("INVALID_MAPPING", 400)
        keys.add(item["key"])
    return {"operation": operation, "source_id": source_id, "changes": changes, "candidates": sorted(candidates),
        "field_choices": choices, "mapping": sorted(mapping, key=lambda x: x["key"])}


def _authority(actor_id, session_id, operation):
    actor = User.objects.filter(pk=actor_id).first()
    if actor is None:
        raise CMSFailure("UNAUTHENTICATED")
    current_session(session_id, actor)
    for capability in ("cms_enter", "cms_source_view", "cms_source_preview", "cms_source_validate", "cms_source_" + OPERATIONS[operation]):
        require(actor, capability)
    if operation == "delete":
        require(actor, "cms_source_delete_preview")
    return actor


def _identity(snapshot):
    return {"doi": normalized_doi(snapshot["doi"]), "pmid": snapshot["pmid"].strip(),
        "bibliography": (normalized_text(snapshot["title"]), tuple(normalized_text(a) for a in snapshot["authors"]),
            snapshot["publication_year"], snapshot["resource_version"])}


def _same_identity(left, right):
    a, b = _identity(left), _identity(right)
    return (any(a[field] and a[field] == b[field] for field in ("doi", "pmid"))
        or bool(a["bibliography"][1] and a["bibliography"][2]) and a["bibliography"] == b["bibliography"])


def _identity_conflict(left, right):
    a, b = _identity(left), _identity(right)
    return any(a[f] and b[f] and a[f] != b[f] for f in ("doi", "pmid"))


def _view_snapshot(value):
    return {key: value[key] for key in ({"id", "version", "archived", "deleted", "provenance_versions"} | SOURCE_FIELDS) if key in value}


def _write_canonical(spec, sources):
    op, changes = spec["operation"], spec["changes"]
    source = copy(sources[spec["source_id"]]) if spec["source_id"] is not None else SourceReference()
    if op in {"create", "update", "merge"}:
        for name, value in changes.items():
            if name != "resource_version":
                setattr(source, name, value)
        source.save()
        sources[source.pk] = source
    if op == "delete":
        source.delete()
    for item in spec["mapping"]:
        if item["action"] != "move":
            continue
        model_name, pk, field = item["key"].split(":")
        model = apps.get_model("atlas", model_name)
        row = model.objects.select_for_update().get(pk=pk)
        setattr(row, field, sources[item["target_id"]])
        try:
            row.full_clean()
            row.save()
        except (ValidationError, ProtectedError) as error:
            codes = [getattr(e, "code", None) for errors in getattr(error, "error_dict", {}).values() for e in errors]
            failure = CMSFailure("UNIQUENESS_CONFLICT" if any(c in {"unique", "unique_together"} for c in codes) else "CONSUMER_VALIDATION", 409)
            failure.detail["key"] = item["key"]
            raise failure from error
    return source.pk


def _validate(spec, actor, role_policy):
    """Caller owns policy lock; acquire the domain lock before any source/claim row locks."""
    lock_brain_curation(connection.alias)
    ids = sorted({spec["source_id"], *spec["candidates"]} - {None})
    sources = {row.pk: row for row in SourceReference.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    if len(sources) != len(ids):
        raise CMSFailure("NOT_FOUND", 404)
    snapshots = {pk: source_snapshot(source) for pk, source in sources.items()}
    impacts, dependencies = {}, {}
    for pk, source in sources.items():
        impacts[pk], dependencies[pk] = _impact(source, lock=True)
        require_impact_scope(actor, impacts[pk])
    required = sorted({"cms_source_view"} | {cap for impact in impacts.values() for cap in required_views(impact)})
    preview = {"normalization": spec["changes"], "comparisons": [], "identity_conflicts": [], "mapping": spec["mapping"],
        "blockers": [], "manual_plan": [], "counts": {"moved": 0, "unchanged": 0, "blocked": 0},
        "rereview": [item for impact in impacts.values() for item in impact["review"]], "required_views": required}

    def block(code, key="", message="This plan requires an explicit correction or manual review."):
        preview["blockers"].append({"code": code, "key": key, "message": message})

    op, main = spec["operation"], spec["source_id"]
    for pk, snapshot in snapshots.items():
        if snapshot["deleted"] or snapshot["archived"] and not (pk == main and op in {"delete", "successor"}):
            block("SOURCE_ARCHIVED", str(pk))
    if op in {"update", "archive", "delete"}:
        preview["blockers"].extend(impacts[main]["protection"])
    if op == "delete" and sum(impacts[main]["counts"].values()):
        block("SOURCE_IN_USE")
    if op == "merge":
        survivor = snapshots[main]
        for pk in spec["candidates"]:
            candidate = snapshots[pk]
            preview["comparisons"].append({"source_id": pk, "fields": {field: [survivor[field], candidate[field]] for field in sorted(SOURCE_FIELDS)}})
            if _identity_conflict(survivor, candidate):
                block("IDENTITY_CONFLICT", str(pk))
            elif not _same_identity(survivor, candidate):
                block("IDENTITY_UNCONFIRMED", str(pk))
            if survivor["resource_version"] != candidate["resource_version"]:
                block("RESOURCE_VERSION_CONFLICT", str(pk))
        differing = {field for field in SOURCE_FIELDS if any(snapshots[pk][field] != survivor[field] for pk in spec["candidates"])}
        if set(spec["field_choices"]) - differing:
            raise CMSFailure("INVALID_FIELD_CHOICES", 400)
        for field in sorted(differing):
            selected = spec["field_choices"].get(field)
            if selected is None:
                block("FIELD_CHOICE_REQUIRED", field)
            elif selected not in snapshots:
                raise CMSFailure("INVALID_FIELD_CHOICES", 400)
            else:
                chosen = _changes({field: snapshots[selected][field]})[field]
                if field in spec["changes"] and spec["changes"][field] != chosen:
                    raise CMSFailure("INVALID_FIELD_CHOICES", 400)
                spec["changes"][field] = chosen
        if spec["changes"] and any(survivor[field] != value for field, value in spec["changes"].items()):
            preview["blockers"].extend(impacts[main]["protection"])
    if op == "split":
        for left, right in combinations(spec["candidates"], 2):
            if _same_identity(snapshots[left], snapshots[right]):
                block("IDENTITY_CONFLICT")
    if op in {"merge", "split"}:
        from_ids = spec["candidates"] if op == "merge" else [main]
        usages = {item["key"]: item for pk in from_ids for group in ("canonical", "review", "archives") for item in impacts[pk][group]}
        mappings = {item["key"]: item for item in spec["mapping"]}
        if set(mappings) - set(usages):
            raise CMSFailure("INVALID_MAPPING", 400)
        for key, usage in usages.items():
            item = mappings.get(key)
            if item is None:
                block("MAPPING_REQUIRED", key)
                continue
            if item["action"] == "retain":
                preview["counts"]["unchanged"] += 1
                if not usage["mutable"] or usage.get("protected"):
                    preview["manual_plan"].append({"key": key, "code": "IMMUTABLE_REFERENCE" if not usage["mutable"] else "SOURCE_PROTECTED"})
                continue
            allowed = [main] if op == "merge" else spec["candidates"]
            if item["target_id"] not in allowed:
                raise CMSFailure("INVALID_MAPPING", 400)
            if not usage["mutable"]:
                block("IMMUTABLE_REFERENCE", key)
            elif usage.get("protected"):
                block("SOURCE_PROTECTED", key)
            else:
                require(actor, "cms_" + usage["domain"] + "_edit")
                preview["counts"]["moved"] += 1
    if op in {"update", "merge"}:
        for pin in snapshots[main]["provenance_versions"].values():
            if "resource_version" in spec["changes"] and pin != spec["changes"]["resource_version"]:
                block("RESOURCE_VERSION_CONFLICT", "resource_version")
        if op == "update" and not any(snapshots[main][field] != value for field, value in spec["changes"].items()):
            block("NO_CHANGES")
    if op in {"merge", "split", "successor"}:
        edges = list(SourceSuccessor.objects.values_list("source_pk", "successor_pk"))
        new_edges = [(pk, main) for pk in spec["candidates"]] if op == "merge" else [(main, pk) for pk in spec["candidates"]]
        adjacency = {}
        for left, right in edges + new_edges:
            adjacency.setdefault(left, set()).add(right)
        for left, right in new_edges:
            pending, seen = [right], set()
            while pending:
                node = pending.pop()
                if node == left:
                    block("SUCCESSOR_CYCLE")
                    break
                if node not in seen:
                    seen.add(node)
                    pending.extend(adjacency.get(node, ()))
    candidate = {**(_row_snapshot(SourceReference()) if main is None else snapshots[main]), **spec["changes"]}
    candidate.setdefault("resource_version", "")
    competitors = []
    if op in {"create", "update", "merge"}:
        for source in SourceReference.objects.exclude(pk__in=ids).order_by("pk"):
            snapshot = source_snapshot(source)
            if _same_identity(candidate, snapshot):
                competitors.append(_view_snapshot(snapshot))
                preview["identity_conflicts"].append({"source_id": source.pk, "code": "IDENTITY_CONFLICT"})
                block("IDENTITY_CONFLICT", str(source.pk))
    # Bind the original normalized request too; preview validation never edits the caller's dict.
    fingerprint = digest({"sources": {str(pk): value for pk, value in snapshots.items()},
        "dependencies": {str(pk): value for pk, value in dependencies.items()}, "competitors": competitors,
        "policy_version": role_policy.version, "request": spec})
    if not preview["blockers"]:
        try:
            with transaction.atomic():
                _write_canonical(spec, dict(sources))
                transaction.set_rollback(True)
        except CMSFailure as error:
            block(str(error.detail["code"]), str(error.detail.get("key", "")))
        except ProtectedError:
            block("SOURCE_PROTECTED")
        except ValidationError:
            block("CONSUMER_VALIDATION")
        except IntegrityError:
            block("UNIQUENESS_CONFLICT")
    preview["normalization"] = dict(spec["changes"])
    preview["counts"]["blocked"] = len(preview["blockers"])
    preview["can_apply"] = not preview["blockers"]
    return sources, snapshots, impacts, fingerprint, preview


def _audit(actor, plan, action, policy, request_id):
    AdminAuditEvent.objects.create(actor=actor, action="source." + action, outcome="success", target_id=plan.source_pk,
        target_key=str(plan.pk), base_revision=1 if action != "preview" else 0, new_revision=2 if action != "preview" else 1,
        diff=sorted(plan.request["changes"]), reason="SOURCE_" + plan.operation.upper(), request_id=request_id, policy_version=policy.version)


def preview_source(actor_id, session_id, data, request_id):
    spec = _request(data)
    with policy_lock() as policy:
        actor = _authority(actor_id, session_id, spec["operation"])
        sources, _, _, fingerprint, preview = _validate(spec, actor, policy)
        plan = SourcePlan.objects.create(operation=spec["operation"], source_pk=spec["source_id"], source_ids=sorted(sources),
            request=spec, fingerprint=fingerprint, preview=preview, actor=actor, actor_ref=attribution(actor.pk))
        _audit(actor, plan, "preview", policy, request_id)
        return plan


def require_plan_scope(actor, plan):
    require(actor, "cms_source_view")
    if not set(plan.preview["required_views"]) <= effective_permissions(actor):
        raise CMSFailure("SOURCE_IMPACT_SCOPE_DENIED")
    for source in SourceReference.objects.filter(pk__in=plan.source_ids):
        require_impact_scope(actor, source_impact(source))


def plan_data(plan, actor=None):
    if actor is not None:
        require_plan_scope(actor, plan)
    receipt = SourcePlanReceipt.objects.filter(plan=plan).first()
    return {"id": str(plan.pk), "schema_version": plan.schema_version, "version": 2 if receipt else plan.version,
        "status": "applied" if receipt else "preview", "operation": plan.operation, "source_id": plan.source_pk,
        "request": plan.request, "fingerprint": plan.fingerprint, "preview": plan.preview,
        "created_at": plan.created_at, "receipt": receipt.result if receipt else None}


def apply_source_plan(actor_id, session_id, plan_id, expected, request_id):
    with policy_lock() as policy:
        plan = SourcePlan.objects.filter(pk=plan_id).first()
        if plan is None:
            raise CMSFailure("NOT_FOUND", 404)
        actor = _authority(actor_id, session_id, plan.operation)
        require_plan_scope(actor, plan)
        if expected != plan.version:
            raise CMSFailure("STALE_REVISION", 412)
        if SourcePlanReceipt.objects.filter(plan=plan).exists():
            raise CMSFailure("SOURCE_PLAN_APPLIED", 409)
        if plan.schema_version != 1:
            raise CMSFailure("SOURCE_PLAN_BLOCKED", 409)
        spec = _request(plan.request)
        sources, before, impacts, fingerprint, preview = _validate(spec, actor, policy)
        if fingerprint != plan.fingerprint:
            raise CMSFailure("STALE_SOURCE_PLAN", 412)
        if not preview["can_apply"] or not plan.preview["can_apply"]:
            raise CMSFailure("SOURCE_PLAN_BLOCKED", 409)
        # Keep original claim/locator/FK snapshots in retained history before moving evidence.
        for pk in before:
            before[pk] = {**before[pk], "usages": _impact(sources[pk])[1]}
        main_id = _write_canonical(spec, sources)
        if plan.operation == "create":
            affected = [main_id]
        elif plan.operation in {"merge", "split", "successor"}:
            affected = sorted(sources)
        else:
            affected = [plan.source_pk]
        history_ids, successor_ids = [], []
        if plan.operation in {"merge", "split", "successor"}:
            edges = [(pk, plan.source_pk) for pk in spec["candidates"]] if plan.operation == "merge" else [(plan.source_pk, pk) for pk in spec["candidates"]]
            for left, right in edges:
                successor_ids.append(SourceSuccessor.objects.create(source_pk=left, successor_pk=right, plan=plan, operation=plan.operation).pk)
        for pk in affected:
            state, _ = SourceState.objects.get_or_create(source_pk=pk)
            state.version += 1
            if pk == main_id and "resource_version" in spec["changes"]:
                state.resource_version = spec["changes"]["resource_version"]
            if plan.operation == "archive":
                state.archived = True
            elif plan.operation == "delete":
                state.deleted = True
            state.full_clean()
            state.save()
            if plan.operation != "delete":
                current = SourceReference.objects.get(pk=pk)
                after = {**source_snapshot(current), "usages": _impact(current)[1]}
            else:
                after = {**before[pk], "deleted": True, "version": state.version}
            history_ids.append(SourceHistory.objects.create(source_pk=pk, version=state.version, plan=plan,
                operation=plan.operation, before=before.get(pk, {}), after=after, actor=actor, actor_ref=attribution(actor.pk)).pk)
        result = {"source_ids": affected, "counts": preview["counts"], "history_ids": history_ids, "successor_ids": successor_ids}
        SourcePlanReceipt.objects.create(plan=plan, result=result, actor=actor, actor_ref=attribution(actor.pk))
        _audit(actor, plan, ACTION[plan.operation], policy, request_id)
        return plan
