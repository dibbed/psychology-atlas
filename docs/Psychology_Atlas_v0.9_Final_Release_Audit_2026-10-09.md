# v0.9 final release audit · 2026-10-09

**Release target: v0.9.0. Audit phase: pre-publication validation.** This records reproducible release-validation databases and current source, not a deployment. Final publication requires production browser/accessibility QA, reviewed hardening and exact merged-main checks. [GitHub Releases](https://github.com/dibbed/psychology-atlas/releases) records the final tag and publication status. v1.0 has not started.

## Authority and changes

Starting local `main`, fetched `origin/main` and GitHub main all resolved to `fdaaf8c44e2d56add89638b2a492211831d92419`. PR [#47](https://github.com/dibbed/psychology-atlas/pull/47) merged v0.9.5 on 2026-10-08. Its exact-main [CI](https://github.com/dibbed/psychology-atlas/actions/runs/37792864033) and [CodeQL](https://github.com/dibbed/psychology-atlas/actions/runs/37792864039) passed. CI included SQLite, PostgreSQL Brain/Assessment/integration, frontend and hygiene. Dependency Review passed on the merged PR; its workflow only runs on pull requests.

The original checkout was clean. Eight existing worktrees were inspected without changing unrelated work: the two older `brain-foundation-review` and `next-advisory` checkouts contained generated `next-env.d.ts` changes. The current release build also generated that file; its incidental change is excluded from this PR.

The existing release convention uses full SemVer and annotated tags, including `v0.8.4`. `v0.9.0` is therefore the final v0.9 target; v0.9.1–v0.9.5 are internal implementation slices, not release tags.

The hardening branch `release/v0.9-final-hardening` corrects stale package/lockfile, README, product-spec and build-manifest metadata. Historical phase records remain explicitly historical. There is no active changelog file to update, so no new changelog is invented. No backend version field exists. No application behavior, dependency version, schema, scientific content or product scope changes in this branch.

Metadata hardening [PR #48](https://github.com/dibbed/psychology-atlas/pull/48) was reviewed and squash-merged to `dc5827fc7c0ea7fc172d959f625b853bcd177e57`; its merged-main [CI](https://github.com/dibbed/psychology-atlas/actions/runs/37844096377) and [CodeQL](https://github.com/dibbed/psychology-atlas/actions/runs/37844096378) passed. The subsequent focused [PR #49](https://github.com/dibbed/psychology-atlas/pull/49) adds production browser QA to CI, aligns manual harness ports, and exposes graph relation-filter selection through `aria-pressed`. This small accessibility fix changes no filters, labels, scientific meaning, API contract, migration or rights statement. Application dependencies and performance budgets are unchanged; Playwright 1.64.0 is isolated runner tooling.

Scoped Codebase Memory queries clarified the shared Brain/Assessment eligibility callers in public APIs, Global Search and Graph. The actual repository root and best-effort file coverage/freshness were checked; current source confirmed implementation-critical results. Independent read-only reviews checked scientific/rights boundaries and migration/security surfaces.

## Frozen-design reconciliation

The full `design-notes-v0.9.md` remains a clearly dated architecture freeze rather than a current completion claim.

| Requirement | Implemented and verified state | Disposition |
| --- | --- | --- |
| Anatomy identity separate from networks | Separate models, reviewed source identities and versioned network definitions | REQUIRED / IMPLEMENTED / source and data VERIFIED |
| One primary sourced hierarchy | 70 child-to-parent links, no selected cycles, 17 public roots; branch eligibility checks ancestry | REQUIRED / IMPLEMENTED / data and regression VERIFIED |
| Public review/provenance gates | Active, reviewed, resolved-source eligibility reused by list/detail/Search/Graph | REQUIRED / IMPLEMENTED / source and regression VERIFIED |
| Claim-level evidence | Hierarchy and scientific assertions retain explicit claim notes and sources; edits require re-review | REQUIRED / IMPLEMENTED / source and regression VERIFIED |
| Controlled publication | Pinned artifacts, complete manifests, atomic conflict-aware publication and receipt verification | REQUIRED / IMPLEMENTED / repeat and regression VERIFIED |
| Brain hierarchy/list/detail frontend | Persian-first routes, filters, sources, attribution and production browser journey | REQUIRED / IMPLEMENTED / VERIFIED |
| Instrument/version/language identities | Four families, five versions, six forms, separately keyed and sourced | REQUIRED / IMPLEMENTED / data and regression VERIFIED |
| Contextual psychometrics | Two separate study samples and findings retain exact form, population, method, precision, locator and limitations | REQUIRED / IMPLEMENTED / data/source VERIFIED |
| Scoped rights/access | Six scoped statements; unknown permissions remain unknown | REQUIRED / IMPLEMENTED / data/source VERIFIED |
| Assessment frontend | Registry/detail routes, exact versions/forms/evidence/rights and production browser journey | REQUIRED / IMPLEMENTED / VERIFIED |
| Search/Graph discovery | Canonical public identities; only sourced anatomical structural edges added | REQUIRED / IMPLEMENTED / real-data API and regression VERIFIED |
| Network/version/study graph nodes | Conditional navigation requirement not established for this corpus | DEFERRED; absence is not a blocker |
| Images/meshes/coordinates, connectivity, imaging/lesion findings | No approved public material or fabricated substitute | DEFERRED |
| Norms/cutoffs and broader contextual evidence | No new public claims fabricated from incomplete evidence | DEFERRED / UNRESOLVED |
| Scoring, user Assessment attempts, diagnosis/treatment behavior, Study-authority changes | Not added | OUT OF SCOPE |
| CMS, review workflow, research/source management and full cross-domain integration | Not implemented in this session | DEFER_TO_V1 |

## Scientific integrity, attribution and rights

Brain identity and all selected hierarchy claims cite pinned FMA 5.1.0 authority, with the CC BY 4.0 attribution/change notices in `docs/research/brain/v0.9.2c/THIRD_PARTY_NOTICES.md` and public Brain attribution. The [pinned FMA license](https://raw.githubusercontent.com/uw-sig/FMA/c6f70808ba2859b88cb0b8362c34fa9017c6f96a/LICENSE) and [CBIG notice](https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.19.2-Yeo2011_Schaefer2018/LICENSE.md) support the recorded scopes. CBIG network labels retain their notice. No Allen/HBAO annotation data, coordinate masks, images, meshes, inferred network memberships, functional localization or unsupported Brain→Concept edge is published by this selection. Source bibliography is not a republication license for its underlying materials.

Assessment families, exact editions and language forms remain separate. PHQ-9 alpha `0.86` (pilot, 46 patients) and `0.873` (main, 185 Persian-speaking patients with type 2 diabetes) retain their separate contexts and original precision. The [original study](https://link.springer.com/article/10.1186/1471-244X-11-61) supports those sample-specific extractions, not universal reliability, validity or translation authorization. Public detail copy preserves the study/sample/method/limitations beside each finding.

The [official DASS FAQ](https://www2.psy.unsw.edu.au/dass/DASSFAQ.htm) supports the recorded owner-stated public-domain questionnaire scopes. They are not extended to manuals or translations. [Pearson's BDI-II page](https://www.pearsonassessments.com/en-us/en-us/Store/Professional-Assessments/Personality-%26-Biopsychosocial/Beck-Depression-Inventory/p/100000159) supports the recorded exact edition and restricted owner-access scope. PHQ/GAD and the Persian PHQ-9 translation permissions remain unknown where documentary evidence is insufficient. A validation paper's article license is not treated as permission to redistribute its questionnaire translation. No new legal grant or jurisdiction-wide legal conclusion is made.

The selected Assessment dossier contains no questionnaire items, scoring keys, manuals, norm tables or cutoff guidance. Recognizable protected-content keys are rejected before staging; canonical publication also requires the exact reviewed hashes. Global Search and Graph reuse public eligibility; text similarity does not generate relations, and graph paths provide no clinical inference. New Assessment nodes have zero incident scientific edges.

## Reconciled release data and publication

A SQLite backup of the real local curated database was migrated and validated in a disposable location outside tracked source. The original database was not migrated or published into. The selected scientific counts match both pinned dossiers and current public data.

| Brain record | Count |
| --- | ---: |
| Public anatomy / primary hierarchy links / roots | 87 / 70 / 17 |
| Network definitions / memberships / functional associations | 7 / 0 / 0 |
| Aliases / external identifiers / dossier sources | 50 / 94 / 25 |
| Approved staging candidates / staging integrity issues | 333 / 0 |

| Assessment record | Count |
| --- | ---: |
| Public instruments / versions / language forms | 4 / 5 / 6 |
| Study contexts / contextual findings / aliases | 2 / 2 / 8 |
| Access statements / cross-domain relations / sources | 6 / 0 / 10 |
| Permissions: unknown / owner-stated public-domain / restricted | 3 / 2 / 1 |
| Availability: unknown / public-access / owner-access | 3 / 2 / 1 |
| Persian forms / Persian study contexts | 1 / 2 |

Brain repeat application returned `ALREADY_PUBLISHED`, `canonical_writes=0`. Assessment application returned `PUBLISHED`, `canonical_writes=65`; repeat returned `ALREADY_PUBLISHED`, `canonical_writes=0`. A subsequent combined repeat compared full logical snapshots of all 143 application/system tables excluding `django_migrations`: **10,709 rows and all timestamps remained identical**. No unintended writes were observed.

The Brain dossier/manifest hashes remain `50b6e33e25b76a77b6ef735503487ac5fab7832d7474e45ad6beb7acdc25a557` / `3f3538fd4f8195b0dbe1c8631d61674cd84c629e7bea1018ba29b91329a3920d`; Assessment pins were independently reconciled against their publisher constants. `verify_research_datasets` passed four archived datasets / 2,294 records.

## Migrations and preservation

There are 37 Atlas migrations, one root and one head: `0037_v094_assessments_atlas`. Brain additions are `0033`–`0036`; Assessment adds nine tables in `0037`. These v0.9 operations are additive model/field/index/constraint changes; no destructive forward data operation was found.

| Executed disposable path | Result |
| --- | --- |
| Zero → latest | PASS; integrity `ok`, zero FK issues |
| Released `0032` → latest → `0032` | PASS; 121 legacy tables / 10,171 rows preserved, allowing only additive Django permission/content-type metadata |
| Pre-Assessment `0036` → latest → `0036` | PASS; 134 legacy tables / 10,654 rows preserved under the same rule |
| Current `0037` schema | All migrations applied; no pending upgrade |
| `check` / `makemigrations --check --dry-run` / `showmigrations atlas` | PASS / no changes detected / through `0037` applied |

Reverse checks establish preservation of the older baseline. Reversing after publication drops the newer tables or approval columns and is **not** a lossless rollback for published v0.9 data; back up before any production downgrade. No production database or deployment was inspected.

## Real-data API and performance

The supplemental read-only smoke passed **122 assertions, zero failures**, covering counts/order, multiple details, reviewed Persian Brain search, pagination, English/acronym/Persian Search, representative filters, invalid/duplicate/overlength inputs, unknown slugs, rejected writes, explicit graph edges, migration head and SQLite integrity/FKs. Negative eligibility and bounded nested payload behavior are covered by the full backend suites. The current full corpus graph has **751 nodes / 1,369 edges**, including 87 Brain and four Assessment nodes plus 70 `brain_part_of` edges.

Five-sample Windows SQLite medians below measure requests and serialization with query capture on the validation copy. Cold graph means application graph-cache miss; database/OS caches were not flushed. They are measurements, not raised acceptance budgets or production latency claims.

| Request | Median ms | SQL queries | Payload bytes |
| --- | ---: | ---: | ---: |
| Brain list | 58.104 | 4 | 52,860 |
| Brain amygdala detail | 84.142 | 8 | 4,973 |
| Brain English / reviewed Persian search | 42.469 / 47.209 | 4 | 3,149 |
| Brain parent filter | 45.034 | 5 | 2,421 |
| Assessment list | 29.945 | 7 | 14,132 |
| Assessment PHQ detail | 67.417 | 13 | 11,946 |
| Assessment English / Persian / acronym search | 47.399 / 46.184 / 54.518 | 7 | 8,141 / 6,928 / 3,725 |
| Assessment combined language/unknown-permission filter | 51.839 | 8 | 3,725 |
| Global Search PHQ-9 | 86.084 | 15 | 3,855 |
| Mixed-domain depression Search | 94.792 | 17 | 19,305 |
| Full graph cold / cached | 490.257 / 14.151 | 52 / 0 | 1,330,845 |

The starting-main Linux PostgreSQL 17 profile independently measured the smaller approved-only corpus (91 nodes / 70 edges): graph 253.193 ms cold / 2.878 ms cached; PHQ-9 Search 124.713 ms; Brain contribution 115.143 ms. Do not compare its smaller payload directly to the full local corpus. The v0.9.3 `MATERIALIZED checked_links` fix remains in current source and its PostgreSQL ancestry-plan regression passes in the exact-main suite. No budget, timeout or dependency range was increased here.

## Executed checks and remaining gates

| Gate | Evidence/status |
| --- | --- |
| Local complete SQLite backend | 570 run / 563 passed / seven expected PostgreSQL-only skips; zero failures; 438.649 s tests / 453.809 s total |
| Starting-main complete SQLite CI | 570 run / 563 passed / seven expected PostgreSQL-only skips; zero failures; 462.367 s |
| Starting-main PostgreSQL Brain | 122 passed / zero skips/failures; 202.486 s tests |
| Starting-main PostgreSQL Assessment/migration | 80 passed / zero skips/failures; 63.713 s tests |
| Starting-main PostgreSQL Search/Graph/legacy knowledge | 41 passed / zero skips/failures; 35.679 s tests |
| Local frontend after version update | `typecheck`, production `build` (29 generation units) and `npm audit --json` PASS; zero vulnerabilities |
| Existing Assessment navigation self-check | PASS; Node's module-type performance warning is non-fatal |
| Django, migration drift, pip and compileall | All PASS; Python 3.12.8 / Django 5.2.17 / DRF 3.18.0 |
| `audit_brain_atlas`, `audit_assessments`, `verify_brain_publication` | All exit 0; zero current integrity findings |
| `verify_research_datasets` | Exit 0; four datasets / 2,294 records |
| `audit_case_graphs`, `audit_recommendation_feedback`, `audit_study_plans`, `audit_v06_release` | All exit 0 |
| SQLite integrity / foreign keys | `ok` / zero issues |
| Source security / hygiene | Read-only v0.9 endpoints; no new tracked database/secret/scientific binary; no unsafe v0.9 HTML rendering; protected external-link handling retained |
| Fresh desktop/mobile/320 px browser regression | PASS in [production CI QA](https://github.com/dibbed/psychology-atlas/actions/runs/37911817154): Brain 43, Atlas 91, resilience 12 assertions |
| Fresh scoped accessibility and release smoke | PASS: 155 additional assertions; zero unexpected console/network/hydration/runtime diagnostics; no WCAG-certification claim |
| Metadata hardening exact-head checks / fresh review | PR #48 PASS at `2b3dedf06fd3c13c13d1eb401940a35885a395ca`; valid threads resolved before protected merge |
| Final browser-hardening exact-head checks / fresh review | Required on the final PR #49 head, including all existing CI/PostgreSQL/frontend/hygiene/CodeQL/Dependency Review gates |
| Clean final-main checks | Required again after PR #49 protected squash merge, including the browser job on main |
| Tag / release / post-release smoke / v1.0 handoff | Publication conditional on all final-main gates; exact SHA and final results are recorded in GitHub Release notes and the post-release handoff |

Source review found no demonstrated scientific, rights, API or migration release blocker. The existing v0.6 archive still reports 59 weak-citation entities / 52 weak-citation relations as visible historical review debt; they are not promoted to new v0.9 independently verified claims.

## Fresh browser evidence and findings

The passing browser job checked candidate head `666a4e359c28463cdbe001d2c0502b000d0a5ca8` through GitHub's PR merge checkout `e29ed829cabe03543ee43de53384ea1d7e825135`. It ran Next's production build/server and the real Django API on Linux, with Chromium `156.0.8078.4`. The disposable database used the established deterministic legacy seed and the pinned reviewed Brain/Assessment selections: **87 anatomy entities, four instruments, 210 graph nodes / 271 edges**. This smaller reproducible browser corpus is distinct from the full local 751-node graph measured above.

The three existing harnesses passed in 12.221 s / 21.070 s / 5.171 s respectively. The adapter's 155 assertions covered 1280×800, 390×844 and 320×844; landmarks/headings, visible keyboard focus and skip navigation, Search's intentional entry focus, labels, visible primary touch targets, named/safe links, keyboard disclosures, header/mobile navigation, RTL/bidi content, long names, no overflow, reduced motion, explicit graph-filter state, actual server loading/outage/retry, an empty migrated database, and final real API/Search/Graph recovery. Eighteen full-page screenshots, three focus screenshots and accessibility snapshots were retained; representative desktop/narrow/mobile views were inspected. These are scoped Chromium release checks, not full WCAG certification, physical-device testing or a multi-browser certification.

All console/page/network diagnostics were retained. Intentional Search/Graph fault injection is explicitly bounded to those API routes. Next prefetch cancellation and HTTP-200 `text/x-component` Flight cancellation for the corresponding committed navigation attempt are classified separately; arbitrary API or asset failures are not exempted. Initial adapter failures were corrected: runner paths must be configured in a step; focus animation must settle; Search autofocus has a different keyboard entry point; a range input inside a closed disclosure has a layout box but is not visible. The latter was reproduced from the failed CI DOM with current CSS, and did not justify a CSS change. Fresh review additionally required per-attempt commit correlation and cleanup that tolerates an already-exited service while retaining diagnostics. The final-head and merged-main browser job must pass independently of this recorded candidate result.

- **SHOULD_FIX_NOW — metadata:** existing maintained version declarations and current roadmap statements were stale at v0.8.4. This branch aligns the candidate version and documents implemented v0.9 while retaining the true published status.
- **RESOLVED RELEASE_BLOCKER — environment/verification:** automatic approval review rejected the normal local frontend start with only `blocked by policy`. The authorized CI route now provides fresh production browser/accessibility evidence. No local runtime restriction was bypassed; older phase browser numbers are not substituted for the current run.
- **SHOULD_FIX_NOW — accessibility:** relation-kind filter buttons relied on selected styling without exposing pressed state. Both kinds of button now expose `aria-pressed`; the browser checks verify exactly one selected filter and an actual source-backed Brain filter change.
- **EXPECTED_LIMITATION:** partial Brain hierarchy, 83 missing Persian anatomy display names, seven missing Persian network display names, zero memberships/functional associations; limited Assessment psychometric evidence and unresolved permissions.
- **DEFER_TO_V1:** Admin CMS + Scientific Review Workflow + Research / Source Management + Full Cross-Domain Integration + final production hardening. Do not implement these while completing this release.

The **Browser release QA** CI job runs `brain_browser_checks.js`, `atlas_browser_checks.js` and `atlas_browser_resilience_checks.js` against the production build and reproducible reviewed corpus. All harnesses use backend port 8015; the frontend uses 3015 with its API URL set at build time. The adapter adds desktop 1280×800, mobile 390×844 and 320 px checks, real backend outages/retry, loading/empty states, diagnostic inspection, screenshots and scoped accessibility evidence. Exact-head review and protected merge must precede clean `HEAD == origin/main == GitHub main` and every merged-main gate. Annotated `v0.9.0` must target that exact SHA, followed by a stable non-draft GitHub Release and post-release API/Graph smoke. The detailed v0.9→v1.0 handoff is created only after the release exists.

## Prepared release-note content (not published)

v0.9 delivers curated Brain anatomy, a sourced primary hierarchy, provenance-preserving rights-compatible publication, public APIs and a Persian-first frontend. Assessments distinguish instrument families, exact versions and language forms, with curated metadata, contextual psychometric findings, scoped rights/access and read-only Persian-first browsing. Global Search discovers both domains; Knowledge Graph adds only explicit sourced anatomy containment and isolated instrument identities.

Quality includes PostgreSQL ancestry and legacy-count hardening, additive migrations, pinned scientific provenance, rights safeguards, complete backend regression and frontend build/dependency checks. Final release notes must add the fresh browser/accessibility results and exact final test counts from the verified release head.

Limits remain explicit: partial hierarchy and incomplete Persian terminology; zero Brain network memberships/functional associations; limited Assessment studies; unknown permissions where evidence is insufficient; no questionnaire content, scoring, diagnosis or treatment behavior. This release does not certify deployment.
