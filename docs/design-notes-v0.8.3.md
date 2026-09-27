# v0.8.3 — Advanced Recommendations V2 design notes

Status: design decision record for the v0.8.3 implementation phases. No V2 code, schema, or API is implemented by this document.

## Verified starting point and ownership boundaries

Phase 1 established a clean `feature/v0.8.3-advanced-recommendations-v2` branch at `0043fe3aec72f882079bae9fc79cf1b0f0bf378a` (`origin/main` and `v0.8.2^{}` at that time). v0.8.2 is merged, tagged, released, and green in main CI. Current source and migration state must be rechecked before implementation.

The existing `backend/atlas/learning.py:get_recommendations()` is Recommendation V1. Both `GET /api/study/overview/` and `GET /api/dashboard/` call it; `frontend/components/StudyCenter.tsx` consumes the overview list. The V1 list contains `type`, `title`, `reason`, `href`, and `priority`, and currently covers due/new Flashcards plus low Disorder/Concept progress. Keep that function and both response fields unchanged in v0.8.3. V2 gets an additive endpoint and frontend consumption; no V1 item shape, ordering, or default limit changes are part of this release.

Canonical authorities remain `UserFlashcardProgress` and `review_flashcard()`/`get_review_queue()` for SRS; `QuizAttempt` and its answers; `CaseAttempt`, pinned `CaseRevision`, and `CaseAttemptEvent`; `CognitiveDistortionPracticeAttempt`; `UserProgress`, `UserConceptProgress`, and `StudyActivity`; explicit Atlas relation and source-link rows; `StudyPlan`/`StudyPlanScope`/`StudyPlanAvailability`; and `StudyBlock`/the deterministic scheduler. A recommendation is advice derived from these rows. It creates no attempt, activity, progress, plan, block, score, SRS due date, or graph relation. `StudyBlock.Origin.RECOMMENDATION` already exists but does **not** authorize automatic block creation in this slice.

`StudyPlan` is user intent, `StudyBlock` is scheduled intention/adherence, a V2 recommendation is transient advice, canonical domain rows are learning evidence, and `RecommendationFeedback` is durable feedback **about advice**. These are separate meanings. Progress percentages and Quiz/Case scores are existing educational product heuristics; V2 must not average or recast them into an overall mastery, exam readiness, competence, or pass-probability score.

## Candidate rules and source facts

V2 is a deterministic rule engine. Generate candidates from owner-scoped, currently eligible data, then deduplicate, apply active dismissals, sort, and limit. Displayed reasons state observable product facts. The following is the initial rule set; `reason_code` is a stable machine code, not rendered Persian copy. Candidate context identifiers are specified in the identity section.

| Type / reason code | Eligibility and factual reason | Action |
| --- | --- | --- |
| `overdue_block` / `block_overdue` | Owner's active-plan `StudyBlock` is pending or in progress, scheduled before the user's study-local date, with an active/actionable target. Show scheduled date and kind, never a predicted outcome. | Existing block `action_href`; also identify its plan/block in the payload. |
| `plan_schedule_stale` / `schedule_stale` | Active `StudyPlan` has `generation_version > 0` and an empty `generation_fingerprint`, using the existing `schedule_stale` meaning. | `/study/plans/<id>`; user may explicitly regenerate there. |
| `plan_generate` / `schedule_missing` | Active plan has `generation_version = 0`. | `/study/plans/<id>`. |
| `srs_review` / `srs_due` | Active-card `UserFlashcardProgress.due_at <= now`; use the same visibility filter as `available_flashcards()`. Count due cards, without freezing card IDs or changing due dates. | `/flashcards`. |
| `plan_capacity` / `plan_capacity_gap` | Freshly generated active plan only. Read `last_generation_summary` and current owner-scoped blocks/scopes. Emit one candidate when at least one supplemental fact applies: `unscheduled_backlog`, `capacity_shortfall`, `scope_without_coverage`, or `zero_usable_capacity`. State unscheduled candidate count, reported `capacity_shortfall_minutes`, configured availability, or explicit uncovered high-priority scope (`priority >= 4`). For an exam plan include nonnegative days to `target_date` as a scheduling fact, never as a standalone trigger. If summary is stale, malformed, or from a different generation version, emit `plan_schedule_stale` or `plan_generate` instead of presenting old backlog as current. | `/study/plans/<id>`; changing availability/scope or regenerating remains an explicit user action. |
| `case_resume` / `case_in_progress` | At most the latest in-progress `CaseAttempt` per Case, started/updated within 30 days, belonging to the owner and a currently accessible Case. Preserve its revision; do not reinterpret prior events or infer clinical ability. | `/cases/<slug>`. |
| `quiz_retry` / `recent_incorrect_quiz_answers` | Latest completed owner `QuizAttempt` for a currently active Quiz is within 30 days and has at least one incorrect `QuizAttemptAnswer`; inspect at most the latest 20 attempts. The reason can say how many answers were incorrect on that attempt. A newer completed attempt supersedes this context. | `/quizzes/<slug>`. |
| `distortion_practice` / `explicit_distortion_scope` | Active Concept of subtype `cognitive_distortion` is in an active owner's explicit plan scope with `include_practice=true`, and an active valid practice item exists. This is a suggestion to practice recognizing examples, never a statement about the user's thoughts or mental state. | `/cognitive-distortions#practice`. |
| `concept_review` / `concept_progress_low` | Owner's active Concept has stored `UserConceptProgress.progress_percent < 70`; this is the existing product heuristic, not a probability. | `/concepts/<slug>`. |
| `disorder_review` / `disorder_progress_low` | Owner's active Disorder has stored `UserProgress.progress_percent < 70`; same product-heuristic boundary. | `/disorders/<slug>`. |
| `graph_explore` / `reviewed_explicit_relation` | An active plan explicitly scopes an active, `reviewed` Theory. A **direct** active `TheoryConcept` row links it to an active Concept; the row has `review_status=reviewed` and at least one linked `SourceReference` with a nonblank `verification_status` other than `citation_from_model_knowledge`. Suggest reading that Concept with the stored relationship type and source citation. No multi-hop or inferred edges. | `/concepts/<slug>`. |
| `srs_start` / `srs_new` | Relevant active Flashcards exist with no `UserFlashcardProgress`, and no due-card candidate wins for the same global queue. Report a new-card count, not a due count. | `/flashcards`. |

`source_checked` is not `reviewed`. The graph rule requires `reviewed` on both Theory and relation, plus an independently checked source link; weak-only rows, inactive endpoints, and source-free rows do not qualify. `ConceptRelationship` has explicit relation semantics and source links but no relation review-status field, so this first graph rule does not silently promote its edges into reviewed advice. Graph text must attribute the stored relationship (`«این مفهوم در اطلس با نظریه X با رابطه Y ثبت شده است»`) and show citation metadata; it must not invent causality, therapeutic efficacy, or scientific certainty. If no rows meet this conservative gate, zero graph recommendations is valid.

The 30-day Quiz/Case window prevents old attempts from becoming permanent weakness labels. `not_helpful` and `helpful` do not enter candidate eligibility or ranking. No rule infers a user's diagnosis, clinical risk, mental state, personality, IQ, learning disability, therapist need, treatment suitability, exam-pass chance, exam-readiness percentage, mastery probability, or clinical competence.

## Identity and exact fingerprint

Each candidate has exactly one primary `reason_code` and a `context_ref` representing the major factual occurrence. Supplemental reason codes may enrich copy without changing identity. The canonical identity tuple is:

`["rec-v2", type, target_type, target_id, reason_code, context_ref]`

`target_id` is the database integer primary key, or JSON `null` for the global review queue. `type`, `target_type`, `reason_code`, and `context_ref` are fixed ASCII vocabulary strings. Serialize this six-element JSON array in UTF-8 using Python `json.dumps(..., ensure_ascii=True, separators=(",", ":"))`; key is `"r2_" + sha256(serialized_bytes).hexdigest()` (67 lowercase ASCII characters). Do not include user ID in the hash: owner isolation is enforced in queries and feedback uniqueness. Never include current time, local date merely because the request ran today, position, counts, progress value, priority, translated copy, title, or mutable slug. Changing a major occurrence produces a new key; repeated identical state produces the same key even if the response is requested twice.

Context examples: `srs_due` and `srs_new` use target `review_queue`, ID `null`, and refs `due_day:<YYYY-MM-DD>` and `new_day:<YYYY-MM-DD>` in the user's configured study timezone. These are explicit daily queue contexts, not the request timestamp: dismissing today's aggregate queue does not hide tomorrow's newly due cards. Low Concept/Disorder progress uses that target's PK and ref `current_progress`; stale plan uses plan PK and `generation:<generation_version>`; backlog uses plan PK and the same generation version; overdue block uses block PK and `scheduled:<YYYY-MM-DD>`; Quiz retry uses Quiz PK and `attempt:<QuizAttempt.id>`; Case resume uses Case PK and `attempt:<CaseAttempt.id>`; scoped distortion practice uses Concept PK and `plan:<plan.id>:scope:<scope.id>`; graph exploration uses Concept PK and `theoryconcept:<relation.id>:<relationship_type>:scope:<scope.id>`. These refs fit the proposed 96-character field. Use only stored IDs/dates/relation codes, never free-form client text.

Worked example: a recent incorrect attempt `91` for Quiz PK `42` yields the exact serialized bytes (shown as ASCII text):

`["rec-v2","quiz_retry","quiz",42,"recent_incorrect_quiz_answers","attempt:91"]`

Its key is `r2_abd11712d8ebc0fe25cdc9be158dc3e9a3688254150b80a01443633344eafcd2`. Changing the count of wrong answers on that same immutable attempt does not change the key; a later completed attempt uses a different `attempt:<id>` and therefore a different key. A stale plan with PK `17` and last generation `3` analogously uses `[...,"plan_schedule_stale","study_plan",17,"schedule_stale","generation:3"]`; regeneration followed by a later stale schedule changes the generation context.

## Ordering and deduplication

Priority is an **ordering priority only**, never a scientific weight. Fixed tier values are: overdue block `120`; stale plan `110`; missing plan schedule `105`; due SRS `100`; plan capacity/backlog `90`; Case resume `80`; Quiz retry `70`; scoped distortion practice `60`; low Concept progress `50`; low Disorder progress `50`; reviewed direct graph exploration `40`; new SRS `30`. Counts, scores, percentages, age, and target-date proximity do not numerically raise priority. Plan capacity is a single candidate even when several of its factual reason codes apply.

Sort by `(priority descending, reason_rank ascending, scheduled_date ascending where relevant else "9999-12-31", target_type ascending, target_slug ascending, key ascending)`. The fixed reason ranks are overdue block `1`, stale plan `2`, missing schedule `3`, due SRS `4`, plan capacity `5`, Case resume `6`, Quiz retry `7`, Distortion practice `8`, low Concept/Disorder progress `9`, graph exploration `10`, and new SRS `11`. Slugs are for a readable stable tie break, with the key as final tie breaker. Explicit `.order_by()` or in-memory sorting must implement the order; never rely on model default ordering. `order` in the response is a one-based position after sorting, deduplication, dismissal, and limit.

Dedup happens before feedback lookup and output limit, using these exact rules:

1. For the same plan, keep `plan_schedule_stale` ahead of `plan_generate` and `plan_capacity`; missing/stale schedule makes old backlog ineligible. Fold `unscheduled_backlog`, `capacity_shortfall`, `scope_without_coverage`, `zero_usable_capacity`, and target-date facts into one `plan_capacity` item and its bounded `reason_codes`/`signals`.
2. For the same actionable `StudyBlock` and immediate action, emit at most one overdue-block item. If a pending/in-progress owner block for **today or earlier** already directs the same Quiz, Case, Concept reading, Disorder reading, Distortion practice, or global Flashcard review, suppress the corresponding generic Quiz retry, Case resume, Concept/Disorder review, Distortion practice, or SRS queue candidate. Future blocks do not suppress an action needed now. An overdue block wins because the user's existing schedule is the most specific action.
3. Only one global `/flashcards` queue item survives: due SRS wins over new SRS. A same-day/overdue Flashcard block wins over both. Never emit a per-Concept Flashcard candidate alongside this global queue candidate.
4. For the same target Concept and reading action, `concept_review` wins over `graph_explore`; among multiple reviewed relations to that Concept, choose the smallest `(scope.id, relation.id)` after eligibility filtering. The graph candidate is exploratory reading, not a second name for low progress. Distortion **practice** remains a distinct action from Concept reading unless a matching practice block already wins.
5. For each Quiz use its most recent eligible completed attempt; for each Case use its one eligible in-progress attempt. Duplicate candidate keys or identical `(action_kind, target_type, target_id, context_ref)` are collapsed with the documented tier order. No near-duplicate advice is created merely to fill the result limit.

## Feedback persistence and migration

The actual current migration tip is `backend/atlas/migrations/0030_studyblock_ck_study_block_started_status_and_more.py`, which depends on `0029_v082_study_blocks` and adds three StudyBlock lifecycle timestamp/status `CheckConstraint`s. No `RecommendationFeedback` or equivalent feedback model exists. The **next proposed migration is `0031_v083_recommendation_feedback.py`**, depending on that exact `0030` migration and the swappable user model. It is additive, creates no historical feedback rows, and must not alter existing progress, attempt, plan, block, or SRS tables.

Proposed `RecommendationFeedback` is an append-only event model, not a Recommendation cache or new learning-evidence table. Exact fields:

| Field | Type / rule |
| --- | --- |
| `id` | `BigAutoField`, primary key. |
| `user` | FK to `settings.AUTH_USER_MODEL`, `CASCADE`, nonnull; ownership always comes from the authenticated request. |
| `recommendation_key` | `CharField(max_length=67)`, nonnull; service validates `^r2_[0-9a-f]{64}$`. |
| `recommendation_type` | `CharField(max_length=32)`, nonnull; one of the V2 types above. |
| `target_type` | `CharField(max_length=32)`, nonnull; `review_queue`, `study_plan`, `study_block`, `quiz`, `clinical_case`, `concept`, or `disorder`. |
| `target_id` | `PositiveBigIntegerField(null=True, blank=True)`; null only for `review_queue`. No generic FK or guessed cross-domain target. |
| `reason_code` | `CharField(max_length=48)`, nonnull; the candidate's primary reason code. |
| `context_ref` | `CharField(max_length=96)`, nonnull; exact identity context string above. |
| `value` | `CharField(max_length=16)` with choices `helpful`, `not_helpful`, `dismissed`. |
| `client_event_id` | `UUIDField`, nonnull; one client-generated identifier per intended feedback action. Unique together with `user` for retry idempotency. |
| `suppressed_until` | `DateTimeField(null=True, blank=True)`; populated only for `dismissed`, exactly seven days after event creation, and null for other values. |
| `created_at` | `DateTimeField(default=timezone.now, editable=False)`, nonnull. Set from the same captured transaction timestamp used to calculate dismissal expiry. No update field: history is append-only. |

Constraints/indexes: unique `(user, client_event_id)`; check `value` in the three choices; check `suppressed_until IS NOT NULL` iff `value='dismissed'`; index `(user, recommendation_key, -created_at, -id)` for latest state and `(user, -created_at)` for owner history/abuse controls. Validate `suppressed_until > created_at` in the service. Historical feedback is retained as separate events even when a later action changes the current state; user deletion cascades their private feedback. Store no inferred weakness label, rendered reason text, diagnosis, or source/history blob.

The current event for a key is the owner's latest `(created_at, id)` row. `dismissed` suppresses **only that exact key** for seven days; it does not suppress a new Quiz attempt, different plan generation, different block, or every future suggestion about a Concept. After expiry the advice may reappear if still eligible, with `feedback.value=null` in the active list; historical events remain. `not_helpful` records product feedback only and does not suppress, demote, or mark a topic as disliked, mastered, or bad. `helpful` never becomes learning evidence or a ranking boost. No snooze action is added: bounded dismissal already covers the needed temporary suppression without a second timing concept.

## Additive API contract

Use the existing `/api/` prefix, DRF authenticated function views, snake_case JSON, and `{code, detail, errors?}` error pattern. Do not replace V1 `recommendations` in `/api/study/overview/` or `/api/dashboard/`.

`GET /api/study/recommendations/?limit=8` returns V2 only. `limit` defaults to 8, accepts ASCII decimal integers `1..20`, and rejects booleans, signs, whitespace, nonnumeric text, extra query parameters, and larger values with HTTP 400 and `code="recommendation_invalid_query"`. No offset pagination in this slice because moving time-sensitive candidates across pages would make feedback/navigation unstable. The response has `version: "v2"`, `as_of` (server ISO timestamp, excluded from keys), `items`, `returned_count`, `suppressed_count`, and `truncated_sources` (true if a documented source cap was hit). Counts are owner-only and bounded by the evaluated candidate window, not promises about all historical data.

Each item is bounded to this shape:

```json
{
  "key": "r2_abd11712d8ebc0fe25cdc9be158dc3e9a3688254150b80a01443633344eafcd2",
  "type": "quiz_retry",
  "target": {"type": "quiz", "id": 42, "slug": "example-quiz"},
  "priority": 70,
  "order": 1,
  "title": "مرور پاسخ‌های این آزمون",
  "description": "در آخرین تلاش، چند پاسخ نادرست ثبت شده است؛ می‌توانی دوباره تمرین کنی.",
  "reason_codes": ["recent_incorrect_quiz_answers"],
  "reasons": ["آخرین تلاش این آزمون در ۳۰ روز اخیر ثبت شده است."],
  "signals": [{"kind": "quiz_attempt", "id": 91, "incorrect_answers": 2}],
  "action": {"href": "/quizzes/example-quiz", "label": "تمرین دوباره"},
  "feedback": {"value": null, "suppressed_until": null}
}
```

`signals` contains at most four factual, owner-scoped summaries, never full attempt answers/events or a speculative label. For graph advice it may contain `relation_type`, relation ID, and at most two cited source IDs/titles/URLs; expose the actual stored relation semantics and review status. `reason_codes`/`reasons` each have at most four entries; title/description length is bounded. Validate target activity and action path again before response; no raw user-provided URL is accepted.

`POST /api/study/recommendations/<str:key>/feedback/` accepts exactly `{"value":"helpful|not_helpful|dismissed","client_event_id":"<UUID>"}` as an object; reject unknown fields, missing/invalid UUID, invalid value, malformed key, or oversized body with HTTP 400 `code="recommendation_feedback_invalid"`. Never accept `user`, `target`, `reason`, `priority`, or expiry from the client. After authentication and strict parsing, check `(request.user, client_event_id)` for a replay first, so a legitimate retry still succeeds if the underlying recommendation has since expired. For a new event, recompute the owner's **pre-dismissal** candidate set under the same bounded rules, find the exact key, and derive all stored identity fields from that candidate. Unknown, foreign, no-longer-eligible, or deduplicated-away keys return the same generic HTTP 404 `code="recommendation_not_found"`; key knowledge is not authorization. A valid suppressed candidate can receive new feedback without an `include_dismissed` list mode.

Within a transaction, replay of an existing `(user, client_event_id)` with the same key/value returns the existing action result without another row or extending dismissal; reuse with different key/value returns HTTP 409 `code="recommendation_feedback_conflict"`. If the latest event for that key already has the same value and, for dismissal, its `suppressed_until` is still in the future, return the latest state without appending or extending it. Otherwise append a new event; a new `helpful` or `not_helpful` event clears active dismissal because it becomes the latest state. A newly dismissed item gets `suppressed_until=created_at + 7 days`. Serialize concurrent writes for one owner/key (including SQLite retry handling) so double clicks cannot append contradictory current events. Response: `{key, feedback: {value, suppressed_until}, recorded_at}`. A per-user daily event cap of 100 new events returns HTTP 429 `code="recommendation_feedback_limit"`; idempotent replays do not count. Candidate validation plus this cap prevents arbitrary client keys from generating unbounded junk rows.

All personal reads and writes require authentication. Queries for plans, blocks, attempts, progress, and feedback start with `user=request.user`; any target resolved from a candidate is rechecked against its canonical active/runnable boundary. Do not reveal whether another owner's plan, block, attempt, feedback, or key exists. Graph/content rows can be public, but the user's reason for seeing a relation remains private. Neither endpoint silently mutates planning or learning state.

## Bounded execution and regression evidence required in implementation phases

Use one captured `now` per request. Candidate source caps: 20 active plans (stable `-updated_at,-id`), 50 actionable overdue blocks (`scheduled_date,id`), latest 20 completed Quiz attempts within 30 days, 20 recent in-progress Case attempts, 10 low-progress Concepts, 10 low-progress Disorders, 20 explicit Distortion scopes, 20 direct graph relations, and a maximum 200 candidates before final dedup/limit. Set `truncated_sources=true` when any cap is hit. Fetch related data in batches (`select_related`, `prefetch_related`, grouped wrong-answer counts, owner-key feedback batch); avoid a per-candidate query. Verify an explicit query budget on populated fixtures in Phase 3; the cap is a safety bound, not evidence of acceptable query count.

Required tests: V1 study-overview and dashboard payload/list regression; V2 fixed-state repeated request identity and ordering (including timezone/date boundary), key examples, strict query validation, deterministic tie breaks, candidate/source caps; due/new SRS and inactive content; recent Quiz errors with a newer attempt and 30-day expiry; Case revision-safe/in-progress visibility; educational Distortion wording; fresh/stale/zero-capacity/exam-plan facts without readiness claims; explicit reviewed/source-backed one-hop graph relation and weak-only exclusion; all dedup precedence cases; feedback replay/change/expiry/concurrent submission/daily cap; forged and foreign keys returning generic 404; no canonical evidence, due date, plan, or block mutation; fresh migration and historical `0030 -> 0031` upgrade preserving existing data. Check schema drift, full affected backend suite, frontend typecheck/build, and existing CI gates during later phases. This document makes no claim that those future tests have passed.

## Deliberate Phase 3 implementation choices and later cleanup

Phase 3 may choose the exact Python module split for the V2 rule engine, serializers/helpers, transaction retry implementation, and the database-query plan after measuring fixtures. It may tune **query budgets** from measured evidence without changing the source caps, eligibility, ordering, identity, or API contract above. Persian wording and frontend presentation can be refined in the frontend phase while retaining factual reason codes and scientific boundaries. If a proposed rule cannot be supported by the current canonical data under these gates, Phase 3 should document the missing evidence and omit that rule rather than invent a proxy. No product/schema/API decision listed above is intentionally left open.

Known v0.8.2 copy debt is **not** edited in this design phase: `docs/Psychology_Atlas_v0.8.2_Study_Blocks_Deterministic_Scheduler_2026-09-26.md` still describes PR/tag/Release as pending despite verified closeout (docs/ship cleanup), and `frontend/components/StudyCenter.tsx` still says daily scheduling is future work (frontend cleanup). These do not change the V2 architecture.

Out of scope for v0.8.3: StudySession, Today Study Command Center overhaul, Today orchestration endpoint, session timers, automatic session logging, session adherence analytics, recommendation-driven automatic plan/block mutation, Brain Atlas, and Assessments Atlas. The design makes no decision for v0.8.4.
