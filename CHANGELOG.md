# Changelog

All notable changes to Psychology Atlas. This project follows Semantic Versioning; a version listed here is not released until an authorized tag and GitHub Release exist.

## [Unreleased] — v1.0.0 (Admin CMS)

### Added

- Capability-based Admin CMS with MFA, revocable sessions, append-only audit, permission-aware Persian/RTL navigation and owner/curator/delegate roles.
- Canonical editors and governance for core content, concepts, DSM, therapy, history, Brain, Assessment, Learning, cases and privacy operations.
- Source and rights governance with scoped material/use decisions, evidence, expiry, review and public-read enforcement.
- CaseRevision publication workflow: review, frozen manifest, independent approval, MFA apply, idempotent receipts, withdrawal and **reinstatement**.
- Immutable P16 preparation dossiers with live dependency, source and rights rechecks for Learning, Brain and Assessment proposals.
- Durable job queue with leases, fenced retries, queue triage, worker-poll evidence and receipt-drift detection.
- Release-readiness API and fail-closed `cms_release_gate` CLI.
- P20 model/content/governance inventory and migration, FK, UNIQUE and NOT NULL integrity gates.
- P22 release handoff, deployment preparation, rollback runbook and owner acceptance checklist.

### Changed

- Public readers fail closed on stale reviews, revoked rights, archived sources, restricted text or restricted metadata.
- Restricted Symptom descriptions are redacted from Disorder detail instead of only from Symptom endpoints.

### Fixed

- Withdrawn case revisions can be reinstated through a fresh, separately approved and MFA-guarded plan, preserving the original publication timestamp and historical attempts.
- Learning previews and preparation reject whitespace-only active choices.
- Preparation dossiers become stale when a learning item or its dependency loses public visibility.
- Physical foreign-key, uniqueness and idempotency-key nullability drift is reported as a release blocker instead of silently accepted.

### Security

- Public rights scopes are applied consistently across list, detail, search, graph and nested serializers, including embedded Symptom text.
- Publication actions require a live admin session, capability checks, independent approval where policy requires it, and single-use MFA step-up bound to the manifest.
- No scientific, legal or rights approval is fabricated by fixtures or tests.

### Known limitations

- Generic multi-domain publication (Learning/Brain/Assessment apply, receipts, recovery) is incomplete; only case publication has the full local path.
- Real scientific/rights attestations, retention/legal-hold policy, representative backup/restore, target TLS/secrets, hosted CI and per-model end-to-end acceptance remain open.
- No v1.0.0 tag, release, deployment or public publication has been performed.
