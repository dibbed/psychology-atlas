# Psychology Atlas Product Spec

## Current implemented version: v0.7.3 — Revision-Pinned Multi-dimensional Educational Scoring + Feedback

Psychology Atlas is an interactive educational system for psychology students. It should behave as a connected learning system, not as a psychology blog and not as a diagnostic product.

### v0.7.3 multidimensional educational scoring invariants

- `CaseRevision.rubric_version` declares the scoring-contract generation for that immutable Case revision; `0` means no multidimensional rubric and `1` is the first v0.7.3 rubric contract.
- `CaseScoringDimension` belongs to one `CaseRevision` and uses a revision-scoped stable key, label, description and sort order. Dimensions are educational product metadata, not psychometric constructs or validated competency scales.
- A decision `CaseQuestion` may reference one primary scoring dimension from the same revision. The existing `CaseChoice.score_value` remains the authoritative numeric score; v0.7.3 does not fabricate a new scientific score scale.
- `CaseAttemptEvent.scoring_dimension` and `CaseAttemptAnswer.scoring_dimension` preserve the dimension used at decision time. Event snapshots also copy dimension key/label/description/order so reached-path history remains reconstructible and auditable.
- The API computes `dimension_feedback` from immutable decision events in the exact path the learner actually traversed. Unvisited branches never inflate a denominator or appear as missed performance.
- Old attempts/revisions remain valid with `rubric_version=0`. Missing dimension data is represented explicitly as legacy/unscored rather than backfilled from later content. Rubric v0 revisions cannot assign active scoring dimensions, and feedback aggregation defensively suppresses any anomalous legacy dimension snapshot instead of treating it as a valid multidimensional rubric.
- The stateful runner does not expose scoring dimensions before a decision. After a decision, reached history can show the dimension label; after completion, Persian/RTL cards show score/max, path-scoped percentage, decision count and review feedback.
- Public detail serialization for `structure_mode=branching` returns no revision steps/questions/choices, preventing unreached future branch content from leaking outside the stateful current-step API; linear detail compatibility is preserved.
- `GET /api/cases/<slug>/attempts/current/` rejects duplicate in-progress corruption instead of selecting one arbitrarily, matching the start/resume integrity guard.
- Dimension feedback is deliberately educational and includes an explicit non-diagnostic/non-competency disclaimer. It must never be presented as therapist fitness, clinical competence, diagnosis or treatment guidance.
- Seeded v0.7.3 content maps 18 current Case decision questions onto 17 revision-owned dimension records across the 6 current Case revisions. Re-seeding identical content is idempotent; rubric changes publish a new CaseRevision instead of mutating historical structure.
- Migration `0026_v073_multidimensional_case_scoring.py` is additive and preserves all prior attempts/revisions. The current local runtime has 12 total revisions: 6 historical v1 revisions and 6 current v2 rubric revisions.
- `audit_case_graphs` now validates rubric existence, question→dimension ownership, unused dimensions, attempt event/answer ownership, and event snapshot key/label consistency in addition to the v0.7.1/v0.7.2 graph/state invariants.
- Focused v0.7.3 tests are 10/10 PASS and the full backend suite is 158/158 PASS. Frontend 0.7.3 typecheck/build and npm audit are green; scientific/research archive regressions remain unchanged.
- Runtime HTTP smoke on `case-high-energy-04` completed three real server decisions and produced path-scoped totals of `information_gathering=6/6` and `differential_reasoning=3/3`; the temporary user/attempt was deleted afterward.
- Detailed release validation is recorded in `BUILD_MANIFEST.json` and `docs/Psychology_Atlas_v0.7.3_Multidimensional_Educational_Scoring_2026-09-16.md`.
- The next Clinical Case slice is v0.7.4 Advanced Case Analytics; it should consume these immutable event/dimension primitives rather than invent parallel scoring state.

### v0.7.2 server attempt engine + runner invariants

- `CaseAttempt.current_step` is the only Case node the client may mutate; `state_version` provides stale-state and replay protection.
- `CaseAttemptEvent` stores decision, automatic advance and terminal-completion history with before/after state versions plus server-generated audit snapshots.
- Authenticated APIs support start/resume, current attempt, owned attempt detail and one-step decision/advance submission.
- Frontend never supplies an authoritative next node or score. Backend resolves the valid `CaseTransition`, score and completion state.
- Exact duplicate submissions are idempotent; conflicting replay, future-node skipping, foreign choices, stale versions and completed-attempt mutation are rejected.
- Resume stays pinned to the original `CaseRevision` even after a newer revision becomes current.
- The stateful CaseRunner renders only `current_step` and the immutable reached-path history returned by the attempt API; it does not use the full public case structure to calculate navigation.
- Decision, information and terminal node UX are distinct. Previous history is read-only, refresh resumes server state, and completion uses the same educational-only guardrails as the rest of the product.
- Login from a Case carries a validated internal `next` path and returns the learner to the same Case after authentication.
- Migration `0025_v072_attempt_state_engine.py` is applied and backfills legacy in-progress attempts to the revision entry step when possible.
- The legacy linear `/cases/<slug>/submit/` endpoint remains for compatibility, but the v0.7.2 frontend runner uses only stateful attempt endpoints.
- Scalar Case score remains intentionally unchanged in v0.7.2. Multi-dimensional educational scoring belongs to v0.7.3 and must not be fabricated ahead of content support.
- Focused v0.7.2 backend tests are 11/11 PASS. Final full-suite/frontend/release validation is recorded in `BUILD_MANIFEST.json` and `docs/Psychology_Atlas_v0.7.2_Server_Branching_Release_2026-09-16.md`.
- Production Chromium E2E covered register, start, branch decision, refresh/resume, immutable path history, terminal completion, new-attempt retry and login return-to-case using a temporary branching fixture that was fully deleted afterward.

v0.7.1 started the Advanced Branching Clinical Cases release series by replacing the implicit linear-only case structure with an additive revisioned graph foundation while preserving historical user data.

### v0.7.1 branching-case foundation invariants

- `ClinicalCase.current_revision` identifies the authoritative published structure for new reads/attempts.
- `CaseRevision` snapshots case title, patient summary, educational objective, difficulty and primary disorder in addition to structural graph ownership.
- Every `CaseStep` belongs to exactly one revision and has a stable node key plus explicit `decision`, `information` or `terminal` node kind.
- `CaseTransition` models branch flow explicitly. Choice transitions can continue to another node or complete the case; information-node automatic transitions are supported by schema.
- v0.7.1 deliberately uses DAG semantics. Cycles are rejected by the case graph audit rather than silently permitted.
- `CaseAttempt.revision` is non-null and protected, so historical attempts remain tied to the exact structural revision they used.
- The legacy linear submit service reads questions only from `current_revision`, stores the revision on the attempt, and rejects branching-mode cases until the stateful v0.7.2 engine is implemented.
- `seed_mvp` hashes canonical case content. Re-running unchanged seed content creates no revisions; changed content publishes a new revision and retires the prior published revision instead of mutating historical structure.
- Migrated v0.6.6 cases become revision 1 with explicit transitions. Current seed inventory is 6 active cases / 6 current revisions / 18 active case nodes / 54 explicit transitions.
- `python manage.py audit_case_graphs` is a read-only structural release guard for missing entry points, cross-revision transitions, invalid/inactive choice ownership, unreachable nodes, cycles, missing completion paths, attempt/revision mismatches and historical answer/revision mismatches.
- Active cases without a published current revision and valid entry step are excluded from public Case APIs.
- `CaseAttemptAnswer` validates both choice→question ownership and question→attempt-revision ownership.
- Case list/detail API adds `structure_mode` and `revision_number`; current step payloads expose `stable_key` and `node_kind` while preserving existing linear fields.
- Public Case list/detail query budgets are <=3 / <=4 queries on the current seeded fixture.
- Full backend suite is 136/136 PASS; Django check, migration drift, Python compileall, project-local `pip check`, SQLite integrity and foreign-key audit all pass.
- Frontend package 0.7.1 typecheck and Next.js 16.3.3 production build pass with 23/23 generation units; npm audit reports 0 vulnerabilities; production `/cases` and representative Case detail smoke return HTTP 200 in Chromium.
- v0.7.1 does not yet implement start/resume/current-node decision APIs, server-side in-progress attempt state, multidimensional scoring, advanced runner UX or analytics. Those remain v0.7.2+.

### v0.6.6 final-freeze invariants

- `python manage.py audit_v06_release` is a read-only release guard over active Psychologist/Theory/Timeline entities and all thirteen v0.6 scientific relation families.
- Active v0.6 provenance gaps are zero. Current scientific-review debt is 59 weak-only entities and 52 weak-only relations whose supporting source set is only `citation_from_model_knowledge`.
- Weak-only rows are allowed to remain `source_checked`, because that status means source-backed rather than independently verified; a weak-only row marked `reviewed` fails the release audit. Current weak-only `reviewed` count is zero.
- Timeline precision audit reports zero invalid combinations. Non-exact events still do not gain fabricated exact dates.
- Compact relation cards and Knowledge Map neighbor cards explicitly surface `citation_from_model_knowledge` as “ارجاع آرشیوی؛ نیازمند بازبینی مستقل” when every source for that relation has that verification status.
- Knowledge Map uses canonical scientific review labels instead of exposing raw review-status codes for v0.6 nodes.
- Global Search clears stale Atlas/DSM results immediately when a new query starts and clears stale results on non-abort request failure.
- Therapy/Technique/Psychologist/Theory/Timeline exact-first search no longer performs a redundant `.exists()` round trip. Exact ranking is computed in the same candidate query and exact-only semantics are preserved when exact candidates exist.
- Real current Global Search measurements are 9 queries for `Aaron T. Beck`, 9 for `Beck Cognitive Model`, 8 for `1897`, and 23 for the broad multi-domain query `CBT`. The focused exact-search regression budget is now <=13 queries.
- Knowledge Graph remains frozen at 660 nodes / 1,299 edges / 54 edge kinds / 365 explicit v0.6 edges with 0 v0.6 relation-level source gaps and 45 cold build queries.
- Five repeated cold Graph builds all used exactly 45 queries; the measured median build time was about 253 ms on the local SQLite release environment. A warmed Graph cache required 0 DB queries.
- Public v0.6 list/detail query budgets remain 3/3/2 for complete Psychologist/Theory/Timeline lists and 13/13/9 for representative details.
- Production HTTP regression is 635/635 PASS across every active Disorder/Concept/Therapy/Technique/Psychologist/Theory/Timeline detail page plus core list/search/map routes.
- Chromium headless interaction audit verifies Global Search result interaction, Knowledge Map traversal and weak-source warning visibility on a real weak-only relation.
- Full backend suite is 128/128 PASS on `backend/.venv`; project-local `pip check`, Python compileall, Django check, research archive verifier and promotion dry-run all pass.
- Frontend 0.6.6 TypeScript check and Next.js 16.3.3 production build pass; 23/23 generation units complete and `npm audit --audit-level=low` reports 0 vulnerabilities.
- Production-oriented `check --deploy` with `DEBUG=0` reports only HSTS include-subdomains/preload warnings, which remain intentional deployment opt-ins rather than application defaults.
- v0.6.6 requires no schema migration and does not alter the exact research archive hashes.
- v0.6 is feature-complete/frozen after v0.6.6. The next feature release is v0.7 Advanced Branching Clinical Cases + Analytics.

Detailed v0.6.6 final-freeze record:

```text
docs/Psychology_Atlas_v0.6.6_Final_Hardening_Freeze_2026-09-12.md
```

### v0.6.5 integration invariants

- Global Search returns Psychologist, Theory and TimelineEvent result families in addition to the existing Disorder/Concept/Symptom/Therapy/Technique results.
- Psychologist and Theory search are alias-aware and exact-first; Timeline title/slug/date search is exact-first with bounded partial fallback.
- Inactive v0.6 entities are excluded from Search and Graph.
- Knowledge Graph now contains 660 nodes and 1,299 edges across eight node types: 148 Concept, 241 Disorder, 34 Symptom, 20 Therapy, 35 Technique, 76 Psychologist, 45 Theory and 61 Timeline.
- Exactly 365 active explicit v0.6 scientific relations are Graph-visible. No staging-only or inferred relation is materialized as an edge.
- v0.6 scientific edge kinds preserve relation family plus original semantic code, e.g. `psychologist_theory_developed_or_majorly_associated_with` and `timeline_theory_marks_theory_milestone`.
- All 365 v0.6 Graph edges have relation-level provenance; source gaps are zero.
- Graph edge source metadata preserves stored verification status/DOI/PMID/citation/URL fields. `citation_from_model_knowledge` is not promoted to verified by Graph visibility.
- Timeline Graph nodes preserve `date_precision`; year-only events do not gain fabricated exact dates.
- Graph filters accept Psychologist/Theory/Timeline node types plus Theory domain, Timeline category/event type and scientific review status.
- Concept neighborhood traversal can include Theory and Timeline through explicit relations.
- Path Finder can traverse mixed old/new domains. The verified real-data Aaron T. Beck → Automatic Thoughts → Cognitive Restructuring path is 2 hops.
- `dsm_nearby` remains structural and excluded from default conceptual shortest paths.
- Graph cache invalidation covers v0.6 entities, every v0.6 relation model, every v0.6 relation-source model and shared SourceReference updates.
- Full-data Graph build budget is frozen at <=45 queries; the no-v0.6 Concept scaling fixture remains <=13 queries.
- Representative integrated Global Search is bounded at <=18 queries; Aaron T. Beck search measured 14 on the current database.
- v0.6.5 requires no schema migration.
- Final freeze on 2026-09-12 passed 126/126 backend tests on `backend/.venv`, frontend typecheck, Next.js 16.3.3 production build (23/23 static-generation units), npm audit with 0 vulnerabilities, production HTTP crawl 635/635, Chromium headless Map runtime smoke, SQLite integrity/foreign-key checks, exact research archive verification and final Graph runtime verification at 660 nodes / 1,299 edges / 54 kinds / 45 build queries / 365 explicit v0.6 edges / 0 v0.6 source gaps.

Detailed v0.6.5 integration record:

```text
docs/Psychology_Atlas_v0.6.5_Graph_Search_Integration_2026-09-05.md
```

### v0.6.4 frontend invariants

- Public routes exist for `/psychologists`, `/psychologists/[slug]`, `/theories`, `/theories/[slug]`, `/timeline` and `/timeline/[slug]`.
- Frontend domain types live in the canonical `frontend/lib/types.ts`; no versioned parallel type module exists.
- Shared scientific display semantics live in `frontend/components/ScientificMeta.tsx` so review/source labels are consistent across all three domains.
- `source_checked` is displayed as source-backed but not final scientific review; it is never labeled simply as “reviewed”.
- `citation_from_model_knowledge` source metadata is visibly distinguished from verified/web-verified source records.
- Missing Persian content is never filled with generated translation: Persian is preferred when stored, otherwise the stored English text is displayed explicitly as English, otherwise a neutral missing-data state is shown.
- Psychologists Explorer supports bilingual/alias discovery, review-state and birth-century filtering, sorting and grid/compact layouts over the 76 active canonical identities.
- Psychologist detail exposes explicit Theory/Concept/Therapy/Timeline/Person relations with relation-level provenance and does not infer creator relationships.
- Theory Explorer exposes real runtime `domain` and `modern_status` metadata without turning status into a validity/efficacy score.
- Theory detail exposes proposition/context/application/criticism/limitation fields when present and preserves explicit Person/Concept/Therapy/Technique/Theory/Timeline relation semantics.
- Timeline renders a chronological decade stream, not a flat card catalog, and supports visible server-side relation scopes for Psychologist/Theory/Therapy/Technique/Concept.
- Timeline date rendering mirrors API precision; year-only data is never converted to fabricated `YYYY-01-01` dates.
- Timeline detail exposes raw date model fields, relation roles, relation provenance and chronological previous/next navigation.
- Home and global navigation expose the three new domains. Home uses `Promise.allSettled` for independent overview/domain requests rather than sequential fallback waterfalls.
- v0.6.4 does not add Psychologist/Theory/Timeline to Global Search or Knowledge Graph. The graph remains 478 nodes / 934 edges / 18 build queries until v0.6.5.
- Direct browser automation was attempted, but optional Playwright support is not installed in the local MCP environment; SSR HTTP route/content smoke plus production build are used without modifying project dependencies to work around that tool limitation.

Detailed v0.6.4 frontend record:

```text
docs/Psychology_Atlas_v0.6.4_Frontend_Atlas_Timeline_2026-09-05.md
```

### v0.6.3 API invariants

- Public read-only endpoints exist for Psychologist, Theory and Timeline list/detail surfaces.
- All list endpoints use the existing `AtlasPagination` contract and expose only active runtime rows.
- Psychologist search covers canonical names, aliases, bilingual summaries/roles/nationality and supports theory/concept/therapy/birth-year filters.
- Theory search covers canonical names, aliases, bilingual summary/core/historical text and supports domain/status/psychologist/concept/therapy/technique filters.
- Timeline supports event type, date precision, category, cross-domain entity and year-window filters.
- Invalid choice/year/range filters return HTTP 400 instead of silently falling back.
- Inactive entities return 404 on detail and are excluded from relation payloads.
- Timeline year-only events remain year-only; API serialization never fabricates `YYYY-01-01`.
- Detail payloads expose entity-source roles plus rich `SourceReference` metadata including authors/DOI/PMID/verification status when present.
- Scientific relations expose the sources attached to that exact relation; relation semantics are not collapsed to generic labels.
- Real-database query budgets are 3/3/2 queries for complete Psychologist/Theory/Timeline lists and 13/13/9 for representative detail endpoints.
- Full backend suite is 120/120 passing after the API slice.
- No v0.6.3 migration is required.
- Knowledge Graph remains intentionally unchanged at 478 nodes / 934 edges / 18 build queries.

Public routes:

```text
GET /api/psychologists/
GET /api/psychologists/<slug>/
GET /api/theories/
GET /api/theories/<slug>/
GET /api/timeline/
GET /api/timeline/<slug>/
```

Detailed v0.6.3 API record:

```text
docs/Psychology_Atlas_v0.6.3_Knowledge_APIs_2026-09-05.md
```

### v0.6.2 promotion invariants

- Runtime inventory after promotion: 76 Psychologists, 45 Theories and 61 TimelineEvents.
- Remaining staging-only identities: 37 Psychologist identity groups, 2 Theory identities and 2 TimelineEvents without resolvable source support.
- Promotion requires canonical `SourceReference` provenance. Unsourced entities and relations remain staging-only.
- Identity resolution uses exact normalized identity plus narrowly bounded same-slug/core-name merging for harmless initials/English possessive variants. There is no general fuzzy person/theory merge.
- Alternate Persian/English names are preserved as aliases instead of overwriting the canonical display name.
- Source-checked biography fields are not backfilled from weaker legacy fields merely because another record names the same person. Unknown birth/death years remain unknown.
- All promoted future-domain entities and relations have zero provenance gaps.
- Explicit runtime relation inventory includes 48 PsychologistTheory, 74 PsychologistConcept, 19 PsychologistTherapy, 75 TheoryConcept, 3 TheoryTherapy, 3 TheoryTheory, 55 TimelinePsychologist, 27 TimelineTheory, 25 TimelineTherapy, 1 TimelineTechnique and 35 TimelineConcept rows.
- Timeline semantics preserve `involves_person`, `marks_theory_milestone`, `marks_therapy_milestone` and `marks_technique_evidence_milestone` instead of collapsing them into a generic relation.
- After supported promotion, fully resolved + source-backed future-domain staging relations left without a canonical model: 0.
- `TheoryTechnique` remains empty because its current staging target Technique is not itself source-backed/runtime-mapped; it is not force-created.
- Promotion is idempotent and has a transaction-backed `--dry-run` mode.
- `seed_mvp` does not own or deactivate promoted v0.6 records/relations.
- Existing Knowledge Graph remains 478 nodes / 934 edges / 18 build queries because v0.6.2 does not make these entities graph-visible yet.

Promotion commands:

```text
python manage.py promote_research_staging
python manage.py promote_research_staging --dry-run
```

Detailed v0.6.2 promotion record:

```text
docs/Psychology_Atlas_v0.6.2_Research_Promotion_2026-09-05.md
```

### v0.6.1 architecture invariants

- v0.6.1 established `Psychologist`, `Theory`, and `TimelineEvent` as canonical runtime models; their initial empty-table boundary was intentionally ended by the explicit v0.6.2 promotion pipeline above.
- Person and Theory aliases are separate rows; canonical names are not overloaded with initials/transliterations/historical spellings.
- Person attribution uses explicit semantics such as `proposed`, `co_proposed`, `developed`, `co_developed`, `expanded`, `researched`, and `contributed_to` instead of a generic `creator` claim.
- Theory relations support the actual staged vocabulary, including `grounds`, `complements`, `reformulated_as`, `challenged_by`, and `supports_interpretation_of`.
- `TheoryTechnique` exists because the real staging corpus contains a theory-to-technique `grounds` relation.
- Every new entity/relation provenance model reuses `SourceReference`; no second bibliography registry exists.
- Timeline dates preserve granularity as exact date, year, year range, approximate year, or unknown. Year-only data must not be converted into fabricated January 1 dates.
- `seed_managed=False` is the default for new entities and scientific relations so future research promotion remains independent from `seed_mvp` ownership.
- New models are not graph-visible in this slice, so existing graph behavior/query budget/cache semantics remain unchanged.
- v0.6.1 did not auto-promote new domains merely because models existed. v0.6.2 now invokes the explicit source-backed promoter only through the research-import promotion flow or `promote_research_staging` command.

Detailed design record:

```text
docs/Psychology_Atlas_v0.6.1_Architecture_Foundation_2026-09-05.md
```

## Architecture decisions

- User accounts: **YES**
- Frontend: **Next.js + React + TypeScript**
- Backend: **Django + Django REST Framework**
- Auth: **JWT** with frontend access-token refresh
- Current database: **SQLite**
- Future database: **PostgreSQL** without business-logic rewrite
- Django ORM/migrations are the persistence source of truth
- Content administration: deterministic seed data plus provenance-aware external research ingestion; dedicated content-admin UI later
- External research is stored losslessly in `ResearchDataset` + `ResearchRecord` before any selective runtime promotion
- Research promotion is non-destructive: existing curated fields are not overwritten and imported content uses independent seed ownership
- User-owned data must remain isolated by authenticated user
- Server controls quiz/case scoring and SRS scheduling
- Do not couple frontend logic to SQLite

### Research dataset ingestion

v0.5.5 stores the two research corpora fully inside the database. The original JSON files were removed from the project root only after exact SHA-256/byte-size round-trip verification from DB storage. New external research files can still be imported explicitly by path.

Current research-ingestion invariants:

- 2 imported `ResearchDataset` rows and 1,918 indexed `ResearchRecord` rows are retained losslessly.
- `ResearchDataset.raw_text` preserves the exact UTF-8 source text; `source_sha256` validates exact reconstruction and `raw_document` preserves the parsed JSON form.
- `ResearchDataset.ingestion_audit` stores section counts and bilingual coverage for primary educational sections.
- `SourceReference` stores authors, DOI, PMID, verification status and extra bibliographic metadata; source dedupe priority is DOI → URL → title/year.
- Complete/source-checked records may promote into the current Concept, Symptom, Therapy, Technique and explicit relation models when the v0.5.5 schema can represent the semantics faithfully.
- Lower-confidence or unsupported records remain staging-only instead of being forced into a misleading runtime model.
- Psychologist, Theory and Timeline Event staging now have dedicated v0.6 runtime domains and promote only when identity/provenance requirements are satisfied. Unsourced records remain staging-only. Claim and ResearchGap records remain staging/review material.
- Primary educational sections are audited for bilingual English/Persian names and key content. Official bibliographic titles, DOI/PMID and source-native metadata are preserved in their original form rather than receiving fabricated translations.
- Imported runtime entities use `seed_managed=False`; Therapy classification/Technique/Disorder/Concept relation rows also have explicit seed ownership so repeated `seed_mvp` cannot deactivate externally imported relations.
- Imported scientific relation promotion requires resolved source provenance.
- Current enriched live inventory is 148 Concepts, 107 Symptoms, 241 canonical Disorders, 20 Therapies, 35 Techniques and 189 canonical sources.
- Current integrated Knowledge Graph is 660 nodes / 1,299 edges / 54 edge kinds with a 45-query full-data build budget; 365 edges come from explicit v0.6 Psychologist/Theory/Timeline relations.

Operational commands:

```text
python manage.py import_research_datasets <paths...>
python manage.py import_research_datasets <paths...> --dry-run
python manage.py import_research_datasets <paths...> --no-promote
python manage.py verify_research_datasets
python manage.py export_research_datasets <output-dir>
```

The archived source files can be reconstructed exactly from the database with these verified hashes:

```text
psychology_atlas_research_dataset.json
SHA-256 753a7d3edf2239becdf2bb27073e8e56fcd24399a5a901bea98da89fbb660bc0

psychology_atlas_research_dataset_complete___1.json
SHA-256 3bfa4fe8b465ff0b6b5b1aaf511372efb136c42ccb0db58a5468645aaf6b27e9
```

### Therapy architecture foundation

Current Therapy backend entities:

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
```

Scientific/schema rules:

- Therapy is a coherent therapeutic approach/model; Technique is a reusable intervention procedure. They are not stored as the same entity.
- Primary orientation is represented by one `TherapyFamily`. Overlapping labels such as focus/method/delivery/population are separate `TherapyClassification` links and may be multiple.
- `TherapyDisorder` stores `clinical_role` separately from `evidence_basis`; neither field is a personalized recommendation.
- `Therapy`, `Technique` and cross-domain relationship provenance reuses the shared `SourceReference` registry through explicit source-link models.
- `review_status` is lightweight metadata only. Full moderation/scientific-review workflow remains deferred.
- Seeded Therapy content uses source-backed educational summaries only. It does not seed treatment rankings, personalized recommendations or fabricated effectiveness percentages.
- Seeded content is marked `source_checked`, not scientifically `reviewed`; full review workflow remains deferred.
- Runtime code uses canonical unversioned modules (`views.py`, `serializers.py`, `seed_mvp.py`). Historical migration files remain because they are required for safe database upgrades.

## Implemented learning domains


### Therapy Atlas

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
GET /api/therapies/compare/?slugs=<2-to-4-slugs>
GET /api/therapies/<slug>/
GET/POST /api/therapy-bookmarks/
DELETE /api/therapy-bookmarks/<slug>/
GET /api/therapy-notes/
GET/PUT/DELETE /api/therapy-notes/<slug>/
GET /api/techniques/
GET /api/techniques/<slug>/
```

The seed uses NICE clinical guidelines, NIMH, Beck Institute and the VA National Center for PTSD. `TherapyDisorder.clinical_role` and `evidence_basis` remain separate fields, and relation-level source links are returned in detail API responses.

Frontend routes:

```text
/therapies
/therapies/[slug]
/techniques/[slug]
```

The Therapy Explorer supports Persian/English search, family and classification filters, connection/name sorting, and card/compact views. Therapy detail separates overview, techniques, clinical contexts, concepts, evidence/limitations and sources. Technique remains an independent detail surface and links back to therapies and concepts. The UI explicitly states that Evidence Basis is evidence-source semantics, not a personalized treatment ranking.

Compare/personal completion in v0.5.5:

- Therapy Compare accepts exactly 2–4 unique active therapies, preserves requested order and returns full structured detail plus an explicit no-ranking/no-recommendation note.
- Therapy Compare UI covers family/classification, principles, structure, techniques, clinical-role/evidence-basis relations, concepts, limitations, safety and entity/relation provenance.
- `TherapyBookmark` and `TherapyNote` are private per authenticated user. Bookmark creation is idempotent; notes are trimmed, bounded to 12,000 characters and empty-save deletes the note.
- Saved, Notes and Dashboard aggregate active Therapy personal data alongside Disorder and Concept data.
- Therapy bookmark/note actions may create `StudyActivity` rows linked to Therapy, but there is no Therapy progress percentage or mastery state.
- Compare frontend requests are abort-safe in both Disorder and Therapy modes; stale requests cannot overwrite current selection state.
- Therapy Detail/Compare prefetch plan is bounded and regression-tested at <=14 DB queries for the two-item compare fixture.

Cross-domain integration from v0.5.4:

- Disorder detail exposes source-backed `TherapyDisorder` relations without replacing the legacy educational `treatment_overview`.
- Concept detail exposes `TherapyConcept` and `TechniqueConcept` relations with relation-level sources.
- Global Search includes Therapy and Technique with exact alias priority.
- Therapy and Technique are independent Knowledge Graph node types and retain direct profile links.
- Graph treatment edges carry relation-level provenance when present.
- No graph edge or search result is interpreted as a personalized treatment recommendation.

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
Therapy ↔ Disorder
Therapy ↔ Concept
Therapy ↔ Technique
Technique ↔ Concept
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
6 Therapy nodes
9 Technique nodes
330 total nodes
772 total edges

23 Concept ↔ Concept edges
65 Disorder ↔ Concept edges
15 Concept ↔ Symptom edges
65 Disorder → Symptom edges
9 Therapy ↔ Disorder edges
7 Therapy ↔ Concept edges
10 Therapy ↔ Technique edges
8 Technique ↔ Concept edges
570 DSM nearby-title Disorder ↔ Disorder edges
```

The graph must use explicit structured relationships. Do not invent similarity percentages.

Current Graph UX includes five node types, Concept domain/subtype/minimum-degree filtering, Therapy family filtering, depth-1/depth-2 Concept neighborhoods and server-side shortest-path finding between Atlas nodes. Node-type filters are applied before neighborhood traversal, minimum degree is evaluated on the final filtered graph, traversal direction is preserved in path results, and `dsm_nearby` structural shortcuts are excluded from the default conceptual shortest path. Path results are still computed only from stored edges.

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
- Therapy bookmarks
- Disorder notes
- Concept notes
- Therapy notes
- Disorder progress
- Concept progress
- Flashcard SRS progress
- Quiz attempts
- Case attempts
- Daily Challenge attempts
- Cognitive Distortion Practice attempts
- Study activity

Seed updates must not intentionally delete these records.

## Still outside v0.5.5

These are intentionally deferred rather than partially implemented placeholders:

- Therapy learning-progress/mastery until real learning evidence exists
- personalized treatment recommendation
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

The Concept Graph and Cognitive Distortions learning layer remain the connected-learning baseline. v0.5.5 completes Therapy Atlas with structured comparison and private study utilities on top of the v0.5.4 cross-domain graph, while keeping all scientific edges explicit and refusing to infer personalized treatment rankings or Therapy mastery.

## Version roadmap

```text
v0.5.1  Therapy Architecture + Backend Foundation ✅
v0.5.2  Scientific Therapy Seed + API ✅
v0.5.3  Therapy Atlas Frontend ✅
v0.5.4  Cross-domain Integration + Knowledge Graph ✅
v0.5.5  Compare + Personal Features + Final Hardening ✅
        Research Dataset Ingestion + provenance-safe enrichment ✅ (same v0.5.5 baseline)
v0.6    Psychologists + Theories + Timeline
v0.7  Advanced Branching Clinical Cases + Analytics
v0.8  Study Mode + Exam Planning + Advanced Recommendations
v0.9  Brain Atlas + Assessments Atlas
v1.0  Admin CMS + Scientific Review + Full cross-domain integration
```

The current product version is v0.5.5 Compare + Personal Features + Final Hardening.
