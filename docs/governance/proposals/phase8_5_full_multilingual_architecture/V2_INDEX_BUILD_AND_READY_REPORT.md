# Full Multilingual V2 — Index Build and READY Report

**Status:** GOVERNED BUILD COMPLETE — READY FOR THE NEXT CONTROLLED PHASE

This report records the controlled BUILDABLE → READY operation. It is not an activation, exposure, retrieval-quality evaluation, or certification record.

## 1. Build and authorization identity

| Field | Value |
| --- | --- |
| Build run | 0b04f05c-a3d5-5879-b878-cd5f8e84ff2f |
| Typed authorization | 0d7a1648-b585-54e8-b80a-129e6409b6d6 |
| Target | scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db |
| Target SHA-256 after idempotent rerun | 4511512ea42b8c8569ff4ad168c1e8a90811ef0034c5540bc1548023b0f65d64 |
| Canonical V2 vector space | 7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7 |
| Source frozen database SHA-256 | 18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d |
| Golden Dataset digest | 32c10db5bbdeddf4fd07aa37eeb04c234173e25293dcba3f9ac70b22e758330f |

The bounded operator consumed typed authorization and governed manifests before source-evidence enumeration. It rejected arbitrary target, profile, run, generation, and vector-space inputs. The target was absent, with no target WAL or SHM, before creation and has no V2 alias promotion after completion.

## 2. Provider and model controls

| Operation | Model | Revision | Result |
| --- | --- | --- | --- |
| Embedding | BAAI/bge-m3 | 5617a9f61b028005a4858fdac845db406aefb181 | PASS: local initialization; 1024 dimensions; finite normalized vectors; ordered batches |
| Reranking | BAAI/bge-reranker-v2-m3 | 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e | NOT RUN for ranking: not required for index construction; V2 semantic-text contract remains enforced |

The build used existing local artifacts only. No model was downloaded, replaced, or modified.

## 3. Corpus, observations, and representation accounting

The isolated target is an SQLite online backup of governed frozen evidence, followed only by additive V2 tables and V2 generation rows. This preserves canonical/OCR/Vision lineage without reparsing or changing the Golden Dataset.

| Item | Expected | Actual | Result |
| --- | ---: | ---: | --- |
| Documents / versions | 44 / 44 | 44 / 44 | PASS |
| Canonical chunks | 2,658 | 2,658 | PASS |
| OCR regions | 402 | 402 | PASS |
| Vision derivations | 463 | 463 | PASS |
| Governed evidence observations | 3,523 | 3,523 | PASS |
| V2 language observations | 3,523 | 3,523 | PASS |
| Script observations | 3,523 | 3,523 | PASS |
| Representation observations | 3,523 | 3,523 | PASS |
| Explicit representation-dependent exclusions | 504 | 504 | PASS |
| Eligible sparse/vector evidence | 3,019 | 3,019 | PASS |

The 504 exclusions are explicit and provenance-bound: 502 legacy-font canonical Ramayana chunks and 2 PDF-encoding-anomaly chunks. They were not rewritten, transformed, relabelled, or discarded. Independently eligible OCR and Vision evidence remains traceable.

manuscript.pdf and Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf remained exactly as governed source evidence.

## 4. Approved V2 generations

| Capability | Generation ID | Expected / succeeded / failed / skipped | State | Checksum |
| --- | --- | --- | --- | --- |
| representation_derivation_v2 | 81f673bb-665d-591a-b12b-472ff3e39b7c | 3523 / 3523 / 0 / 0 | ready | d08a748116bc106f499c4a59f1df85d86907741035be10aa5995eb2d55234335 |
| language_text_v2 | a7220adf-202c-536e-8e7c-c09d4d4c563f | 3019 / 3019 / 0 / 0 | ready | 1aa2374437c72ef8f3bf23ba9cc09e65b8d6e4aa2f4d0c0b645f60a458b0f3a8 |
| multilingual_embedding_v2 | 62243160-bed5-5064-a664-815984232e31 | 3019 / 3019 / 0 / 0 | ready | 3051a749bfdfe41a83e44da4ec60cd3e1df18619dee9ff3135ebd3373bfcba30 |
| multilingual_vector_v2 | 2b26443e-bb99-5bf8-a4af-a01ba99af8ce | 3019 / 3019 / 0 / 0 | ready | 3051a749bfdfe41a83e44da4ec60cd3e1df18619dee9ff3135ebd3373bfcba30 |

All four coverage manifests are complete. The build-run ledger is ready. No V2 active-index-generation record or V2 alias set exists.

## 5. Integrity, recovery, and idempotency

- SQLite integrity check is ok; foreign-key audit returned no rows.
- No orphaned V2 observations, projection rows, embeddings, or coverage manifests were found.
- Every V2 embedding is bound to the canonical V2 vector-space identity and passed finite-value, dimension, and L2-normalization validation.
- The first run stopped safely after embeddings when its audit decoder found an envelope-key compatibility defect (payload, not root). No alias was promoted. The decoder was corrected; the same typed run resumed and reused all 3,019 committed embeddings without recomputation.
- A subsequent governed rerun preserved counts, generation IDs, checksums, and no-duplicate invariants. SQLite physical bytes changed due to run/checkpoint timestamps and layout; semantic governed state is idempotent.

## 6. Security and protected-state verification

Authorization was checked from typed build authorization before source evidence enumeration. Scope authorization was not weakened. V1 and V2 vector spaces remain separated.

| Protected artifact | SHA-256 | Result |
| --- | --- | --- |
| Golden Dataset composite | 32c10db5bbdeddf4fd07aa37eeb04c234173e25293dcba3f9ac70b22e758330f | PASS |
| manuscript.pdf | 31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085 | PASS |
| Ramayana PDF | 759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75 | PASS |
| Frozen multimodal DB | 18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d | PASS |
| Frozen manifest | 17977efc87d3d95bb1e2e6e6c8025e78b63a4c3a0a301f98869b44724fef5a8f | PASS |
| WP-10 DB | 8ffbb367b35a313c8866e89e21f499aeef92153d5ef6e57d362208f0c05bca0d | PASS |
| V1 DB | 861c0f1bc50894fadf2eba6088bcadf68083f3a7043e44d20a3583419c84b00f | PASS |

The pre-existing frozen -shm sidecar retained the same content hash and size, but its filesystem timestamp changed during read-only SQLite access. Frozen DB and WAL bytes, corpus files, manifests, model snapshots, V1 DB, and WP-10 DB contents are unchanged. This metadata-only side effect is recorded explicitly.

## 7. Validation evidence

| Validation | Result |
| --- | --- |
| Focused V2 / governance / authorization suite | PASS: 71 tests |
| Ruff on changed V2 paths | PASS |
| Strict mypy on changed V2 sources | PASS |
| compileall on changed V2 sources | PASS |
| JSON proposal parsing (24 artifacts) and Draft 2020-12 schema validation (11 schemas) | PASS |
| git diff --check | PASS |

The standard repository-wide 90% coverage gate fails when applied to this focused subset (34.49% aggregate repository coverage) even though all 71 selected tests pass. That is a test-run configuration result, not a V2 test failure. Pytest also emitted a Windows access warning for its temporary cache directory.

## 8. READY gate result

Every mandatory build gate A–U is PASS: authorized isolated target, matching corpus identity, governed count reconciliation, complete observation and exclusion accounting, four complete READY generations, valid checksums and dependencies, provenance and authorization integrity, vector integrity and space isolation, recovery/idempotency, matching profile/build fingerprints, unchanged protected content, and zero alias promotion/runtime exposure.

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

## 9. Remaining limitations and next authorization

This build is not a quality result. Legacy-font canonical evidence remains explicitly excluded pending a separately governed representation transformation profile. No retrieval benchmark, Decision-7 evaluation, WP-16 behavioral run, reranker quality run, active-alias promotion, MCP/HTTP exposure, or certification occurred.

The next action requires separate explicit authorization for a controlled READY → ACTIVE phase. It must validate the runtime readiness projection and atomically promote only approved V2 aliases. This report grants no activation authority.
