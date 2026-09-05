# Psychology Atlas — v0.6.1 Architecture Foundation

**Date:** 2026-09-05  
**Baseline:** `v0.5.5-final` / `20a60e961a05fde1053f72bb6bddb4fb60f16ed5`  
**Scope:** Canonical Psychologist + Theory + Timeline architecture, provenance foundation, attribution semantics, and migration only.

## 1. Scope boundary

v0.6.1 intentionally does **not** promote staged Psychologist/Theory/Timeline records, add public APIs, add frontend routes, or add these domains to the Knowledge Graph. Those belong to later v0.6 slices.

The goal of this slice is to make the production schema capable of representing future promotion faithfully and safely.

## 2. Research Staging audit used for schema design

The frozen Research Staging database contains:

- 130 Psychologist records
- 53 Theory records
- 63 Timeline Event records
- 82 Claim records
- 25 Research Gap records
- 805 staged relationships overall

Two incompatible-but-related record shapes exist in the imported corpora.

### Psychologist shapes

Legacy-style records include fields such as:

- `psychologist_id`
- `slug`
- `name_en` / `name_fa`
- `born` / `died`
- `nationality`
- `role`
- `key_contributions`
- `key_works`
- `affiliations`
- `verification`

Complete-style records include fields such as:

- `id`
- `full_name`
- `canonical_name`
- `name_fa`
- `aliases`
- `birth_year` / `death_year`
- `nationality_background`
- `academic_disciplines`
- `major_contributions`
- `associated_theories`
- `associated_concepts`
- `associated_therapies`
- `major_publications`
- `institutions`
- `historical_context`
- `source_ids`
- `review`

### Theory shapes

Legacy-style records include:

- `theory_id`
- `slug`
- `name_en` / `name_fa`
- `domain`
- `core_proposition_en` / `core_proposition_fa`
- `proposed_by`
- `period`
- `supports`
- `challenges`
- `sources`
- `verification`

Complete-style records include:

- `id`
- `aliases`
- `theory_family_domain`
- `origin_development_period`
- `creator_developer_ids`
- `historical_context`
- `summary_en` / `summary_fa`
- `core_propositions`
- `major_construct_ids`
- `mechanisms`
- `predictions`
- `applications`
- `supporting_evidence`
- `criticism`
- `limitations`
- `modern_scientific_status`
- `historical_importance`
- related entity IDs
- `source_ids`
- `review`

### Timeline shapes

Legacy-style records are primarily year-level:

- `event_id`
- `year`
- `year_start`
- `event_en` / `event_fa`
- `category`
- `related`
- `sources`
- `verification`

Complete-style records include:

- `id`
- `date`
- `year`
- `date_precision`
- `title_en` / `title_fa`
- `description_en` / `description_fa`
- `people_ids`
- `theory_ids`
- `concept_ids`
- `therapy_ids`
- `historical_importance_en` / `historical_importance_fa`
- `source_ids`
- `evidence_status`
- `review`

The current staged Timeline corpus uses year precision, but the canonical model explicitly supports exact dates, year-only dates, year ranges, approximate years, and unknown precision so future imports do not need fake January 1 dates.

## 3. Canonical entity models

Added:

- `Psychologist`
- `PsychologistAlias`
- `Theory`
- `TheoryAlias`
- `TimelineEvent`

Entity rules:

- stable unique slugs
- Persian-first-compatible bilingual fields
- `ScientificReviewStatus`
- `is_active`
- `seed_managed`
- nullable historical values instead of fabricated values
- aliases stored separately from canonical names
- Psychologist birth/death ordering constraint
- Timeline precision constraints preventing false exact dates

## 4. Shared provenance

No second bibliography registry was introduced.

All new source links reuse the canonical `SourceReference` model:

- `PsychologistSource`
- `TheorySource`
- `TimelineEventSource`

Source roles are explicit so a primary publication is not silently treated as equivalent to a secondary biography or historical review.

## 5. Attribution semantics

Added explicit Psychologist attribution vocabulary:

- `originated`
- `proposed`
- `co_proposed`
- `developed`
- `co_developed`
- `expanded`
- `popularized`
- `researched`
- `applied`
- `contributed_to`
- `criticized`
- `challenged`
- `associated_with`

This intentionally avoids collapsing all historical association into a misleading `creator` relation.

## 6. Canonical relation models

Psychologist relations:

- `PsychologistTheory`
- `PsychologistConcept`
- `PsychologistTherapy`
- `PsychologistPsychologist`

Theory relations:

- `TheoryConcept`
- `TheoryTherapy`
- `TheoryTechnique`
- `TheoryTheory`

`TheoryTechnique` was added because the actual staged corpus contains a real `theory -> technique` relation (`grounds`), even though it was not listed in the initial handoff recommendation.

Timeline cross-domain links:

- `TimelinePsychologist`
- `TimelineTheory`
- `TimelineTherapy`
- `TimelineConcept`

Every relation family has a dedicated `...Source` model backed by `SourceReference`.

## 7. Theory relation semantics

The canonical vocabulary currently supports staged and expected semantics including:

- `grounds`
- `informs`
- `supports`
- `complements`
- `challenges`
- `challenged_by`
- `reformulated_as`
- `supports_interpretation_of`
- `extends`
- `refines`
- `associated_with`

Actual staged relationship examples found during the audit include:

- Psychologist -> Therapy: `developed`, `co_developed`, `contributed_to`
- Psychologist -> Theory: `proposed`, `co_proposed`
- Theory -> Therapy: `grounds`, `complements`
- Theory -> Concept: `grounds`
- Theory -> Technique: `grounds`
- Theory -> Theory: `reformulated_as`, `challenged_by`, `supports_interpretation_of`

## 8. Timeline safety rules

`TimelineEvent.DatePrecision`:

- `exact_date`
- `year`
- `year_range`
- `approximate_year`
- `unknown`

Database/model validation prevents:

- exact-date precision without an exact date
- storing an exact date on non-exact events
- year/range precision without a start year
- year ranges without an end year
- end years earlier than start years

This protects against transforming a source that only says `1879` into a fabricated `1879-01-01`.

## 9. Seed/history ownership

All new canonical entities and scientific relations include `seed_managed=False` by default.

Future Research promotion must create imported records with `seed_managed=False`. Existing `seed_mvp` ownership rules must never deactivate externally promoted v0.6 records.

## 10. Promotion remains disabled in v0.6.1

The existing `import_research_datasets` command still promotes only the v0.5-compatible domains it explicitly supported before this slice.

The presence of new Django models does not automatically make Psychologist/Theory/Timeline staging records production content.

Promotion will be implemented separately after duplicate, alias, source, and relation mapping rules are finalized and tested.

## 11. Graph boundary

The new models are **not graph-visible in v0.6.1**.

Therefore graph building and graph cache invalidation are intentionally unchanged in this slice. Graph integration belongs to the dedicated v0.6 graph phase, where query budgets and path semantics can be tested together.

## 12. Migration

Added migration:

`0018_v061_psychologists_theories_timeline_foundation.py`

The migration is additive. Existing ResearchDataset/ResearchRecord, Atlas content, and user-owned/history rows are not rewritten or deleted.

## 13. v0.6.1 acceptance target

Before this slice is considered complete:

- Django check passes
- migration applies cleanly
- migration drift is zero
- existing v0.5.5 tests still pass
- new architecture tests pass
- research archive verifier passes
- seed remains idempotent/history-safe
- actual DB counts for frozen domains remain stable
- Psychologist/Theory/Timeline production tables remain empty until explicit promotion
- frontend typecheck/build still pass even though no frontend v0.6 UI is added

## 14. Next slice

v0.6.2 should implement conservative promotion only after:

1. canonical identity resolution across both dataset schemas
2. duplicate review
3. alias normalization
4. source-ID resolution
5. review-status mapping
6. relation vocabulary mapping
7. unsupported/ambiguous semantics remain staging-only
8. idempotency tests prove repeated promotion creates no duplicates
