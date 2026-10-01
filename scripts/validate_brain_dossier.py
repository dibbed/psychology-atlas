"""Resolve a portable dossier and exercise existing commands in a new disposable DB.

No canonical publication path. The input database is opened read-only, and the
output directory must not exist and must be outside the repository.
"""

import argparse
import copy
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]


def normalized_text(value):
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold()))


def normalized_doi(value):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", unquote(value.strip()), flags=re.I).casefold()


def canonical_url(value):
    if not value:
        return ""
    url = urlsplit(value.strip())
    # Preserve meaningful query parameters, including resource versions.
    query = urlencode(sorted((k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
                             if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")))
    return urlunsplit((url.scheme.lower(), url.netloc.lower(), url.path.rstrip("/"), query, url.fragment))


def identities(row):
    keys = set()
    for field, normalize in (("doi", normalized_doi), ("pmid", lambda s: s.strip()), ("url", canonical_url)):
        if row.get(field):
            keys.add((field, normalize(row[field])))
    authors = row.get("authors", [])
    if row.get("publication_year") and authors and row.get("title"):
        keys.add(("bibliography", normalized_text(row["title"]), row["publication_year"], normalized_text(authors[0])))
    return keys


def classify_source(candidate, registry):
    """All identity signals participate; disagreeing signals never choose a winner."""
    hits = [row for row in registry if identities(candidate) & identities(row)]
    if not hits:
        return "NEW_VERIFIED_SOURCE_CANDIDATE", None
    if len(hits) > 1:
        common = set.intersection(*(identities(row) for row in hits)) & identities(candidate)
        return ("AMBIGUOUS" if common else "CONFLICT"), None
    found = hits[0]
    for field, normalize in (("doi", normalized_doi), ("pmid", lambda s: s.strip())):
        if candidate.get(field) and found.get(field) and normalize(candidate[field]) != normalize(found[field]):
            return "CONFLICT", None
    if candidate.get("url") and found.get("url"):
        urls = [candidate["url"], *candidate.get("verified_alternate_urls", [])]
        if canonical_url(found["url"]) not in {canonical_url(url) for url in urls}:
            return "CONFLICT", None
    titles = [candidate["title"], *candidate.get("verified_alternate_titles", [])]
    if normalized_text(found["title"]) not in {normalized_text(t) for t in titles}:
        return "CONFLICT", None
    if candidate.get("publication_year") and found.get("publication_year") and candidate["publication_year"] != found["publication_year"]:
        return "CONFLICT", None
    return "MATCHED_EXISTING", found["id"]


def verify_parent(dossier_path, metadata):
    name = metadata["parent_input_filename"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.json", name):
        raise ValueError("Parent input must be a plain JSON filename beside the dossier.")
    parent = (dossier_path.parent / name).resolve()
    if parent.parent != dossier_path.parent:
        raise ValueError("Parent input must not escape the dossier directory.")
    raw = parent.read_bytes()
    if len(raw) != metadata["parent_bytes"] or hashlib.sha256(raw).hexdigest() != metadata["parent_sha256"]:
        raise ValueError("Preserved parent bytes or SHA-256 conflict with reviewed lineage.")
    json.loads(raw.decode("utf-8"))


def audit_is_clear(audit):
    return not audit["errors"] and not audit["review_debt"] and audit["staging_issues"] == 0


def verify_inventory_and_dispositions(document):
    """Enforce this research phase's reviewed inventory and unresolved rights gate."""
    metadata, records = document["dataset_metadata"], document["records"]
    declared = metadata["record_counts"]
    if any(type(n) is not int or n < 0 for n in declared.values()) or Counter(declared) != Counter(r["category"] for r in records):
        raise ValueError("Records conflict with declared per-category inventory.")
    deferred = metadata["deferred_hierarchy_claims"]
    entries = [(r["id"], r["category"], "records") for r in records]
    entries += [(r["record"]["id"], "hierarchy", "dataset_metadata.deferred_hierarchy_claims") for r in deferred]
    ledger = metadata["publication_review_ledger"]
    if (len({e[0] for e in entries}) != len(entries) or
            Counter(entries) != Counter((r["record_id"], r["category"], r["location"]) for r in ledger) or
            Counter(r["classification"] for r in ledger) != Counter(metadata["publication_review_counts"])):
        raise ValueError("Publication ledger coverage/counts conflict with retained research records.")
    if (metadata["rights_review_summary"]["commercial_anatomy_publication"] != "BLOCKED_UNRESOLVED" or
            metadata["anatomy_approved_candidate_count"] != 0 or
            metadata["publication_guardrails"]["canonical_writes"] != 0 or
            metadata["publication_guardrails"]["no_canonical_brain_publication"] is not True):
        raise ValueError("This research phase requires unresolved anatomical rights and zero publication.")
    by_id = {r["record_id"]: r for r in ledger}
    for row in records + [r["record"] for r in deferred]:
        protected = row["category"] in ("anatomy", "hierarchy") or row.get("owner_type") == "anatomy"
        if protected:
            decision = by_id[row["id"]]
            if (decision["classification"] != "DEFERRED" or decision["publication_rights_status"] != "BLOCKED_UNRESOLVED" or
                    row["review_status"] != "source_checked" or row["verification_status"] != "source_checked"):
                raise ValueError("Allen-derived anatomical research must remain source-checked and rights-deferred.")
    if any(r["category"] == "hierarchy" for r in records) or any(r["classification"] != "DEFERRED" for r in deferred):
        raise ValueError("Unapproved hierarchy must remain deferred outside staging records.")


def self_test():
    source = dict(title="Example: atlas", doi="10.1234/atlas", pmid="123", url="https://example.org/atlas?version=1",
                  authors=["A Author"], publication_year=2025)
    registry = [dict(source, id=7, doi="https://doi.org/10.1234/ATLAS")]
    assert classify_source(source, registry) == ("MATCHED_EXISTING", 7)
    assert classify_source(source, []) == ("NEW_VERIFIED_SOURCE_CANDIDATE", None)
    assert classify_source(source, registry + [dict(source, id=8)]) == ("AMBIGUOUS", None)
    assert classify_source(source, [dict(source, id=7, pmid="999")]) == ("CONFLICT", None)
    assert classify_source(source, [dict(source, id=7, title="Different paper")]) == ("CONFLICT", None)
    assert classify_source(source, [dict(source, id=7, doi="", url=""),
                                    dict(source, id=8, pmid="", url="", title="Other", publication_year=2024)]) == ("CONFLICT", None)
    assert canonical_url("https://EXAMPLE.org/atlas/?utm_source=x&version=1") == source["url"]
    assert canonical_url(source["url"]) != canonical_url(source["url"].replace("version=1", "version=2"))
    assert classify_source(source, [dict(source, id=7, url=source["url"].replace("version=1", "version=2"))]) == ("CONFLICT", None)
    audit = dict(errors=[], review_debt=[], staging_issues=0)
    assert audit_is_clear(audit)
    assert not audit_is_clear(dict(audit, review_debt=["unreviewed canonical row"]))
    assert not audit_is_clear(dict(audit, staging_issues=1))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "master.json"
        parent = path.with_name("parent.json")
        raw = b'{"example": true}\r\n'
        parent.write_bytes(raw)
        lineage = dict(parent_input_filename=parent.name, parent_bytes=len(raw), parent_sha256=hashlib.sha256(raw).hexdigest())
        verify_parent(path, lineage)
        parent.write_bytes(raw.replace(b"\r\n", b"\n"))
        for wrong in (lineage, dict(lineage, parent_input_filename="../parent.json")):
            try:
                verify_parent(path, wrong)
            except ValueError:
                pass
            else:
                raise AssertionError("Changed/escaping parent input was accepted")
    master = json.loads((ROOT / "docs/research/brain/v0.9.2b/psychology_atlas_brain_curated_dossier_v0.9.2b.json").read_bytes())
    verify_inventory_and_dispositions(master)
    for mutation in ("empty", "deleted", "approval", "reviewed", "hierarchy", "rights"):
        bad = copy.deepcopy(master)
        metadata = bad["dataset_metadata"]
        if mutation == "empty":
            bad["records"] = []
        elif mutation == "deleted":
            bad["records"].pop()
        elif mutation == "approval":
            next(r for r in metadata["publication_review_ledger"] if r["category"] == "anatomy")["classification"] = "APPROVED_CANDIDATE"
            metadata["publication_review_counts"]["DEFERRED"] -= 1
            metadata["publication_review_counts"]["APPROVED_CANDIDATE"] += 1
        elif mutation == "reviewed":
            next(r for r in bad["records"] if r["category"] == "anatomy")["review_status"] = "reviewed"
        elif mutation == "hierarchy":
            restored = metadata["deferred_hierarchy_claims"].pop(0)["record"]
            restored.update(review_status="reviewed", verification_status="source_checked")
            bad["records"].append(restored)
            metadata["record_counts"]["hierarchy"] = 1
            next(r for r in metadata["publication_review_ledger"] if r["record_id"] == restored["id"])["location"] = "records"
        else:
            metadata["rights_review_summary"]["commercial_anatomy_publication"] = "CLEARED"
        try:
            verify_inventory_and_dispositions(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Truncated/inconsistent or rights-unblocked dossier was accepted: " + mutation)
    print("Dossier validation self-check: PASS (source conflicts, audit debt, parent lineage, inventory/ledger coverage, commercial rights deferral)")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_deferred_hierarchy(derived):
    """Use existing structural rules in a probe archive that is always rolled back.

    Only the in-memory probe changes hierarchy review state to satisfy the
    parser's approval precondition. This is not scientific/rights approval.
    """
    from django.db import transaction
    from atlas.brain_staging import ingest_brain_document, validate_brain_staging

    probe = copy.deepcopy(derived)
    claims = copy.deepcopy(probe["dataset_metadata"]["deferred_hierarchy_claims"])
    for claim in claims:
        claim["record"]["review_status"] = "reviewed"
        probe["records"].append(claim["record"])

    def check(document):
        with transaction.atomic():
            try:
                archive, _ = ingest_brain_document(json.dumps(document, ensure_ascii=False), "deferred-hierarchy-structural-probe.json")
                return validate_brain_staging(archive.key)
            finally:
                transaction.set_rollback(True)

    report = check(probe)
    if report["issues"] or report["candidate_count"] != len(probe["records"]):
        raise ValueError("Deferred hierarchy structural validation failed: " + json.dumps(report["issues"]))
    # Exercise the same endpoint/predicate/provenance/cycle rules in disposable
    # transactions. Neither valid nor deliberately invalid probes are archived.
    mutations = {"parent_slug": ("missing-anatomy-endpoint", "unresolved_endpoint"),
                 "predicate": ("is_a", "unsupported_hierarchy"),
                 "source_notes": ({}, "missing_provenance"),
                 "child_slug": (claims[0]["record"]["parent_slug"], "hierarchy_cycle")} if claims else {}
    for field, (value, expected) in mutations.items():
        bad = copy.deepcopy(probe)
        bad["records"][-len(claims)][field] = value
        failure = check(bad)
        if expected not in {issue["code"] for issue in failure["issues"]}:
            raise ValueError("Deferred hierarchy regression was not rejected: " + field)
    return dict(claim_count=len(claims), structural_report=report, negative_checks=list(mutations),
                archive_rolled_back=True, publication_approval=False)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(dossier_path, input_database, output):
    dossier_path, input_database, output = (Path(p).resolve() for p in (dossier_path, input_database, output))
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Disposable output must be outside the repository; target-specific IDs must not be tracked.")
    if output.exists():
        raise ValueError("Output already exists; refusing to overwrite any evidence or database.")
    document = json.loads(dossier_path.read_bytes().decode("utf-8"))
    if document.get("schema_version") != "brain-staging-v1":
        raise ValueError("Current brain-staging-v1 schema required.")
    metadata = document["dataset_metadata"]
    verify_parent(dossier_path, metadata)
    verify_inventory_and_dispositions(document)
    catalog = metadata["verified_source_catalog"]
    sources = [r for r in document["records"] if r["category"] == "source"]
    placeholders = [s["source_reference_id"] for s in sources]
    if any(type(p) is not int or p >= 0 for p in placeholders) or len(set(placeholders)) != len(placeholders):
        raise ValueError("Portable source references must be distinct external negative placeholders.")
    for source in sources:
        verified = catalog[source["id"]]
        if verified.get("bibliographic_verification") != "independently_verified" or not verified.get("verification_urls"):
            raise ValueError("Source lacks recorded bibliographic verification.")
        if any(verified[k] != source[k] for k in ("title", "citation", "doi", "pmid", "url")):
            raise ValueError("Source row conflicts with the reviewed bibliographic catalog.")
    original_hash = digest(input_database)
    output.mkdir(parents=True)
    target = output / "curation.sqlite3"
    with sqlite3.connect(input_database.as_uri() + "?mode=ro", uri=True) as original, sqlite3.connect(target) as disposable:
        original.backup(disposable)
    os.environ["DB_ENGINE"] = "sqlite"
    os.environ["SQLITE_PATH"] = str(target)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    sys.path.insert(0, str(ROOT / "backend"))
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection, transaction
    from atlas.brain_publication import source_is_resolved
    from atlas.models import ResearchDataset, SourceReference

    def command(name, *args, **kwargs):
        log = io.StringIO()
        try:
            call_command(name, *args, stdout=log, **kwargs)
        finally:
            (output / (name + ".txt")).write_text(log.getvalue(), encoding="utf-8")
        result = log.getvalue()
        return result

    command("migrate", interactive=False)

    def canonical_snapshot():
        snapshot = {}
        with connection.cursor() as cursor:
            for table in sorted(connection.introspection.table_names()):
                if table.startswith("atlas_brain"):
                    cursor.execute(f'SELECT * FROM "{table}" ORDER BY id')
                    rows = cursor.fetchall()
                    snapshot[table] = dict(count=len(rows), sha256=hashlib.sha256(repr(rows).encode()).hexdigest())
        return snapshot

    before = canonical_snapshot()
    registry = list(SourceReference.objects.order_by("pk").values("id", "title", "doi", "pmid", "url", "authors", "publication_year"))
    resolutions = []
    for source in sources:
        status, pk = classify_source(catalog[source["id"]], registry)
        resolutions.append(dict(source_id=source["id"], classification=status, target_pk=pk))
    # Check portable sources against one another too, before creating any rows.
    for source in sources:
        peers = [dict(catalog[s["id"]], id=s["id"]) for s in sources if s["id"] != source["id"]]
        if classify_source(catalog[source["id"]], peers)[0] != "NEW_VERIFIED_SOURCE_CANDIDATE":
            raise ValueError("Overlapping portable source identities require explicit review.")
    write_json(output / "source-resolution.json", resolutions)
    if any(r["classification"] in ("AMBIGUOUS", "CONFLICT", "REJECTED") for r in resolutions):
        raise ValueError("Unresolved source identity; inspect source-resolution.json. No source rows created.")
    derived = copy.deepcopy(document)
    derived_sources = {r["id"]: r for r in derived["records"] if r["category"] == "source"}
    with transaction.atomic():
        for resolution in resolutions:
            sid = resolution["source_id"]
            if resolution["target_pk"] is None:
                m = catalog[sid]
                source = SourceReference.objects.create(
                    **{k: m[k] for k in ("title", "citation", "url", "doi", "pmid")},
                    organization=m.get("organization", ""), authors=m.get("authors", []),
                    publication_year=m.get("publication_year"), source_type=m.get("source_type", ""),
                    verification_status="source_checked", metadata={"dossier_source_identity": m,
                        "rights_review": metadata["rights_review_summary"]["rights_register"][sid]})
                resolution["target_pk"] = source.pk
            else:
                source = SourceReference.objects.get(pk=resolution["target_pk"])
            if source.pk <= 0 or not source_is_resolved(source):
                raise ValueError("Matched/created registry row is not checked and resolved; no silent registry edits.")
            derived_sources[sid].update(source_reference_id=source.pk,
                **{k: getattr(source, k) for k in ("title", "citation", "url", "doi", "pmid")})
    write_json(output / "source-resolution.json", resolutions)
    derived["dataset_metadata"]["target_resolution"] = dict(portable=False, target_database="curation.sqlite3",
        portable_master_sha256=digest(dossier_path), source_registry_row_count_before=len(registry),
        classifications=dict(Counter(r["classification"] for r in resolutions)))
    resolved = output / (dossier_path.stem + ".resolved.json")
    write_json(resolved, derived)
    deferred_validation = verify_deferred_hierarchy(derived)
    write_json(output / "deferred-hierarchy-validation.json", deferred_validation)
    command("import_brain_dataset", str(resolved))
    archived = ResearchDataset.objects.get(source_sha256=digest(resolved))
    promotion = json.loads(command("promote_brain_staging", dataset=archived.key))
    audit = json.loads(command("audit_brain_atlas", as_json=True))
    integrity = command("verify_research_datasets")
    after = canonical_snapshot()
    unchanged = before == after and original_hash == digest(input_database)
    summary = dict(portable_master_sha256=digest(dossier_path), resolved_sha256=digest(resolved),
        source_resolution=dict(Counter(r["classification"] for r in resolutions)),
        canonical_before=before, canonical_after=after, original_database_unchanged=original_hash == digest(input_database),
        canonical_unchanged=before == after, canonical_writes=promotion["canonical_writes"],
        staging=promotion, deferred_hierarchy_validation=deferred_validation, audit=audit, archival_integrity=integrity.strip())
    write_json(output / "validation-summary.json", summary)
    if (not unchanged or promotion["issues"] or promotion["candidate_count"] != len(document["records"]) or
            promotion["canonical_writes"] != 0 or not audit_is_clear(audit)):
        raise ValueError("Validation did not meet unchanged/zero-write/no-issue/no-debt requirements; inspect evidence.")
    print(json.dumps({"result": "PASS", "records": promotion["candidate_count"], "issues": 0,
        "canonical_writes": 0, "source_resolution": summary["source_resolution"],
        "canonical_unchanged": True, "original_database_unchanged": True}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dossier", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif all((args.dossier, args.database, args.output)):
        run(args.dossier, args.database, args.output)
    else:
        parser.error("Use --self-test or supply --dossier, --database and a new external --output directory.")
