# Psychology Atlas v0.6.3 — Psychologist + Theory + Timeline Read APIs

Date: 2026-09-05

## Scope

v0.6.3 exposes the source-backed Psychologist, Theory and Timeline runtime introduced by v0.6.1/v0.6.2 through the canonical Django REST Framework layer. This slice is intentionally read-only. It does not add frontend routes, graph nodes, global-search integration, user-owned features, diagnosis/treatment recommendations, or a separate versioned API module.

Canonical runtime modules remain:

```text
backend/atlas/views.py
backend/atlas/serializers.py
backend/atlas/urls.py
```

No database migration is required for v0.6.3.

## Public endpoints

```text
GET /api/psychologists/
GET /api/psychologists/<slug>/

GET /api/theories/
GET /api/theories/<slug>/

GET /api/timeline/
GET /api/timeline/<slug>/
```

All list endpoints use the existing `AtlasPagination` contract:

```text
page_size = 30
page_size query parameter supported
max_page_size = 300
```

Only active runtime entities are exposed. Detail endpoints return 404 for inactive rows.

## Psychologist API

### List contract

The list serializer exposes:

- canonical English/Persian names
- bilingual summary and role fields
- bilingual nationality fields
- birth/death year only when actually stored
- `review_status`
- aliases
- active relation counts for theories, concepts, therapies and timeline events

Supported filters:

```text
q
review_status
nationality
theory=<theory-slug>
concept=<concept-slug>
therapy=<therapy-slug>
birth_from=<year>
birth_to=<year>
```

`q` searches canonical names, slug, bilingual summary/role/nationality and aliases.

### Detail contract

Detail additionally exposes:

- academic disciplines
- bilingual contributions
- affiliations
- bilingual historical context
- entity-level sources with role metadata
- sourced Psychologist→Theory relations
- sourced Psychologist→Concept relations
- sourced Psychologist→Therapy relations
- sourced Psychologist↔Psychologist relations with explicit direction
- sourced Timeline relations

Relation payloads preserve their actual vocabulary such as `proposed`, `co_proposed`, `developed`, `researched`, `influenced`, etc. They are not collapsed into a generic creator/association label.

## Theory API

### List contract

The list serializer exposes:

- canonical bilingual names
- domain
- period text
- bilingual summary
- modern scientific/status label as stored
- review status
- aliases
- active counts for linked psychologists, concepts, therapies, techniques and timeline events

Supported filters:

```text
q
review_status
domain
modern_status
psychologist=<psychologist-slug>
concept=<concept-slug>
therapy=<therapy-slug>
technique=<technique-slug>
```

### Detail contract

Detail additionally exposes:

- bilingual core propositions
- bilingual historical context
- proposition/application/criticism/limitation lists
- bilingual historical importance
- entity-level SourceReference provenance
- Psychologist→Theory attribution links
- Theory→Concept
- Theory→Therapy
- Theory→Technique
- Theory→Theory in both incoming and outgoing direction
- Timeline milestone links

Every promoted scientific relation returned by these detail endpoints carries relation-level SourceReference provenance.

## Timeline API

### List contract

Timeline rows expose the original temporal granularity:

```text
exact_date
year
year_range
approximate_year
unknown
```

Fields include:

- bilingual title
- event type + display label
- category
- date precision + display label
- `date_text`
- `year_start`
- `year_end`
- `exact_date`
- review status
- active linked-entity counts

Supported filters:

```text
q
event_type
date_precision
review_status
category
psychologist=<slug>
theory=<slug>
therapy=<slug>
technique=<slug>
concept=<slug>
year_from=<year>
year_to=<year>
```

Year filters operate as an overlap window and do not invent an exact date. For example a year-only event stored as `1980` is serialized with:

```json
{
  "date_precision": "year",
  "date_text": "1980",
  "year_start": 1980,
  "exact_date": null
}
```

### Detail contract

Timeline detail returns sourced links to:

- Psychologists
- Theories
- Therapies
- Techniques
- Concepts

Role semantics are preserved exactly where supported, including:

```text
involves_person
marks_theory_milestone
marks_therapy_milestone
marks_technique_evidence_milestone
related
```

## Provenance contract

v0.6.3 adds a richer API source serializer for the new domains. Source payloads can expose:

```text
id
title
organization
citation
url
publication_year
source_type
authors
doi
pmid
verification_status
```

Entity-source links additionally preserve their source role and note. Relation-source links preserve the exact sources attached to that scientific relation.

The API does not synthesize citations, authors, DOI, PMID, dates or verification state.

## Query strategy

List endpoints use database annotations for active relation counts plus bounded alias prefetching. Detail endpoints use explicit `Prefetch` querysets with `select_related` for relation endpoints and relation-source rows. Serializer methods read from the prefetched relation caches rather than issuing one query per relation.

Measured against the real v0.6.2 runtime database:

```text
Psychologist list, 76 results:   3 queries
Theory list, 45 results:         3 queries
Timeline list, 61 results:       2 queries

Psychologist detail:            13 queries
Theory detail:                  13 queries
Timeline detail:                 9 queries
```

The automated v0.6.3 suite also contains explicit upper bounds so later refactors cannot silently introduce N+1 behavior.

## Validation and safety boundaries

- invalid `review_status`, `event_type` or `date_precision` values return HTTP 400
- invalid/non-numeric/out-of-range years return HTTP 400
- reversed year/birth ranges return HTTP 400
- inactive entities are excluded from list and detail APIs
- inactive relation endpoints are excluded from serialized relation blocks
- year-only events remain year-only
- API output is educational and descriptive; it does not rank therapies or generate personalized diagnosis/treatment advice

## Validation result

Targeted v0.6.3 tests:

```text
6 / 6 PASS
```

Full backend suite after v0.6.3:

```text
120 / 120 PASS
```

Additional gates:

```text
Django system check                         PASS
makemigrations --check --dry-run           PASS · no changes detected
compileall                                 PASS
pip check                                  PASS
research archive verification              PASS · 2 datasets / 1918 records
real runtime                               76 Psychologists / 45 Theories / 61 TimelineEvents
Knowledge Graph                            478 nodes / 934 edges / 18 queries (unchanged)
```

## Explicitly deferred to later v0.6 slices

v0.6.4:

- Psychologists frontend explorer/profile
- Theories frontend explorer/profile
- Timeline UX
- navigation/home integration for these domains

v0.6.5:

- Knowledge Graph nodes/edges for Psychologist/Theory/Timeline
- Global Search integration
- cross-domain pathfinding involving the new domains
- graph cache invalidation for the new runtime relation families

v0.6.6:

- final hardening
- accessibility/performance audit
- final release freeze
