"""Typed immutable proposals; canonical publication/withdrawal belongs to P16."""
import hashlib
import json
import uuid

from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, Q

from .cms_audit import CONTENT_REASONS, changed_fields
from .cms_content_models import ContentRevision, ContentState
from .cms_domains import (DOMAIN_SPECS, dependency_snapshot, domain_for, entry_tuple,
    preview_snapshot, required_reference_capabilities, schema_data, validate_snapshot)
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_sessions import current_session

REGISTRY = {kind: entry_tuple(kind) for kind in DOMAIN_SPECS}
CategoryProposal = REGISTRY["category"][1]
DisorderProposal = REGISTRY["disorder"][1]


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
