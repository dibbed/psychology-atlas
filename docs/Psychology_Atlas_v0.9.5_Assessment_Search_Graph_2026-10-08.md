# v0.9.5 Assessment UI, Global Search and Knowledge Graph · 2026-10-08

This records implementation and executed local validation from base main `859d69575060d55bc3750a2dd610926dd43dc897`. PR-head review, PostgreSQL CI, protected merge and merged-main checks are separate completion gates; this document does not certify their future results or deployment.

## User-facing behavior and contracts

- `/assessments`: native GET search and the actual `construct`, `intended_use`, `form_kind`, `language`, `access`, `license`, `page`, `page_size` API capabilities. New selections reset the page; browser back retains the prior query. Blank form controls are omitted from strict API requests. The API has no facet endpoint: construct/language are text inputs with descriptor links on detail pages. Rights indicators are shown on details because the list serializer lacks those records.
- `/assessments/[slug]`: family, version and language form remain separate identities. Study population, sample, method, original metric precision, citation, extraction locator and limitations accompany evidence. `0.86` and `0.873` are separate PHQ-9 sample estimates. BDI resolves to its family, without choosing BDI-II. Sources reuse the existing scientific components; bounded/truncated collections are disclosed.
- Loading, retryable backend/network failure, empty public corpus, no matches, invalid/unknown address and absent optional evidence have distinct presentations. Retry reloads the actual service. Native document navigation handles Assessment request replacement; client search/graph requests use abort guards, including late responses from transports that ignore cancellation.
- `GET /api/search/?q=...` adds `brain_entities` and `assessments`, reusing current public list serialization, reviewed alias gates and Persian normalization. Each new domain is capped at ten canonical rows. Exact name/slug/alias matches sort first, followed by stable name/ID order; ambiguous acronyms retain separate families. Existing response keys/domains remain intact.
- The graph adds only `brain_anatomy` and `assessment` nodes. Reviewed version aliases discover their canonical instrument family. The only added edge is `brain_part_of`: sourced, structural `part_of`, child-to-parent direction, source version and bounded claim provenance. There are no network/version/study/finding nodes or inferred Brain/Assessment cross-domain edges. Existing scientific/archival legacy edges retain their semantics.
- Graph type/domain/kind metadata and validation include the new domains. Isolated instruments remain usable through discovery, selection and canonical navigation. Structural edges are excluded from default paths; explicit `include_structural=1` or `relation=brain_part_of` enables traversal while retaining original edge direction/provenance.
- Cache revision tags reject stale cold builders; atomic reads do not populate shared cache. Signals invalidate immediately and after commit for included entities, public aliases/versions, ancestry and bibliography/claim links. The configured default remains Django LocMem: invalidation is process-local, not a demonstrated distributed multi-worker guarantee.

No schema, seed/publication policy, protected test content, scoring, diagnosis, Study/CMS feature, tag or release is changed. Next.js and its locked platform packages receive the security patch from 16.3.6 to 16.3.8; no dependency is added.

## Observed corpus and scientific limits

Live integration used a disposable read-only SQLite backup of the already published corpus, without seeding or promoting content for local QA:

| Domain | Observed selection |
| --- | --- |
| Brain | 87 anatomies; 70 sourced hierarchy links; 7 networks; 50 aliases; 94 identifiers; zero memberships or functional associations |
| Assessment | 4 families; 5 versions; 6 forms; 2 study contexts; 2 contextual findings; 8 aliases; 6 access records; 10 sources; zero cross-domain relations |
| Complete graph | 751 nodes / 1,369 edges; legacy 660 nodes / 1,299 edges plus 91 public nodes / 70 anatomical edges |
| Rights | 3 unknown, 2 owner-stated public-domain, 1 restricted permission records; availability 3 unknown, 2 public-access, 1 owner-access |

The reviewed Persian PHQ display name is searchable. No reviewed Persian alias exists in the inspected PHQ family/version alias collections; none was invented. The separately identified Persian PHQ form has unknown authorization/redistribution rights. Missing studies for other versions are explicit, not evidence of validity or invalidity. Public access is not a universal licensing grant. Historical weak archival provenance remains visible in legacy domains (`audit_v06_release` reports 59 weak entities / 52 weak relations).

Discovery used scoped current-source inspection after checking the available graph: it indexed an older checkout and differed from current main by 68 files. Empty scoped retrieval did not prove absent callers; rebuilding that unrelated index was disproportionate. Developer code graphs are retrieval aids, not scientific relation evidence.

## Executed local checks

Environment: Windows/PowerShell, Python 3.12.8 with installed project dependencies, Node 22.18.0 / npm 10.9.3, SQLite. Backend commands ran in `backend`, frontend commands in `frontend`; `DEBUG=1`, `DB_ENGINE=sqlite`, and `SQLITE_PATH=./data/v095-qa.sqlite3` selected the disposable integration copy. Earlier worker-focused suites used `SQLITE_PATH=./data/v095-tests.sqlite3` and Django-created disposable test databases. No frontend `npm test` script exists.

| Exact command/check | Result |
| --- | --- |
| `python manage.py test atlas.tests.AtlasApiTests.test_concept_map_query_count_does_not_scale_per_concept atlas.tests_v095_integration --noinput --verbosity 1` | exit 0; 27 run / 27 passed; final focused checks |
| `python manage.py test atlas.tests_v095_integration atlas.tests_v092_brain_api atlas.tests_v092_brain_relations atlas.tests_v092c_brain_publication atlas.tests_v091_brain atlas.tests_v094_assessments --noinput --verbosity 1` | exit 0; 200 run / 194 passed / 6 PostgreSQL-only skips; preceding snapshot |
| Focused legacy search/graph compatibility invocation below | exit 0; 55 run / 55 passed; preceding snapshot |
| `python manage.py test --noinput --durations 15 --timing` | pre-count-fix snapshot: exit 0; 567 run / 561 passed / 6 PostgreSQL-only skips; 412.499 s tests, 431.594 s total |
| `python manage.py check` | exit 0; zero issues |
| `python manage.py makemigrations --check --dry-run` | exit 0; no changes |
| `python manage.py showmigrations` | exit 0; all applied, single Atlas leaf `0037_v094_assessments_atlas` |
| `python manage.py audit_assessments`, `audit_brain_atlas`, `verify_brain_publication`, `verify_research_datasets` | each exit 0; no new integrity issues; four datasets / 2,294 records verified |
| `python manage.py audit_case_graphs`, `audit_recommendation_feedback`, `audit_study_plans`, `audit_v06_release` | each exit 0; legacy review debt disclosed above |
| `npm run typecheck`, `npm run build` | each exit 0 |
| `npm audit --json` | exit 0; zero vulnerabilities at all severities |
| `node --experimental-strip-types app/assessments/assessment.selfcheck.mjs` | exit 0; normalization, duplicate/unsupported filter rejection, local pagination, filter preservation/reset |
| `git diff --check` | exit 0 |

After the count fix, `python manage.py test atlas.tests.V063KnowledgeApiTests atlas.tests_v095_integration --noinput --verbosity 1` ran 41 tests on each engine: SQLite 40 passed / one PostgreSQL-only skip (15.400 s), isolated PostgreSQL 41 passed (35.310 s), both exit 0. These cover all nine legacy search/catalog/detail callers, scoped distinct relation-row counts, inactive exclusions, integer zeros, canonical alias deduplication and the actual configured PostgreSQL JIT cost threshold. Final current-source Django check, migration drift/applied listing and every audit in the table also exited 0 after this edit.

The 567-test snapshot includes the integration regressions and migration tests before the subsequent legacy count optimization; final-head CI reruns the full suite. The 55-test preceding invocation (log redirection omitted) was:

```sh
python manage.py test atlas.tests_v095_integration atlas.tests.TherapyCrossDomainGraphTests atlas.tests.V063KnowledgeApiTests atlas.tests.AtlasApiTests.test_concept_map_returns_concept_and_disorder_edges atlas.tests.AtlasApiTests.test_global_search_hides_orphan_symptoms atlas.tests.AtlasApiTests.test_global_search_matches_disorder_and_concept_slugs atlas.tests.AtlasApiTests.test_concept_map_query_count_does_not_scale_per_concept atlas.tests.AtlasApiTests.test_search_normalizes_common_arabic_and_persian_letter_variants atlas.tests.AtlasApiTests.test_graph_exposes_node_metadata_degree_and_edge_explanation atlas.tests.AtlasApiTests.test_graph_filters_by_domain_and_relation atlas.tests.AtlasApiTests.test_neighborhood_supports_depth_two atlas.tests.AtlasApiTests.test_graph_path_finds_shortest_structured_route atlas.tests.AtlasApiTests.test_neighborhood_node_type_never_returns_disconnected_second_level_node atlas.tests.AtlasApiTests.test_graph_min_degree_is_applied_after_relation_filter atlas.tests.AtlasApiTests.test_graph_path_marks_reverse_traversal atlas.tests.AtlasApiTests.test_graph_path_excludes_dsm_nearby_shortcuts_by_default atlas.tests.AtlasApiTests.test_graph_cache_invalidates_after_model_change --noinput --verbosity 1
```

The PostgreSQL job extends the existing Brain/Assessment API, migration and concurrent publication suites with all `atlas.tests_v095_integration` tests and read-only profiling on the approved selection in a disposable PostgreSQL 17 database. Initial PR head `012177b` passed 122 Brain, 80 Assessment/migration and 26 integration PostgreSQL tests. Diagnostic head `76e4176` passed the first two suites but timed out at the existing 15-minute job limit before finishing integration; it is not a passing head. The following diagnostic head runs profiling first, without increasing that limit. An isolated local PostgreSQL 17.5 cluster on loopback port 55495 was subsequently initialized with approved existing publication commands; all migrations were applied. Its Windows build has no JIT, so its timing cannot establish Linux JIT behavior. Its 91-node/70-edge selection contains the approved Brain/Assessment corpus only. Exact final PR/main runs remain separate gates. Deterministic cache race tests simulate adverse ordering; they do not establish distributed cache behavior.

## Real browser evidence and runnable QA

The existing Playwright MCP harness ran against an actual Next.js production build at port 3015 and curated Django backend at port 8015. `scripts/atlas_browser_checks.js` passed **91 assertions**, using real API identities/responses. `scripts/atlas_browser_resilience_checks.js` separately passed **12 supplemental deterministic fault/race assertions** using real responses with injected transport ordering/failure.

| Journey | Observed evidence |
| --- | --- |
| Assessment | Four real detail slugs, invalid slug, no-match query, page size/next page, search/page reset, short-form and combined language/access filters, reset, browser back, original values/sample/rights and absent optional studies |
| Global Search | Brain English/Persian title and sourced English alias; Assessment English/acronym/Persian title; canonical navigation/back; legacy concept real match and legacy sections |
| Graph | Both new domains, version acronym discovery, isolated Assessment detail/back, Brain selection, canonical legacy selection/reload; every new-domain incident edge checked as sourced anatomical hierarchy |
| Resilience | Separate loading/no-match/error, actual backend stopped/restarted, actual empty public Assessment corpus in a second disposable copy; retry and deliberately late success/error cannot overwrite the newer query |
| Responsive/accessibility smoke | 1280x800, 390x844, 320 px; no horizontal document overflow on list/detail/search/map; long names wrap, native filters/cards/labels remain usable; skip link and native disclosure keyboard/visible focus, reduced motion |

Successful real journeys collected zero runtime/console errors or unexpected failed HTTP responses; expected invalid-address responses and intentional network failures were kept separate. Desktop/mobile screenshots were visually inspected and kept outside tracked evidence. This is keyboard/reflow smoke, not full accessibility compliance.

Those initial journeys used Next 16.3.6. A later smoke restart failed because the QA backend omitted the port-3015 CORS origin; the launch environment was corrected. After repeated command-approval rejections, the simpler verified installed CLI (`node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3015`) succeeded without environment mutation or a hidden launcher. A fresh real-browser run on Next 16.3.8 then passed **57 assertions**: all four details, original metrics/sample context/rights, optional evidence absence, invalid slug, native search/short-form/combined language-access filters/page/reset/back, English/Persian/alias/acronym and legacy search, canonical navigation, isolated and structural graph/legacy/refresh, all three requested widths, actual backend outage on four surfaces, actual empty public corpus, retry recovery, fast query replacement, native disclosure and skip-link focus. Focus was visibly outlined at 3 px. The normal responsive matrix had no unexpected failed requests (complete untruncated network capture) or console errors; intentional outage failures were separate. The reviewed QA corpus was restored. Final merged-main smoke remains a separate gate.

To rerun, start the documented backend/frontend with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8015/api`, navigate to the local frontend, then pass each script's function to Playwright MCP `browser_run_code_unsafe`. For real service-failure QA stop only that disposable backend, inspect index/detail retryable errors, restart it and retry. Empty-corpus QA used a second copy with individually validated deactivation of four instrument families; the reviewed integration copy was preserved. Do not publish/seed or mutate production data for QA.

## Query and performance evidence

`python ../scripts/profile_atlas_integration.py <output.json>` uses Django's real HTTP client, `perf_counter`, `CaptureQueriesContext`, one cache-cold sample and five subsequent samples. No SQL writes are allowed. Cold means only graph cache cleared; database/OS caches remain. Bytes are uncompressed serialized response bytes; timings include eligibility, serialization and response handling. Search has no application cache. Raw profiles/logs stay outside the PR.

`--query-plans` additionally runs PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` for the three slowest captured SELECTs of the first `PHQ-9` request, outside the timed sample. Initial Linux CI search medians were 1,865.906–2,113.390 ms; Windows PostgreSQL plans exposed high legacy count-query estimates, but no JIT. These findings prompted investigation rather than a new benchmark target or relaxed limit.

Linux diagnostic head `1559ff9` confirmed the cause: legacy psychologist/theory count joins estimated costs 728,025.60 / 16,290,453.13 and triggered JIT compilation costing 967.792 / 865.856 ms, against complete executions of 968.078 / 866.150 ms. Brain search cost was 543.03, execution 60.924 ms, without JIT. `PHQ-9` remained 15 queries / 3,847 bytes and measured 2,037.836 ms warm median. That head passed all 122 / 80 / 26 PostgreSQL tests within the unchanged limit; its frontend audit failed on newly reported Next advisories. Local patch validation on exact installed/locked 16.3.8 passed typecheck, build, navigation selfcheck and `npm audit` (zero vulnerabilities). The failed CI head is not merge evidence.

The fix isolates each existing filtered `Count(distinct=True)` in a correlated subquery against the same caller queryset, avoiding independent relation-branch join products without changing relation counts or activity gates. Final Windows PostgreSQL plans cost 1,363.93 / 1,696.12 / 265.60; `PHQ-9` measured 15 queries, 3,851 bytes and 116.383 ms warm median. Its smaller corpus and absent LLVM JIT prevent direct comparison to SQLite or proof of Linux latency; final CI profiles independently validate Linux. No database JIT setting, query budget or test timeout was raised.

| SQLite request / representative query | Cold / warm SQL | Warm median ms | Payload bytes |
| --- | --- | --- | --- |
| Full graph, 751 nodes / 1,369 edges | 52 / 0 | 14.815 | 1,330,845 |
| Brain graph contribution, 87 anatomies | 52 / 0 | 6.072 | 193,166 |
| Assessment graph contribution, 4 instruments | 52 / 0 | 5.586 | 4,354 |
| Global Search `PHQ-9` | 15 / 15 | 85.754 | 3,855 |
| Global Search `پرسش‌نامه` | 15 / 15 | 85.775 | 7,072 |
| Global Search `brain` | 13 / 13 | 90.044 | 16,033 |
| Global Search legacy `corpus` | 13 / 13 | 113.351 | 8,605 |
| Brain list/search contribution `brain` | 4 / 4 | 73.915 | 14,960 |
| Assessment list/search contribution `PHQ-9` | 7 / 7 | 52.194 | 3,725 |
| Path, structural disabled / explicitly enabled | 52 / 0 | 7.899 / 6.526 | 117 / 3,578 |

The final post-count-fix graph cold sample was 665.127 ms including initialization; subsequent cold filtered/path samples were 350.600–469.084 ms. The preceding integration snapshot measured graph 621.005 ms cold / 13.599 ms warm and global `PHQ-9` 82.179 ms, Persian 71.518 ms, `brain` 71.326 ms and legacy `corpus` 68.358 ms. The final SQLite sample is slower while concurrent validation runs; it does not establish a SQLite performance improvement. Query counts and payload bytes are unchanged by the count fix. Before integration the same local corpus measured graph 45 cold / 0 warm queries, 337.6 ms cold / 12.85 ms warm and 1,137,169 bytes; old Global Search `PHQ-9` measured eight queries / 20.62 ms / 145 bytes because it lacked the new domain. These are illustrative same-machine samples, not a production SLA or controlled benchmark: active test/browser work, initialization and corpus matches affect timings.

The legacy synthetic absolute graph budget is retained as measured 13 + 3 fixed reads = 16 (public anatomy, resolved Assessment source IDs, instruments); growth checks still reject per-node queries. The real corpus adds seven fixed graph reads. New search prefetches bounded rows/collections; there is no whole-table per-result retrieval. Eligibility still reads the shared resolved source registry once per Assessment request.

Scoped SQLite `EXPLAIN QUERY PLAN` confirmed materialized `public_tree` / `eligible` / `checked_links`, indexed entity/link/source/alias lookups and bounded output ordering. The existing PostgreSQL ancestry implementation explicitly materializes checked links to avoid repeated provenance regex validation inside a recursive join. Search cost includes current scientific provenance checks and legacy DISTINCT/ORDER BY scans; no ancestry limit or existing budget was silently increased to hide a regression. PostgreSQL job profiling records its own engine, smaller approved corpus, samples, query counts and payloads; do not substitute the SQLite numbers for it.

## Handoff boundaries

Review every final file/diff and exclude generated Next agent instruction files, raw profiles, local databases, browser scratch files and original user edits. Completion requires successful exact-head CI/PostgreSQL/CodeQL/Dependency Review, a fresh configured review with no unresolved valid findings, protected SHA-guarded squash merge, clean synchronized main and required merged-main checks/smokes/audits. No final v0.9 tag or automatic v0.9.6 follows this work.
