# Psychology Atlas Product Spec

## Current implemented version: v0.3 Study Engine + Knowledge Graph

Psychology Atlas is an interactive educational system for psychology students. It should behave as a connected learning system, not as a psychology blog and not as a diagnostic product.

## Architecture decisions

- User accounts: **YES**
- Frontend: **Next.js + React + TypeScript**
- Backend: **Django + Django REST Framework**
- Auth: **JWT** with frontend access-token refresh
- Current database: **SQLite**
- Future database: **PostgreSQL** without business-logic rewrite
- Django ORM/migrations are the persistence source of truth
- Content administration: **deterministic seed data for now**, dedicated content-admin UI later
- User-owned data must remain isolated by authenticated user
- Server controls quiz/case scoring and SRS scheduling
- Do not couple frontend logic to SQLite

## Implemented learning domains

### Disorders Atlas

- 30 active disorders
- 7 categories
- structured symptoms
- differential/related disorder relationships
- assessment/treatment/course educational summaries
- source metadata
- related quizzes/cases/concepts
- private bookmark/note/progress

### Concepts Atlas

- 35 active concepts
- Persian + English names
- simple definition
- academic definition
- educational example
- concept kind
- Concept ↔ Concept relationships
- Disorder ↔ Concept roles
- sources
- flashcards
- private bookmark/note/progress

Every active seeded Disorder currently has at least one Concept link.
Every active seeded Concept currently has at least one active Flashcard.

### Knowledge Graph V1

Current graph layers:

```text
Concept ↔ Concept
Disorder ↔ Concept
Disorder → Symptom
```

Seeded graph baseline:

```text
35 Concept nodes
30 Disorder nodes
30 Symptom nodes
95 total nodes
144 total edges
```

The graph must use explicit structured relationships. Do not invent similarity percentages.

### Active-learning tools

- Compare Disorders V2
- 5 quizzes / 40 questions
- 6 staged clinical cases / 18 stages
- 41 flashcards
- spaced-repetition review queue
- 12 Daily Challenges
- Search V3 across Disorder / Concept / Symptom

## Study Engine v0.3

The study engine records meaningful user activity:

```text
Disorder View
Concept View
Quiz Completed
Case Completed
Flashcard Review
Daily Challenge
Note Saved
Bookmark Saved
```

Repeated page-view events are deduplicated over a short server-side window so analytics are not inflated by React development remounts or rapid refreshes.

### Study surfaces

- current Study Streak
- 42-day Heatmap
- review due/new/reviewed counts
- concepts studied/mastered
- Daily Challenge completion
- Recommendation Engine V1
- Dashboard V3
- unified Saved base for Disorder + Concept
- unified Notes base for Disorder + Concept

The v0.3 streak/heatmap logic remains backward-compatible with pre-v0.3 Disorder progress, Quiz attempts and Case attempts while avoiding double-counting new StudyActivity events.

## Progress semantics

Progress values are **educational activity indicators**, not diagnosis, clinical severity or university grades.

### Disorder progress

Current milestones include:

- authenticated Disorder view: at least 25%
- completing a related Quiz: progress increases according to the existing learning service
- completing a related Case: progress increases according to the existing learning service
- high/full-credit Case performance can mark the Disorder completed

Progress must never regress because a page is revisited.

### Concept progress

Current v0.3 signals include:

- Concept view: at least 20%
- Flashcard `again`: at least 30%
- Flashcard `hard`: at least 45%
- Flashcard `good`: at least 70%
- Flashcard `easy`: at least 85% and can mark Concept completed
- Daily Challenge can raise linked Concept progress

This is a practical MVP mastery indicator. A later version may replace it with a richer evidence-weighted mastery model.

## Spaced repetition semantics

Private per-user Flashcard state stores:

```text
state
due_at
interval_days
ease_factor
repetitions
lapses
last_rating
last_reviewed_at
```

Ratings:

```text
again
hard
good
easy
```

Scheduling is server-side. The frontend only submits the rating and displays the resulting queue.

## Product identity

The current signature loop is:

```text
Explore Disorder / Concept
        ↓
Follow Knowledge Graph
        ↓
Quiz / Case / Flashcard / Daily Challenge
        ↓
Record activity and performance
        ↓
Detect weak or unfinished topics
        ↓
Schedule / recommend review
        ↓
Review again
```

The UI should prioritize relationships, cards, structured comparisons and active learning over long unstructured articles.

## Scientific/content rules

- Educational use only.
- Do not copy DSM text verbatim.
- Do not fabricate prevalence, diagnostic claims, treatment claims, references or similarity percentages.
- Maintain source metadata.
- Educational examples must not be framed as personal diagnosis.
- Inactive educational content should not appear in public/user-facing navigation or recommendation results.
- Before public production release, perform dedicated scientific review of seeded content and attach more granular claim-level references.

## User-owned data

The following data is private per authenticated user:

- Disorder bookmarks
- Concept bookmarks
- Disorder notes
- Concept notes
- Disorder progress
- Concept progress
- Flashcard SRS progress
- Quiz attempts
- Case attempts
- Daily Challenge attempts
- Study activity

Seed updates must not intentionally delete these records.

## Still outside v0.3

These are intentionally deferred rather than partially implemented placeholders:

- Therapy Atlas
- Psychologists Atlas
- Theories Atlas
- Psychology Timeline
- Brain Atlas
- dedicated Assessments Atlas
- dedicated Cognitive Distortions exercise engine beyond current Concept content
- Study Plan / exam date planning
- adaptive Quiz / independent Question Bank
- fully branching Clinical Cases with conditional paths
- advanced clinical-skill analytics
- advanced personalized Recommendation Engine
- XP / Levels / Achievements
- content versioning
- scientific review workflow
- content-admin CMS
- claim-level citation graph

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
Psychologists / Theories / Timeline
↕
Cases / Assessments
↕
Quizzes / Flashcards / Daily Practice
↕
Personal study plan and mastery
```

v0.3 establishes the reusable learning and Knowledge Graph foundation before expanding into the remaining psychology domains.
