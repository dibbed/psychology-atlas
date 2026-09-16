# Psychology Atlas v0.7.3 — Multi-dimensional Educational Scoring + Feedback

Date: 2026-09-16

## Release goal

v0.7.3 extends the revision-safe, server-authoritative Clinical Case engine from v0.7.1/v0.7.2 with a multidimensional **educational** rubric. The release does not replace the existing scalar Case score and does not introduce a psychometric or clinical-competency instrument. Instead, each scored decision may belong to one revision-owned educational dimension, and the API derives path-scoped dimension totals from immutable attempt events.

The core design rule is that scoring semantics are versioned with the Case content. A learner who started an older revision keeps that exact scoring contract; later rubric changes publish a new `CaseRevision` rather than rewriting historical attempts.

## Data model

### `CaseRevision.rubric_version`

- `0`: legacy/no multidimensional rubric.
- `1`: v0.7.3 revision-owned educational rubric.
- The field is additive and defaults to `0`, preserving old revisions and attempts without fabricated backfill.

### `CaseScoringDimension`

New revision-owned model:

- `revision`
- `stable_key`
- `label`
- `description`
- `sort_order`
- `is_active`
- `seed_managed`

`(revision, stable_key)` is unique. Dimensions are product-authored educational grouping metadata, not validated psychometric constructs.

### Question/event/answer ownership

`CaseQuestion.scoring_dimension` optionally points to one dimension from the same revision. `full_clean()` rejects cross-revision ownership.

`CaseAttemptEvent.scoring_dimension` and `CaseAttemptAnswer.scoring_dimension` preserve the dimension selected by the question at answer time. Both models validate that the dimension belongs to the attempt revision and matches the question.

For stateful events, the immutable event snapshot also stores:

```json
{
  "scoring_dimension": {
    "key": "...",
    "label": "...",
    "description": "...",
    "sort_order": 1
  }
}
```

This snapshot protects reached-path interpretation from later metadata drift and gives the release audit a historical consistency surface.

## Scoring semantics

v0.7.3 deliberately reuses the existing `CaseChoice.score_value`. It does **not** invent a second numeric scale.

For each decision event:

- awarded dimension score = selected choice `score_value`
- dimension maximum = highest active choice score for that question
- attempt scalar `score` / `max_score` continues to accumulate exactly as in v0.7.2
- the same awarded/max pair is additionally grouped by the question's scoring dimension

The dimension denominator is **path-scoped**. Only decision events actually reached in the learner's attempt are aggregated. Nodes and branches that were not traversed are not counted as missed points.

This matters for branching cases because a full-graph denominator would incorrectly penalize a learner for mutually exclusive branches.

## `dimension_feedback` API contract

`CaseAttemptStateSerializer` now returns additive `dimension_feedback`:

- `rubric_version`
- `available`
- `decision_count`
- `unscored_decisions`
- `dimensions[]`
- `review_dimensions[]`
- `message`
- `disclaimer`

Each dimension row contains:

- stable key and label
- description and sort order
- accumulated score/max score
- path-scoped percentage
- number of reached decisions in that dimension
- `needs_review`
- educational review feedback

For legacy attempts/revisions with `rubric_version=0`, the API explicitly returns no multidimensional breakdown instead of inferring one from current content.

## Progressive disclosure and frontend behavior

The current decision payload does not expose its scoring dimension before the learner answers. This avoids turning rubric metadata into an answer cue.

After a decision is committed:

- reached-path history can show the educational dimension from the immutable event snapshot
- the old choice feedback and question explanation remain visible
- score authority remains entirely server-side

After completion, `CaseRunner` shows:

- existing overall Case score and percentage
- multidimensional result cards
- score/max and percentage for each reached dimension
- decision count per dimension
- review-oriented feedback
- an explicit disclaimer that the breakdown is not diagnosis, treatment advice, professional assessment or clinical-competence measurement

The runner still never calculates branch transitions or authoritative scores on the client.

## Seeded rubric inventory

The six current seeded Clinical Cases were promoted to rubric version 1 through new revisions.

Current runtime after v0.7.3 seed:

```text
Clinical Cases:                     6
Total CaseRevisions:               12
Historical v1 revisions:            6
Current v2 rubric revisions:        6
CaseScoringDimensions:             17
Total CaseSteps:                   36
Current CaseSteps:                 18
Total CaseTransitions:            108
Current CaseTransitions:           54
Current rubric-mapped questions:   18
```

Seed dimension vocabulary currently includes:

- `information_gathering`
- `differential_reasoning`
- `safety_attention`
- `mechanism_formulation`
- `calibrated_summary`

These are educational organization labels authored for the product. They must not be interpreted as a validated clinical competency framework.

## Revision and seed safety

`case_seed_hash()` now includes rubric version, dimension inventory, each dimension's key/label/description definition, and step-to-dimension mapping. Therefore both rubric structure and rubric wording participate in Case content identity.

When the desired rubric differs from the current revision:

1. the old published revision is retired
2. a new revision number is created
3. dimensions/questions/steps/transitions are created under that new revision
4. `ClinicalCase.current_revision` moves to the new published revision
5. historical attempts stay pinned to their old protected revision

A compatibility edge case was hardened during release review: a very old seed-managed revision with no `content_hash` is no longer mutated in place when the incoming Case requires rubric v1. It publishes a new revision instead.

Repeated seed on the final v0.7.3 content is idempotent: the runtime remains at 12 revisions and 17 dimensions.

## Migration

Migration:

```text
0026_v073_multidimensional_case_scoring.py
```

It adds:

- `CaseRevision.rubric_version`
- `CaseScoringDimension`
- nullable/protected dimension bindings on `CaseQuestion`, `CaseAttemptEvent`, and `CaseAttemptAnswer`
- dimension revision/activity index and revision-scoped unique stable key

The migration is additive. Old rows remain valid with null dimension bindings and rubric version 0.

## Audit hardening

`audit_case_graphs` now checks the existing graph/state invariants plus:

- rubric v1 revisions have active dimensions
- active rubric dimensions have stable keys and labels
- rubric decision questions have a dimension
- question dimensions belong to the same revision and are active
- active dimensions are actually referenced
- event dimension belongs to the attempt revision
- event dimension matches the event question
- answer dimension belongs to the attempt revision
- answer dimension matches the answer question
- dimension event snapshots exist when required
- snapshot key/label match the preserved dimension relation
- public detail for branching cases returns no future steps/questions/choices; only the stateful attempt endpoint exposes the current reachable step
- duplicate in-progress corruption is rejected consistently by both start/resume and current-attempt endpoints
- a clean SQLite migration chain through `0022`–`0026` plus two seed runs passes graph audit
- a historical `0021` fixture with completed and in-progress attempts upgrades through `0026` with revision, transition, current-step and legacy rubric compatibility preserved

Final runtime audit:

```text
cases=6
revisions=12
dimensions=17
attempts=0
events=0
answers=0
failures=0
PASS
```

## Runtime HTTP smoke

A real local backend server was exercised with a temporary user whose password was intentionally unusable. A JWT was generated only inside the smoke process and was never printed.

Flow on `case-high-energy-04`:

```text
start: revision=2 rubric_version=1
first decision:  score 3/3
second decision: score 6/6
third decision:  completed score 9/9
```

Final path-scoped dimension result:

```text
information_gathering: 6/6 (100%)
differential_reasoning: 3/3 (100%)
unscored decisions: 0
history events: 3
```

The temporary user and cascaded attempts/events/answers were deleted in `finally`; cleanup count was verified as zero.

Frontend production route `/cases/case-high-energy-04` returned HTTP 200 from the production Next.js server. Authenticated browser form filling was not forced around the host safety layer; authenticated runtime scoring was verified through the real HTTP API instead.

## Validation

Verified on the final implementation snapshot before release metadata closeout:

```text
Focused v0.7.3 backend tests:  9/9 PASS
Full backend suite:             157/157 PASS
Django system check:            PASS
Migration drift check:          PASS
Python compileall:              PASS
pip check:                      PASS
Case graph/scoring audit:       PASS
Seed idempotency:               PASS
SQLite integrity_check:         ok
SQLite foreign_key_check:       0 violations
Frontend TypeScript:            PASS
Next.js production build:       PASS (23/23 generation units)
npm audit --audit-level=low:    0 vulnerabilities
v0.6 scientific audit:          PASS / unchanged
Research archive verifier:      PASS / 1918 exact records
```

Research archive hashes remain:

```text
psychology_atlas_research_dataset.json
753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0

psychology_atlas_research_dataset_complete___1.json
3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

## Scientific and product boundaries

v0.7.3 does not claim that its dimensions are psychometrically validated. The release intentionally avoids:

- clinical competence scoring
- therapist fitness assessment
- diagnosis from Case performance
- treatment recommendations based on dimension totals
- comparison of a learner against normative populations
- fabricated scoring thresholds or labels such as clinically competent/incompetent

The breakdown is a transparent educational summary of choices made inside one simulated scenario.

## Compatibility

- v0.7.2 state machine semantics remain authoritative.
- existing scalar score/max score are unchanged.
- exact retry idempotency and stale/skip/foreign-choice guards are unchanged.
- v0.7.2 attempts with rubric version 0 remain readable.
- the legacy linear submit endpoint remains available for compatibility and preserves dimension ownership on new answers, but the current CaseRunner continues to use only the stateful attempt engine.
- public Case detail still preserves the existing structure contract; dimension metadata is not exposed pre-decision as an answer cue.

## Deliberate boundaries for the next release

v0.7.3 does not add aggregate population analytics, cross-user comparison, node dropout dashboards or advanced attempt analytics. Those belong to **v0.7.4 Advanced Case Analytics** and should consume the immutable v0.7.2/v0.7.3 event primitives rather than create parallel state.
