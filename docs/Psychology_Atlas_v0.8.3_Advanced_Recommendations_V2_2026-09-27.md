# Psychology Atlas v0.8.3 — Advanced Recommendations V2

Release record · 2026-09-27

## Architecture and authority

The authenticated V2 endpoint builds recommendations from canonical, owner-scoped learning and planning records. `atlas/recommendations_v2.py` reads StudyPlans, StudyBlocks, flashcard SRS due state, QuizAttempts, CaseAttempts, progress and reviewed Theory–Concept relations. `atlas/recommendation_views.py` applies current feedback and a response limit. The Persian Study Center renders the resulting explanations and links. V2 does not write learning history, modify a schedule, recalculate SRS, or create settings during a read. The older `/api/study/overview/` contract and its consumers remain in place.

## Signals and exclusions

| Recommendation | Evidence and action |
| --- | --- |
| `overdue_block` | Pending/in-progress active-plan block scheduled before the owner's today; open its canonical target. |
| `plan_schedule_stale` | Generated active Plan without a valid current generation summary; open Plan. |
| `plan_generate` | Active Plan with generation version zero; open Plan to generate. |
| `srs_review` | Due, visible flashcards in canonical SRS; open flashcard flow. |
| `plan_capacity` | Current generation reports backlog, capacity shortfall, uncovered high-priority scopes or zero usable capacity; open Plan. |
| `case_resume` | Recent in-progress owned attempt for a runnable active Case; open Case. |
| `quiz_retry` | Recent completed owned attempt with incorrect answers for active Quiz; open Quiz. |
| `distortion_practice` | Explicit active Plan scope with practice enabled and an active item; open distortion practice. |
| `concept_review`, `disorder_review` | Recorded low progress for active content; open canonical detail. |
| `graph_explore` | Active, reviewed, explicitly sourced Theory–Concept relation inside an active Plan scope; open Concept. |
| `srs_start` | Active, visible flashcards with no owner review history, when no due cards exist; open flashcards. |

Draft, paused, completed and archived Plans produce no plan signals. Deleted/inactive content, unavailable Quiz/Case targets, unpublished or unrunnable Case revisions and inactive flashcards are excluded. A scheduled actionable block through today suppresses equivalent generic advice. No due and no new cards produce no SRS candidate; no qualifying signals return an empty `items` list. The Case and Quiz windows are 30 days. Exam target dates are descriptive context only, including today and past dates; they do not predict success or extend scheduler horizons. Capacity gaps reflect the existing scheduler summary, including cross-plan constraints reported there.

## Determinism, identity and bounds

Each key is `r2_` plus SHA-256 of a canonical JSON tuple: V2 marker, recommendation type, target type/ID, reason code and context reference. A generation version or attempt change can create a new key; unchanged source state yields the same key. Candidates sort by descending fixed priority, fixed type rank, scheduled date, target type/slug and key. Exact-key and equivalent-action duplicates are removed before feedback filtering. Priority is a product ordering heuristic, not a scientific score.

Source windows cap active Plans at 20, overdue Blocks at 50, recent QuizAttempts and CaseAttempts at 20 each, and other progress/graph source slices at bounded sizes. The candidate list caps at 200; GET returns at most 20 (`limit` defaults to 8). `truncated_sources` reports source or candidate truncation. An indexed, compact identifier scan across actionable Blocks through today preserves duplicate suppression when overdue advice exceeds its 50-item cap. The realistic fixture includes 21 Plans, 51 Blocks, 20 QuizAttempts, 20 CaseAttempts, 80 flashcards and 22 low-progress records; the query-budget regression asserts at most 25 database queries and a 20-item response, with `truncated_sources=true`.

## Feedback and API

`GET /api/study/recommendations/?limit=8` requires authentication. Only one ASCII-decimal `limit` from 1 to 20 is accepted; unknown/repeated/invalid parameters return `400 recommendation_invalid_query`. The response includes `version: "v2"`, `as_of`, ordered `items`, `returned_count`, `suppressed_count` and `truncated_sources`. Each item exposes an explanation (`reason_codes`, `reasons`, `signals`), target, priority, canonical action and current feedback. The internal context reference is omitted.

`POST /api/study/recommendations/<key>/feedback/` requires authentication and a body of at most 1024 bytes containing exactly `value` (`helpful`, `not_helpful`, `dismissed`) and UUID `client_event_id`. Bad input returns `400 recommendation_feedback_invalid`; a key outside the owner's current candidate set returns generic `404 recommendation_not_found`; conflicting reuse of an event ID returns `409 recommendation_feedback_conflict`; the per-owner 100-event UTC-day cap returns `429 recommendation_feedback_limit`. Feedback is owner-scoped and append-only. Exact event replay is idempotent; repeated same-value feedback reuses the latest event while it is effective. Helpful and not-helpful label the item without changing its rank. Dismissal hides that key until `suppressed_until = recorded_at + 7 days`; expiry restores it. A new context key is unaffected. Transactional owner-row serialization, the `(user, client_event_id)` unique constraint and bounded SQLite lock retries protect concurrent writes.

Migration `0031_v083_recommendation_feedback.py` adds only `RecommendationFeedback`, its latest/history indexes, unique event constraint and value/suppression checks. It does not backfill users, Plans, Blocks or feedback. The read-only `audit_recommendation_feedback` checks runtime integrity; migrations and a fresh-install path were validated in Phase 5.

## Timezone and scientific boundaries

Plan-day and overdue comparisons use the owner's IANA study timezone; missing or invalid settings fall back to the application timezone. SRS eligibility uses canonical `due_at <= now` instants. A calendar boundary can change a day-scoped key without rewriting historical evidence. Case/Quiz recency uses actual timestamps. Neither recommendations nor feedback represent mastery, exam readiness, probability, diagnosis, treatment guidance, psychometric measurement or clinical competence. Reviewed graph edges and checked sources describe catalog provenance, not personalized clinical advice.

## Compatibility and validation evidence

- Focused V2 suite: **37/37** passed, covering empty/history variants, inactive/deleted/archived targets, duplicates, date/timezone boundaries, feedback/idempotency/expiry, auth/ownership and the larger query-budget fixture.
- Full backend suite: **280/280** passed on final Phase 6 precommit source. Legacy `/api/study/overview/` and Study Center, v0.8.2 scheduler, v0.7 Case and v0.6 scientific regressions are included.
- Backend gates: Django `check`, `makemigrations --check --dry-run`, `compileall`, `pip check`, `audit_study_plans`, `audit_case_graphs`, `audit_v06_release`, `verify_research_datasets` and `audit_recommendation_feedback` passed in Phase 5. Fresh-install and historical migration preservation checks passed; no model drift.
- Frontend gates: typecheck and production build passed; `npm audit --audit-level=low` reported zero vulnerabilities.
- Real browser QA on final Phase 5 source: authenticated new user, generated Plan schedule, stale schedule, backlog, overdue Block, all feedback values and refresh persistence, seven-day dismissal expiry, canonical links, unauthenticated/expired auth, desktop 1280×800 and mobile 390×844. Both viewports had zero horizontal overflow. Temporary QA users and dependent rows were deleted and verified absent.
- Browser QA found and fixed stale v0.8.2 future-V2 wording in the Plan detail page. No scientific content or Case/SRS authority was changed.

Next roadmap boundary: **v0.8.4 — Today Study Mode + Study Sessions + UI**. This release does not implement that slice.
