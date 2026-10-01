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
    titles = [candidate["title"], *candidate.get("verified_alternate_titles", [])]
    if normalized_text(found["title"]) not in {normalized_text(t) for t in titles}:
        return "CONFLICT", None
    if candidate.get("publication_year") and found.get("publication_year") and candidate["publication_year"] != found["publication_year"]:
        return "CONFLICT", None
    return "MATCHED_EXISTING", found["id"]


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
    print("Source resolver self-check: PASS (matches, duplicate/ambiguous, conflict, version-preserving URL)")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        call_command(name, *args, stdout=log, **kwargs)
        result = log.getvalue()
        (output / (name + ".txt")).write_text(result, encoding="utf-8")
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
        staging=promotion, audit=audit, archival_integrity=integrity.strip())
    write_json(output / "validation-summary.json", summary)
    if not unchanged or promotion["issues"] or promotion["canonical_writes"] != 0:
        raise ValueError("Validation did not meet unchanged/zero-write/no-issue requirements; inspect evidence.")
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
