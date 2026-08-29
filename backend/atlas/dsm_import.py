from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from django.db import transaction
from django.db.models import Count
from django.utils.text import slugify

from .models import (
    Category,
    DSMCorpus,
    DSMRecord,
    DSMRecordRelation,
    Disorder,
    DisorderSource,
    SourceReference,
)

PROFILE_KEY = "پروفایل_آموزشی_پیشرفته_MASTER"
MASTER_ID_KEY = "شناسه_MASTER"
NODE_ROOT_KEYS = {
    "فصل‌های_اختلال",
    "بخش_تکمیلی_عوارض_دارویی",
    "سایر_شرایط_کانون_توجه_بالینی",
    "بخش_سه",
}

# Existing Atlas titles that are intentionally shorter than the MASTER title.
DISORDER_TITLE_ALIASES = {
    "adjustmentdisorder": "adjustmentdisorders",
    "excoriationdisorder": "excoriationskinpickingdisorder",
    "persistentdepressivedisorder": "persistentdepressivedisorderdysthymia",
    "socialanxietydisorder": "socialanxietydisordersocialphobia",
    "trichotillomania": "trichotillomaniahairpullingdisorder",
}


@dataclass(frozen=True)
class CollectedNode:
    master_id: str
    profile: dict[str, Any]
    source: dict[str, Any]
    path: tuple[str, ...]
    parent_master_id: str | None


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def _normalize_record_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    return re.sub(r"[^0-9a-z\u0600-\u06ff]+", " ", value).strip()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _flatten_strings(value: Any) -> list[str]:
    rows: list[str] = []
    if isinstance(value, str):
        rows.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                rows.append(key)
            rows.extend(_flatten_strings(item))
    elif isinstance(value, list):
        for item in value:
            rows.extend(_flatten_strings(item))
    return rows


def _prune_nested_nodes(value: Any, *, root: bool = True) -> Any:
    """Keep the current record intact while replacing nested MASTER records with refs.

    The complete unmodified JSON still lives in DSMCorpus.raw_document. This avoids
    multiplying chapter/group payloads many times in the normalized record table.
    """
    if isinstance(value, dict):
        if not root and value.get(MASTER_ID_KEY):
            profile = value.get(PROFILE_KEY) or {}
            return {
                MASTER_ID_KEY: value.get(MASTER_ID_KEY),
                "نام_فارسی": profile.get("نام_فارسی") or value.get("نام_فارسی") or value.get("نام"),
                "نام_انگلیسی": profile.get("نام_انگلیسی") or value.get("نام_انگلیسی"),
            }
        return {key: _prune_nested_nodes(item, root=False) for key, item in value.items()}
    if isinstance(value, list):
        return [_prune_nested_nodes(item, root=False) for item in value]
    return value


def _collect_nodes(document: dict[str, Any]) -> list[CollectedNode]:
    rows: list[CollectedNode] = []

    def walk(value: Any, path: tuple[str, ...] = (), parent_master_id: str | None = None) -> None:
        if isinstance(value, dict):
            master_id = value.get(MASTER_ID_KEY)
            profile = value.get(PROFILE_KEY)
            next_parent = parent_master_id
            if master_id and isinstance(profile, dict):
                rows.append(
                    CollectedNode(
                        master_id=str(master_id),
                        profile=profile,
                        source=value,
                        path=path,
                        parent_master_id=parent_master_id,
                    )
                )
                next_parent = str(master_id)
            for key, item in value.items():
                if key == PROFILE_KEY:
                    continue
                walk(item, path + (str(key),), next_parent)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path + (str(index),), parent_master_id)

    walk(document)
    return rows


def _display_type(status: str) -> str:
    if status.startswith("تشخیص رسمی"):
        return DSMRecord.DisplayType.DIAGNOSIS
    if status.startswith("شرط/کد کانون توجه بالینی"):
        return DSMRecord.DisplayType.CLINICAL_ATTENTION
    if status.startswith("شرط پژوهشی"):
        return DSMRecord.DisplayType.RESEARCH
    if status.startswith("مدل جایگزین"):
        return DSMRecord.DisplayType.ALTERNATIVE_MODEL
    if status.startswith("مشخص‌کننده"):
        return DSMRecord.DisplayType.SPECIFIER
    if status.startswith("ارجاع ساختاری"):
        return DSMRecord.DisplayType.REFERENCE
    if status.startswith("کد اضافی"):
        return DSMRecord.DisplayType.CODE
    if "ساختار" in status or "چارچوب" in status or status.startswith("گروه/عنوان"):
        return DSMRecord.DisplayType.STRUCTURAL
    return DSMRecord.DisplayType.OTHER


def _sort_index(master_id: str) -> int:
    match = re.search(r"M(\d+)$", master_id)
    return int(match.group(1)) if match else 0


def _source_organization(key: str) -> str:
    if key.startswith("APA_"):
        return "American Psychiatric Association"
    if key.startswith("PO_"):
        return "Psychiatry Online"
    return ""


def _upsert_source_registry(registry: dict[str, Any]) -> dict[str, SourceReference]:
    result: dict[str, SourceReference] = {}
    for key, value in registry.items():
        if not isinstance(value, dict):
            continue
        title = _as_text(value.get("عنوان"))[:500]
        url = _as_text(value.get("نشانی"))
        source = SourceReference.objects.filter(title=title, url=url).first()
        defaults = {
            "organization": _source_organization(key),
            "citation": _as_text(value.get("کاربرد")),
            "source_type": "dsm_master",
        }
        if source:
            for field, field_value in defaults.items():
                setattr(source, field, field_value)
            source.save(update_fields=[*defaults.keys(), "updated_at"])
        else:
            source = SourceReference.objects.create(title=title, url=url, **defaults)
        result[key] = source
    return result


def _validate_document(document: dict[str, Any], nodes: list[CollectedNode]) -> None:
    expected = document.get("آمار_MASTER", {}).get("تعداد_گره‌های_آدرس‌پذیر_دارای_پروفایل_MASTER")
    health = document.get("تست_سلامت_MASTER", {})
    health_expected = health.get("تعداد_پروفایل")
    unique_ids = {node.master_id for node in nodes}

    if expected is not None and len(nodes) != int(expected):
        raise ValueError(f"MASTER profile count mismatch: expected {expected}, got {len(nodes)}")
    if health_expected is not None and len(nodes) != int(health_expected):
        raise ValueError(f"MASTER health profile count mismatch: expected {health_expected}, got {len(nodes)}")
    if len(unique_ids) != len(nodes):
        raise ValueError("MASTER contains duplicate master IDs")
    if health.get("JSON_قابل_بارگذاری") is False or health.get("نتیجه") not in (None, "PASS"):
        raise ValueError("MASTER health check is not PASS")


def _chapter_maps(document: dict[str, Any]) -> tuple[dict[str, int], dict[str, str]]:
    numbers: dict[str, int] = {}
    english: dict[str, str] = {}
    for chapter in document.get("فصل‌های_اختلال", []):
        if not isinstance(chapter, dict):
            continue
        number = chapter.get("شماره")
        fa = _as_text(chapter.get("نام_فارسی"))
        en = _as_text(chapter.get("نام_انگلیسی"))
        try:
            numeric = int(number)
        except (TypeError, ValueError):
            continue
        if fa:
            numbers[fa] = numeric
            english[fa] = en
        if en:
            numbers[en] = numeric
    return numbers, english


def _record_defaults(
    node: CollectedNode,
    *,
    corpus: DSMCorpus,
    chapter_numbers: dict[str, int],
    chapter_english: dict[str, str],
) -> dict[str, Any]:
    profile = node.profile
    path = profile.get("مسیر_ساختاری") or {}
    chapter_fa = _as_text(path.get("فصل"))
    chapter_en = _as_text(path.get("فصل_انگلیسی")) or chapter_english.get(chapter_fa, "")
    chapter_number = chapter_numbers.get(chapter_fa) or chapter_numbers.get(chapter_en)
    status = _as_text(profile.get("وضعیت_طبقه‌بندی"))
    source_payload = _prune_nested_nodes(node.source)
    old_education = node.source.get("اطلاعات_آموزشی")
    old_keywords = (
        _flatten_strings(old_education.get("کلیدواژه‌های_جست‌وجو", []))
        if isinstance(old_education, dict)
        else []
    )
    search_parts = [
        _as_text(profile.get("نام_فارسی")),
        _as_text(profile.get("نام_انگلیسی")),
        status,
        chapter_fa,
        chapter_en,
        _as_text(path.get("گروه")),
        _as_text(profile.get("خلاصه_مفهومی_بازبینی‌شده")),
        *_flatten_strings(profile.get("ویژگی‌های_کلیدی_آموزشی", [])),
        *_flatten_strings(profile.get("ارزیابی_هدفمند", [])),
        *_flatten_strings(profile.get("افتراق_تشخیصی_هدفمند", [])),
        *_flatten_strings(profile.get("عناوین_نزدیک_یا_ارجاعات", [])),
        *old_keywords,
    ]
    return {
        "corpus": corpus,
        "sort_index": _sort_index(node.master_id),
        "root_section": _as_text(path.get("ریشه")) or (node.path[0] if node.path else ""),
        "chapter_number": chapter_number,
        "chapter_name_fa": chapter_fa,
        "chapter_name_en": chapter_en,
        "group_name": _as_text(path.get("گروه")),
        "name_fa": _as_text(profile.get("نام_فارسی")),
        "name_en": _as_text(profile.get("نام_انگلیسی")),
        "source_type": _as_text(node.source.get("نوع")),
        "classification_status": status,
        "display_type": _display_type(status),
        "specialization_level": _as_text(profile.get("سطح_اختصاصی‌سازی")),
        "summary": _as_text(profile.get("خلاصه_مفهومی_بازبینی‌شده")),
        "key_features": profile.get("ویژگی‌های_کلیدی_آموزشی") or [],
        "assessment": profile.get("ارزیابی_هدفمند") or [],
        "differential": profile.get("افتراق_تشخیصی_هدفمند") or [],
        "comorbidity": _as_text(profile.get("همبودی_و_همپوشانی")),
        "course": _as_text(profile.get("سیر_و_پیش‌آگهی_آموزشی")),
        "management": profile.get("مدیریت_و_درمان_کلی_آموزشی") or [],
        "assessment_tools": profile.get("ابزارهای_سنجش_نمونه") or [],
        "context_considerations": _as_text(profile.get("ملاحظات_فرهنگی_رشدی_و_زمینه‌ای")),
        "red_flags": _as_text(profile.get("پرچم‌های_قرمز_و_ایمنی")),
        "pitfalls": profile.get("دام‌های_رایج_در_مطالعه_یا_تشخیص") or [],
        "nearby_titles": profile.get("عناوین_نزدیک_یا_ارجاعات") or [],
        "official_updates": profile.get("به‌روزرسانی‌های_رسمی_مرتبط") or [],
        "homonym_info": profile.get("هم‌نامی_یا_تکرار_ساختاری") or {},
        "prevalence_numeric": profile.get("شیوع_عددی"),
        "prevalence_policy": _as_text(profile.get("سیاست_شیوع")),
        "coding": _as_text(profile.get("کدگذاری")),
        "source_keys": profile.get("منابع_پایه") or [],
        "quality": profile.get("کیفیت_و_محدودیت") or {},
        "exam_tip": _as_text(profile.get("نکته_امتحانی_کلیدی")),
        "self_test": profile.get("سؤال‌های_خودآزمایی_پیشرفته") or [],
        "structural_path": path,
        "search_text": "\n".join(str(part) for part in search_parts if part),
        "source_payload": source_payload,
        "is_active": True,
    }


def _resolve_record_title(
    source: DSMRecord,
    title: str,
    index: dict[str, list[DSMRecord]],
) -> DSMRecord | None:
    candidates = [
        candidate for candidate in index.get(_normalize_record_name(title), [])
        if candidate.pk != source.pk
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def score(candidate: DSMRecord) -> tuple[int, int]:
        value = 0
        if source.group_name and candidate.group_name == source.group_name:
            value += 16
        if source.chapter_number is not None and candidate.chapter_number == source.chapter_number:
            value += 8
        if source.root_section and candidate.root_section == source.root_section:
            value += 4
        if candidate.display_type == source.display_type:
            value += 2
        return value, -candidate.sort_index

    ranked = sorted(candidates, key=score, reverse=True)
    if len(ranked) > 1 and score(ranked[0]) == score(ranked[1]):
        return None
    return ranked[0]


def _rebuild_record_relations(corpus: DSMCorpus) -> dict[str, int]:
    records = list(corpus.records.filter(is_active=True).order_by("sort_index"))
    index: dict[str, list[DSMRecord]] = defaultdict(list)
    for record in records:
        for name in {record.name_fa, record.name_en}:
            normalized = _normalize_record_name(name)
            if normalized:
                index[normalized].append(record)

    rows: list[DSMRecordRelation] = []
    seen: set[tuple[int, int, str]] = set()
    for source in records:
        for raw_title in source.nearby_titles:
            title = raw_title if isinstance(raw_title, str) else _as_text(raw_title.get("عنوان")) if isinstance(raw_title, dict) else ""
            target = _resolve_record_title(source, title, index) if title else None
            if not target:
                continue
            key = (source.pk, target.pk, DSMRecordRelation.Kind.NEARBY)
            if key in seen:
                continue
            seen.add(key)
            rows.append(DSMRecordRelation(
                source=source,
                target=target,
                relationship_type=DSMRecordRelation.Kind.NEARBY,
                explanation="عنوان نزدیک یا ارجاع ثبت‌شده در پروفایل آموزشی MASTER.",
            ))

        for item in source.differential:
            if isinstance(item, dict):
                title = _as_text(item.get("عنوان"))
                explanation = _as_text(item.get("نقطه_افتراق"))
            elif isinstance(item, str):
                title = item
                explanation = ""
            else:
                continue
            target = _resolve_record_title(source, title, index) if title else None
            if not target:
                continue
            key = (source.pk, target.pk, DSMRecordRelation.Kind.DIFFERENTIAL)
            if key in seen:
                continue
            seen.add(key)
            rows.append(DSMRecordRelation(
                source=source,
                target=target,
                relationship_type=DSMRecordRelation.Kind.DIFFERENTIAL,
                explanation=explanation,
            ))

    DSMRecordRelation.objects.filter(source__corpus=corpus).delete()
    DSMRecordRelation.objects.bulk_create(rows, batch_size=500)
    return {
        "nearby": sum(1 for row in rows if row.relationship_type == DSMRecordRelation.Kind.NEARBY),
        "differential": sum(1 for row in rows if row.relationship_type == DSMRecordRelation.Kind.DIFFERENTIAL),
    }


def _link_existing_disorders(
    corpus: DSMCorpus,
    source_registry: dict[str, SourceReference],
) -> int:
    records = list(
        corpus.records.filter(display_type=DSMRecord.DisplayType.DIAGNOSIS, is_active=True)
        .order_by("sort_index")
    )
    by_name: dict[str, list[DSMRecord]] = defaultdict(list)
    for record in records:
        if record.name_en:
            by_name[_normalize_name(record.name_en)].append(record)

    corpus.records.update(linked_disorder=None)
    linked = 0
    for disorder in Disorder.objects.filter(is_active=True).select_related("category"):
        normalized = _normalize_name(disorder.name_en)
        target = DISORDER_TITLE_ALIASES.get(normalized, normalized)
        candidates = by_name.get(target, [])
        if not candidates:
            continue

        category_name = _normalize_name(disorder.category.name_en)
        record = next(
            (
                candidate
                for candidate in candidates
                if category_name
                and _normalize_name(candidate.chapter_name_en)
                and (
                    category_name in _normalize_name(candidate.chapter_name_en)
                    or _normalize_name(candidate.chapter_name_en) in category_name
                )
            ),
            candidates[0],
        )
        record.linked_disorder = disorder
        record.save(update_fields=["linked_disorder", "updated_at"])
        linked += 1

        for source_key in record.source_keys:
            source = source_registry.get(source_key)
            if not source:
                continue
            DisorderSource.objects.update_or_create(
                disorder=disorder,
                source=source,
                defaults={"note": f"DSM MASTER [{source_key}] · {record.master_id}"},
            )
    return linked


def _record_list_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return " • ".join(_as_text(item) for item in value if item not in (None, ""))
    return _as_text(value)


def _category_for_diagnosis(corpus: DSMCorpus, record: DSMRecord) -> Category:
    if record.chapter_number is not None:
        slug = f"dsm-chapter-{record.chapter_number:02d}"
        name_en = record.chapter_name_en or f"DSM Chapter {record.chapter_number}"
        name_fa = record.chapter_name_fa
        description = (
            f"فصل {record.chapter_number} در DSM MASTER آموزشی. "
            "این اطلس متن معیارهای رسمی DSM را بازتولید نمی‌کند."
        )
        sort_order = record.chapter_number
    else:
        section = corpus.raw_document.get(record.root_section, {})
        if not isinstance(section, dict):
            section = {}
        slug = "dsm-supplemental-medication-adverse-effects"
        name_en = _as_text(section.get("نام_انگلیسی")) or "Medication-Induced Disorders and Adverse Effects"
        name_fa = _as_text(section.get("نام_فارسی")) or "اختلالات و عوارض ناشی از دارو"
        description = _as_text(section.get("وضعیت")) or "بخش تکمیلی DSM MASTER آموزشی."
        sort_order = 21

    category, _ = Category.objects.update_or_create(
        slug=slug,
        defaults={
            "name_en": name_en[:200],
            "name_fa": name_fa[:200],
            "description": description,
            "sort_order": sort_order,
            "is_active": True,
        },
    )
    return category


def _preferred_diagnosis_record(candidates: list[DSMRecord]) -> DSMRecord:
    linked = [candidate for candidate in candidates if candidate.linked_disorder_id]
    if linked:
        return sorted(linked, key=lambda row: row.sort_index)[0]

    normalized_name = _normalize_name(candidates[0].name_en) if candidates else ""
    if "personalitydisorder" in normalized_name:
        personality = [candidate for candidate in candidates if candidate.chapter_number == 18]
        if personality:
            return sorted(personality, key=lambda row: row.sort_index)[0]
    return sorted(candidates, key=lambda row: row.sort_index)[0]


def _unique_disorder_slug(name_en: str, master_id: str) -> str:
    base = slugify(name_en)[:150] or f"dsm-{master_id.lower()}"
    candidate = base
    suffix = master_id.rsplit("-", 1)[-1].lower()
    counter = 0
    while Disorder.objects.filter(slug=candidate).exists():
        counter += 1
        extra = suffix if counter == 1 else f"{suffix}-{counter}"
        cutoff = max(1, 159 - len(extra))
        candidate = base[:cutoff] + "-" + extra
    return candidate


def _sync_diagnosis_catalog(
    corpus: DSMCorpus,
    source_registry: dict[str, SourceReference],
) -> dict[str, int]:
    """Create one canonical Atlas Disorder page for every unique formal diagnosis."""
    records = list(
        corpus.records.filter(display_type=DSMRecord.DisplayType.DIAGNOSIS, is_active=True)
        .select_related("linked_disorder", "linked_disorder__category")
        .order_by("sort_index")
    )
    groups: dict[str, list[DSMRecord]] = defaultdict(list)
    for record in records:
        key = _normalize_name(record.name_en) or _normalize_record_name(record.name_fa)
        groups[key].append(record)

    existing_by_name: dict[str, list[Disorder]] = defaultdict(list)
    for disorder in Disorder.objects.all().select_related("category"):
        normalized = _normalize_name(disorder.name_en)
        target = DISORDER_TITLE_ALIASES.get(normalized, normalized)
        existing_by_name[target].append(disorder)

    created = 0
    updated = 0
    seen_generated_ids: set[int] = set()
    category_ids: set[int] = set()

    for key, candidates in groups.items():
        canonical = _preferred_diagnosis_record(candidates)
        disorder = canonical.linked_disorder
        if disorder is None:
            matches = existing_by_name.get(key, [])
            if matches:
                disorder = sorted(
                    matches,
                    key=lambda row: (
                        row.data_origin != Disorder.Origin.CURATED,
                        not row.is_active,
                        row.id,
                    ),
                )[0]

        category = _category_for_diagnosis(corpus, canonical)
        category_ids.add(category.id)
        generated_defaults = {
            "category": category,
            "name_en": canonical.name_en[:220],
            "name_fa": canonical.name_fa[:220],
            "short_description": canonical.summary,
            "overview": canonical.summary,
            "clinical_features": _record_list_text(canonical.key_features),
            "risk_factors": canonical.context_considerations,
            "treatment_overview": _record_list_text(canonical.management),
            "assessment_overview": _record_list_text(canonical.assessment),
            "typical_onset": "",
            "course_note": canonical.course,
            "is_active": True,
        }

        if disorder is None:
            disorder = Disorder.objects.create(
                slug=_unique_disorder_slug(canonical.name_en, canonical.master_id),
                data_origin=Disorder.Origin.DSM_MASTER,
                **generated_defaults,
            )
            existing_by_name[key].append(disorder)
            created += 1
        else:
            disorder.category = category
            disorder.is_active = True
            update_fields = ["category", "is_active", "updated_at"]
            if disorder.data_origin == Disorder.Origin.DSM_MASTER:
                for field, value in generated_defaults.items():
                    setattr(disorder, field, value)
                update_fields = [*generated_defaults.keys(), "updated_at"]
            else:
                if not disorder.name_en:
                    disorder.name_en = canonical.name_en[:220]
                    update_fields.append("name_en")
                if not disorder.name_fa:
                    disorder.name_fa = canonical.name_fa[:220]
                    update_fields.append("name_fa")
            disorder.save(update_fields=list(dict.fromkeys(update_fields)))
            updated += 1

        if disorder.data_origin == Disorder.Origin.DSM_MASTER:
            seen_generated_ids.add(disorder.id)

        for candidate in candidates:
            target_id = disorder.id if candidate.pk == canonical.pk else None
            if candidate.linked_disorder_id != target_id:
                candidate.linked_disorder_id = target_id
                candidate.save(update_fields=["linked_disorder", "updated_at"])

        for source_key in canonical.source_keys:
            source = source_registry.get(source_key)
            if source:
                DisorderSource.objects.update_or_create(
                    disorder=disorder,
                    source=source,
                    defaults={"note": f"DSM MASTER [{source_key}] · {canonical.master_id}"},
                )

    generated_qs = Disorder.objects.filter(data_origin=Disorder.Origin.DSM_MASTER)
    if seen_generated_ids:
        generated_qs.exclude(id__in=seen_generated_ids).update(is_active=False)
    else:
        generated_qs.update(is_active=False)

    return {
        "diagnosis_records": len(records),
        "disorders": len(groups),
        "duplicate_records_collapsed": len(records) - len(groups),
        "created": created,
        "updated": updated,
        "categories": len(category_ids),
    }


@transaction.atomic
def import_master_json(json_path: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    path = Path(json_path)
    raw_bytes = path.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    document = json.loads(raw_bytes.decode("utf-8"))
    nodes = _collect_nodes(document)
    _validate_document(document, nodes)

    version = document.get("نسخه_MASTER", {})
    date_text = _as_text(version.get("تاریخ_ساخت")) or "2026-08-29"
    version_date = date.fromisoformat(date_text)
    corpus_key = f"dsm5tr-fa-master-{version_date.isoformat()}"
    metadata = {key: value for key, value in document.items() if key not in NODE_ROOT_KEYS}

    corpus, _ = DSMCorpus.objects.update_or_create(
        key=corpus_key,
        defaults={
            "title": _as_text(document.get("عنوان"))[:500],
            "version_name": _as_text(version.get("نام"))[:300],
            "version_date": version_date,
            "language": _as_text(document.get("زبان"))[:80],
            "purpose": _as_text(document.get("هدف")),
            "copyright_note": _as_text(document.get("محدودیت_حق_نشر")),
            "clinical_note": _as_text(document.get("نکته_بالینی")),
            "source_filename": path.name,
            "source_sha256": source_sha256,
            "official_status": document.get("وضعیت_رسمی_بررسی_شده_تا_2026_08_29", {}),
            "source_registry": document.get("ثبت_منابع_MASTER", {}),
            "quality_audit": document.get("ممیزی_کیفیت_MASTER", {}),
            "stats": document.get("آمار_MASTER", {}),
            "study_guide": document.get("راهنمای_مطالعه_مرحله‌ای", []),
            "urgent_warnings": document.get("راهنمای_هشدارهای_فوری", {}),
            "cultural_note": _as_text(document.get("یادداشت_فرهنگی_و_زمینه‌ای")),
            "periodic_review": document.get("موارد_نیازمند_بازبینی_دوره‌ای_MASTER", []),
            "release_updates": document.get("ثبت_به‌روزرسانی‌های_سپتامبر_2025_MASTER", {}),
            "health_check": document.get("تست_سلامت_MASTER", {}),
            "metadata": metadata,
            "raw_document": document,
            "is_active": True,
        },
    )
    DSMCorpus.objects.exclude(pk=corpus.pk).update(is_active=False)

    source_registry = _upsert_source_registry(corpus.source_registry)
    chapter_numbers, chapter_english = _chapter_maps(document)
    seen: set[str] = set()
    parent_map: dict[str, str | None] = {}

    for node in nodes:
        defaults = _record_defaults(
            node,
            corpus=corpus,
            chapter_numbers=chapter_numbers,
            chapter_english=chapter_english,
        )
        DSMRecord.objects.update_or_create(
            corpus=corpus,
            master_id=node.master_id,
            defaults=defaults,
        )
        seen.add(node.master_id)
        parent_map[node.master_id] = node.parent_master_id

    corpus.records.exclude(master_id__in=seen).delete()
    records_by_id = {
        record.master_id: record
        for record in corpus.records.filter(master_id__in=seen)
    }
    parent_updates: list[DSMRecord] = []
    for master_id, parent_master_id in parent_map.items():
        record = records_by_id[master_id]
        parent = records_by_id.get(parent_master_id) if parent_master_id else None
        if record.parent_id != (parent.id if parent else None):
            record.parent = parent
            parent_updates.append(record)
    if parent_updates:
        DSMRecord.objects.bulk_update(parent_updates, ["parent"])

    relation_counts = _rebuild_record_relations(corpus)
    matched_existing_disorders = _link_existing_disorders(corpus, source_registry)
    catalog_counts = _sync_diagnosis_catalog(corpus, source_registry)
    type_counts = {
        row["display_type"]: row["count"]
        for row in corpus.records.values("display_type").annotate(count=Count("id"))
    }

    result = {
        "corpus_id": corpus.id,
        "key": corpus.key,
        "sha256": source_sha256,
        "records": corpus.records.count(),
        "linked_disorders": catalog_counts["disorders"],
        "matched_existing_disorders": matched_existing_disorders,
        "diagnosis_catalog": catalog_counts,
        "sources": len(source_registry),
        "relations": relation_counts,
        "types": type_counts,
    }
    if dry_run:
        transaction.set_rollback(True)
    return result
