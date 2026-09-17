# Psychology Atlas v0.7.4.1 — Personal Case Analytics Foundation

Date: 2026-09-16

Status: development slice complete; official public release baseline remains v0.7.3 until the full v0.7.4 analytics release is frozen.

## Goal

v0.7.4.1 establishes the backend analytics contract for Clinical Cases without creating a second state machine or a second scoring system. Analytics is computed from the existing history-safe primitives introduced in v0.7.1–v0.7.3:

- `CaseAttempt`
- immutable `CaseAttemptEvent`
- revision-pinned `CaseRevision`
- event snapshot metadata
- existing scalar Case score
- revision-owned scoring dimensions where `rubric_version >= 1`

The slice is personal-only and educational-only. It does not expose population analytics, cross-user comparisons, normative ranking, clinical competence scoring, diagnosis or treatment recommendations.

## API surface

Authenticated endpoints:

```text
GET /api/case-analytics/overview/
GET /api/case-analytics/cases/<slug>/
```

No user identifier is accepted from the client. Both endpoints scope all attempt/event queries to `request.user`.

### Overview contract

The overview response contains:

- `analytics_version=1`
- `scope=personal`
- generated timestamp
- total/completed/in-progress attempt counts
- completion rate
- average percentage across completed attempts that have a positive max score
- count of scored completed attempts
- distinct Case count
- reached decision count
- per-Case summaries
- educational-only disclaimer

Per-Case summary rows contain current Case identity plus latest attempted revision metadata, attempt counts, completion rate, completed-attempt score summary, reached decision count and last activity timestamp.

### Per-Case detail contract

The per-Case response contains:

- attempt summary
- total reached decision count
- revision-aware dimension aggregates
- revision-aware reached branch-choice distributions
- grouped completed paths
- up to 20 recent attempts
- explicit legacy/rubric-v0 counters
- educational-only disclaimer

A Case with no owned attempt history returns 404 for that user, even if another user has attempts for the same Case.

## Analytics semantics

### Personal scope

All analytics is derived only from the authenticated user's own attempts/events. There is no population denominator, percentile, leaderboard or cross-user aggregation.

### Completion rate

Completion rate is descriptive:

```text
completed attempts / all personal attempts for the selected scope
```

No interpretation beyond that product metric is implied.

### Completed-attempt score summary

Each completed attempt with `max_score > 0` contributes its own `score / max_score` percentage. The API returns the arithmetic mean of those attempt percentages plus the number of scored completed attempts included.

This value is an educational product summary, not a validated scale and not comparable to professional competence.

### Dimension aggregation

Dimension aggregation uses only immutable decision-event snapshots and only when the attempt revision has `rubric_version >= 1`.

Grouping key includes:

- Case revision number
- dimension key
- dimension label
- dimension description

This prevents silently merging dimension definitions across historical Case revisions.

For each group the API returns:

- score / max score
- percentage when max score is positive
- reached decision count
- distinct attempt count
- snapshot sort order
- descriptive `needs_review` flag when reached score is below reached max score

`rubric_version=0` attempts never fabricate multidimensional performance.

### Branch distribution

Branch distribution is based only on decision events actually reached by the user. It is grouped by revision and decision `step_key`; each reached choice is identified by preserved `selected_choice_id` while immutable snapshot text remains the historical display label.

For each reached choice the API returns:

- selection count
- percentage within that reached decision node
- accumulated score / max score
- descriptive score percentage when defined

Unvisited branches are not inserted as zero-count failures.

### Completed paths

Path groups are built only from completed attempts with reconstructible event snapshots. In-progress paths are deliberately excluded from completed-path statistics.

Path identity includes revision number plus the ordered sequence of reached event types, step keys, selected choice IDs, snapshot choice text and target keys. The API returns at most 20 path groups, sorted by frequency and recency.

Historical completed attempts with missing or non-reconstructible stateful event history remain valid but are counted explicitly in `completed_attempts_without_reconstructible_path` instead of receiving a fabricated path.

### In-progress attempts

Immutable decisions already committed in an in-progress attempt may contribute to:

- reached decision count
- dimension aggregation
- branch-choice distribution

They do not contribute to completed-path groups or completed-attempt score averages.

## Legacy and malformed-history handling

v0.7.4.1 preserves history rather than reinterpreting it.

- `rubric_version=0` attempts remain readable.
- rubric-v0 decision events increment an explicit legacy counter and do not create dimension aggregates.
- malformed/missing dimension snapshots are counted as unscored dimension decisions for rubric-enabled attempts.
- malformed legacy snapshot description/sort-order/step-title values are normalized defensively instead of crashing the analytics response.
- inactive Cases remain available in personal analytics when owned historical attempts exist.

## Query and response bounds

Regression coverage verifies bounded query counts independent of attempt count:

```text
personal overview: <= 3 authenticated-request queries
per-Case detail:   <= 4 authenticated-request queries
```

The current design uses bounded query count rather than one query per attempt/event.

Response bounds:

```text
recent_attempts:       max 20
completed_path_groups: max 20
```

No new analytics table or materialized cache is introduced in this slice.

## Schema boundary

No database migration is required for v0.7.4.1. Existing v0.7.1–v0.7.3 models already contain the canonical analytics inputs.

`makemigrations --check --dry-run` reports no changes detected.

## Privacy and product-safety boundary

Analytics endpoints require authentication and accept no target-user parameter. Cross-user history is neither returned nor aggregated.

Every analytics response includes the product disclaimer that the metrics describe only performance in the user's educational scenario history and are not:

- clinical competence measures
- diagnostic results
- treatment-quality measures
- therapist-fitness assessments
- normative rankings against other people

## Regression coverage

Focused v0.7.4.1 analytics tests: **10/10 PASS**

Coverage includes:

1. authentication requirement
2. personal-only overview aggregation
3. dimension / branch / completed-path detail aggregation
4. cross-user ownership isolation
5. inactive owned Case history preservation
6. explicit rubric-v0 legacy behavior
7. malformed legacy snapshot hardening
8. same-text choices remain distinct by preserved choice identity
9. pre-stateful completed history remains readable without fabricated paths
10. bounded query counts

Full backend suite: **168/168 PASS**

Additional validation:

```text
Django system check:            PASS
Migration drift check:          PASS — no changes detected
Case graph/state audit:         PASS — failures=0
Python compileall:              PASS
pip check:                      PASS — no broken requirements
SQLite integrity_check:         ok
SQLite foreign_key_check:       0
in_progress_without_step:       0
Frontend typecheck:             PASS
Frontend production build:      PASS — 23/23 generation units
npm audit --audit-level=low:     0 vulnerabilities
v0.6 scientific audit:          PASS
Research archive verification:  PASS — 2 datasets / 1918 records / exact hashes
```

The v0.6 scientific baseline remains unchanged:

```text
active provenance gaps: 0
weak-only entities:     59
weak-only relations:    52
weak-only reviewed:     0
timeline precision:     0 issues
```

Research archive hashes remain:

```text
753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0
3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

## Deliberately deferred to v0.7.4.2

v0.7.4.1 does not build the analytics dashboard UI. v0.7.4.2 should consume this backend contract and add Persian/RTL personal Case analytics presentation, responsive/mobile behavior and accessible visualizations without duplicating aggregation logic in the frontend.

## Deliberately deferred beyond v0.7.4.2

Population analytics, cross-user cohorts, research analytics, instructor dashboards and normative comparison are not implied by this foundation and require separate product/privacy/scientific decisions before implementation.
