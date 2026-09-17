# Psychology Atlas v0.7.4 — Personal Case Analytics

Date: 2026-09-17

Status: v0.7.4 release freeze complete; this document is the source record for the final tag and GitHub Release.

## Release goal

v0.7.4 completes the Advanced Case Analytics slice of the v0.7 roadmap by turning immutable, revision-pinned Clinical Case attempt history into authenticated **personal educational analytics**.

The release is deliberately narrow in interpretation. It summarizes the learner's own recorded scenario history and does not introduce population comparison, psychometric scoring, diagnosis, treatment recommendations, therapist-fitness claims, or clinical-competency measurement.

The release is composed of three implementation slices:

- `v0.7.4.1` — Personal Case Analytics Foundation
- `v0.7.4.2` — Persian/RTL Personal Case Analytics UI
- `v0.7.4.3` — Analytics Hardening + v0.7.4 Release Freeze

## Personal analytics API

Authenticated endpoints:

```text
GET /api/case-analytics/overview/
GET /api/case-analytics/cases/<slug>/
```

Both endpoints are personal-only and derive their result from existing `CaseAttempt` and immutable `CaseAttemptEvent` history. No parallel analytics table or second scoring engine is introduced.

The response contract remains:

```text
analytics_version = 1
scope = personal
```

The v0.7.4.3 freeze adds explicit regression coverage that locks the expected v1 response keys so accidental contract drift is caught before release.

## Overview semantics

The overview reports:

- total, completed and in-progress attempts
- completion rate
- average percentage across completed attempts that have a real positive maximum score
- number of started Cases
- total recorded decision count
- per-Case personal summaries ordered by latest activity

A completed attempt with `max_score <= 0` is explicitly unscored. It is not converted into a fabricated percentage and does not enter the average scored-attempt denominator.

## Per-Case analytics semantics

Per-Case detail reports:

- recent attempts, capped at 20
- revision-aware educational dimension aggregation
- reached branch-choice distributions
- reconstructible completed-path groups, capped at 20 groups
- explicit legacy/partial-history counters
- whether the current Case is still runnable

In-progress immutable decisions may contribute to decision, dimension and branch aggregates, but only completed attempts are eligible for completed-path statistics.

## Revision boundaries

Analytics never silently merges scoring meaning across revisions.

Dimension groups include the historical `CaseRevision.version` and immutable snapshot label/description. Branch groups also carry revision identity. Completed path signatures are grouped inside the revision that produced them.

v0.7.4.3 adds a direct two-revision regression fixture proving that identical stable keys or visible choice text from different revisions remain distinct semantic groups.

## Completed-path integrity hardening

The original v0.7.4.1 path builder already used immutable events rather than the mutable current Case graph. v0.7.4.3 tightens the definition of a reconstructible completed path.

A completed attempt is now considered reconstructible only when its immutable event stream is internally complete:

- event state versions start at 0 and advance exactly one step at a time
- each event's before/after state pair is contiguous
- snapshot `step_key`, `outcome` and target semantics are structurally valid, and snapshot `node_kind` matches the immutable event type
- the next event starts on the target stable key recorded by the previous continue event
- a decision event retains a real selected choice and choice text
- a continue event cannot be the final event
- the final event must have `outcome=complete`
- a completion event cannot point to another target step
- the final immutable event count must agree with the attempt's recorded `state_version`

If any of those historical guarantees are missing, analytics does **not** repair, infer or backfill the path. The attempt remains visible in overall history and increments:

```text
legacy.completed_attempts_without_reconstructible_path
```

This preserves history without presenting corrupted or partial data as a real completed route.

## Legacy and partial-history policy

Historical compatibility remains explicit:

- `rubric_version=0` attempts remain readable without invented multidimensional scoring
- malformed or missing historical dimension snapshots do not crash analytics
- a decision without a usable dimension snapshot increments the unscored-dimension counter
- pre-stateful completed attempts remain visible but cannot fabricate completed paths
- duplicate in-progress rows are reported as stored history; analytics does not silently delete or normalize them

This release is read-only with respect to analytics history.

## Ownership and inactive Cases

Analytics remains strictly user-scoped.

- another user's attempts never appear in overview or detail
- an inactive Case with history owned by the authenticated learner remains readable
- an inactive Case with no owned history returns the same unavailable/not-found boundary and does not disclose another user's history
- a runnable Case with no owned history returns the explicit `case_history_not_found` response code
- a genuinely missing/unavailable Case uses `case_not_found`

## Query and response bounds

The release keeps analytics query counts independent of attempt volume:

```text
overview authenticated request: <= 3 queries
per-Case detail request:         <= 4 queries
recent_attempts:                 <= 20 rows
completed_path groups:           <= 20 groups
```

A v0.7.4.3 regression fixture creates 40 completed attempts with 80 immutable events and verifies that the query budgets remain bounded, the aggregate counts remain correct, and the recent-attempt cap remains enforced.

## Persian/RTL frontend

Routes:

```text
/case-analytics
/case-analytics/[slug]
```

The frontend renders backend-owned percentages and grouping only. It does not reconstruct Case paths or authoritative scores in React.

The analytics surface includes:

- overview KPIs
- per-Case summaries
- revision-aware educational dimensions
- reached branch-choice distributions
- completed-path history
- recent attempts
- legacy compatibility notice
- explicit educational/non-clinical disclaimer

## Authentication hardening

v0.7.4.3 closes two authentication edge cases found during release QA.

First, analytics already redirected unauthenticated users through `?next=...`, but the login page previously allowed a return path only for `/cases/<slug>`. The login allowlist now also accepts only these analytics shapes:

```text
/case-analytics
/case-analytics/<safe-slug>
```

The allowlist stays path-pattern based and does not accept arbitrary external URLs, preserving the existing open-redirect boundary.

Second, when an authenticated request has no valid access token and refresh also fails, the shared API client now raises `ApiError(401)` instead of a generic `Error`. Analytics pages can therefore consistently route the user back through login rather than treating token expiry as an ordinary server failure.

## Accessibility and narrow-screen hardening

The v0.7.4.3 UI pass adds:

- semantic `progressbar` roles and values for percentage meters
- screen-reader-only status text for loading state
- retry without unnecessary full-page reload
- long historical Persian/technical text wrapping
- additional <=380px layout rules
- reduced-motion browser verification

Real browser validation at `320 x 800` confirmed:

```text
overview clientWidth=320 / scrollWidth=320
per-Case detail clientWidth=320 / scrollWidth=320
horizontal overflow: 0
first keyboard Tab target: skip-link
prefers-reduced-motion: reduce
```

Desktop Chromium QA also verified the overview and a real Case analytics detail page using actual persisted stateful attempt history.

## QA data cleanup

The final authenticated browser fixture used one temporary QA user with one completed attempt:

```text
before cleanup: 1 attempt / 3 events / 3 answers
after cleanup:  user=0 / attempts=0 / events=0 / answers=0
```

Temporary screenshots under `.qa/` were removed before release commit and the temporary backend/frontend servers were stopped.

## Schema and scientific-content boundary

v0.7.4.3 introduces no model or migration changes.

The release does not alter:

- Case scoring scale
- seeded Clinical Case scientific content
- therapy/psychologist/theory/timeline source data
- scientific review statuses
- research archive records

The v0.6 scientific audit remains unchanged at release freeze:

```text
active provenance gaps:    0
weak-only entities:       59
weak-only relations:      52
weak-only reviewed rows:   0
timeline precision issues: 0
```

These weak archival-source rows remain visible scientific-review debt and are not upgraded by v0.7.4.

## Research archive integrity

The exact archived research corpora remain unchanged:

```text
psychology_atlas_research_dataset.json
762 records / 618107 bytes
sha256 753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0

psychology_atlas_research_dataset_complete___1.json
1156 records / 1281373 bytes
sha256 3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9

Total ResearchRecord rows: 1918
```

## Runtime Case integrity

The release-time read-only Case audit reports:

```text
cases=6
revisions=12
dimensions=17
attempts=0
events=0
answers=0
failures=0
```

SQLite release checks also report:

```text
integrity_check=ok
foreign_key_check=0
in_progress_without_step=0
duplicate_in_progress_groups=0
```

## Local release validation

Verified on the v0.7.4.3 release-freeze branch before PR closure:

```text
Focused v0.7.4.3 analytics hardening tests: 11/11 PASS
Full backend suite:                          179/179 PASS
Django system check:                        PASS
Migration drift check:                      PASS / no changes detected
Case graph/state/scoring audit:             PASS
SQLite integrity + FK audit:                PASS
Python compileall:                          PASS
pip check:                                  PASS
v0.6 scientific release audit:             PASS / unchanged
Research archive verifier:                  PASS / 2 datasets / 1918 records
Frontend package version:                   0.7.4
Frontend dependency install:                npm ci PASS
Frontend TypeScript:                        PASS
Next.js production build:                   PASS / 24/24 generation units
Next.js validated version:                  16.3.5
npm audit --audit-level=low:                0 vulnerabilities
Desktop authenticated Chromium QA:          PASS
320px reduced-motion Chromium QA:           PASS / no horizontal overflow
Temporary QA cleanup:                       PASS
```

No schema migration is required for v0.7.4.

## Release boundary

The v0.7.4 tag/release must be created only after the release PR is merged and all required GitHub CI, CodeQL, dependency-review and repository-hygiene gates are green on the final branch/main commit.

The release tag must point to the final merged `main` commit, not to the feature-branch pre-merge SHA.

## Next roadmap slice

After v0.7.4 is frozen, the next planned feature release is:

```text
v0.8 — Study Mode + Exam Planning + Advanced Recommendations
```

That next release should treat the v0.7 Clinical Case attempt/scoring/analytics history as a stable input rather than reopening its core state or analytics contracts without an explicit new version.
