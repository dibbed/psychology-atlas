"""Deterministic bibliographic source identity; no database or network writes."""

import re
import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


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
    for field in ("citation", "organization"):
        if candidate.get(field) and found.get(field) and normalized_text(candidate[field]) != normalized_text(found[field]):
            return "CONFLICT", None
    if candidate.get("authors") and found.get("authors"):
        if [normalized_text(a) for a in candidate["authors"]] != [normalized_text(a) for a in found["authors"]]:
            return "CONFLICT", None
    return "MATCHED_EXISTING", found["id"]
