# Psychology Atlas — Public Repository Operations

This document records the maintenance and security baseline for the public GitHub repository.

## Repository intent

The repository is public for portfolio, technical review, and project transparency. It is **not open-source software**. No open-source license is granted; publication on GitHub does not grant general reuse, modification, redistribution, sublicensing, or derivative-work rights beyond permissions necessarily provided by GitHub's platform terms.

## Main-branch workflow

1. Start from an up-to-date `main`.
2. Create a focused feature/fix/chore branch.
3. Commit logically scoped changes.
4. Push the branch and open a pull request.
5. Required CI/security checks must pass.
6. Resolve review conversations.
7. Merge through the protected `main` branch.
8. Delete the merged branch.

Direct feature work on `main`, force-pushes, and history rewrites are not part of the normal workflow.

## Automated checks

### CI

`.github/workflows/ci.yml` runs on pull requests and `main` pushes:

- Django system check
- migration drift check
- migration application
- deterministic seed smoke
- clinical-case graph/runtime audit
- full backend test suite
- Python compileall and `pip check`
- frontend `npm ci`
- TypeScript typecheck
- Next.js production build
- `npm audit --audit-level=high`
- repository hygiene checks for tracked secrets/local databases/private keys/machine-specific absolute paths
- verification that the public usage/no-license notice remains present

### Dependency Review

`.github/workflows/dependency-review.yml` reviews dependency diffs on pull requests and blocks newly introduced high/critical vulnerable dependencies.

### CodeQL

`.github/workflows/codeql.yml` scans both Python and JavaScript/TypeScript using the `security-extended` query suite on pull requests, `main` pushes, a weekly schedule, and manual dispatch.

All third-party GitHub Actions are pinned to full commit SHAs. Dependabot tracks GitHub Actions so those pins can be updated by reviewed pull requests rather than floating automatically.

## Dependency maintenance

`.github/dependabot.yml` checks weekly for:

- Python/pip updates under `/backend`
- npm updates under `/frontend`
- GitHub Actions updates under `/`

Automated version-update PRs are limited to minor and patch releases and are grouped to reduce pull-request noise. Major upgrades are intentionally manual because they can change framework/runtime contracts. Dependabot security updates remain enabled independently and may still open the update required to remediate a vulnerability.

## Security reporting

The repository uses `.github/SECURITY.md` and GitHub private vulnerability reporting. Security reports must not be opened as public issues when they contain exploit details or sensitive information.

Expected repository-level controls:

- Dependabot vulnerability alerts
- Dependabot security updates
- secret scanning
- secret-scanning push protection
- CodeQL/code scanning
- private vulnerability reporting

## Releases

Version releases should be tagged only after the release commit is merged into `main` and the release gate is green. Release notes should summarize user-visible behavior, architecture changes, validation, scientific/data-integrity constraints, and known limitations.

## Scientific and educational guardrails

Public-repository automation does not replace the project's scientific review rules:

- `source_checked` is not equivalent to independently reviewed.
- weak or archival provenance stays visibly weak.
- clinical-case scores are educational, not measures of clinical competence.
- Psychology Atlas is not a diagnosis or treatment system.
- content/relation changes must preserve explicit provenance and historical revision integrity.
