# Full Multilingual V2 — Activation and ACTIVE Report

**Result:** ACTIVE NOT GRANTED — GOVERNED ROLLBACK PREREQUISITE BLOCKED

## 1. Pre-activation state

The authorized target exists at:

    scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db

Read-only preflight confirms:

| Field | Value |
| --- | --- |
| Build run | 0b04f05c-a3d5-5879-b878-cd5f8e84ff2f |
| Build state | ready |
| Profile fingerprint | 51eb57f1f252d4e3e771668be8a70316303ede40c97cf0d3d25f7d20ed728034 |
| Vector space | 7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7 |
| SQLite integrity | ok |
| Foreign-key errors | none |
| V2 alias sets | 0 |
| Active V2 aliases | 0 |

The four governed generations are all ready, complete, checksum-valid, and bound to the specified profile and vector space:

| Capability | Generation ID | Checksum |
| --- | --- | --- |
| representation_derivation_v2 | 81f673bb-665d-591a-b12b-472ff3e39b7c | d08a748116bc106f499c4a59f1df85d86907741035be10aa5995eb2d55234335 |
| language_text_v2 | a7220adf-202c-536e-8e7c-c09d4d4c563f | 1aa2374437c72ef8f3bf23ba9cc09e65b8d6e4aa2f4d0c0b645f60a458b0f3a8 |
| multilingual_embedding_v2 | 62243160-bed5-5064-a664-815984232e31 | 3051a749bfdfe41a83e44da4ec60cd3e1df18619dee9ff3135ebd3373bfcba30 |
| multilingual_vector_v2 | 2b26443e-bb99-5bf8-a4af-a01ba99af8ce | 3051a749bfdfe41a83e44da4ec60cd3e1df18619dee9ff3135ebd3373bfcba30 |

V1 active-index rows were read and retained. No V1 alias, database, vector space, corpus object, model artifact, OCR/Vision evidence, or frozen evidence was changed.

## 2. Activation authorization and atomic-promotion audit

No typed V2 activation authorization artifact exists. The existing V2 build authorization is deliberately BUILD-only and cannot be reused for activation.

More importantly, the repository's existing atomic activation implementation requires both:

1. exactly four complete READY target generations; and
2. exactly four distinct, retained, complete, profile-compatible READY rollback generations.

This is enforced by SQLiteMultilingualStore.promote_multilingual_v2_alias_set and by the V2 readiness projection. It requires a rollback alias-set digest binding the complete rollback set before promotion.

This is the first V2 build. There is no prior V2 alias set and therefore no retained prior V2 four-generation rollback target. The current target generation set cannot truthfully be supplied as its own rollback set: that would make rollback a no-op, violate the retained-prior-target contract, and falsely satisfy the V2 readiness predicate.

Creating a typed activation artifact without a valid rollback binding would be a false authorization. Modifying the promoter to accept a missing or self-referential rollback target would weaken the approved atomic activation and rollback invariant. Neither action was taken.

## 3. Why ACTIVE cannot be established

The migration plan and V2 readiness contract require an atomic alias set with a retained, compatible rollback target. The actual database has:

    multilingual_v2_alias_sets = 0
    active_multilingual_v2_alias_set = 0

Accordingly:

- active_alias_set_atomic cannot be true;
- active_alias_matches_ready_set cannot be true;
- rollback_metadata_valid cannot be true;
- V2_ACTIVE cannot be truthfully projected.

The build remains READY. This is a contract/lifecycle blocker, not a quality, provider, corpus, language, representation, vector, provenance, or authorization failure.

## 4. Tests and static validation

| Check | Result |
| --- | --- |
| Full V2 storage/readiness/build authorization tests | PASS: 30 tests |
| Ruff on activation-relevant modules | PASS |
| Strict mypy on activation-relevant modules | PASS |
| compileall | PASS |
| git diff --check | PASS |

Pytest emitted the existing Windows temporary-cache access warning. It did not affect test results.

## 5. Protected-state verification

No activation transaction was attempted. Therefore no V2 alias, active-generation row, activation authorization, runtime registration, capability-discovery state, or exposure state was created.

The previous READY protected hashes remain governing evidence:

- Golden Dataset composite: 32c10db5bbdeddf4fd07aa37eeb04c234173e25293dcba3f9ac70b22e758330f
- manuscript.pdf: 31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085
- Ramayana PDF: 759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75
- Frozen multimodal DB: 18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d
- Frozen manifest: 17977efc87d3d95bb1e2e6e6c8025e78b63a4c3a0a301f98869b44724fef5a8f
- WP-10 DB: 8ffbb367b35a313c8866e89e21f499aeef92153d5ef6e57d362208f0c05bca0d
- V1 DB: 861c0f1bc50894fadf2eba6088bcadf68083f3a7043e44d20a3583419c84b00f

## 6. Final lifecycle

    DECLARED: PASS
    IMPLEMENTED: PASS
    CONFIGURED: PASS
    BUILDABLE: PASS
    READY: PASS

    ACTIVE: FALSE
    EXPOSED: FALSE
    EVALUATED: FALSE
    VERIFIED: FALSE
    CERTIFIED: FALSE

No retrieval evaluation, Decision-7, WP-16 run, benchmark, reranker-quality evaluation, capability exposure, or certification occurred.

## 7. Exact next prerequisite

A governance decision is required before activation can proceed:

- authorize and define first-V2-activation rollback semantics that are genuinely safe and compatible with the existing atomic V2 alias contract; or
- build and retain a second complete, compatible V2 generation set to serve as the prior/rollback target, then create a typed activation authorization binding the exact target and rollback sets.

Until one of those is completed, V2 activation is correctly fail-closed.
