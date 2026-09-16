# Psychology Atlas v0.7.2 — Server-Authoritative Case Attempts + Stateful Runner

**Release date:** 2026-09-16
**Release line:** v0.7 Advanced Branching Clinical Cases + Analytics
**Slice:** v0.7.2

## Release purpose

v0.7.2 turns the revision-safe branching case foundation from v0.7.1 into a real server-authoritative execution engine and a stateful Persian/RTL CaseRunner.

The backend is the source of truth for the learner's current node, accepted decision, valid transition, score update, and completion state. The frontend renders the current attempt state and immutable reached-path history returned by the API; it does not calculate or submit an authoritative next branch.

This remains an educational system. Case scores and feedback are not clinical competency certificates, personal diagnoses, or treatment recommendations.

## Backend attempt state

`CaseAttempt` now carries:

- `current_step`
- `state_version`
- immutable revision binding inherited from v0.7.1

`CaseAttemptEvent` records the append-only-enough execution history for:

- decision events
- automatic information-node advances
- terminal completion acknowledgements

Each event stores:

- source step
- selected question/choice when applicable
- resolved transition
- resolved next step when applicable
- outcome
- awarded/max score for that event
- state version before and after
- a server-generated educational snapshot of the reached step/decision

Decision snapshots include question prompt, question explanation, choice text, choice feedback, outcome, and target stable key when applicable. This allows previously reached learning feedback to remain interpretable even if a later Case revision becomes current.

## Server-authoritative transition contract

The client may submit only the state it is currently acting on:

```text
step_id
choice_id
state_version
```

The client never supplies an authoritative `next_step_id`, transition id, score, max score, or completion state.

The service locks the attempt, verifies ownership and current state, validates the current node kind and active content, resolves the valid `CaseTransition`, records the event, advances `state_version` exactly once, updates the attempt, and applies completion side effects once.

## Replay and tamper resistance

v0.7.2 rejects:

- future-node skipping
- a step other than `current_step`
- a choice from another question/case/revision
- stale state versions
- conflicting replay for a previously recorded step
- mutation of a completed attempt
- malformed state versions
- invalid resume state
- multiple simultaneous in-progress attempts for the same user/case integrity condition

An exact retry of the already accepted step/choice/state version is idempotent. It returns the previously recorded event without adding duplicate score, answers, history, progress, or completion activity.

## Start and resume behavior

Starting a Case:

1. Locks the Case and checks for an existing in-progress attempt owned by the user.
2. If one valid attempt exists, it is resumed against its original revision.
3. If none exists, a new attempt starts at the published revision's active entry step.
4. A corrupt or duplicate in-progress state fails explicitly instead of choosing an arbitrary attempt.

Publishing a newer Case revision does not move an existing in-progress attempt onto the new revision.

## Stateful APIs

Authenticated endpoints:

```text
POST /api/cases/<slug>/attempts/
GET  /api/cases/<slug>/attempts/current/
GET  /api/case-attempts/<id>/
POST /api/case-attempts/<id>/decisions/
```

The legacy linear endpoint remains available for backward compatibility:

```text
POST /api/cases/<slug>/submit/
```

The v0.7.2 frontend CaseRunner does not use the legacy submit endpoint.

## Frontend CaseRunner

The CaseRunner was rebuilt around `CaseAttemptState`.

Implemented behavior:

- authenticated start/resume
- current server-owned step only
- distinct decision/information/terminal node UX
- immutable reached-path history
- decision feedback/explanation from event snapshots
- refresh-safe resume
- locked previous decisions
- no client-side branch calculation
- stale-state error recovery
- disabled/busy protection around mutation
- keyboard focus handling for the new current node
- `aria-live` state/error announcements
- `aria-pressed` choice selection state
- responsive Persian/RTL layout
- explicit educational-only result language
- create-a-new-attempt flow after completion

The full public Case detail structure is retained for backward API compatibility, but it is not used by the stateful runner to decide navigation.

## Authentication return flow

When an unauthenticated learner enters a Case, the runner sends them to login with an internal `next` path. The login page accepts only a local path beginning with a single `/`, preventing protocol-relative external redirects, and returns the learner to the same Case after successful authentication.

## Migration

New migration:

```text
0025_v072_attempt_state_engine.py
```

It creates `CaseAttemptEvent`, adds `current_step` and `state_version` to `CaseAttempt`, adds attempt-state indexes/constraints, and backfills legacy in-progress attempts to their revision entry step when possible.

## Audit expansion

`python manage.py audit_case_graphs` now validates both revision graphs and persisted attempt/event history, including:

- attempt revision/case ownership
- valid in-progress current step
- duplicate in-progress attempt detection
- event step/revision ownership
- exact state-version sequencing
- event/transition/choice consistency
- event chain consistency with the attempt state
- answer/revision consistency

## Production browser E2E

A temporary branching Case fixture and temporary user were used against the real local Django API and production Next.js build in Chromium.

Verified flow:

1. Register through the real UI.
2. Open the branching Case.
3. Start an attempt (`201`).
4. Select a decision in the UI.
5. Backend accepts and resolves the branch (`200`).
6. Reload the Case page.
7. The same in-progress attempt resumes (`200`).
8. Reached-path history is preserved.
9. Advance through the selected branch to its terminal state.
10. Complete the attempt from the UI.
11. Start a new attempt after completion (`201`).
12. Enter the Case while logged out, follow the safe login return path, and resume the in-progress attempt after authentication.

The temporary user, attempts, events, answers, progress/activity rows, transitions, steps, revision, and Case fixture were deleted after the audit. Final database checks report no remaining E2E attempt/event rows.

## Release validation

```text
Backend full suite:               147/147 PASS
Focused v0.7.2 attempt tests:      11/11 PASS
Django system check:               PASS
Migration drift:                   No changes detected
Python compileall:                 PASS
Project venv pip check:            PASS
Case graph/state audit:            PASS
Current Case audit inventory:      6 cases / 6 revisions / 0 attempts / 0 events / 0 answers / 0 failures
SQLite integrity_check:            ok
SQLite foreign_key_check:          0
In-progress attempt without step:  0
v0.6 scientific release audit:     PASS
Research archive verification:     2 datasets / 1918 records / exact hashes PASS
Frontend package:                  0.7.2
TypeScript typecheck:               PASS
Next.js production build:          PASS / 23 of 23 generation units
npm audit --audit-level=low:        0 vulnerabilities
Chromium stateful Case E2E:         PASS
```

Scientific debt from the frozen v0.6 domain remains explicit and unchanged:

```text
active provenance gaps: 0
weak-only v0.6 entities: 59
weak-only v0.6 relations: 52
weak-only rows incorrectly reviewed: 0
timeline precision issues: 0
```

Protected research archive remains unchanged:

```text
psychology_atlas_research_dataset.json
762 records
sha256 753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0

psychology_atlas_research_dataset_complete___1.json
1156 records
sha256 3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

## Deliberately deferred

v0.7.2 does not introduce fabricated scoring dimensions or analytics. The next planned slice is:

**v0.7.3 — Multi-dimensional Educational Scoring + Feedback**

Candidate dimensions must be justified by actual Case content structure before they become schema or UI. Later v0.7 slices can build runner UX/analytics further without weakening server authority or historical revision safety.
