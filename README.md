# Psychology Atlas — v0.6.3 · Psychologist + Theory + Timeline Read APIs

یک وب‌اپ Full-Stack فارسی و RTL برای یادگیری تعاملی روان‌شناسی. v0.6.3 داده‌های source-backed و deduplicated نسخه v0.6.2 را از طریق APIهای read-only برای Psychologist، Theory و Timeline در دسترس می‌گذارد. خروجی‌ها aliases، review status، provenance سطح entity و relation، semantics تاریخی صریح و date precision واقعی Timeline را حفظ می‌کنند. Frontend این دامنه‌ها و Knowledge Graph/Global Search integration هنوز عمداً برای v0.6.4 و v0.6.5 نگه داشته شده‌اند.

> این نرم‌افزار آموزشی است و ابزار تشخیص، درمان یا جایگزین ارزیابی حرفه‌ای نیست.

## v0.6.3 Psychologist + Theory + Timeline APIs

Endpointهای عمومی جدید:

```text
GET /api/psychologists/
GET /api/psychologists/<slug>/
GET /api/theories/
GET /api/theories/<slug>/
GET /api/timeline/
GET /api/timeline/<slug>/
```

List APIها از pagination فعلی پروژه استفاده می‌کنند و search/filterهای دامنه‌ای دارند. نمونه فیلترها:

```text
psychologists: q, review_status, nationality, theory, concept, therapy, birth_from, birth_to
theories:      q, review_status, domain, modern_status, psychologist, concept, therapy, technique
timeline:      q, event_type, date_precision, review_status, category,
               psychologist, theory, therapy, technique, concept, year_from, year_to
```

Detail APIها relationهای علمی را همراه sourceهای همان relation برمی‌گردانند؛ provenance شامل title/organization/citation/URL و در صورت موجود بودن `authors`, `doi`, `pmid`, `verification_status` است. API هیچ citation یا تاریخ جدیدی جعل نمی‌کند.

Timeline granularity نیز عین DB حفظ می‌شود؛ رویداد year-only مثل `1980` همچنان `exact_date=null` دارد و به `1980-01-01` تبدیل نمی‌شود.

Query budget واقعی روی دیتابیس فعلی:

```text
Psychologist list (76 rows)   3 queries
Theory list (45 rows)         3 queries
Timeline list (61 rows)       2 queries
Psychologist detail          13 queries
Theory detail                13 queries
Timeline detail               9 queries
```

Validation این slice:

```text
6/6 targeted v0.6.3 API tests PASS
120/120 full backend tests PASS
Knowledge Graph unchanged: 478 nodes / 934 edges / 18 queries
No migration required
```

سند عمیق v0.6.3:

```text
docs/Psychology_Atlas_v0.6.3_Knowledge_APIs_2026-09-05.md
```

## v0.6.2 Conservative Research Promotion

وضعیت runtime بعد از promotion واقعی:

```text
Psychologist       76
Theory              45
TimelineEvent       61
PsychologistAlias    7
TheoryAlias           2
```

Stagingهایی که عمداً promote نشدند:

```text
Psychologist        37 identity group بدون source قابل‌حل
Theory               2 identity بدون source قابل‌حل
TimelineEvent         2 event بدون source قابل‌حل
```

Promotion روی نام خام یا `external_id` کورکورانه انجام نمی‌شود. duplicateهای بین دو corpus با identity resolution محافظه‌کارانه merge شدند؛ fuzzy person matching عمومی وجود ندارد. نمونه‌های واقعی merge‌شده شامل `Ivan Pavlov` / `Ivan P. Pavlov` و `Beck Cognitive Model` / `Beck's cognitive model` هستند و spellingهای جایگزین به alias منتقل می‌شوند.

Relationهای source-backed v0.6 که اکنون canonical شده‌اند شامل:

```text
PsychologistTheory       48
PsychologistConcept      74
PsychologistTherapy      19
TheoryConcept            75
TheoryTherapy             3
TheoryTheory              3
TimelinePsychologist     55
TimelineTheory           27
TimelineTherapy          25
TimelineTechnique         1
TimelineConcept          35
```

تمام entityها و relationهای promoted بالا provenance صریح `SourceReference` دارند. پس از تکمیل semanticsهای Timeline، تعداد relationهای آینده‌ای که endpointهایشان resolve و sourceشان معتبر است ولی هنوز بدون مدل canonical مانده‌اند:

```text
0
```

Timeline semantics واقعی staging بدون collapse شدن به `related` عمومی حفظ می‌شوند، از جمله:

```text
involves_person
marks_theory_milestone
marks_therapy_milestone
marks_technique_evidence_milestone
```

`TimelineTechnique` در همین slice اضافه شد چون corpus واقعی یک milestone شواهد برای Technique دارد. در مقابل `TheoryTechnique` فعلاً صفر است، چون relation staging موجود به Techniqueای اشاره می‌کند که خودش هنوز source-backed/runtime-mapped نیست؛ بنابراین force-promotion انجام نشده است.

فرمان مستقل promotion:

```text
python manage.py promote_research_staging
python manage.py promote_research_staging --dry-run
```

`import_research_datasets` نیز در حالت promotion، بعد از ingestion و promotionهای قبلی همین pipeline را اجرا می‌کند. `--no-promote` همچنان staging-only باقی می‌ماند.

Migrationهای v0.6.2:

```text
0019_v062_research_promotion_semantics.py
0020_v062_timeline_relation_semantics.py
0021_v062_timeline_therapy_technique_semantics.py
```

سند عمیق v0.6.2:

```text
docs/Psychology_Atlas_v0.6.2_Research_Promotion_2026-09-05.md
```

## v0.6.1 Architecture Foundation

مدل‌های canonical جدید:

```text
Psychologist
PsychologistAlias
Theory
TheoryAlias
TimelineEvent
```

Provenance مستقیم entityها از همان registry مشترک `SourceReference` استفاده می‌کند:

```text
PsychologistSource
TheorySource
TimelineEventSource
```

Relationهای صریح foundation:

```text
PsychologistTheory
PsychologistConcept
PsychologistTherapy
PsychologistPsychologist

TheoryConcept
TheoryTherapy
TheoryTechnique
TheoryTheory

TimelinePsychologist
TimelineTheory
TimelineTherapy
TimelineConcept
```

برای تمام relationهای بالا مدل `...Source` اختصاصی وجود دارد. `TheoryTechnique` عمداً اضافه شد چون در staging واقعی relation از نوع `theory -> technique / grounds` وجود دارد. Attributionهای شخصی دیگر به یک `creator` مبهم collapse نمی‌شوند و vocabularyهایی مثل `proposed`, `co_proposed`, `developed`, `co_developed`, `expanded`, `researched`, `contributed_to` و `associated_with` صریح‌اند.

`TimelineEvent` precision تاریخی را صریح نگه می‌دارد:

```text
exact_date
year
year_range
approximate_year
unknown
```

در نتیجه اگر source فقط سالی مثل `1879` داشته باشد، schema اجازه نمی‌دهد آن سال به تاریخ ساختگی `1879-01-01` تبدیل شود.

Migration این slice:

```text
0018_v061_psychologists_theories_timeline_foundation.py
```

در خود v0.6.1 Research promotion عمداً غیرفعال بود تا schema قبل از ورود داده تثبیت شود. این مرز تاریخی اکنون در v0.6.2 با pipeline محافظه‌کارانه و source-backed بالا تکمیل شده است.

سند عمیق طراحی:

```text
docs/Psychology_Atlas_v0.6.1_Architecture_Foundation_2026-09-05.md
```

## Therapy Atlas

هسته seeded Therapy Atlas همچنان عمداً کوچک و قابل‌ردیابی است؛ علاوه بر آن، v0.5.5 می‌تواند research corpusهای source-backed را با ownership مستقل import کند. محتوای imported هیچ ادعای effectiveness percentage، رتبه‌بندی «بهترین درمان» یا recommendation شخصی ایجاد نمی‌کند. مدل‌های اصلی runtime:

```text
TherapyFamily
TherapyClassification
Therapy
TherapyAlias
TherapyBookmark
TherapyNote
Technique
TechniqueAlias
TherapyClassificationLink
TherapyTechnique
TherapyDisorder
TherapyConcept
TechniqueConcept
+ explicit SourceReference link models
```

تصمیم‌های اصلی schema:

- `Therapy` و `Technique` دو entity مستقل‌اند.
- هر Therapy یک `TherapyFamily` اصلی دارد، اما classificationهای هم‌پوشان می‌توانند چندتایی باشند.
- `TherapyDisorder.clinical_role` از `evidence_basis` جدا است تا «نقش بالینی» با «نوع پشتوانه شواهد» یکی نشود.
- provenance جدید registry جدا نمی‌سازد و از `SourceReference` موجود استفاده می‌کند.
- `review_status` فقط metadata ساده `unreviewed / source_checked / reviewed` است؛ workflow کامل review همچنان برای v1.0 باقی مانده است.
- content entityهای اصلی `is_active` و `seed_managed` دارند تا lifecycle آینده history-safe بماند.
- فایل‌های runtime نسخه‌ای قدیمی ادغام شده‌اند؛ backend اکنون `views.py`, `serializers.py` و `seed_mvp.py` canonical دارد و فایل‌های `v3_*` / `v4_*` موازی ندارد.
- migration history حذف نشده است، چون برای ارتقای امن دیتابیس‌های قبلی لازم است.

Therapy migrations:

```text
0013_therapy_technique_techniqueconcept_and_more.py
0014_studyactivity_therapy_therapybookmark_therapynote.py
0015_researchdataset_researchrecord_and_more.py
0016_techniqueconcept_seed_managed_and_more.py
0017_researchdataset_ingestion_audit_and_more.py
```

### Research Dataset Ingestion (v0.5.5 data enrichment)

دو corpus پژوهشی JSON به‌صورت کامل داخل DB import شده‌اند و فایل‌های اصلی پس از ممیزی SHA/round-trip از root پروژه حذف شده‌اند. برای import فایل پژوهشی جدید یا re-import فایل بازسازی‌شده:

```bash
python manage.py import_research_datasets <path-a.json> <path-b.json>
```

برای verify کردن آرشیو DB بدون نیاز به فایل اصلی:

```bash
python manage.py verify_research_datasets
```

برای بازسازی دقیق فایل‌های اصلی از DB:

```bash
python manage.py export_research_datasets <output-dir>
```

اگر فایل ورودی موقت در اختیار باشد، حالت‌های ایمن import نیز حفظ شده‌اند:

```bash
python manage.py import_research_datasets <paths...> --dry-run
python manage.py import_research_datasets <paths...> --no-promote
```

معماری import دو لایه است:

- `ResearchDataset` علاوه بر JSON parsed، metadata، statistics، quality-control و SHA-256، حالا `raw_text` دقیق فایل اصلی و `ingestion_audit` را هم نگه می‌دارد؛ بنابراین source file بعد از import قابل بازسازی byte-for-byte است.
- `ResearchRecord` هر entity/relation/claim را با external ID، canonical key، source IDs، `name_en/name_fa` و وضعیت promotion ایندکس می‌کند.
- Sourceها با اولویت DOI → URL → title/year dedupe می‌شوند و author/DOI/PMID/verification metadata حفظ می‌شود.
- داده‌های schema-compatible و source-backed به Concept/Symptom/Therapy/Technique و relationهای موجود promote می‌شوند؛ داده‌های ضعیف‌تر یا ناسازگار staging-only می‌مانند.
- Psychologist/Theory/Timeline/Claim در این مرحله research-staging هستند و به معنی شروع v0.6 نیستند، اما normalized bilingual index آن‌ها کامل است.
- existing curated content overwrite نمی‌شود؛ importer فقط رکورد جدید می‌سازد یا فیلدهای خالی را محافظه‌کارانه تکمیل می‌کند.
- relationهای imported دارای `seed_managed=False` هستند؛ `seed_mvp` فقط relationهای متعلق به خودش را مدیریت می‌کند و research relationها را deactivate نمی‌کند.
- bilingual audit روی بخش‌های آموزشی اصلی رکوردبه‌رکورد انجام می‌شود. عنوان رسمی مقالات، DOI/PMID و bibliographic metadata عمداً به ترجمه ساختگی تبدیل نمی‌شوند و به زبان اصلی منبع حفظ می‌شوند.

وضعیت corpus فعلی پس از import و حذف فایل‌های source:

```text
2 ResearchDataset
1,918 ResearchRecord
189 canonical SourceReference
148 Concept (20 cognitive distortions)
107 Symptom
241 Disorder (existing canonical disorder catalog preserved)
10 TherapyFamily
16 TherapyClassification
20 Therapy
35 Technique
176 research relationships promoted with resolved provenance
478 Knowledge Graph nodes / 934 edges / 18 build queries
```

آرشیو دقیق فایل‌های حذف‌شده داخل DB:

```text
psychology_atlas_research_dataset.json
618,107 bytes
SHA-256 753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0

psychology_atlas_research_dataset_complete___1.json
1,281,373 bytes
SHA-256 3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

داده‌های آینده که losslessly در staging محفوظ‌اند شامل 130 Psychologist record، 53 Theory record، 63 Timeline event، 82 Claim، 25 Research Gap و audit/correction metadata هستند.

### Scientific Therapy Seed

موجودی seeded Therapy Atlas عمداً کوچک و source-backed نگه داشته شده است:

```text
3 Therapy families
5 overlapping classifications
6 Therapies
9 Techniques
9 Therapy ↔ Disorder links
7 Therapy ↔ Concept links
10 Therapy ↔ Technique links
8 Technique ↔ Concept links
10 dedicated Therapy sources
```

Therapyهای seeded:

```text
Cognitive Behavioral Therapy (CBT)
Behavioral Activation (BA)
Interpersonal Psychotherapy (IPT)
Dialectical Behavior Therapy (DBT)
Cognitive Processing Therapy (CPT)
Prolonged Exposure Therapy (PE)
```

منابع seed از NICE، NIMH، Beck Institute و VA National Center for PTSD هستند. تمام Therapy/Techniqueهای seeded با `review_status=source_checked` ثبت می‌شوند، نه `reviewed`.

### Therapy API

```text
GET /api/therapies/
GET /api/therapies/taxonomy/
GET /api/therapies/compare/?slugs=<2-to-4-slugs>
GET /api/therapies/<slug>/
GET/POST /api/therapy-bookmarks/
DELETE   /api/therapy-bookmarks/<slug>/
GET      /api/therapy-notes/
GET/PUT/DELETE /api/therapy-notes/<slug>/
GET /api/techniques/
GET /api/techniques/<slug>/
```

فیلترهای Therapy شامل `q`, `family`, `classification`, `disorder`, `concept`, `evidence_basis`, `clinical_role` هستند. Techniqueها با `q`, `therapy`, `concept` فیلتر می‌شوند. Detail responseها provenance هر relation را نیز برمی‌گردانند.

### Therapy Atlas Frontend

```text
/therapies
/therapies/[slug]
/techniques/[slug]
```

- Therapy Explorer دارای جست‌وجوی فارسی/انگلیسی، Family rail، classification chips، مرتب‌سازی اتصال/نام و حالت card/compact است.
- Therapy و Technique در UI همچنان دو Entity مستقل‌اند.
- صفحه Therapy بخش‌های معرفی، تکنیک‌ها، زمینه‌های بالینی، مفاهیم، شواهد/محدودیت‌ها و منابع دارد.
- رابطه‌های Therapy ↔ Disorder، Therapy ↔ Concept و Therapy ↔ Technique همراه provenance همان رابطه نمایش داده می‌شوند.
- Technique Detail درمان‌های متصل، Conceptهای متصل، محدودیت‌ها، safety note و منابع مستقیم را نمایش می‌دهد.
- Evidence Basis در UI به‌صراحت به‌عنوان نوع پشتوانه شواهد نمایش داده می‌شود، نه رتبه‌بندی شخصی درمان.

### Compare + Personal Features + Final Hardening

- `/compare?type=therapy` بین ۲ تا ۴ Therapy را با ترتیب انتخاب کاربر و فقط روی ابعاد ساختاریافته مقایسه می‌کند: Family، classifications، اصول، ساختار، Techniques، Disorder relations، Concepts، limitations، safety و provenance.
- Compare هیچ efficacy ranking، similarity percentage یا «بهترین درمان» تولید نمی‌کند و API نیز disclaimer صریح برمی‌گرداند.
- Therapy Detail اکنون Bookmark خصوصی، لینک مستقیم به Therapy Compare و تب «یادداشت من» دارد.
- `TherapyBookmark` و `TherapyNote` کاملاً user-scoped هستند؛ duplicate bookmark idempotent است، note تا ۱۲٬۰۰۰ کاراکتر محدود می‌شود و محتوای inactive در لیست‌های شخصی نمایش داده نمی‌شود.
- Saved، Notes و Dashboard اکنون Therapy را کنار Disorder و Concept پوشش می‌دهند.
- Bookmark/Note درمان در `StudyActivity` ثبت می‌شود، اما هیچ `UserTherapyProgress` یا mastery percentage ساخته نشده است.
- Compare requestها در هر دو حوزه Disorder/Therapy abort-safe شده‌اند تا response قدیمی نتواند انتخاب جدید را overwrite کند.
- query plan Therapy Compare از ۲۵ query ثابت به حداکثر ۱۴ query در regression fixture کاهش یافت و budget تستی دارد.

### Cross-domain Integration + Knowledge Graph

- تب درمان در Disorder Detail اکنون relationهای ساختاریافته `TherapyDisorder` را همراه Clinical Role، Evidence Basis و منبع همان رابطه نمایش می‌دهد.
- Concept Detail درمان‌ها و Techniqueهای مرتبط را مستقیماً از `TherapyConcept` و `TechniqueConcept` نشان می‌دهد.
- Global Search اکنون Disorder، Concept، Symptom، Therapy، Technique و DSM MASTER را پوشش می‌دهد و aliasهای دقیق مانند CBT/ERP را اولویت می‌دهد.
- Atlas Graph اکنون پنج node type دارد: Concept، Disorder، Symptom، Therapy و Technique.
- چهار خانواده edge جدید به Graph اضافه شده‌اند: Therapy ↔ Disorder، Therapy ↔ Concept، Therapy ↔ Technique و Technique ↔ Concept.
- edgeهای Therapy/Technique در Graph provenance منبع دارند و تغییر source/relation cache را invalidate می‌کند.
- Path Finder همچنان shortest path واقعی را روی edgeهای ذخیره‌شده محاسبه می‌کند؛ `dsm_nearby` به‌طور پیش‌فرض shortcut مسیر مفهومی نیست.
- Graph هیچ treatment ranking یا personalized recommendation تولید نمی‌کند.

## Stack

- **Frontend:** Next.js 16.3.3 + React 19 + TypeScript
- **Backend:** Django 5.2 + Django REST Framework
- **Auth:** JWT + automatic access-token refresh
- **Database now:** SQLite
- **Database later:** PostgreSQL-ready through Django ORM + migrations
- **Content:** deterministic/idempotent seed command, no content-admin UI yet

## Preserved hardening baseline

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

## Current content inventory

- **241 canonical disorder pages** across 20 DSM chapters + 1 supplemental medication/adverse-effects section
- **30 structured symptoms**
- **44 psychology concepts**
- **12 Cognitive Distortions** grounded in the Beck Institute educational worksheet taxonomy
- **8 searchable Concept aliases**
- **65 Disorder ↔ Concept links**
- **23 Concept ↔ Concept relationships**
- **15 Concept ↔ Symptom links**
- **50 flashcards**
- **6 source-backed therapies**
- **9 source-backed techniques**
- **9 Therapy ↔ Disorder evidence links**
- **18 Cognitive Distortion recognition practice items × 4 choices = 72 choices**
- **12 daily challenges × 4 choices**
- **5 quizzes × 8 questions = 40 questions**
- **6 staged clinical cases × 3 stages = 18 case stages**
- Institutional source metadata attached to every seeded concept and disorder
- **DSM-5-TR Persian MASTER reference layer:** 438 addressable educational/structural records imported from the audited 2026-08-29 bundle without flattening non-diagnosis records into disorders
- **243 formal-diagnosis MASTER records → 241 canonical Atlas disorder pages**; 2 duplicate structural occurrences remain independently addressable in DSM MASTER but collapse to one Disorder page each
- **30 curated disorder pages preserved + 211 DSM-generated disorder pages**
- **22 Neurodevelopmental Disorder pages**, including Autism Spectrum Disorder and Attention-Deficit/Hyperactivity Disorder
- **Disorders Explorer:** sticky chapter rail, responsive chapter selector, deep Persian/English search, grid/compact view modes, keyboard `/` focus shortcut, and browser-local recently viewed disorders

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

## Core features

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

### Knowledge Graph

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
Therapy ↔ Disorder
Therapy ↔ Concept
Therapy ↔ Technique
Technique ↔ Concept
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

Current graph:

```text
330 nodes
  44 concepts
 241 canonical disorders
  30 symptoms
   6 therapies
   9 techniques

23 Concept ↔ Concept edges
65 Disorder ↔ Concept edges
15 Concept ↔ Symptom edges
65 Disorder → Symptom edges
 9 Therapy ↔ Disorder edges
 7 Therapy ↔ Concept edges
10 Therapy ↔ Technique edges
 8 Technique ↔ Concept edges
570 DSM MASTER nearby-title edges
= 772 edges
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
- Recommendation Engine

The streak and heatmap remain backward-compatible with historical quiz, case and disorder-progress data while avoiding double-counting StudyActivity events.

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

### Search

Route:

```text
/search
```

Searches simultaneously across:

- Disorders
- Concepts
- Symptoms linked to active disorders

The client uses cancellation/debounce to prevent stale request races.

### Dashboard

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

## Core account and learning features

The current system preserves the established learning core:

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

Current migration history includes:

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

Current validation baseline:

```text
Django system check                  PASS
Backend tests                        98 / 98 PASS
DSM import idempotency               PASS · 1 corpus / 438 records / 241 canonical Disorder pages / 6 sources
DSM diagnosis sync                    PASS · 243 formal records → 241 canonical pages · 211 created + 30 curated preserved
Neurodevelopmental chapter            PASS · 22 Disorder pages including Autism Spectrum Disorder and ADHD
DSM resolved relations               PASS · 1,826 nearby / 159 differential
DSM graph                            PASS · 438 nodes / 2,400 edges
Atlas graph with DSM layer           PASS · 330 nodes / 772 edges
DSM study inventory                  PASS · 2,190 self-tests / 438 exam tips / 14 glossary terms
DSM source SHA256                    PASS · matches bundle manifest
Migration drift                      none
Python compileall                    PASS
pip check                            PASS
TypeScript typecheck                 PASS
Next.js production build             PASS
npm audit --audit-level=low           0 vulnerabilities
Frontend main-route smoke test        PASS
Therapy Atlas production build         PASS · /therapies + /therapies/[slug] + /techniques/[slug]
Therapy Atlas HTTP runtime smoke       PASS · list + CBT detail + ERP detail render seeded content
Therapy Compare + Personal tests        PASS · 8 targeted compare/ownership/validation/query-budget/seed-preservation tests
Therapy Compare query budget            PASS · <=14 queries for bounded 2-item comparison fixture
Research dataset import test             PASS · lossless + source dedupe + conservative promotion + idempotency + seed-preservation
Research raw-file round-trip              PASS · exact byte size + SHA-256 reproduction from DB after source deletion
Research bilingual ingestion audit        PASS · all primary educational sections have complete EN/FA names + key content; normalized Claim/Psychologist/Theory/Timeline indexes complete
Research archive verifier                 PASS · 2 datasets / 1,918 records verified without original JSON files
Research corpus live inventory            PASS · 2 datasets / 1,918 records / 189 sources / 148 concepts / 107 symptoms / 20 therapies / 35 techniques
Research-enriched Knowledge Graph         PASS · 478 nodes / 934 edges / 18 build queries after repeated seed runs
Disorders Explorer hydrated E2E       PASS · 241 catalog / chapter rail / recent Autism persistence
DSM API + route smoke test            PASS
Concept inventory                PASS · 44 concepts / 12 distortions / 8 aliases
Relation provenance              PASS · 12 Beck-backed distortion membership relations
Concept ↔ Symptom layer          PASS · 15 structured links
Flashcard inventory              PASS · 50 active cards
Distortion practice              PASS · 18 items / 72 choices / exactly 1 correct per item
Knowledge Graph                         PASS · 5 node types / 772 edges / provenance / filters / depth-2 neighborhood / shortest-path
Seed/DSM category compatibility       PASS · two seed runs keep 21 DSM-backed categories
Live route smoke                 PASS · API + /cognitive-distortions + /concepts + /map + /study
Authenticated Practice E2E            PASS · submit → StudyActivity → ConceptProgress → StudyOverview
DSM overview HTML payload             ~115 KB after lazy metadata loading
```

The Disorders Explorer browser validation remains part of the regression baseline together with production-build, live HTTP smoke tests for Concept/Graph/Distortion routes, and an authenticated Practice-to-Study-Engine runtime flow.

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
Dashboard
Therapy Compare
Therapy Bookmark
Therapy Note
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

## Roadmap from v0.5.5

Therapy Atlas is being implemented as five bounded v0.5.x parts:

```text
v0.5.1  Therapy Architecture + Backend Foundation ✅
v0.5.2  Scientific Therapy Seed + API ✅
v0.5.3  Therapy Atlas Frontend ✅
v0.5.4  Cross-domain Integration + Knowledge Graph ✅
v0.5.5  Compare + Personal Features + Final Hardening ✅
        Research Dataset Ingestion + provenance-safe enrichment ✅ (same v0.5.5 baseline)
v0.6    Psychologists + Theories + Timeline
v0.7    Advanced Branching Clinical Cases + Analytics
v0.8    Study Mode + Exam Planning + Advanced Recommendations
v0.9    Brain Atlas + Assessments Atlas
v1.0    Admin CMS + Scientific Review + Full cross-domain integration
```

## Deliberately not part of v0.5.5

These remain later-version work rather than partially implemented placeholders:

- Therapy progress/mastery until real learning evidence exists
- Personalized treatment recommendation
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
