"""Brain publication gates shared by reads, staging validation, and audits."""

import re

from django.db.models import Q, TextField
from django.db.models.expressions import RawSQL
from django.db.models.functions import Replace, Trim
from django.db.models import Value

from .models import BrainAnatomicalEntity, BrainHierarchyLink, SourceReference


CHECKED_SOURCE_STATES = (
    "source_checked", "verified", "search_verified", "web_verified_doi", "web_verified_doi_and_pmid",
)
URL_PATTERN = r"^https?://[A-Za-z0-9][^\s/]+(?:/[^\s]*)?\Z"
DOI_PATTERN = r"^10[.][0-9]{4,9}/\S+\Z"
PMID_PATTERN = r"^[0-9]+\Z"
NESTED_LIMIT = 30


def source_is_resolved(source):
    if source is None or source.verification_status not in CHECKED_SOURCE_STATES:
        return False
    if not source.title.strip() or not source.citation.strip():
        return False
    locators = ((source.url, URL_PATTERN), (source.doi, DOI_PATTERN), (source.pmid, PMID_PATTERN))
    return any(value for value, _ in locators) and all(
        not value or re.fullmatch(pattern, value) for value, pattern in locators
    )


def resolved_sources():
    def stripped(field):
        value = field
        for whitespace in ("\t", "\n", "\r"):
            value = Replace(value, Value(whitespace), Value(""), output_field=TextField())
        return Trim(value, output_field=TextField())

    return SourceReference.objects.filter(verification_status__in=CHECKED_SOURCE_STATES).alias(
        checked_title=stripped("title"), checked_citation=stripped("citation"),
    ).exclude(checked_title="").exclude(checked_citation="").filter(
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
        is_active=True, review_status="reviewed", source_version__regex=r"\S",
        source_links__source__in=resolved_sources(), source_links__note__regex=r"\S",
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
