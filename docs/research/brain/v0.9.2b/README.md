# v0.9.2B — reviewed Brain scientific dossier

Reviewed on **2026-10-01**, against main `89be24d61515ac603113fca4b83b84ccc9e2504e` (merged v0.9.2 infrastructure, PR #36).

**NO CANONICAL BRAIN PUBLICATION.** This phase prepares candidates for separate scientific publication review. It does not implement a publisher, change the parser, populate public content, add a frontend, or start v0.9.3.

**Dossier NOT READY for the intended potentially commercial publication.** The user confirmed commercial use is possible or undecided. HBAO's declared CC BY 4.0 and the upstream Allen research/noncommercial terms have not been reconciled for StructureGraph 10. All 75 anatomy identities and their dependent aliases/identifiers are deferred; 74 scientifically verified hierarchy claims are preserved only in metadata, not serialized as approved staging hierarchy. This is a rights compatibility question, not a finding that the scientific identities or either license declaration are false.

## Intake and artifacts

The original Web file is preserved byte-for-byte here, including its CRLF line endings. It is input evidence, not authority. The adjacent `.gitattributes` prevents line-ending conversion from changing either dossier's SHA-256.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `psychology_atlas_brain_curated_web_dossier_v0.9.2b.json` | 396,308 | `a0baf10cbd21a26651ba1df68b3bc3d4553455e1eb8f6ea69e791c503d7dd321` |
| `psychology_atlas_brain_curated_dossier_v0.9.2b.json` | 1,053,780 | `738b3ce478b0dd9f9213f5d8b8aba002701972fc2ab39eaa9263a81ca5893213` |

Both are valid UTF-8 JSON using current `brain-staging-v1`. The input dataset key/version are `psychology-atlas-brain-curated-web-dossier-v092b` / `0.9.2b-web-candidate-2026-10-01`; the master uses `psychology-atlas-brain-curated-dossier-v092b` / `0.9.2b-curated-2026-10-01`.

| Category | Web input | Independently added | Removed from staging candidates | Reviewed master |
|---|---:|---:|---:|---:|
| Sources | 14 | 11 | 1 | 24 |
| Anatomy | 53 | 22 | 0 | 75 |
| Hierarchy | 52 | 0 | 52 | 0 |
| Aliases | 53 | 30 | 0 | 83 |
| External identifiers | 105 | 104 | 52 | 157 |
| Networks | 7 | 0 | 0 | 7 |
| Network memberships | 0 | 0 | 0 | 0 |
| Functional associations | 0 | 0 | 0 | 0 |
| **Total** | **284** | **167** | **105** | **346** |

An additional **22 independently added hierarchy claims** are preserved as deferred metadata, making **189 independently added research records** across staging and deferred hierarchy. Five new functional evidence candidates and two newer authority/version leads are also preserved in metadata. The 179 retained staging input records were amended/reannotated, plus 52 original hierarchy claims were independently checked and reannotated in metadata: **231 amended research records overall**. This is not a claim that 231 anatomical facts were wrong. Four shortened callosal labels, six unsupported midline assignments, two network names, a Persian article's publication year, source versions/locators, and Persian review assertions received substantive corrections. Record and field lists distinguish these dispositions.

Whole-record rejections: **0**. Of the 105 removed input records, **52** are useful Uberon subclass crosswalks classified **DEFERRED**, **52** are independently verified original hierarchy claims deferred for rights, and **1** is an aggregator source classified **UNRESOLVED** (source resolution: **AMBIGUOUS**). All remain traceable in the master and the original input. **56 unsupported Persian approval assertions were withdrawn**, and all 60 generated Persian descriptions were removed.

## Scientific decisions and independent evidence

The selected 75 identities, native identifiers, acronyms, and 74 immediate parent assertions were checked against [HBAO release 2025-02-10 at immutable commit 3ff2721](https://raw.githubusercontent.com/brain-bican/human_brain_atlas_ontology/3ff272135c917b0437edc4cab7d23bd25f05244b/hbao-base.json) and independently cross-checked against [Allen StructureGraph 10](https://api.brain-map.org/api/v2/structure_graph_download/10.json). The master records the fetched byte hashes and a selected label/acronym/parent snapshot. Each deferred hierarchy claim identifies its exact subject, object, BFO `part_of` predicate, release and Allen parent ID. These anatomy entries use `source_checked`, not publication-reviewed status; hierarchy publication approval count is **0**.

This is an explicitly **source-specific annotation hierarchy**. Its gray/white branches do not imply exhaustive tissue composition of the named regions. HBAO, Allen 3D 2020, and Ding's histological atlas are not treated as spatially interchangeable. All 73 nonsided identities retain `not_established` laterality; the two additional subthalamic nuclei have explicit source-side labels. No mirrored anatomy, masks, coordinates, universal developmental hierarchy, or new invented brainstem parent is supplied.

The 22 new entities cover missing frontal/temporal gyri, parahippocampal gyrus, midbrain/myelencephalon and selected nuclei, epithalamus/pineal gland, cerebellar cortex, CA2/CA3 and source-explicit left/right subthalamic nuclei. Native Allen IDs were added for all 75 anatomy entries. HBAO's `is_a` Uberon mappings are preserved as deferred subclass evidence rather than unqualified equivalent identifiers. Ventricular parentage, finer parcels and competing hierarchies remain deferred.

Seven network definition candidates are retained because their identities have direct versioned evidence: [Yeo et al. 2011](https://doi.org/10.1152/jn.00338.2011) plus the author-maintained [ordered names CSV in CBIG v0.19.2-Yeo2011_Schaefer2018](https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.19.2-Yeo2011_Schaefer2018/stable_projects/brain_parcellation/Yeo2011_fcMRI_clustering/1000subjects_reference/7NetworksOrderedNames.csv). Each definition states the cortical surface/group scope, resting-state method and limitations. Label 4 is **Salience / Ventral Attention**, label 6 **Control**; inherited technical slugs are traceable and do not establish equivalent network taxonomies. There is no HBAO-to-Yeo parcel crosswalk, so **memberships remain zero**.

**Functional staging associations remain zero.** Five new evidence candidates in metadata resolve exact existing Concept slugs `fear-conditioning` and `cognitive-reappraisal`; they include method, task, population, source version, evidence key and limitations. [Bo et al. 2024](https://doi.org/10.1038/s41593-024-01605-7) challenges a general amygdala suppression account of reappraisal; [Radua et al. 2025](https://doi.org/10.1038/s41467-025-63078-x) changes the interpretation of older conditioning findings. Historical positive results and later null/competing findings are preserved together, not converted into causal edges. Finer insula mappings, lesion networks, coordinates, disorder/symptom relations and visual assets remain research leads outside staging relation fields.

The [Ding 2016 article](https://doi.org/10.1002/cne.24080) and its [2017 correction](https://doi.org/10.1002/cne.24130) have the same title but different DOI/PMID/year. They are separately verified sources, never merged by title alone. All retained paper DOI/PMID metadata was checked using PubMed/Europe PMC and Crossref, with publisher/institutional documents for datasets and Persian sources. The source catalog records authors, organization/publisher, citation, year (or explicitly missing date), resource version, evidence role and verification URLs.

## Persian terminology

Four anatomy names have independently observed academic/professional usage: `ناحیه CA1`, `عقده‌های قاعده‌ای`, `جسم پینه‌ای`, and `آمیگدال`; one additional corpus-callosum transliteration is sourced. Evidence comes from the [Tabriz CA1 article](https://mj.tbzmed.ac.ir/fa/Article/mj-31006), [Tabriz clinical article](https://mj.tbzmed.ac.ir/fa/Article/7630), [official ISUOG Persian leaflet](https://www.isuog.org/asset/F525BC70-4CF1-4D29-8ED64BD325142F71/) and [Tayebi et al. 2024](https://mj.tbzmed.ac.ir/PDF/mj-46-545.pdf). A rat study supplies terminology usage, not human anatomical extent or functional evidence. The older clinical article's English publisher citation establishes **2012**, correcting the input's 2011; its Persian issue date is 1390.

There are **78 unresolved identity terms**: 71 anatomy names and all seven network names. They remain empty, as do all Persian descriptions. Attested usage is not a national nomenclature standard or a claimed human specialist sign-off. The per-identity terminology ledger preserves the original candidates and explains each decision.

## Sources, rights and attribution

The real local registry initially contained 189 SourceReferences. Deterministic resolution classified the 24 retained master sources as **NEW_VERIFIED_SOURCE_CANDIDATE**, with **0 MATCHED_EXISTING**. Original Web sources: 13 new verified candidates and one ambiguous primary-publisher lead. No fake negative database PKs were inserted. Source-row approval concerns bibliographic identity and its stated evidence role, not permission to redistribute all material from the cited resource.

The portable master retains unique negative external placeholders. The validation script considers normalized DOI, PMID, canonical URL and normalized bibliographic identity together. Duplicate or conflicting locator hits fail closed; existing rows are not silently merged or rewritten. Only verified new rows are created in a disposable target. Target-specific positive IDs and the `.resolved.json` derivative are generated outside the repository and must not be committed.

Rights findings are recorded per source and per use. HBAO declares [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); upstream Allen and Uberon attribution is retained. [Uberon](https://obofoundry.org/ontology/uberon.html) declares CC BY 3.0. The pinned [CBIG MIT grant](https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.19.2-Yeo2011_Schaefer2018/LICENSE.md) and full copyright/license notice are retained for the selected name/index metadata. The [Allen 3D 2020 README](https://download.alleninstitute.org/informatics-archive/allen_human_reference_atlas_3d_2020/version_1/README.pdf) establishes CC BY 4.0 from September 2022 for that particular atlas resource.

The [HBAO README](https://raw.githubusercontent.com/brain-bican/human_brain_atlas_ontology/3ff272135c917b0437edc4cab7d23bd25f05244b/README.md) states that it converts Allen StructureGraph 10. [Allen's current terms](https://alleninstitute.org/legal/terms-of-use) permit research/noncommercial use, require attribution and preserve Allen's Freedom to Innovate; commercial uses need an applicable specific grant or written permission. The [citation policy](https://alleninstitute.org/legal/citation-policy) requires clear dataset attribution and source links when data is displayed. No graph-10-specific commercial exception was independently established. Its scope is not resolved by the separate 2020 3D license or HBAO's declaration alone. The dossier records this unresolved compatibility and blocks all Allen-derived anatomical publication candidates. The research artifact remains noncommercial curation; no exclusive rights to upstream data or restrictions on Allen's independently developed improvements are asserted.

Independent expansion also found the newer [HOMBA 2026 ontology](https://alleninstitute.github.io/CCF-MAP/docs/HOMBA_ontology_v1.html) and [AHRAv2](https://alleninstitute.github.io/CCF-MAP/descriptions/human_ccf.html). Their distinct identities, developmental/cross-species scope and rights/version questions are preserved as deferred authority leads; neither is silently substituted for HBAO or licensed by the version-1 2020 grant.

These grants do not cover every upstream figure, template or third-party asset. [NIMH policy](https://www.nimh.nih.gov/site-info/policies) allows its institutional text subject to exceptions but requires permission for images even with attribution. The [HRA Brain Male v1.3 NIH 3D candidate](https://3d.nih.gov/entries/20960?version=1) declares CC BY 4.0, but its mirrored/resized geometry and HBAO crosswalk need separate review. The 2025 Radua article declares CC BY-NC-ND 4.0; none of its source content/figures is redistributed.

**No images, meshes, atlas volumes, masks or publisher full text are bundled.** Unresolved ISUOG/article visual rights, third-party MNI/FreeSurfer content and future mesh notices affect deferred assets; no permission for those uses is asserted. This research derivative is not an official HBAO, Allen, Uberon or CBIG release. Third-party license notices do not grant an open-source license to the surrounding repository or blanket commercial rights to this dossier.

## Reproduce validation

From the repository root, with its installed backend dependencies:

```powershell
python scripts/validate_brain_dossier.py --self-test
python scripts/validate_brain_dossier.py `
  --dossier docs/research/brain/v0.9.2b/psychology_atlas_brain_curated_dossier_v0.9.2b.json `
  --database backend/data/psychology_atlas.sqlite3 `
  --output ../brain-dossier-validation
```

The output directory must be new and outside the repository. Before database/output creation, the script verifies exact parent lineage, declared category counts, complete publication ledger coverage/counts, and this phase's commercial anatomical deferral. The script opens the original SQLite database read-only, backs it up, migrates only the copy, resolves verified SourceReferences, emits a target-specific derivative, and invokes the existing importer, read-only promoter, Brain audit and research archive verifier. It compares every canonical Brain table before/after and verifies that the original database hash is unchanged. Refusals and failures retain evidence rather than overwrite a previous run. The recorded verification URLs and immutable source hashes allow rechecking the scientific inputs; the runtime resolver is not an automated scientific reviewer. Rights clearance requires a separately reviewed phase change; editing a dossier status cannot silently unblock this research phase.

## Executed checks

- Brain baseline: **106 tests passed, 3 PostgreSQL-only concurrency tests skipped** on SQLite.
- Validation self-check: **PASS**, covering matches, duplicate ambiguity, conflicting locators/title, version-sensitive URL conflicts, audit debt/issues, altered/escaping parent lineage, truncated staging/deferred inventory, ledger coverage and wrapper dispositions, anatomical approval/review mutations and restored hierarchy while rights remain unresolved.
- Strict UTF-8/JSON intake and reviewed master: **PASS**.
- Disposable local source resolution: **24 new verified sources, 0 existing matches**, no unresolved bibliographic source rows in the derivative. Bibliographic resolution does not clear commercial rights.
- Existing `import_brain_dataset`: **346 staging research records archived, 0 issues**.
- Existing `promote_brain_staging`: **346 staging records, 0 issues, `canonical_writes=0`**. This is structural validation, not publication eligibility.
- Deferred hierarchy: **74 claims / 420 combined probe records, 0 structural issues**, checked through the existing staging validator in transactions that always roll back. The temporary probe review state satisfies the parser's structural precondition only; master/resolved dispositions remain deferred. Invalid endpoint, predicate, provenance and cycle mutations are rejected by those same existing rules; no probe archive survives.
- Existing `audit_brain_atlas --json`: **0 errors, 0 review debt, 0 staging issues**.
- Existing `verify_research_datasets`: **3 datasets / 2,264 records PASS**, including the two unchanged legacy archives.
- Public API on the migrated validation copy: **200 with zero list results; 404 for `brain` detail**.
- `git diff --check`: **PASS**.
- Every canonical Brain content count remained **0**: anatomy, networks, hierarchy, aliases, external identifiers, memberships and functional associations. Original database bytes were unchanged. The original local schema has no Brain tables; only the disposable copy was migrated through 0036.

The promoter/audit retain their existing blocked-publication labels. Those labels are infrastructure behavior, not evidence that canonical publication happened or that a curator may bypass it. Remote production database state was not accessed. CI now runs the same resolver check and disposable dossier validation at the PR head; live CI and fresh review status belong to the PR, not a fabricated completion entry in this artifact.

## Review boundary

The master includes a candidate-by-candidate scientific/rights ledger covering **420 retained research entries** (346 staging records and 74 metadata-only hierarchy claims): **45 APPROVED_CANDIDATE** entries comprising 24 bibliographic sources, seven network definitions, seven network label aliases and seven native network identifiers; **375 DEFERRED** entries comprising all Allen-derived anatomy, anatomy aliases/identifiers and hierarchy. The removed Uberon crosswalks and unresolved aggregator source have their own ledgers; functional and terminology research remain explicit. Approval here is confined to the stated source/name metadata scope; it does not claim canonical approval, human specialist certification, a publication-ready anatomical corpus or automatic release authorization.

Open scientific work: specialist terminology/identity sign-off where required by publication review; unresolved Persian names; ventricular primary parentage; competing finer atlas identities; Uberon equivalence; HBAO-to-network spatial mappings; reconciliation of task-specific functional findings. **The commercial anatomical rights gate is unresolved and material.** It needs source/rightsholder clarification or a separately curated commercially compatible corpus. Other open rights work concerns deferred assets/content. A later explicitly authorized publication phase must review these boundaries and keep unsupported/deferred material unpublished.
