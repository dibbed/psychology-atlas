# v0.9.2C controlled Brain publication — 2026-10-01

The selected corpus can be used publicly and potentially commercially. Its anatomical authority is the **official University of Washington FMA 5.1.0**, independently parsed and checked, rather than the Allen annotation hierarchy with substituted citations. The old source-specific research remains unchanged in v0.9.2B; no exact spatial equivalence to Allen/HBAO is asserted.

PR #39 was squash-merged at `75db336d2c6047b8e6c80adc708d0666cf83578a` before this branch started. Its current-head CI, both CodeQL analyses and Dependency Review passed; the fresh review found no further major issues and all eleven review threads were resolved.

## Exact approval artifacts

| Artifact | SHA-256 |
| --- | --- |
| Original Web input | `a0baf10cbd21a26651ba1df68b3bc3d4553455e1eb8f6ea69e791c503d7dd321` |
| Preserved v0.9.2B reviewed dossier | `738b3ce478b0dd9f9213f5d8b8aba002701972fc2ab39eaa9263a81ca5893213` |
| [v0.9.2C publication dossier](psychology_atlas_brain_publication_dossier_v0.9.2c.json) | `50b6e33e25b76a77b6ef735503487ac5fab7832d7474e45ad6beb7acdc25a557` |
| [Publication manifest](publication_manifest.json) | `3f3538fd4f8195b0dbe1c8631d61674cd84c629e7bea1018ba29b91329a3920d` |

Version: `0.9.2c-fma510-2026-10-01`. Approval is limited to these exact bytes, version, per-record scientific review and rights dispositions. A new corpus requires a separately reviewed change to the artifacts and code pins. Portable sources retain negative identity placeholders; positive target PKs are generated separately and never committed as portable identities.

## Candidate reconciliation

| Category | Approved for publication | Previous deferred items cleared |
| --- | ---: | ---: |
| Verified source identities | 25 | 0 |
| Anatomy | 87 | 68 |
| Networks | 7 | 0 |
| Aliases | 50 | 1 |
| External identifiers | 94 | 0 |
| Hierarchy | 70 | 35 |
| Network memberships | 0 | 0 |
| Functional associations | 0 | 0 |

Of the previous **375** deferred candidates, **104** clear the gates after independent recuration; **271** remain deferred: seven anatomy identities, 75 Allen-specific aliases, 150 Allen/HBAO identifiers, and 39 old hierarchy assertions. Rights-rejected count is **0**: ambiguous grants are retained as deferred research, not declared prohibited. The anatomy clearance means independently verified **generic FMA structural identities**, not clearance of the old atlas annotation extents or coordinates.

All 420 previous retained candidates have a disposition in the manifest. **184 independently added candidates** comprise 19 anatomy entities, 42 aliases, 87 native FMA identifiers, 35 newly selected hierarchy claims and one verified source. Total ledger: **604 = 333 APPROVED_FOR_PUBLICATION + 271 DEFERRED**. Canonical Brain records: **308**, plus **25** verified SourceReference identities and their evidence links. Deferred records exist outside the staging publication record list and remain traceable to the byte-preserved B dossier.

The additional major anatomy includes forebrain, hindbrain, brainstem, adult midbrain/medulla, cerebral hemisphere, hippocampus/hippocampus proper, and the ventricular system, lateral/third/fourth ventricles and cerebral aqueduct. Smaller bridge identities support explicit nucleus/cortical containment. No parcel-count expansion or visual asset is included.

## Scientific review and rights

The primary [official FMA repository](https://github.com/uw-sig/FMA/tree/c6f70808ba2859b88cb0b8362c34fa9017c6f96a) contains FMA 5.1.0 and an explicit [CC BY 4.0 grant](https://raw.githubusercontent.com/uw-sig/FMA/c6f70808ba2859b88cb0b8362c34fa9017c6f96a/LICENSE). The ontology Git LFS digest is `beb3dc47979ad5434ef70fd02af4307f147f2023f7d8c2c57103b995191194c3` (208,047,132 bytes). The license digest is `7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661`. [HRA raw-asset metadata](https://cdn.humanatlas.io/digital-objects/vocab/fma/v5.1.0/metadata.json) independently records FMA 5.1.0 and CC BY 4.0, but its OWL asset has different bytes; the publication selection uses the official upstream file. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) permits commercial sharing/adaptation with attribution, a change notice and no additional restrictions on licensed material.

[OBO Foundry's FMA entry](https://obofoundry.org/ontology/fma.html) still links an old CUSTOM license/install page containing a **2006 draft**. This historical pointer does not replace the current rightsholder's explicit grant on the pinned official version. The [2014 FMA neuroanatomy paper](https://doi.org/10.1186/2041-1480-5-1) also describes an earlier CC BY 3.0 release; it is corroboration, not the license used for these exact new bytes. The unresolved Allen/HBAO commercial-use issue is preserved, not declared resolved for those data.

Every published anatomical entity has an exact native FMA identity, kind, source scope, laterality and claim note. Generic FMA classes retain `not_established` laterality; the two source-explicit subthalamic nuclei remain left and right. This distinguishes generic classes from bilateral coordinate masks. All four previous independently attested Persian names and one Persian alias are retained; **83 anatomy and seven network names remain untranslated**. Attestation is not a claimed national nomenclature or specialist certification.

The **70 links form a partial forest with 17 roots**. Exact direct restrictions, qualified inherited restrictions and transitive part paths are recorded individually. Only `regional_part_of` and `constitutional_part_of`, source specializations of `part_of`, provide containment. `is_a` alone and inversion of existential `has_part` never prove containment. One active primary parent is selected per child; alternative FMA paths are not treated as competing active parents. Some generic containment is absent from the pinned source, so a missing parent does not imply anatomical independence. Allen's gray/white collection branches are not copied. FMA's broader neuraxis gray/white terms are not silently substituted for brain-only identities. Developmental mesencephalon/myelencephalon equivalence remains deferred.

Selected synonyms are exact FMA annotations reviewed for scope. Contradictory Genu/Rostrum annotations, historical `archistriatum`/`paleostriatum`, cortex-versus-whole-lobe synonyms and source-specific acronyms are not published. No universal inter-atlas equality is asserted.

Seven pinned Yeo/CBIG cortical network definitions retain their method, sample, version and limitations. No anatomical crosswalk or membership is supplied. Functional evidence remains in deferred research; activation is not exclusive localization and association is not causation or diagnosis. New rights research also checked Uberon (release 2026-06-23, actual ontology version IRI 2026-06-19) and FIPAT's current CC BY-SA 4.0 lists; neither is mixed into this primary hierarchy. Meshes, figures and coordinates remain outside the publication rights grant. See [third-party notices](THIRD_PARTY_NOTICES.md).

## Controlled operation

Back up the configured target database and apply existing migrations first. This phase adds **no schema migration**. The command accepts only the checked-in approved dossier and manifest, verifies their exact pins before writes, resolves bibliographic identity without silent merges, runs the existing staging validator, and writes in dependency order inside one transaction. The existing global Brain curation lock serializes duplicate publication and competing curator/source changes on PostgreSQL; SQLite uses the established IMMEDIATE transaction mode.

From `backend`, with the intended `SQLITE_PATH` or PostgreSQL environment configured:

```sh
python manage.py publish_curated_brain --expected-dossier-sha256 50b6e33e25b76a77b6ef735503487ac5fab7832d7474e45ad6beb7acdc25a557 --expected-manifest-sha256 3f3538fd4f8195b0dbe1c8631d61674cd84c629e7bea1018ba29b91329a3920d --dry-run
python manage.py publish_curated_brain --expected-dossier-sha256 50b6e33e25b76a77b6ef735503487ac5fab7832d7474e45ad6beb7acdc25a557 --expected-manifest-sha256 3f3538fd4f8195b0dbe1c8631d61674cd84c629e7bea1018ba29b91329a3920d --apply
python manage.py verify_brain_publication
python manage.py audit_brain_atlas --json
python manage.py verify_research_datasets
```

Dry-run is the default and rolls back sources, archive, pointers and canonical rows. `--resolved-output` may write a **new**, target-specific derivative outside version control; dry-run allocations are tentative. Export uses exact UTF-8 LF bytes so a repeat importer is byte-idempotent on Windows. Apply repetitions verify the immutable receipt and **every canonical field/evidence link** and perform no writes. Conflicting data fail closed rather than being overwritten or mass-reviewed. A promotion pointer alone cannot exempt a staging conflict; exemptions require exact pinned archive and complete manifest/canonical reconciliation. The ordinary `promote_brain_staging` remains read-only with `canonical_writes=0`.

Every reused source must exactly match all approved bibliographic fields, including organization, authors, year and source type; blank existing values fail closed. Receipt verification repeats this check, so later source metadata changes invalidate the receipt.

`verify_brain_publication` checks actual database counts, receipt, source/provenance, review debt, SQLite integrity/foreign keys, anonymous API and established query budgets. It does not publish or repair. Publishing to this configured database does not by itself prove deployment to an external server.

## Verification

The new tests cover changed hashes, source conflicts/duplicates, dry-run rollback, late atomic failure, exact repeated execution, forged pointers, curator changes, real-corpus API/search/pagination/exclusions/provenance and concurrent PostgreSQL duplication. The full v0.9.1/v0.9.2 regressions remain in the gate. Persistent PostgreSQL worker connections are explicitly closed at test completion so database teardown works with `CONN_MAX_AGE=60`.

Measured real-corpus query counts are recorded in the PR after final validation; original synthetic limits remain list/search **4**, detail **11**, parent/kind/laterality filters **5**. CI publishes only into its disposable database, verifies the actual public API and runs the PostgreSQL focused publication/concurrency suite. No production credentials, database, resolved positive-PK artifact or full ontology cache is tracked.
