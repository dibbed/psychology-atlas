# Psychology Atlas v0.6.4 Deep Audit — 2026-09-05

## Scope

This audit reviewed the project from the frozen v0.5.5 baseline through v0.6.1–v0.6.4, with emphasis on whether the implemented runtime actually matches the documented architecture and release claims.

Audit layers:

1. Git/release/version consistency
2. Django schema, migrations and database integrity
3. Research staging/promotion/idempotency
4. Scientific provenance and source-registry quality boundaries
5. Psychologist/Theory/Timeline API contracts and query budgets
6. Frontend routes and runtime rendering across old and new domains
7. Knowledge Graph/Search boundary before v0.6.5
8. Production-oriented security configuration
9. Documentation/manifest drift

## Overall result

The v0.6.1–v0.6.4 architecture and runtime are fundamentally sound. No schema corruption, broken migration, broken promoted target, provenance gap, API N+1 regression, Timeline date fabrication, Graph boundary leak, archive corruption or broad route failure was found.

Two real issues were found and fixed during this audit:

- stale release metadata/documentation still presenting pre-research seed counts as current runtime counts;
- legacy Concept/Disorder/Therapy/Technique source tabs rendering URL-less bibliographic sources as clickable empty links.

Both were corrected without changing backend scientific data or fabricating URLs.

## Git/release integrity

Release chain reviewed:

```text
20a60e9  v0.5.5 final freeze
4b3704c  v0.6.2 research promotion foundation
1a37653  v0.6.3 knowledge read APIs
dfb1523  v0.6.4 frontend people/theory/timeline
```

The audit began from a clean `main` working tree.

## Database and migration integrity

Checks:

```text
Django full test suite                 120/120 PASS
makemigrations --check --dry-run       PASS · no changes detected
migrate --plan                         PASS · no pending operations
SQLite PRAGMA integrity_check          ok
SQLite PRAGMA foreign_key_check        0 issues
Python compileall                      PASS
pip check                              PASS
```

No backend runtime or migration changes were required by the audit.

## Current live runtime inventory

```text
Disorder                               241
Symptom                                107
Concept                                148
Cognitive Distortion subtype            20
ConceptAlias                            31
ConceptRelationship                     40
ConceptSymptom                          19

TherapyFamily                           10
TherapyClassification                   16
Therapy                                 20
Technique                               35
TherapyDisorder                         28
TherapyConcept                          43
TherapyTechnique                        50
TechniqueConcept                        54

Psychologist                            76
PsychologistAlias                        7
Theory                                  45
TheoryAlias                              2
TimelineEvent                           61
```

## v0.6 provenance integrity

Active entity provenance gaps:

```text
Psychologist      0 / 76
Theory            0 / 45
TimelineEvent     0 / 61
```

Active relation provenance gaps:

```text
PsychologistTheory          0 / 48
PsychologistConcept         0 / 74
PsychologistTherapy         0 / 19
PsychologistPsychologist    0 / 0
TheoryConcept               0 / 75
TheoryTherapy               0 / 3
TheoryTechnique             0 / 0
TheoryTheory                0 / 3
TimelinePsychologist        0 / 55
TimelineTheory              0 / 27
TimelineTherapy             0 / 25
TimelineTechnique           0 / 1
TimelineConcept             0 / 35
```

All active Psychologist/Theory/Timeline canonical names and slugs have both EN/FA identity fields present.

## Scientific-quality boundary

The audit distinguished existence of provenance from strength of independent verification.

Entity rows whose only direct source verification status is `citation_from_model_knowledge` remain `unreviewed`:

```text
Psychologist      25 weak-only entities · 0 source_checked
Theory            14 weak-only entities · 0 source_checked
TimelineEvent     20 weak-only entities · 0 source_checked
```

There are 52 v0.6 relation rows whose relation provenance currently relies only on `citation_from_model_knowledge`:

```text
PsychologistTheory       5
PsychologistTherapy      9
TheoryConcept            1
TheoryTherapy            3
TheoryTheory             2
TimelinePsychologist    17
TimelineTheory           2
TimelineTherapy          7
TimelineConcept          6
```

This is not hidden from users: the frontend labels `source_checked` as source-backed but not final scientific review, and labels `citation_from_model_knowledge` as an archival citation requiring independent review.

These 52 relations should remain in the scientific-review queue for v0.6.6/v1.0 rather than being silently upgraded or deleted.

## Source registry integrity

```text
SourceReference                         189
Duplicate non-empty DOI                   0
Duplicate non-empty URL                   0
Duplicate title/year                      0
Malformed basic DOI syntax                0 / 79
Non-numeric PMID                          0 / 29
Malformed non-empty HTTP(S) URLs          0
```

No DOI, PMID, URL, author or citation was fabricated during the audit.

## Research archive and promotion

Exact archive verification:

```text
psychology_atlas_research_dataset.json
762 records · 618107 bytes
sha256 753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0

psychology_atlas_research_dataset_complete___1.json
1156 records · 1281373 bytes
sha256 3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

ResearchRecord inventory:

```text
Total                                    1918
Psychologist staging                      130 · 93 mapped / 37 unpromoted
Theory staging                              53 · 51 mapped / 2 unpromoted
Timeline staging                            63 · 61 mapped / 2 unpromoted
Relationship staging                       805 · 479 mapped / 326 unpromoted
```

Relationship promotion now documented as:

```text
176 pre-v0.6 promoted relationship rows
303 v0.6 future-domain promoted relationship rows
479 total promoted relationship ResearchRecord rows
```

All 1,271 ResearchRecord rows carrying `promoted_model`/`promoted_pk` point to existing runtime targets; broken mappings = 0.

`promote_research_staging --dry-run` remains idempotent and reports no duplicate entity creation.

## Timeline integrity

Current promoted Timeline span:

```text
1879–2026
61 events
```

Invalid precision/date combinations found: 0.

Year-only events retain `exact_date = null`; no synthetic January 1 dates were introduced.

## v0.6 API integrity

Real database query budgets reconfirmed:

```text
Psychologist list     3 queries
Theory list           3 queries
Timeline list         2 queries
Psychologist detail  13 queries
Theory detail        13 queries
Timeline detail       9 queries
```

Invalid filter checks return HTTP 400 for invalid review status, invalid year integers/ranges, invalid Timeline event type and invalid date precision.

Pagination is bounded by the project contract (`AtlasPagination.max_page_size = 300`).

## Frontend deep crawl

A production Next build was started against the real local backend and 514 URLs were crawled, covering:

- Home / main list routes / Graph / Search
- all 148 Concept detail routes
- all 20 Therapy detail routes
- all 35 Technique detail routes
- all 76 Psychologist detail routes
- all 45 Theory detail routes
- all 61 Timeline detail routes
- Timeline scopes for every active Psychologist
- Timeline scopes for every active Theory

Result:

```text
514/514 HTTP/content checks PASS
0 Application error markers
0 Internal Server Error markers
0 visible undefined markers
0 visible NaN markers
0 [object Object] markers
```

Final frontend gates after audit fixes:

```text
TypeScript typecheck                    PASS
Next.js production build               PASS · 23 generation units
npm audit --audit-level=low             0 vulnerabilities
```

Direct Playwright visual interaction remains unavailable because optional Playwright support is not installed in the local MCP environment. This is a validation limitation, not a project runtime failure.

## Fixed regression: URL-less direct sources

Research enrichment introduced legitimate bibliographic sources that have citation metadata but no direct URL.

Current URL-less source-link counts:

```text
ConceptSource       58
DisorderSource       5
TherapySource       11
TechniqueSource      4
```

Legacy source tabs previously rendered every source as `<a href={source.url}>`, producing `href=""` for these rows.

Fixed components:

```text
frontend/components/ConceptDetailClient.tsx
frontend/components/DisorderDetailClient.tsx
frontend/components/TherapyDetailView.tsx
frontend/components/TechniqueDetailView.tsx
```

New behavior:

- source with URL -> external link;
- source without URL -> non-clickable source card + `URL مستقیم ثبت نشده`;
- citation/title remains visible;
- no URL is guessed or fabricated.

`DSMRecordView.tsx` already handled this case correctly and required no change.

## Fixed release-metadata drift

`README.md` and `BUILD_MANIFEST.json` contained several old seed-baseline values under current-runtime wording, including 44 Concepts / 30 Symptoms / 330 Graph nodes and a generic 176 promoted relationship count.

They were synchronized to the current live database and the historical seed/pre-v0.6 numbers are now explicitly identified as historical/seed values rather than current totals.

A live manifest-to-database consistency script reports zero mismatches for the audited current fields.

## Knowledge Graph / Search boundary

Current graph remains:

```text
478 nodes
934 edges
18 build queries
33 edge kinds
```

Node types:

```text
148 Concept
241 Disorder
34 Symptom
20 Therapy
35 Technique
```

Psychologist, Theory and Timeline are still intentionally absent from Graph/Search integration until v0.6.5.

Current pre-v0.6 Graph/Search behavior remains healthy:

- CBT global search resolves Cognitive Behavioral Therapy;
- Panic Disorder -> CBT -> Cognitive Restructuring path resolves in 2 hops.

## Deployment security audit

Local `DEBUG=1` naturally triggers Django `--deploy` warnings.

With `DEBUG=0`, a non-default secret and production host:

- SSL redirect becomes enabled by default;
- session cookie secure becomes enabled;
- CSRF cookie secure becomes enabled;
- HSTS seconds defaults to one year;
- Django then reports only HSTS include-subdomains/preload as warnings.

Those two remain explicit opt-ins because they should only be enabled when all deployment subdomains and preload consequences are understood.

## Final assessment

Safe to continue to v0.6.5 after this audit hardening commit.

Remaining known limitations are intentional rather than hidden defects:

1. 52 v0.6 relation rows still need stronger independent source verification before final scientific sign-off.
2. Browser visual interaction/viewport QA still needs a Playwright-capable environment.
3. Psychologist/Theory/Timeline Graph + Global Search integration is intentionally deferred to v0.6.5.
4. Full scientific review/CMS/claim-level review workflow remains later roadmap work.
