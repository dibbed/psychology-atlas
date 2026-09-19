# Psychology Atlas v0.8.1 — Study Planning Foundation

Date: 2026-09-19  
Release line: v0.8 Study Mode + Exam Planning + Advanced Recommendations  
Previous public release: v0.7.5 — Clinical Case Integrity Patch  
Next planned slice: v0.8.2 — Study Blocks + Deterministic Scheduler

## Purpose

v0.8.1 is the first implementation slice of the v0.8 Study Mode line. It deliberately builds only the user-owned **intent/configuration layer** required by later scheduling and recommendation work.

The release adds:

- personal Study settings;
- general and exam Study Plans;
- recurring weekly availability;
- explicit content Scope;
- lifecycle management;
- authenticated owner-scoped APIs;
- Persian/RTL Study Plan management UI.

It deliberately does **not** add:

- generated StudyBlock rows;
- an automatic scheduler;
- exam-readiness percentages;
- a new mastery model;
- Recommendation V2;
- Study Sessions;
- a Today endpoint;
- changes to canonical Flashcard SRS due dates;
- changes to Quiz/Case scoring;
- changes to Daily Challenge date semantics.

That boundary is intentional. v0.8.1 records what the learner wants to study and when they are generally available. Later slices may generate operational schedules from this stable input.

## Baseline reconciliation

Development started from the exact v0.7.5 release baseline:

```text
branch: main
HEAD: 9539223c3190edf5d73eede8196ba26b379c80c9
tag: v0.7.5
working tree: clean
```

Pre-change release gates were rerun before schema work:

```text
backend: 189/189 PASS
Django check: PASS
migration drift: none
Case graph audit: PASS
v0.6 scientific audit: PASS
research archive verification: 2 datasets / 1918 records PASS
```

No pre-existing failure was folded into the v0.8.1 branch.

## Schema

Migration:

```text
backend/atlas/migrations/0028_v081_study_plan_foundation.py
```

adds four models.

### UserStudySettings

Purpose: personal defaults used by Study Planning.

Fields include:

- user one-to-one;
- `study_timezone`;
- `default_daily_minutes`;
- `default_session_minutes`;
- `week_starts_on`.

Invariants:

- timezone must be a valid IANA timezone;
- daily minutes: 5..720;
- session minutes: 5..240;
- session minutes cannot exceed daily minutes;
- week start uses Python weekday convention 0..6.

Settings are **lazy**. Migration 0028 creates no row for an existing user.

### StudyPlan

Purpose: a user-owned study goal/configuration container.

Kinds:

```text
general
exam
```

Statuses:

```text
draft
active
paused
completed
archived
```

Important fields:

- name;
- start_date;
- target_date;
- notes;
- generation_version;
- last_generated_at;
- archived_at;
- completed_at.

Exam invariants:

```text
target_date required
target_date >= start_date
```

General plans may have no target date.

`generation_version` remains 0 in v0.8.1 because no scheduler exists yet.

### StudyPlanAvailability

Purpose: deterministic recurring weekly capacity for one Plan.

Fields:

- plan;
- weekday 0..6;
- available_minutes 0..1440.

Constraint:

```text
unique(plan, weekday)
```

API convention:

- all seven weekdays are present after save;
- 0 minutes explicitly means unavailable.

This avoids ambiguous missing-day semantics in the future scheduler.

### StudyPlanScope

Purpose: explicit content selected for a Plan.

Supported target domains:

1. Disorder
2. Concept
3. Therapy
4. Theory
5. Psychologist
6. TimelineEvent
7. Quiz
8. ClinicalCase

The model uses explicit nullable protected foreign keys, not GenericForeignKey.

Why:

- database referential integrity;
- inactive-target policy can be audited;
- query behavior is explicit;
- migrations remain reviewable;
- deleted/retargeted content cannot silently rewrite user intent.

Each Scope row must reference **exactly one** target.

Database/model guards cover:

- exactly one target;
- priority 1..5;
- one occurrence of the same target per Plan;
- explicit protected FK ownership.

Scope priority is operational scheduler input only. It is not mastery, scientific importance, exam readiness, diagnosis, clinical competence or treatment recommendation.

## Timezone boundary

v0.8.1 introduces a per-user IANA timezone for Study Planning.

Examples:

```text
Asia/Tehran
Europe/Berlin
America/New_York
```

Fixed offsets such as `+03:30` are rejected.

The boundary is intentionally narrow:

- StudyPlan default dates use `UserStudySettings.study_timezone`;
- the new-plan frontend also derives its default date from that timezone;
- existing Daily Challenge behavior continues using the established application-timezone semantics;
- historical DailyChallengeAttempt dates are not migrated or reinterpreted.

This avoids silently changing an existing one-attempt-per-day contract.

## API

New authenticated routes:

```text
GET/PUT   /api/study/settings/
GET       /api/study/scope-catalog/
GET/POST  /api/study/plans/
GET/PATCH /api/study/plans/<id>/
PUT       /api/study/plans/<id>/availability/
PUT       /api/study/plans/<id>/scopes/
POST      /api/study/plans/<id>/activate/
POST      /api/study/plans/<id>/pause/
POST      /api/study/plans/<id>/archive/
```

### Ownership

Every personal Plan lookup begins with the authenticated user scope.

A user cannot:

- read another user's Plan;
- patch it;
- replace its Scope;
- replace its Availability;
- activate/pause/archive it.

Cross-user requests return the same generic 404 semantics as a missing Plan.

### Stable errors

Machine-readable codes are returned for Study Planning validation and lifecycle failures, including:

```text
study_plan_not_found
study_plan_archived
study_plan_invalid
study_plan_invalid_date_range
study_plan_scope_invalid
study_plan_scope_duplicate
study_plan_no_availability
study_plan_not_actionable
study_timezone_invalid
```

Malformed non-object payloads are normalized to `study_plan_invalid` rather than leaking a separate DRF validation shape.

### Scope catalog

The authenticated Scope catalog exposes one uniform picker contract across all eight target domains.

It:

- returns active/runnable targets only;
- accepts bounded text search;
- caps result count;
- rejects unknown target types;
- rejects pathological query length;
- provides stable slug/title/subtitle fields to the frontend.

It does not infer hidden content relationships or auto-expand a selected topic.

## Lifecycle

### Draft

Editable Plan configuration.

### Active

Activation requires:

- at least one Scope item;
- at least one weekday with positive available minutes.

Scope and Availability are frozen while active.

### Paused

Preserves configuration and allows Scope/Availability editing.

### Archived

Non-destructive.

Archive:

- preserves Plan;
- preserves Scope;
- preserves Availability;
- prevents silent reactivation.

No user-owned row is deleted by archive.

### Completed

The status is reserved in the schema for later explicit completion semantics. v0.8.1 does not automatically mark an exam Plan complete when a target date passes.

## Existing Study engine compatibility

The existing endpoint:

```text
GET /api/study/overview/
```

is intentionally unchanged.

Regression tests lock its existing top-level contract:

- streak;
- heatmap;
- recommendations;
- review;
- concepts;
- daily_challenge_completed;
- distortion_practice.

v0.8.1 does not insert Plans into the old overview response.

Existing systems remain canonical:

- `UserFlashcardProgress` for SRS;
- `QuizAttempt` for Quiz outcomes;
- `CaseAttempt` / immutable events for Case history;
- DailyChallengeAttempt for challenge completion;
- UserConceptProgress / UserProgress for learning progress.

No parallel completion/mastery data is created in StudyPlan.

## Frontend

New routes:

```text
/study/plans
/study/plans/new
/study/plans/[id]
```

### Plans page

Provides:

- Plan list;
- archived-plan section;
- personal Study settings;
- IANA timezone edit;
- daily/session defaults;
- week-start setting;
- direct create/manage navigation.

### New Plan page

Supports:

- general/exam kind;
- start date;
- exam target date;
- notes.

The start-date default is based on the saved Study timezone rather than the browser/device timezone.

### Plan detail

Supports:

- Plan metadata edits;
- seven-day availability;
- Scope search/add/remove;
- priority 1..5;
- include-practice flag;
- activate;
- pause;
- archive.

The UI clearly states that v0.8.1 does not generate StudyBlocks.

An active Plan must be paused before changing Scope or Availability.

### Integration

Study Planning is discoverable from:

- primary Study Center;
- Learn navigation;
- Study Plan list/create/detail routes.

The old Study Center remains functional and continues consuming the existing overview endpoint.

## Deep audit fixes during release closure

The v0.8.1 closeout audit found and fixed three concrete issues before release:

### 1. Malformed payload error inconsistency

Problem:

Study Planning endpoints still called the generic request-object helper, so a JSON array could return a DRF validation response without the stable Study Planning error code.

Fix:

A Study-specific object helper now returns:

```text
code=study_plan_invalid
```

for non-object payloads.

Regression coverage was added.

### 2. Unbounded Scope search text

Problem:

Scope catalog result count was bounded, but search text length was not.

Fix:

Search text is capped at 200 characters and oversized input returns `study_plan_scope_invalid`.

Regression coverage was added.

### 3. New-plan device-timezone drift

Problem:

The initial new-plan form derived the date from the browser's local timezone. A user whose configured Study timezone differed from the device could receive the wrong date around midnight.

Fix:

The new-plan page loads `UserStudySettings` first and derives the initial date using `study_timezone`.

This preserves the intended timezone boundary.

### 4. Scope replacement N+1 risk

Problem:

The first replace-all implementation resolved every Scope target with its own database query. The API capped Scope rows, but a large Plan could still turn one request into query count proportional to the number of selected targets.

Fix:

Scope payloads are normalized first, slugs are grouped by target type, and active targets are resolved in bulk with at most one lookup per used target domain.

Regression:

```text
40 Concept targets
full authenticated PUT /scopes/
<=12 database queries
PASS
```

### 5. Lifecycle write serialization and activation integrity

Problem:

Scope/Availability writes checked Plan status without locking the Plan row. Metadata PATCH also loaded an unlocked Plan and then saved the model. On a row-locking database such as PostgreSQL, a concurrent Archive/Activate and edit could observe stale lifecycle state.

Fix:

All Plan metadata, Scope, Availability and lifecycle mutation paths now acquire the same Plan row with `select_for_update()` inside an atomic transaction.

Activation also revalidates current configuration:

- all seven Availability rows must still exist;
- at least one day must have positive capacity;
- every Scope target must still be active/runnable.

A Plan therefore cannot become active from incomplete or stale configuration.

### 6. Clinical Case Scope runnability parity

Problem:

The initial Case Scope queryset checked published revision and active entry step, but did not fully mirror the final v0.7.5 Case availability authority.

Fix:

Clinical Case Scope now requires the same structural boundaries as the public Case API:

- current revision belongs to the Case;
- revision is published;
- entry step exists and is active;
- entry step belongs to the same revision;
- entry step belongs to the same Case;
- revision primary disorder is null or active.

Regression fixtures cover both an inactive revision disorder and a deliberately foreign entry step.

## Migration validation

### Historical upgrade

Automated MigrationExecutor regression:

```text
0027_v075_case_attempt_concurrency_guard
→ 0028_v081_study_plan_foundation
```

creates historical user/progress state before the migration and verifies afterward:

- user survives;
- UserProgress survives unchanged;
- no StudyPlan is fabricated;
- no UserStudySettings row is fabricated.

Result: PASS.

### Fresh install

A clean SQLite database was migrated from zero through 0028.

Result: PASS.

### Runtime database

Before applying 0028 to the development runtime database, a local backup was created:

```text
backend/data/psychology_atlas.pre_v081_20260919.sqlite3
```

Then:

```text
Applying atlas.0028_v081_study_plan_foundation... OK
```

After QA cleanup:

```text
atlas_userstudysettings=0
atlas_studyplan=0
atlas_studyplanavailability=0
atlas_studyplanscope=0
```

No test intent remains in the development database.

## Backend validation

Focused v0.8.1 suite:

```text
28/28 PASS
```

Coverage includes:

- lazy user Settings;
- IANA timezone validation;
- minute bounds;
- one Settings row per user;
- general Plan creation;
- exam target requirements;
- reversed-date rejection;
- archive immutability;
- cross-user isolation;
- seven-day Availability;
- duplicate weekday rejection;
- negative/huge minute rejection;
- all eight Scope domains;
- duplicate/inactive Scope rejection;
- exactly-one-target model validation;
- priority validation;
- lifecycle activation/pause/archive;
- active configuration freeze;
- old Study overview compatibility;
- seed preservation;
- bounded Plan-list query count;
- bounded Scope replacement query count with 40 targets resolved in <=12 queries;
- user deletion cascade;
- Scope catalog search/active boundary;
- malformed payload stable error code;
- authentication requirements;
- oversized Scope query rejection;
- historical 0027→0028 migration preservation.

Full Django discovery:

```text
217/217 PASS
```

Additional backend gates:

```text
Django check                         PASS
makemigrations --check --dry-run     PASS / No changes detected
Python compileall                    PASS
pip check                            PASS / No broken requirements
audit_case_graphs                    PASS
audit_v06_release                    PASS
verify_research_datasets             PASS
```

Case graph regression remained:

```text
cases=6
revisions=12
dimensions=17
attempts=0
events=0
answers=0
failures=0
```

Scientific release debt remained unchanged:

```text
active provenance gaps=0
weak-only entities=59
weak-only relations=52
weak-only reviewed=0
timeline precision issues=0
```

Research archive remained exact:

```text
2 datasets
1918 records
psychology_atlas_research_dataset.json
  sha256=753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0
psychology_atlas_research_dataset_complete___1.json
  sha256=3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

SQLite runtime integrity after migration:

```text
PRAGMA integrity_check = ok
PRAGMA foreign_key_check = 0 rows
```

## Frontend validation

Package version:

```text
0.8.1
```

TypeScript:

```text
npm run typecheck
PASS
```

Production build:

```text
Next.js 16.3.5
26/26 generation units
PASS
```

Study Planning routes are present in the production route table:

```text
○ /study/plans
○ /study/plans/new
ƒ /study/plans/[id]
```

Dependency audit:

```text
npm audit --audit-level=low
0 vulnerabilities
```

## Browser QA

Real Chromium QA used a temporary authenticated user against the migrated development runtime.

Flow:

1. register;
2. open Study Plans;
3. create a general Plan;
4. search Scope catalog;
5. add a Scope;
6. save Scope;
7. activate the Plan;
8. verify Plan list/detail;
9. repeat layout checks on desktop and mobile.

Programmatic results:

```text
desktop 1280x800
  list_overflow=0
  detail_overflow=0
  active_plan=PASS

mobile 390x844
  list_overflow=0
  detail_overflow=0
  active_plan=PASS
```

The temporary QA user was deleted afterward. Cascades returned all v0.8.1 personal runtime tables to zero rows.

## Safety and scientific boundary

Study Planning is an educational organization feature.

It must not present:

- diagnosis;
- treatment recommendation;
- therapist competence;
- scientific importance ranking;
- psychometric assessment;
- exam-success probability;
- fabricated readiness percentage.

A Scope priority of 5 means only “schedule this earlier/more strongly within this Plan” for future deterministic scheduling.

No v0.8.1 change modifies the protected v0.6 scientific/research corpus.

## Release boundary and next slice

v0.8.1 is complete when the intent/configuration layer is stable.

The next slice should be **v0.8.2 — Study Blocks + Deterministic Scheduler**.

v0.8.2 should consume the existing v0.8.1 primitives rather than redesign them:

- UserStudySettings;
- StudyPlan;
- StudyPlanAvailability;
- StudyPlanScope;
- generation_version;
- last_generated_at.

It should add generated operational StudyBlock state and deterministic scheduling while preserving all existing canonical learning evidence.

It should not mutate SRS due dates merely to make the plan fit.

