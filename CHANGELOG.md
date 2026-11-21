# Changelog

All notable changes to Psychology Atlas. This project follows Semantic Versioning; a version listed here is not released until an authorized tag and GitHub Release exist.

## [Unreleased] — v1.0.0 (Admin CMS)

### Added

- Turn 08 W16-02: exact revision-bound, immutable private frozen review manifests for Learning, Brain and Assessment, with safe dry-run, idempotent freeze, actor-scoped receipt, a schema-checked digest, Persian UI and migration `0061`. **Review-only:** no public Apply/clearance or candidate data is exposed.
- Turn 08 W16-03: independent reviewer source/scientific/rights **attestation records** for W16 frozen manifests, per-kind capability and two-person gates, append-only evidence/revocation, fresh policy and source checks, redacted API status and Persian reviewer form, migration `0062`. Attestations are **not** legal/scientific publication clearance or authority for Apply.
- W16 plan-lineage schema preparation: migration `0063` adds a nullable self-reference and changes dossier binding to a foreign key for a possible later reinstatement plan. **No generic reinstatement operation is implemented.**
- Turn 07 W13-02 follow-up: versioned `claim-context-v2` evidence fingerprints cover prompts, answer keys, choices and linked Concept/Disorder state across all four Learning authoring kinds; original explanation-only evidence stays marked for review after additive migration `0060`.
- Permission-aware, paged, append-only Learning evidence history includes per-revision actor, timestamp, source changes/removal reasons and current-rights redaction. Historical source and learner data are not rewritten.
- W13 private, versioned source locators for individual QuizQuestion explanations, Flashcards, Daily Challenges and Distortion Practice, with stale-source/rights indicators and no automatic scientific approval or publication. Legacy Learning transfer fails closed for actively sourced content until a provenance-preserving transfer format is authorized.
- W13 Daily Challenge admin contract documents server-local date rotation, eligible-pool order and historical answer pinning; the existing scheduling engine is unchanged.
- Capability-based Admin CMS with MFA, revocable sessions, append-only audit, permission-aware Persian/RTL navigation and owner/curator/delegate roles.
- Canonical editors and governance for core content, concepts, DSM, therapy, history, Brain, Assessment, Learning, cases and privacy operations.
- Source and rights governance with scoped material/use decisions, evidence, expiry, review and public-read enforcement.
- CaseRevision publication workflow: review, frozen manifest, independent approval, MFA apply, idempotent receipts, withdrawal and **reinstatement**.
- Immutable P16 preparation dossiers with live dependency, source and rights rechecks for Learning, Brain and Assessment proposals.
- Turn 08: selection snapshots now bind current editorial-review and source-metadata-rights statuses, with bounded source inspection and fail-closed stale/missing-baseline rechecks.
- Turn 08: `GET /api/admin/publication/preparations/{id}/candidate-preview/` projects the **exact sealed private candidate** only to a scope-authorized admin; public payload, approval and publication remain unavailable.
- Turn 08 continuation: revision-pinned private candidate field-change footprint, bounded reader-impact topology for the Brain/Assessment/Learning selection kinds, permission-scoped exact-alias ambiguity, and debounced slug-only private autocomplete. Public post-Apply projection is still unavailable without a frozen authorized manifest.
- Turn 08 W17 follow-up: private candidate impact now lists **only registered public Reader routes** and marks missing Brain Network / Flashcard detail and Brain/Assessment Compare routes honestly. A read-only witness checks existing public Brain/Assessment roots via canonical public selectors, including the old and proposed parents of a retargeted relation, without exposing drafts or granting publication.
- Public Search now disambiguates exact Brain/Assessment aliases present in already visible rights-cleared search results, reporting capped pages as incomplete and rendering Persian links to the distinct public identities. Uses already prefetched payloads to preserve the historical 13-query budget; no extra alias SQL queries. Final local QA: SQLite Atlas 1,248 (1,221 PASS/27 SKIP), PostgreSQL17 211/211 PASS, Chrome 32/32 PASS (3 screenshots, 0 JS errors).
- Durable job queue with leases, fenced retries, queue triage, worker-poll evidence and receipt-drift detection.
- Release-readiness API and fail-closed `cms_release_gate` CLI.
- P20 model/content/governance inventory and migration, FK, UNIQUE and NOT NULL integrity gates.
- P22 release handoff, deployment preparation, rollback runbook and owner acceptance checklist.

### Changed

- Public readers fail closed on stale reviews, revoked rights, archived sources, restricted text or restricted metadata.
- Restricted Symptom descriptions are redacted from Disorder detail instead of only from Symptom endpoints.

### Fixed

- W13-02: ETag changes on relevant source/right/context drift, repeated identical source submissions do not generate duplicate revisions, source removal without a real reason is rejected, and a failed AuditEvent insert rolls back the whole evidence revision.
- W13-02: Persian Learning Evidence UI refetches after parent content saves, discards stale asynchronous responses, protects both staged/unadded inputs and changed source locators from unintended navigation, and reuses current source/rights state during history pagination.
- W13-01: Admin Distortion Practice snapshots and simulations now revalidate active target/choice Concept dependencies after subtype and active-state drift and deny invalid previews without writing learner history.
- Turn 08 W16-00 (F03): P16 Learning publication dependency fingerprints now include Concept `subtype` even without an `updated_at` change; invalid target/active choice Concept types reject stale preparation while preserving historical choices.
- Turn 08 W16-00 follow-up: inactive historical choices remain fingerprinted without incorrectly blocking new preparation when current options are eligible.
- Turn 08 W16-01 follow-up: immutable Selection snapshots now invalidate on ReviewTask version/decision-context drift and Learning claim evidence/source metadata/rights drift.
- 2026-11-13: Allow fresh reviews for withdrawn case revisions and unblock review renewal after source changes while retaining stale-manifest and MFA gates.
- 2026-11-13: Expose case reinstatement to authorized administrators and refresh publication plan and revision-history statuses after actions.
- Withdrawn case revisions can be reinstated through a fresh, separately approved and MFA-guarded plan, preserving the original publication timestamp and historical attempts.
- Learning previews and preparation reject whitespace-only active choices.
- Preparation dossiers become stale when a learning item or its dependency loses public visibility.
- Physical foreign-key, uniqueness and idempotency-key nullability drift is reported as a release blocker instead of silently accepted.

### Security

- 2026-11-21: Upgrade pinned Next.js from `16.4.3` to `16.4.6` (including the npm lockfile) to address all five then-open GitHub Dependabot alerts affecting Next.js on `main` (2 critical, 1 high, 2 moderate). Local `npm audit --audit-level=low` now reports **0 vulnerabilities**. Alert closure on the default branch must be verified after the actual merge and Dependabot re-scan; this code change is not a release or production deployment.
- Public rights scopes are applied consistently across list, detail, search, graph and nested serializers, including embedded Symptom text.
- Publication actions require a live admin session, capability checks, independent approval where policy requires it, and single-use MFA step-up bound to the manifest.
- No scientific, legal or rights approval is fabricated by fixtures or tests.

### Known limitations

- Portable citation/provenance transfer v2 remains explicitly **DESIGN_ONLY**, pending verified cross-environment SourceReference identity mapping and owner/legal permission for source-derived private locators. Existing v1 transfer continues to reject source-bound exports with 409 rather than silently lose provenance.
- P16 F03 subtype drift is fixed and covered by focused SQLite regression in Turn 08; full-suite/PostgreSQL and external publication acceptance remain independent.
- W17 candidate preview and its field-name-only impact map are **private only**; public post-Apply Search/Graph/Compare projection parity and a rights-cleared frozen manifest still need independently authorized implementation. Scoped exact-alias ambiguity does not imply global cross-domain identity resolution.
- Generic multi-domain publication (Learning/Brain/Assessment apply, receipts, recovery) is incomplete; only case publication has the full local path.
- Real scientific/rights attestations, retention/legal-hold policy, representative backup/restore, target TLS/secrets, hosted CI and per-model end-to-end acceptance remain open.
- No v1.0.0 tag, release, deployment or public publication has been performed.
