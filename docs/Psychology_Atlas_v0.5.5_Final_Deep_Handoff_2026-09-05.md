# Psychology Atlas — v0.5.5 Final Deep Handoff
**Date:** 2026-09-05
**Project:** Psychology Atlas
**Current release:** v0.5.5 — Compare + Personal Features + Final Hardening
**Next planned release:** v0.6 — Psychologists + Theories + Timeline

---

## 1) Project purpose

Psychology Atlas is a Persian-first, bilingual, RTL educational psychology platform for psychology students. It is designed as a connected learning system rather than a set of disconnected articles.

The project is explicitly educational and is not a diagnostic or treatment-recommendation product.

Core scientific guardrails:

1. No personal diagnosis.
2. No fabricated treatment efficacy percentages, rankings, or response probabilities.
3. No personalized treatment recommendations.
4. Do not reproduce DSM-5-TR diagnostic criteria verbatim.
5. Do not fabricate prevalence, diagnosis codes, DOI/PMID, citations, historical dates, or statistical values.
6. Scientific relations require sources or must be explicitly marked educational/proposed.
7. Preserve provenance and source metadata.
8. User-owned/history data must survive seed/content updates.
9. Knowledge Graph edges must come from explicit database relations.
10. Therapy learning mastery/progress must not be inferred without a real learning-evidence model.

---

## 2) Current stack

### Backend
- Django 5.2.17
- Django REST Framework 3.18.0
- SimpleJWT 5.5.1
- SQLite currently
- PostgreSQL-ready via Django ORM/migrations

### Frontend
- Next.js 16.3.3
- React 19
- TypeScript
- App Router
- Persian-first RTL UI

### Authentication
- JWT access/refresh
- Refresh blacklist/logout
- Authenticated user data isolation

---

## 3) Canonical runtime architecture

Do not re-introduce parallel versioned runtime modules.

Canonical backend runtime files:
- `backend/atlas/views.py`
- `backend/atlas/serializers.py`
- `backend/atlas/management/commands/seed_mvp.py`

Canonical frontend shared types:
- `frontend/lib/types.ts`

Historical Django migrations remain and must not be removed.

---

## 4) Roadmap status

- v0.3 — Study Engine + Concepts + Flashcards + SRS ✅
- v0.4 — Full Concept Graph + Cognitive Distortions ✅
- v0.5 — Therapy Atlas series ✅
  - v0.5.1 Therapy Architecture + Backend Foundation ✅
  - v0.5.2 Scientific Therapy Seed + API ✅
  - v0.5.3 Therapy Atlas Frontend ✅
  - v0.5.4 Cross-domain Integration + Knowledge Graph ✅
  - v0.5.5 Compare + Personal Features + Final Hardening ✅
  - v0.5.5 Research Dataset Ingestion + provenance-safe enrichment ✅
- v0.6 — Psychologists + Theories + Timeline ⏭ NEXT
- v0.7 — Advanced Branching Clinical Cases + Analytics
- v0.8 — Study Mode + Exam Planning + Advanced Recommendations
- v0.9 — Brain Atlas + Assessments Atlas
- v1.0 — Admin CMS + Scientific Review + Full cross-domain integration

---

## 5) Therapy Atlas v0.5.5

Therapy and Technique are separate entities.

Main runtime entities:
- TherapyFamily
- TherapyClassification
- Therapy
- TherapyAlias
- TherapyBookmark
- TherapyNote
- TherapyClassificationLink
- Technique
- TechniqueAlias
- TherapyTechnique
- TherapyDisorder
- TherapyConcept
- TechniqueConcept

Source/provenance entities:
- TherapySource
- TechniqueSource
- TherapyTechniqueSource
- TherapyDisorderSource
- TherapyConceptSource
- TechniqueConceptSource

`ScientificReviewStatus`:
- unreviewed
- source_checked
- reviewed

Seeded Therapy/Technique content remains source-backed and does not make ranking or personalized treatment claims.

---

## 6) Therapy Compare and personal features

Implemented:

### Therapy Compare
`GET /api/therapies/compare/?slugs=<2-to-4-slugs>`

Rules:
- 2–4 unique slugs
- input order preserved
- active Therapy/family only
- no efficacy ranking
- no "best treatment"
- no personalized recommendation

### Therapy Bookmark
- authenticated
- idempotent create
- user-scoped
- active-content filtering
- StudyActivity integration without Therapy mastery inference

### Therapy Notes
- authenticated
- private
- user-scoped
- trim on server
- maximum 12,000 characters
- empty save deletes the note
- does not affect scientific content or Graph

Saved/Notes/Dashboard include Therapy data.

---

## 7) Research Dataset Ingestion architecture

The two large research JSON corpora were imported into the database and then removed from the project root only after exact recovery verification.

Two-layer architecture:

### ResearchDataset
Lossless dataset envelope.

Stores:
- source filename
- SHA-256
- dataset metadata
- dataset statistics
- source quality-control payload
- `raw_document`
- exact source `raw_text`
- `ingestion_audit`
- active status

### ResearchRecord
Normalized searchable index.

Stores:
- dataset
- section
- external ID
- canonical key
- slug
- normalized `name_en`
- normalized `name_fa`
- source IDs
- verification status
- review status
- full record payload
- promoted runtime model / PK

This preserves all incoming research even if current v0.5.5 runtime schema cannot represent it.

---

## 8) Research source preservation and recovery

Original research JSON files were deliberately removed after exact round-trip verification.

Archived files:

### `psychology_atlas_research_dataset.json`
- size: 618,107 bytes
- SHA-256:
  `753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0`

### `psychology_atlas_research_dataset_complete___1.json`
- size: 1,281,373 bytes
- SHA-256:
  `3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9`

Recovery:

```bash
python manage.py export_research_datasets <output-dir>
```

Verification without original files:

```bash
python manage.py verify_research_datasets
```

The verifier checks:
- raw text exists
- SHA-256 matches
- parsed raw text equals `raw_document`
- `ResearchRecord` count equals audited section count
- bilingual coverage requirements
- normalized bilingual index coverage

---

## 9) Research ingestion inventory

Current research archive:
- 2 ResearchDataset
- 1,918 ResearchRecord
- 189 canonical SourceReference

Current live runtime inventory:
- 148 Concept
- 20 Cognitive Distortion
- 107 Symptom
- 241 canonical Disorder
- 10 TherapyFamily
- 16 TherapyClassification
- 20 Therapy
- 35 Technique

Future-domain records preserved in staging:
- 130 Psychologist
- 53 Theory
- 63 Timeline Event
- 82 Claim
- 25 Research Gap
- correction/terminology/audit metadata

These future-domain records are intentionally NOT partial v0.6 runtime implementation.

---

## 10) Bilingual policy

Primary educational content is audited for English/Persian coverage.

Normalized staging index coverage is complete for:
- concepts
- cognitive distortions
- symptoms
- disorders
- therapy families
- therapy classifications
- therapies
- techniques
- psychologists
- theories
- timeline events
- claims

Important scientific rule:
Official article titles, DOI/PMID, journal metadata, and source-native bibliographic fields remain in their original form. Do not fabricate Persian translations for bibliographic metadata merely to satisfy a bilingual UI rule.

---

## 11) Source deduplication and provenance

Source canonicalization priority:

1. DOI
2. URL
3. normalized title + publication year

`SourceReference` supports:
- authors
- DOI
- PMID
- organization
- source type
- publication year/date
- journal-related metadata
- verification status
- extra bibliographic metadata

Incoming curated/scientific relations require resolved provenance before runtime promotion.

---

## 12) Conservative promotion rules

Research data is never blindly imported into live runtime.

Rules:
- Existing curated content is not overwritten.
- Importer may create compatible new entities.
- Importer may conservatively fill empty fields.
- Unsupported semantics remain staging-only.
- Lower-quality records remain staging-only.
- Unmapped relation endpoints remain staging-only.
- Psychologist/Theory/Timeline/Claim remain staging-only until v0.6.

Current promotion audit:
- 176 research relationships promoted with resolved source provenance.
- Unsupported/unmapped relationships remain losslessly in staging.

---

## 13) Seed ownership hardening

Critical v0.5.5 fix:

Research relations must not be disabled by `seed_mvp`.

Explicit `seed_managed` ownership exists on:
- TherapyClassificationLink
- TherapyTechnique
- TherapyDisorder
- TherapyConcept
- TechniqueConcept

Rules:
- seeded relations → `seed_managed=True`
- imported research relations → `seed_managed=False`

Repeated `seed_mvp` runs preserve imported research entities and relations.

---

## 14) Knowledge Graph status

Current research-enriched Graph:

- 478 nodes
- 934 edges
- 18 build queries

The graph remained 478/934 after repeated `seed_mvp` runs.

No fabricated similarity score is used.

Structural DSM `dsm_nearby` edges remain excluded from conceptual shortest-path by default unless structural traversal is explicitly requested.

---

## 15) Important migrations

Relevant current migrations:

- `0013_therapy_technique_techniqueconcept_and_more.py`
- `0014_studyactivity_therapy_therapybookmark_therapynote.py`
- `0015_researchdataset_researchrecord_and_more.py`
- `0016_techniqueconcept_seed_managed_and_more.py`
- `0017_researchdataset_ingestion_audit_and_more.py`

Migration `0017` adds exact research-source preservation and bilingual ingestion auditing.

---

## 16) Research management commands

### Import external datasets
```bash
python manage.py import_research_datasets <paths...>
```

Dry run:
```bash
python manage.py import_research_datasets <paths...> --dry-run
```

Store only, no runtime promotion:
```bash
python manage.py import_research_datasets <paths...> --no-promote
```

Verify DB archive:
```bash
python manage.py verify_research_datasets
```

Recover exact original JSON files:
```bash
python manage.py export_research_datasets <output-dir>
```

---

## 17) Final database snapshot

A consistent SQLite backup was created outside the Git repository using SQLite's backup API.

Snapshot location:

`C:\Users\Meliodas\Downloads\psychology_atlas_backups\v0.5.5_final\db_v0.5.5_final.sqlite3`

Snapshot metadata:
- bytes: 49,364,992
- SHA-256:
  `2d80c23b3eaf799dc0242fcc0cafeb0f9b50e8fbf606e867c6654cdaf4341bcb`
- `PRAGMA integrity_check`: `ok`
- SQLite tables: 78

Backup directory also contains:
- `snapshot_manifest.json`
- `db_v0.5.5_final.sha256.txt`

Critical counts in the snapshot:
- ResearchDataset: 2
- ResearchRecord: 1,918
- SourceReference: 189
- Concept: 148
- Symptom: 107
- Disorder: 241
- Therapy: 20
- Technique: 35
- TherapyTechnique: 50
- TherapyDisorder: 28
- TherapyConcept: 43
- TechniqueConcept: 54

---

## 18) Final validation baseline

Final v0.5.5 backend release checks:

- `manage.py check` — PASS
- `makemigrations --check --dry-run` — PASS / no changes detected
- Python `compileall atlas config` — PASS
- `pip check` — PASS
- `verify_research_datasets` — PASS
- Backend tests — **98 / 98 PASS**
- Research raw-file round-trip — PASS
- DB snapshot integrity check — PASS
- Research archive exact SHA recovery — PASS
- Graph — 478 nodes / 934 edges / 18 build queries

Frontend:
- `npm run typecheck` — PASS
- `npm run build` — PASS
- Next.js 16.3.3 production build generated all expected routes
- `npm audit --audit-level=low` — PASS · 0 vulnerabilities
- Final frontend audit was re-run on 2026-09-05 before the freeze commit/tag.

Ruff note:
- Backend venv previously did not have Ruff installed; do not falsely report Ruff as PASS unless it is explicitly installed and run.

---

## 19) Git release history relevant to v0.5.5

Important commits:

- `6926b76` — `feat: release v0.5.4 cross-domain knowledge graph`
- `6b812f1` — `feat: release v0.5.5 therapy compare personal hardening`
- `6cb5018` — `feat: add v0.5.5 research dataset ingestion`
- `5f3e77f` — `chore: harden research archive and remove source jsons`

The obsolete DSM source bundle files were intentionally deleted by the project owner and should be committed as cleanup before tagging the final v0.5.5 baseline.

Recommended final tag:
`v0.5.5-final`

---

## 20) What must NOT be done before v0.6

Do not:
- reintroduce versioned runtime Python modules
- convert staged Psychologist/Theory/Timeline data into ad-hoc partial models
- infer Therapy progress/mastery
- create treatment rankings
- create personalized treatment recommendations
- fabricate graph edges to increase connectivity
- overwrite curated records with lower-confidence research content
- discard `ResearchDataset.raw_text` or `raw_document`
- make seed cleanup touch `seed_managed=False` research relations

---

## 21) v0.6 starting point

Next version:
**v0.6 — Psychologists + Theories + Timeline**

Strong starting advantage:
The research staging layer already contains:
- 130 Psychologist records
- 53 Theory records
- 63 Timeline Event records
- 82 Claims
- source/provenance metadata
- bilingual normalized index values

Recommended v0.6 implementation sequence:

### Part 1 — Architecture and models
Design canonical domain models for:
- Psychologist / Researcher
- Theory / Model
- TimelineEvent
- person aliases
- theory aliases
- person ↔ theory
- person ↔ concept
- person ↔ therapy
- theory ↔ concept
- theory ↔ therapy
- timeline ↔ person/theory/therapy/concept
- explicit source-link/provenance models

Do not simply copy ResearchRecord payloads into production tables.

### Part 2 — Conservative promotion
Build a dedicated promotion/migration path from ResearchRecord staging to v0.6 runtime models.

Must preserve:
- stable IDs
- bilingual text
- source provenance
- attribution semantics:
  - originated
  - developed
  - co_developed
  - expanded
  - popularized
  - researched
  - criticized
  - associated_with

### Part 3 — APIs
Create list/detail/filter endpoints with bounded prefetch/query budgets.

### Part 4 — Frontend
Persian-first:
- Psychologists Atlas
- Theories Atlas
- Timeline
- cross-links to Concept/Therapy/Disorder where scientifically supported

### Part 5 — Graph integration
Add new node types and explicit edges only.
No inferred relation strength or fake confidence numbers.

### Part 6 — final hardening
- provenance audit
- seed preservation
- query budget
- HTTP smoke
- frontend build
- migration drift
- full suite
- updated handoff

---

## 22) Final release readiness criteria

v0.5.5 is ready to freeze when:
- intentional DSM deletions are committed
- working tree is clean
- final handoff is committed
- final tag `v0.5.5-final` points to that commit
- snapshot remains outside repo and its SHA is documented
- no generated frontend noise is accidentally committed

At that point development should move to v0.6 rather than adding more v0.5.x features.
