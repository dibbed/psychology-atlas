"""Lossless Brain staging and read-only candidate validation.

This module deliberately has no canonical promotion path. A reviewed source
dossier and a separately approved publication pass are still required.
"""

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import CommandError
from django.db import transaction

from .brain_publication import valid_brain_url, source_is_resolved
from .models import (
    BrainAnatomicalAlias, BrainNetworkAlias, BrainAnatomicalEntity, BrainHierarchyLink, BrainNetwork,
    BrainNetworkMembership, BrainFunctionalAssociation, BrainExternalIdentifier,
    ResearchDataset, ResearchRecord, ScientificReviewStatus, SourceReference,
)


SCHEMA = "brain-staging-v1"
CATEGORIES = {
    "anatomy": ("brain_anatomy", "A"), "network": ("brain_networks", "B"),
    "alias": ("brain_aliases", "C"), "hierarchy": ("brain_hierarchy", "D"),
    "external_identifier": ("brain_external_identifiers", "E"), "source": ("brain_sources", "F"),
    "network_membership": ("brain_network_memberships", "G"),
    "functional_association": ("brain_functional_associations", "G"),
}
COMMON_FIELDS = {"id", "category", "source_ids", "source_notes", "review_status", "verification_status", "is_active"}
FIELDS = {
    "source": {"source_reference_id", "title", "citation", "url", "doi", "pmid"},
    "anatomy": {"slug", "name_en", "name_fa", "kind", "laterality", "description_en", "description_fa",
                "source_version", "spatial_scope", "persian_reviewed"},
    "network": {"slug", "name_en", "name_fa", "kind", "description_en", "description_fa",
                "source_version", "definition", "method", "persian_reviewed"},
    "alias": {"owner_type", "owner_slug", "text", "language", "alias_type", "persian_reviewed"},
    "hierarchy": {"child_slug", "parent_slug", "predicate", "source_version", "explanation_en", "explanation_fa"},
    "external_identifier": {"owner_type", "owner_slug", "namespace", "identifier", "source_version", "url"},
    "network_membership": {"entity_slug", "network_slug", "evidence_key", "predicate", "source_version", "method",
                           "qualifier", "limitations", "explanation_en", "explanation_fa"},
    "functional_association": {"subject_type", "subject_slug", "concept_slug", "evidence_key", "predicate",
                               "source_version", "method", "task_context", "population_context", "limitations",
                               "explanation_en", "explanation_fa"},
}


def text(value):
    return value if isinstance(value, str) else ""


def stable_slug(value):
    return bool(re.fullmatch(r"[a-z0-9_-]{1,180}", text(value)))


def ingest_brain_document(raw_text, filename):
    try:
        document = json.loads(raw_text)
    except (ValueError, TypeError) as error:
        raise CommandError(f"Invalid Brain JSON: {error}") from error
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA:
        raise CommandError(f"An explicit {SCHEMA} document is required; generic research is not Brain input.")
    metadata = document.get("dataset_metadata")
    rows = document.get("records")
    if not isinstance(metadata, dict) or not stable_slug(metadata.get("key")) or not text(metadata.get("version")).strip():
        raise CommandError("Brain dataset metadata requires an explicit stable key and source version.")
    if len(metadata["key"]) > 160 or len(metadata["version"]) > 120 or not isinstance(rows, list):
        raise CommandError("Invalid Brain dataset key/version length or records collection.")
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    key = f"{metadata['key']}-{digest[:12]}"
    with transaction.atomic():
        dataset, created = ResearchDataset.objects.get_or_create(source_sha256=digest, defaults={
            "key": key, "source_filename": Path(filename).name, "dataset_name": metadata["key"],
            "dataset_version": metadata["version"], "metadata": metadata,
            "ingestion_audit": {"list_record_total": len(rows), "brain_staging_schema": SCHEMA},
            "raw_text": raw_text, "raw_document": document,
        })
        if not created:
            if dataset.raw_text != raw_text or dataset.raw_document != document:
                raise CommandError("Archived Brain dataset integrity conflict; existing data was preserved.")
            # Preserve curator changes, review states, inactivity, and staging pointers.
            return dataset, False
        ids = Counter(text(row.get("id")) for row in rows if isinstance(row, dict))
        for index, original in enumerate(rows):
            row = original if isinstance(original, dict) else {"raw_record": original}
            external_id = text(row.get("id"))
            if not external_id or ids[external_id] > 1 or len(external_id) > 270:
                external_id = f"record-{index:06d}-{hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]}"
            section, _ = CATEGORIES.get(row.get("category") if isinstance(row.get("category"), str) else "", ("brain_unsupported", "H"))
            ResearchRecord.objects.create(
                dataset=dataset, section=section, external_id=external_id,
                canonical_key=f"{section}:{text(row.get('slug')) or external_id}"[:400],
                slug=text(row.get("slug"))[:220], name_en=text(row.get("name_en"))[:500], name_fa=text(row.get("name_fa"))[:500],
                source_ids=row.get("source_ids") if isinstance(row.get("source_ids"), list) else [],
                review_status=text(row.get("review_status"))[:64], verification_status=text(row.get("verification_status"))[:64],
                payload=row,
            )
    return dataset, True


def validate_brain_staging(dataset_key=None):
    all_datasets = ResearchDataset.objects.filter(raw_document__schema_version=SCHEMA).order_by("key")
    datasets = all_datasets
    if dataset_key:
        datasets = datasets.filter(key=dataset_key)
        if not datasets.exists():
            raise CommandError("The selected dataset is not a Brain staging document.")
    report = {"publication": "blocked_missing_curated_dossier", "canonical_writes": 0,
              "candidate_count": 0, "classifications": {key: 0 for key in "ABCDEFGH"}, "issues": []}
    all_identities = defaultdict(list)
    all_evidence = defaultdict(list)
    all_external_ids = defaultdict(list)
    all_aliases = defaultdict(list)
    for dataset in datasets.prefetch_related("records"):
        _validate_dataset(dataset, report)
    reported = {(row["dataset"], row["record"], row["code"]) for row in report["issues"]}

    def issue(key, record, code):
        if dataset_key and key != dataset_key:
            return
        identity = (key, record.external_id, code)
        if identity not in reported:
            report["issues"].append({"dataset": key, "record": record.external_id, "code": code})
            reported.add(identity)
    # A dataset selector limits the report, not the scope of uniqueness checks:
    # another archived dossier can still conflict with a selected candidate.
    for dataset in all_datasets.prefetch_related("records"):
        for record in dataset.records.all():
            row = record.payload
            if not isinstance(row, dict):
                continue
            if row.get("category") in ("anatomy", "network") and stable_slug(row.get("slug")):
                all_identities[(row["category"], row["slug"])].append((dataset.key, record))
            if row.get("category") in ("network_membership", "functional_association") and stable_slug(row.get("evidence_key")):
                all_evidence[(row["category"], row["evidence_key"])].append((dataset.key, record))
            if row.get("category") == "external_identifier" and all(
                text(row.get(field)).strip() for field in ("namespace", "identifier", "source_version")
            ):
                identity = (text(row["namespace"]).strip().casefold(), text(row["identifier"]).strip(),
                            text(row["source_version"]).strip().casefold())
                all_external_ids[identity].append((dataset.key, record))
            if row.get("category") == "alias" and all(text(row.get(field)).strip() for field in (
                "owner_type", "owner_slug", "language", "text",
            )):
                identity = (text(row["owner_type"]), text(row["owner_slug"]), text(row["language"]),
                            " ".join(text(row["text"]).split()).casefold())
                all_aliases[identity].append((dataset.key, record))
    for (category, evidence_key), group in all_evidence.items():
        model = BrainNetworkMembership if category == "network_membership" else BrainFunctionalAssociation
        codes = []
        if len(group) > 1:
            codes.append("duplicate_evidence_key")
        if model.objects.filter(evidence_key=evidence_key).exists():
            codes.append("canonical_evidence_key_conflict")
        for key, record in group:
            for code in codes:
                issue(key, record, code)
    for group in all_identities.values():
        if len({key for key, _ in group}) > 1:
            signatures = {json.dumps({field: row.payload.get(field) for field in (
                "kind", "laterality", "name_en", "source_version", "spatial_scope", "definition",
            )}, sort_keys=True) for _, row in group}
            code = "ambiguous_identity" if len(signatures) > 1 else "duplicate_candidate"
            for key, record in group:
                issue(key, record, code)
    canonical_external_ids = {
        (namespace.strip().casefold(), identifier.strip(), version.strip().casefold())
        for namespace, identifier, version in BrainExternalIdentifier.objects.values_list(
            "namespace", "identifier", "source_version",
        ).iterator()
    }
    for identity, group in all_external_ids.items():
        codes = []
        if len(group) > 1:
            codes.append("duplicate_external_identifier")
        if identity in canonical_external_ids:
            codes.append("canonical_external_identifier_conflict")
        for key, record in group:
            for code in codes:
                issue(key, record, code)
    canonical_aliases = set()
    for owner_type, model, owner_field in (("anatomy", BrainAnatomicalAlias, "entity"), ("network", BrainNetworkAlias, "network")):
        for slug, language, alias in model.objects.values_list(f"{owner_field}__slug", "language", "text").iterator():
            canonical_aliases.add((owner_type, slug, language, " ".join(alias.split()).casefold()))
    for identity, group in all_aliases.items():
        codes = []
        if len(group) > 1:
            codes.append("duplicate_alias")
        if identity in canonical_aliases:
            codes.append("canonical_alias_conflict")
        for key, record in group:
            for code in codes:
                issue(key, record, code)
    report["issues"].sort(key=lambda row: (row["dataset"], row["record"], row["code"]))
    report["ready_for_curation"] = report["candidate_count"] - len({(row["dataset"], row["record"]) for row in report["issues"]})
    return report


def _validate_dataset(dataset, report):
    records = sorted(dataset.records.all(), key=lambda row: (row.section, row.external_id))
    source_pks = {row.payload.get("source_reference_id") for row in records if isinstance(row.payload, dict)
                  and type(row.payload.get("source_reference_id")) is int}
    source_objects = SourceReference.objects.in_bulk(source_pks)
    external_ids = Counter(text(row.payload.get("id")) for row in records if isinstance(row.payload, dict))
    sources = {}
    identities = defaultdict(list)
    candidate_names = defaultdict(list)
    aliases = defaultdict(list)
    mappings = defaultdict(list)
    links = []
    invalid_types = set()

    def issue(record, code):
        entry = {"dataset": dataset.key, "record": record.external_id, "code": code}
        if entry not in report["issues"]:
            report["issues"].append(entry)

    for record in records:
        row = record.payload
        report["candidate_count"] += 1
        category = row.get("category") if isinstance(row, dict) and isinstance(row.get("category"), str) else ""
        classification = CATEGORIES.get(category, ("", "H"))[1]
        report["classifications"][classification] += 1
        if classification == "H":
            issue(record, "unsupported_category")
            continue
        if not text(row.get("id")) or external_ids[text(row.get("id"))] != 1:
            issue(record, "duplicate_external_id" if text(row.get("id")) else "missing_external_id")
        if set(row) - (COMMON_FIELDS | FIELDS[category]):
            issue(record, "unsupported_fields")
        string_fields = (COMMON_FIELDS | FIELDS[category]) - {
            "source_ids", "source_notes", "is_active", "persian_reviewed", "source_reference_id",
        }
        if any(not isinstance(row[field], str) for field in string_fields if field in row):
            issue(record, "invalid_field_type")
            invalid_types.add(record.pk)
            continue
        if "is_active" in row and type(row["is_active"]) is not bool:
            issue(record, "invalid_active_state")
        model = {"anatomy": BrainAnatomicalEntity, "network": BrainNetwork, "alias": BrainAnatomicalAlias,
                 "hierarchy": BrainHierarchyLink, "external_identifier": BrainExternalIdentifier,
                 "network_membership": BrainNetworkMembership, "functional_association": BrainFunctionalAssociation}.get(category)
        if model and any(field.max_length and field.name in row and field.name != "text"
                         and len(text(row[field.name])) > field.max_length for field in model._meta.concrete_fields):
            issue(record, "invalid_field_length")
        if category == "source":
            source = source_objects.get(row.get("source_reference_id")) if type(row.get("source_reference_id")) is int else None
            if not source_is_resolved(source) or not any(text(row.get(key)) for key in ("url", "doi", "pmid")):
                issue(record, "unresolved_source")
            elif any(text(row.get(key)) != getattr(source, key) for key in ("title", "citation", "url", "doi", "pmid")):
                issue(record, "source_identity_conflict")
            elif external_ids[text(row.get("id"))] == 1:
                sources[row["id"]] = source
            continue
        if row.get("review_status") not in ScientificReviewStatus.values:
            issue(record, "invalid_review_state")
        if category in ("anatomy", "network"):
            if not stable_slug(row.get("slug")) or not text(row.get("name_en")).strip():
                issue(record, "invalid_identity")
            if len(text(row.get("name_en"))) > 255 or text(row.get("name_en")) != " ".join(text(row.get("name_en")).split()):
                issue(record, "invalid_identity")
            if not text(row.get("source_version")).strip() or not text(row.get("spatial_scope" if category == "anatomy" else "definition")).strip():
                issue(record, "ambiguous_identity")
            if text(row.get("name_fa")) and row.get("persian_reviewed") is not True:
                issue(record, "unverified_persian_term")
            choices = BrainAnatomicalEntity.Kind.values if category == "anatomy" else BrainNetwork.Kind.values
            if row.get("kind") not in choices:
                issue(record, "invalid_kind")
            if category == "anatomy" and row.get("laterality") not in BrainAnatomicalEntity.Laterality.values:
                issue(record, "invalid_laterality")
            if category == "network" and not text(row.get("method")).strip():
                issue(record, "missing_evidence_context")
            identities[(category, text(row.get("slug")))].append(record)
            identity = (category, text(row.get("name_en")).casefold(), row.get("kind"), row.get("laterality"),
                        text(row.get("source_version")), text(row.get("spatial_scope", row.get("definition"))))
            candidate_names[identity].append(record)
        elif category == "alias":
            normalized_alias = " ".join(text(row.get("text")).split())
            if (not normalized_alias or len(normalized_alias) > BrainAnatomicalAlias._meta.get_field("text").max_length
                    or row.get("language") not in BrainAnatomicalAlias.Language.values
                    or row.get("alias_type") not in BrainAnatomicalAlias.AliasType.values):
                issue(record, "invalid_alias")
            if row.get("language") == "fa" and row.get("persian_reviewed") is not True:
                issue(record, "unverified_persian_term")
            aliases[(text(row.get("owner_type")), text(row.get("owner_slug")), row.get("language"),
                     " ".join(text(row.get("text")).split()).casefold())].append(record)
        elif category == "external_identifier":
            if any(not text(row.get(field)).strip() for field in ("namespace", "identifier", "source_version")):
                issue(record, "invalid_external_identifier")
            if row.get("url") and not valid_brain_url(row["url"]):
                issue(record, "invalid_external_identifier")
            mappings[(text(row.get("namespace")).strip().casefold(), text(row.get("identifier")).strip(),
                      text(row.get("source_version")).strip().casefold())].append(record)
        elif category == "hierarchy":
            links.append(record)
            if row.get("predicate") != "part_of" or not text(row.get("source_version")).strip() or row.get("review_status") != "reviewed":
                issue(record, "unsupported_hierarchy")
        else:
            predicate = "participates_in_network" if category == "network_membership" else "functional_association"
            required = ("evidence_key", "source_version", "method", "qualifier") if category == "network_membership" else (
                "evidence_key", "source_version", "method", "explanation_en", "task_context", "population_context", "limitations",
            )
            if row.get("predicate") != predicate:
                issue(record, "unsupported_predicate")
            if any(not text(row.get(field)).strip() for field in required):
                issue(record, "missing_evidence_context")
            if not stable_slug(row.get("evidence_key")):
                issue(record, "invalid_evidence_identity")

    for groups, code in ((identities, "ambiguous_identity"), (candidate_names, "ambiguous_identity"),
                         (aliases, "duplicate_alias"), (mappings, "duplicate_external_identifier")):
        for group in groups.values():
            if len(group) > 1:
                for record in group:
                    issue(record, code)
    for (category, slug), group in identities.items():
        model = BrainAnatomicalEntity if category == "anatomy" else BrainNetwork
        existing = model.objects.filter(slug=slug).first()
        if existing:
            for record in group:
                fields = ("name_en", "kind", "laterality") if category == "anatomy" else ("name_en", "kind")
                if any(record.payload.get(field) != getattr(existing, field) for field in fields):
                    issue(record, "canonical_identity_conflict")

    def endpoint(record, category, slug):
        group = identities.get((text(category), text(slug)), [])
        if len(group) != 1 or group[0].payload.get("is_active") is False:
            issue(record, "unresolved_endpoint")
            return None
        return group[0].payload

    parents = defaultdict(list)
    for record in records:
        if record.pk in invalid_types or not isinstance(record.payload, dict):
            continue
        row = record.payload
        category = row.get("category") if isinstance(row.get("category"), str) else ""
        if category not in CATEGORIES or category == "source":
            continue
        ids = row.get("source_ids")
        notes = row.get("source_notes")
        if not isinstance(ids, list) or not ids or any(not isinstance(value, str) or value not in sources for value in ids):
            issue(record, "unresolved_source")
        if isinstance(ids, list):
            string_ids = [value for value in ids if isinstance(value, str)]
            resolved_ids = [sources[value].pk for value in string_ids if value in sources]
            if len(string_ids) != len(set(string_ids)) or len(resolved_ids) != len(set(resolved_ids)):
                issue(record, "duplicate_source_id")
        if not isinstance(notes, dict) or not isinstance(ids, list) or any(not text(notes.get(value)).strip() for value in ids if isinstance(value, str)):
            issue(record, "missing_provenance")
        if category in ("alias", "external_identifier"):
            endpoint(record, row.get("owner_type"), row.get("owner_slug"))
        elif category == "hierarchy":
            child = endpoint(record, "anatomy", row.get("child_slug"))
            parent = endpoint(record, "anatomy", row.get("parent_slug"))
            parents[text(row.get("child_slug"))].append(record)
            if child and parent and BrainHierarchyLink.laterality_conflicts(child.get("laterality"), parent.get("laterality")):
                issue(record, "laterality_conflict")
        elif category == "network_membership":
            endpoint(record, "anatomy", row.get("entity_slug"))
            endpoint(record, "network", row.get("network_slug"))
        elif category == "functional_association":
            endpoint(record, row.get("subject_type"), row.get("subject_slug"))
            from .models import Concept
            if not Concept.objects.filter(slug=text(row.get("concept_slug")), is_active=True).exists():
                issue(record, "unresolved_construct")
    for child, group in parents.items():
        if len(group) > 1:
            for record in group:
                issue(record, "multiple_primary_parents")
    for record in links:
        current = text(record.payload.get("parent_slug"))
        seen = {text(record.payload.get("child_slug"))}
        while current in parents:
            if current in seen:
                issue(record, "hierarchy_cycle")
                break
            seen.add(current)
            current = text(parents[current][0].payload.get("parent_slug"))
