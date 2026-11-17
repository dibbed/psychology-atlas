"""Public exact-alias ambiguity without additional SQL.

Only inspect already serialized, rights-cleared Brain and Assessment results
from the existing public search query. Never query drafts, staging, raw source
text or hidden aliases. If either search result page or its nested aliases
were capped, explicitly report incomplete coverage rather than false
cross-domain uniqueness.
"""


def public_exact_alias_disambiguation(q, brain_results, assessment_results):
    base = {
        "scope": "public_brain_assessment_visible_search_page_only",
        "visible_count": 0,
        "truncated": False,
        "matches": [],
        "public_drafts_included": False,
    }
    if not 2 <= len(q) <= 160:
        return {**base, "status": "not_checked_query_length"}

    matches = []
    q_folded = q.casefold()
    incomplete = len(brain_results) >= 10 or len(assessment_results) >= 10

    for result in brain_results:
        incomplete = incomplete or result.get("aliases_truncated", False)
        if any(alias.get("text", "").casefold() == q_folded
               for alias in result.get("aliases", [])):
            matches.append({"domain": "brain_anatomy", "slug": result["slug"]})
    for result in assessment_results:
        aliases = result.get("aliases", {})
        incomplete = incomplete or bool(aliases.get("truncated"))
        if any(alias.get("text", "").casefold() == q_folded
               for alias in aliases.get("results", [])):
            matches.append({"domain": "assessment", "slug": result["slug"]})

    matches.sort(key=lambda row: (row["domain"], row["slug"]))
    status = ("more_than_limit" if incomplete
              else "multiple_exact_public_matches" if len(matches) > 1
              else "one_exact_public_match" if matches
              else "no_exact_public_matches")
    return {
        **base, "status": status, "visible_count": len(matches),
        "truncated": bool(incomplete), "matches": matches,
    }
