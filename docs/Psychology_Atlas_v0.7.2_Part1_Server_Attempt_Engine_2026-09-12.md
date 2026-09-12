# Psychology Atlas — v0.7.2 Part 1/2 · Server Attempt State Engine

**Date:** 2026-09-12
**Status:** development slice complete; v0.7.2 is not released yet
**Base release:** v0.7.1 Branching Clinical Case Architecture + Revision Safety
**Repository:** `C:\Users\Meliodas\Downloads\psychology_atlas_fullstack_mvp`

## 1. Scope of this part

v0.7.2 is intentionally split into two implementation prompts because server-authoritative state, frontend resume UX, browser regression and release freeze together are too large for one safe slice.

Part 1 implements the backend source of truth:

- start or resume a CaseAttempt
- persist the exact current CaseStep
- submit one decision/advance at a time
- let the server resolve the only valid transition
- immutable-enough event history for audit
- state-version replay/tamper protection
- idempotent exact retry
- user ownership isolation
- completed-attempt immutability
- compatibility with old linear submit
- migration/backfill for existing in-progress attempts
- structural + state-history audit coverage

Part 2 remains responsible for the frontend CaseRunner migration, resume UX, locked history UI, completion presentation, TypeScript contracts, browser interaction audit and final v0.7.2 release metadata/freeze.

## 2. New persistent attempt state

`CaseAttempt` now owns two additional state fields:

```text
current_step
state_version
```

`current_step` is a protected reference to the authoritative node the user is currently allowed to act on.

`state_version` starts at `0` and advances exactly once for every accepted state event. The client must send the version it observed. A stale version cannot mutate the attempt.

The model validates:

- attempt revision belongs to the attempt Case
- current step belongs to the same Case
- current step belongs to the exact attempt revision
- an in-progress attempt must have a current step

A new `(user, case, status)` index supports resume lookup.

## 3. CaseAttemptEvent

New model:

```text
CaseAttemptEvent
```

Event types:

```text
decision
advance
terminal_complete
```

Each event stores:

```text
attempt
step
event_type
question                  nullable
selected_choice           nullable
transition                nullable for terminal completion
next_step                 nullable
outcome
awarded_score
max_score
state_version_before
state_version_after
snapshot
created_at
```

Two uniqueness rules protect history:

```text
(attempt, step)
(attempt, state_version_before)
```

Because v0.7.1 Case graphs are DAGs, one step may be committed at most once per attempt.

The server-created `snapshot` preserves the educational decision context needed for later audit/UI even if canonical display content is changed administratively in the future. Current snapshots include step identity/title/kind, question prompt when applicable, selected choice text/feedback, transition outcome and target stable key.

## 4. Event integrity rules

Decision event:

- requires a question, selected choice and explicit CaseTransition
- question must belong to the event step
- selected choice must belong to that question
- transition source must be the same step
- transition choice must be the selected choice

Information advance event:

- has no question/choice
- requires the explicit automatic transition (`choice = null`)
- automatic transition must originate from the current step

Terminal completion event:

- has no question/choice/transition/next step
- is only legal on a terminal CaseStep
- outcome is always `complete`

All events must advance state version exactly once.

## 5. Server-authoritative engine

New service entry points in canonical `backend/atlas/services.py`:

```text
start_or_resume_case_attempt(...)
advance_case_attempt(...)
```

No parallel v7 runtime modules were created.

### Start/resume

Start locks the ClinicalCase row, then checks for an existing in-progress attempt owned by the user for that Case.

Rules:

- zero existing attempts: create one at the published revision entry step
- exactly one: return it unchanged as resume
- more than one: fail as an integrity problem instead of choosing one arbitrarily
- invalid/missing/inactive resume step: fail rather than silently repairing history

This keeps new attempt creation serialized on PostgreSQL while remaining safe on the current SQLite development database.

### Submit decision/advance

The request supplies:

```text
step_id
choice_id        nullable for information/terminal nodes
state_version
```

The server then:

1. locks the owned attempt row
2. checks whether the exact step was already committed
3. returns the prior result for an exact replay
4. rejects a conflicting replay
5. rejects completed-attempt mutation
6. rejects stale `state_version`
7. rejects any `step_id` other than the server-owned current step
8. resolves the active question and choice when the step is a decision
9. resolves the explicit CaseTransition from the database
10. records the immutable event snapshot
11. records CaseAttemptAnswer for decision nodes
12. updates scalar legacy score/max-score for compatibility
13. advances to the server-selected next node or completes the attempt
14. applies completion side effects exactly once

The frontend never sends or chooses `next_step_id`.

## 6. Idempotency and replay behavior

Idempotency is tied to persisted attempt state rather than a best-effort browser flag.

Example:

```text
state_version = 0
step = entry
choice = A
```

First valid request:

```text
creates event 0 -> 1
moves current_step
updates score once
```

An exact retry with the same step/choice/version:

```text
returns the existing event
idempotent = true
creates no new answer/event/activity/progress mutation
```

A retry with another choice or another version is rejected.

A request for a future node is rejected because only `attempt.current_step` may mutate state.

## 7. Completion semantics

Decision or information transitions with `outcome=complete` finish immediately.

A terminal node is intentionally visible as the current node first. It requires one explicit acknowledgement request with no choice. That records a `terminal_complete` event and then completes the attempt.

When completed:

```text
status = completed
current_step = null
completed_at = server time
```

Any new mutation is rejected, except an exact replay of an already committed request, which is returned idempotently without side effects.

## 8. Completion side effects

The new stateful engine preserves the existing scalar educational score behavior until v0.7.3 introduces audited multi-dimensional scoring.

On the single transition from in-progress to completed:

- UserProgress uses the attempt revision's snapshotted primary disorder
- progress is non-regressive
- StudyActivity `CASE_COMPLETED` is written once
- metadata records attempt ID, score/max score, revision number and `stateful_engine=true`

This is still educational progress, not a clinical-competence metric.

## 9. New API contract

Authenticated endpoints:

```text
POST /api/cases/<slug>/attempts/
GET  /api/cases/<slug>/attempts/current/
GET  /api/case-attempts/<id>/
POST /api/case-attempts/<id>/decisions/
```

### Start

Returns `201` for a new attempt and `200` when resuming the existing in-progress attempt.

Response includes:

```text
id
case snapshot
status
state_version
score
max_score
current_step only
history
created_at
updated_at
completed_at
resumed
```

### Current

Returns the user's current in-progress attempt for the Case or 404 when no resumable attempt exists.

### Attempt detail

User-scoped read of either in-progress or completed history. Cross-user access returns 404.

### Decision

Returns the new authoritative state plus:

```text
event_id
idempotent
```

`choice_id` is required for decision nodes and must be null/absent for information or terminal nodes.

## 10. Migration

New migration:

```text
0025_v072_attempt_state_engine.py
```

It:

- creates CaseAttemptEvent
- adds CaseAttempt.current_step
- adds CaseAttempt.state_version
- adds the resume index
- backfills existing in-progress attempts to their revision entry step when available

The migration applied successfully to the real local database.

## 11. Audit hardening

`python manage.py audit_case_graphs` now audits both graph and runtime state.

It additionally checks:

- duplicate in-progress attempts for the same user/Case
- in-progress attempt missing current step
- current step Case/revision mismatch
- completed attempt retaining current step
- contiguous event state versions
- attempt.state_version matching the persisted event sequence
- event step/question/choice/transition/target revision ownership
- historical CaseAttemptAnswer ownership

Current real database result after migration:

```text
cases=6
revisions=6
attempts=0
events=0
answers=0
failures=0
PASS
```

## 12. Tests added in Part 1

Focused v0.7.2 tests cover:

1. start + resume returns one attempt
2. duplicate in-progress integrity violation is rejected
3. server chooses the next branch and records history
4. skip / foreign choice / stale state are rejected
5. exact duplicate decision is idempotent
6. conflicting replay is rejected
7. information advance completes exactly once
8. completed attempt cannot be mutated
9. attempt/current/decision endpoints are user-scoped
10. resume remains bound to the original revision after a new Case revision becomes current
11. terminal node requires explicit completion acknowledgement
12. malformed state version is rejected
13. stateful event history passes the expanded case audit

The `-k v072` focused suite currently reports 11 test methods because several related assertions are grouped within the same method.

## 13. Validation at Part 1 boundary

Completed successfully:

```text
v0.7.2 focused tests: 11/11 PASS
full backend suite at Part-1 commit boundary: 147/147 PASS
Django system check: PASS
migration 0025: applied successfully
makemigrations --check --dry-run: No changes detected
compileall: PASS
pip check: PASS
SQLite integrity_check: ok
SQLite foreign_key_check: 0
in-progress attempts without current_step: 0
case graph/state audit: PASS
v0.6 scientific release audit: PASS
research archive verification: 2 datasets / 1918 records / exact hashes PASS
```

A final full backend run is performed again immediately before the Part 1 commit because one additional duplicate-attempt test was added after the earlier 146-test run.

## 14. Compatibility boundaries

The old endpoint remains available:

```text
POST /api/cases/<slug>/submit/
```

It remains limited to `structure_mode=linear` and now creates completed attempts with `current_step=null`.

The new engine works from explicit CaseTransition records for both linear and branching structures, so Part 2 can migrate the frontend without deleting the compatibility endpoint.

No v0.7.3 multi-dimensional scoring model was introduced here.

No analytics was introduced here.

No AI-generated transition logic was introduced here.

## 15. Part 2/2 exact continuation

Next prompt should implement:

```text
1. frontend/lib/types.ts stateful attempt/event contracts
2. migrate CaseRunner from local linear state to server attempt state
3. start/resume behavior on page load
4. decision submit with step_id + choice_id + state_version
5. information-node Continue action
6. terminal acknowledgement/completion flow
7. locked reached-history UI without future-branch spoilers
8. completed summary based on reached path only
9. loading/error/retry/double-click hardening
10. RTL/mobile/keyboard accessibility pass
11. browser E2E for start -> branch -> resume -> complete
12. final backend + frontend regression
13. README / PROJECT_SPEC / BUILD_MANIFEST v0.7.2 release sync
14. package version bump to 0.7.2
15. final v0.7.2 release commit
```

The official released version remains v0.7.1 until Part 2 completes and the final v0.7.2 release gate passes.
