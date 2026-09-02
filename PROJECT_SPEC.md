# Psychology Atlas Product Spec

## Current implemented version: v0.5.2 — Scientific Therapy Seed + API

Psychology Atlas is an interactive educational system for psychology students. It should behave as a connected learning system, not as a psychology blog and not as a diagnostic product.

v0.5.2 is Part 2 of Therapy Atlas. It preserves the v0.5.1 schema foundation and adds a compact source-backed Therapy/Technique dataset plus public read APIs. Dedicated Therapy frontend, Graph V3 integration, compare and personal features remain deferred to later v0.5.x parts.

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

### Therapy architecture foundation

Current Therapy backend entities:

```text
TherapyFamily
TherapyClassification
Therapy
TherapyAlias
Technique
TechniqueAlias
TherapyClassificationLink
TherapyTechnique
TherapyDisorder
TherapyConcept
TechniqueConcept
```

Scientific/schema rules:

- Therapy is a coherent therapeutic approach/model; Technique is a reusable intervention procedure. They are not stored as the same entity.
- Primary orientation is represented by one `TherapyFamily`. Overlapping labels such as focus/method/delivery/population are separate `TherapyClassification` links and may be multiple.
- `TherapyDisorder` stores `clinical_role` separately from `evidence_basis`; neither field is a personalized recommendation.
- `Therapy`, `Technique` and cross-domain relationship provenance reuses the shared `SourceReference` registry through explicit source-link models.
- `review_status` is lightweight metadata only. Full moderation/scientific-review workflow remains deferred.
- v0.5.2 seeds only source-backed educational summaries. It does not seed treatment rankings, personalized recommendations or fabricated effectiveness percentages.
- Seeded content is marked `source_checked`, not scientifically `reviewed`; full review workflow remains deferred.
- Runtime code uses canonical unversioned modules (`views.py`, `serializers.py`, `seed_mvp.py`). Historical migration files remain because they are required for safe database upgrades.

## Implemented learning domains


### Therapy Atlas backend

Current seeded inventory:

```text
3 TherapyFamily
5 TherapyClassification
6 Therapy
9 Technique
9 TherapyDisorder
7 TherapyConcept
10 TherapyTechnique
8 TechniqueConcept
10 dedicated Therapy/Technique source records
```

Public APIs:

```text
GET /api/therapies/
GET /api/therapies/taxonomy/
GET /api/therapies/<slug>/
GET /api/techniques/
GET /api/techniques/<slug>/
```

The seed uses NICE clinical guidelines, NIMH, Beck Institute and the VA National Center for PTSD. `TherapyDisorder.clinical_role` and `evidence_basis` remain separate fields, and relation-level source links are returned in detail API responses.

### Disorders Atlas

- 241 active canonical Disorder pages
- 20 DSM disorder chapters + 1 supplemental medication/adverse-effects section
- 30 curated pages preserved + 211 DSM-generated pages
- Persian + English names across the full canonical catalog
- structured symptoms and curated differential/related disorder relationships where available
- linked DSM MASTER educational profiles for every canonical formal diagnosis
- assessment/treatment/course educational summaries
- source metadata
- related quizzes/cases/concepts where curated learning links exist
- private bookmark/note/progress
- chapter-oriented Disorders Explorer with deep search, grid/compact views and browser-local recently viewed history

### Concepts Atlas

- 44 active concepts
- Persian + English names
- simple definition
- academic definition
- educational example
- concept kind + scientific domain + subtype
- searchable Persian/English aliases
- 12 source-grounded Cognitive Distortion concepts using the Beck Institute educational worksheet taxonomy
- recognition cues, counterexamples and common-confusion notes for Cognitive Distortions
- Concept ↔ Concept relationships with richer relation vocabulary
- relationship-level provenance support
- Disorder ↔ Concept roles
- Concept ↔ Symptom structured links
- sources
- flashcards
- private bookmark/note/progress

Every one of the 30 curated seeded Disorders currently has at least one Concept link. DSM-generated Disorder pages may rely primarily on their MASTER profile until later cross-domain enrichment.
The current seed has 44 concepts, 50 active flashcards and an 18-item Cognitive Distortion recognition bank. Practice scoring is server-side and feeds StudyActivity plus Concept Progress.

### Knowledge Graph

Current graph layers:

```text
Concept ↔ Concept
Disorder ↔ Concept
Concept ↔ Symptom
Disorder → Symptom
Disorder ↔ Disorder via DSM nearby-title links
```

Original curated graph baseline:

```text
35 Concept nodes
30 curated Disorder nodes
30 Symptom nodes
95 total nodes
144 base Atlas edges
```

Current graph:

```text
44 Concept nodes
241 canonical Disorder nodes
30 Symptom nodes
315 total nodes
738 total edges

23 Concept ↔ Concept edges
65 Disorder ↔ Concept edges
15 Concept ↔ Symptom edges
65 Disorder → Symptom edges
570 DSM nearby-title Disorder ↔ Disorder edges
```

The graph must use explicit structured relationships. Do not invent similarity percentages.

Current Graph UX includes domain/subtype/minimum-degree filtering, depth-1/depth-2 Concept neighborhoods and server-side shortest-path finding between Atlas nodes. Node-type filters are applied before neighborhood traversal, minimum degree is evaluated on the final filtered graph, traversal direction is preserved in path results, and `dsm_nearby` structural shortcuts are excluded from the default conceptual shortest path. Path results are still computed only from stored edges.

### Active-learning tools

- Compare Disorders
- 5 quizzes / 40 questions
- 6 staged clinical cases / 18 stages
- 50 flashcards
- spaced-repetition review queue
- 12 Daily Challenges
- 18 Cognitive Distortion recognition items / 72 choices
- Cognitive Distortions Explorer with basic/intermediate/advanced practice
- Search across Disorder / Concept / Symptom

## Study Engine

The study engine records meaningful user activity:

```text
Disorder View
Concept View
Quiz Completed
Case Completed
Flashcard Review
Daily Challenge
Cognitive Distortion Practice
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
- Recommendation Engine
- Dashboard
- unified Saved base for Disorder + Concept
- unified Notes base for Disorder + Concept

The streak/heatmap logic remains backward-compatible with historical Disorder progress, Quiz attempts and Case attempts while avoiding double-counting StudyActivity events.

## Progress semantics

Progress values are **educational activity indicators**, not diagnosis, clinical severity or university grades.

### Disorder progress

Current milestones include:

- explicit authenticated Disorder-view activity: at least 25%; the Disorder detail GET itself is read-only
- completing a related Quiz: 25% baseline + up to 60 percentage points according to Quiz score
- completing a related Case: 25% baseline + up to 60 percentage points according to Case performance
- only sufficiently high earned progress can mark the Disorder completed

Progress must never regress because a page is revisited.

### Concept progress

Current signals include:

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
- Cognitive Distortion Practice attempts
- Study activity

Seed updates must not intentionally delete these records.

## Still outside v0.5.1

These are intentionally deferred rather than partially implemented placeholders:

- Therapy Atlas
- Psychologists Atlas
- Theories Atlas
- Psychology Timeline
- Brain Atlas
- dedicated Assessments Atlas
- full CBT thought-record/reframing workflow beyond the educational recognition engine
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

The Concept Graph and Cognitive Distortions learning layer remain the current connected-learning baseline. v0.5.1 now establishes Therapy/Technique as the next cross-domain schema using the existing provenance foundation rather than creating a parallel source system.

## Version roadmap

```text
v0.5.1  Therapy Architecture + Backend Foundation ✅
v0.5.2  Scientific Therapy Seed + API ✅
v0.5.3  Therapy Atlas Frontend
v0.5.4  Cross-domain Integration + Knowledge Graph
v0.5.5  Compare + Personal Features + Final Hardening
v0.6    Psychologists + Theories + Timeline
v0.7  Advanced Branching Clinical Cases + Analytics
v0.8  Study Mode + Exam Planning + Advanced Recommendations
v0.9  Brain Atlas + Assessments Atlas
v1.0  Admin CMS + Scientific Review + Full cross-domain integration
```

The current product version is v0.5.2 Scientific Therapy Seed + API.
