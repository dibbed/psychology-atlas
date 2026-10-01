"""Brain publication gates shared by reads, staging validation, and audits."""

import re

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.db.models.functions import Length

from .models import BrainAnatomicalEntity, BrainHierarchyLink, SourceReference


SOURCE_LENGTHS = {field.name: field.max_length for field in SourceReference._meta.concrete_fields if field.max_length}
CHECKED_SOURCE_STATES = (
    "source_checked", "verified", "search_verified", "web_verified_doi", "web_verified_doi_and_pmid",
)
# Conservative database-safe subset of Django URLs: ASCII DNS/IPv4 URIs, no credentials or IPv6; encode Unicode paths/hosts first.
URL_PATTERN = (r"(?i)^(?=[!-~]+\Z)https?://(?=[^/?#]{1,253}(?:[/?#]|\Z))"
               rf"(?:{URLValidator.ipv4_re}|{URLValidator.host_re})(?::(?:[0-9]{{1,4}}|[0-5][0-9]{{4}}|6[0-4][0-9]{{3}}|65[0-4][0-9]{{2}}|655[0-2][0-9]|6553[0-5]))?(?:[/?#][^\s]*)?\Z")
URL_VALIDATOR = URLValidator(schemes=["http", "https"])


def valid_brain_url(value):
    if not isinstance(value, str) or len(value) > SourceReference._meta.get_field("url").max_length:
        return False
    try:
        URL_VALIDATOR(value)
    except ValidationError:
        return False
    return bool(re.fullmatch(URL_PATTERN, value))


PMID_PATTERN = r"^[0-9]+\Z"
NESTED_LIMIT = 30
# Explicit Python str.strip whitespace, independent of the SQL engine's locale.
NONBLANK_PATTERN = "[^\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000]"
DOI_PATTERN = rf"^10[.][0-9]{{4,9}}/{NONBLANK_PATTERN}+\Z"


def source_is_resolved(source):
    if source is None or source.verification_status not in CHECKED_SOURCE_STATES:
        return False
    if any(not isinstance(getattr(source, field), str) or len(getattr(source, field)) > maximum
           for field, maximum in SOURCE_LENGTHS.items()):
        return False
    if not source.title.strip() or not source.citation.strip():
        return False
    if source.url and not valid_brain_url(source.url):
        return False
    locators = ((source.url, URL_PATTERN), (source.doi, DOI_PATTERN), (source.pmid, PMID_PATTERN))
    return any(value for value, _ in locators) and all(
        not value or re.fullmatch(pattern, value) for value, pattern in locators
    )


def resolved_sources():
    lengths = {f"brain_{field}_length": Length(field) for field in SOURCE_LENGTHS}
    bounds = {f"brain_{field}_length__lte": maximum for field, maximum in SOURCE_LENGTHS.items()}
    return SourceReference.objects.alias(**lengths).filter(
        **bounds,
        verification_status__in=CHECKED_SOURCE_STATES,
        title__regex=NONBLANK_PATTERN, citation__regex=NONBLANK_PATTERN,
    ).filter(
        Q(url__regex=URL_PATTERN) | Q(doi__regex=DOI_PATTERN) | Q(pmid__regex=PMID_PATTERN),
    ).filter(
        Q(url="") | Q(url__regex=URL_PATTERN),
        Q(doi="") | Q(doi__regex=DOI_PATTERN),
        Q(pmid="") | Q(pmid__regex=PMID_PATTERN),
    )


def public_anatomy():
    """One recursive SQL read gates the entire primary ancestry, including cycles.

    An active unsupported parent link cannot make its child look like a root.
    UNION terminates safely even if database writes bypassed model validation.
    The CTE uses SQL supported by both configured engines (SQLite/PostgreSQL).
    """
    entity_sql, entity_params = BrainAnatomicalEntity.objects.filter(
        is_active=True, review_status="reviewed", kind__in=BrainAnatomicalEntity.Kind.values,
        laterality__in=BrainAnatomicalEntity.Laterality.values, source_links__source__in=resolved_sources(),
    ).order_by().values("pk").distinct().query.sql_with_params()
    link_sql, link_params = BrainHierarchyLink.objects.filter(
        is_active=True, review_status="reviewed", source_version__regex=NONBLANK_PATTERN,
        source_links__source__in=resolved_sources(), source_links__note__regex=NONBLANK_PATTERN,
    ).order_by().values("pk").distinct().query.sql_with_params()
    entity_table = BrainAnatomicalEntity._meta.db_table
    hierarchy_table = BrainHierarchyLink._meta.db_table
    sql = f"""
        WITH RECURSIVE eligible(id) AS ({entity_sql}), checked_links(id) AS ({link_sql}), public_tree(id) AS (
            SELECT e.id FROM eligible e WHERE NOT EXISTS (
                SELECT 1 FROM {hierarchy_table} h WHERE h.child_id = e.id AND h.is_active
            )
            UNION
            SELECT c.id FROM public_tree t
            JOIN {hierarchy_table} h ON h.parent_id = t.id
            JOIN eligible c ON c.id = h.child_id
            JOIN {entity_table} ce ON ce.id = c.id
            JOIN {entity_table} pe ON pe.id = t.id
            WHERE h.id IN (SELECT id FROM checked_links)
              AND NOT (pe.laterality IN ('left', 'right')
                  AND ce.laterality IN ('left', 'right', 'midline', 'bilateral')
                  AND ce.laterality <> pe.laterality)
        ) SELECT id FROM public_tree
    """
    params = (*entity_params, *link_params)
    return BrainAnatomicalEntity.objects.filter(pk__in=RawSQL(sql, params))
