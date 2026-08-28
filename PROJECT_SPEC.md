# Psychology Atlas Product Spec

## Current implemented version: v0.2 Core Learning Upgrade

Psychology Atlas is an interactive educational system for psychology students. It should behave as a learning system, not as a psychology blog or a diagnostic product.

## Architecture decisions

- User accounts: **YES**
- Frontend: **Next.js + React + TypeScript**
- Backend: **Django + Django REST Framework**
- Auth: **JWT** with frontend access-token refresh
- Current database: **SQLite**
- Future database: **PostgreSQL** without business-logic rewrite
- ORM/migrations are the source of truth
- Content administration: **seed data for now**, admin UI later
- User-owned data must remain isolated by authenticated user

## Implemented in v0.2

1. Accounts
2. Disorders Atlas
3. Persian search and category filters
4. Disorder Detail V2 with tabbed learning surfaces
5. Compare Disorders V2
6. Staged Clinical Cases V2
7. Expanded Quiz system
8. Bookmarks / Saved
9. Private per-disorder Notes
10. Activity-based Progress
11. Student Dashboard V2
12. Mini Concept Map derived from real symptom/relationship data
13. Global loading/error states
14. JWT refresh and local CORS fixes

## Current educational dataset

- 30 disorders
- 7 disorder categories
- 5 quizzes / 40 quiz questions
- 6 clinical cases / 18 staged case steps
- Structured symptom relationships
- Structured differential/related disorder relationships
- Institutional source metadata

## Progress semantics

Progress is an **activity completion indicator**, not a mastery score and not a clinical measure.

Current v0.2 milestones:

- Authenticated disorder view: at least 25%
- Completing a related quiz: at least 65%
- Completing a related clinical case: at least 75%
- Full-credit case: at least 85% and topic marked completed

This model can later be replaced by a richer study-plan/mastery engine without changing the public content model.

## Product identity

Signature direction:

```text
Compare Disorders
+
Interactive Clinical Cases
+
Concept Map
```

The UI should prioritize cards, relationships, structured comparisons and active learning over long unstructured articles.

## Scientific rules

- Educational use only.
- Do not copy DSM text verbatim.
- Do not fabricate prevalence, diagnostic claims, treatment claims, references, or similarity percentages.
- Maintain source metadata.
- Content should clearly distinguish educational summaries from individual clinical diagnosis.
- Before public production release, perform a dedicated scientific review of every seeded disorder, case and quiz and attach more granular references.

## Still outside v0.2

These remain planned for later versions:

- Flashcards
- Spaced repetition
- Full cross-domain Concept Map
- Psychology Dictionary
- Cognitive Distortions Explorer
- Therapy Atlas
- Psychologists Atlas
- Theories Atlas
- Psychology Timeline
- Study Mode with exam dates/topics
- Study streak
- Study heatmap
- Daily challenge
- XP / Levels / Achievements
- Recommendation engine based on weak concepts
- Study Plan
- Brain Atlas
- Full branching clinical-case engine with conditional branches
- Content admin panel / CMS

## Full-product direction

The eventual product should connect:

```text
Disorders
↕
Symptoms
↕
Concepts
↕
Therapies
↕
Cases
↕
Quizzes / Flashcards
↕
Personal study progress
```

v0.2 intentionally deepens the core learning loop before expanding into every psychology domain.
