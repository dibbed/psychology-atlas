## Summary

Describe the change and why it is needed.

## Validation

- [ ] Relevant backend tests pass
- [ ] Frontend typecheck/build pass when frontend code changes
- [ ] `git diff --check` passes
- [ ] No local secrets, database files, credentials, or machine-specific paths are introduced

## Psychology Atlas integrity checks

- [ ] Scientific/provenance semantics are unchanged, or the change is source-backed and documented
- [ ] Educational content is not presented as diagnosis, treatment advice, or clinical-competence assessment
- [ ] Historical/revision-bound user data remains backward-compatible when schema or case logic changes
- [ ] API/auth changes preserve user ownership and cross-user isolation

## Release/documentation impact

- [ ] README / PROJECT_SPEC / BUILD_MANIFEST updated when release behavior changes
- [ ] Migration included when the Django model state changes
- [ ] Release or handoff documentation updated when crossing a version boundary
