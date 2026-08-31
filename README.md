# Psychology Atlas — v0.4.1 · Graph & Study Hardening

یک وب‌اپ Full-Stack فارسی و RTL برای یادگیری تعاملی روان‌شناسی. v0.4.1 یک bug-hardening release روی v0.4 است: integrity و lifecycle محتوای تمرین/Quiz/Case، semantics و performance Graph، progress logic، input validation، timezone، JWT logout/blacklist و production security defaults را سخت‌گیری می‌کند، بدون تغییر taxonomy علمی اصلی v0.4.

> این نرم‌افزار آموزشی است و ابزار تشخیص، درمان یا جایگزین ارزیابی حرفه‌ای نیست.

## Stack

- **Frontend:** Next.js 16.3.3 + React 19 + TypeScript
- **Backend:** Django 5.2 + Django REST Framework
- **Auth:** JWT + automatic access-token refresh
- **Database now:** SQLite
- **Database later:** PostgreSQL-ready through Django ORM + migrations
- **Content:** deterministic/idempotent seed command, no content-admin UI yet

## v0.4.1 hardening

- Practice submit قبل از هر تغییر state، integrity پاسخ صحیح و active بودن choice/concept را validate می‌کند.
- Seed محتوای تاریخی user-owned را حذف نمی‌کند؛ stale child content به‌صورت soft-inactive نگه داشته می‌شود.
- Quiz/Case progress بر اساس عملکرد واقعی افزایش می‌یابد و score ضعیف دیگر mastery مصنوعی ایجاد نمی‌کند.
- GET جزئیات Disorder read-only است؛ ثبت view فقط از endpoint رسمی progress انجام می‌شود.
- Neighborhood filter قبل از BFS اعمال می‌شود و خروجی disconnected تولید نمی‌کند.
- `min_degree` روی graph نهایی فیلترشده اعمال می‌شود.
- Path Finder جهت traversal را حفظ می‌کند و `dsm_nearby` به‌صورت پیش‌فرض shortest-path مفهومی را shortcut نمی‌کند.
- Atlas/DSM graph queryها سبک‌تر شده‌اند و Atlas graph cache با model signals invalidation می‌شود.
- ورودی‌های عددی oversized به 400 تبدیل می‌شوند، نه 500.
- timezone اپ از env قابل تنظیم است و پیش‌فرض `Asia/Tehran` است.
- production بدون `SECRET_KEY` بالا نمی‌آید؛ secure cookie/HSTS/HTTPS defaults، GZip، DRF throttling، CSP/security headers و JWT refresh blacklist/logout اضافه شده‌اند.
- Frontend raceهای Practice/Neighborhood/Path، stale Compare و DSM Graph URL/count state اصلاح شده‌اند.

## v0.4 content

- **241 canonical disorder pages** across 20 DSM chapters + 1 supplemental medication/adverse-effects section
- **30 structured symptoms**
- **44 psychology concepts**
- **12 Cognitive Distortions** grounded in the Beck Institute educational worksheet taxonomy
- **8 searchable Concept aliases**
- **65 Disorder ↔ Concept links**
- **23 Concept ↔ Concept relationships**
- **15 Concept ↔ Symptom links**
- **50 flashcards**
- **18 Cognitive Distortion recognition practice items × 4 choices = 72 choices**
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

## Core features through v0.4

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

Every curated seeded disorder has at least one Concept link. Every Cognitive Distortion subtype now has an active flashcard, and the dedicated practice bank covers definition recognition plus harder confusion/contrast cases. DSM-generated Disorder pages may rely primarily on their linked MASTER profile until dedicated cross-domain enrichment is added.

### Knowledge Graph V2

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

Current graph in v0.4:

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
- Concept domain/subtype/minimum-degree filters
- Concept Neighborhood Explorer with depth 1 or 2
- server-side shortest-path finder between any two Atlas nodes

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
GET  /api/concepts/<slug>/neighborhood/?depth=1|2

GET  /api/concept-map/
GET  /api/concept-map/path/?from=<node-id>&to=<node-id>
GET  /api/concept-map/?node_type=&domain=&kind=&subtype=&category=&relation=&min_degree=
GET  /api/cognitive-distortions/overview/
GET  /api/cognitive-distortions/practice/
POST /api/cognitive-distortions/practice/<slug>/submit/
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

Validated on the completed v0.4 release after both the Concept Graph foundation and Part 2 Explorer/Practice upgrade:

```text
Django system check                  PASS
Backend tests                        64 / 64 PASS
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
v0.4 concept inventory                PASS · 44 concepts / 12 distortions / 8 aliases
v0.4 relation provenance              PASS · 12 Beck-backed distortion membership relations
v0.4 Concept ↔ Symptom layer          PASS · 15 structured links
v0.4 flashcard inventory              PASS · 50 active cards
v0.4 distortion practice              PASS · 18 items / 72 choices / exactly 1 correct per item
v0.4 Graph V2                         PASS · filters / depth-2 neighborhood / shortest-path
Seed/DSM category compatibility       PASS · two seed runs keep 21 DSM-backed categories
Live v0.4 route smoke                 PASS · API + /cognitive-distortions + /concepts + /map + /study
Authenticated Practice E2E            PASS · submit → StudyActivity → ConceptProgress → StudyOverview
DSM overview HTML payload             ~115 KB after lazy metadata loading
```

The existing v0.3.1 Disorders Explorer browser validation remains part of the regression baseline. v0.4 additionally passed production-build and live HTTP smoke tests for the new Concept/Graph/Distortion routes plus an authenticated Practice-to-Study-Engine runtime flow.

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
Cognitive Distortion Practice
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

## Roadmap after v0.4

v0.4 was implemented in two internal phases and is now complete. The next product-domain expansion is Therapy Atlas:

```text
v0.5  Therapy Atlas
v0.6  Psychologists + Theories + Timeline
v0.7  Advanced Branching Clinical Cases + Analytics
v0.8  Study Mode + Exam Planning + Advanced Recommendations
v0.9  Brain Atlas + Assessments Atlas
v1.0  Admin CMS + Scientific Review + Full cross-domain integration
```

## Deliberately not part of v0.4

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
