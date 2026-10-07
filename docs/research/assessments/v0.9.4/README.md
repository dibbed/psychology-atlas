# v0.9.4 Assessment metadata selection · 2026-10-07

This release contains original educational summaries and bibliographic metadata for four instrument families, five exact versions, six language forms, two study contexts, two contextual findings, eight aliases and six access records. Ten independently checked sources support the selection. It contains no questionnaire items, manuals, scoring keys, norm tables, cutoff guidance, diagnostic result or scoring implementation.

## Corpus reconciliation

The read-only source database contained 2,251 ResearchRecords. The scoped English term/plural search found 106 records: 38 instrument-name leads also classified as weak, five bibliographic records, 58 incidental mentions, seven rights-sensitive matches and five research gaps. Classifications overlap. No verified edition or extractable psychometric context was established from these corpus matches. Zero old corpus records were promoted into Assessments. [Full classification](corpus_recon.json) retains record identities and searched terms; `scripts/assessment_recon.py` regenerates it from a read-only database connection.

## Independently checked selection

| Family | Selected version | Primary identity evidence | Publication decision |
| --- | --- | --- | --- |
| Patient Health Questionnaire | PHQ-9, 2001 | [PHQ family publication](https://pubmed.ncbi.nlm.nih.gov/10568646/), [PHQ-9 publication](https://pubmed.ncbi.nlm.nih.gov/11556941/) | Exact nine-item form; other PHQ forms remain outside this selection. |
| Generalized Anxiety Disorder scale | GAD-7, 2006 | [Original paper](https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/410326) | Family is an Atlas grouping for the sourced GAD scale. No separate generic GAD edition or family acronym is asserted. |
| Depression Anxiety Stress Scales | DASS-42; DASS-21 short form | [Original paper](https://pubmed.ncbi.nlm.nih.gov/7726811/), [official overview](https://www2.psy.unsw.edu.au/dass/over.htm), [official FAQ](https://www2.psy.unsw.edu.au/dass/DASSFAQ.htm) | Separate full/short identities and explicit derivation. Short-form publication year remains unknown. |
| Beck Depression Inventory | BDI-II, 1996 | [Original family paper](https://pubmed.ncbi.nlm.nih.gov/13688369/), [publisher's exact edition](https://www.pearsonassessments.com/en-us/en-us/Store/Professional-Assessments/Personality-%26-Biopsychosocial/Beck-Depression-Inventory/p/100000159) | Family BDI is separate from BDI-II. Original BDI/BDI-IA editions were not silently assigned or imported. |

Persian family titles are reviewed Atlas display translations. They are not official questionnaire translations and do not imply validation. The original English forms identify the selected versions; their separate redistribution authorization defaults to unknown. The Persian PHQ-9 form is identified only by the translation evaluated in [Khamseh et al. 2011](https://link.springer.com/article/10.1186/1471-244X-11-61).

## Reviewed extraction sheet

| Finding | Exact form | Population/sample | Method and source locator | Reported value | Limitations |
| --- | --- | --- | --- | --- | --- |
| `phq9-fa-2011-pilot-alpha` | PHQ-9; Khamseh 2011 Persian translation | Translation pilot, 46 patients; diagnoses not separately specified | Cronbach's alpha; Methods → Procedures | `0.86` | Pilot context; no independent translation authorization or universal validity claim. |
| `phq9-fa-2011-main-alpha` | Same exact Persian form | 185 Persian-speaking patients with type 2 diabetes, consecutive Tehran clinic sample, February–July 2009 | Cronbach's alpha; Results → internal consistency paragraph | `0.873` | Main clinical sample; no confidence interval extracted, no general-population inference. |

Both findings cite DOI `10.1186/1471-244X-11-61`, PMID `21496289`. Pilot and main estimates are stored separately, with original precision. They are not averaged or presented as instrument-wide scores. SCID is described as the main study's comparator, not as a comparator for Cronbach's alpha. Internal consistency does not establish test–retest reliability, clinical diagnostic accuracy or normative interpretation.

The original GAD-7 paper reports several numerical estimates, but their exact language and subsample contexts need a separate extraction before numeric publication. Other language/population studies and conflicting findings remain scientific debt. No DASS or BDI Persian validation/authorization is asserted by this selection. Zero canonical cross-domain relations are published; the constrained relation architecture and negative tests exist, while exact existing endpoint identity review remains deferred.

## Rights and access register

Rights describe an exact material/form/use; they are not an instrument-wide grant. The six reviewed access records comprise three unknown permissions, two official public-domain statements and one restricted publisher-access record. Access availability is three unknown, two public-access and one owner-access record.

- PHQ-9 and GAD-7: the [current official landing page](https://www.phqscreeners.com/) identifies the instruments. It did not establish the exact commercial redistribution or digital-use terms checked here. Those permissions remain unknown.
- DASS-42 and DASS-21 original English questionnaires: the official FAQ states public-domain use/copying for the questionnaire. The register preserves the exact questionnaire scope and source statement. It does not apply this status to the manual or to translations; jurisdiction-specific legal review was not performed.
- BDI-II: the publisher offers commercial materials with qualification level B. Access is through the publisher; redistribution rights for protected material are not granted by this registry.
- Persian PHQ-9: the article's CC BY 2.0 terms concern the article. They do not establish authorization or redistribution permission for its evaluated questionnaire translation. The translation's rights remain unknown.

This metadata selection does not require or grant commercial reuse of protected test materials. Rights remain unresolved where documentary evidence is insufficient. There is no imported test content even for instruments whose owner permits questionnaire use.

## Controlled publication and provenance

`curated_dossier.json` and `publication_manifest.json` are individually hash-pinned in `atlas.assessment_publication`. The manifest covers every selected row's identity, source check, scientific review, rights review and version resolution. These statuses describe this metadata/extraction curation process; they do not certify universal clinical validity or constitute a new licensing grant. Sources resolve by all DOI/PMID/canonical URL/normalized bibliographic signals. Conflicting or ambiguous signals block the whole transaction. Shared source mutations and Assessment writes reuse the existing curation transaction lock.

Staging retains safe source data losslessly. Recognizable protected-content keys are rejected before storage. Unsupported safe metadata remains staging-only. Dry runs execute validation inside a rolled-back transaction and leave zero net canonical/archive/source writes. Application is atomic, conflict-aware, and never overwrites a curator's conflicting or inactive content. A repeat verifies canonical fields, source links, archive projections, hashes, manifest receipt and staging pointers before returning `ALREADY_PUBLISHED` with zero canonical writes. No repeat updates timestamps. Existing sources are reused only when their exact verified metadata agree.

```sh
python manage.py import_assessment_dataset ../docs/research/assessments/v0.9.4/curated_dossier.json --dry-run
python manage.py publish_curated_assessments                 # dry run
python manage.py publish_curated_assessments --apply
python manage.py publish_curated_assessments --apply         # verified zero-write repeat
python manage.py audit_assessments
```

No assessment publication occurs during `seed_mvp`. The publisher is a separate explicit command. Public and historically linked records use deactivation, not hard deletion. Reviewed content/source/context edits require removal of approval, including dependent checked claims. Bulk writes cannot bypass validated saves. PostgreSQL concurrent publication has one effect; SQLite uses the project's IMMEDIATE transaction setting.

## Public API

`GET /api/assessments/` and `GET /api/assessments/<slug>/` expose active, reviewed, source-backed metadata. Lists use AtlasPagination (30 by default, maximum 300), deterministic name/ID order and exact-match relevance. `q` searches English/Persian titles, Arabic/Persian spelling variants, reviewed family/version aliases and version identities. An ambiguous acronym returns matching families, without selecting the latest edition.

Reviewed filters: `construct`, `intended_use`, `form_kind`, `language`, `access`, `license`. All version filters must be satisfied by the same public version. Combined language/rights filters require the access statement for that exact language form; an English grant cannot establish Persian permission. Unknown values, duplicate parameters and search text longer than 255 characters return 400. No public review-status or staging search exists.

Nested collections have at most 30 results and explicit `truncated` flags. Studies serialize version, exact language/form, population, sample size/context, administration, informant, method, comparator, citation and limitations beside their findings. Inactive/unreviewed ancestors hide dependent content. A derivation reference is shown only when its target version is public; hiding a full form does not automatically hide its independently reviewed short form. Derivation cycle checks read the current stored chain. Recognized inactive Concept/Disorder endpoints hide relations; the existing Symptom table has no active field, so its established identity contract is retained. Expired access statements are hidden. There are no write, item, scoring or diagnosis endpoints.

## Validation and migration

Additive migration `0037_v094_assessments_atlas` follows the live `0036` tip and creates nine separate Assessment tables. It edits no previous migration or Brain/Study/Case/SRS schema. Runnable migration tests exercise released `0032` → `0037`, current-main `0036` → `0037`, reverse paths and a disposable zero → latest database. The real-corpus migration script compares every legacy scientific row and permits only Django's additive post-migrate permission/content-type metadata.

```sh
python manage.py test atlas.tests_v094_assessments atlas.tests_v094_assessment_migrations --noinput
python ../scripts/profile_assessments.py ./data/assessment-profile.json
python ../scripts/verify_assessment_migrations.py ./data/input-copy.sqlite3 ./data/migration-report.json
```

Final local results and actual request measurements are recorded in [validation_report.json](validation_report.json). PostgreSQL plans include the actual provenance, version/form and evidence queries, rather than just the top-level instrument query. CI reruns SQLite publication/audit/profile and PostgreSQL Assessment concurrency/migration tests alongside existing Brain regression. Completion also requires current-head CI/review and merged-main validation.

## Explicit non-goals

Assessment frontend; questionnaire taking; user attempts or score history; self-diagnosis; scoring/interpretation engine; cutoff/norm/sensitivity cards; treatment recommendation; Global Search/Knowledge Graph integration; StudyPlan/Today/SRS integration; v0.9.5 work; v0.9 tag/release.
