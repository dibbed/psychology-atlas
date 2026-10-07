"""Lossless safe staging and one hash-pinned, atomic Assessment metadata publication."""
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import transaction

from . import models as m
from .brain_publication import source_is_resolved
from .brain_source_resolution import classify_source

SCHEMA = "psychology-atlas-assessments-v1"
ROOT = Path(__file__).resolve().parents[2]
DOSSIER = ROOT / "docs/research/assessments/v0.9.4/curated_dossier.json"
MANIFEST = DOSSIER.with_name("publication_manifest.json")
DOSSIER_SHA = "6f42ca1c251ce45ab06a8bc3ffe81ec853bbb09c39c3acfe9d57d05956e5f9cf"
MANIFEST_SHA = "fc7afe5047618ca568ed9f5981e1057d7687b9d143e7dc92b0cbcc49736c1ade"
SOURCE_FIELDS = ("title", "organization", "citation", "url", "publication_year", "source_type", "authors", "doi", "pmid")
MODELS = {"source": m.SourceReference, "instrument": m.AssessmentInstrument, "version": m.AssessmentVersion,
          "language_form": m.AssessmentLanguageForm, "study": m.AssessmentValidationStudy,
          "finding": m.AssessmentPsychometricEvidence, "alias": m.AssessmentAlias,
          "access": m.AssessmentAccess, "relation": m.AssessmentRelation}
ORDER = tuple(MODELS)
REFERENCES = {"version": {"instrument": "instrument", "derived_from": "version"},
              "language_form": {"version": "version", "authorization_source": "source"},
              "study": {"version": "version", "language_form": "language_form", "source": "source"},
              "finding": {"study": "study"},
              "alias": {"instrument": "instrument", "version": "version", "source": "source"},
              "access": {"version": "version", "language_form": "language_form", "source": "source"},
              "relation": {"version": "version", "language_form": "language_form"}}
PROTECTED_KEYS = {"items", "test_items", "item_bank", "item_banks", "questions", "questionnaire_text",
                  "scoring_key", "scoring_keys", "scoring_rules", "manual_text", "translation_text", "official_translation_text"}


def protected_paths(value, path="$"):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_").replace(" ", "_")
            if normalized in PROTECTED_KEYS:
                found.append(path + "." + str(key))
            found.extend(protected_paths(child, path + "." + str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(protected_paths(child, f"{path}[{index}]"))
    return sorted(found)


def parse_document(raw_text):
    try:
        document = json.loads(raw_text)
    except (ValueError, TypeError) as error:
        raise CommandError("Invalid Assessment JSON.") from error
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA:
        raise CommandError("An explicit Assessment dossier is required; generic research strings are not instruments.")
    if protected_paths(document):
        raise CommandError("Protected content is prohibited, including in staging: " + ", ".join(protected_paths(document)))
    metadata, rows = document.get("dataset_metadata"), document.get("records")
    if (not isinstance(metadata, dict) or not isinstance(rows, list)
            or any(not isinstance(metadata.get(key), str) or not metadata[key].strip() for key in ("key", "version"))):
        raise CommandError("Assessment dataset identity and records are required.")
    if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in rows):
        raise CommandError("Every staging record requires a stable explicit ID.")
    if len({row["id"] for row in rows}) != len(rows):
        raise CommandError("Duplicate staging IDs cannot be collapsed.")
    for row in rows:
        links = row.get("sources", [])
        if (not isinstance(row.get("data", {}), dict) or not isinstance(links, list)
                or any(not isinstance(link, dict) or not isinstance(link.get("source"), str)
                       or not isinstance(link.get("note"), str) for link in links)):
            raise CommandError("Assessment rows require metadata objects and explicit source/note links.")
    return document


def archive_fields(row):
    data = row.get("data", {})
    return dict(section="assessment_" + str(row.get("category", "unsupported"))[:48], external_id=row["id"],
                canonical_key="assessment:" + row["id"], slug=data.get("slug", ""),
                name_en=data.get("name_en", data.get("label", "")), name_fa=data.get("name_fa", ""),
                source_ids=[link["source"] for link in row.get("sources", [])], review_status="unreviewed",
                verification_status="staging_only", payload=row)


def ingest_document(raw_text, filename):
    document = parse_document(raw_text)
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    with transaction.atomic():
        m.lock_brain_curation("default")
        dataset, created = m.ResearchDataset.objects.get_or_create(source_sha256=digest, defaults={
            "key": document["dataset_metadata"]["key"] + "-" + digest[:12],
            "source_filename": Path(filename).name, "dataset_name": document["dataset_metadata"]["key"],
            "dataset_version": document["dataset_metadata"]["version"], "metadata": document["dataset_metadata"],
            "raw_text": raw_text, "raw_document": document,
            "ingestion_audit": {"list_record_total": len(document["records"]), "assessment_staging_schema": SCHEMA}})
        if not created:
            verify_archive(dataset, document, raw_text)
            return dataset, False
        dataset.full_clean()
        for row in document["records"]:
            record = m.ResearchRecord(dataset=dataset, **archive_fields(row))
            record.full_clean()
            record.save()
        return dataset, True


def verify_archive(dataset, document, raw_text):
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    if (not dataset.is_active or dataset.raw_text != raw_text or dataset.raw_document != document
            or dataset.metadata != document["dataset_metadata"] or dataset.dataset_version != document["dataset_metadata"]["version"]
            or dataset.source_sha256 != digest or dataset.key != document["dataset_metadata"]["key"] + "-" + digest[:12]
            or dataset.dataset_name != document["dataset_metadata"]["key"]
            or dataset.ingestion_audit.get("list_record_total") != len(document["records"])):
        raise CommandError("Assessment archive changed or was deactivated; no canonical overwrite is permitted.")
    records = list(dataset.records.order_by("external_id"))
    if len(records) != len(document["records"]):
        raise CommandError("Assessment archive record count mismatch.")
    expected = {row["id"]: archive_fields(row) for row in document["records"]}
    for record in records:
        if record.external_id not in expected or any(getattr(record, key) != value for key,value in expected[record.external_id].items()):
            raise CommandError("Assessment archive index/payload mismatch: " + record.external_id)


def projection(row, resolved):
    category = row.get("category")
    if category not in MODELS or not isinstance(row.get("data"), dict):
        raise CommandError("Unsupported Assessment category: " + str(category))
    model, data = MODELS[category], dict(row["data"])
    allowed = {field.name for field in model._meta.concrete_fields if field.editable
               and field.name not in {"id", "created_at", "updated_at", "seed_managed", "review_status", "is_active", "metadata", "verification_status"}}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise CommandError("Unsupported fields on " + row["id"] + ": " + ", ".join(unknown))
    for field, target_category in REFERENCES.get(category, {}).items():
        if field in data and data[field] is not None:
            key = data[field]
            target = resolved.get(key)
            if target is None or not isinstance(target, MODELS[target_category]):
                raise CommandError("Unresolved exact endpoint: " + row["id"] + "." + field)
            data[field] = target
    if category == "relation":
        for field in ("concept", "symptom", "disorder"):
            if data.get(field):
                model = getattr(m, field.capitalize())
                target = model.objects.filter(slug=data[field], **({} if field == "symptom" else {"is_active": True})).first()
                if target is None:
                    raise CommandError("Unknown relation endpoint: " + data[field])
                data[field] = target
    for field in ("verified_on", "expires_on"):
        if data.get(field):
            try:
                data[field] = date.fromisoformat(data[field])
            except (TypeError, ValueError) as error:
                raise CommandError("Invalid rights verification date.") from error
    return MODELS[category], data


def apply_rows(document, *, verify_only=False):
    """Natural keys, full projections, and provenance must all agree; no upserts."""
    resolved, writes = {}, 0
    registry = list(m.SourceReference.objects.values("id", *SOURCE_FIELDS))
    for category in ORDER:
        for row in (row for row in document["records"] if row.get("category") == category):
            model, fields = projection(row, resolved)
            if category == "source":
                status, pk = classify_source(fields, registry)
                if status in {"AMBIGUOUS", "CONFLICT"}:
                    raise CommandError("Source resolution " + status + ": " + row["id"])
                if pk is None:
                    if verify_only:
                        raise CommandError("Published source is missing: " + row["id"])
                    obj = model.objects.create(**fields, verification_status="source_checked")
                    registry.append(dict(id=obj.pk, **{f: getattr(obj, f) for f in SOURCE_FIELDS}))
                    writes += 1
                else:
                    obj = model.objects.get(pk=pk)
                if any(getattr(obj, key) != value for key,value in fields.items()) or not source_is_resolved(obj):
                    raise CommandError("Source metadata or verification conflict: " + row["id"])
            else:
                if category == "instrument":
                    identity = {"slug": fields["slug"]}
                elif category == "version":
                    identity = {key: fields[key] for key in ("instrument", "key")}
                elif category == "language_form":
                    identity = {key: fields[key] for key in ("version", "language", "key")}
                elif category == "alias":
                    identity = {key: fields.get(key) for key in ("instrument", "version", "text", "language")}
                else:
                    identity = {"key": fields["key"]}
                obj = model.objects.filter(**identity).first()
                if obj:
                    if (not obj.is_active or obj.review_status != "reviewed" or obj.seed_managed
                            or any(getattr(obj, key) != value for key,value in fields.items())):
                        raise CommandError("Canonical identity/content conflict: " + row["id"])
                else:
                    if verify_only:
                        raise CommandError("Published canonical record missing: " + row["id"])
                    obj = model.objects.create(**fields)
                    if category in {"instrument", "version", "language_form", "relation"}:
                        owner_field = "relation" if category == "relation" else category
                        for link in row.get("sources", []):
                            source = resolved.get(link["source"])
                            if not isinstance(source, m.SourceReference):
                                raise CommandError("Unresolved claim source: " + row["id"])
                            m.AssessmentSource.objects.create(**{owner_field: obj}, source=source, note=link["note"])
                            writes += 1
                    obj.review_status = "reviewed"
                    obj.save()
                    writes += 1
                obj.full_clean()
                if category in {"instrument", "version", "language_form", "relation"}:
                    actual = sorted((link.source_id, link.note) for link in obj.source_links.all())
                    expected = sorted((resolved[link["source"]].pk, link["note"]) for link in row.get("sources", []))
                    if actual != expected:
                        raise CommandError("Claim provenance conflict: " + row["id"])
            resolved[row["id"]] = obj
    if len(resolved) != len(document["records"]):
        raise CommandError("Unsupported rows must remain staging-only.")
    return resolved, writes


def validate_staging(dataset):
    before = canonical_counts()
    try:
        with transaction.atomic():
            m.lock_brain_curation("default")
            verify_archive(dataset, dataset.raw_document, dataset.raw_text)
            apply_rows(dataset.raw_document)
            transaction.set_rollback(True)
        issues = []
    except (ValidationError, CommandError, KeyError, TypeError, ValueError) as error:
        issues = [str(error)]
    return dict(dataset=dataset.key, status="VALID" if not issues else "BLOCKED", issues=issues,
                canonical_writes=0, canonical_counts_unchanged=before == canonical_counts())


def canonical_counts():
    return {key: model.objects.count() for key,model in MODELS.items() if key != "source"}


def approved_artifacts(dossier=DOSSIER, manifest=MANIFEST):
    documents = []
    for path, digest in ((dossier, DOSSIER_SHA), (manifest, MANIFEST_SHA)):
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise CommandError("Assessment publication artifact differs from its reviewed hash: " + Path(path).name)
        documents.append(json.loads(raw))
    document, decisions = documents
    parse_document(Path(dossier).read_text(encoding="utf-8"))
    rows = document["records"]
    expected = {row["id"] for row in rows}
    approved = decisions.get("records", [])
    if (decisions.get("dossier_sha256") != DOSSIER_SHA or len(approved) != len(expected)
            or {row.get("id") for row in approved} != expected
            or Counter(row["category"] for row in rows) != Counter(decisions.get("counts", {}))
            or any(row.get("identity") != "verified" or row.get("sources") != "verified"
                   or row.get("scientific_review") != "passed" or row.get("rights_review") != "metadata_only"
                   or row.get("version_resolution") != "passed" for row in approved)):
        raise CommandError("Assessment manifest must exactly cover every scientific/rights-reviewed metadata record.")
    return document, decisions


def verify_publication(dataset):
    document, _ = approved_artifacts()
    verify_archive(dataset, document, DOSSIER.read_text(encoding="utf-8"))
    if dataset.ingestion_audit.get("assessment_publication") != {"dossier_sha256": DOSSIER_SHA, "manifest_sha256": MANIFEST_SHA}:
        raise CommandError("Assessment publication manifest receipt mismatch.")
    resolved, writes = apply_rows(document, verify_only=True)
    for record in dataset.records.all():
        obj = resolved[record.external_id]
        if (record.promoted_model, record.promoted_pk) != (obj._meta.label, obj.pk):
            raise CommandError("Assessment publication pointer mismatch: " + record.external_id)
    return dict(status="VERIFIED", canonical_writes=writes, records=len(resolved))


def publish(*, apply=False, dossier=DOSSIER, manifest=MANIFEST):
    document, decisions = approved_artifacts(dossier, manifest)
    with transaction.atomic():
        m.lock_brain_curation("default")
        raw_text = Path(dossier).read_text(encoding="utf-8")
        dataset, created = ingest_document(raw_text, Path(dossier).name)
        receipt = dataset.ingestion_audit.get("assessment_publication")
        if receipt and receipt != {"dossier_sha256": DOSSIER_SHA, "manifest_sha256": MANIFEST_SHA}:
            raise CommandError("Assessment publication receipt was changed.")
        resolved, writes = apply_rows(document, verify_only=bool(receipt))
        for record in dataset.records.all():
            obj = resolved[record.external_id]
            expected = (obj._meta.label, obj.pk)
            actual = (record.promoted_model, record.promoted_pk)
            if receipt and actual != expected:
                raise CommandError("Assessment publication staging pointer mismatch: " + record.external_id)
            if not receipt and any(actual):
                raise CommandError("Unexpected pre-publication staging pointer: " + record.external_id)
            if not receipt:
                record.promoted_model, record.promoted_pk = expected
                record.save(update_fields=("promoted_model", "promoted_pk", "updated_at"))
        if not receipt:
            dataset.ingestion_audit["assessment_publication"] = {"dossier_sha256": DOSSIER_SHA, "manifest_sha256": MANIFEST_SHA}
            dataset.save(update_fields=("ingestion_audit", "updated_at"))
        result = dict(status="ALREADY_PUBLISHED" if receipt else ("PUBLISHED" if apply else "DRY_RUN"),
                      canonical_writes=writes if apply else 0, counts=decisions["counts"], dataset=dataset.key)
        if not apply:
            transaction.set_rollback(True)
        return result
