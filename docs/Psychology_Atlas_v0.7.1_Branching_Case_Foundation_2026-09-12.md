# Psychology Atlas — v0.7.1 Branching Clinical Case Architecture + Revision Safety

**Date:** 2026-09-12
**Release line:** v0.7 Advanced Branching Clinical Cases + Analytics
**Slice:** v0.7.1
**Repository:** `C:\Users\Meliodas\Downloads\psychology_atlas_fullstack_mvp`
**Base:** frozen v0.6.6 line plus its v0.7 handoff documentation

---

## 1. Goal

v0.7.1 converts the existing Clinical Case subsystem from an implicitly linear content structure into an additive, revisioned graph foundation without yet introducing the stateful branching runner planned for v0.7.2.

The key requirement was history safety: changing case content in a later seed must never reinterpret or destroy an older user attempt.

v0.7.1 therefore focuses on:

- canonical Case revisions
- stable Case node identity
- explicit branch transitions
- attempt-to-revision binding
- deterministic seed revisioning
- linear compatibility
- structural graph validation
- public visibility guards
- bounded list/detail queries

It deliberately does **not** implement start/resume/current-node APIs, in-progress branch execution, multidimensional scoring, analytics, or the advanced Case Runner UI.

---

## 2. Baseline audit result

Before v0.7.1, the runtime Case structure was:

```text
ClinicalCase
  -> CaseStep
      -> CaseQuestion
          -> CaseChoice
```

`CaseStep` was ordered only by `sort_order`. `CaseChoice` carried score/feedback but no explicit next-node transition. The frontend advanced through steps using local React state and submitted every answer at the end. The backend then created a `CaseAttempt`, scored the full linear payload, completed the attempt immediately, updated progress, and recorded StudyActivity.

This meant the product had staged cases, but not a real branching case graph and not an immutable content version boundary for historical attempts.

---

## 3. Canonical v0.7.1 schema

### ClinicalCase

Added:

```text
structure_mode:
  linear
  branching

current_revision -> CaseRevision
```

`current_revision` is the authoritative published structure for new public reads and new legacy-linear attempts.

### CaseRevision

Added canonical revision ownership with:

```text
case
version
status: draft | published | retired
content_hash
entry_step
published_at
seed_managed
```

Revision-level content snapshots preserve:

```text
title
patient_summary
educational_objective
difficulty
primary_disorder
```

This avoids relying only on mutable `ClinicalCase` display fields when interpreting historical attempts.

### CaseStep

Every Case node now belongs to exactly one revision and includes:

```text
revision
stable_key
node_kind:
  decision
  information
  terminal
```

Uniqueness is revision-scoped for both `stable_key` and `sort_order`.

### CaseTransition

Branch flow is explicit rather than inferred:

```text
revision
source_step
choice       # nullable for automatic information-node transitions
target_step  # present for continue transitions
outcome:
  continue
  complete
sort_order
is_active
seed_managed
```

A choice cannot silently point outside its source node/revision through normal model validation. Continue transitions require a target; complete transitions must not have one.

### CaseAttempt

Added required:

```text
revision -> CaseRevision (PROTECT)
```

Historical attempts are therefore pinned to the exact revision they used.

### CaseAttemptAnswer

Model validation now enforces:

- selected choice belongs to the selected question
- question belongs to the same revision as the attempt

The release audit also checks existing stored answers for these invariants.

---

## 4. Migration strategy

New migrations:

```text
0022_v071_branching_case_foundation.py
0023_v071_case_revision_snapshots.py
0024_v071_case_revision_integrity.py
```

The migration path is additive and preserves existing Case content.

Existing v0.6.6 cases were backfilled into revision 1. Existing linear choices received explicit transitions to the next active step, while choices on the final step received explicit `complete` transitions.

Current real DB inventory after migration and repeated seed validation:

```text
ClinicalCase      6
CaseRevision      6
CaseStep         18
CaseTransition   54
published revs    6
blank seed hashes 0
```

Every current Case remains on revision 1 because repeated unchanged seeds are idempotent.

---

## 5. Seed revision lifecycle

`seed_mvp` now computes a deterministic SHA-256 content hash from canonical Case seed content.

Behavior:

```text
same content hash
  -> reuse current revision
  -> create no new revision

changed content hash
  -> retire old published revision
  -> create next version
  -> create fresh nodes/questions/choices/transitions
  -> set new revision as current_revision
```

The old revision is not rewritten when a later seed changes the Case.

A regression test explicitly changes seeded content after creating an Attempt and verifies:

- revision 2 is published
- revision 1 becomes retired
- revision 1 content remains unchanged
- the historical Attempt remains bound to revision 1

Two repeated real-database seed runs remained stable at `6 revisions / 18 nodes / 54 transitions`.

---

## 6. Case graph integrity rules

New module:

```text
backend/atlas/case_graph.py
```

New read-only management command:

```text
python manage.py audit_case_graphs
```

The validator checks:

- revision contains active nodes
- entry point exists and belongs to the revision
- stable node keys exist
- node/revision/case ownership is consistent
- transition source and target belong to the revision
- transition choice belongs to the source node
- inactive choice/question is not used by an active transition
- decision nodes have exactly one active question
- every active decision choice has exactly one active transition
- decision nodes do not use automatic transitions
- information nodes contain no active questions and have exactly one automatic transition
- terminal nodes contain no active questions and no outgoing transitions
- unreachable nodes
- graph cycles
- at least one completion path from the entry point

v0.7.1 intentionally treats the Case flow as a DAG. Cycles fail the release audit rather than being accepted as runtime behavior.

The management command additionally checks:

- active Case has a current revision
- current revision belongs to the Case
- current revision is published
- current revision has an entry step
- active Case has exactly one published revision
- Attempt revision belongs to the Attempt Case
- stored answer choice/question ownership
- stored answer question/Attempt revision ownership

Current real database result:

```text
Clinical case graph audit: cases=6 revisions=6 attempts=0 answers=0 failures=0
Clinical case graph audit PASS
```

---

## 7. Public API compatibility

Existing routes are preserved:

```text
GET  /api/cases/
GET  /api/cases/<slug>/
POST /api/cases/<slug>/submit/
```

List/detail payloads now expose:

```text
structure_mode
revision_number
```

Current step payloads additionally expose:

```text
stable_key
node_kind
```

Only the `current_revision` is serialized. Historical revision nodes do not leak into the current Case detail response.

Active Cases without a published current revision and valid entry point are excluded from public list/detail queries.

The old final-submit endpoint remains a compatibility path for `linear` cases only. A `branching` Case is rejected there, preventing the old all-at-once scoring service from pretending to execute a branching graph. Stateful execution belongs to v0.7.2.

Measured regression budgets on the real seeded fixture:

```text
GET /api/cases/?page_size=100                <= 3 queries
GET /api/cases/case-sudden-fear-01/          <= 4 queries
```

Serializer filtering uses prefetched revision nodes/questions/choices rather than introducing per-node queries.

---

## 8. Frontend compatibility

Canonical frontend type definitions remain in:

```text
frontend/lib/types.ts
```

`ClinicalCase` now includes:

```text
structure_mode: "linear" | "branching"
revision_number: number | null
```

Step types include:

```text
stable_key
node_kind
```

The existing linear `CaseRunner` remains functional. v0.7.1 does not fake branching behavior in local React state; the real server-authoritative branching runner is intentionally deferred to v0.7.2.

Frontend package version:

```text
0.7.1
```

---

## 9. Scientific/provenance boundary

v0.7.1 is a structural release. It does not add new clinical claims, diagnostic criteria, treatment recommendations, historical assertions, or new Case scientific content.

Therefore no new parallel Case bibliography registry was introduced merely for this schema slice. Existing project safety rules remain unchanged: future Case content enrichment must not invent scientific claims or citations, and any stronger claim-level/source architecture should reuse the existing canonical provenance strategy rather than create unsourced edges or facts.

The v0.6 scientific and research layers were re-audited after the Case changes:

```text
v0.6 provenance gaps: 0
weak-only v0.6 entities: 59
weak-only v0.6 relations: 52
weak-only rows incorrectly marked reviewed: 0
Timeline precision issues: 0
```

The exact ResearchDataset archive also remains intact:

```text
2 datasets
1918 ResearchRecord rows
both archived source JSON SHA-256 hashes PASS
```

---

## 10. Regression tests added/hardened

v0.7.1 coverage includes:

- Case submit binds Attempt to current revision
- detail reads only current revision nodes
- cycle detection
- no-completion-path detection
- changed seed creates a new revision without mutating historical attempts
- unchanged repeated seed is revision-idempotent
- active Case without valid published revision is hidden publicly
- current revision must belong to the same Case and be published
- branching Case cannot use the legacy linear submit endpoint
- CaseAttemptAnswer cannot cross revision boundaries
- public Case list/detail query budgets remain bounded
- existing inactive-disorder Case behavior remains protected
- existing low-score progress behavior remains protected

Final backend suite:

```text
136 / 136 PASS
```

---

## 11. Final validation

Backend:

```text
Django check                         PASS
makemigrations --check --dry-run     PASS / no changes
backend tests                        136 / 136 PASS
Python compileall                    PASS
pip check                            PASS
Case graph audit                     PASS
v0.6 scientific release audit        PASS
Research dataset exact verifier       PASS
seed_mvp repeated twice              PASS / stable revision counts
SQLite integrity_check               ok
SQLite foreign_key_check             0 rows
Case list query budget               <= 3
Case detail query budget             <= 4
```

Frontend:

```text
package version                      0.7.1
TypeScript typecheck                 PASS
Next.js 16.3.3 production build      PASS
static generation units              23 / 23
npm audit --audit-level=low          0 vulnerabilities
```

Production smoke:

```text
/cases                               HTTP 200
/cases/case-sudden-fear-01           HTTP 200
backend /api/cases/                  HTTP 200
backend representative case detail   HTTP 200
Chromium headless                    PASS
```

Generated `frontend/next-env.d.ts` build churn was restored rather than committed.

---

## 12. Explicitly deferred to v0.7.2+

Not implemented in v0.7.1:

```text
server-authoritative CaseAttempt start
resume current attempt
current node state
submit one decision at a time
server-resolved transition traversal
attempt event/path history
concurrency/idempotency for decision submit
branch-aware completion
multidimensional scoring
advanced branching CaseRunner UI
Case analytics
```

The immediate next slice is:

> **v0.7.2 — Server-authoritative Attempt State + Start/Resume/Decision APIs**

Its implementation should build on `CaseRevision`, `CaseStep.stable_key`, `CaseTransition`, and required `CaseAttempt.revision` rather than replacing them.
