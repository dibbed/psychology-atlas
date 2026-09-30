# v0.9.2 — Brain infrastructure, data publication blocked

Date: 2026-09-30. Contract: [frozen v0.9 design](design-notes-v0.9.md).

## VERIFIED_FACTS

- Baseline main: `a26141ad0616dad4e006ff01a9338c5142aadb83`, the verified squash merge of PR #35. Local main, origin/main, and GitHub main agreed before branching.
- PR #35 had no unresolved review threads; merge CI and CodeQL passed. Its final migration was `0033_v091_brain_foundation`.
- The owner explicitly confirmed there is **no approved Brain anatomical corpus or scientific relation dossier**. Existing generic research records cannot supply canonical Brain content automatically.
- The baseline backend suite ran 354 tests successfully, with 2 PostgreSQL-only skips on SQLite. Baseline frontend typecheck and production build passed.
- This slice implements infrastructure. Curated anatomical, hierarchy, network, and scientific relation data publication remains blocked. No tag or release belongs to this slice.

## CHANGED_FILES

- `backend/atlas/brain_publication.py`, `brain_views.py`, `brain_serializers.py`, and `urls.py`: publication gate and bounded read API.
- `backend/atlas/brain_staging.py` and commands `import_brain_dataset`, `promote_brain_staging`: lossless archival and read-only candidate validation.
- `backend/atlas/models.py` and migrations `0034_v092_brain_relation_support`, `0035_v092_brain_alias_review`: two approved relation types with four empty evidence tables, plus source-backed per-alias review gates. The alias migration contains no data promotion.
- Command `audit_brain_atlas`: deterministic integrity and publication-debt audit.
- Five `tests_v092_brain_*` modules: synthetic fixtures only. `tests_v091_migration.py` restores current migration leaves during teardown.
- README and this phase record document the limitation.

## API contract

`GET /api/brain-anatomy/` and `GET /api/brain-anatomy/<slug>/` are read-only. Only active, reviewed anatomy with resolved evidence and a fully publishable primary ancestry is visible. Inactive/unreviewed records and unsupported ancestry return 404 on detail. There is no network API in this slice.

List supports `q`, `kind`, `laterality`, and `parent` (a public parent slug). Unknown, repeated, empty enum, and malformed filters are rejected. English/Persian names, stable slugs, and reviewed aliases are searched; aliases appear only with their resolved spelling citation and claim note. Persian character variants use the existing search helper. Exact matches rank first, then English name and ID. Unsearched lists use English name and ID.

AtlasPagination uses 30 rows by default and caps pages at 300. Aliases, source links, identifiers, children, memberships, and functional associations are capped at 30 per owner, with truncation flags. The primary parent has a single bounded summary. Responses contain citations, claim notes, source versions, review states, and evidence context, with no raw ResearchRecord payload or curator metadata.

Resolved sources require a checked verification state, nonblank title/citation, and a valid URL, DOI, or PMID. Every supplied locator must be valid. Supported existing states are `source_checked`, `verified`, `search_verified`, `web_verified_doi`, and `web_verified_doi_and_pmid`. Weak model-knowledge citations cannot authorize publication. This mechanical gate does not confer scientific approval.

## Staging contract

`python manage.py import_brain_dataset <explicit-path>` accepts only `brain-staging-v1` JSON, with `dataset_metadata.key`, `dataset_metadata.version`, and an explicit `records` array. `--dry-run` rolls archival back. There is no default input file or approved dataset path.

Each record declares a category: anatomy (A), network (B), alias (C), hierarchy (D), external identifier (E), source (F), approved relation (G), or unsupported/incidental (H). Source records must bind to an existing resolved SourceReference and match its citation and locators. Identity needs explicit kind, laterality where applicable, source version, and scope/definition. Aliases need an explicit owner; Persian terms require an explicit review marker. Claim records require source IDs and claim-specific notes. Unsupported fields, predicates, ambiguous identities, missing evidence, invalid endpoints, hierarchy cycles, and laterality conflicts produce issues.

Raw UTF-8 text, parsed document, and SHA-256 are preserved. Exact repeated imports reuse staging without rewriting local review states, records, inactivity, or promotion pointers. Duplicate/malformed record IDs receive deterministic archival keys while retaining the original payload. Generic research datasets are ignored.

`python manage.py promote_brain_staging [--dataset <archived-key>]` is deliberately a **read-only validator**: it always reports `canonical_writes=0` and publication blocked. Even a structurally valid candidate remains staging-only. Neither command creates SourceReferences, canonical entities, aliases, hierarchy, or relation rows.

The alias review migration adds unreviewed-by-default review state, a protected optional source, and claim note to anatomical and network aliases. Checked/reviewed aliases require a resolved source and nonblank spelling note. Changing evidence or identity on a reviewed alias requires returning it to unreviewed. Existing aliases do not become public through the schema change.

Migration 0036 adds individual review state and a mapping claim note to external identifiers. Existing identifiers retain their source and default to unreviewed with an empty note. Public identifiers require reviewed mapping approval, a resolved source, and a nonblank claim note. Changing a reviewed mapping requires returning it to unreviewed; partial saves validate the state that will persist.

Identity, relation evidence-key, and external-identifier conflict checks compare selected candidates with all archived Brain dossiers. External-identifier keys are also compared with canonical mappings. Selecting one dataset limits report candidates; it does not narrow conflict detection. Identical findings are reported once.

## Approved empty relation support

- `BrainNetworkMembership`: anatomy participates in a versioned network definition, with method and qualifier.
- `BrainFunctionalAssociation`: exactly one anatomy OR network subject associates with an active Concept, with method, task, population, exact claim, and limitations.

Evidence keys are stable; checked/reviewed relations require resolved relation-level sources and nonblank claim notes. Active relations require active endpoints. PROTECT deletion and checked-owner source retention preserve evidence; partial saves validate the fields that will actually persist. The database enforces exclusive association subjects and unique evidence identities.

No connectivity, lesion, imaging, symptom, disorder, diagnosis, coordinate, or inferred network data is created. Association does not establish causation, exclusive localization, or diagnosis.

## PRESERVED_INVARIANTS

- v0.9.1 hierarchy cycles, laterality, stable identities, and protected provenance remain intact.
- Anatomy and network identities remain separate; anatomical hierarchy is not network membership.
- Generic research, Study systems, recommendations, mastery, assessments, and frontend source are unchanged.
- Synthetic claims exist only in automated tests, never in seeds or research files.
- The dirty original checkout is preserved; all work uses an isolated branch from current main.

## VERIFICATION_EXECUTED

- New focused tests: 60 passed on SQLite. Query measurements from populated **test-only** fixtures: list 4, detail 11, search 4, parent/kind filters 5. Regression budgets were frozen after measuring. Page size 1 uses the same list query count; nested children and maximum page size are bounded.
- v0.9.1 regression tests: 27 tests, OK, with 2 PostgreSQL-only skips on SQLite.
- Full SQLite backend suite on finalized code: 414 tests, OK, with 2 PostgreSQL-only skips. PostgreSQL focused verification on finalized code: all 87 v0.9.1 + v0.9.2 tests passed without skips, including foundation concurrency and alias/identifier review migration checks; query measurements matched SQLite.
- Disposable copy upgrade from 0032 through 0033, 0034, 0035, and 0036 preserved all 110 pre-existing Atlas table contents, including 2 datasets and 1,918 ResearchRecords. Migration 0035 leaves aliases unreviewed and source-less; migration 0036 leaves existing identifiers unreviewed while retaining their source. Original database was not migrated.
- `check`, `makemigrations --check --dry-run`, `showmigrations atlas`, `verify_research_datasets`, `audit_brain_atlas`, `audit_v06_release`, `audit_study_plans`, `audit_recommendation_feedback`, and `audit_case_graphs` passed against the migrated copy. SQLite integrity_check returned `ok`; foreign_key_check returned no violations. Compilation and `git diff --check` passed.
- Copy counts: anatomy 0, networks 0, hierarchy 0, memberships 0, functional associations 0, aliases 0, external identifiers 0. All Brain review/source distributions are empty; these are zero-content counts, not synthetic test counts.

## FAILED_OR_BLOCKED_CHECKS / UNVERIFIED_AREAS

Curated data publication is blocked by the missing approved scientific/source dossier. No production deployment or scientific review has occurred. GitHub checks, fresh review, merge, and post-merge verification are reported separately from local evidence.

## REMAINING_RISKS / NEXT_PHASE_DEPENDENCIES

Before any public data pass, provide approved anatomical identities, versioned hierarchy/network definitions, resolved source bindings, exact reviewed relation claims and limitations, and verified Persian terminology. Parser validation cannot substitute for that dossier. No external corpus construction or subsequent roadmap phase is authorized by this slice.
