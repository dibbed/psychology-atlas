# v0.8.4 — Today Study Mode + Study Sessions + UI: design notes

Status: **design only**, 2026-09-29. This document freezes the contract for later implementation phases. It does not claim that the schema, routes, UI, migration, or tests exist.

## Verified starting point and authority

The Phase 1 branch is `feature/v0.8.4-today-study-sessions` at `24e04e5277723c95dd414dcc0e20a117afd7ab79`, equal to `origin/main` after fetch. The v0.8.3 tag peels to `1a9acef59a70ff894fda02d4383693b61c0084b4`; two later frontend commits are in this baseline. `backend/atlas/migrations/0031_v083_recommendation_feedback.py` is the actual migration tip and is applied locally. The frontend package declares `0.8.3`. Source inspection found no `StudySession`, `StudySessionItem`, `/api/study/today/`, or server session timer.

Current sources to preserve: `backend/atlas/models.py`, `study_planning.py`, `study_scheduler.py`, `learning.py`, `services.py`, `recommendations_v2.py`, `recommendation_views.py`, `views.py`, `urls.py`, `tests.py`; `frontend/components/StudyCenter.tsx`, `StudyRecommendationsV2.tsx`, `FlashcardReview.tsx`, `QuizRunner.tsx`, `CaseRunner.tsx`, `frontend/app/study/**`, `frontend/lib/types.ts`, `frontend/lib/api.ts`, `frontend/app/globals.css`, and the post-v0.8.3 `frontend/app/redesign.css`. The v0.8.1–v0.8.3 release documents and `PROJECT_SPEC.md` are historical constraints; current source wins on runtime details.

The ownership boundary is fixed:

| Record | Meaning |
| --- | --- |
| `StudyPlan`, availability, scope, settings | User intent and configuration. |
| `StudyBlock` | Scheduled intention and plan adherence, with existing completion evidence rules. |
| `StudySession` | One user's focused-study orchestration and self-reported adherence window. |
| Recommendation V2 and `RecommendationFeedback` | Advice and feedback about advice. |
| `UserFlashcardProgress`, `QuizAttempt`, `CaseAttempt`, `CaseAttemptEvent`, `DailyChallengeAttempt`, `CognitiveDistortionPracticeAttempt`, `StudyActivity`, `UserConceptProgress`, and `UserProgress` | Canonical learning evidence. |

Session completion does **not** assert mastery, exam readiness, knowledge probability, clinical competence, verified attention, or successful completion of its block or every underlying activity. No new clinical diagnosis, treatment advice, psychometric scoring, exam-pass probability, notification infrastructure, calendar integration, FSRS rewrite, or social/XP feature belongs to this slice.

## StudySession persistence and migration

Add exactly one model, `StudySession(TimeStampedModel)`, to `atlas`. The migration filename is **`0032_v084_study_sessions.py`**, depending on `0031_v083_recommendation_feedback`. It is additive: no data migration or fabricated session rows, and no changes to Plan, Block, SRS, attempts, feedback, or scientific content. Phase 3 must recheck the migration graph before creating the file; if another migration lands first, reconcile rather than force this number.

| Field | Exact design |
| --- | --- |
| `id` | Repository's default Django `BigAutoField` primary key. |
| `user` | `ForeignKey(settings.AUTH_USER_MODEL, CASCADE, related_name="study_sessions")`, non-null. Account deletion removes personal sessions. |
| `plan` | `ForeignKey(StudyPlan, CASCADE, related_name="sessions")`, non-null. v0.8.4 sessions are block anchored; no ad-hoc session start. There is no public hard-delete Plan API; Plan archive retains sessions. A privileged hard deletion follows the existing Plan/Block cascade boundary. |
| `primary_block` | `ForeignKey(StudyBlock, SET_NULL, null=True, blank=True, related_name="study_sessions")`. Required at creation; nullable afterward only to preserve a session if its Block is hard deleted outside the public flow. No public block delete exists. A session with a missing block offers no stale canonical action. |
| `block_id_at_start` | `PositiveBigIntegerField`, non-null and immutable. Snapshots the original block ID for event replay and history if `primary_block` becomes null. It is an identifier, not completion evidence. |
| `client_event_id` | `UUIDField`, non-null; the caller's durable start idempotency token. Never supplied by the server after a write as a substitute for client retry reuse. |
| `status` | `CharField(max_length=16, choices=in_progress/completed/abandoned, default=in_progress)`. |
| `planned_minutes` | `PositiveSmallIntegerField`, integer 5..240. User intent for this focus window, not the block's estimated duration. |
| `started_at` | `DateTimeField`, non-null, set from one server `timezone.now()` captured during successful start. |
| `completed_at`, `abandoned_at` | Nullable `DateTimeField`s; exactly one is set for the corresponding terminal status. |
| `actual_seconds` | `PositiveIntegerField(default=0)`, 0..86,400. Server-calculated, capped wall-clock elapsed seconds; zero while active. It is neither attention proof nor learning evidence. |
| `created_at`, `updated_at` | Inherited from the existing `TimeStampedModel`. |

Database constraints (named to match the repository's `ck_`/`uq_` convention): `uq_study_session_active_user` is a conditional unique constraint on `user` where `status='in_progress'`; `uq_study_session_event` is unique on `(user, client_event_id)`; `ck_study_session_block_id` requires `block_id_at_start > 0`; `ck_study_session_minutes` enforces 5..240; `ck_study_session_seconds` enforces 0..86,400; `ck_study_session_lifecycle` accepts only the three status/timestamp combinations: active has no terminal timestamp and zero seconds, completed has only `completed_at >= started_at`, abandoned has only `abandoned_at >= started_at`. The lifecycle check also excludes unknown status values. Explicit indexes: `(user, -started_at, -id)` for personal history and `(plan, -started_at, -id)` for bounded plan history. The partial unique active index serves current-session lookup. Do not add redundant user/status indexes without measured need.

Cross-row rules cannot be encoded by ordinary Django `CheckConstraint`s: `plan.user_id == user_id`, `primary_block.plan_id == plan_id`, and `primary_block.plan.user_id == user_id`. Enforce them under the service transaction on every start and reject inconsistent direct model writes with `clean()`; include corruption detection in a read-only audit or focused integrity test. Store no user-supplied `user_id`, plan ID, target URL, completion evidence, score, or arbitrary metadata. Session rows do not mutate Block status.

**No `StudySessionItem` in v0.8.4.** One primary Block supplies the focused action; the existing Plan/Block tables supply schedules; Today computes a bounded next action on read. There is no evidenced requirement for an independently persisted, ordered multi-item queue. Canonical actions outside a Block remain directly available without a Session. Adding items would create a second scheduling authority and unresolved completion semantics.

## Timing, lifecycle, and concurrency

The server is the time authority. Capture `timezone.now()` once for a successful transition. On completion or abandonment, set the corresponding end timestamp to `max(now, started_at)` to tolerate a small backward wall-clock adjustment and satisfy timestamp checks. Compute raw elapsed as `max(0, floor((end-start).total_seconds()))`; persist `actual_seconds=min(raw_elapsed, 86400)`. The end timestamps preserve the raw wall-clock interval, while `actual_seconds` deliberately caps it at 24 hours. A browser left open for hours or days does not accrue verified attention. This assumes reasonably synchronized server clocks; a large forward jump can inflate the wall interval to the cap, and a backward jump is floored at zero. No client clock or monotonic timer is used to rewrite persisted timestamps across requests/processes. `planned_minutes` is not automatically revised; no session elapsed value enters Today capacity or progress/mastery. Client timer ticks are display-only. Active response `elapsed_seconds` is the same capped calculation from `as_of - started_at`; `elapsed_capped` flags a raw interval above the cap. Terminal responses use persisted `actual_seconds` and the same flag derived from timestamps. Show the planned duration separately; never label the elapsed interval as focused attention.

Start requires an owned, active-plan, pending or in-progress Block with a currently active/runnable target under `study_scheduler`'s existing target checks. Requiring an **active** Plan is intentionally stricter than the existing Block-completion method, which currently rejects only archived/completed Plans; it prevents starting a new focus window from a paused or draft Plan without changing old Block behavior. Future-dated actionable Blocks may be started explicitly; Today only proposes due/today Blocks. An own inactive Plan, skipped/superseded/completed Block, inactive target, or mismatched relationship cannot start. A stale generation summary alone does not invalidate a preserved actionable Block. Start neither changes `StudyBlock.status`/`started_at` nor generates, reschedules, completes, or creates another Block. The two no-target kinds already in the Block enum get a clear v0.8.4 action: `notes_review -> /notes` and `daily_challenge_optional -> /study#daily-challenge`. This is a Today/Session presentation mapping; it does not silently change the released v0.8.2 Block response's `/study` fallback. A `daily_challenge_optional` Block is session-startable only when scheduled for the owner's current study day and the existing app-day Challenge is available and incomplete. Neither no-target kind currently has a normal scheduler producer.

Inside an atomic start transaction: check the caller's `(user, client_event_id)` replay first; lock the user row to serialize per-owner starts on PostgreSQL; resolve and lock the owner-scoped Plan and Block in that stable order; validate eligibility; inspect the owner's active Session; then create. The partial unique constraint is the final race guard on both SQLite and PostgreSQL. On SQLite, `select_for_update()` is insufficient: use the repository's bounded retry pattern only for detected transient `database is locked` errors, outside a rolled-back atomic attempt. On a relevant unique `IntegrityError`, roll back, re-read the owner-scoped event replay first and then the active Session, and apply the contract below; do not retry blindly or turn unrelated integrity failures into success. PostgreSQL relies on row locks plus the same unique constraints. Concurrent different-Block starts yield one creation and one conflict; concurrent equivalent starts yield one row.

An exact event-ID replay returns its original Session, including if it has since completed or been abandoned, with HTTP 200. Compare the requested `primary_block_id` with immutable `block_id_at_start`; compare `planned_minutes` only if explicitly supplied. Reusing an event ID for a different Block or explicitly different duration is HTTP 409. If a different event ID targets the same active Block with the same effective planned minutes, return that active Session with HTTP 200; this is an *active-state* equivalence, not a new durable alias for the second event ID. A different Block or duration while any Session is active returns HTTP 409. The UI must generate one UUID per explicit Start click and retain it across network retries or refresh recovery. A later deliberate Start after terminal transition uses a new UUID. This distinguishes a stale browser retry from a new session.

`complete` moves only `in_progress -> completed`; repeating it on an already completed Session is idempotent HTTP 200 with unchanged timestamps/seconds. `abandon` similarly moves only `in_progress -> abandoned` and repeats as HTTP 200. Crossing terminal states is HTTP 409. Completion/abandon remain possible if the Plan was later archived, the target became inactive, or the Block was deleted; they close an already-owned time window and do not assert Block success. GETs do not expire, abandon, or otherwise mutate Sessions automatically.

## Session HTTP contract

All routes are authenticated, under `backend/atlas/urls.py`, with existing trailing-slash conventions:

| Method and route | Request | Success |
| --- | --- | --- |
| `POST /api/study/sessions/` | Exact JSON object `{ "primary_block_id": positive integer, "client_event_id": UUID, "planned_minutes"?: integer }`. Omitted minutes use the owner's `default_session_minutes`; explicit value must be 5..240 and no more than `default_daily_minutes`. | 201 `{ "session": Session, "created": true }`; exact replay or equivalent active Session: 200 with `created:false`. |
| `GET /api/study/sessions/current/` | No query parameters. | 200 `{ "session": Session|null }`. No active Session is normal, not 404. |
| `GET /api/study/sessions/<int:id>/` | No query parameters. | 200 `{ "session": Session }`. |
| `POST /api/study/sessions/<int:id>/complete/` | Empty JSON object `{}`. | 200 `{ "session": Session }`. |
| `POST /api/study/sessions/<int:id>/abandon/` | Empty JSON object `{}`. | 200 `{ "session": Session }`. |

An empty POST body may be normalized to `{}` only for complete/abandon; JSON arrays, scalars, malformed JSON, oversized bodies (>1024 bytes), unknown fields, Boolean-as-integer values, invalid UUIDs, and extra query parameters are rejected. Start requires its two fields. The normal Session object has exactly: `id`, `status`, `plan_id`, `primary_block_id`, `block_id_at_start`, `planned_minutes`, `started_at`, `completed_at`, `abandoned_at`, `actual_seconds`, `elapsed_seconds`, `elapsed_capped`, `as_of`, `created_at`, `updated_at`, and `primary_block`. ISO 8601 aware timestamps or `null`; `primary_block` is a compact object `{id, plan_id, block_kind, status, scheduled_date, estimated_minutes, snapshot_title, action_href, target_active, evidence_required}` or `null`. `action_href` is `null` when the target is no longer actionable; no raw client URL is accepted. `client_event_id` is omitted from reads and returned Session payloads; the client already owns its retry token.

Stable error body is `{ "code": string, "detail": string }`, optionally `errors` for field validation. Codes/statuses: `study_session_invalid` (400 body/field/size), `study_session_invalid_query` (400 query), `study_session_not_found` (404 foreign or missing Session), `study_block_not_found` (404 foreign or missing start Block), `study_session_block_unavailable` (409 owned but nonactionable Block/target/Plan), `study_session_event_conflict` (409 event token reused for different intent), `study_session_active` (409 different active request), and `study_session_transition_conflict` (409 crossed terminal transition). Check replay under `user=request.user` before checking whether its original Block still exists. All Session ID lookups begin with `user=request.user`; cross-owner Session, Plan, and Block existence is never disclosed. Authentication uses the existing DRF/JWT boundary and returns its established 401 response.

## Today API: exact read contract

`GET /api/study/today/` is authenticated, accepts no query parameters (otherwise 400 `study_today_invalid_query`), and returns HTTP 200. Capture one aware `now` and use it for classifications, Session elapsed display, and the nested Recommendation V2 read. It is **read-only**: do not call `study_settings_for_user()` or `get_study_plan_schedule()`, which can lazily create settings; do not regenerate Plans, write feedback, update Session state, or alter Blocks. Read a saved `UserStudySettings` row or use the same app-timezone/default-setting fallback as existing V2 reads without inserting a row.

The JSON object has exactly these top-level keys:

```json
{
  "version": "v1",
  "as_of": "2026-09-29T09:00:00+00:00",
  "local_date": "2026-09-29",
  "timezone": "Asia/Tehran",
  "capacity": {
    "available_minutes": 45,
    "scheduled_minutes": 50,
    "completed_minutes": 20,
    "remaining_minutes": 25,
    "over_capacity_minutes": 5
  },
  "active_session": null,
  "review": { "due": 6, "overdue": 2, "new": 3 },
  "active_plans": { "total": 2, "items": [], "truncated": false },
  "today_blocks": { "total": 3, "items": [], "truncated": false },
  "overdue_blocks": { "total": 1, "items": [], "truncated": false },
  "daily_challenge": {
    "challenge_date": "2026-09-29",
    "available": true,
    "completed": false,
    "action": { "href": "/study#daily-challenge", "label": "چالش روزانه" }
  },
  "next_action": {
    "kind": "today_block",
    "reason_code": "block_due_today",
    "target": { "type": "study_block", "id": 12 },
    "plan_id": 4,
    "block_id": 12,
    "recommendation_key": null,
    "can_start_session": true,
    "action": { "href": "/quizzes/example", "label": "شروع فعالیت" }
  },
  "recommendations": {
    "version": "v2", "as_of": "2026-09-29T09:00:00+00:00",
    "items": [], "returned_count": 0, "suppressed_count": 0,
    "truncated_sources": false
  }
}
```

This is a shape example, not fixture data or a claim about the runtime database. `active_session` is the Session object above or `null`. Each `active_plans.items` entry is `{id, name, plan_kind, target_date, days_remaining, generation_version, schedule_stale, today_available_minutes}`; `days_remaining` is a signed integer (`target_date - local_date`) or `null`, never readiness. Each Block item is `{id, plan_id, block_kind, status, scheduled_date, sequence, estimated_minutes, snapshot_title, scope_priority, action_href, target_active, evidence_required, can_start_session}`. `scope_priority` is 1..5 or `null`; it is a plan ordering input, not scientific importance. Block lists contain only pending/in-progress, active-plan, currently actionable targets; an unavailable Block is omitted from actionable lists and cannot be selected. `today_blocks` is scheduled on `local_date`; `overdue_blocks` is scheduled earlier. Thus Block list totals do not include completed rows even though completed estimates enter capacity. Each list has an exact total count computed independently of its cap; items are limited to 20 and `truncated = total > items.length`. Active Plan items are limited to 20, ordered by `id`; capacity and block totals still use all eligible active Plans. Both Block lists order by descending scope priority (null last), then oldest `scheduled_date`, `sequence`, `plan_id`, `id`. Keep serializer fields bounded; do not embed scopes, availability arrays, schedule summaries, attempt answers, Case event history, or full catalog content.

`review.due` counts visible owned `UserFlashcardProgress` with `due_at <= now`; `overdue` is the subset with `due_at` before the start of the owner's `local_date` in the study timezone; `new` counts visible cards without a progress row. These are counts, not frozen card selections. `daily_challenge.challenge_date` and `completed` use the **existing application-timezone** `DailyChallengeAttempt.activity_date` semantics; `available` requires a valid active challenge, while an existing attempt still counts as completed if its challenge later becomes inactive. Its action is `null` if unavailable or completed. The frontend adds an anchor to the existing `DailyChallengeCard`; no duplicate challenge engine is introduced. Recommendations is the existing V2 response contract with the normal default limit of 8, including current feedback and suppression.

### Today capacity and timezone

Let `D` be the owner's study-local date and `W` its Python weekday. Let `G` be the saved `default_daily_minutes`, or the model default when settings are absent. Let `A` be the sum of `available_minutes` for weekday `W` across **all active owned Plans**, treating absent/corrupt weekday rows as zero for this read and surfacing the Plan as needing configuration through existing Plan UI/advice. Then `available_minutes = min(G, A)`; with no active Plan or zero availability it is zero. This uses the global daily limit already used by the scheduler's cross-plan overcapacity report and does not add per-Plan capacities together without a global bound.

For all owner Blocks on `D` whose Plan is active and status is pending, in-progress, or completed (excluding skipped/superseded), `scheduled_minutes = sum(estimated_minutes)`. A completed Block still contributes even if its content later becomes inactive; the schedule/adherence history remains. `completed_minutes` is the subset with status completed, also from **Block estimates**, not Session elapsed time or canonical scores. `remaining_minutes = max(available_minutes - completed_minutes, 0)` describes configured capacity not yet marked complete; it is not a free unscheduled slot. `over_capacity_minutes = max(scheduled_minutes - available_minutes, 0)` exposes overlapping Plans and excess schedule explicitly. For an unscheduled optional action, define `unscheduled_headroom = max(available_minutes - scheduled_minutes, 0)` internally; this is not another response field. Zero availability can coexist with scheduled or completed Blocks and must report the overage without hiding it. Do not clamp scheduled/completed sums, silently move Blocks, or treat minutes as measured learning. All five response values aggregate the full eligible set, not only the 20 displayed rows.

`local_date`, Block today/overdue classification, Plan `days_remaining`, SRS-overdue midnight, and capacity weekday use `UserStudySettings.study_timezone` (valid IANA zone, fallback to configured application timezone without a GET write). Due SRS eligibility still uses absolute `due_at <= now`. Daily Challenge continues to use the app timezone and its existing one-attempt-per-app-day unique constraint; do not reinterpret historical challenge rows. When study and app dates differ near midnight, return both `local_date` and `daily_challenge.challenge_date` and use each for its own authority.

### Deterministic next action

Return exactly one `next_action`, never a score. Its fixed shape is shown above; `target.type` is one of `study_session`, `clinical_case`, `study_block`, `review_queue`, `daily_challenge`, `study_plan`, `quiz`, `concept`, `disorder`, or `none` (the Recommendation V2 fallback retains V2's actual target type); `target.id`, `plan_id`, `block_id`, and `recommendation_key` are nullable. `can_start_session` is true only for an actionable Block candidate. The action URL is a server-derived local canonical path, never user input. Selection uses this strict precedence:

1. Active owned Session: `resume_session`, reason `session_in_progress`; action `/study/session/<id>`. If its Block/Plan/target later becomes unavailable, still resume the Session with reason `session_focus_unavailable`; the focused page offers a safe close path and no invalid content action.
2. A recent resumable owned `CaseAttempt` within the V2 30-day window, for a runnable Case and its pinned valid revision: `resume_case`, reason `case_in_progress`, action `/cases/<slug>`. Tie: latest `updated_at`, then largest attempt ID. Reuse a shared canonical Case eligibility/resumability predicate with V2 rather than copying its rule; this step represents an active attempt and remains independent of whether advice about that attempt was dismissed. The current Quiz API creates and completes attempts in one submission and has no resumable in-progress runner, so **no Quiz-resume candidate is fabricated** in v0.8.4.
3. An actionable overdue Block: `overdue_block`, reason `block_overdue`; select highest scope priority first, then oldest date, sequence, plan ID, Block ID.
4. An actionable Block on `D`: `today_block`, reason `block_due_today`; same priority rule, then sequence, plan ID, Block ID.
5. Visible due SRS cards: `srs_review`, reason `srs_overdue` when the overdue subset is nonzero, otherwise `srs_due`; action `/flashcards`. Canonical SRS chooses individual cards at runtime.
6. Valid, incomplete Daily Challenge if `remaining_minutes > 0` **and** `unscheduled_headroom > 0`: `daily_challenge`, reason `challenge_available`; action `/study#daily-challenge`. An overbooked schedule never creates a fictional free slot for this optional suggestion.
7. The first still-visible, non-dismissed item in the nested Recommendation V2 response: `recommendation`, reason `recommendation_v2`, carrying its key, target, and canonical action exactly as returned by V2. No extra ranking or feedback interpretation.
8. Deterministic onboarding: if no Plans, `create_plan` -> `/study/plans/new`; if Plans exist but none is active, `review_plans` -> `/study/plans`; otherwise the lowest-ID active missing/stale schedule Plan gives `prepare_schedule` -> `/study/plans/<id>`; otherwise new SRS cards give `srs_new` -> `/flashcards`; otherwise `review_plans` -> `/study/plans`. These are `kind=onboarding` with the indicated reason codes.

For `resume_session`, `target.id` is the Session ID and `plan_id`/`block_id` reflect that Session (the latter may be null after Block deletion). For `resume_case`, `target.id` is the Case ID, not an attempt or revision ID; the existing Case route resumes the owned attempt. Block actions use `target.id=block_id` and its `plan_id`. SRS uses `{type:"review_queue",id:null}`; Daily Challenge uses `{type:"daily_challenge",id:null}` because its app-day identity is already in `daily_challenge.challenge_date`. Recommendation fallback copies the V2 `target.type/id` and key. Onboarding uses a StudyPlan ID only for `prepare_schedule`, otherwise `{type:"none",id:null}`. Nonapplicable `plan_id`, `block_id`, and `recommendation_key` are null, and `can_start_session` is false. `action.label` is a bounded, factual server label for the selected route; Persian copy may be refined without changing identity, reason code, or destination.

Block eligibility reuses the existing active/runnable target and Plan checks. A stale generation summary does not erase a preserved actionable Block; the UI also shows `schedule_stale` and the Plan link. If a target becomes inactive between selection and click, the canonical destination or start service rechecks eligibility and fails safely. The selector never regenerates a stale Plan, completes a Block, changes due dates, or mutates a recommendation. Its precedence and priority are workflow heuristics, never AI scoring, readiness, mastery, probability, or scientific importance.

## Session ↔ canonical activity and Block completion

The Session has one primary Block and does not record a second set of Quiz answers, Case events, flashcard ratings, practice choices, or learning progress. The focused page offers the Block's one canonical destination: flashcards -> existing review flow; Quiz -> existing Quiz runner; Case -> existing revision-safe CaseRunner; Distortion -> existing practice flow; reading/review -> existing content page. Daily Challenge remains its independent card/attempt flow. Navigation away leaves the Session active; returning uses `GET current` or `GET detail`.

Session complete/abandon **never** calls `complete_study_block()`. Completing a Block is a distinct explicit action through the existing `POST /api/study/blocks/<id>/complete/`, subject to all v0.8.2 checks: an owner/target-matched completed QuizAttempt, completed revision-bound CaseAttempt, matching `StudyActivity` flashcard review, or matching Distortion attempt as applicable; reading/review uses explicit user confirmation and means adherence only. The reserved `daily_challenge_optional` Block kind also retains v0.8.2 confirmation-only adherence semantics; a real `DailyChallengeAttempt` remains the sole evidence that the challenge was answered. The focused page shows Block status and `evidence_required`; it must not claim evidence is already available merely because a Session is active or completed. On an explicit Block-complete click, display the existing result or `study_block_evidence_missing` response. An optional completed Block's stored `completion_evidence.kind` may be shown without exposing answers/events.

Session `started_at` does **not** move the existing Block evidence floor. `study_scheduler._canonical_completion_evidence()` currently uses the Block's scheduled-day boundary, `block.started_at` or `block.created_at`, and owner/target matching. Preserve that contract. Evidence predating Session start may still satisfy the Block if it passes v0.8.2 rules; never describe it as activity performed during the Session. No automatic Block completion, Quiz/Case scoring, Daily Challenge submission, SRS review, or plan mutation follows from ending a Session.

## Recommendation V2 and legacy compatibility

Extract or reuse one read-only V2 assembly path so `/api/study/recommendations/` and Today share the released `build_candidates()` ordering, deduplication, feedback application, eight-item default, response shape, and one captured `now`. Do not reproduce V2 rules in Today. `RecommendationFeedback` remains a separate append-only write flow; Today GET cannot create feedback or change rank, Plan, Block, or SRS state. Dismissal applies to nested V2 items and therefore to the recommendation fallback for `next_action`.

Keep `GET /api/study/overview/` and `GET /api/dashboard/` response shapes and V1 recommendation fields intact. `/study` moves its main authenticated orchestration request to Today, but existing consumers and direct endpoints continue to work. Regression tests compare frozen top-level and representative nested V1 keys before/after, verify dashboard recommendation behavior, and verify that the new Today read does not create settings or change legacy responses.

## Frontend structure

`/study` becomes the Persian/RTL Today Study Command Center within the **current** page shell and the post-release `redesign.css` plus `globals.css` styling. It presents next action, active Session resume, study-local date and capacity with overage, due/new SRS, today/overdue Block lists, active Plans and stale schedule links, the existing Daily Challenge card, and the existing `StudyRecommendationsV2` supporting module. Feed the nested Today V2 response into that module on the main screen instead of making a duplicate initial GET; its feedback POST still uses the released endpoint and refreshes Today afterward. Keep its current authenticated/anonymous boundary: anonymous visitors see a login path and existing public challenge access; personal Today data requires auth. The UI uses typed Today/Session shapes in `frontend/lib/types.ts` and the existing JWT-refresh `api()` helper. Do not replace Plan management under `/study/plans`, `/study/plans/new`, or `/study/plans/[id]`.

Add `/study/session/[id]` as a focused, recoverable shell: status, server start time and explicitly unverified elapsed display, planned minutes, primary Block summary, one canonical action link, Block status/evidence-required explanation, explicit separate Block-complete control, complete Session, and abandon Session. If the Block is unavailable, show the reason and safe Plan/Study navigation while retaining complete/abandon. Disable duplicate submissions and retain the start UUID through retries. Do not embed or clone flashcard, Quiz, Case, Distortion, or Daily Challenge engines. Returning from those existing routes refreshes Session and Block state. A next-action preview is optional and is not required for v0.8.4.

## Security, bounds, and verification plan

Every personal Session, Plan, Block, attempt, SRS, progress, and feedback query starts with the authenticated owner. Foreign and missing Session/Block IDs return the same generic 404; foreign Plan IDs are never accepted from the start body. Recheck Block target activity and Case runnability on start and action use. No user ID, action URL, score, elapsed seconds, or completion claim from the client is authoritative.

Today uses aggregate counts/sums over all eligible owner rows and bounded display slices (20 active Plans, 20 today Blocks, 20 overdue Blocks, V2's default 8 items). Use `select_related` for Block targets/Plan and `prefetch_related` only for bounded Plan rows; aggregate capacity and minute totals in SQL; use the existing V2 batched candidate/feedback path and a bounded recent Case lookup. Never issue a query per Block, Plan, or Recommendation, nor load unlimited attempts/events. A populated fixture must include more than each display cap, several overlapping Plans, large due-card history, inactive targets, multiple recent Case attempts, and feedback. Record actual query counts and enforce a measured stable budget; Phase 4 may tune that **measured query threshold** without changing payload caps or behavior. Do not declare an invented maximum now.

Focused tests to implement later:

| Area | Required cases |
| --- | --- |
| Session schema/service/API | Fresh start, current absent/present, same-token retry before/after terminal, equivalent active start, conflicting token, different active Block, concurrent same/different starts on SQLite, DB one-active constraint, PostgreSQL-compatible lock path, complete/abandon and same/cross terminal repeats, timestamp/seconds server authority and cap, stale browser token, invalid/oversized/unknown-field bodies. |
| Ownership/integrity | Cross-owner Session GET/current/complete/abandon, foreign Plan/Block start, Plan-Block mismatch via model/service, archived Plan, inactive target, skipped/completed Block, hard-deleted primary Block history, Plan/user deletion behavior, no inferred foreign active state. |
| Today | No Plan, one/multiple overlapping Plans, today/overdue Blocks and caps/ties, active/unavailable-focus Session, due/overdue/new SRS, app-date Daily Challenge state, V2 feedback/dismissal integration, stale schedule, zero/over capacity and exact formulas, deterministic next action and inactive target fallthrough, study/app midnight boundary, no settings creation or other GET write. |
| Canonical evidence | Quiz, revision-bound Case, flashcard activity, Distortion attempt, reading confirmation; Session completion alone does not satisfy any evidence-backed Block; Session start does not shift the v0.8.2 evidence floor; legacy overview/dashboard remain stable. |
| Performance/UI | Realistic fixture with measured query count, exact totals despite list truncation, desktop/mobile Persian RTL and overflow, auth expiry, retry UUID persistence, return from canonical runner, timer cap wording, unavailable Block recovery. |
| Migration/release gates | Historical applied `0031 -> 0032` upgrade preserving users, Plans, Blocks, attempts, feedback and zero fabricated Sessions; fresh SQLite migrate; model drift check; SQLite constraint and concurrent-start tests; relevant full backend suite; existing read-only audits; frontend typecheck/build and browser journey. |

## Deliberately open implementation-only choices

Phase 3 may choose the exact Python module split, shared V2 response-helper location, ORM query/annotation syntax, and error-copy wording while preserving all codes, fields, eligibility, ordering, ownership, and transaction rules above. Phase 4 may set the query-budget threshold from measured fixture evidence. Frontend phases may refine Persian copy, visual arrangement, and responsive behavior while preserving the frozen API and authority boundaries. These are implementation choices, not permission to add a second evidence system or change the contract.
