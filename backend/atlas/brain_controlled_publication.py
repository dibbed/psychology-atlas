"""The single approved v0.9.2C publication pass, never a generic auto-promoter."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import CommandError
from django.db import transaction

from . import models as m
from .brain_publication import source_is_resolved
from .brain_source_resolution import classify_source

ROOT = Path(__file__).resolve().parents[2]
DOSSIER = ROOT / "docs/research/brain/v0.9.2c/psychology_atlas_brain_publication_dossier_v0.9.2c.json"
MANIFEST = DOSSIER.with_name("publication_manifest.json")
DOSSIER_SHA = "50b6e33e25b76a77b6ef735503487ac5fab7832d7474e45ad6beb7acdc25a557"
MANIFEST_SHA = "3f3538fd4f8195b0dbe1c8631d61674cd84c629e7bea1018ba29b91329a3920d"
VERSION = "0.9.2c-fma510-2026-10-01"
PREDECESSOR = DOSSIER.parent.parent / "v0.9.2b/psychology_atlas_brain_curated_dossier_v0.9.2b.json"
PREDECESSOR_SHA = "738b3ce478b0dd9f9213f5d8b8aba002701972fc2ab39eaa9263a81ca5893213"
ORDER = ("source", "anatomy", "network", "alias", "external_identifier", "hierarchy")
ENTITY_FIELDS = ("slug", "name_en", "name_fa", "kind", "description_en", "description_fa", "is_active")
SOURCE_FIELDS = ("title", "organization", "citation", "url", "publication_year", "source_type", "authors", "doi", "pmid")


def encoded(document):
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def approved_artifacts(dossier=DOSSIER, manifest=MANIFEST):
    documents = []
    for path, expected in ((dossier, DOSSIER_SHA), (manifest, MANIFEST_SHA)):
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise CommandError("Publication artifact hash differs from the explicitly reviewed pin: " + Path(path).name)
        documents.append(json.loads(raw.decode("utf-8")))
    document, manifest = documents
    rows = document["records"]
    decisions = manifest["candidates"]
    approved = {e["record_id"] for e in decisions if e["classification"] == "APPROVED_FOR_PUBLICATION"
                and e["scientific_status"] == "VERIFIED" and e["rights_status"] in
                {"RIGHTS_CLEARED", "RIGHTS_REPLACED_WITH_CLEAR_SOURCE", "RIGHTS_EXPLICIT_PERMISSION"}}
    if (manifest["dossier_sha256"] != DOSSIER_SHA or manifest["dossier_version"] != VERSION
            or document["dataset_metadata"]["version"] != VERSION
            or Counter(r["category"] for r in rows) != Counter(manifest["counts"])
            or len({r["id"] for r in rows}) != len(rows) or approved != {r["id"] for r in rows}
            or any(r["category"] not in ORDER or r["review_status"] != "reviewed" for r in rows)):
        raise CommandError("Scientific/rights approval manifest does not exactly cover the publication selection.")
    return document, manifest


def resolve_document(document, *, create):
    derived = copy.deepcopy(document)
    catalog = document["dataset_metadata"]["verified_source_catalog"]
    registry = list(m.SourceReference.objects.values("id", *SOURCE_FIELDS))
    sources, decisions = {}, []
    for row in derived["records"]:
        if row["category"] != "source":
            continue
        candidate = catalog[row["id"]]
        if candidate["bibliographic_verification"] != "independently_verified":
            raise CommandError("Unverified bibliography: " + row["id"])
        status, pk = classify_source(candidate, registry)
        if status in ("AMBIGUOUS", "CONFLICT"):
            raise CommandError("Source resolution " + status + ": " + row["id"])
        if pk is None:
            if not create:
                raise CommandError("Publication source missing: " + row["id"])
            source = m.SourceReference.objects.create(
                **{f: candidate.get(f) for f in SOURCE_FIELDS}, verification_status="source_checked",
                metadata={"brain_verified_catalog": candidate, "publication_dossier_sha256": DOSSIER_SHA})
            registry.append(dict(id=source.pk, **{f: getattr(source, f) for f in SOURCE_FIELDS}))
            decision = "NEW_VERIFIED_SOURCE"
        else:
            source = m.SourceReference.objects.get(pk=pk)
            decision = "EXISTING_MATCH"
        if any(getattr(source, field) != candidate.get(field) for field in SOURCE_FIELDS):
            raise CommandError("Approved source metadata differs from registry: " + row["id"])
        if not source_is_resolved(source):
            raise CommandError("Existing bibliography is not checked/resolved: " + row["id"])
        sources[row["id"]] = source
        row.update(source_reference_id=source.pk, **{f: getattr(source, f) for f in ("title", "citation", "url", "doi", "pmid")})
        decisions.append(dict(source_id=row["id"], classification=decision, target_pk=source.pk))
    derived["dataset_metadata"]["target_resolution"] = dict(portable_master_sha256=DOSSIER_SHA,
        publication_manifest_sha256=MANIFEST_SHA, source_ids={key: obj.pk for key, obj in sources.items()})
    return derived, sources, decisions


def projection(row, sources):
    """Exact canonical fields and evidence; used for creation and receipt verification."""
    category = row["category"]
    links = None
    if category == "source":
        return m.SourceReference, {"pk": sources[row["id"]].pk}, None
    if category in ("anatomy", "network"):
        model = m.BrainAnatomicalEntity if category == "anatomy" else m.BrainNetwork
        fields = {f: row.get(f, "" if f != "is_active" else True) for f in ENTITY_FIELDS}
        fields["seed_managed"] = False
        if category == "anatomy":
            fields["laterality"] = row["laterality"]
        links = (m.BrainAnatomicalEntitySource, "entity") if category == "anatomy" else (m.BrainNetworkSource, "network")
    elif category in ("alias", "external_identifier"):
        owner_field = "entity" if row["owner_type"] == "anatomy" else "network"
        owner_model = m.BrainAnatomicalEntity if owner_field == "entity" else m.BrainNetwork
        model = (m.BrainAnatomicalAlias if owner_field == "entity" else m.BrainNetworkAlias) if category == "alias" else m.BrainExternalIdentifier
        names = ("text", "language", "alias_type") if category == "alias" else ("namespace", "identifier", "source_version", "url")
        fields = {f: row[f] for f in names}
        fields[owner_field + "_id"] = owner_model.objects.get(slug=row["owner_slug"]).pk
        if category == "external_identifier":
            fields[("network" if owner_field == "entity" else "entity") + "_id"] = None
        if len(row["source_ids"]) != 1:
            raise CommandError("An alias/identifier requires its exact single approval source: " + row["id"])
        sid = row["source_ids"][0]
        fields.update(source_id=sources[sid].pk, source_note=row["source_notes"][sid])
    elif category == "hierarchy":
        model = m.BrainHierarchyLink
        fields = {f: row[f] for f in ("source_version", "explanation_en", "explanation_fa", "is_active")}
        fields.update(child_id=m.BrainAnatomicalEntity.objects.get(slug=row["child_slug"]).pk,
                      parent_id=m.BrainAnatomicalEntity.objects.get(slug=row["parent_slug"]).pk, sort_order=0)
        links = (m.BrainHierarchyLinkSource, "relationship")
    else:
        raise CommandError("No approved publication implementation for: " + category)
    fields["review_status"] = "reviewed"
    return model, fields, links


def canonical_counts():
    return {"anatomy": m.BrainAnatomicalEntity.objects.count(), "network": m.BrainNetwork.objects.count(),
            "alias": m.BrainAnatomicalAlias.objects.count() + m.BrainNetworkAlias.objects.count(),
            "external_identifier": m.BrainExternalIdentifier.objects.count(), "hierarchy": m.BrainHierarchyLink.objects.count(),
            "network_membership": m.BrainNetworkMembership.objects.count(), "functional_association": m.BrainFunctionalAssociation.objects.count()}


def superseded_predecessor_keys(datasets):
    """Only the exact reviewed B archive is historical after this pinned C pass.

    No archive, source or record is edited/deleted. Names and claimed hashes alone
    never exempt an unknown or curator-modified archive from conflict validation.
    """
    datasets = list(datasets)
    selections = [d for d in datasets if d.ingestion_audit.get("publication_manifest_sha256") == MANIFEST_SHA]
    if not selections:
        return set()
    document, _ = approved_artifacts()
    derived, _, _ = resolve_document(document, create=False)
    def intact(dataset):
        raw = dataset.raw_text
        rows = dataset.raw_document.get("records", [])
        archived = list(dataset.records.all())
        records = {r.external_id: r for r in archived}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return False
        return (hashlib.sha256(raw.encode("utf-8")).hexdigest() == dataset.source_sha256
                and parsed == dataset.raw_document and dataset.metadata == dataset.raw_document["dataset_metadata"]
                and len(rows) == len(archived) == len(records) and set(records) == {r["id"] for r in rows}
                and all(records[r["id"]].payload == r and records[r["id"]].source_ids == r["source_ids"]
                        and records[r["id"]].review_status == r["review_status"]
                        and records[r["id"]].verification_status == r["verification_status"] for r in rows))
    if not any(d.raw_document == derived and intact(d) for d in selections):
        return set()
    raw = PREDECESSOR.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PREDECESSOR_SHA:
        raise CommandError("Reviewed predecessor artifact hash conflict.")
    previous = json.loads(raw.decode("utf-8"))
    original_sources = {r["id"]: r for r in previous["records"] if r["category"] == "source"}
    registry = list(m.SourceReference.objects.values("id", *SOURCE_FIELDS))
    result = set()
    for dataset in datasets:
        if dataset.raw_document.get("dataset_metadata", {}).get("key") != previous["dataset_metadata"]["key"]:
            continue
        normalized = copy.deepcopy(dataset.raw_document)
        if not isinstance(normalized.get("records"), list) or any(not isinstance(r, dict) for r in normalized["records"]):
            continue
        resolution = normalized["dataset_metadata"].pop("target_resolution", None)
        if resolution is not None and (not isinstance(resolution, dict) or resolution.get("portable_master_sha256") != PREDECESSOR_SHA):
            continue
        valid_sources = True
        for row in normalized.get("records", []):
            if row.get("category") != "source" or row.get("id") not in original_sources:
                continue
            original = original_sources[row["id"]]
            if row.get("source_reference_id") != original["source_reference_id"]:
                status, pk = classify_source(previous["dataset_metadata"]["verified_source_catalog"][row["id"]], registry)
                if status != "MATCHED_EXISTING" or pk != row.get("source_reference_id"):
                    valid_sources = False
                row["source_reference_id"] = original["source_reference_id"]
        if (valid_sources and normalized == previous and intact(dataset)
                and not dataset.records.exclude(promoted_model="", promoted_pk=None).exists()):
            result.add(dataset.key)
    return result


def verify_receipt(dataset, document=None, manifest=None):
    """A pointer alone is not evidence; verify pinned input, raw archive and all canonical data."""
    if document is None:
        document, manifest = approved_artifacts()
    derived, sources, _ = resolve_document(document, create=False)
    raw = encoded(derived)
    if (not dataset.is_active or dataset.metadata != derived["dataset_metadata"]
            or dataset.raw_text != raw or dataset.raw_document != derived or
            dataset.source_sha256 != hashlib.sha256(raw.encode("utf-8")).hexdigest() or
            dataset.ingestion_audit.get("publication_manifest_sha256") != MANIFEST_SHA):
        raise CommandError("Publication archive/receipt differs from the pinned approved selection.")
    archived = list(dataset.records.all())
    records = {r.external_id: r for r in archived}
    if len(archived) != len(records):
        raise CommandError("Publication archive contains duplicate external record IDs.")
    if set(records) != {r["id"] for r in derived["records"]}:
        raise CommandError("Publication archive records differ from the reviewed inventory.")
    for row in derived["records"]:
        record = records[row["id"]]
        model, fields, links = projection(row, sources)
        obj = model.objects.filter(pk=record.promoted_pk).first()
        if (record.payload != row or record.review_status != row["review_status"]
                or record.verification_status != row["verification_status"] or record.source_ids != row["source_ids"]
                or record.promoted_model != model._meta.label or obj is None
                or any(getattr(obj, f) != value for f, value in fields.items())):
            raise CommandError("Published record identity/state conflict: " + row["id"])
        obj.full_clean()
        if links:
            actual = dict(obj.source_links.values_list("source_id", "note"))
            expected = {sources[sid].pk: row["source_notes"][sid] for sid in row["source_ids"]}
            if actual != expected:
                raise CommandError("Published claim-specific provenance conflict: " + row["id"])
    expected_counts = {key: manifest["counts"].get(key, 0) for key in canonical_counts()}
    if canonical_counts() != expected_counts:
        raise CommandError("Canonical Brain counts do not exactly reconcile with the approved manifest.")
    return set(records)


def published_record_ids(dataset):
    if dataset.ingestion_audit.get("publication_manifest_sha256") != MANIFEST_SHA:
        return set()
    try:
        return verify_receipt(dataset)
    except (CommandError, ValueError, ObjectDoesNotExist, ValidationError):
        return set()


def publish(*, dry_run=True, dossier=DOSSIER, manifest=MANIFEST):
    document, approval = approved_artifacts(dossier, manifest)
    with transaction.atomic():
        # ponytail: rare curator operation reuses the existing global Brain lock.
        m.lock_brain_curation("default")
        before = canonical_counts()
        derived, sources, decisions = resolve_document(document, create=True)
        raw = encoded(derived)
        from .brain_staging import ingest_brain_document, validate_brain_staging
        dataset, created = ingest_brain_document(raw, DOSSIER.name.replace(".json", ".resolved.json"))
        if not created:
            verify_receipt(dataset, document, approval)
            result = dict(status="ALREADY_PUBLISHED", canonical_writes=0, counts=before, dataset_key=dataset.key)
        else:
            if any(before.values()):
                raise CommandError("This first controlled pass requires an empty Brain corpus or its exact valid receipt.")
            # Approval is provisional inside this atomic transaction; any failure
            # rolls it back. It enables exact predecessor recognition during staging.
            dataset.ingestion_audit = dict(dataset.ingestion_audit, publication_manifest_sha256=MANIFEST_SHA,
                                          portable_master_sha256=DOSSIER_SHA)
            dataset.save(update_fields=("ingestion_audit", "updated_at"))
            validation = validate_brain_staging(dataset.key)
            if validation["issues"]:
                raise CommandError("Brain staging validation failed: " + json.dumps(validation["issues"]))
            records = {r.external_id: r for r in dataset.records.all()}
            for category in ORDER:
                for row in derived["records"]:
                    if row["category"] != category:
                        continue
                    model, fields, links = projection(row, sources)
                    if category == "source":
                        obj = sources[row["id"]]
                    else:
                        obj = model.objects.create(**dict(fields, review_status="unreviewed" if links else "reviewed"))
                        if links:
                            link_model, owner_field = links
                            for sid in row["source_ids"]:
                                link_model.objects.create(**{owner_field: obj, "source": sources[sid], "note": row["source_notes"][sid]})
                            obj.review_status = "reviewed"
                            obj.save(update_fields=("review_status", "updated_at"))
                    record = records[row["id"]]
                    record.promoted_model, record.promoted_pk = model._meta.label, obj.pk
                    record.save(update_fields=("promoted_model", "promoted_pk", "updated_at"))
            verify_receipt(dataset, document, approval)
            result = dict(status="DRY_RUN_VALIDATED" if dry_run else "PUBLISHED", canonical_writes=0 if dry_run else sum(canonical_counts().values()),
                          planned_canonical_rows=sum(canonical_counts().values()), counts=canonical_counts(), dataset_key=dataset.key)
        result.update(dossier_sha256=DOSSIER_SHA, manifest_sha256=MANIFEST_SHA, version=VERSION,
                      source_resolution=decisions, source_registry_count=m.SourceReference.objects.count())
        if dry_run:
            transaction.set_rollback(True)
        return result, derived
