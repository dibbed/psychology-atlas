# Psychology Atlas: released v0.9 → v1.0 handoff

Date: **2026-10-09**. Status: **v0.9.0 published; v1.0 not started**.

This document was created after publication on the separate `docs/v0.9-to-v1.0-handoff` branch. It does not move released main or change the release tag. Current source and GitHub state always take precedence over this dated record. No production deployment or production database upgrade occurred during the release session.

## 1. Release identity and evidence

| Item | Verified value |
| --- | --- |
| Repository | [dibbed/psychology-atlas](https://github.com/dibbed/psychology-atlas) |
| Session starting main, including merged v0.9.5 | `fdaaf8c44e2d56add89638b2a492211831d92419` |
| Metadata hardening | [PR #48](https://github.com/dibbed/psychology-atlas/pull/48), merged main `dc5827fc7c0ea7fc172d959f625b853bcd177e57` |
| Browser/accessibility hardening | [PR #49](https://github.com/dibbed/psychology-atlas/pull/49), final head `56b0c396056092fe49a39f61d73bf3d91a1079c3` |
| Final main / release commit | **`e63c9063926bf4e72d5b2fa6a53e21cc5fad5327`** |
| Annotated tag | **`v0.9.0`**, tag object `6182f7a1f2fc53ba67ef801633480a7677bcea29`, peeled target exactly the release commit |
| GitHub Release | [v0.9.0 — Brain Atlas + Assessments Atlas](https://github.com/dibbed/psychology-atlas/releases/tag/v0.9.0), published 2026-10-09 10:09:27 UTC; draft=false, prerelease=false, zero uploaded assets |
| Final-main CI | [37914722860](https://github.com/dibbed/psychology-atlas/actions/runs/37914722860), SUCCESS on the exact release commit |
| Final-main CodeQL | [37914722844](https://github.com/dibbed/psychology-atlas/actions/runs/37914722844), SUCCESS for Python and JavaScript/TypeScript |
| Final-PR Dependency Review | [37913702097](https://github.com/dibbed/psychology-atlas/actions/runs/37913702097), SUCCESS on final head; workflow is PR-only |
| Fresh final-head review | [Review result](https://github.com/dibbed/psychology-atlas/pull/49#issuecomment-6078564824): no major issues at `56b0c39605`; all four valid review threads resolved |
| Post-release smoke | Seven successful API journeys: Brain list/detail, Assessment list/detail, Brain Search, Assessment Search, Graph discovery |

Both hardening PRs used the repository's protected squash strategy. PR #49 was merged with an exact-head guard; no admin bypass or dependency/security exception was used. Main, origin/main and GitHub main matched the release SHA with a clean verification checkout before tagging and after publication. Other existing worktrees and unrelated generated-file changes were preserved.

The maintained frontend package, lockfile root/package entry and build manifest all declare **0.9.0**. The backend has no separate maintained release-version field. Full SemVer annotated tags follow the recent release convention; v0.9.1–v0.9.5 denote implementation slices, not public release tags. No new duplicate version source or changelog was invented. The pre-publication [audit](Psychology_Atlas_v0.9_Final_Release_Audit_2026-10-09.md) remains a dated record; this handoff and the published GitHub Release record final results.

## 2. Architecture and authority boundaries

The backend is Django/DRF, with SQLite development/reproducible validation and PostgreSQL 17 CI regression/concurrency coverage. The frontend is Next.js 16.3.8 / React 19.3 / TypeScript, using the existing Persian/RTL shell, API configuration, header/navigation and domain-specific pages. CI uses Python 3.12 and Node 22; the local release environment used Python 3.12.8, Django 5.2.17 and DRF 3.18.0. These are observed validation environments, not a production inventory.

Existing public domains remain: disorders, concepts, symptoms, therapies, techniques, psychologists, theories, timeline, DSM metadata and educational cases. Personal learning retains JWT authentication and owner-scoped bookmarks/notes, quizzes, flashcards/SRS, case attempts/analytics, distortion practice, Daily Challenge and Study Mode. Brain/Assessment browsing adds public educational metadata; it does not add scoring, user Assessment attempts, diagnostic localization or treatment advice.

StudyPlan owns planning intent and settings. StudyBlock owns scheduled intention and explicit completion. StudySession remains a focus/adherence window. Today is a read-only assembler; Recommendation V2 provides deterministic advice with separate feedback. Existing canonical activity records retain learning-evidence authority. A Session, graph path or newly browsed scientific record must not become a second mastery/scoring engine.

Important source boundaries:

| Boundary | Current implementation |
| --- | --- |
| Shared bibliography and archive | `backend/atlas/models.py`: `SourceReference`, `ResearchDataset`, `ResearchRecord`; archive verification and explicit promotion commands |
| Brain canonical identity | `BrainAnatomicalEntity`, independent `BrainNetwork`, typed aliases, versioned identifiers and source links |
| Brain scientific relationships | `BrainHierarchyLink`; separate `BrainNetworkMembership` and `BrainFunctionalAssociation` with relation-level sources |
| Brain eligibility and API | `brain_publication.py`, `brain_views.py`, `brain_serializers.py`; public reads reuse reviewed identity, provenance and ancestor eligibility |
| Brain import/publication | `brain_staging.py`, `brain_source_resolution.py`, `brain_controlled_publication.py`; pinned reviewed artifacts, receipt verification and conflict checks |
| Assessment identity | `assessment_models.py`: `AssessmentInstrument`, `AssessmentVersion`, `AssessmentLanguageForm` |
| Assessment evidence/rights | `AssessmentValidationStudy`, `AssessmentPsychometricEvidence`, `AssessmentAccess`, `AssessmentAlias`, `AssessmentRelation`, `AssessmentSource` |
| Assessment publication/API | `assessment_publication.py`, `assessment_views.py`; `public_sets()` gates every public nested domain by active/reviewed/source eligibility and consistent exact-form relationships |
| Search and Graph | Explicit builders in `views.py`, reusing Brain/Assessment public sets; `search_utils.py` handles reviewed name/alias queries and Persian spelling variants |
| Cache invalidation | `signals.py`: model save/delete invalidates graph immediately and after transaction commit; graph reads bypass shared caching inside atomic blocks and check revision before publishing cache |
| Frontend | `app/brain`, `app/assessments`, `components/GlobalSearch.tsx`, `KnowledgeMap.tsx`, and existing loaders/API helpers |

Graph caching is revision-tagged with a 300-second payload timeout; cached responses copy node/edge dictionaries. Future curator writes must preserve rollback-safe cache behavior and cover all affected source/alias/relation models. Reviewed-source protection requires returning dependent checked claims to unreviewed before changing their source. QuerySet/model safeguards, publication receipt checks and database constraints must remain effective outside a future UI as well as inside it.

Discovery used scoped Codebase Memory queries to clarify shared public-eligibility callers across APIs/Search/Graph, followed by current-source and runtime verification. Retrieval indexes are aids, not proof of public eligibility or a promise of fresh coverage in the next session.

## 3. Public routes and contracts

| Surface | Public route |
| --- | --- |
| Brain explorer/detail | `/brain`, `/brain/[slug]` |
| Brain API | `GET /api/brain-anatomy/`, `GET /api/brain-anatomy/<slug>/` |
| Assessment explorer/detail | `/assessments`, `/assessments/[slug]` |
| Assessment API | `GET /api/assessments/`, `GET /api/assessments/<slug>/` |
| Global Search | `/search`, `GET /api/search/` |
| Knowledge Graph/path | `/map`, `GET /api/concept-map/`, `GET /api/concept-map/path/` |

List APIs use the existing pagination envelope, deterministic ordering and bounded page sizes/nested records. Brain supports name/alias search, kind/laterality, parent and root browsing. Root and parent filters cannot be combined. Assessment filters retain exact version/form, language, construct and access/license semantics. Navigation self-checks cover duplicate/unsupported filters, pagination, filter preservation and page reset. Do not change these contracts to fit a future admin or integration screen.

Global Search's Brain response key is **`brain_entities`**; its Assessment key is **`assessments`**. Graph node types are **`brain_anatomy`** and **`assessment`**. Instrument graph nodes identify canonical families, not an inferred clinical relationship. Anatomy containment uses **`brain_part_of`** with explicit structural semantics and provenance. Text similarity never creates a scientific edge; traversal never grants clinical meaning. Inactive/unreviewed or invalidly sourced new-domain records stay non-public.

## 4. Data, publication and scientific state

The original curated local SQLite database was preserved. Its pre-Assessment `0036` state was backed up into an untracked validation copy outside the repository, then migrated to `0037` and published through the reviewed commands. Counts below describe that validated release corpus and the matching pinned selections; they do not assert that an operational database has been upgraded. No database or temporary report was uploaded as a release asset.

| Brain selection | Count |
| --- | ---: |
| Public anatomical entities | 87 |
| Primary hierarchy links / public roots | 70 / 17 |
| Separate network definitions | 7 |
| Network memberships / functional associations | **0 / 0** |
| Aliases / external identifiers / dossier sources | 50 / 94 / 25 |
| Approved staging candidates / staging integrity issues | 333 / 0 |
| Reviewed Persian anatomy names / missing names | 4 / 83 |
| Reviewed Persian Brain aliases | 1 |
| Network definitions missing reviewed Persian names | 7 |

| Assessment selection | Count |
| --- | ---: |
| Public instruments / exact versions / language forms | 4 / 5 / 6 |
| Study contexts / findings | 2 / 2 |
| Aliases / sources / access statements | 8 / 10 / 6 |
| Scientific cross-domain relations | **0** |
| Persian forms / Persian study contexts | 1 / 2 |
| Permissions: unknown / owner-stated public-domain / restricted | 3 / 2 / 1 |
| Availability: unknown / public-access / owner-access | 3 / 2 / 1 |

The four families are PHQ, GAD, DASS and BDI. PHQ-9 findings retain separate pilot alpha **0.86, n=46** and main alpha **0.873, n=185**, from Persian-speaking patients with type 2 diabetes. Population, exact form, method, precision and limitations remain beside each finding. These values are not universal reliability/validity or diagnostic claims.

The full curated validation graph contains **751 nodes / 1,369 edges**, including 87 Brain and four Assessment nodes and 70 `brain_part_of` edges. Assessment nodes are honestly isolated. CI browser QA uses the established deterministic legacy seed plus the same new-domain selections: **210 nodes / 271 edges**, still 87 Brain / four Assessment identities. The PostgreSQL approved-only profile is a third, smaller corpus: 91 nodes / 70 edges. Compare timings only within their stated corpus/environment.

Controlled publication is deterministic, atomic, idempotent, conflict-aware and provenance preserving. Brain publication requires dossier SHA-256 `50b6e33e25b76a77b6ef735503487ac5fab7832d7474e45ad6beb7acdc25a557` and manifest SHA-256 `3f3538fd4f8195b0dbe1c8631d61674cd84c629e7bea1018ba29b91329a3920d`. Assessment publication likewise uses its reviewed artifact pins. `seed_mvp` does not authorize or publish these scientific selections.

On final main, both repeat publishers returned **`ALREADY_PUBLISHED`, `canonical_writes=0`**. Full logical snapshots of **143 tables / 10,709 rows**, including timestamps, were identical before/after. Four research archives / **2,294 records** passed checksum verification. All eight established audits passed: `audit_brain_atlas`, `audit_assessments`, `verify_brain_publication`, `verify_research_datasets`, `audit_case_graphs`, `audit_recommendation_feedback`, `audit_study_plans`, `audit_v06_release`.

Publication/research source-of-truth documents:

- [Frozen v0.9 design](design-notes-v0.9.md), explicitly historical design rather than implementation status.
- [Brain curated dossier](research/brain/v0.9.2b/psychology_atlas_brain_curated_dossier_v0.9.2b.json), [approved publication record](research/brain/v0.9.2c/README.md), [third-party notices](research/brain/v0.9.2c/THIRD_PARTY_NOTICES.md).
- [Assessment research/publication record](research/assessments/v0.9.4/README.md), [reviewed dossier](research/assessments/v0.9.4/curated_dossier.json).
- [v0.9.5 integration record](Psychology_Atlas_v0.9.5_Assessment_Search_Graph_2026-10-08.md), [final pre-publication audit](Psychology_Atlas_v0.9_Final_Release_Audit_2026-10-09.md), and final GitHub Release notes.

## 5. Migrations and preservation

There are **37 Atlas migrations**, one root and one head: **`0037_v094_assessments_atlas`**. Brain uses `0033`–`0036`; `0037` adds nine Assessment tables. Forward v0.9 operations are additive models/fields/indexes/constraints; the release audit found no destructive data operation or conflicting head.

| Executed disposable path | Result |
| --- | --- |
| Zero → latest | PASS; integrity `ok`, zero FK issues |
| v0.8.4 `0032` → latest → `0032` | PASS; 121 legacy tables / 10,171 rows preserved, allowing additive Django permission/content-type metadata |
| Pre-Assessment `0036` → latest → `0036` | PASS; 134 legacy tables / 10,654 rows preserved under the same rule |
| Current `0037` → latest | No-op; all migrations applied |
| Final-main `check`, drift and `showmigrations atlas` | PASS, no changes detected, through `0037` applied |

Final validation-copy `PRAGMA integrity_check` returned **`ok`** and `foreign_key_check` returned **zero rows**. Reverse checks establish preservation of the older baseline. Reversing after v0.9 publication drops newer scientific storage/approval columns and is not a lossless rollback; a production migration plan must include a verified backup and restore path. Do not migrate the user's original curated database merely because this handoff names a newer release.

## 6. Fresh final-main quality evidence

The following numbers come from the final-main run, not historical feature PRs:

| Suite | Run / passed / skips / failures | Test duration | Total where reported |
| --- | --- | ---: | ---: |
| Complete backend SQLite | **570 / 563 / 7 / 0** | 465.258 s | Not separately reported |
| PostgreSQL Brain | **122 / 122 / 0 / 0** | 147.462 s | 161.340 s |
| PostgreSQL Assessment | **80 / 80 / 0 / 0** | 56.565 s | 69.165 s |
| PostgreSQL Search/Graph + legacy knowledge | **41 / 41 / 0 / 0** | 28.889 s | 41.525 s |

The seven SQLite skips are established PostgreSQL-only cases, covered in the PostgreSQL job. Brain/Assessment API, scientific eligibility, migration, publication/idempotency, concurrency, Search and Graph regressions are included in those current suites. The PostgreSQL `MATERIALIZED checked_links` ancestry-plan regression remains effective; no budget or timeout was raised.

Frontend `npm run typecheck`, Assessment navigation self-check, `npm run build` (**29 generation units**) and `npm audit` passed, with **zero reported vulnerabilities**. There is no general frontend unit-test framework in the current package scripts; do not invent a Jest/Vitest pass count. The Node self-check emits a non-fatal module-type performance warning, retained as tooling debt; it is not a browser hydration warning. Python `pip check`, CI `compileall`, Django checks, migration drift, repository hygiene and `git diff --check` passed. No new tracked database, secret, machine-specific runtime configuration or protected scientific asset was introduced.

Production browser QA ran on GitHub's Linux runner with Next production build/server, real Django APIs, disposable reviewed/empty SQLite databases, and isolated pinned Playwright **1.64.0**, Chromium **156.0.8078.4**. Normal local frontend start remained rejected by automatic approval review with `blocked by policy`; the explicitly authorized CI route supplied fresh evidence without bypassing that restriction.

| Final-main browser harness | Assertions | Duration |
| --- | ---: | ---: |
| `brain_browser_checks.js` | **43 passed** | 12.123 s |
| `atlas_browser_checks.js` | **91 passed** | 21.489 s |
| `atlas_browser_resilience_checks.js` | **12 passed** | 5.293 s |
| Supplemental scoped accessibility/release smoke | **155 passed** | Included in browser job |

All **301 assertions** passed at **1280×800, 390×844 and 320×844**. Coverage includes multiple valid/invalid details; English/Persian/alias/acronym search; combined filters/pagination/back navigation; explicit sourced hierarchy; contextual evidence and rights display; server loading/outage/retry; migrated empty corpus/no-results; stale-response races; keyboard/focus/skip links; headings/landmarks/labels/disclosures; visible primary touch targets; RTL/bidi and long scientific names; safe/named source links; reduced motion; no horizontal overflow; explicit graph-filter pressed state. Scoped checks are not full WCAG certification, physical-device testing or multi-browser certification.

The final-main report names exactly `e63c9063926bf4e72d5b2fa6a53e21cc5fad5327`, reports **zero unexpected console/network/runtime diagnostics**, and retains **18 full-page screenshots, three focus screenshots and accessibility snapshots**. Representative desktop/mobile/narrow screenshots were inspected. Deliberate Search/Graph fault injection and protocol-verified Next prefetch/committed-Flight cancellation remain separately recorded. Arbitrary API/asset aborts are not exempted. The adapter self-check verified already-exited-service handling, permission-error preservation, matching attempt commits and later-URL-visit isolation. CI artifact `browser-release-qa-e63c9063926bf4e72d5b2fa6a53e21cc5fad5327` has 14-day retention; it is not a permanent scientific archive.

## 7. Performance baselines

Fresh final-main Windows SQLite measurements use the populated validation copy, five samples where applicable and query capture. Graph cold means an application cache miss, not flushed OS/database caches. They are validation observations, not production latency guarantees.

| Request | Median ms | SQL queries | Payload bytes |
| --- | ---: | ---: | ---: |
| Brain list | 43.826 | 4 | 52,860 |
| Brain amygdala detail | 59.944 | 8 | 4,973 |
| Brain English / reviewed Persian search | 38.954 / 44.516 | 4 | 3,149 |
| Brain parent / roots | 37.711 / 37.475 | 5 / 4 | 2,421 / 29,200 |
| Assessment list | 27.786 | 7 | 14,132 |
| Assessment PHQ detail | 67.894 | 13 | 11,946 |
| Assessment English / Persian / acronym search | 42.336 / 40.821 / 49.107 | 7 | 8,141 / 6,928 / 3,725 |
| Assessment combined language/unknown-license filter | 50.852 | 8 | 3,725 |
| Global Search PHQ-9 | 81.005 | 15 | 3,855 |
| Mixed-domain depression Search | 111.913 | 17 | 19,305 |
| Full graph cold build / cached request | 474.350 / 14.403 | 52 / 0 | 1,330,845 |

Brain-only cached graph is 5.524 ms / 193,166 bytes; Assessment-only cached graph is 3.990 ms / 4,354 bytes. Filtered cold graph requests still build the full eligible corpus. Search has independent request queries rather than a shared graph-cache hit. Keep this distinction when evaluating performance work. PostgreSQL CI also profiles its smaller approved-only corpus and emits query plans; preserve those checks before changing eligibility query construction.

## 8. Scientific, rights and technical debt

**Scientific limits:** Primary Brain hierarchy is partial. Eighty-three anatomy and seven network definitions lack reviewed Persian display names. There are no published network memberships, functional associations, unsupported Brain→Concept edges, coordinates, imaging/lesion/3D relationships or diagnostic localization. Names, text similarity and graph proximity cannot supply missing evidence. Assessment psychometrics remain limited to two contextual findings; broader studies, approved terminology, norms and cutoffs require distinct review and scope decisions. Version/form/study nodes are conditional design items, not silently promoted release blockers.

**Rights limits:** FMA 5.1.0 selection retains CC BY 4.0 attribution/change notices; applicable CBIG network metadata retain their MIT notice. Allen/HBAO annotations, images/meshes and unapproved assets are not republished. Source bibliography alone does not license underlying materials. Official DASS owner statements apply only to recorded questionnaire scopes; they do not license manuals or translations. BDI-II stays restricted/owner-access. PHQ/GAD and Persian PHQ-9 form permissions remain unknown where evidence is insufficient. A validation article's license does not authorize questionnaire translation redistribution. No protected items, scoring keys, manuals or unauthorized translations are supplied.

**Historical review debt:** `audit_v06_release` passes with **59 weak-citation entities / 52 weak-citation relations** still explicitly reported. They remain archival debt and are not recast as newly reviewed v0.9 science. No arbitrary new dataset, claim or legal grant was added to close a numerical gap.

**Technical/operational limits:** No Admin CMS or full scientific review UI exists. Commands and model protections supply current controlled publication, not a complete curator workflow. Larger full-graph payloads, filtered cold builds, broader cross-browser/assistive-technology validation, production PostgreSQL migration/restore rehearsal, real deployment/security configuration, monitoring and operational performance remain future work. Do not claim deployment from local/CI success. The module-type warning in the frontend self-check is optional tooling cleanup; avoid broad dependency upgrades solely for release polish.

At handoff creation, there were **zero open GitHub issues and zero open dependency security alerts**. Optional open maintenance PRs were [#44](https://github.com/dibbed/psychology-atlas/pull/44) (frontend dependency group), [#41](https://github.com/dibbed/psychology-atlas/pull/41) (python-dotenv), and [#26](https://github.com/dibbed/psychology-atlas/pull/26) (Actions versions). They were not merged into this release. Reconcile their live state and advisories before starting the next phase.

## 9. Explicit v1.0 boundary and next-session entry

The authorized next roadmap is **Admin CMS + Scientific Review Workflow + Research / Source Management + Full Cross-Domain Integration + final production hardening**. This is a handoff of scope, not authorization to implement it in the v0.9 release session.

Begin a separately authorized v1.0 session by reconciling main/tag/release, worktrees, current migration tip, CI, open maintenance PRs and the curated operational database. Read the frozen design and research/publication/rights records before choosing schemas or UI. Keep the release SHA as an immutable baseline; do not infer current database state from the migration files alone.

1. Design the curator/admin surface around existing canonical models, constrained relationships and explicit permissions. Reuse publication/audit boundaries; do not make raw admin saves a path around scientific review or rights gates.
2. Specify review roles, claim-level review/re-review, evidence locators, source changes, conflict handling, withdrawal and audit history. Preserve atomic writes, idempotency, concurrent safety and rollback/cache invalidation behavior. UI status cannot replace backend/database enforcement.
3. Establish research/source management for versioned bibliographies, archived artifacts, provenance, duplicate resolution and documented rights/translation scope. Separate archival ingestion, curation, review and publication. Unknown permission stays unknown until documentary evidence resolves it.
4. Plan full cross-domain integration with explicit node/edge meanings, source-backed relationships and stable existing public/API identities. Add a relation only with reviewed domain-specific evidence. Do not infer clinical guidance from graph paths or retrofit Assessment families/forms into one identity.
5. Plan final production hardening with a real environment inventory, PostgreSQL upgrade/backup/restore rehearsal, security/deployment configuration, performance/query-plan measurements, monitoring and broader browser/accessibility evidence. Use current CI/browser harnesses as the baseline and keep failures visible; do not raise budgets merely to pass.

Assessment scoring, user Assessment attempts, protected questionnaire/manual content, personalized diagnosis/treatment recommendations, arbitrary new Brain evidence domains/datasets and a new learning-authority engine are not silently included in this roadmap. They require separate explicit scope, scientific and rights decisions.

## 10. Reproducible validation and closure

The current CI workflow is the supported release-browser execution path: install current backend/frontend dependencies, initialize a disposable database, migrate, seed the established legacy corpus, publish both pinned reviewed selections, audit/verify, build Next with the intended API URL, launch normal Django/Next servers on **8015/3015**, wait for readiness, run all three harnesses and scoped checks, retain logs/screenshots, and terminate servers. Playwright stays isolated runner tooling; no second frontend/browser test stack was added to application dependencies.

The reusable profile scripts are `scripts/profile_assessments.py` and `scripts/profile_atlas_integration.py`; Brain publication verification also reports bounded query counts. Existing frontend navigation self-check and backend suites are authoritative for their tested boundaries. Future evidence must record the exact head, corpus, environments, passes/skips/failures and relevant durations. Do not substitute historical slice counts for a new final-main run.

Post-release verification confirmed the tag target, stable release, unchanged GitHub main, all final-main checks green, a clean verification checkout and successful seven-request API/Search/Graph smoke. This handoff is documentation-only on its separate branch; it requires no post-tag product fix or main commit. **v0.9 is released and complete. v1.0 remains unimplemented.**
