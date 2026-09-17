# Psychology Atlas v0.7.5 — Clinical Case Integrity Patch

Date: 2026-09-18  
Release line: v0.7 final patch  
Previous public release: v0.7.4 — Personal Case Analytics  
Next planned feature line: v0.8 — Study Mode + Exam Planning + Advanced Recommendations

## Purpose

v0.7.5 is the final planned patch for the v0.7 Clinical Case line. It was produced after a post-release audit of the complete v0.7 stack rather than as a new feature slice. The audit covered revision ownership, the legacy linear compatibility endpoint, stateful attempt invariants, event immutability, multidimensional educational scoring boundaries, personal analytics reconstruction, authentication recovery, browser behavior, migration history, fresh-install behavior, database integrity and SQLite concurrency.

The patch deliberately does **not** add new psychology content, a new scoring model, a new analytics contract, or a new roadmap feature. It closes correctness and integrity gaps discovered after v0.7.4 while preserving the existing educational-only semantics.

## Fixed integrity issues

### 1. CaseRevision is the authoritative content snapshot

`ClinicalCase` remains the stable identity container for slug and cross-domain identity, but current public Case metadata now consistently comes from the owned published `current_revision`:

- title
- patient summary
- educational objective
- difficulty
- primary disorder

The Case list/detail serializers were hardened accordingly. Public availability also validates that the current revision belongs to the same Case, that the entry step belongs to that same revision and Case, and that the entry step is active.

This prevents mutable `ClinicalCase` metadata from silently overriding the revision snapshot that attempts and historical state are supposed to preserve.

### 2. Legacy linear submit side effects are revision-safe

The compatibility endpoint `/api/cases/<slug>/submit/` already created attempts pinned to a `CaseRevision`, but progress and `StudyActivity.disorder` side effects were still derived from mutable `ClinicalCase.primary_disorder`.

v0.7.5 binds those side effects to `attempt.revision.primary_disorder` instead. A regression fixture explicitly creates a mismatch between the mutable Case disorder and the revision disorder and verifies that only the revision disorder receives progress/activity side effects.

### 3. Disorder -> Case reverse integration uses the same authority

Disorder detail `study_resources.cases` previously came from the mutable reverse `ClinicalCase.primary_disorder` relationship. This could disagree with the public Case API after a revision changed the Case's primary disorder/title/difficulty.

The reverse integration now prefetches current published Case revisions and serializes Case title/difficulty from those revision snapshots. A Case appears under the revision primary disorder rather than a stale mutable Case relation.

### 4. Public Case runnability is structurally owned

A public Case is available only when all of these are true:

- `ClinicalCase.is_active == True`
- a `current_revision` exists
- `current_revision.case_id == ClinicalCase.id`
- revision status is `published`
- an entry step exists
- the entry step is active
- `entry_step.revision_id == current_revision.id`
- `entry_step.case_id == ClinicalCase.id`
- revision primary disorder is either null or active

This closes malformed-FK/state cases that were possible through direct database mutation even though ordinary application writes were expected to be valid.

### 5. Analytics path reconstruction cross-checks snapshots against immutable FKs

v0.7.4.3 already rejected many malformed histories, but the post-release audit showed that a coherently altered snapshot chain could still appear internally plausible if multiple snapshot fields were changed together.

v0.7.5 reconstructs a completed path only if snapshot semantics and stored event FKs agree on:

- revision entry step stable key
- event step stable key
- event/node kind mapping
- outcome
- actual next-step stable key
- choice presence rules
- contiguous state versions
- previous-target -> next-event step chaining
- terminal completion position

Corrupted or partial histories remain visible in attempt totals and compatibility counters but are not silently repaired or emitted as trusted completed paths.

### 6. CaseAttemptEvent model validation is stricter

`CaseAttemptEvent.clean()` now rejects:

- `decision` events on non-decision nodes
- `advance` events on non-information nodes

The existing terminal semantics remain enforced by the event flow and graph audit.

### 7. `audit_case_graphs` now covers history-state integrity

The graph audit was expanded beyond structural Case graph ownership. It now checks attempt/event state including:

- first event matches revision entry step
- untouched in-progress attempt starts at revision entry
- state versions are contiguous
- every event advances exactly one state version
- each continue event targets the following recorded event step
- completion cannot be followed by another event
- completed attempt must have no current step
- completed attempt must have `completed_at`
- in-progress attempt must not have `completed_at`
- completed attempts with event history must finish in a completion event
- in-progress attempts must point to the latest event target
- event step belongs to attempt revision
- event type matches actual step node kind
- snapshot step key matches actual step
- snapshot node kind matches actual event type
- snapshot outcome matches actual event outcome
- snapshot target matches actual `next_step`
- decision snapshots contain choice text
- non-decision snapshots do not fabricate choice text

The audit is read-only. It reports corruption and does not rewrite history.

### 8. Recent analytics attempts use latest activity ordering

Per-Case analytics `recent_attempts` now sort by `updated_at` rather than `created_at`. This makes "recent" reflect the latest interaction/completion activity rather than only the time the attempt was first opened.

## Concurrency hardening

### Database invariant

Migration:

`backend/atlas/migrations/0027_v075_case_attempt_concurrency_guard.py`

adds a conditional unique constraint:

- fields: `(user, case)`
- condition: `status = in_progress`
- constraint name: `uq_case_attempt_user_case_in_progress`

The database therefore enforces the product invariant that one learner can have at most one active attempt for the same Case.

### Historical duplicate preflight

Before adding the constraint, migration 0027 scans for existing duplicate in-progress `(user, case)` groups.

If duplicates exist, migration stops with an explicit error and a bounded sample of affected user/case/count tuples. It does **not**:

- delete an attempt
- merge attempts
- choose a winner
- rewrite status
- fabricate completion

A migration audit created two historical duplicate active attempts on schema 0026 and verified:

- migration 0027 fails intentionally
- both duplicate rows remain present afterward
- no silent repair occurs

### SQLite start/resume race

SQLite does not provide PostgreSQL-style row-level `SELECT ... FOR UPDATE` behavior. Concurrent attempt starts could therefore produce `database is locked` even though duplicate rows were not ultimately persisted.

v0.7.5 configures Django's SQLite backend with `transaction_mode=IMMEDIATE` so write transactions acquire write intent at transaction start instead of entering a deferred read→write lock-upgrade race. A 10-second SQLite busy timeout and a bounded SQLite-only retry remain as defensive fallback around start/resume. Combined with the database unique constraint, two identical concurrent starts converge on one shared in-progress attempt.

Final stress regression:

- 25 rounds per test run
- 2 simultaneous start calls per round
- 5 consecutive complete stress-test runs
- exactly one created attempt per round
- both callers receive the same attempt id
- zero leaked SQLite lock errors
- zero duplicate active attempts

### SQLite decision race and idempotency

The same SQLite writer race could occur when two identical decision submissions reached the same attempt concurrently.

Decision advancement runs under the same SQLite `IMMEDIATE` transaction mode and bounded retry fallback. If a competing transaction commits the same immutable event first, the losing caller re-reads the event and returns it as an exact idempotent replay only when:

- same attempt
- same step
- same `state_version_before`
- same selected choice

Final stress regression:

- 25 rounds per test run
- 2 simultaneous identical decisions per round
- 5 consecutive complete stress-test runs
- one immutable event
- one immutable answer
- one score application
- one state-version increment
- both callers converge on the same event id
- exactly one call reports idempotent replay
- zero SQLite lock leakage

PostgreSQL retains its row-lock behavior and the same database uniqueness invariant.

## CaseRunner hardening

The frontend runner now treats authenticated API 401 responses consistently across:

- start/resume
- decision submission
- state refresh after an error
- restart/new attempt

A 401 clears stale attempt/choice/error state and returns the component to the authentication-required UI rather than leaving the learner in a generic server-error state.

When a learner resumes an attempt pinned to a revision that is no longer the current public Case revision, the runner displays an explicit historical-revision notice and shows the educational objective from the pinned attempt revision. The current public Case header remains based on the current revision.

Browser QA verified this split directly with a temporary fixture containing:

- historical revision 1 with an in-progress attempt
- current revision 2 with different public content

The page showed the current public Case title while the runner correctly resumed the historical step and displayed the pinned-revision notice.

## Migration validation

### Historical v0.6.2 -> v0.7.5 upgrade

A dedicated `MigrationExecutor` audit used Django historical model states rather than current models against an old schema.

Starting state:

- atlas migration `0021_v062_timeline_therapy_technique_semantics`
- one legacy linear Case
- one legacy step/question/choice
- one completed attempt with one answer
- one in-progress attempt with one answer

The database was migrated through all v0.7 migrations including 0027.

Verified result:

- Case preserved
- completed attempt preserved
- in-progress attempt preserved
- both answers preserved
- revision 1 backfilled
- structure mode remains linear
- entry step backfilled to `step-1`
- in-progress attempt current step backfilled to `step-1`
- no fabricated event history for pre-state-engine legacy attempts
- active-attempt constraint accepts the valid single in-progress row

### Fresh install

A clean temporary SQLite database was migrated through 0027 and seeded twice.

Result after the second identical seed:

- 6 active Clinical Cases
- 6 fresh CaseRevisions
- 17 CaseScoringDimensions
- 54 CaseTransitions
- `audit_case_graphs`: 0 failures

This verifies migration completeness and seed idempotency on a fresh deployment.

## Regression validation before release closeout

Backend:

- Case-focused `AtlasApiTests + V075CaseConcurrencyTests`: **130/130 PASS**
- full Django backend suite: **187/187 PASS**
- Django system check: PASS
- `makemigrations --check --dry-run`: no changes detected
- project venv `pip check`: no broken requirements
- Python compileall: PASS

Current development database:

- Case graph audit: 6 Cases / 12 revisions / 17 dimensions / 0 failures
- QA attempts/events/answers after cleanup: 0 / 0 / 0
- SQLite `integrity_check`: ok
- SQLite foreign-key check: 0 violations
- partial unique active-attempt index present

Scientific/research regression:

- v0.6 scientific release audit: PASS
- active provenance gaps: 0
- weak-only entities: 59
- weak-only relations: 52
- weak-only rows incorrectly marked reviewed: 0
- timeline precision issues: 0
- research archive: 2 datasets / 1918 records
- source archive SHA-256 verification: PASS
- v0.7.5 does not alter scientific or research corpus data

Frontend final local validation:

- TypeScript: PASS
- Next.js 16.3.5 production build: 24/24 generation units
- npm audit: 0 vulnerabilities
- mobile QA: 320x800 horizontal overflow false
- invalid server-rejected refresh token returns CaseRunner to auth state and clears local tokens

Local release closeout repeats passed on the final v0.7.5 code: Case-focused 130/130, full backend 187/187, TypeScript, Next.js 24/24 build, npm audit, migration/fresh-install guards, database integrity and scientific/research audits. GitHub tag/release is created only after the merged `main` commit passes post-merge CI and CodeQL.

## Version boundary

v0.7 is now composed of:

- v0.7.1 — revision-safe branching Case architecture
- v0.7.2 — server-authoritative stateful attempt engine and branching runner
- v0.7.3 — revision-pinned multidimensional educational scoring
- v0.7.4 — personal Case analytics
- v0.7.5 — post-release integrity, migration and concurrency patch

v0.7.5 is the final planned release in this line. Normal roadmap development proceeds to v0.8. A later v0.7.x release should exist only if a newly discovered defect requires a patch; it should not be used to continue feature scope.

## Safety boundary

All Clinical Case scoring and analytics remain educational product behavior. Nothing in v0.7.5 converts Case scores, dimensions, paths or analytics into:

- diagnosis
- treatment advice
- psychometric measurement
- normative learner ranking
- therapist fitness
- clinical competence certification
- treatment-quality assessment

That boundary remains unchanged from v0.7.3/v0.7.4.
