# Psychology Atlas — v0.6.2 Research Promotion
## Conservative Promotion + Dedupe + Aliases

**Date:** 2026-09-05  
**Project path:** `<repository-root>`
**Base:** v0.6.1 Architecture Foundation  
**Scope:** source-backed ResearchRecord promotion only. Public APIs, frontend Atlas pages and Knowledge Graph visibility remain deferred.

---

## 1. Goal

v0.6.2 converts the canonical Psychologist/Theory/Timeline schema from v0.6.1 into a controlled runtime projection of the existing lossless Research Staging archive.

The promotion rule is intentionally conservative:

```text
ResearchRecord
    ↓
identity resolution
    ↓
resolved SourceReference provenance
    ↓
canonical entity
    ↓
alias preservation
    ↓
explicit sourced relations
```

No missing source, date, attribution or endpoint is fabricated.

---

## 2. New promotion runtime

New canonical service:

```text
backend/atlas/research_promotion.py
```

New management command:

```text
python manage.py promote_research_staging
python manage.py promote_research_staging --dry-run
```

`--dry-run` executes the complete pipeline inside a transaction and rolls back both runtime rows and staging-index normalization.

The existing `import_research_datasets` command now invokes the same promoter after its previous v0.5-compatible source/content/relation promotion. `--no-promote` remains staging-only.

---

## 3. Identity resolution

Blind creation from `external_id` is not used.

Cross-corpus analysis showed duplicate/variant identity records. Promotion groups exact normalized identities and permits only a narrowly bounded merge when records share a stable canonical slug and their names differ only by harmless single-letter initials or English possessive morphology.

Examples observed in the real corpus:

```text
Ivan Pavlov
Ivan P. Pavlov
→ one canonical Psychologist + alias

Beck Cognitive Model
Beck's cognitive model
→ one canonical Theory + alias
```

General fuzzy matching is deliberately not implemented.

Potential-duplicate staging records remain review hints rather than automatic merge commands.

---

## 4. Source policy

A future-domain record is eligible only when its source references resolve to the canonical shared `SourceReference` registry.

For Psychologist records, source evidence may come from:

```text
source_ids
key_works
major_publications
```

This allows older source-linked person records to resolve provenance without pretending that every legacy biographical field has the same verification quality.

Important field-level rule:

> A source-checked identity does not make weaker legacy demographic fields source-checked.

For example, unreviewed legacy `born` / `died` values are not copied into canonical `birth_year` / `death_year` merely because another source-checked row describes the same person.

Unknown remains unknown.

---

## 5. Canonical runtime inventory

After committed promotion:

```text
Psychologist         76
PsychologistAlias     7
PsychologistSource  135

Theory               45
TheoryAlias            2
TheorySource          74

TimelineEvent         61
TimelineEventSource   61
```

Staging identities deliberately left unpromoted:

```text
Psychologist identity groups without resolved source   37
Theory identities without resolved source               2
Timeline events without resolved source                  2
```

ResearchRecord mapping state:

```text
psychologists:   130 total / 93 mapped staging rows / 37 unmapped
                 93 rows map to 76 canonical people because duplicates share one target

theories:         53 total / 51 mapped staging rows / 2 unmapped
                 51 rows map to 45 canonical theories

timeline_events:  63 total / 61 mapped / 2 unmapped
```

---

## 6. Canonical-key correction

The old generic staging normalizer used `section.rstrip("s")`, which created malformed future-domain keys such as:

```text
theorie:...
timeline_event:...
```

v0.6.2 replaces that logic with an explicit section→entity map and repairs the existing normalized indexes:

```text
theorie:        → theory:
timeline_event: → timeline-event:
```

The raw ResearchDataset/ResearchRecord payloads are not rewritten.

---

## 7. Relation semantics

The real staging corpus introduced relation labels beyond the initial v0.6.1 vocabulary. They were modeled explicitly rather than weakened into generic associations.

Added person-attribution semantics include:

```text
researched_or_developed
developed_or_majorly_associated_with
majorly_associated_with
```

Theory semantics include:

```text
includes_construct
```

Timeline semantics include:

```text
involves_person
marks_theory_milestone
marks_therapy_milestone
marks_technique_evidence_milestone
```

`TimelineTechnique` + `TimelineTechniqueSource` were added because the real corpus contains a source-backed Technique evidence milestone.

---

## 8. Promoted sourced relation inventory

Current runtime rows:

```text
PsychologistTheory       48
PsychologistConcept      74
PsychologistTherapy      19
PsychologistPsychologist  0

TheoryConcept            75
TheoryTherapy             3
TheoryTechnique           0
TheoryTheory               3

TimelinePsychologist     55
TimelineTheory           27
TimelineTherapy          25
TimelineTechnique         1
TimelineConcept          35
```

All promoted rows above have relation-level `SourceReference` provenance.

The empty `TheoryTechnique` table is intentional. The staged `Theory → Technique / grounds` relation currently targets an uncertainty-exposure Technique that is itself not source-backed/runtime-mapped. The relation therefore remains staging-only instead of creating an unsupported Technique.

After all supported v0.6.2 relation promotion:

```text
fully resolved + source-backed future-domain relations without a canonical model = 0
```

The single future-domain relation skipped for missing relation provenance remains staging-only.

---

## 9. Timeline precision

All 61 currently promoted timeline records are year-only events in the current source-backed subset.

Verified runtime invariant:

```text
date_precision = year
exact_date = null
```

No `YYYY` value is converted to `YYYY-01-01`.

The schema remains capable of exact dates, year ranges, approximate years and unknown precision if future verified data provides them.

---

## 10. Idempotency and lifecycle

Repeated `promote_research_staging` runs create no duplicate canonical entities, aliases, source links or relations.

Repeated `seed_mvp` runs preserve all v0.6.2 promoted rows because imported scientific entities/relations are not seed-owned.

Existing user/history state remains unchanged.

---

## 11. Migrations

```text
0018_v061_psychologists_theories_timeline_foundation.py
0019_v062_research_promotion_semantics.py
0020_v062_timeline_relation_semantics.py
0021_v062_timeline_therapy_technique_semantics.py
```

---

## 12. Validation

Backend regression:

```text
114 / 114 tests PASS
Django check PASS
migration drift NONE
compileall PASS
pip check PASS
```

Research archive:

```text
ResearchDataset  2
ResearchRecord   1,918
SourceReference  189
verify_research_datasets PASS
```

The raw source archive remains byte-for-byte recoverable with the frozen SHA-256 values.

Seed lifecycle:

```text
seed_mvp run #1 PASS
seed_mvp run #2 PASS
v0.6.2 runtime rows preserved
```

Knowledge Graph intentionally unchanged in this slice:

```text
478 nodes
934 edges
18 build queries
```

This is expected because Psychologist/Theory/Timeline graph integration belongs to a later v0.6 slice.

---

## 13. Deferred to v0.6.3+

Not implemented by v0.6.2:

```text
Psychologist public API
Theory public API
Timeline public API
Psychologist frontend Atlas
Theory frontend Atlas
Timeline UX
Global Search integration
Knowledge Graph node/edge integration
Graph cache invalidation for graph-visible v0.6 models
```

The next logical slice is v0.6.3: public Psychologist + Theory APIs and Timeline API contract with bounded filters/query budgets and provenance-aware detail serialization.
