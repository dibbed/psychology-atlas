# v0.9 Brain and Assessments Atlases — architecture freeze

Status: **design only** · 2026-09-29. This document freezes domain boundaries and conditional implementation contracts. It does not assert that any v0.9 schema, data, route, UI, or test exists.

Labels in this document have fixed meanings:

- **VERIFIED** — observed in the current checkout, local staging database, GitHub, or the linked external source. Repository facts are tied to `b334835432ce2245ec5c7d5a8b71cd37d40767f3`; recheck before implementation.
- **PROPOSED** — the v0.9 architecture decision and its acceptance criteria; no implementation is implied.
- **DEFERRED** — intentionally omitted from v0.9, even where a future model is described.
- **OUT OF SCOPE** — prohibited for this roadmap without a separately reviewed change.
- **UNRESOLVED** — an input or scientific/rightsholder decision that cannot be inferred from this corpus. A dependent record must not be published until resolved.

## 1. Verified authority and constraints

**VERIFIED — repository:** Local `main`, `origin/main`, and remote GitHub `main` resolve to `b334835432ce2245ec5c7d5a8b71cd37d40767f3`. `v0.8.4` is the latest published release and points to that commit. Open PRs #30 and #26 are dependency updates. CI and CodeQL completed successfully on the main commit. The latest migration file and applied `atlas` migration are `0032_v084_study_sessions`; it depends on `0031_v083_recommendation_feedback`. This is a snapshot, not a promise about the migration number at implementation time.

**VERIFIED — live architecture:** `backend/atlas/models.py` defines `SourceReference`, per-domain alias and source-link models, `ScientificReviewStatus` (`unreviewed`, `source_checked`, `reviewed`), abstract `ScientificRelationBase`, and lossless `ResearchDataset`/`ResearchRecord`. `backend/atlas/management/commands/import_research_datasets.py` and `backend/atlas/research_promotion.py` enumerate supported sections and relation semantics. `backend/atlas/views.py` explicitly builds global search and Knowledge Graph results from named domains. `backend/atlas/signals.py` explicitly lists models that invalidate the `atlas_graph` cache. `backend/atlas/search_utils.py` handles Persian/Arabic yeh and kaf variants; `backend/atlas/pagination.py` sets page size 30 and maximum 300. Disorder, concept, and therapy bookmarks/notes have separate foreign keys, handlers, and serializers; they are not polymorphic.

**VERIFIED — staging:** The local database has two active archived research datasets and 1,918 ResearchRecords. It has no dedicated anatomical, network, instrument, version, adaptation, norms, or psychometric section. Record 1889 explicitly names the missing brain/neuroscience atlas and method-specific evidence; 1887 explicitly names the missing assessment instrument, psychometric, norm, rights, translation, and validation pass. Records 1890 and 1894 flag Persian terminology and neurocognitive gaps. Three structured neuropsychology concepts (records 864–866) describe executive functions, inhibitory control, and cognitive flexibility; they are not brain structures. Thirty-eight older symptom payloads hold 52 distinct `measures` strings, with model-knowledge verification rather than instrument-level validation. The DSM `assessment_tools` content is mostly a repeated generic caution. There is no canonical Brain or Assessment entity to migrate or promote.

**VERIFIED — external scientific boundary:** NIMH RDoC distinguishes circuits, physiology, behavior, self-report, and paradigms as separate units of analysis ([NIMH](https://www.nimh.nih.gov/research/research-funded-by-nimh/rdoc/units)). The Human Connectome Project describes one specific versioned multimodal cortical parcellation, not a universal anatomical identity system ([HCP](https://humanconnectome.org/study/hcp-young-adult/article/nature-article-cortical-brain-maps-at-the-highest-resolution-to-date)). Inferring a cognitive process from activation alone is limited by selectivity ([Poldrack 2006](https://pubmed.ncbi.nlm.nih.gov/16406760/)); distributed lesions can converge on a symptom-related network ([Boes et al. 2015](https://pubmed.ncbi.nlm.nih.gov/26264514/)). COSMIN treats measurement properties and their study methods separately ([COSMIN manual](https://www.cosmin.nl/wp-content/uploads/COSMIN-manual-V2_final.pdf)). The International Test Commission calls for rightsholder permission before test adaptation ([ITC guidance](https://www.intestcom.org/files/guideline_test_adaptation_2ed.pdf)). These sources guide the design; they do not supply approved v0.9 content rows.

**PROPOSED — authority rule:** Current source and migration graph win over this document if they change. ResearchRecord payloads, index output, and source links are leads, not publication approval. An entity or scientific relation becomes public only after identity, source, scientific review, and rights gates appropriate to that record pass.

## 2. Brain Atlas identity and hierarchy

### 2.1 Primary entities

**PROPOSED — `BrainAnatomicalEntity`:** The canonical browsable anatomy unit is a named anatomical entity in one curated hierarchy. It can represent whole-brain/root structures, hemispheres, lobes, cortical regions, subcortical structures, and other named anatomical structures. `BrainRegion` is too narrow for all these units and must not silently equate a lobe, nucleus, and parcellated cortical area. The kind is explicit; kind does not imply a function. A structure can exist without any behavioral association.

**PROPOSED — laterality:** A curated entity has explicit laterality: left, right, midline, bilateral/unlateralized, or not established. Side-specific entities have distinct stable identities and slugs only when the chosen source distinguishes them. Do not generate mirror records or infer laterality. A hemisphere may be a real hierarchy node; laterality is also an attribute used to validate its descendants. A generic bilateral identity must not be silently merged with a side-specific one.

**PROPOSED — `BrainNetwork`:** A distributed functional network is a separate canonical entity, not a subtype of anatomical structure and not a parent in the anatomical tree. Networks can overlap and change with method, task, and atlas definition. Structure-to-network participation is an explicit sourced relation. A network can have aliases and external identifiers of its own. It has no anatomical parent field.

**DEFERRED — functional systems:** Broad labels such as “executive system” do not become `BrainAnatomicalEntity` or `BrainNetwork` by naming alone. Existing `Concept` can represent a cognitive construct when appropriate. A separate functional-system taxonomy awaits a scientific source set and demonstrated navigation need.

### 2.2 Canonical identity

**PROPOSED:** Each anatomy/network entity has an immutable public slug, canonical English name, optional reviewed Persian name, explicit kind, active flag, `ScientificReviewStatus`, and ownership (`seed_managed` versus research-promoted). Slugs are identity keys, never generated from a translated display name after creation. Renames retain the slug unless a documented identity correction requires an alias/redirect decision. English and Persian aliases and abbreviations are separate, typed, language-tagged rows with uniqueness within their owner. Acronyms are searchable but not globally unique. Persian spelling and transliteration are reviewed; `search_variants` is a query aid, not an identity resolver.

**PROPOSED — external IDs:** An external identifier records namespace, identifier, source/atlas version, and URL if authoritative; uniqueness is scoped to namespace and version. HCP parcel IDs, Brodmann labels, and coordinates are not interchangeable canonical identities. The same English label from two atlases is a dedupe candidate, not an automatic merge. Dedupe requires kind, laterality, defined spatial scope, source version, and curator review. Conflicting or ambiguous records remain staging-only with a reported conflict.

### 2.3 Anatomy tree

**PROPOSED:** v0.9 has one selected **primary hierarchy**. A concrete `BrainHierarchyLink` records child, immediate parent, the selected anatomy source/version, review/active state, and relation-level `SourceReference` links. At most one active primary link exists per child; a root has no incoming parent link. No fabricated root content is required before a reviewed dataset exists. Parent means “anatomically part of within the selected hierarchy,” not “functions like,” “connects to,” or “is activated with.” A child cannot parent itself; moving a link must reject any cycle. Validation must also reject a side-specific child under an incompatible opposite-side parent and prevent an active child of an inactive parent from being published. Inactivating a parent hides its descendant branch from public hierarchy views until curated repair or explicit reparenting. Historical links and entities remain stored.

**PROPOSED — deletion:** Public content changes use deactivation, not hard deletion. Any child, historical source link, association, or external mapping blocks hard deletion of an anatomical entity; source references remain protected. A curator-only hard-delete policy would require a separate migration-safe review of dependent data and is not an API operation.

**DEFERRED — multiple parents:** Anatomical hierarchies can differ by atlas or framework. v0.9 does not represent competing parentage as one unqualified tree or infer extra parents from labels. If multiple sourced hierarchies are required, introduce multiple explicitly versioned hierarchy schemes in a later design; keep the v0.9 primary tree coherent.

## 3. Brain scientific assertions and provenance

**PROPOSED — distinct meanings:**

| Assertion | v0.9 treatment | Publication gate |
| --- | --- | --- |
| Anatomical `part_of` | `BrainHierarchyLink` in the primary hierarchy only | Named anatomical source/version, relation-level citation, cycle and laterality validation. |
| Structure participates in network | Dedicated membership relation, never parentage | Network definition, method, source, and qualifier. |
| Structure/network related to a cognitive function or existing Concept | Dedicated functional-association relation with exact subject type, construct, claim wording, method/task/population context, and limitations | Resolved primary or authoritative synthesis source and scientific review. No inference from name alone. |
| Connectivity between structures/networks | **DEFERRED** as a separate directed/undirected, modality-specific evidence class | Needs measure, direction, task/state, population, processing method, and source. |
| Imaging activation | **DEFERRED** as a study finding, not a generic graph edge | Needs contrast, modality, sample, statistical threshold, coordinate space/parcellation, and source. |
| Lesion-to-symptom evidence | **DEFERRED** as a distinct study finding | Needs lesion definition, comparison, symptom measure, sample, network effects/limitations, and source. |
| Symptom/disorder association | **DEFERRED** until evidence semantics and confounding are reviewed | Must not imply localization or diagnostic inference. |
| Theory relation | **DEFERRED** unless a specific historically/scientifically defensible relation is proposed | Theory is not anatomical evidence. |

**PROPOSED — relation shape:** Each implemented scientific relation has concrete endpoint roles and an explicit predicate; it reuses `ScientificReviewStatus`, active state, ownership, and separate relation-level links to `SourceReference` with a note identifying the supported claim. Entity-level sources document identity/description; they do not automatically support every relation. An abstract field mixin may reuse existing `ScientificRelationBase`, but no generic `associated_with` table or edge is approved. Where a study supports several modalities, findings remain method-specific and cite the same source as needed. Unsupported relation types are staging-only.

**PROPOSED — interpretation rules:** Association ≠ causation. Activation ≠ exclusive functional localization. Lesion evidence ≠ universal functional localization. Brain association ≠ diagnostic inference. Public copy and graph edge labels must preserve those distinctions; pathfinding cannot convert a sequence of associations into a clinical conclusion. `source_checked` means citation and claim were checked against a source, while `reviewed` requires the designated scientific review process. Unreviewed rows remain non-public by default in this new domain.

**UNRESOLVED:** Which first anatomical atlas/version and which reviewed association dossier will be licensed and curated? No data or public relation is approved by this architecture alone.

## 4. Brain visualization

**PROPOSED:** v0.9.3 begins with an accessible hierarchy/list and source-backed detail pages. It needs no coordinates or image asset. Network pages or diagrams are shown only when reviewed network definitions and relations exist. A visualization never substitutes for the text hierarchy and citations.

**DEFERRED — anatomical image/map:** An optional asset requires documented origin, license and permitted use, attribution, version, coordinate system where applicable, parcel/region identifier mapping to canonical entities, update policy, and keyboard/screen-reader text fallback. No coordinate, shape, or brain illustration is synthesized to make a missing asset appear factual. Failure to obtain an asset does not block the core atlas.

## 5. Assessments Atlas identity and forms

### 5.1 Instrument, version, and adaptation

**PROPOSED — `AssessmentInstrument`:** Canonical family identity only: stable slug, canonical English name, reviewed Persian display name if available, aliases/acronyms, short description, construct overview, publisher/rightsholder reference when verified, active flag, ownership, `ScientificReviewStatus`, and entity-level sources. It does **not** carry universal reliability, validity, cutoff, norm, item text, scoring key, license grant, or diagnostic claim.

**PROPOSED — `AssessmentVersion`:** A separately identified published edition, revision, or short form of exactly one instrument. It has stable version/form key, official label, form kind, publication year if sourced, optional `derived_from` version, intended age/range and administration/informant notes where officially sourced, active/review/ownership fields, and source links. The unique identity is instrument plus version/form key; “short form” does not overwrite the full form. Unknown edition stays unknown rather than being assigned the latest version.

**PROPOSED — `AssessmentLanguageForm`:** A distinct translation/adaptation of one version, identified by version, language/locale, translation identifier or named source, and publisher/owner where known. Multiple Persian forms can coexist without automatic dedupe. `name_fa` on the instrument is a display translation, not proof of an authorized test form. A form is called “validated for population X” only through linked reviewed validation evidence for that form and population; no `is_validated` boolean follows merely from Persian text or a translated title. Official/authorized status is a separately sourced rights fact, not inferred from publication.

**PROPOSED — `AssessmentValidationStudy`:** A source-backed study/sample container distinct from the form it evaluates. It identifies the exact version/language form, citation, study design, population, recruitment/sample context, sample size where reported, administration mode, informant, comparator/reference standard when applicable, and limitations. One publication may report multiple populations or samples and thus more than one study context. A study row establishes that evidence was reported; it does not make a form universally validated. Its findings are separate records below.

**PROPOSED — aliases:** Instrument and version aliases/acronyms are typed and language-tagged, unique within their owner. An acronym such as BDI is ambiguous without version and must not redirect to BDI-II automatically. Dedupe uses verified publisher/form identifiers, exact edition and language, plus curator review. Similar names, score ranges, or construct overlap are insufficient.

### 5.2 Purpose, construct, population, mode, informant

**PROPOSED:** Intended uses are explicit sourced statements such as screening, severity monitoring, research measurement, or diagnostic support, scoped to a version/form and context. Formal diagnosis is **not** an instrument relation: clinical diagnosis requires a separate professional assessment and standard. Construct links to existing `Concept` are explicit sourced `measures` or `research_measure_of` relations; symptom/disorder links use the narrower approved meanings below. Administration mode (paper, clinician interview, self-report digital, etc.), informant, target population, age range, and language are properties of the version/form or evidence context as appropriate, not universal instrument assumptions. No global Population master table is justified by the current corpus; controlled descriptors plus study-specific sample details are sufficient for v0.9.

### 5.3 Access and rights

**PROPOSED — access record:** Access and licensing are scoped to version/form, material type, use, jurisdiction, owner, terms, evidence source, verification date, and expiry where applicable. The default is **unknown / permission not established**. A public web page, published validation article, or accessible PDF does not establish public-domain status, permission to redistribute a form, or permission to implement digital scoring. Metadata listing and access to protected materials are separate decisions. User-visible access language must say what is actually verified, not collapse unknown into “free.”

**OUT OF SCOPE — protected content:** Do not store or serve proprietary item banks, protected questions, scoring keys, manual text, or official translation content unless explicit rights for the exact material and use have been documented. v0.9 has no item-bank or scoring engine fields/API. This boundary applies even if a third-party site displays the material. The rightsholder/licensing review is per instrument and version; legal uncertainty remains unresolved rather than guessed.

## 6. Psychometric evidence

**PROPOSED — dedicated `AssessmentPsychometricEvidence`:** v0.9 needs a context-aware finding record even if the first curated release has zero numerical findings. Each finding belongs to one `AssessmentValidationStudy`, through which it identifies the exact instrument version/language form, `SourceReference`, population, sample/context, administration/informant, study method, comparator/reference standard, and study limitations. The finding itself identifies the measurement property, statistic type and method, value and units when meaningful, uncertainty/interval when reported, finding-specific limitations, `ScientificReviewStatus`, and active/ownership state. A study can yield multiple findings. Version/form and source resolution are required before numerical publication. The API must serialize this context beside a value. Values retain original precision and are never aggregated silently into an instrument-level headline.

**PROPOSED — property semantics:** Reliability includes its method (for example internal consistency versus test–retest), interval, and sample. Validity names its form (content, structural, criterion, cross-cultural, or construct) and comparator/design. Responsiveness is distinct from reliability. Sensitivity and specificity are paired with a specified cutoff, target condition, reference standard, sampling frame, and confidence interval where available; they are not free-floating properties. A norm requires a defined normative sample, score distribution, demographic stratification, version/form, and use conditions. A cutoff requires outcome, purpose, population, threshold direction, and validation source.

**PROPOSED — v0.9 publication limit:** The foundation may hold reviewed, source-backed descriptive evidence and carefully extracted reliability/validity findings. Numeric publication requires a reviewed extraction sheet and faithful serialization of method, population, version/form, and limitation beside the value. No numeric finding is derived from the current staging `measures` strings.

**DEFERRED:** Norm tables, score calculators, severity bands, cutoffs, sensitivity/specificity cards, automatic recommendations, and interpretation engines. Their contextual structures must be designed from real studies and licensing decisions before implementation. The evidence model must not use a single nullable field pile to imply these are already supported.

## 7. Assessment relations

**PROPOSED — approved meanings, conditional on source-backed rows:**

| Predicate | Endpoint and meaning | Guardrail |
| --- | --- | --- |
| `measures` | Version/form → existing `Concept`: a stated target construct. | Does not establish validity in every population. |
| `research_measure_of` | Version/form → `Concept`: used to operationalize a construct in research. | Not equivalent to clinical utility. |
| `screens_for` | Version/form → `Disorder` or `Symptom`: supported screening purpose. | A positive screen is not a diagnosis. |
| `monitors` | Version/form → `Symptom`, `Disorder`, or `Concept`: supported longitudinal severity/change use. | Requires responsiveness and interpretation context when claimed. |
| `diagnostic_support_for` | Version/form → `Disorder`: source explicitly supports use as one input in an assessment. | Never serialize as “diagnoses”; no automatic diagnostic inference. |

**PROPOSED:** These are separate concrete relation semantics or an equivalently constrained typed relation with endpoint-specific validation and relation-level source links; graph labels must retain the predicate. A relation cannot become public without source resolution, supported form/version, and scientific review. Theory and Therapy have no automatic instrument edge. A therapy-to-assessment relation needs a demonstrated use case and explicit trial/protocol evidence, so it is **DEFERRED**. Existing Concept/Symptom/Disorder IDs are reused only after identity review; textual mentions are not automatic edges.

## 8. Cross-domain product integration

**PROPOSED — staged entry:** v0.9.2 API and v0.9.3 frontend may expose curated Brain anatomy independently; v0.9.4 does the same for curated Assessments. Their domain-local search uses existing Persian variants, reviewed aliases, and stable slugs. Neither domain appears in global search or the Knowledge Graph until v0.9.5 integration tests and graph semantics pass.

**PROPOSED — global search:** Extend the current fixed response shape additively with `brain_entities` and `assessments` only after the corresponding public records exist. Preserve existing arrays and search ranking behavior. Search only active, public/reviewed rows and active parents/forms; exact canonical name/slug/alias/acronym matches rank ahead of descriptions. Avoid merging identically named anatomy from different parcellations or ambiguous assessment acronyms into one result.

**PROPOSED — Knowledge Graph:** Add explicitly named node types for anatomy, network (only if populated), instrument, and version/form only where the graph has a navigable use case. Add only reviewed, source-backed relation types. Hierarchy and instrument-version edges are structural; functional and psychometric claims are scientific and must remain visibly distinct. Do not turn study findings, “screens for,” or a graph path into diagnosis/causation. Graph filters, available-edge metadata, neighborhood validation, and pathfinding endpoint checks must enumerate the new types. Pathfinding may traverse approved edges, but response labels/provenance preserve direction and relation meaning; clinical inference from transitive paths is prohibited.

**PROPOSED — cache:** The current `atlas_graph` cache and explicit signal sender tuple require deliberate additions for each included model and source-link model. Deactivation, parent changes, alias changes where graph labels use them, relation updates, and source-link changes must invalidate the cache. Verify transaction timing and no stale graph after commit; do not infer that the existing tuple covers new tables.

**PROPOSED — frontend:** New navigation is independent of Study Center. Details show source and review context, limitations, language/form identity, and rights/access status without making numeric psychometrics look universal. The Brain hierarchy has keyboard and screen-reader navigation and a list fallback. A protected form is linked only to an authorized owner/publisher access path, not embedded.

**DEFERRED to v1.0 — Saved and Notes:** Current `Bookmark`, `UserNote`, `ConceptBookmark`, `ConceptNote`, `TherapyBookmark`, and `TherapyNote` are domain-specific. v0.9 does not add Brain/Assessment saved or notes and does not retrofit a polymorphic table. Any later feature must define deletion, inactive-content visibility, owner privacy, and migration of existing saved data explicitly.

## 9. Study and recommendation boundary

**OUT OF SCOPE for v0.9:** `StudyPlanScope`, `StudyBlock`, `StudySession`, Today API, Recommendation V2, mastery/progress, SRS, and scheduler. Brain and Assessment are educational atlas domains. Browsing, reading, bookmarking decisions, or seeing a graph edge cannot create learning evidence, clinical competence, plan scope, recommendation eligibility, or a scheduled block. A future integration needs a separate reviewed architecture and evidence contract. The existing StudyPlan/Block/Session and canonical learning-evidence authorities remain unchanged.

## 10. Data ownership, ingestion, and promotion

**VERIFIED:** The existing importer archives raw datasets and promotes specific v0.5-compatible sections. `ResearchStagingPromoter` promotes source-backed psychologists, theories, timeline events, and supported explicit relations; it is not a generic promoter. `seed_managed` is an ownership marker in several domains, and existing seed code often deactivates omitted owned rows. `ResearchRecord.promoted_model/promoted_pk` links staging to runtime content; unsupported rows stay unpromoted.

**PROPOSED:** Brain and Assessment require dedicated, domain-specific import/promotion validation rather than extending a catch-all mapper. Ingest raw source documents losslessly under a versioned dataset key and hash; do not discard unsupported fields. Resolve source IDs first, then canonical identity and aliases, then evidence and relations. Run inside atomic transactions with dry-run/audit output and idempotent natural keys. An existing slug with conflicting kind, laterality, version, language, or rightsholder is a reported conflict, never overwritten by a near-name match. An absent source, unresolved endpoint, unverified scientific claim, missing rights for protected content, or ambiguous version leaves the record staging-only.

**PROPOSED — ownership:** Curated seed rows are `seed_managed=True`; research-promoted rows are `False` and retain staging pointers/provenance. Reseeding may update only owned fields/rows and deactivates removed seed-owned public content rather than deleting it. Promotion never claims seed ownership or silently reactivates curator-disabled content. Review debt is visible in importer/audit summaries by unreviewed, source-checked, reviewed, weak-only, unsourced, and rights-unknown categories; those are measurements, not a new scientific review vocabulary. A citation from model knowledge is not promoted to independently verified evidence merely by importing it.

**UNRESOLVED:** There is no approved v0.9 source corpus or rights register. The present staging datasets cannot populate the new canonical entities automatically.

## 11. Proposed read-only API contract

**PROPOSED — initial routes only:** `GET /api/brain-anatomy/` and `GET /api/brain-anatomy/<slug>/` expose reviewed active `BrainAnatomicalEntity` rows. The route names the broader anatomical domain because hemispheres, lobes, and structures are included alongside regions. `GET /api/assessments/` and `GET /api/assessments/<slug>/` expose reviewed active instruments and bounded reviewed version/form summaries. These are design contracts, not implemented routes. A separate network route is **DEFERRED** until reviewed network content creates a use case. No public write, scoring, item, coordinate, or diagnosis endpoint is approved.

**PROPOSED — list behavior:** Use repository `AtlasPagination` page-number response (`count`, `next`, `previous`, `results`), page size 30 and maximum 300. Stable ordering is canonical English name then ID, with exact-match relevance first when `q` is supplied. Brain filters: kind, laterality, and parent slug. Assessment filters: construct, intended use, version/form language, and access availability only when those facts are reviewed. Public routes expose reviewed content only, so a public `review_status` filter has no use case. All filter values are validated; unknown values are rejected consistently with existing views. `q` searches English/Persian names, reviewed aliases/acronyms, and slug using `search_variants`; it does not join private staging payload text.

**PROPOSED — detail behavior:** Return stable identity, kind/form, immediate hierarchy or versions, concise approved relation summaries, entity- and relation-level citations, review state, limitations, and rights/access note. Nested children, associations, evidence, and versions are bounded and deterministically ordered; large evidence collections require a later paginated use case rather than unbounded detail payloads. Inactive or unreviewed new-domain records return 404 publicly, including through inactive parents or forms. Historical internal records remain for curation. Do not expose raw ResearchRecord documents, proprietary items, scoring keys, or private workflow notes.

**PROPOSED — performance:** Use `select_related`/`prefetch_related` and bounded serialization where current patterns justify them. Profile representative realistic fixtures and assert against observed query regressions; this document freezes no arbitrary query-count ceiling. Preserve existing v0.8.4 API payloads and routing.

## 12. Provisional migration and slice plan

**VERIFIED:** `0032_v084_study_sessions` is currently the applied tip. **PROPOSED:** If it remains the tip at implementation time, a provisional additive sequence is `0033` Brain identity/hierarchy/network foundation, `0034` Brain provenance/approved relation support, `0035` Assessment instrument/version/language/rights foundation, and `0036` Assessment evidence/relation support. Split or combine only to match the actual final dependency graph and migration safety. No migration is created in this session. Every migration preserves existing content, users, study data, and legacy API contracts; no fabricated backfill or automatic promotion occurs. Validate released v0.8.4 → latest on a disposable copy and zero → latest. Recheck the live graph before assigning filenames.

### Slice acceptance criteria

| Slice | Required completion evidence |
| --- | --- |
| **v0.9.1 Brain Atlas Foundation** | Identity, alias, source, hierarchy, network, laterality, ownership, active/review, and deletion rules implemented as approved; no fabricated content; self-parent/cycle/opposite-side/inactive-parent tests; additive migration validated from v0.8.4 and zero. |
| **v0.9.2 Brain Data + API + Scientific Relations** | Dedicated importer, source/rights resolution and idempotency audit; reviewed anatomical dataset and only approved relation types; list/detail contracts with bounded payloads; negative tests for unsupported claims, missing sources, inactive endpoints, and deletion; no fake coordinates. If the curated dossier is absent, do not claim data completion. |
| **v0.9.3 Brain Atlas Frontend** | Accessible hierarchy/list and details using real API records, citations, limits, and loading/empty/error states; no anatomy asset dependency; no study authority changes. |
| **v0.9.4 Assessments Foundation + Data + API** | Instrument/version/language-form/rights/evidence context implemented; dedicated importer leaves weak strings in staging; source-backed curated metadata and only permitted content; list/detail contracts; tests for translation ≠ validation, acronym ambiguity, rights unknown, contextual metrics, and migration preservation. |
| **v0.9.5 Assessment UI + Global Search + Knowledge Graph** | Assessment UI communicates purpose, version, evidence context, and access; both new domains enter global search and graph only with reviewed rows; explicit edge semantics, graph filtering/path direction, provenance, Persian search, cache invalidation, inactive exclusion, and backward-compatibility tests pass. No diagnosis from graph paths. |
| **v0.9.6 Hardening + Release** | Scientific and rights audits for every published row, full relevant backend/frontend regression, realistic query profiling, both migration paths, CI/CodeQL and release checks; unresolved rights or evidence rows remain unpublished; release only after separate authorization/workflow. |

## 13. Test strategy and gates

**PROPOSED — Brain:** Identity and stable slug; alias/language/acronym collision handling; external-ID namespace/version; hierarchy roots, self-parent, cycles, laterality, parent inactivation, traversal, and delete protection; network separation; source and relation provenance; review state; seed versus promotion ownership; importer idempotency/conflict/staging-only behavior; v0.8.4 data preservation.

**PROPOSED — Assessment:** Instrument versus version/form identity; revisions and short forms; ambiguous aliases/acronyms; multiple translations and no inferred Persian validation; rightsholder/access unknown by default; prohibited content cannot be imported or serialized; source resolution; evidence population/method/version/form context; rejected universal metrics; inactive version/form visibility; migration preservation.

**PROPOSED — integration:** Global-search additive response and Persian variants; graph node/edge types, provenance, filters, pathfinding direction, non-diagnostic labels, and cache invalidation on entity/relation/source changes; domain-specific serializer bounds and query-profile regression; unchanged legacy search, graph, bookmark/note, and study contracts. Run both released v0.8.4 → latest and zero → latest migration paths on disposable databases. Focused tests precede full regression; live rights and scientific review require documentary evidence, not tests alone.

## 14. Unresolved inputs and stop conditions

**UNRESOLVED — Brain:** authoritative initial atlas/parcellation and version, exact hierarchy and laterality mapping, external-ID policy, approved entity list, network definitions, reviewed study extraction for any functional/lesion/imaging claims, and image rights if a map is later desired. Until supplied, anatomy can be modeled but no public brain rows or associations are approved.

**UNRESOLVED — Assessment:** prioritized exact instruments/editions/forms; owner and rights for metadata, materials, translations, and digital use; construct and intended-use review; original and Persian validation papers by population; extracted method-specific psychometrics; policy for conflicting studies. Until supplied, no public instrument content, numeric claims, or rights assertions are approved.

**UNRESOLVED — product:** final public labels for anatomical versus network browsing, whether a reviewed network catalogue has enough content for v0.9, and the precise curated-source review roles. These do not authorize changes to study, scoring, or diagnosis systems.

**OUT OF SCOPE — this session:** Django models, migrations, seed/promotion runs, APIs, frontend runtime, global search, Knowledge Graph runtime, study system changes, tagging, and release. The next session is v0.9.1 only after this architecture and its evidence inputs are accepted; this document does not start it.
