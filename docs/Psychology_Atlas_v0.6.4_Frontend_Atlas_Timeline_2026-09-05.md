# Psychology Atlas v0.6.4 — Frontend Psychologists, Theories & Timeline

Date: 2026-09-05

## Release boundary

v0.6.4 is the frontend/UX slice of the v0.6 Psychologists + Theories + Timeline roadmap. It consumes the public read-only APIs completed in v0.6.3 and does not expand the canonical backend schema, research-promotion rules, global search, or Knowledge Graph.

The release adds three public atlas surfaces and their detail routes:

```text
/psychologists
/psychologists/[slug]
/theories
/theories/[slug]
/timeline
/timeline/[slug]
```

The existing graph remains intentionally unchanged until v0.6.5. No Psychologist, Theory, or Timeline node is presented as graph-visible in this release.

## Data contracts used

The frontend uses the canonical v0.6.3 endpoints:

```text
GET /api/psychologists/
GET /api/psychologists/<slug>/
GET /api/theories/
GET /api/theories/<slug>/
GET /api/timeline/
GET /api/timeline/<slug>/
```

Frontend types were added to the existing canonical `frontend/lib/types.ts`; no parallel versioned type module was created.

Rich source metadata exposed by v0.6.3 is represented in the shared `SourceReference` type:

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

Entity-level source links preserve their `role`, while relation-level sources stay attached to the exact relation that carries them.

## Scientific display policy

### Review state

The UI does not treat `source_checked` as final scientific review.

Display semantics:

```text
unreviewed     -> بازبینی‌نشده
source_checked -> دارای منبع؛ بازبینی نهایی نشده
reviewed       -> بازبینی علمی ثبت‌شده
```

### Source verification state

Source verification metadata is also not flattened into a single “verified” badge. In particular:

```text
citation_from_model_knowledge -> ارجاع آرشیوی؛ نیازمند بازبینی مستقل
verified                      -> راستی‌آزمایی‌شده
web_verified_doi_and_pmid     -> DOI و PMID راستی‌آزمایی‌شده
web_verified_doi              -> DOI راستی‌آزمایی‌شده
search_verified               -> راستی‌آزمایی‌شده با جست‌وجو
search_context_verified       -> زمینه منبع راستی‌آزمایی‌شده
```

This distinction is important because the current canonical source registry contains both web/institutionally verified records and archival citations retained from source material.

### Bilingual gaps

The UI never manufactures a Persian translation when only English content exists in the runtime record.

Policy:

1. display Persian content when the Persian field is populated;
2. otherwise display the source English text with explicit LTR direction and a label that the available source text is English;
3. if neither language is populated, display a neutral missing-data statement;
4. never turn a missing biography, role, nationality, contribution, theory proposition, or historical note into model-generated prose.

This is particularly relevant for the current Psychologist corpus, where many canonical identities have relations and provenance but no direct `summary_fa` or `summary_en` field.

## Psychologists Atlas

### Landing explorer

`/psychologists` fetches the current active canonical catalog and renders a client-side explorer using the existing RTL dark design language.

Explorer capabilities:

- Persian/English/alias search;
- search over available role, nationality and summary text;
- review-state filter;
- dynamically derived birth-century filter;
- sorting by total explicit connections, Timeline events, birth year or name;
- card and compact views;
- relation counts for Theory, Concept, Therapy and Timeline;
- aliases shown separately from the canonical name;
- explicit missing-summary messaging instead of generated biography text.

### Psychologist detail

`/psychologists/[slug]` contains tabs for:

```text
Overview
Theories
Concepts
Therapies
Timeline
Related Psychologists
Sources
```

The page preserves historical attribution semantics such as `developed`, `co_developed`, `proposed`, `researched_or_developed`, `contributed_to`, and `majorly_associated_with` rather than reducing them to a generic creator badge.

Relation cards show:

- the canonical target entity;
- relationship type;
- relation review status;
- Persian relation explanation when present, otherwise explicit English fallback;
- source count and source organizations from the exact relation.

When Timeline links exist, the profile links to a server-filtered Timeline view using `?psychologist=<slug>`.

## Theory Atlas

### Landing explorer

`/theories` provides:

- bilingual/alias search;
- dynamic domain filter based on real runtime values;
- review-state filter;
- UI grouping of `modern_status` into active/influential, historical/foundational, and other groups for discovery only;
- sorting by total explicit connections, connected Psychologists, Timeline events, or name;
- card and compact views;
- direct display of humanized domain/period/status metadata.

The detail page continues to expose the original/raw status value. The grouping does not replace or reinterpret the source semantics.

### Theory detail

`/theories/[slug]` contains:

```text
Overview
Psychologists
Concepts
Therapies + Techniques
Related Theories
Timeline
Sources
```

Overview fields include the source-backed runtime fields when available:

- core proposition;
- historical context;
- key propositions;
- applications;
- criticisms;
- limitations;
- historical importance.

`modern_status` is explicitly described as metadata, not a score of truth, validity, efficacy, or clinical superiority.

Theory-to-Therapy and Theory-to-Technique relations are presented as historical/theoretical relations, never as personalized treatment recommendations.

## Psychology Timeline

### Timeline explorer

`/timeline` is not a generic card grid. It renders a chronological stream grouped by decade with an explicit date column and timeline nodes.

Filters include:

- bilingual/title/category search;
- category;
- relation presence by Psychologist, Theory, Therapy, Technique or Concept;
- review status;
- chronological ascending/descending order.

Each event shows only explicit cross-domain link counts returned by the API.

### Server-side relation scope

The route accepts the canonical API relation parameters:

```text
/timeline?psychologist=<slug>
/timeline?theory=<slug>
/timeline?therapy=<slug>
/timeline?technique=<slug>
/timeline?concept=<slug>
```

These filters are applied server-side before rendering. A visible scope banner shows the active relation scope and provides an explicit “exit scoped view” action so the user is never unaware that the Timeline has been narrowed.

Real runtime smoke during implementation confirmed:

```text
all active Timeline events       61
Aaron T. Beck scoped events       5
Beck Cognitive Model events       2
```

### Date precision

Timeline serialization and UI preserve the backend precision model:

```text
exact_date
year
year_range
approximate_year
unknown
```

The UI never converts a year-only record into January 1. The current promoted runtime contains 61 year-precision events spanning 1879–2026; their `exact_date` stays null.

### Timeline detail

`/timeline/[slug]` includes:

- prominent precision-aware date display;
- title and bilingual description;
- raw `date_text` visibility;
- explicit date model fields in the overview;
- previous/next chronological navigation;
- tabs for Psychologists, Theories, Therapy/Technique, Concepts and Sources;
- relation role and relation-level provenance.

The detail route starts its independent detail/list fetches in parallel. The list fetch is used only to derive neighboring events and fails independently without breaking the event detail page.

## Shared scientific UI components

A shared `frontend/components/ScientificMeta.tsx` module centralizes:

- scientific review labels;
- bilingual fallback behavior;
- rich SourceReference display;
- source verification labels;
- relation-source summaries;
- Persian number formatting;
- non-semantic humanization of underscore codes.

This prevents the three new atlas domains from developing inconsistent scientific-status semantics.

## Navigation and Home integration

The global navigation now recognizes:

```text
/psychologists
/theories
/timeline
```

They appear in the Explore group and context rail without expanding the already crowded primary navigation row.

Detail context labels were added for:

- Psychologist profile;
- Theory profile;
- historical event.

Home now loads independent overview/domain counts with `Promise.allSettled`, so one unavailable API does not suppress all other home content.

Home adds a dedicated strip for the current counts of Psychologists, Theories and Timeline events and expands the learning rail to include all three new domains.

The home copy explicitly calls the map the “current Knowledge Graph” because v0.6.4 does not yet integrate the new v0.6 domains into graph/search.

## Performance and rendering decisions

- landing pages fetch one bounded catalog request each (`page_size=300`, below the existing AtlasPagination max);
- filtering and sorting are local for the current small catalog sizes (76 / 45 / 61);
- search input uses `useDeferredValue` to avoid coupling typing directly to expensive filter/sort work;
- detail fetches remain server-side;
- Timeline detail starts independent fetches in parallel;
- Home uses `Promise.allSettled` instead of sequential retry waterfalls;
- no new client-side global state or parallel API abstraction was introduced.

## Responsive behavior

The new UX extends the existing dark RTL design system rather than introducing a separate visual system.

Desktop:

- two-column entity cards;
- multi-column metric strips;
- decade + event-axis Timeline;
- sticky content tabs;
- rich source cards with provenance audit column.

Tablet/mobile:

- atlas headers collapse to one column;
- filters collapse from multi-column to two-column and then one-column;
- cards become single-column;
- metrics collapse to two/three columns;
- tabs become horizontally scrollable;
- Timeline axis becomes a single-column event stream;
- source cards and previous/next navigation stack vertically.

## Validation performed

Implementation-time checks:

```text
TypeScript typecheck                    PASS
Next.js production build               PASS
Next route generation                   PASS · 23 static-generation units
SSR HTTP route smoke                    PASS
Home                                    200
Psychologists landing                   200
Aaron T. Beck detail                    200
Theories landing                        200
Beck Cognitive Model detail             200
Timeline landing                        200
Pavlov 1897 event detail                200
Timeline relation-scoped route          200
visible undefined / NaN audit           PASS
new-domain Graph/Search boundary scan   PASS
```

Direct Playwright visual inspection could not be executed in the local MCP environment because optional Playwright support is not installed. The browser attempt was made and failed with the environment-level `playwright_not_installed` capability error; no project dependency was changed to work around that tool limitation.

Final release gates completed after versioning to 0.6.4:

```text
frontend TypeScript typecheck          PASS · 0.6.4
frontend production build             PASS · 0.6.4
production HTTP content smoke          PASS · 8/8 audited routes
npm audit --audit-level=low            PASS · 0 vulnerabilities
backend full regression                PASS · 120/120
Django system check                    PASS
makemigrations --check --dry-run       PASS · no changes detected
Python compileall                      PASS
pip check                              PASS · no broken requirements
research archive verifier              PASS · 2 datasets / 1,918 records / exact hashes
v0.6 runtime inventory                 76 Psychologist / 45 Theory / 61 TimelineEvent
Knowledge Graph freeze                 478 nodes / 934 edges / 18 queries / 33 edge kinds
new v0.6 Graph node types              none
```

The generated `frontend/next-env.d.ts` change from the build was restored, so release diff contains only intentional source/version/documentation changes. Git diff/status hygiene is checked immediately before the release commit.

## Deliberately deferred to v0.6.5

- Psychologist nodes in Knowledge Graph;
- Theory nodes in Knowledge Graph;
- Timeline nodes/edges in Knowledge Graph where product semantics justify them;
- Psychologist/Theory/Timeline integration into Global Search;
- graph cache/signal expansion for the new models;
- pathfinding involving new v0.6 domains;
- graph/query-budget re-freeze after the new node/edge families are introduced.

v0.6.4 therefore completes the public frontend Atlas and Timeline experience while keeping the v0.6.5 integration boundary explicit and auditable.
