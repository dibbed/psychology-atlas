# Psychology Atlas — v0.2 Core Learning Upgrade

یک وب‌اپ Full-Stack فارسی و RTL برای یادگیری تعاملی روان‌شناسی، با تمرکز بر مرور اختلالات، مقایسه، استدلال بالینی آموزشی، آزمون و پیگیری پیشرفت.

> این نرم‌افزار آموزشی است و ابزار تشخیص یا درمان پزشکی نیست.

## Stack

- **Frontend:** Next.js 16.3 + React 19 + TypeScript
- **Backend:** Django + Django REST Framework
- **Auth:** JWT + automatic access-token refresh in the frontend
- **Database now:** SQLite
- **Database later:** PostgreSQL-ready through Django ORM + migrations
- **Content:** deterministic seed command, no admin UI yet

## v0.2 content

- **30 disorders** across 7 categories
- **5 quizzes × 8 questions = 40 questions**
- **6 staged clinical cases × 3 stages = 18 case stages**
- Structured symptoms and differential/related-disorder links
- Institutional source metadata

## v0.2 features

- Registration / login / logout
- Automatic JWT access-token refresh
- Disorders Atlas with search + category filters
- Persian RTL disorder detail V2 with tabs:
  - معرفی
  - نشانه‌ها
  - ویژگی‌های بالینی
  - تشخیص افتراقی
  - ارزیابی
  - درمان
  - تمرین
  - Mini Concept Map
  - یادداشت شخصی
  - منابع
- Compare Disorders V2 for 2–4 disorders
- Preselection from `/compare?add=<slug>`
- Staged Clinical Case V2
- Detailed case score and missed-decision feedback
- Expanded quiz system with server-side scoring
- Private bookmarks
- Private per-disorder notes
- Notes list page
- Activity-based learning progress
- Dashboard V2:
  - topics studied
  - quiz average
  - case average
  - saved topics
  - note count
  - study days
  - continue learning
  - weak topics
  - recent quizzes/cases/notes/saved topics
- Global error UI and loading UI
- CORS support for both `localhost:3000` and `127.0.0.1:3000`

## Data safety / architecture

User-owned data is isolated by authenticated user:

- bookmarks
- notes
- progress
- quiz attempts
- case attempts

The seed command updates seeded educational content without intentionally deleting user-owned records.

The frontend does not depend on SQLite. Database access stays behind Django ORM:

```text
Next.js / React
       ↓
Django REST API
       ↓
Django ORM
       ↓
SQLite now / PostgreSQL later
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

Opening the Django root redirects to the frontend.

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

`http://127.0.0.1:3000` is also supported for local development.

## Validation commands

Backend:

```powershell
python manage.py check
python manage.py test
```

Frontend:

```powershell
npm run typecheck
npm run build
```

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

GET  /api/quizzes/
GET  /api/quizzes/<slug>/
POST /api/quizzes/<slug>/submit/

GET  /api/cases/
GET  /api/cases/<slug>/
POST /api/cases/<slug>/submit/

GET/POST /api/bookmarks/
DELETE   /api/bookmarks/<slug>/

POST /api/progress/<slug>/view/
GET  /api/notes/
GET/PUT/DELETE /api/notes/<slug>/
GET  /api/dashboard/
```

## Scientific content rules

- Do not copy DSM text verbatim.
- Do not invent similarity percentages.
- Avoid presenting educational summaries as personal diagnosis.
- Keep source metadata attached to educational content.
- Before production/content publication, each disorder should receive a dedicated scientific content review and more granular claim-level references.

## Next candidates after v0.2

Not implemented yet:

- Flashcards + spaced repetition
- Full Concept Map across disorders, concepts, therapies and psychologists
- Therapy Atlas
- Psychology Dictionary
- Cognitive Distortions Explorer
- Psychologists / Theories / Timeline
- Study plans, exam dates and streak/heatmap
- XP / achievements
- Brain Atlas
- Content admin panel

See `PROJECT_SPEC.md` for product scope.
