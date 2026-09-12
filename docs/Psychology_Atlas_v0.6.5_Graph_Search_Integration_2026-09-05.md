# Psychology Atlas v0.6.5 — Knowledge Graph + Global Search Integration

Date: 2026-09-05
Branch: `main`
Scope: v0.6.5 integration slice

## Purpose

v0.6.5 makes the canonical Psychologist, Theory and Timeline domains introduced in v0.6.1–v0.6.4 first-class participants in the existing Atlas Knowledge Graph and Global Search. The integration is deliberately explicit: no similarity model, co-occurrence heuristic, generated historical attribution, or inferred confidence edge is introduced.

Every new Graph edge corresponds to an active canonical runtime relation already stored in the database. Relation semantics and relation-level `SourceReference` provenance are preserved in the Graph payload rather than collapsed into a generic `related` edge.

## Runtime inventory integrated

```text
Psychologist     76
Theory           45
TimelineEvent    61
```

New explicit relation inventory:

```text
PsychologistTheory       48
PsychologistConcept      74
PsychologistTherapy      19
PsychologistPsychologist  0
TheoryConcept            75
TheoryTherapy             3
TheoryTechnique           0
TheoryTheory               3
TimelinePsychologist      55
TimelineTheory            27
TimelineTherapy           25
TimelineTechnique          1
TimelineConcept           35
--------------------------------
Total                    365
```

No unsupported staging relation is force-created for Graph completeness.

## Global Search integration

`GET /api/search/?q=...` now returns eight Atlas result families plus DSM search handled by the frontend:

```text
disorders
concepts
symptoms
therapies
techniques
psychologists
theories
timeline_events
```

Psychologist search covers canonical English/Persian names, slug, aliases, summaries, roles, nationality and historical context. Theory search covers canonical names, aliases, summaries, core proposition, historical context, domain, period and modern status. Timeline search covers title, slug, descriptions, historical importance, category and stored date text.

Psychologist, Theory and Timeline use exact-first behavior for canonical identifiers/names where appropriate, then fall back to partial search. This avoids a broad substring match outranking an exact historical entity or event title.

Inactive runtime rows are never returned.

Real-database examples verified during implementation:

```text
Aaron T. Beck          -> psychologist: aaron-t-beck
                         + matching 1994 Timeline milestone
Beck Cognitive Model   -> theory: beck-cognitive-model
1897                   -> timeline: tl-pavlov-1897
```

Representative full search uses a bounded query count; Aaron T. Beck search measured 14 queries on the current database. The test suite enforces a <=18 query budget for the new integrated search path.

## Knowledge Graph node integration

Three new node types are added:

### Psychologist

Graph IDs use:

```text
psychologist:<slug>
```

Payload includes canonical names, role, nationality when known, birth/death years when known, review status, stored summary and public profile href.

### Theory

Graph IDs use:

```text
theory:<slug>
```

Payload includes canonical names, domain, period, modern status, review status, stored summary/core-proposition fallback and public profile href.

### Timeline

Graph IDs use:

```text
timeline:<slug>
```

Payload includes title, event type, category, review status, stored description/historical importance, date precision, date text, year range and exact date only when an exact date actually exists.

A year-only event is never converted to a fabricated `YYYY-01-01` date.

## Knowledge Graph edge integration

New edge kinds retain both relation family and original semantic code:

```text
psychologist_theory_<relationship_type>
psychologist_concept_<relationship_type>
psychologist_therapy_<relationship_type>
psychologist_psychologist_<relationship_type>
theory_concept_<relationship_type>
theory_therapy_<relationship_type>
theory_technique_<relationship_type>
theory_theory_<relationship_type>
timeline_psychologist_<role>
timeline_theory_<role>
timeline_therapy_<role>
timeline_technique_<role>
timeline_concept_<role>
```

Examples:

```text
psychologist_theory_developed_or_majorly_associated_with
theory_concept_includes_construct
theory_theory_extends
timeline_theory_marks_theory_milestone
timeline_technique_marks_technique_evidence_milestone
```

This design prevents attribution vocabulary such as `developed`, `researched`, `challenged`, `grounds`, `extends`, or historical milestone roles from being flattened into an ambiguous edge.

## Graph provenance

Each scientific v0.6 edge exposes:

```text
review_status
explanation
sources[]
```

Each source carries the stored fields needed for scientific inspection when present:

```text
id
title
organization
citation
url
publication_year
source_type
verification_status
doi
pmid
```

Audit result on the real database:

```text
v0.6 Graph edges             365
relation-level source gaps     0
```

`citation_from_model_knowledge` remains exactly that verification state. It is not upgraded to `verified` merely because the relation is Graph-visible. The existing frontend scientific semantics continue to distinguish those citations as requiring independent review.

## New Graph size and budget

Before v0.6.5:

```text
478 nodes
934 edges
18 build queries
33 edge kinds
```

After v0.6.5 integration:

```text
660 nodes
1299 edges
45 build queries
54 edge kinds
```

Node distribution:

```text
Disorder       241
Concept        148
Psychologist    76
Timeline        61
Theory          45
Technique       35
Symptom         34
Therapy         20
```

The 182 new nodes are exactly 76 Psychologists + 45 Theories + 61 Timeline events. The 365 new edges equal the explicit active v0.6 relation inventory.

The graph build query budget rises because thirteen source-prefetched scientific relation families were added. The full-data v0.6.5 test freezes the build at <=45 queries. The older Concept-scaling regression remains separately strict at <=13 queries in a fixture with no v0.6 entities, confirming that query count remains constant rather than scaling with Concept count.

The graph payload remains cached for five minutes.

## Cache invalidation

`backend/atlas/signals.py` now invalidates `atlas_graph` on save/delete of:

- Psychologist / Theory / TimelineEvent;
- all v0.6 scientific relation models;
- all corresponding relation-source models;
- `SourceReference` via the pre-existing shared invalidation path.

Tests explicitly verify invalidation when a new `PsychologistTheorySource` is attached and when a Psychologist summary changes.

## Filtering

The Graph API accepts the new node types:

```text
psychologist
theory
timeline
```

It also adds bounded filters:

```text
theory_domain
timeline_category
event_type
review_status
```

Invalid event types, review states and node types return HTTP 400 instead of silently degrading.

The frontend Knowledge Map supports the same discovery concepts locally over the fetched Graph, including Theory domain, Timeline category and review status controls.

## Pathfinding

The existing shortest-path engine remains generic and automatically traverses new explicit edges. The `dsm_nearby` structural edge remains excluded by default from conceptual shortest paths unless explicitly requested.

Verified fixture path:

```text
Psychologist Jane Researcher
  -> Theory v0.6.3 Model
  -> Technique v0.6.3 Technique
2 hops
```

Verified real-database path:

```text
Aaron T. Beck
  -> Automatic Thoughts
  -> Cognitive Restructuring
2 hops
```

No inferred similarity edge is required for either path.

## Concept neighborhood integration

Concept neighborhood traversal now permits `node_type=theory` and `node_type=timeline`, allowing a Concept profile/neighborhood to expose stored theory/historical context through the same explicit Graph relation set.

## Frontend integration

### Global Search

The public search UI now renders dedicated sections for:

- Psychologists;
- Theories;
- Timeline events.

Cards preserve canonical names and review status and link directly to the v0.6.4 detail routes.

### Knowledge Map

The Map now exposes eight Atlas node layers:

```text
Concept
Disorder
Symptom
Therapy
Technique
Psychologist
Theory
Timeline
```

New nodes receive separate visual treatment, structured contextual metadata, node-type filters and readable relation semantics. Relation labels preserve the original relation family and semantic role rather than presenting raw underscore codes.

### Path Finder

Path Finder labels the new relation families and supports mixed paths across people, theories, concepts, therapies, techniques and historical events.

### Home

Home is updated from the v0.6.4 deferred-Graph wording to the v0.6.5 integrated Graph state.

## Tests added

Six focused v0.6.5 integration tests are included inside the future-domain API fixture suite:

1. Global Search integration + exact-first relevance + bounded query budget.
2. v0.6 Graph nodes, all thirteen relation families and rich provenance.
3. new Graph filters + validation + cross-domain pathfinding.
4. Graph cache invalidation for entity/relation-source changes.
5. Atlas overview integration + full Graph build query budget.
6. Concept neighborhood traversal into Theory and Timeline.

The existing Concept Graph query-scaling test was updated from 10 to 13 queries because the integrated Graph performs three additional constant node-table reads. Its original non-scaling invariant is preserved.

Targeted suite after relevance hardening:

```text
12/12 PASS
```

## No schema migration

v0.6.5 reuses the models and provenance schema introduced in v0.6.1–v0.6.2.

```text
python manage.py makemigrations --check --dry-run
No changes detected
```

## Research/archive safety

Promotion dry-run remains idempotent and reports the same supported corpus mapping:

```text
76 Psychologists matched
45 Theories matched
61 Timeline events matched
303 v0.6 future-domain relationship records promoted/matched
```

Both exact research archives continue to verify byte-for-byte with their frozen SHA-256 hashes.

## Deliberately not done in v0.6.5

- no generated/inferred person or theory relations;
- no embedding similarity edges;
- no fabricated Graph confidence score;
- no fabricated date precision;
- no automatic upgrade from `citation_from_model_knowledge` to verified provenance;
- no scientific human-review workflow;
- no new schema migration.

Those quality-review and final performance concerns remain appropriate for v0.6.6 and the later v1.0 scientific-review/CMS work.

## Final freeze validation — 2026-09-12

The v0.6.5 integration slice was closed against the project-local release environment rather than the system-global Python installation.

```text
backend/.venv pip check                     PASS · no broken requirements
Django system check                         PASS
makemigrations --check --dry-run           PASS · No changes detected
full backend suite                          PASS · 126/126
frontend TypeScript                         PASS · psychology-atlas-frontend@0.6.5
Next.js production build                    PASS · 16.3.3 Turbopack · 23/23 static-generation units
npm audit --audit-level=low                 PASS · 0 vulnerabilities
production HTTP crawl                       PASS · 635/635
Chromium headless Map runtime smoke         PASS · HTTP 200
SQLite integrity_check                      ok
SQLite foreign_key_check                    0 issues
research archive verifier                   PASS · 2 datasets / 1918 records / exact hashes
promotion dry-run                           PASS · 76 / 45 / 61 entities · 303 v0.6 relation records
Graph runtime                               660 nodes / 1299 edges / 54 kinds / 45 queries
v0.6 explicit Graph edges                   365
v0.6 Graph relation-level source gaps       0
```

The 635-route production crawl includes every active detail page for 241 Disorders, 148 Concepts, 20 Therapies, 35 Techniques, 76 Psychologists, 45 Theories and 61 Timeline events, plus Home, Map, Search and the public list surfaces that actually exist. The frontend intentionally has Technique detail routes but no standalone `/techniques` list page, so that nonexistent route is not counted as a failure.

A real browser-runtime smoke also opened `/map?node=psychologist:aaron-t-beck` in Chromium headless and returned HTTP 200 with the expected application title. This replaces the earlier v0.6.4 environment limitation where Playwright support was unavailable.

The system-global Python installation has unrelated dependency conflicts from other local tools; it is not the project release environment. `backend/.venv` is clean and is the environment used for the final release test gate.

## Release boundary

v0.6.5 completes the product-level integration of Psychologists, Theories and Timeline into discovery and structured navigation. v0.6.6 is the final v0.6 hardening/freeze slice: performance review, scientific-review queue visibility, final regression and release freeze rather than another broad feature expansion.
