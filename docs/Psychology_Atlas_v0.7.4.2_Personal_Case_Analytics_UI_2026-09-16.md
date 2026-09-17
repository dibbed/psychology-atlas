# Psychology Atlas v0.7.4.2 — Persian/RTL Personal Case Analytics UI

Date: 2026-09-16

Status: development slice complete; official release baseline remains v0.7.3 until v0.7.4.3 hardening/freeze.

## Goal

v0.7.4.2 turns the personal-only analytics API introduced in v0.7.4.1 into a usable Persian/RTL learning surface. The frontend is intentionally a consumer of backend-owned analytics semantics. It does not rebuild dimension, branch, score or path aggregation in React.

## Routes

Authenticated personal routes:

```text
/case-analytics
/case-analytics/[slug]
```

Unauthenticated access redirects through the existing validated internal `next` flow, for example:

```text
/login?next=%2Fcase-analytics
```

## Overview page

`/case-analytics` renders the v0.7.4.1 personal overview payload:

- total attempts
- completed and in-progress attempts
- completion rate
- average score percentage for completed scored attempts
- number of Cases started
- number of reached decisions
- per-Case personal summaries ordered by backend recency
- explicit educational/non-clinical interpretation boundary

Each Case row shows backend-provided completion and score summaries and links to its personal detail page.

The UI does not infer missing percentages. `null` remains an explicit unavailable state.

## Per-Case detail page

`/case-analytics/[slug]` renders only owned history returned by the backend.

### Educational dimensions

For each backend dimension group the UI shows:

- revision number
- historical dimension label and description
- score / max score
- backend-computed percent
- reached decision count
- contributing attempt count
- review emphasis when `needs_review` is true

The progress bar is a visualization of the backend percentage, not a new frontend scoring formula.

### Reached branch choices

For every reached decision point the UI shows:

- revision number
- immutable step key/title from analytics history
- reached choice text
- selection count
- backend selection percentage
- backend score percentage

Choice identity remains backend-owned. The frontend does not merge choices by display text.

### Completed paths

Only reconstructible completed path groups returned by the backend are rendered. Each path displays its ordered historical steps and recorded choice text.

No path is reconstructed from the current mutable Case graph.

### Recent attempts

The bounded recent-attempt list shows:

- completed/in-progress state
- revision number
- attempt identifier
- decision and event counts
- score/max and backend percentage
- latest relevant timestamp

### Legacy compatibility

When legacy counters are non-zero, a dedicated compatibility notice makes the boundary explicit:

- rubric v0 attempts
- unscored dimension decisions
- completed attempts without a reconstructible path

The UI does not fabricate dimensions or paths to make old history look complete.

## Product integration

Case Analytics is reachable from:

- Personal navigation
- `/dashboard`
- `/cases`
- a completed Case attempt through `CaseRunner`

The navigation context recognizes `/case-analytics/[slug]` as a Case analytics detail page.

## Frontend types

`frontend/lib/types.ts` now includes typed contracts for:

- `CaseAnalyticsAttemptSummary`
- `CaseAnalyticsCaseSummary`
- `CaseAnalyticsOverview`
- `CaseAnalyticsDimension`
- `CaseAnalyticsBranchChoice`
- `CaseAnalyticsBranch`
- `CaseAnalyticsPathStep`
- `CaseAnalyticsCompletedPath`
- `CaseAnalyticsRecentAttempt`
- `CaseAnalyticsDetail`

These types mirror the v0.7.4.1 API payload and keep the backend as the semantic authority.

## Loading, empty and error states

The analytics pages include explicit states for:

- initial loading
- API error and retry
- authenticated overview with no Case history
- per-Case 404/no-owned-history
- legacy partial history

Authentication is checked client-side with the existing refresh-aware token utilities before making personal API calls.

## Responsive design

The UI extends the existing Psychology Atlas dark/RTL design system rather than introducing a separate dashboard visual language.

Desktop detail uses a two-column analytical section for dimensions and recent attempts, followed by full-width branch and path panels.

Responsive breakpoints collapse the surface progressively:

- <=900px: overview KPI becomes 2 columns; detail becomes one column; Case rows stack
- <=620px: KPI becomes one column; branch choices, attempts, path cards and notices collapse without horizontal scrolling

## Browser QA

Real stateful Case data was created through the product UI using temporary QA accounts.

Verified surfaces:

```text
Desktop viewport: 1280px wide
Mobile viewport:  390 x 844
Overview page:     PASS
Per-Case detail:   PASS
Auth redirect:     PASS
Case completion -> analytics data: PASS
```

Inspected visual points:

1. navigation and Personal context state
2. title hierarchy and CTA placement
3. KPI strip density and responsive stacking
4. per-Case summary row alignment
5. dimension meters and text wrapping
6. branch-choice distribution bars
7. completed-path vertical flow
8. recent-attempt responsive collapse
9. educational disclaimer visibility
10. mobile horizontal-overflow/clipping check

No material clipping or horizontal overflow remained in the audited desktop/mobile renders.

All temporary QA users and their user-owned attempt/activity history were deleted after browser verification. Screenshot artifacts were also removed from the repository before commit.

## Safety boundary

The UI preserves the backend disclaimer and must not imply:

- diagnosis
- treatment guidance or treatment quality
- psychometric validation
- normative ranking against other learners
- therapist fitness
- professional or clinical competence

The product summarizes educational scenario activity for the authenticated learner only.

## Schema and scientific content

v0.7.4.2 is frontend-focused:

- no model changes
- no migration
- no Case scoring changes
- no seed content changes
- no scientific source/provenance changes

The v0.7.4.1 backend analytics contract remains authoritative.

## Validation baseline

Final validation for this slice is recorded in `BUILD_MANIFEST.json` and includes:

- frontend TypeScript typecheck
- Next.js production build including `/case-analytics` routes
- npm vulnerability audit
- full backend regression
- Django check
- Case graph/state audit
- migration drift check
- SQLite integrity checks
- repository diff/manifest validation
- real desktop/mobile browser QA

## Next slice

v0.7.4.3 — Analytics Hardening + Release Freeze.

That slice should focus on final edge-case/performance/E2E hardening and freeze the complete v0.7.4 analytics release rather than adding another analytics architecture.
