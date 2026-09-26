# Psychology Atlas v0.8.2 — Study Blocks + Deterministic Scheduler

Release date: 2026-09-26  
Status: release candidate evidence gathered locally; GitHub PR, merge, tag and Release publication are the release-closeout steps.

## Release scope

v0.8.2 extends the frozen v0.8.1 Study Planning foundation with scheduled StudyBlock intentions and a deterministic scheduler. It does not add StudySession or Recommendation V2. A StudyPlan remains intent/configuration. StudyBlock represents planned activity and adherence; it is not a mastery score, psychometric result, exam-pass probability or clinical competence measure.

## Architecture and persistence

- `StudyPlan` remains the owner of plan intent and generation state. Existing UserStudySettings, IANA study timezone, StudyPlanAvailability and explicit-FK StudyPlanScope semantics from v0.8.1 remain in force.
- `StudyBlock` stores plan, optional same-plan scope, block kind/status/origin, date and sequence, bounded estimated minutes, generation version, user lock, title/subtitle snapshots, metadata, explicit target foreign keys, and started/completed/skipped timestamps.
- Model and database validation enforce target/kind consistency, exactly one required target, scope/plan ownership, block generation not ahead of the plan, minute bounds, and lifecycle timestamp/status consistency.
- Migration `0029_v082_study_blocks.py` additively introduces block storage and supporting integrity. Migration `0030_studyblock_ck_study_block_started_status_and_more.py` adds lifecycle timestamp/status database checks. No plan, settings or StudyBlock is fabricated by either migration.

## API surface

Existing study planning routes remain, with schedule and block actions:

- `POST /api/study/plans/<id>/generate/` — generate or regenerate schedule.
- `GET /api/study/plans/<id>/schedule/` — read schedule, generation metadata and explicit capacity/unavailable/cross-plan warnings.
- `POST /api/study/blocks/<id>/reschedule/` — move an actionable block to a valid plan date and lock it to the user.
- `POST /api/study/blocks/<id>/unlock/` — unlock an eligible generated pending block.
- `POST /api/study/blocks/<id>/skip/` — preserve a skipped block as history.
- `POST /api/study/blocks/<id>/complete/` — complete only when block-kind evidence rules are met.

All personal plan and block actions are authenticated and owner-scoped. A foreign user's object is indistinguishable from a missing one (generic 404 behavior).

## Scheduler rules and guarantees

- The candidate ordering and schedule derive from the same plan/settings/availability/scope inputs and stable tie-breaks, so identical inputs yield identical output.
- An unchanged generation is a no-op: it does not create duplicates or increment `generation_version`.
- Plan-level write serialization makes simultaneous generation converge on one final generation. SQLite lock handling has bounded retries; PostgreSQL keeps row-lock behavior.
- Daily plan capacity is respected. The response explicitly reports unscheduled backlog and capacity shortfall, scopes unavailable at generation time, schedule date range, and days whose combined active plans exceed capacity. No other plan is silently changed and no exam readiness score is inferred.
- General-plan horizon is bounded; exam schedule dates do not extend beyond `target_date`. Pathologically distant exam ranges are bounded.
- Changing scheduler inputs (scope, availability, plan kind, start or target date) marks a prior schedule stale. Name/notes are not scheduler inputs. Successful regeneration clears stale state.
- If a scope target becomes inactive, its old future generated pending unlocked blocks are superseded; the scheduler does not guess substitute content. The unavailable scope is reported.

## Regeneration and block lifecycle

Only future, generated, pending and unlocked candidate blocks may be superseded during regeneration. Completed, in-progress, manual, past, user-locked and other meaningful historical state is preserved. Superseding retains rows rather than deleting history. Skipped candidate history is not silently recreated as pending. Rescheduling validates the owner, actionability and date range, allocates a valid sequence, and sets the user lock. Regeneration preserves locked work. Unlock is limited to generated pending blocks so later generation may reschedule them.

## Canonical evidence boundary

- Flashcard blocks reserve review capacity only. Actual due cards are selected at runtime by canonical SRS; no future card IDs are frozen into the plan. StudyBlock rescheduling/snoozing does not change an SRS due date.
- Quiz completion requires a real QuizAttempt by the same owner for that Quiz.
- Clinical Case completion requires a completed CaseAttempt by the same owner for that Case, revision-safe under the v0.7.5 case rules. The scheduler neither creates attempts nor duplicates scoring.
- Distortion practice completion requires a matching real attempt.
- Evidence must be for the same owner and target and must not predate the block's scheduled day.
- Reading/review confirmation can complete a block as plan adherence only.

## Read-only audit

`python manage.py audit_study_plans` inspects invalid timezones, session/default-minute issues, incomplete availability, exam dates/target, active plans without usable scope/capacity, invalid/inactive scopes, invalid blocks, generation versions ahead of the plan, scope/plan mismatch, inactive targets and duplicate active generated candidate keys. It reports stored corruption without repair or mutation. The failure-path test corrupts a persisted value, runs the audit, and confirms the value remains unchanged.

## Implementation audit and fixes

The release audit retained regressions for concurrent generation convergence, stale inputs and no-op regeneration, inactive-scope preservation/reporting, owner isolation on generation and block actions, block/evidence lifecycle integrity, and actual query budgets for scope resolution/block generation. An observed test-only concurrency failure came from overlapping per-thread date mocks; the fixed test shares one stable date patch around the concurrent calls. The scheduler's same-input convergence regression then passes.

The migration regression uses Django `MigrationExecutor` with actual historical models at 0028, including existing settings, all seven availability rows, scope, nonzero generation version and last-generated timestamp. Upgrade to 0029 preserved each and created zero StudyBlocks. Fresh database migration through 0030 and repeated seed snapshots were also checked.

## Validation evidence

Local backend and project checks:

- Focused v0.8.2 suite: **26/26 PASS**.
- Full backend suite: **243/243 PASS**.
- `python manage.py check`: PASS.
- `python manage.py makemigrations --check --dry-run`: PASS, no changes detected.
- `python -m compileall -q atlas config`: PASS.
- `python -m pip check`: PASS, no broken requirements.
- Historical 0028→0029 preservation regression: PASS.
- Fresh SQLite migration through 0030: PASS. `seed_mvp` repeated; two final normalized snapshots matched across 108 `atlas_*` tables and 1,133 rows (SHA-256 `64b18db805bfa1d0822f60c366106ecb8e64a6f9d7557a6338fd63b4c8ce8838`).
- Existing development DB was backed up before migration; migrations 0029/0030 applied. `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned 0 rows.
- `audit_study_plans`: PASS on runtime and fresh DB, zero failures after QA cleanup.
- `audit_case_graphs`: PASS on runtime (6 Cases, 12 revisions, 17 dimensions; no attempts/events/answers after cleanup); fresh seeded DB audit also passed.
- `audit_v06_release`: PASS; zero provenance gaps, 59 weak-only entities and 52 weak-only relations surfaced as existing review debt.
- `verify_research_datasets`: PASS on the runtime DB, 2 datasets / 1,918 records with stored hashes verified. Fresh DB has no imported source archive files by design, so archive verification is reported against the populated runtime DB.
- Frontend package version: `0.8.2`. `npm run typecheck`: PASS. `npm run build`: PASS, Next.js 16.3.5 Turbopack, 26/26 generation units. `npm audit --audit-level=low`: PASS, 0 vulnerabilities.

Real Chromium browser QA used the local production frontend and backend. At 390×844 and 1280×800, registration/login, plan creation with a long Persian title, scope and availability changes, generation, unchanged no-op regenerate, reschedule+lock, locked regeneration preservation, unlock, skip+regenerate preservation, reading completion, and rejected Quiz completion without evidence all passed. Both viewports had zero horizontal overflow. Reduced-motion preference, keyboard focus, auth-expiry redirect and Persian text wrapping were checked. The temporary QA account and its plan/settings/scope/availability/blocks were deleted; no QA user remains.

The existing runtime research corpus and Case/scientific audits remained intact. This release changes scheduling behavior only and adds no parallel learning or mastery evidence engine.

## Release state and repository gates

- PR: pending.
- Exact PR merge SHA: pending; record the actual squash-merge commit here during closeout.
- Tag: `v0.8.2`, to point at verified final `main` after post-merge checks.
- GitHub Actions, Dependency Review and Python/JavaScript CodeQL: pending PR checks.
- GitHub Release: pending; publish only after post-merge checks and tag verification.

## Next roadmap slice: v0.8.3

Proceed to v0.8.3 on the frozen v0.8.2 foundations. Keep StudyPlan intent, StudyBlock schedule/adherence and canonical SRS/Quiz/Case/Distortion evidence boundaries intact. StudySession or Recommendation V2 should only enter scope when the next slice explicitly defines their contracts; do not redesign v0.8.1/v0.8.2 as part of that work.
