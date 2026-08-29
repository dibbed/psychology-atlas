# Psychology Atlas — v0.4 Part 1 · Concept Graph Foundation + Cognitive Distortions

یک وب‌اپ Full-Stack فارسی و RTL برای یادگیری تعاملی روان‌شناسی. checkpoint فعلی نیمه اول v0.4 است: پایه موفق v0.3.1 حفظ شده و لایه Concept با taxonomy، alias، provenance، Concept↔Symptom و یک مجموعه منبع‌دار Cognitive Distortions عمیق‌تر شده است؛ Explorer/Graph UX پیشرفته و تمرین‌های اختصاصی برای Part 2 می‌مانند.

> این نرم‌افزار آموزشی است و ابزار تشخیص، درمان یا جایگزین ارزیابی حرفه‌ای نیست.

## Stack

- **Frontend:** Next.js 16.3.3 + React 19 + TypeScript
- **Backend:** Django 5.2 + Django REST Framework
- **Auth:** JWT + automatic access-token refresh
- **Database now:** SQLite
- **Database later:** PostgreSQL-ready through Django ORM + migrations
- **Content:** deterministic/idempotent seed command, no content-admin UI yet

## v0.4 Part 1 content

- **241 canonical disorder pages** across 20 DSM chapters + 1 supplemental medication/adverse-effects section
- **30 structured symptoms**
- **44 psychology concepts**
- **12 Cognitive Distortions** grounded in the Beck Institute educational worksheet taxonomy
- **8 searchable Concept aliases**
- **65 Disorder ↔ Concept links**
- **23 Concept ↔ Concept relationships**
- **15 Concept ↔ Symptom links**
- **41 flashcards**
- **12 daily challenges × 4 choices**
- **5 quizzes × 8 questions = 40 questions**
- **6 staged clinical cases × 3 stages = 18 case stages**
- Institutional source metadata attached to every seeded concept and disorder
- **DSM-5-TR Persian MASTER reference layer:** 438 addressable educational/structural records imported from the audited 2026-08-29 bundle without flattening non-diagnosis records into disorders
- **243 formal-diagnosis MASTER records → 241 canonical Atlas disorder pages**; 2 duplicate structural occurrences remain independently addressable in DSM MASTER but collapse to one Disorder page each
- **30 curated disorder pages preserved + 211 DSM-generated disorder pages**
- **22 Neurodevelopmental Disorder pages**, including Autism Spectrum Disorder and Attention-Deficit/Hyperactivity Disorder
- **Disorders Explorer v0.3.1:** sticky chapter rail, responsive chapter selector, deep Persian/English search, grid/compact view modes, keyboard `/` focus shortcut, and browser-local recently viewed disorders

## DSM-5-TR Persian MASTER reference layer

Source bundle:

```text
DSM5TR_MASTER_2026-08-29_bundle/
```

The importer verifies the source JSON, preserves the complete parsed document in `DSMCorpus.raw_document`, and builds a normalized searchable `DSMRecord` index. The source manifest SHA256 is preserved and verified during the audited import:

```text
9680d7b1e85ae4ef58efa58f7c76bfcc04c7b317f1fbd40cbb2e27be02542694
```

Imported record types are deliberately kept separate:

```text
243 formal diagnoses
 92 structural/title records
 65 clinical-attention conditions/codes
 20 structural references
  8 research conditions
  7 Section III alternative-model records
  2 specifiers
  1 additional code
438 total addressable MASTER records
```

Routes:

```text
/dsm
/dsm/<MASTER-ID>
```

The DSM explorer supports Persian/English full-text search, chapter and classification filters, hierarchy navigation, source registry links, audited quality metadata, official-update notes, targeted assessment, differential review, course, educational management, safety flags, self-test questions, and a lazy-loaded view of remaining file-level metadata/indexes. Every canonical formal diagnosis is synchronized into the main Disorder Atlas with Persian and English names, and each Disorder page links back to its matching MASTER profile.

Import or refresh the bundle idempotently from the backend directory:

```powershell
python manage.py import_dsm_master
python manage.py import_dsm_master --dry-run
```

The bundle itself states that it is an educational/structural reference, not verbatim DSM diagnostic criteria, not an automated diagnostic tool, and not a substitute for current professional coding or individualized treatment guidance. Proposed/non-final changes remain distinct from approved updates.

## Core features through v0.4 Part 1

### Concepts Atlas

Routes:

```text
/concepts
/concepts/<slug>
```

Each concept can include:

- Persian and English names
- simple definition
- academic definition
- educational example
- concept kind + domain + subtype taxonomy
- searchable Persian/English aliases
- recognition cues, counterexamples and common-confusion notes for Cognitive Distortions
- Concept ↔ Concept relationships with richer semantics
- relationship-level provenance support
- Disorder ↔ Concept relationships and roles
- Concept ↔ Symptom relationships
- institutional/source metadata
- linked flashcards
- personal progress
- personal bookmark
- personal note

Every curated seeded disorder has at least one Concept link. The v0.4 Part 1 concept inventory is now larger than the existing flashcard inventory by design; flashcard/practice expansion for the new Cognitive Distortions is part of v0.4 Part 2. DSM-generated Disorder pages may rely primarily on their linked MASTER profile until dedicated cross-domain enrichment is added.

### Knowledge Graph V1

Route:

```text
/map
```

The graph is built from database relationships, not fabricated similarity percentages.

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
95 nodes
  35 concepts
  30 curated disorders
  30 symptoms
144 base Atlas edges
```

Current graph after v0.4 Part 1:

```text
315 nodes
  44 concepts
 241 canonical disorders
  30 symptoms

23 Concept ↔ Concept edges
65 Disorder ↔ Concept edges
15 Concept ↔ Symptom edges
65 Disorder → Symptom edges
570 DSM MASTER nearby-title edges
= 738 edges
```

The map supports two source-grounded scopes: the original Atlas graph and a DSM MASTER graph. The DSM scope contains 438 MASTER nodes and 2,400 relations (415 hierarchy, 1,826 nearby-title links, 159 differential links that resolve to another MASTER record). Generic differential phrases are not forced into graph nodes.

The map supports node browsing, node-type filters, direct-neighbor exploration and deep links such as:

- live graph/node/edge counts
- per-node degree from real edges
- edge-type filtering
- structured edge explanations when available
- exploration history/path
- high-connectivity node shortcuts
- richer node metadata (English/Persian name, group and summary)

```text
/map?node=concept:avoidance
```

### Flashcards + Spaced Repetition

Route:

```text
/flashcards
```

Flashcard progress is private per user and stores:

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

The review queue supports contextual filtering:

```text
/flashcards?concept=avoidance
/flashcards?disorder=panic-disorder
```

The server calculates the next due date. Client-side code does not control SRS state.

### Study Activity Engine

The backend records meaningful study events:

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

Repeated Disorder/Concept view events within a short window are deduplicated to avoid inflating analytics from React development remounts or rapid refreshes.

### Study Center

Route:

```text
/study
```

Includes:

- current study streak
- 42-day study heatmap
- due flashcards
- unseen flashcards
- reviewed flashcards
- concepts studied
- concepts mastered
- Daily Challenge
- Recommendation Engine V1

The streak and heatmap remain backward-compatible with v0.2 quiz, case and disorder-progress history while avoiding double-counting new v0.3 events.

### Daily Challenge

Route/API:

```text
GET  /api/daily-challenge/
POST /api/daily-challenge/
```

Properties:

- deterministic daily selection from active challenge content
- answers do not expose `is_correct` before submission
- one attempt per user per calendar day
- duplicate/concurrent submission is handled safely
- existing attempts continue to show the original challenge even if active challenge content changes later that day
- concept progress and study activity are updated after submission

### Search V3

Route:

```text
/search
```

Searches simultaneously across:

- Disorders
- Concepts
- Symptoms linked to active disorders

The client uses cancellation/debounce to prevent stale request races.

### Dashboard V3

Route:

```text
/dashboard
```

Includes:

- study streak
- topics studied
- concepts studied/mastered
- quiz average
- case average
- saved items
- notes
- review due/new counts
- 42-day heatmap
- study recommendations
- continue learning for disorders
- continue learning for concepts
- weak topics
- recent quizzes/cases
- recent disorder/concept notes
- recent disorder/concept bookmarks

Inactive/stale educational content is filtered from user-facing lists so old user records do not create links to deactivated pages.

### Universal Notes / Saved Base

Routes:

```text
/saved
/notes
```

Both pages now combine Disorder and Concept user data while keeping ownership private per authenticated user.

## Preserved v0.2 features

v0.3 extends rather than replaces the previous learning core:

- registration / login / logout
- automatic JWT access-token refresh
- Disorders Atlas with Persian RTL detail pages
- symptom-aware disorder search
- Compare Disorders for 2–4 disorders
- staged Clinical Cases
- server-side case scoring and feedback
- quizzes with server-side scoring
- Disorder bookmarks
- Disorder notes
- activity-based Disorder progress
- not-found/error/loading states
- CORS support for both `localhost:3000` and `127.0.0.1:3000`

## Data ownership

User-owned records remain scoped to the authenticated user:

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

The seed command updates educational content without intentionally deleting user-owned records.

## Database architecture

The frontend has no SQLite dependency. Persistence stays behind Django ORM:

```text
Next.js / React
       ↓
Django REST API
       ↓
Django ORM
       ↓
SQLite now / PostgreSQL later
```

v0.3 migrations:

```text
0003_concept_dailychallenge_dailychallengechoice_and_more.py
0004_alter_concept_kind.py
```

## Quick start

### Backend

```powershell
cd backend
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_mvp
python manage.py runserver 8000
```

Backend API:

```text
http://127.0.0.1:8000/api/
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend:

```text
http://localhost:3000
```

`http://127.0.0.1:3000` is also supported locally.

## Important API routes

```text
POST /api/auth/register/
POST /api/auth/login/
POST /api/auth/refresh/
GET  /api/auth/me/

GET  /api/categories/
GET  /api/disorders/
GET  /api/disorders/<slug>/
GET  /api/disorders/compare/?slugs=a,b

GET  /api/concepts/
GET  /api/concepts/<slug>/
POST /api/concepts/<slug>/view/

GET  /api/concept-map/
GET  /api/atlas-overview/
GET  /api/search/?q=<query>

GET  /api/dsm/overview/
GET  /api/dsm/metadata/
GET  /api/dsm/study-kit/
GET  /api/dsm/graph/
GET  /api/dsm/records/?q=<query>&type=<type>&chapter=<number>
GET  /api/dsm/records/<MASTER-ID>/
GET  /api/dsm/records/by-disorder/<slug>/

GET  /api/flashcards/
GET  /api/flashcards/review-queue/
POST /api/flashcards/<slug>/review/

GET/POST /api/daily-challenge/
GET      /api/study/overview/

GET/POST /api/bookmarks/
DELETE   /api/bookmarks/<slug>/
GET/POST /api/concept-bookmarks/
DELETE   /api/concept-bookmarks/<slug>/

GET /api/notes/
GET/PUT/DELETE /api/notes/<slug>/
GET /api/concept-notes/
GET/PUT/DELETE /api/concept-notes/<slug>/

POST /api/progress/<slug>/view/
GET  /api/dashboard/

GET  /api/quizzes/
GET  /api/quizzes/<slug>/
POST /api/quizzes/<slug>/submit/

GET  /api/cases/
GET  /api/cases/<slug>/
POST /api/cases/<slug>/submit/
```

## Release validation baseline

Validated on the current v0.4 Part 1 checkpoint after the Concept Graph foundation and Cognitive Distortions data-layer upgrade:

```text
Django system check                  PASS
Backend tests                        58 / 58 PASS
DSM import idempotency               PASS · 1 corpus / 438 records / 241 canonical Disorder pages / 6 sources
DSM diagnosis sync                    PASS · 243 formal records → 241 canonical pages · 211 created + 30 curated preserved
Neurodevelopmental chapter            PASS · 22 Disorder pages including Autism Spectrum Disorder and ADHD
DSM resolved relations               PASS · 1,826 nearby / 159 differential
DSM graph                            PASS · 438 nodes / 2,400 edges
Atlas graph with DSM layer           PASS · 315 nodes / 738 edges
DSM study inventory                  PASS · 2,190 self-tests / 438 exam tips / 14 glossary terms
DSM source SHA256                    PASS · matches bundle manifest
Migration drift                      none
Python compileall                    PASS
pip check                            PASS
TypeScript typecheck                 PASS
Next.js production build             PASS
npm audit --audit-level=low           0 vulnerabilities
Frontend main-route smoke test        PASS
Disorders Explorer hydrated E2E       PASS · 241 catalog / chapter rail / recent Autism persistence
DSM API + route smoke test            PASS
v0.4 Part 1 concept inventory         PASS · 44 concepts / 12 distortions / 8 aliases
v0.4 relation provenance              PASS · 12 Beck-backed distortion membership relations
v0.4 Concept ↔ Symptom layer          PASS · 15 structured links
Seed/DSM category compatibility       PASS · two seed runs keep 21 DSM-backed categories
DSM overview HTML payload             ~115 KB after lazy metadata loading
```

The existing v0.3.1 Disorders Explorer browser validation remains part of the regression baseline. v0.4 Part 1 itself is primarily a data/API/schema checkpoint; the heavier Concept Explorer/Graph browser UX is intentionally reserved for Part 2.

Real user-flow validation covered:

```text
Register
Auth / Me
JWT Refresh
Concept View
Concept Bookmark
Concept Note
Disorder View
Disorder Bookmark
Flashcard Review
Daily Challenge
Study Overview
Dashboard V3
Unified Saved
Unified Notes
```

## Scientific/content rules

- Do not copy DSM text verbatim.
- Do not invent similarity percentages.
- Do not present educational summaries as a personal diagnosis.
- Keep educational examples clearly non-diagnostic.
- Keep source metadata attached to educational content.
- Before production/publication, content should receive dedicated scientific review and more granular claim-level citations.

## Roadmap after v0.4 Part 1

v0.4 is intentionally split into two implementation phases so the graph/data foundation can be validated before adding the heavier explorer and learning UX:

```text
v0.4 Part 1  Concept taxonomy + aliases + provenance + Concept↔Symptom + Cognitive Distortions foundation
v0.4 Part 2  Full Concept Explorer/Graph UX + neighborhood/path finding + distortion practice/learning expansion
v0.5         Therapy Atlas
v0.6  Psychologists + Theories + Timeline
v0.7  Advanced Branching Clinical Cases + Analytics
v0.8  Study Mode + Exam Planning + Advanced Recommendations
v0.9  Brain Atlas + Assessments Atlas
v1.0  Admin CMS + Scientific Review + Full cross-domain integration
```

## Deliberately not part of v0.4 Part 1

These remain later-version work rather than partially implemented placeholders:

- Therapy Atlas
- Psychologists Atlas
- Theories Atlas
- Psychology Timeline
- Brain Atlas
- dedicated Assessments Atlas
- fully branching Clinical Cases
- adaptive question bank
- exam planning / study plans
- XP / achievements
- advanced recommendation engine
- content-admin CMS and scientific review workflow
- claim-level citation graph

See `PROJECT_SPEC.md` for the broader product direction.
