# Full Multilingual V2 — First Activation Rollback Remediation and ACTIVE Report

**Result:** FIRST V2 ACTIVATION COMPLETE — ACTIVE; NOT EXPOSED

## 1. Original blocker and forensic conclusion

The former promoter required a distinct four-generation V2 rollback set for every activation. That is correct for a V2 upgrade, but cannot be literally satisfied by the first V2 activation because no prior V2 serving state exists.

The repository migration plan separately identifies the valid pre-exposure recovery path: abandon or disable the isolated V2 state while preserving the V1 baseline. V1 cannot be a V2 rollback target: its generations, profiles, and vector spaces remain separate. The actual safety invariant is therefore:

> An activation must be atomic and have a governed recovery path to the prior serving state. For first V2 activation, that recovery is atomic V2-alias deactivation; for subsequent V2 upgrades, it is atomic restoration of a retained prior V2 alias set.

No second V2 index was necessary.

## 2. Governed first-activation contract

A typed activation authorization was added and validated:

| Field | Value |
| --- | --- |
| Authorization ID | 3d8e50f6-1dda-5abf-89b9-c04f2ffd6a43 |
| Authorization digest | 52ae49cbf5958e6d3760a60846ab98cfaf90174ef4558f1f2441288fd83b8521 |
| Activation mode | first_v2_activation |
| Recovery mode | deactivate_v2_alias_set |
| Build run | 0b04f05c-a3d5-5879-b878-cd5f8e84ff2f |
| Profile fingerprint | 51eb57f1f252d4e3e771668be8a70316303ede40c97cf0d3d25f7d20ed728034 |
| Vector space | 7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7 |

First V2 activation permits no prior V2 alias and names no rollback generations. It never accepts a self-referential rollback set. Its recovery digest binds only V2 deactivation and explicitly records that V1 aliases are not mutated.

Subsequent V2 upgrades remain unchanged in principle: they require an existing active V2 alias, exactly four distinct retained complete READY rollback generations, and a digest binding that prior V2 set. The promoter rejects an upgrade with no active V2 alias.

## 3. Implementation

Added:

- typed V2 activation authorization contract and JSON Schema;
- bounded manifest-consuming activation operator and fixed-input activation script;
- V2-only activation audit table;
- explicit first-activation recovery mode;
- atomic V2 deactivation method for first-activation rollback;
- active V2 generation-set resolver in canonical dependency order;
- SQLite schema migration 16.

Changed:

- V2 readiness rollback model now distinguishes prior_v2_alias_set from deactivate_v2_alias_set.
- V2 promoter requires typed authorization for all activation modes.
- Existing complete-generation promotion tests now cover first activation, self-referential rejection, and subsequent upgrade semantics.

No retrieval, provider, corpus, model, MCP, or evaluation code was changed.

## 4. Pre-activation validation

The isolated target was verified before mutation:

    scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db

- build run state: ready;
- SQLite integrity: ok;
- foreign-key errors: none;
- no active V2 alias before activation;
- four exact READY generation IDs and checksums matched the typed authorization;
- complete coverage, provenance, and authorization-compatible manifests matched;
- embedding vector space matched the canonical V2 identity;
- no V1 database or protected target was accepted.

The four activated generations are:

| Capability | Generation ID | Checksum |
| --- | --- | --- |
| representation_derivation_v2 | 81f673bb-665d-591a-b12b-472ff3e39b7c | d08a748116bc106f499c4a59f1df85d86907741035be10aa5995eb2d55234335 |
| language_text_v2 | a7220adf-202c-536e-8e7c-c09d4d4c563f | 1aa2374437c72ef8f3bf23ba9cc09e65b8d6e4aa2f4d0c0b645f60a458b0f3a8 |
| multilingual_embedding_v2 | 62243160-bed5-5064-a664-815984232e31 | 3051a749bfdfe41a83e44da4ec60cd3e1df18619dee9ff3135ebd3373bfcba30 |
| multilingual_vector_v2 | 2b26443e-bb99-5bf8-a4af-a01ba99af8ce | 3051a749bfdfe41a83e44da4ec60cd3e1df18619dee9ff3135ebd3373bfcba30 |

## 5. Atomic activation and recovery evidence

The promoted V2 alias-set digest is:

    b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0

One transaction wrote the V2 alias record, the active V2 alias pointer, and the typed activation record. No V1 active-index-generation row was altered.

A controlled isolated rollback test was executed:

1. The active V2 set resolved to all four canonical generations.
2. The typed first-activation recovery atomically deleted only the V2 active alias.
3. The V2 resolver returned no active V2 set.
4. The same typed authorization atomically restored the approved V2 set.
5. The final active set again resolves to exactly the four authorized generations.

The transaction cannot persist a partial four-generation V2 set. The original attempt before schema migration failed before commit because the new audit table was absent; it created no alias. Schema migration 16 was added solely to the isolated V2 target, then the governed activation succeeded.

## 6. Runtime and exposure boundary

The V2 storage resolver resolves the active set through the governed V2 alias mechanism and returns the canonical representation → sparse → embedding → vector order. No generation ID is hardcoded into retrieval execution.

V2 public capability discovery, MCP, HTTP, SSE, and stdio exposure were not changed or invoked. Therefore:

- ACTIVE is backed by the exact isolated alias set and resolver;
- EXPOSED remains false;
- no model-supported language is advertised as verified or certified;
- no transport or retrieval evaluation was executed.

## 7. Validation

| Validation | Result |
| --- | --- |
| Focused V2 lifecycle, authorization, storage, projection, runtime and scope tests | PASS: 54 tests |
| Ruff | PASS |
| Strict mypy | PASS |
| compileall | PASS |
| Activation authorization JSON Schema and readiness schema validation | PASS |
| git diff --check | PASS |

Pytest emitted the existing Windows temporary-cache access warning. It did not affect test results.

## 8. Protected-state verification

Before/after content hashes match for:

- Golden Dataset composite;
- manuscript.pdf;
- Ramayana PDF;
- frozen multimodal database and manifest;
- WP-10 database;
- V1 database;
- BGE-M3 snapshot;
- BGE reranker snapshot.

V1 active-index-generation count remains 47. V2 has one active V2 alias-set record and zero V2 rows in the V1 active-index-generation table, preserving V1/V2 lifecycle and vector-space isolation.

Only isolated V2 activation metadata, the V2-only active alias, and V2 schema version 16 changed.

## 9. Final lifecycle

    DECLARED: PASS
    IMPLEMENTED: PASS
    CONFIGURED: PASS
    BUILDABLE: PASS
    READY: PASS
    ACTIVE: PASS

    EXPOSED: FALSE
    EVALUATED: FALSE
    VERIFIED: FALSE
    CERTIFIED: FALSE

No retrieval evaluation, Decision-7, WP-16, benchmark, qrel work, ranking metric, reranker-quality run, public transport exposure, or certification occurred.

## 10. Next authorized action

A separate controlled ACTIVE → EVALUATED authorization is required before any retrieval behavior or quality assessment is run. This report grants no evaluation, exposure, verification, or certification authority.

