# Psychology Atlas: Agent Documentation Policy

## Single canonical external project reference

- The only standalone project-wide master plan, status report, and cross-version handoff file in Downloads is:
  `C:\Users\Meliodas\Downloads\Psychology_Atlas_Master.md`.
- When asked to update the overall project handoff, status, roadmap, or master documentation, **edit that exact file in place**, maintaining the filename across releases. Do not create dated, version-suffixed, or "final" alternative master Markdown documents in Downloads.
- Update the active status at the top of that file with a dated, source-checked snapshot. Do not present historical appendix text as live implementation evidence.
- Source of truth for implementation: actual repository, Git state, schema/migrations, database, current tests, and current CI/release evidence. Existing archived design is intent, not proof of implementation.
- This rule only applies to standalone project-wide master documentation in Downloads. Keep source code, migrations, milestone handoffs and other technical docs **inside this repository** under their established paths. Do not delete/rename them to comply with the single-master rule.
- Preserve existing worktree changes and scientific, privacy, history, review and publication invariants. Never infer permission to commit, push, merge, migrate, release, or deploy from a handoff.
- The initial consolidation on 2026-10-31 copied and verified nine historical Downloads Markdown documents into the canonical master appendix before retiring the redundant standalone copies.
