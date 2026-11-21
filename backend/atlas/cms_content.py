"""Typed immutable proposals; canonical publication/withdrawal belongs to P16."""
import hashlib
import json
import re
import unicodedata
import uuid

from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, ManyToManyRel, ManyToOneRel, OneToOneRel, Q

from .cms_audit import CONTENT_REASONS, changed_fields
from .cms_content_models import ContentRevision, ContentState
from .cms_domains import (DOMAIN_SPECS, MODEL_KINDS, dependency_snapshot, domain_for, entry_tuple,
    preview_snapshot, required_reference_capabilities, schema_data, validate_snapshot)
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_sessions import current_session
from .models import ConceptAlias

REGISTRY = {kind: entry_tuple(kind) for kind in DOMAIN_SPECS}
CategoryProposal = REGISTRY["category"][1]
DisorderProposal = REGISTRY["disorder"][1]

# P07.04: bounded, read-only duplicate evidence. These kinds own a human-facing
# name and a persisted identity; relationship kinds are intentionally excluded.
DUPLICATE_KINDS = {
    "category": {"identity": "slug", "names": ("name_en", "name_fa")},
    "disorder": {"identity": "slug", "names": ("name_en", "name_fa")},
    "symptom": {"identity": "slug", "names": ("name_en", "name_fa")},
    "concept": {"identity": "slug", "names": ("name_en", "name_fa")},
    "dsm-corpus": {"identity": "key", "names": ("title",)},
    "dsm-record": {"identity": "master_id", "names": ("name_en", "name_fa")},
}
MAX_DUPLICATE_CANDIDATES = 50
MAX_DUPLICATE_POOL = 400
LEXICAL_THRESHOLD = 0.6
IMPACT_LABELS = {"CASCADE": "cascade", "PROTECT": "protect", "RESTRICT": "protect",
    "SET_NULL": "detach", "SET_DEFAULT": "detach", "DO_NOTHING": "orphan_risk", "LINK": "link"}


def _normalize_duplicate_text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _duplicate_tokens(value):
    return set(re.findall(r"[^\W_]+", _normalize_duplicate_text(value), flags=re.UNICODE))


def _token_similarity(left, right):
    return len(left & right) / len(left | right) if left and right else 0.0


def _duplicate_aliases(kind, obj):
    if kind != "concept":
        return []
    return list(ConceptAlias.objects.filter(concept_id=obj.pk).order_by("pk").values_list("text", flat=True)[:100])


def _duplicate_pool(kind, obj):
    model, _, _ = kind_entry(kind)
    spec = DUPLICATE_KINDS[kind]
    base = model.objects.exclude(pk=obj.pk)
    if kind == "dsm-record":
        base = base.filter(corpus_id=obj.corpus_id)
    ids = set()
    identity = getattr(obj, spec["identity"], "")
    if identity:
        ids.update(base.filter(**{spec["identity"] + "__iexact": identity})
            .order_by("pk").values_list("pk", flat=True)[:MAX_DUPLICATE_POOL])
    names = [getattr(obj, field, "") for field in spec["names"]]
    aliases = _duplicate_aliases(kind, obj)
    for field in spec["names"]:
        for value in names:
            if isinstance(value, str) and value:
                ids.update(base.filter(**{field + "__iexact": value})
                    .order_by("pk").values_list("pk", flat=True)[:MAX_DUPLICATE_POOL])
    tokens = set()
    for value in names + aliases:
        tokens.update(token for token in _duplicate_tokens(value) if len(token) >= 3)
    if tokens:
        condition = Q(pk__in=[])
        for field in spec["names"]:
            for token in sorted(tokens)[:12]:
                condition |= Q(**{field + "__icontains": token})
        ids.update(base.filter(condition).order_by("pk").values_list("pk", flat=True)[:MAX_DUPLICATE_POOL])
    if kind == "concept":
        exact = {value for value in names + aliases if isinstance(value, str) and value}
        if exact:
            ids.update(ConceptAlias.objects.filter(text__in=exact).order_by("pk")
                .values_list("concept_id", flat=True)[:MAX_DUPLICATE_POOL])
        alias_condition = Q(pk__in=[])
        for token in sorted(tokens)[:12]:
            alias_condition |= Q(text__icontains=token)
        if tokens:
            ids.update(ConceptAlias.objects.filter(alias_condition).order_by("pk")
                .values_list("concept_id", flat=True)[:MAX_DUPLICATE_POOL])
    ids.discard(obj.pk)
    return model.objects.filter(pk__in=ids).order_by("pk"), len(ids) > MAX_DUPLICATE_POOL


def _duplicate_evidence(kind, obj, candidate, aliases):
    spec = DUPLICATE_KINDS[kind]
    subject_identity = _normalize_duplicate_text(getattr(obj, spec["identity"], ""))
    candidate_identity = _normalize_duplicate_text(getattr(candidate, spec["identity"], ""))
    evidence, rank, score = [], 3, 0.0
    if subject_identity and subject_identity == candidate_identity:
        evidence.append({"type": "identity", "field": spec["identity"], "value": getattr(candidate, spec["identity"])})
        rank, score = 0, 1.0
    subject_names = {field: _normalize_duplicate_text(getattr(obj, field, "")) for field in spec["names"]}
    candidate_names = {field: _normalize_duplicate_text(getattr(candidate, field, "")) for field in spec["names"]}
    matched_names = sorted(field for field in spec["names"] if subject_names[field] and subject_names[field] == candidate_names[field])
    if matched_names:
        evidence.append({"type": "name", "fields": matched_names, "value": next(getattr(candidate, field) for field in matched_names)})
        rank, score = min(rank, 1), max(score, 0.9)
    subject_aliases = {_normalize_duplicate_text(value) for value in _duplicate_aliases(kind, obj) if value}
    candidate_aliases = {_normalize_duplicate_text(value) for value in aliases if value}
    alias_hits = sorted(subject_aliases & (candidate_aliases | set(candidate_names.values())))
    if alias_hits:
        evidence.append({"type": "alias", "values": alias_hits[:5]})
        rank, score = min(rank, 1), max(score, 0.85)
    if rank > 1:
        subject_tokens = set().union(*[_duplicate_tokens(value) for value in set(subject_names.values()) | subject_aliases])
        candidate_tokens = set().union(*[_duplicate_tokens(value) for value in set(candidate_names.values()) | candidate_aliases])
        similarity = _token_similarity(subject_tokens, candidate_tokens)
        if similarity >= LEXICAL_THRESHOLD:
            evidence.append({"type": "token", "similarity": round(similarity, 4)})
            rank, score = 2, similarity
    if not evidence:
        return None
    label = next((getattr(candidate, field) for field in spec["names"] if getattr(candidate, field, "")),
        str(getattr(candidate, spec["identity"], "") or candidate.pk))
    return {"id": candidate.pk, "label": str(label)[:500], "tier": {0: "identity_conflict", 1: "probable_duplicate",
        2: "lexical_only"}[rank], "score": round(score, 4), "evidence": evidence,
        "is_active": bool(getattr(candidate, "is_active", True)),
        "identity": {"field": spec["identity"], "value": getattr(candidate, spec["identity"], None)}}


def duplicate_candidates(actor, kind, target_id):
    """Read-only duplicate evidence; never merges, deletes or rewrites an identity."""
    kind_entry(kind)
    if kind not in DUPLICATE_KINDS:
        raise CMSFailure("INVALID_QUERY", 400)
    state, obj = resolve(actor, kind, target_id)
    if obj is None:
        return {"kind": kind, "domain": domain_for(kind), "state_id": str(state.pk), "canonical_pk": None,
            "subject": None, "candidates": [], "count": 0, "truncated": False,
            "tiers": {"identity_conflict": 0, "probable_duplicate": 0, "lexical_only": 0},
            "merge_available": False, "canonical_write": 0, "reason": "NO_CANONICAL_IDENTITY",
            "notice": "پیش‌نویس بدون هویت اصلی است؛ نامزد تکراری فقط برای رکورد اصلی محاسبه می‌شود."}
    pool, truncated = _duplicate_pool(kind, obj)
    candidates = list(pool[:MAX_DUPLICATE_POOL])
    alias_map = {}
    if kind == "concept" and candidates:
        for concept_id, text in ConceptAlias.objects.filter(concept_id__in=[row.pk for row in candidates]).order_by("pk").values_list("concept_id", "text"):
            alias_map.setdefault(concept_id, []).append(text)
    state_ids = dict(ContentState.objects.filter(kind=kind, canonical_pk__in=[row.pk for row in candidates])
        .values_list("canonical_pk", "pk"))
    results = []
    for candidate in candidates:
        evidence = _duplicate_evidence(kind, obj, candidate, alias_map.get(candidate.pk, []))
        if evidence is None:
            continue
        evidence["state_id"] = str(state_ids[candidate.pk]) if candidate.pk in state_ids else None
        results.append(evidence)
    order = {"identity_conflict": 0, "probable_duplicate": 1, "lexical_only": 2}
    results.sort(key=lambda row: (order[row["tier"]], -row["score"], row["id"]))
    truncated = truncated or len(results) > MAX_DUPLICATE_CANDIDATES
    results = results[:MAX_DUPLICATE_CANDIDATES]
    spec = DUPLICATE_KINDS[kind]
    subject_label = next((getattr(obj, field) for field in spec["names"] if getattr(obj, field, "")),
        str(getattr(obj, spec["identity"], "") or obj.pk))
    return {"kind": kind, "domain": domain_for(kind), "state_id": str(state.pk), "canonical_pk": obj.pk,
        "subject": {"label": str(subject_label)[:500], "identity": {"field": spec["identity"],
            "value": getattr(obj, spec["identity"], None)}},
        "candidates": results, "count": len(results), "truncated": truncated,
        "tiers": {tier: sum(1 for row in results if row["tier"] == tier) for tier in order},
        "merge_available": False, "canonical_write": 0,
        "notice": "فقط شواهد خواندنی؛ هیچ merge، حذف یا بازنویسی هویت انجام نمی‌شود."}


def _impact_relations(model):
    for field in model._meta.get_fields():
        if not isinstance(field, (ManyToOneRel, ManyToManyRel, OneToOneRel)):
            continue
        related = field.related_model
        if related.__module__.startswith("atlas.cms_"):
            continue
        accessor = field.get_accessor_name()
        if not accessor or accessor.startswith("+"):
            continue
        fk = getattr(field, "field", None)
        on_delete = getattr(getattr(fk, "remote_field", None), "on_delete", None)
        yield field, related, accessor, getattr(on_delete, "__name__", "LINK" if isinstance(field, ManyToManyRel) else "UNKNOWN")


def _relation_count(obj, field, related, accessor):
    if isinstance(field, ManyToManyRel):
        return getattr(obj, accessor).count()
    return related._base_manager.filter(**{field.field.name: obj}).count()


def archive_impact(actor, kind, target_id):
    """Live reverse-relation counts for archive review; performs no canonical write."""
    kind_entry(kind)
    state, obj = resolve(actor, kind, target_id)
    if obj is None:
        return {"kind": kind, "domain": domain_for(kind), "state_id": str(state.pk), "canonical_pk": None,
            "relations": [], "totals": {"relations": 0, "checked_relations": 0, "rows": 0, "by_impact": {}},
            "impact_digest": digest({"kind": kind, "canonical_pk": None, "relations": []}),
            "canonical_write": 0, "raw_archive_changed": False, "search_graph": "computed_at_read_time",
            "reason": "NO_CANONICAL_RECORD", "notice": "پیش‌نویس منتشرنشده اثر بایگانی اصلی ندارد."}
    relations = []
    for field, related, accessor, on_delete in _impact_relations(type(obj)):
        count = _relation_count(obj, field, related, accessor)
        kind_name = MODEL_KINDS.get(related)
        relations.append({"model": related._meta.label_lower, "field": field.field.name if not isinstance(field, ManyToManyRel) else field.name,
            "label": str(related._meta.verbose_name), "count": count, "on_delete": on_delete,
            "impact": IMPACT_LABELS.get(on_delete, "link" if isinstance(field, ManyToManyRel) else "other"),
            "domain": domain_for(kind_name) if kind_name else "other"})
    relations.sort(key=lambda row: (row["model"], row["field"]))
    by_impact = {}
    for row in relations:
        if row["count"]:
            by_impact[row["impact"]] = by_impact.get(row["impact"], 0) + row["count"]
    digest_input = [[row["model"], row["field"], row["count"], row["on_delete"]] for row in relations]
    return {"kind": kind, "domain": domain_for(kind), "state_id": str(state.pk), "canonical_pk": obj.pk,
        "relations": relations, "totals": {"relations": sum(1 for row in relations if row["count"]),
            "checked_relations": len(relations), "rows": sum(row["count"] for row in relations),
            "by_impact": by_impact},
        "impact_digest": digest({"kind": kind, "canonical_pk": obj.pk, "relations": digest_input}),
        "content_state": {"version": state.version, "publication": state.publication,
            "revision_status": state.current_revision.status if state.current_revision_id else None,
            "intent": state.current_revision.intent if state.current_revision_id else None,
            "legacy_origin": state.legacy_origin, "revisions": state.revisions.count()},
        "canonical_write": 0, "raw_archive_changed": False, "search_graph": "computed_at_read_time",
        "notice": "شمارش‌ها از روابط ORM فعلی‌اند؛ پیش‌نمایش بایگانی هیچ نوشتن، merge یا تغییر raw انجام نمی‌دهد."}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        cls=DjangoJSONEncoder).encode()).hexdigest()


def kind_entry(kind):
    if kind not in REGISTRY:
        raise CMSFailure("NOT_FOUND", 404)
    return REGISTRY[kind]


def capability(kind, action):
    kind_entry(kind)
    return "cms_%s_%s" % (domain_for(kind), action)


def require_references(actor, kind, payload):
    for cap in required_reference_capabilities(kind, payload):
        require(actor, cap)


def scoped_states(actor, rows):
    held = effective_permissions(actor)
    visible = Q(pk__in=[])
    for kind in REGISTRY:
        if capability(kind, "view") not in held:
            continue
        scope = Q(kind=kind)
        for field in schema_data(kind)["fields"]:
            if field["type"] == "reference" and not set(required_reference_capabilities(kind, {field["name"]: 1})) <= held:
                key = "current_revision__payload__" + field["name"]
                scope &= Q(**{key + "__isnull": True}) | Q(**{key: None})
        visible |= scope
    return rows.filter(visible)


def scoped_revisions(actor, kind, rows):
    held = effective_permissions(actor)
    for field in schema_data(kind)["fields"]:
        if field["type"] == "reference" and not set(required_reference_capabilities(kind, {field["name"]: 1})) <= held:
            key = "payload__" + field["name"]
            rows = rows.filter(Q(**{key + "__isnull": True}) | Q(**{key: None}))
    return rows


def canonical_snapshot(kind, obj):
    return {key: getattr(obj, key) for key in kind_entry(kind)[2]}


def editable_snapshot(kind, obj):
    legacy = {"category": ("name_en", "name_fa", "description"),
        "disorder": ("name_en", "name_fa", "short_description", "overview")}
    if kind in legacy:
        return {key: getattr(obj, key) for key in legacy[kind]}
    model, serializer, _ = kind_entry(kind)
    return json.loads(json.dumps({key: getattr(obj, model._meta.get_field(key).attname)
        for key, field in serializer().fields.items() if not field.read_only
        and not next((item["create_only"] for item in schema_data(kind)["fields"] if item["name"] == key), False)},
        cls=DjangoJSONEncoder))


def dependencies(kind, obj, payload=None, lock=False):
    # Keep P02's persisted edit dependency hashes exactly representable.
    if kind in {"category", "disorder"}:
        if kind == "disorder" and obj is not None:
            from .models import Category
            rows = Category.objects.select_for_update() if lock else Category.objects
            category = rows.get(pk=obj.category_id)
            legacy = {"category_id": category.pk, "category": canonical_snapshot("category", category)}
        else:
            legacy = {}
        if payload is None:
            return digest(legacy)
    return digest(dependency_snapshot(kind, obj, payload, lock))


def resolve(actor, kind, target_id, lock=False):
    kind_entry(kind)
    if capability(kind, "view") not in effective_permissions(actor):
        raise CMSFailure("NOT_FOUND", 404)
    rows = ContentState.objects.filter(kind=kind)
    if lock:
        rows = rows.select_for_update()
    if isinstance(target_id, str) and target_id.isascii() and target_id.isdigit() and len(target_id) <= 18:
        state = rows.filter(canonical_pk=int(target_id)).first()
    else:
        try:
            state = rows.filter(pk=uuid.UUID(str(target_id))).first()
        except (ValueError, TypeError, AttributeError):
            state = None
    if state is None:
        raise CMSFailure("NOT_FOUND", 404)
    obj = None
    if state.canonical_pk is not None:
        canonical = kind_entry(kind)[0].objects
        if lock:
            canonical = canonical.select_for_update()
        obj = canonical.filter(pk=state.canonical_pk).first()
        if obj is None:
            raise CMSFailure("NOT_FOUND", 404)
    require_references(actor, kind, state.current_revision.payload)
    return state, obj


def validate_payload(kind, data, partial=False):
    fields = kind_entry(kind)[1]().fields
    policies = {item["name"]: item for item in schema_data(kind)["fields"]}
    if (not isinstance(data, dict) or not data or any(key not in fields or fields[key].read_only
            or (partial and policies.get(key, {}).get("create_only")) for key in data)):
        raise CMSFailure("INVALID_FIELDS", 400)
    form = kind_entry(kind)[1](data=data, partial=partial)
    form.is_valid(raise_exception=True)
    return json.loads(json.dumps(dict(form.validated_data), cls=DjangoJSONEncoder))


def immutable_metadata(kind, obj):
    if obj is None:
        return {}
    model = kind_entry(kind)[0]
    result = {}
    for item in schema_data(kind)["fields"]:
        key = item["name"]
        if not (item["readonly_reason"] or item["create_only"]):
            continue
        value = getattr(obj, model._meta.get_field(key).attname)
        if isinstance(value, (dict, list)) or key in {"raw_document", "source_payload"}:
            encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), cls=DjangoJSONEncoder).encode()
            result[key] = {"sha256": hashlib.sha256(encoded).hexdigest(), "size_bytes": len(encoded)}
        else:
            result[key] = value
    return result


def safe_payload(kind, data):
    fields = kind_entry(kind)[1]().fields
    return {key: value for key, value in data.items()
        if key in fields and not fields[key].read_only and key not in {"raw_document", "source_payload"}}


def field_values(kind, obj, payload):
    model, serializer, _ = kind_entry(kind)
    values = {key: getattr(obj, model._meta.get_field(key).attname)
        for key in serializer.Meta.fields if key not in {"raw_document", "source_payload"}} if obj is not None else {}
    values.update(safe_payload(kind, payload))
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def revision_data(state, obj=None):
    revision = state.current_revision
    if obj is None and state.canonical_pk is not None:
        obj = kind_entry(state.kind)[0].objects.filter(pk=state.canonical_pk).first()
    return {"id": str(state.pk), "kind": state.kind, "domain": domain_for(state.kind), "canonical_pk": state.canonical_pk,
        "version": state.version, "canonical_digest": state.canonical_digest, "publication": state.publication,
        "legacy_origin": state.legacy_origin, "current_revision": revision.pk if revision else None,
        "revision_status": revision.status if revision else None, "payload": safe_payload(state.kind, revision.payload) if revision else {},
        "field_values": field_values(state.kind, obj, revision.payload if revision else {}),
        "intent": revision.intent if revision else "edit", "immutable_fields": immutable_metadata(state.kind, obj),
        "payload_digest": revision.payload_digest if revision else digest({}),
        "dependency_digest": revision.dependency_digest if revision else digest({})}


def stale(state, expected, submitted, current):
    base = state.revisions.filter(sequence=expected).first()
    base_payload = base.payload if base else {}
    mine = {**base_payload, **submitted}
    fields = changed_fields(base_payload, current) + changed_fields(base_payload, mine)
    exc = CMSFailure("STALE_REVISION", 412, "نسخه تغییر کرده است؛ نسخهٔ فعلی را دریافت و تغییرها را دوباره بررسی کنید.")
    exc.detail.update({"current_revision": state.version, "current_etag": '"%s"' % state.version,
        "diff": [{"field": key, "mine_changed": base_payload.get(key) != mine.get(key),
                  "current_changed": base_payload.get(key) != current.get(key)} for key in sorted(set(fields))],
        "blockers": ["RELOAD_AND_REBASE"]})
    return exc


def check_current(state, obj, expected, base_digest=None, submitted=None):
    actual_digest = digest(canonical_snapshot(state.kind, obj)) if obj else digest({})
    if expected != state.version or (base_digest is not None and base_digest != state.canonical_digest) or actual_digest != state.canonical_digest:
        error = stale(state, expected, submitted or {}, state.current_revision.payload)
        if actual_digest != state.canonical_digest:
            error.detail["blockers"] = ["CANONICAL_RECONCILIATION_REQUIRED"]
        raise error
    if state.current_revision.payload_digest != digest(state.current_revision.payload):
        raise CMSFailure("PAYLOAD_CHANGED", 409)


def propose(actor_id, session_id, kind, target_id, data, expected, base_digest, reason, request_id):
    with policy_lock() as policy:
        kind_entry(kind)
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, capability(kind, "edit" if target_id is not None else "create"))
        require(actor, capability(kind, "view"))
        require_references(actor, kind, data if isinstance(data, dict) else {})
        patch = validate_payload(kind, data, partial=target_id is not None)
        if not isinstance(reason, str) or reason not in CONTENT_REASONS:
            raise CMSFailure("INVALID_REASON", 400)
        if target_id is None:
            state = ContentState.objects.create(kind=kind, canonical_digest=digest({}))
            before, obj = {}, None
        else:
            state, obj = resolve(actor, kind, target_id, lock=True)
            before = state.current_revision.payload
            check_current(state, obj, expected, base_digest, patch)
            if base_digest is None:
                raise stale(state, expected, patch, before)
            if state.current_revision.status not in {"legacy", "draft", "changes_requested"}:
                raise CMSFailure("INVALID_TRANSITION", 409)
        after = {**before, **patch}
        require_references(actor, kind, after)
        after = validate_snapshot(kind, after, obj)
        revision = ContentRevision.objects.create(state=state, sequence=state.version + 1,
            base_version=state.version, base_digest=state.canonical_digest, payload=after, payload_digest=digest(after),
            dependency_digest=dependencies(kind, obj, after, True), schema_version=2,
            intent=state.current_revision.intent if target_id is not None else "edit", actor=actor)
        if ContentState.objects.filter(pk=state.pk, version=state.version).update(version=F("version") + 1,
                current_revision=revision, publication="pending_update" if state.publication in {"current", "pending_update"} else state.publication) != 1:
            raise CMSFailure("STALE_REVISION", 412)
        AdminAuditEvent.objects.create(actor=actor, action="revision.created", outcome="success", target_kind=kind,
            target_key=str(state.pk), base_revision=state.version, new_revision=revision.sequence, reason=reason,
            diff=changed_fields(before, after), policy_version=policy.version, request_id=request_id)
        state.refresh_from_db()
        return state


def inspect_proposal(actor_id, session_id, kind, target_id, expected, action):
    with policy_lock():
        kind_entry(kind)
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, capability(kind, action))
        state, obj = resolve(actor, kind, target_id, lock=True)
        check_current(state, obj, expected)
        candidate = validate_snapshot(kind, state.current_revision.payload, obj)
        require_references(actor, kind, candidate)
        result = {"record": revision_data(state, obj), "valid": True, "publication_available": False,
            "blockers": ["CANONICAL_PUBLICATION_UNAVAILABLE"]}
        if action == "preview":
            result["preview"] = preview_snapshot(kind, candidate, obj)
        return state, result


def archive_proposal(actor_id, session_id, kind, target_id, expected, request_id):
    with policy_lock() as policy:
        kind_entry(kind)
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, capability(kind, "archive"))
        state, obj = resolve(actor, kind, target_id, lock=True)
        check_current(state, obj, expected)
        if obj is None or state.current_revision.status not in {"legacy", "draft", "changes_requested", "approved"}:
            raise CMSFailure("INVALID_TRANSITION", 409)
        old = state.current_revision
        candidate = validate_snapshot(kind, old.payload, obj)
        require_references(actor, kind, candidate)
        revision = ContentRevision.objects.create(state=state, sequence=state.version + 1, base_version=state.version,
            base_digest=state.canonical_digest, payload=candidate, payload_digest=digest(candidate),
            dependency_digest=dependencies(kind, obj, candidate, True), schema_version=2, intent="archive", actor=actor)
        if ContentState.objects.filter(pk=state.pk, version=state.version).update(version=F("version") + 1, current_revision=revision) != 1:
            raise CMSFailure("STALE_REVISION", 412)
        AdminAuditEvent.objects.create(actor=actor, action="revision.created", outcome="success", target_kind=kind,
            target_key=str(state.pk), base_revision=state.version, new_revision=revision.sequence, reason="CONTENT_UPDATE",
            diff=["intent"], policy_version=policy.version, request_id=request_id)
        state.refresh_from_db()
        return state


def discard(actor_id, session_id, kind, target_id, expected, base_digest, request_id):
    with policy_lock() as policy:
        kind_entry(kind)
        actor = User.objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, capability(kind, "edit"))
        state, obj = resolve(actor, kind, target_id, lock=True)
        check_current(state, obj, expected, base_digest)
        if base_digest is None:
            raise stale(state, expected, {}, state.current_revision.payload)
        if state.canonical_pk is not None or state.current_revision.status != "draft":
            raise CMSFailure("INVALID_TRANSITION", 409)
        revision = ContentRevision.objects.create(state=state, sequence=state.version + 1, base_version=state.version,
            base_digest=state.canonical_digest, payload={}, payload_digest=digest({}), dependency_digest=digest({}),
            status="discarded", schema_version=2, intent=state.current_revision.intent, actor=actor)
        if ContentState.objects.filter(pk=state.pk, version=state.version).update(version=F("version") + 1, current_revision=revision) != 1:
            raise CMSFailure("STALE_REVISION", 412)
        AdminAuditEvent.objects.create(actor=actor, action="revision.discarded", outcome="success", target_kind=kind,
            target_key=str(state.pk), base_revision=state.version, new_revision=revision.sequence, reason="DRAFT_DISCARD",
            policy_version=policy.version, request_id=request_id)
        state.refresh_from_db()
        return state
