# Psychology Atlas v0.6.6 — Final Hardening, Performance & v0.6 Freeze

Date: 2026-09-12
Branch: `main`
Baseline: v0.6.5 commit `5016dee9239c3b9414d5bb163e5dfa1b9831d99d`
Scope: final v0.6 hardening/freeze; no broad new product domain

## Release goal

v0.6.6 closes the Psychologists + Theories + Timeline release series after v0.6.5 Graph/Search integration. The slice focuses on repeatable scientific-release auditing, search/runtime hardening, provenance visibility, performance verification, production browser/crawl regression and final release consistency.

No scientific claim is upgraded merely to make the release look complete. Weak archival citations remain weak, unknown Timeline precision remains unknown, and unsupported staging records remain staging-only.

## Changes made

### 1. Repeatable scientific release audit

New command:

```text
python manage.py audit_v06_release
```

The command is read-only. It audits active v0.6 entities and all thirteen v0.6 relation families for:

- missing relation/entity provenance;
- rows supported only by `citation_from_model_knowledge`;
- weak-only rows incorrectly marked `reviewed`;
- invalid Timeline precision/date combinations.

The command treats `source_checked` correctly: it means source-backed, not independently verified. Therefore a weak-only row may remain `source_checked`, but a weak-only row marked `reviewed` fails the release audit.

Regression tests cover both cases.

Real DB result:

```text
Psychologist      76 active · 0 gaps · 25 weak-only · 0 weak-reviewed
Theory            45 active · 0 gaps · 14 weak-only · 0 weak-reviewed
TimelineEvent     61 active · 0 gaps · 20 weak-only · 0 weak-reviewed

v0.6 relations   365 active · 0 gaps · 52 weak-only · 0 weak-reviewed
Timeline precision issues: 0
```

The known 52 weak-only relation rows remain scientific-review debt rather than being silently deleted or upgraded.

### 2. Global Search performance hardening

The v0.6.5 exact-first implementation used `.exists()` before reading each Therapy / Technique / Psychologist / Theory / Timeline result family. That preserved correctness but introduced five redundant existence queries in a multi-domain search.

v0.6.6 preserves the same exact-first semantics in one query per result family:

- broad candidate match is fetched once;
- exact rank is computed in SQL;
- if exact candidates exist, only exact candidates are serialized;
- otherwise partial matches are serialized.

Real DB query counts before -> after:

```text
Aaron T. Beck          14 -> 9
Beck Cognitive Model   14 -> 9
1897                    13 -> 8
CBT multi-domain        28 -> 23
```

The focused exact-search regression budget is tightened from `<=18` to `<=13` queries.

### 3. Global Search stale-result hardening

The client search previously retained prior result data during the 220ms debounce window and could keep stale results visible after a failed request.

v0.6.6 clears Atlas/DSM result state immediately when a new query begins, clears stale error state when the query changes, and clears result data on non-abort request failures. Aborted requests remain silent.

This prevents a new query from temporarily presenting the previous query's cards as if they belonged to the new input.

### 4. Scientific provenance visibility hardening

`citation_from_model_knowledge` was present in API/Graph payloads, but compact relation cards and Map neighbor cards mainly showed source organization/title. That made the verification boundary less visible in high-level navigation.

v0.6.6 adds a reusable weak-source summary:

```text
ارجاع آرشیوی؛ نیازمند بازبینی مستقل
```

It appears when every source supporting that relation is `citation_from_model_knowledge`.

The Knowledge Map also renders canonical `ReviewStatus` labels rather than raw review-status codes.

A real weak relation used for browser verification:

```text
Paul Salkovskis
  -> Cognitive Model of OCD (Salkovskis)
source: Obsessional-compulsive problems: a cognitive-behavioural analysis
verification_status: citation_from_model_knowledge
review_status: source_checked
```

Browser automation confirmed the warning element exists and is interactive inside the real Graph relation card. The same warning was also present after opening the Psychologist detail Theory tab.

## Graph performance freeze

Real current Graph:

```text
660 nodes
1299 edges
54 edge kinds
365 explicit v0.6 edges
0 v0.6 relation-level source gaps
45 cold build queries
```

Five direct cold Graph builds:

```text
query counts: [45, 45, 45, 45, 45]
min:    ~240.5 ms
median: ~253.3 ms
max:    ~258.2 ms
```

Graph cache verification:

```text
cold: 45 DB queries · ~238.5 ms
hot:   0 DB queries · ~2.84 ms
```

No Graph query count scales per node. Cache invalidation coverage from v0.6.5 remains active for v0.6 entities, relation models, relation-source models and shared SourceReference updates.

## API performance reconfirmed

Real DB list/detail budgets remain stable:

```text
Psychologist list   3 queries
Theory list         3 queries
Timeline list       2 queries
Psychologist detail 13 queries
Theory detail       13 queries
Timeline detail      9 queries
```

## Production browser + HTTP regression

Production Next was started against the real local Django backend.

Full route crawl:

```text
635 / 635 PASS
```

Coverage:

```text
241 Disorder detail pages
148 Concept detail pages
20 Therapy detail pages
35 Technique detail pages
76 Psychologist detail pages
45 Theory detail pages
61 Timeline detail pages
9 core/list/search/map routes
```

Checks rejected:

- non-200 responses;
- `Application error`;
- `Internal Server Error`;
- visible `undefined`;
- visible `NaN`;
- `[object Object]`.

Browser interaction in Chromium headless also verified:

- Global Search input accepts `Aaron T. Beck` and renders a clickable `/psychologists/aaron-t-beck` result;
- Map loads `psychologist:paul-salkovskis`;
- the weak-source warning exists in the Map relation DOM and selecting it traverses to `theory:cognitive-model-ocd-salkovskis`;
- Psychologist detail tab interaction exposes the same weak-source warning in the Theory relation card.

## Database / research integrity

```text
SQLite integrity_check      ok
SQLite foreign_key_check    0 issues
ResearchDataset             2
ResearchRecord              1918
SourceReference             189
Promoted target mappings    1271 · 0 broken
```

Exact archives remain unchanged:

```text
psychology_atlas_research_dataset.json
618107 bytes
sha256 753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0

psychology_atlas_research_dataset_complete___1.json
1281373 bytes
sha256 3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

Promotion dry-run remains conservative and idempotent:

```text
76 Psychologists matched
45 Theories matched
61 Timeline events matched
303 v0.6 relationship records matched/promoted
1 v0.6 relation staging record remains unsupported/unresolved and is not force-promoted
```

## Source registry sanity

Current source registry audit:

```text
189 SourceReference rows
67 citation_from_model_knowledge sources
0 duplicate DOI keys
0 duplicate URL keys
0 duplicate title/year keys
0 malformed DOI values under basic DOI syntax check
0 non-numeric PMID values
0 malformed non-empty HTTP(S) URLs
```

No DOI, PMID, URL, author or date was fabricated in v0.6.6.

## Security/deployment audit

With `DEBUG=0`, a non-default secret, a production host and HTTPS frontend origin, Django `check --deploy` reports only:

```text
security.W005 · SECURE_HSTS_INCLUDE_SUBDOMAINS is not enabled
security.W021 · SECURE_HSTS_PRELOAD is not enabled
```

These remain intentional opt-ins. Enabling either blindly can affect every subdomain or create preload-list consequences, so v0.6.6 does not force them in application code.

The project-local backend virtual environment passes `pip check` with no broken requirements.

## Final automated gates

```text
backend/.venv pip check                    PASS
Python compileall                          PASS
Django system check                        PASS
makemigrations --check --dry-run          PASS · no changes detected
v0.6 scientific release audit             PASS
research archive verifier                 PASS
promotion dry-run                          PASS
full backend suite                         PASS · 128/128
frontend TypeScript                        PASS · frontend 0.6.6
Next.js production build                   PASS · Next.js 16.3.3 · 23/23 generation units
npm audit --audit-level=low                PASS · 0 vulnerabilities
production HTTP crawl                      PASS · 635/635
Chromium interaction audit                 PASS
```

## Schema boundary

v0.6.6 adds no model/schema migration.

The canonical runtime architecture remains:

```text
backend/atlas/views.py
backend/atlas/serializers.py
backend/atlas/urls.py
backend/atlas/management/commands/seed_mvp.py
frontend/lib/types.ts
```

The new `audit_v06_release` management command is release/audit tooling, not a parallel runtime module.

## Final v0.6 boundary

v0.6 is now feature-complete and frozen for the Psychologists + Theories + Timeline scope:

```text
v0.6.1  architecture/models/migrations/provenance
v0.6.2  conservative research promotion/dedupe/aliases
v0.6.3  public knowledge read APIs
v0.6.4  public frontend + Timeline UX
v0.6.5  Knowledge Graph + Global Search integration
v0.6.6  final hardening/performance/scientific-debt visibility/release freeze
```

The next feature release is v0.7: Advanced Branching Clinical Cases + Analytics.

Scientific work intentionally remaining for later review/CMS work:

- strengthen independent verification for 59 weak-only v0.6 entities and 52 weak-only v0.6 relations;
- do not mark those rows `reviewed` without stronger evidence;
- full claim-level scientific review workflow remains a v1.0 concern.

## Git transport note

At the start of v0.6.6, the local repository had no configured Git remote (`git remote -v` returned no entries). The release can be committed and tagged locally, but it cannot be pushed until a real remote URL is configured; no remote is invented or guessed by the release process.
