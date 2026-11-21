"""Authorized History lineage from the persisted ResearchRecord promotion locator.

Only `promoted_model`/`promoted_pk` is evidence. Names, slugs, payloads and
source ids are never used to infer a link, and this module never writes.
"""
from django.db.models import Prefetch

from .cms_artifacts import scoped_datasets
from .cms_domains import domain_for, entry_tuple
from .cms_policy import CMSFailure, effective_permissions
from .models import ResearchRecord, ResearchRecordDecision

MAX_LINEAGE_RECORDS = 10


def _normalized_label(value):
    if not isinstance(value, str):
        return ""
    value = value.strip().casefold()
    return value if "." in value else "atlas." + value


def _model_labels(model):
    return {_normalized_label(value) for value in
        (model._meta.label_lower, model.__name__, model._meta.model_name) if value}


def _origin(status, reason=None, records=(), count=0, restricted=0, truncated=False):
    result = {"status": status, "records": list(records), "count": count, "restricted_count": restricted,
        "truncated": truncated, "canonical_write": 0, "auto_review": False}
    if reason:
        result["reason"] = reason
    return result


def _lineage_record(record, include_names):
    latest = record.lineage_decisions[0] if record.lineage_decisions else None
    data = {"record_id": record.pk, "dataset_id": record.dataset_id,
        "dataset_name": record.dataset.dataset_name, "dataset_version": record.dataset.dataset_version,
        "section": record.section, "external_id": record.external_id,
        "promoted_model": record.promoted_model, "staging_state": latest.action if latest else "unmapped",
        "version": latest.sequence if latest else 0}
    if include_names:
        data["name_en"] = record.name_en
        data["name_fa"] = record.name_fa
    return data


def lineage_for_many(actor, kind, pks):
    """Return one explicit origin per canonical id; never raises for missing lineage."""
    model = entry_tuple(kind)[0]
    ids = sorted({int(pk) for pk in pks})
    if not ids:
        return {}
    held = effective_permissions(actor)
    if "cms_research_view" not in held:
        return {pk: _origin("unavailable", "RESEARCH_VIEW_REQUIRED") for pk in ids}
    rows = list(ResearchRecord.objects.filter(promoted_pk__in=ids).select_related("dataset")
        .prefetch_related(Prefetch("cms_decisions", queryset=ResearchRecordDecision.objects.order_by("-sequence"),
            to_attr="lineage_decisions")).order_by("dataset_id", "section", "pk"))
    labels = _model_labels(model)
    matching, mismatching = {}, set()
    for row in rows:
        if _normalized_label(row.promoted_model) in labels:
            matching.setdefault(row.promoted_pk, []).append(row)
        else:
            mismatching.add(row.promoted_pk)
    dataset_ids = set(scoped_datasets(actor).values_list("pk", flat=True))
    include_names = "cms_research_raw_read" in held
    result = {}
    for pk in ids:
        linked = matching.get(pk, [])
        if linked:
            visible = [row for row in linked if row.dataset_id in dataset_ids]
            if visible:
                result[pk] = _origin("linked", count=len(visible),
                    restricted=len(linked) - len(visible), truncated=len(visible) > MAX_LINEAGE_RECORDS,
                    records=[_lineage_record(row, include_names) for row in visible[:MAX_LINEAGE_RECORDS]])
            else:
                result[pk] = _origin("restricted", "RESEARCH_SCOPE_DENIED", count=len(linked))
        elif pk in mismatching:
            result[pk] = _origin("unknown", "PROMOTED_MODEL_MISMATCH")
        else:
            result[pk] = _origin("unlinked", "NO_PROMOTED_RESEARCH_RECORD")
    return result


def lineage_for(actor, kind, pk):
    return lineage_for_many(actor, kind, [pk])[pk]


def provenance_data(actor, kind, state, obj):
    if domain_for(kind) != "history":
        raise CMSFailure("NOT_FOUND", 404)
    origin = (_origin("unlinked", "NO_CANONICAL_RECORD") if obj is None
        else lineage_for(actor, kind, obj.pk))
    return {"kind": kind, "state_id": str(state.pk), "canonical_pk": obj.pk if obj else None,
        "origin": origin, "canonical_write": 0, "auto_review": False,
        "notice": "این نمایش فقط locator ثبت‌شدهٔ ResearchRecord است؛ دادهٔ خام، نام جایگزین یا تأیید علمی نیست."}
