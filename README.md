# Psychology Atlas — v0.3 Study Engine + Knowledge Graph

یک وب‌اپ Full-Stack فارسی و RTL برای یادگیری تعاملی روان‌شناسی. نسخه ۰.۳ هسته v0.2 را حفظ می‌کند و یک چرخه یادگیری واقعی روی آن می‌سازد: مطالعه، تمرین، سنجش، تشخیص ضعف، زمان‌بندی مرور و مرور دوباره.

> این نرم‌افزار آموزشی است و ابزار تشخیص، درمان یا جایگزین ارزیابی حرفه‌ای نیست.

## Stack

- **Frontend:** Next.js 16.3.3 + React 19 + TypeScript
- **Backend:** Django 5.2 + Django REST Framework
- **Auth:** JWT + automatic access-token refresh
- **Database now:** SQLite
- **Database later:** PostgreSQL-ready through Django ORM + migrations
- **Content:** deterministic/idempotent seed command, no content-admin UI yet

## v0.3 content

- **30 disorders** across 7 categories
- **30 structured symptoms**
- **35 psychology concepts**
- **65 Disorder ↔ Concept links**
- **14 Concept ↔ Concept relationships**
- **41 flashcards**
- **12 daily challenges × 4 choices**
- **5 quizzes × 8 questions = 40 questions**
- **6 staged clinical cases × 3 stages = 18 case stages**
- Institutional source metadata attached to every seeded concept and disorder

## Core v0.3 features

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
- concept kind
- Concept ↔ Concept relationships
- Disorder ↔ Concept relationships and roles
- institutional sources
- linked flashcards
- personal progress
- personal bookmark
- personal note

Every active seeded disorder has at least one Concept link, and every active seeded Concept has at least one Flashcard.

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
Disorder → Symptom
```

Seeded graph baseline:

```text
95 nodes
  35 concepts
  30 disorders
  30 symptoms

144 edges
```

The map supports node browsing, node-type filters, direct-neighbor exploration and deep links such as:

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
GET  /api/search/?q=<query>

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

Validated on the v0.3 working tree after the deep bug audit:

```text
Django system check                 PASS
Backend tests                       42 / 42 PASS
Migration drift                     none
Python compileall                   PASS
pip check                           PASS
Seed idempotency                    PASS
TypeScript typecheck                PASS
Next.js production build            PASS
npm audit --audit-level=high         0 vulnerabilities
Frontend main-route smoke test       PASS
Public v0.3 API smoke test           PASS
Real authenticated v0.3 user flow    PASS
Temporary audit user cleanup         PASS
```

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

## Deliberately not part of v0.3

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
