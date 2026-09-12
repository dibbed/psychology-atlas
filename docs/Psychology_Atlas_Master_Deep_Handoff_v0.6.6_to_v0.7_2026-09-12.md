# Psychology Atlas — Master Deep Handoff v0.6.6 → v0.7

**Date:** 2026-09-12  
**Project:** Psychology Atlas  
**Current frozen release:** `v0.6.6 — Final Hardening + Performance + v0.6 Freeze`  
**Next feature release:** `v0.7 — Advanced Branching Clinical Cases + Analytics`

---

## 0. هدف این فایل

این فایل handoff اصلی برای شروع یک تاپیک جدید است. فرض بر این است که دستیار بعدی باید بدون تکرار تاریخچه، پروژه را از وضعیت frozen فعلی ادامه دهد و وارد v0.7 شود.

این سند باید به‌عنوان نقطه شروع خوانده شود، اما در صورت اختلاف بین این فایل و runtime واقعی، **کد، دیتابیس، migrations و Git فعلی منبع نهایی حقیقت هستند**. قبل از تغییرات بزرگ، وضعیت repo و validationهای اصلی دوباره بررسی شوند.

### متن پیشنهادی برای شروع تاپیک جدید

```text
طبق فایل Psychology_Atlas_Master_Deep_Handoff_v0.6.6_to_v0.7_2026-09-12.md پروژه را از وضعیت فعلی ادامه بده.
اول repo و وضعیت frozen v0.6.6 را verify کن، بعد v0.7 را مرحله‌ای و با حفظ تمام قواعد علمی/معماری موجود پیاده‌سازی کن. هرجا defect واقعی دیدی همان مرحله با regression test اصلاح کن. تغییرات را در release boundaryهای منطقی commit کن.
```

---

# 1. وضعیت دقیق پروژه در زمان handoff

## مسیر repo

```text
C:\Users\Meliodas\Downloads\psychology_atlas_fullstack_mvp
```

## Git

```text
branch: main
working tree: clean
current commit:
b3eeacb0cb94481727991fce5dc493d394cf563f

subject:
chore: freeze v0.6.6 final release

tag:
v0.6.6-final
```

Commit قبل از آن:

```text
5016dee9239c3b9414d5bb163e5dfa1b9831d99d
feat: release v0.6.5 graph and search integration
```

Release chain مهم:

```text
20a60e9  chore: freeze v0.5.5 final baseline
4b3704c  feat: release v0.6.2 research promotion foundation
1a37653  feat: release v0.6.3 knowledge read APIs
dfb1523  feat: release v0.6.4 frontend people theory timeline
d788be9  fix: harden source rendering and release metadata
5016dee  feat: release v0.6.5 graph and search integration
b3eeacb  chore: freeze v0.6.6 final release
```

## Git remote / push

در زمان freeze v0.6.6، repo هیچ remote تنظیم‌شده‌ای نداشت:

```text
git remote -v
# no entries
```

Push واقعاً امتحان شد و Git پیام زیر را داد:

```text
fatal: No configured push destination.
```

بنابراین release محلی commit + tag شده ولی push نشده است. **هیچ remote حدسی ساخته نشود.** اگر در تاپیک بعدی remote واقعی از طرف کاربر یا repo اضافه شد، آن‌وقت push انجام شود.

---

# 2. Stack و معماری پایه

## Frontend

```text
Next.js 16.3.3
React 19
TypeScript
App Router
Persian/RTL-first UI
```

Frontend version در freeze فعلی:

```text
0.6.6
```

## Backend

```text
Django 5.2
Django REST Framework
SimpleJWT
SQLite فعلی
PostgreSQL-ready through Django ORM + migrations
```

## Auth / user state

- JWT + refresh flow
- refresh blacklist/logout فعال است
- private user-owned data باید همیشه user-scoped بماند
- هیچ endpoint شخصی نباید cross-user leakage ایجاد کند

---

# 3. قانون بسیار مهم معماری canonical

در backend، runtime اصلی باید در ماژول‌های canonical باقی بماند:

```text
backend/atlas/views.py
backend/atlas/serializers.py
backend/atlas/urls.py
backend/atlas/management/commands/seed_mvp.py
```

برای releaseهای جدید فایل runtime موازی مثل موارد زیر نساز:

```text
v7_views.py
v7_serializers.py
v7_urls.py
```

Frontend type source اصلی:

```text
frontend/lib/types.ts
```

قواعد:

- قابلیت جدید را در معماری موجود integrate کن، نه یک architecture موازی.
- component/API utility/style موجود را reuse کن.
- management command مستقل برای audit/import/export مجاز است، چون runtime موازی محسوب نمی‌شود.
- migrationها additive و قابل‌ردیابی باشند.
- داده تاریخی user-owned و research archive نباید هنگام seed یا migration پاک شود.

---

# 4. Roadmap کلان پروژه

Roadmap اصلی:

```text
v0.3
Study Engine + Concepts + Flashcards + SRS

v0.4
Full Concept Graph + Cognitive Distortions

v0.5
Therapy Atlas

v0.6
Psychologists + Theories + Timeline

v0.7
Advanced Branching Clinical Cases + Analytics

v0.8
Study Mode + Exam Planning + Advanced Recommendations

v0.9
Brain Atlas + Assessments Atlas

v1.0
Admin CMS + Scientific Review + Full cross-domain integration
```

## وضعیت v0.6

```text
v0.6.1  Architecture + Models + Migrations + Provenance            ✅
v0.6.2  Research Promotion + Dedupe + Aliases                    ✅
v0.6.3  Psychologist + Theory + Timeline APIs                     ✅
v0.6.4  Frontend Psychologists/Theories + Timeline UX             ✅
v0.6.5  Knowledge Graph + Global Search integration               ✅
v0.6.6  Final Hardening + Performance + complete v0.6 freeze      ✅
```

**v0.6 اکنون feature-complete و frozen است.**

---

# 5. موجودی runtime فعلی

اعداد مهم در freeze v0.6.6:

```text
Categories                         21
Disorders                         241
Symptoms                          107
Concepts                          148
Cognitive Distortions              20
Concept aliases                    31
Disorder ↔ Concept links           65
Concept ↔ Concept relations        40
Concept ↔ Symptom links            19
Flashcards                         50

Therapy families                   10
Therapy classifications            16
Therapies                          20
Techniques                         35
Therapy ↔ Disorder links           28
Therapy ↔ Concept links            43
Therapy ↔ Technique links          50
Technique ↔ Concept links          54

Psychologists                      76
Psychologist aliases                7
Theories                           45
Theory aliases                      2
Timeline events                    61
```

v0.6 relation inventory:

```text
PsychologistTheory                 48
PsychologistConcept                74
PsychologistTherapy                19
PsychologistPsychologist            0
TheoryConcept                      75
TheoryTherapy                       3
TheoryTechnique                     0
TheoryTheory                        3
TimelinePsychologist               55
TimelineTheory                     27
TimelineTherapy                    25
TimelineTechnique                   1
TimelineConcept                    35
--------------------------------------
Total explicit v0.6 relations     365
```

---

# 6. Research archive و staging

Research archive موجود و immutable-by-default است.

```text
ResearchDataset: 2
ResearchRecord: 1918
SourceReference: 189
```

Exact source archives:

## Dataset 1

```text
psychology_atlas_research_dataset.json
records: 762
bytes: 618107
sha256:
753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0
```

## Dataset 2

```text
psychology_atlas_research_dataset_complete___1.json
records: 1156
bytes: 1281373
sha256:
3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

Commands مهم:

```text
python manage.py verify_research_datasets
python manage.py export_research_datasets <output-dir>
python manage.py promote_research_staging --dry-run
```

آخرین وضعیت promotion:

```text
Psychologists matched                         76
Theories matched                              45
Timeline events matched                       61
v0.6 relation records matched/promoted       303
1 v0.6 staged relation unresolved/unsupported
```

Promotion باید conservative بماند:

- unsupported staging را force-promote نکن.
- unsourced record را canonical نکن.
- fuzzy identity merge عمومی ایجاد نکن.
- aliases canonical identity را overwrite نکنند.
- Claims / ResearchGap همچنان staging-only هستند مگر roadmap صریحاً تغییر کند.

---

# 7. قواعد علمی و ایمنی که نباید شکسته شوند

این پروژه educational است، نه diagnostic/treatment product.

## ممنوع یا خارج از scope

- تشخیص شخصی کاربر
- توصیه درمان شخصی
- treatment ranking شخصی‌سازی‌شده
- efficacy percentage ساختگی
- citation ساختگی
- DOI/PMID/URL/author/date ساختگی
- متن verbatim از DSM که مجوز بازنشر آن وجود ندارد
- تبدیل similarity یا co-occurrence حدسی به relation علمی
- تولید exact date برای داده‌ای که فقط year دارد

## Provenance

هر relation علمی مهم باید provenance صریح داشته باشد.

`source_checked` یعنی:

```text
دارای منبع؛ بازبینی نهایی نشده
```

و **معادل reviewed نیست**.

`citation_from_model_knowledge` در UI باید به‌صورت زیر نمایش داده شود:

```text
ارجاع آرشیوی؛ نیازمند بازبینی مستقل
```

نباید به verified ارتقا پیدا کند مگر منبع مستقل واقعی اضافه شود.

## Scientific debt فعلی

Audit v0.6.6:

```text
active provenance gaps: 0
weak-only v0.6 entities: 59
weak-only v0.6 relations: 52
weak-only rows incorrectly marked reviewed: 0
Timeline precision issues: 0
```

تقسیم 52 relation ضعیف:

```text
PsychologistTheory        5
PsychologistTherapy       9
TheoryConcept             1
TheoryTherapy             3
TheoryTheory              2
TimelinePsychologist     17
TimelineTheory            2
TimelineTherapy           7
TimelineConcept           6
```

این 52 relation باید debt علمی باقی بمانند تا منبع مستقل واقعی پیدا شود. v0.7 نباید صرفاً برای تمیز کردن metric، status آن‌ها را تغییر دهد.

Management command جدید:

```text
python manage.py audit_v06_release
```

این command read-only است و release guard علمی v0.6 محسوب می‌شود.

---

# 8. Timeline precision contract

Timeline از این precisionها استفاده می‌کند:

```text
exact_date
year
year_range
approximate_year
unknown
```

قواعد:

- `year` نباید به `YYYY-01-01` تبدیل شود.
- `year_range` باید start/end معتبر داشته باشد.
- `exact_date` فقط وقتی exact date واقعاً ثبت شده است.
- unknown واقعاً unknown بماند.

Audit فعلی:

```text
invalid precision/date combinations: 0
```

---

# 9. Public v0.6 APIs

Read-only knowledge APIs:

```text
/api/psychologists/
/api/psychologists/<slug>/
/api/theories/
/api/theories/<slug>/
/api/timeline/
/api/timeline/<slug>/
```

Representative real DB query budgets:

```text
Psychologist list      3 queries
Theory list            3 queries
Timeline list          2 queries
Psychologist detail   13 queries
Theory detail         13 queries
Timeline detail        9 queries
```

Pagination project contract:

```text
AtlasPagination.max_page_size = 300
```

---

# 10. Global Search در freeze فعلی

Global Search result families:

```text
disorders
concepts
symptoms
therapies
techniques
psychologists
theories
timeline_events
```

Psychologist/Theory:

- alias-aware
- exact-first
- inactive excluded

Timeline:

- title/slug/date exact-first
- fallback به partial content search
- inactive excluded

v0.6.6 redundant `.exists()` round-tripها را حذف کرد ولی exact-first semantics را حفظ کرد.

Real DB query counts:

```text
Aaron T. Beck           9 queries
Beck Cognitive Model    9 queries
1897                     8 queries
CBT multi-domain        23 queries
```

Focused exact-search test budget:

```text
<= 13 queries
```

Frontend stale-result hardening نیز انجام شده:

- با شروع query جدید result قبلی فوراً clear می‌شود.
- error قبلی clear می‌شود.
- non-abort failure result قدیمی را نگه نمی‌دارد.
- aborted request silent می‌ماند.

---

# 11. Knowledge Graph در freeze فعلی

Graph node types:

```text
Concept        148
Disorder       241
Symptom         34
Therapy         20
Technique       35
Psychologist    76
Theory          45
Timeline        61
-------------------
Total          660
```

Graph:

```text
nodes: 660
edges: 1299
edge kinds: 54
cold build queries: 45
explicit v0.6 edges: 365
v0.6 relation-level source gaps: 0
```

Edge inventory:

```text
729 explicit/runtime non-DSM edges
570 dsm_nearby structural edges
1299 total
```

Graph performance audit v0.6.6:

```text
5 repeated cold builds:
[45, 45, 45, 45, 45] queries

median build time on local SQLite:
~253 ms

warmed cache:
0 DB queries
~2.84 ms measured locally
```

## Graph semantics

v0.6 edges فقط از DB relationهای صریح می‌آیند.

نمونه kindها:

```text
psychologist_theory_developed_or_majorly_associated_with
psychologist_concept_researched_or_developed
theory_concept_includes_construct
theory_theory_extends
timeline_theory_marks_theory_milestone
timeline_technique_marks_technique_evidence_milestone
```

هیچ generic inferred `related` edge برای new domains ایجاد نشود مگر واقعاً relation canonical آن همین semantic باشد.

## Pathfinding

Existing BFS generic است؛ architecture جدید برای pathfinding نساز.

مسیر real DB نمونه:

```text
Aaron T. Beck
→ Automatic Thoughts
→ Cognitive Restructuring

2 hops
```

`dsm_nearby` structural است و به‌طور پیش‌فرض conceptual shortest path را shortcut نمی‌کند.

## Cache invalidation

Graph cache invalidation پوشش می‌دهد:

- Psychologist
- Theory
- TimelineEvent
- تمام v0.6 relation models
- تمام v0.6 relation-source models
- SourceReference
- Therapy/Technique و relationهای مرتبط قدیمی

---

# 12. Frontend routes مهم

## Core domains

```text
/
/search
/map
/disorders
/disorders/[slug]
/concepts
/concepts/[slug]
/therapies
/therapies/[slug]
/techniques/[slug]
/psychologists
/psychologists/[slug]
/theories
/theories/[slug]
/timeline
/timeline/[slug]
```

## Study / user surfaces

```text
/dashboard
/study
/flashcards
/quizzes
/quizzes/[slug]
/cases
/cases/[slug]
/compare
/saved
/notes
```

## DSM MASTER

```text
/dsm
/dsm/[masterId]
/map?scope=dsm
```

---

# 13. DSM MASTER boundary

DSM MASTER لایه reference جدا از canonical Atlas است.

Current important counts:

```text
DSM MASTER records                        438
formal diagnosis records                  243
canonical Disorder pages                  241
Atlas links                               241
DSM graph nodes                           438
DSM graph edges                          2400
self-test questions                      2190
exam tips                                 438
```

DSM text را verbatim بازتولید نکن. Existing project implementation باید به‌عنوان audited educational/reference layer حفظ شود.

---

# 14. v0.6.6 چه چیزهایی اضافه/اصلاح کرد

v0.6.6 feature domain جدید اضافه نکرد؛ hardening و freeze بود.

## 14.1 Scientific release audit

File:

```text
backend/atlas/management/commands/audit_v06_release.py
```

Audit می‌کند:

- entity provenance gap
- relation provenance gap
- weak-only `citation_from_model_knowledge`
- weak-only row اشتباهاً `reviewed`
- Timeline precision problems

Regression tests دارد.

## 14.2 Search performance

File:

```text
backend/atlas/views.py
```

Therapy/Technique/Psychologist/Theory/Timeline exact-first search دیگر برای هر family یک `.exists()` جدا اجرا نمی‌کند.

## 14.3 Search stale UI

File:

```text
frontend/components/GlobalSearch.tsx
```

stale cards در debounce/failure حذف شدند.

## 14.4 Provenance visibility

Files:

```text
frontend/components/ScientificMeta.tsx
frontend/components/KnowledgeMap.tsx
frontend/app/globals.css
```

weak-only source summary به relation cards و Map اضافه شد.

## 14.5 Review labels در Map

Knowledge Map به‌جای raw status code از canonical `ReviewStatus` UI استفاده می‌کند.

---

# 15. آخرین validation/freeze matrix

در release freeze v0.6.6:

```text
backend/.venv pip check                    PASS
Python compileall                          PASS
Django system check                        PASS
makemigrations --check --dry-run          PASS · No changes detected
v0.6 scientific release audit             PASS
research archive verifier                 PASS
promotion dry-run                          PASS
full backend test suite                    PASS · 128/128
frontend TypeScript                        PASS · 0.6.6
Next.js production build                   PASS · 16.3.3 · 23/23 generation units
npm audit --audit-level=low                PASS · 0 vulnerabilities
production HTTP crawl                      PASS · 635/635
Chromium interaction audit                 PASS
SQLite integrity_check                     ok
SQLite foreign_key_check                   0 issues
manifest/version consistency               PASS · 0 mismatches
```

Production crawl 635 route شامل:

```text
241 Disorder details
148 Concept details
20 Therapy details
35 Technique details
76 Psychologist details
45 Theory details
61 Timeline details
9 core/list/search/map routes
```

Browser interaction واقعی روی Chromium headless:

- Search: `Aaron T. Beck`
- clickable Psychologist result
- Map navigation
- weak-source warning روی relation واقعی Paul Salkovskis → Cognitive Model of OCD
- Psychologist detail Theory tab

همگی PASS شدند.

---

# 16. Security/deployment وضعیت فعلی

Production-oriented check با:

```text
DEBUG=0
non-default SECRET_KEY
production ALLOWED_HOSTS
HTTPS frontend origin
```

Django `check --deploy` فقط این warnings را نگه می‌دارد:

```text
security.W005 · SECURE_HSTS_INCLUDE_SUBDOMAINS not enabled
security.W021 · SECURE_HSTS_PRELOAD not enabled
```

این دو عمداً opt-in هستند؛ کورکورانه فعال نشوند.

Production defaults قبلی شامل:

- SSL redirect
- secure session cookie
- secure CSRF cookie
- HSTS seconds
- CSP/security headers
- GZip
- DRF throttling
- JWT refresh blacklist/logout

است.

---

# 17. User-owned data که باید حفظ شود

در seed/migration/refactor نباید داده کاربر حذف یا ownership آن شکسته شود.

موارد مهم:

```text
Disorder bookmarks
User notes
User progress
Concept bookmarks
Concept notes
Concept progress
Flashcard SRS progress
Daily challenge attempts
Study activity
Cognitive distortion practice attempts
Therapy bookmarks
Therapy notes
Quiz/case-related user history where present
```

v0.7 به‌خصوص هنگام بازطراحی Clinical Cases باید migration path داشته باشد که attempt/history قدیمی را حذف نکند.

---

# 18. وضعیت فعلی Clinical Cases قبل از v0.7

Clinical Cases از نسخه‌های قبلی وجود دارند اما roadmap v0.7 قرار است آن‌ها را به **Advanced Branching Clinical Cases + Analytics** ارتقا دهد.

مدل‌های فعلی شناخته‌شده در backend:

```text
ClinicalCase
CaseStep
CaseQuestion
CaseChoice
```

در تست‌های فعلی case submit:

- choice دارای `score_value` است.
- feedback server-side است.
- case performance می‌تواند UserProgress را تغییر دهد.
- integrity پاسخ باید قبل از state mutation validate شود.
- progress قبلاً harden شده تا score ضعیف mastery مصنوعی نسازد.

**قبل از طراحی v0.7، schema/API فعلی Clinical Cases باید دوباره از کد واقعی audit شود.** این handoff عمداً جزئیات فیلدهایی را که verify نشده‌اند حدس نمی‌زند.

---

# 19. هدف محصولی v0.7

v0.7 باید Clinical Cases را از یک sequence آموزشی نسبتاً خطی به یک engine تصمیم‌گیری آموزشی چندمرحله‌ای تبدیل کند.

هدف:

- branching واقعی بر اساس تصمیم کاربر
- حفظ state attempt در server
- تصمیم‌ها مسیر کیس را تغییر دهند
- scoring چندبعدی به‌جای فقط جمع ساده امتیاز
- feedback مبتنی بر reasoning آموزشی
- analytics برای الگوی خطا/تصمیم
- اتصال case به Concept / Disorder / Therapy / Technique به‌صورت آموزشی
- history و resume امن
- بدون تشخیص شخصی و بدون treatment recommendation شخصی

---

# 20. پیشنهاد تقسیم v0.7 به sub-releaseها

این تقسیم **پیشنهادی** است و هنوز implementation نشده؛ در تاپیک بعدی بعد از audit current case code می‌توان آن را نهایی کرد.

## v0.7.1 — Branching Case Architecture + Data Model

هدف:

- audit کامل مدل‌های case موجود
- طراحی additive branching schema
- migration بدون شکستن caseهای قدیمی
- graph validation برای case flow
- provenance/source boundary برای case content در صورت نیاز
- compatibility layer برای caseهای linear فعلی

موضوعات پیشنهادی برای بررسی مدل، نه نام‌های قطعی:

```text
case node / stage
transition / branch rule
decision outcome
attempt
attempt event/history
dimension score
case endpoint state
```

قواعد مهم:

- transition باید explicit باشد.
- branch AI-inferred نباشد.
- orphan/unreachable node تشخیص داده شود.
- accidental infinite cycle کنترل شود.
- terminal states مشخص باشند.
- existing linear CaseStep بتواند migrate/adapt شود.

## v0.7.2 — Server Branching Engine + Attempt State

هدف:

- start/resume attempt
- submit decision
- server determines valid next node
- state/history immutable-enough برای audit
- replay/tamper resistance
- idempotent submit where appropriate
- completed attempt قابل resume-edit نباشد مگر contract صریح داشته باشد

Backend باید source of truth باشد؛ frontend نباید next branch را خودش authoritative محاسبه کند.

## v0.7.3 — Multi-dimensional Scoring + Educational Feedback

به‌جای یک total score ساده، dimensions پیشنهادی بعد از audit:

```text
assessment reasoning
concept recognition
differential reasoning
intervention-selection reasoning
safety/ethics awareness
evidence interpretation
```

اما این dimensions فقط وقتی اضافه شوند که content structure واقعاً پشتیبانی کند.

Guardrails:

- score ≠ clinical competence certificate
- score ≠ diagnostic accuracy on real persons
- score ≠ treatment recommendation authority
- negative decision لزوماً صفر learning value نیست

## v0.7.4 — Branching Case Frontend Runner

Frontend نیاز دارد:

- stage context
- decision options
- progressive disclosure
- feedback state
- timeline/history of decisions
- resume state
- completed summary
- accessible keyboard interaction
- RTL/Persian-first design
- responsive mobile layout

از existing app design system استفاده شود؛ UI architecture موازی ساخته نشود.

## v0.7.5 — Case Analytics

Analytics آموزشی، نه clinical analytics.

پیشنهادها:

- attempt count
- completion rate
- branch frequency
- most-missed decisions
- score dimensions
- concept-level weakness signals
- retry improvement
- time/order metadata فقط اگر privacy/utility آن روشن باشد

Analytics user-specific باید ownership-safe باشد.

Aggregate analytics باید از data leakage جلوگیری کند.

## v0.7.6 — Cross-domain Integration + Final Audit

Integration احتمالی:

- Case ↔ Disorder
- Case ↔ Concept
- Case ↔ Therapy
- Case ↔ Technique
- StudyActivity
- Dashboard
- Recommendation Engine، فقط در حد educational study recommendation

در پایان:

- deep bug audit
- query budgets
- browser crawl
- attempt integrity tests
- permission tests
- migration/seed preservation
- final v0.7 freeze

---

# 21. پیشنهاد اولین کار در تاپیک بعدی

بهترین شروع برای v0.7 این است که **مستقیماً schema جدید ننویسیم**. ابتدا audit دقیق current Clinical Case subsystem انجام شود.

ترتیب پیشنهادی:

```text
1. git status / current commit verification
2. inspect ClinicalCase / CaseStep / CaseQuestion / CaseChoice models
3. inspect serializers / views / urls for cases
4. inspect case submit scoring and UserProgress mutation
5. inspect existing seed case content
6. inspect frontend /cases and /cases/[slug]
7. inspect all case-related tests
8. map current constraints and ownership/history behavior
9. write v0.7.1 schema plan based on actual code
10. implement additive branching foundation
11. migrations + regression tests
12. full validation
13. logical commit boundary
```

این audit باید پاسخ دهد:

- آیا attempt model مستقل وجود دارد یا فقط submission/progress indirect است؟
- آیا answer history ذخیره می‌شود؟
- آیا question/choice ordering stable است؟
- آیا case versioning لازم است؟
- آیا old attempts باید به version قدیمی case bind شوند؟
- آیا branch graph نیاز به cycle دارد یا DAG کافی است؟
- terminal node semantics چیست؟
- score aggregation فعلی دقیقاً چگونه است؟
- StudyActivity integration فعلی چه contractی دارد؟

تا این موارد از runtime واقعی خوانده نشده‌اند، schema branching نباید بر پایه حدس طراحی شود.

---

# 22. v0.7 integrity rules پیشنهادی

این‌ها باید هنگام implementation به تست تبدیل شوند.

## Branch graph integrity

- هر start case دقیقاً یک entry point معتبر داشته باشد.
- transition target باید متعلق به همان case باشد.
- inactive node/choice نباید branch target فعال باشد.
- invalid choice ID قبل از mutation reject شود.
- user نتواند nodeای را submit کند که current state attempt نیست.
- user نتواند step را skip کند با دستکاری request.
- duplicate submit نباید double-score/double-progress کند.
- unreachable content report شود.
- cycle اگر مجاز نیست reject شود؛ اگر مجاز است باید bounded exit contract داشته باشد.

## Attempt integrity

- attempt متعلق به user دیگر قابل خواندن/نوشتن نباشد.
- completion state immutable یا strongly controlled باشد.
- decision history server-owned باشد.
- next node authoritative از server بیاید.
- old case version history حفظ شود اگر case content بعداً تغییر کند.

## Scoring integrity

- score_value client-trusted نباشد.
- client فقط choice/action identifier بفرستد.
- score server-side resolve شود.
- max score و dimension score از canonical content محاسبه شود.
- weak performance progress مصنوعی ایجاد نکند.

---

# 23. v0.7 scientific/clinical guardrails

Clinical Cases باید fictional/educational framing واضح داشته باشند.

Case نباید:

- از کاربر بخواهد خودش یا شخص واقعی را diagnose کند.
- خروجی «شما احتمالاً فلان اختلال را دارید» تولید کند.
- treatment recommendation شخصی برای user بسازد.
- از score به‌عنوان clinical competency certification استفاده کند.

Case feedback باید از جنس زیر باشد:

```text
در این سناریوی آموزشی، این انتخاب با داده‌های ارائه‌شده سازگارتر است زیرا...
```

نه:

```text
برای چنین فردی حتماً باید این درمان انجام شود.
```

اگر Therapy/Technique در case مطرح شد، context و evidence semantics existing project حفظ شود.

---

# 24. Versioning پیشنهاد شده برای Case content

در v0.7 بهتر است قبل از پیاده‌سازی attempt persistence بررسی شود که آیا case content versioning لازم است.

دلیل:

اگر user attempt را روی نسخه A شروع کند و بعد seed نسخه B همان case را تغییر دهد، branch history نباید بی‌معنی شود.

راه‌حل‌های ممکن برای بررسی:

- immutable case revision
- attempt snapshot of structural version
- version field روی case graph
- seed-managed revision ownership

اما بدون audit current schema هیچ‌کدام را کورکورانه implement نکن.

---

# 25. Performance expectations برای v0.7

Query budgetها باید از ابتدا test شوند، ولی عدد نهایی بعد از طراحی واقعی تعیین شود.

حداقل expectation:

- case list N+1 نداشته باشد.
- case detail graph با تعداد node خطی query رشد نکند.
- attempt submit query count bounded باشد.
- analytics dashboard aggregate per-row loop نداشته باشد.
- prefetch/select_related هدفمند استفاده شود.

Performance را بعد از fixture واقعی measure کن و سپس budget test freeze کن؛ budget حدسی از ابتدا ننویس.

---

# 26. Seed policy برای v0.7

`seed_mvp.py` canonical seed command باقی می‌ماند.

قواعد:

- repeated seed idempotent باشد.
- seed-owned case content با `seed_managed` یا ownership semantics فعلی هماهنگ باشد.
- user attempts/history حذف نشوند.
- imported/research-owned content کورکورانه deactivate نشود.
- old case revision مورد استفاده attemptهای historical نابود نشود.

قبل از تغییر seed، tests preservation اضافه کن.

---

# 27. Files که احتمالاً در v0.7 مهم خواهند بود

Backend:

```text
backend/atlas/models.py
backend/atlas/serializers.py
backend/atlas/views.py
backend/atlas/urls.py
backend/atlas/tests.py
backend/atlas/management/commands/seed_mvp.py
backend/atlas/signals.py
```

Frontend:

```text
frontend/lib/types.ts
frontend/lib/api.ts
frontend/app/cases/page.tsx
frontend/app/cases/[slug]/page.tsx
frontend/components/*Case*
frontend/app/globals.css
frontend/app/dashboard/* or dashboard components where applicable
```

Release/docs:

```text
README.md
PROJECT_SPEC.md
BUILD_MANIFEST.json
docs/
```

v0.6 audit command:

```text
backend/atlas/management/commands/audit_v06_release.py
```

---

# 28. Validation commands پایه برای هر release slice

Backend project venv:

```text
backend\.venv\Scripts\python.exe manage.py check
backend\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
backend\.venv\Scripts\python.exe manage.py test atlas
backend\.venv\Scripts\python.exe -m pip check
```

Research/scientific:

```text
python manage.py verify_research_datasets
python manage.py promote_research_staging --dry-run
python manage.py audit_v06_release
```

Frontend:

```text
npm run typecheck
npm run build
npm audit --audit-level=low
```

Git hygiene:

```text
git diff --check
git status
git diff --stat
git diff --cached --check
```

Production release gate بعد از feature slice بزرگ:

- Django runtime smoke
- Next production start
- route crawl
- Chromium interaction audit
- clean generated-file diff
- version/manifest consistency

---

# 29. Generated / environment notes

## `frontend/next-env.d.ts`

Next build ممکن است این فایل را تغییر دهد. اگر فقط generated churn است و intentional change نیست:

```text
git checkout -- frontend/next-env.d.ts
```

قبل از commit بررسی شود.

## Python environment

Release environment معتبر:

```text
backend/.venv
```

Python global ویندوز dependency conflictهای مربوط به ابزارهای دیگر داشت؛ release gate بر اساس global Python سنجیده نشود.

`backend/.venv pip check` در freeze v0.6.6 PASS است.

---

# 30. User working preferences

کاربر انتظار دارد:

- تغییر واقعی روی repo انجام شود، نه فقط پیشنهاد متنی.
- audit عمیق باشد.
- defect واقعی اگر در همان مسیر امن قابل اصلاح است، همان‌جا اصلاح شود.
- برای regression test نوشته شود.
- commit فقط در logical release/freeze boundary زده شود.
- وسط کار updateهای کوتاه و مفید داده شود.
- سؤال تکراری که context پاسخ آن را دارد پرسیده نشود.
- فارسی ارتباط برقرار شود.
- scientific/provenance semantics حفظ شود.
- citation/translation/date ساختگی ایجاد نشود.
- اگر push ممکن است و remote واقعی وجود دارد، در release boundary push انجام شود.

---

# 31. چیزهایی که نباید در شروع v0.7 تغییر کنند

بدون دلیل مستقیم برای Clinical Cases دست نزن به:

- research archive hashes
- Psychologist/Theory/Timeline scientific statuses
- Graph semantics frozen v0.6
- DSM MASTER corpus
- Therapy scientific provenance
- existing user-owned data contracts
- v0.6 release tag/history

اگر v0.7 نیاز دارد به این بخش‌ها وصل شود، integration additive انجام شود.

---

# 32. Known debt / intentionally deferred

این موارد bug پنهان محسوب نمی‌شوند؛ roadmap/debt شناخته‌شده‌اند:

- 59 weak-only v0.6 entities نیازمند source مستقل قوی‌تر
- 52 weak-only v0.6 relations نیازمند independent review
- full claim-level scientific review workflow تا v1.0
- Admin CMS تا v1.0
- Brain Atlas تا v0.9
- Assessment Atlas تا v0.9
- full exam planning تا v0.8
- XP/achievements فعلاً deferred
- personalized treatment recommendations عمداً خارج scope

v0.7 نباید scope creep به این حوزه‌ها پیدا کند.

---

# 33. Definition of Done پیشنهادی برای v0.7

v0.7 زمانی واقعاً بسته شود که:

1. Branching Clinical Case engine server-authoritative باشد.
2. attempt history user-scoped و tamper-resistant باشد.
3. old linear cases/data شکسته نشوند.
4. scoring چندبعدی یا scoring نهایی با content semantics واقعی هماهنگ باشد.
5. duplicate/invalid submit state را خراب نکند.
6. branch graph integrity test داشته باشد.
7. frontend runner در desktop/mobile/RTL کار کند.
8. resume/completion state قابل‌اعتماد باشد.
9. analytics آموزشی ownership-safe باشد.
10. cross-domain links explicit باشند، نه inferred.
11. full backend suite PASS باشد.
12. frontend typecheck/build/audit PASS باشد.
13. migration drift صفر باشد.
14. DB/research integrity حفظ شود.
15. production crawl/browser interaction PASS باشد.
16. docs/manifest/version sync باشند.
17. Git clean + release commit/tag انجام شود.
18. اگر remote واقعی وجود داشت push شود.

---

# 34. آخرین وضعیت رسمی برای handoff

```text
Release: Psychology Atlas v0.6.6
State: FINAL / FROZEN
Branch: main
Commit: b3eeacb0cb94481727991fce5dc493d394cf563f
Tag: v0.6.6-final
Working tree at handoff creation start: clean
Remote: not configured
Next phase: v0.7 Advanced Branching Clinical Cases + Analytics
```

v0.6 به‌عنوان پایه پایدار برای v0.7 در نظر گرفته شود. تغییرات جدید باید additive، regression-tested، provenance-safe، user-data-safe و release-bounded باشند.

---

# 35. دستور عملی برای دستیار تاپیک بعدی

بعد از خواندن این فایل:

```text
1. repo را در مسیر ثبت‌شده باز کن.
2. HEAD/tag/clean status را verify کن.
3. هیچ feature v0.6 را دوباره بازطراحی نکن مگر defect واقعی مرتبط با v0.7 کشف شود.
4. Clinical Case subsystem فعلی را عمیق audit کن.
5. بر اساس کد واقعی، v0.7 را به sub-releaseهای منطقی نهایی کن.
6. از v0.7.1 معماری branching شروع کن.
7. schema را additive و history-safe طراحی کن.
8. قبل از mutation tests integrity بنویس.
9. پس از هر slice تست کامل و diff audit بگیر.
10. در release boundary commit بزن؛ push فقط با remote واقعی.
```

**نقطه شروع پیشنهادی مستقیم:**

```text
Deep audit of current ClinicalCase / CaseStep / CaseQuestion / CaseChoice models,
case serializers/views/URLs, submit scoring, progress mutation, seed behavior,
frontend case runner, and all case-related tests — then implement v0.7.1.
```

---

**End of handoff — v0.6.6 → v0.7**
