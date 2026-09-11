# Full Multilingual V2 — ACTIVE to EVALUATED Report

**Result:** `EVALUATED: FALSE` — evaluation blocked before any query, provider inference, ranking, or metric calculation.

**Date:** 2026-09-01  
**Scope:** controlled ACTIVE-to-EVALUATED preflight only

## 1. Executive determination

The governed V2 alias set is present, internally complete, and resolves to the four approved READY generations. However, the repository does not yet compose that set into a real, public, authorized Full Multilingual V2 application service. Consequently an evaluator cannot use the required production path without either constructing its own dependencies/candidates or calling a provider directly. Both are expressly forbidden by the evaluation contract.

This is an `EVALUATION_HARNESS_ERROR` / runtime-composition blocker, not a retrieval-quality result and not evidence that any language, document, script, or representation is absent or unsupported.

No evaluation case, qrel, query embedding, retrieval request, reranker call, benchmark, or ranking metric was executed.

## 2. Active-state preflight

Read-only inspection of the isolated V2 database at `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` produced:

| Check | Result | Evidence |
| --- | --- | --- |
| SQLite integrity | PASS | `PRAGMA integrity_check = ok` |
| Foreign-key integrity | PASS | `PRAGMA foreign_key_check` returned zero rows |
| Active V2 alias digest | PASS | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` |
| Activation mode | PASS | `first_v2_activation` / `deactivate_v2_alias_set` |
| V1 active-index rows | PASS | 47; V2 uses its separate alias mechanism |
| Active alias membership | PASS | Exactly four governed generation IDs |

The generation records are all `ready`:

| Capability | Generation ID | Items | Checksum |
| --- | --- | ---: | --- |
| `representation_derivation_v2` | `81f673bb-665d-591a-b12b-472ff3e39b7c` | 3,523 | `d08a748116bc106f499c4a59f1df85d86907741035be10aa5995eb2d55234335` |
| `language_text_v2` | `a7220adf-202c-536e-8e7c-c09d4d4c563f` | 3,019 | `1aa2374437c72ef8f3bf23ba9cc09e65b8d6e4aa2f4d0c0b645f60a458b0f3a8` |
| `multilingual_embedding_v2` | `62243160-bed5-5064-a664-815984232e31` | 3,019 | `3051a749bfdfe41a83e44da4ec60cd3e1df18619dee9ff3135ebd3373bfcba30` |
| `multilingual_vector_v2` | `2b26443e-bb99-5bf8-a4af-a01ba99af8ce` | 3,019 | `3051a749bfdfe41a83e44da4ec60cd3e1df18619dee9ff3135ebd3373bfcba30` |

The canonical V2 vector-space identity remains `7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7`.

## 3. Evaluator/runtime parity gate

The V2 evaluation architecture is normative: semantic evaluation must invoke the same public application service as production. It must not directly call providers, construct reranker inputs, select permissive authorization, or synthesize provenance. See `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md`, sections 8–9, and `mnemo.models.multilingual_evaluation.RuntimeParityEvidenceV1`.

Repository inspection established the following:

| Required production component | Current code | Preflight result |
| --- | --- | --- |
| Shared retrieval algorithm | `mnemo.retrieval.full_multilingual_v2.FullMultilingualRetrievalApplicationV2` | Present, but only a dependency-injected class |
| Authorized dense/sparse implementations | `multilingual_dense_v2.py`, `multilingual_sparse_v2.py` | Present as protocol-driven components |
| Advanced retrieval adapter | `FullMultilingualAdvancedSourceV2` | Present, but dependency-injected only |
| Production composition of the application | Repository-wide construction search | **Absent**: the only instantiation is a unit test |
| Runtime selection of active V2 generations for retrieval | `KnowledgeEngine._compose_advanced_retrieval` | **Absent while `v2_exposed` is false**; engine only accepts a caller-supplied source when exposure is already true |
| V2 evaluator using that application | Scripts and `mnemo-core` search | **Absent** |

The active alias resolver exists in `SQLiteMultilingualMixin.resolve_active_multilingual_v2_generation_set`, but there is no production factory that consumes its result, composes the exact active dense/sparse sources, central authorizer, shared candidate builder, public reranker, detector/admission policy, and V2 projector, then provides that application to evaluation.

Constructing those pieces inside a new evaluator would violate the contract's path-parity rule. Querying the V2 tables, calling BGE-M3 or the reranker, or creating candidate text from the evaluator would also violate the explicit evaluation instructions. Therefore evaluation stopped before execution.

## 4. Metrics, cohorts, and failure attribution

| Item | Status | Reason |
| --- | --- | --- |
| Grounded query/qrel construction | NOT RUN | No admissible evaluator/application path |
| Dynamic language/script cohort discovery | NOT RUN | Must be bound to the same active retrieval runtime |
| EN/HI/MR regression | NOT RUN | No quality evaluation was run; this is not a corpus-absence claim |
| Marathi `manuscript.pdf` regression | NOT RUN | The corpus file remains present; no assertion of Marathi absence was made |
| Ramayana legacy representation cohort | NOT RUN | Governed exclusions remain representation-specific, not language-wide |
| OCR/Vision cohorts | NOT RUN | No evaluator execution |
| Recall@1 / Recall@5 / Recall@10 | UNMEASURED | No valid ranked cases; `N=0` is not reported as zero accuracy |
| MRR / nDCG@10 | UNMEASURED | No valid ranked cases |
| Reranker pairwise accuracy | UNVERIFIED | No governed decisive-pair dataset was run |
| Reranker semantic-text invariant | NOT RUN in evaluation | No candidate was constructed; prior contract/unit coverage remains separate |

No `CORPUS_ABSENT`, `PROVIDER_UNSUPPORTED`, `DENSE_MISS`, `SPARSE_MISS`, or `RERANKER_MISS` was emitted. Those claims require execution evidence that was not produced.

## 5. Protected-state verification

Only read-only filesystem inspection and an immutable SQLite URI were used. No evaluation database or write-sidecar was created. The active V2 database was not mutated.

| Protected item | Result | SHA-256 / evidence |
| --- | --- | --- |
| Golden Dataset | PASS | 44 files; governed snapshot composite `32c10db5bbdeddf4fd07aa37eeb04c234173e25293dcba3f9ac70b22e758330f` remains the reference |
| `manuscript.pdf` | PASS | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` |
| Ramayana PDF | PASS | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` |
| Frozen multimodal DB | PASS | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` |
| V1 active aliases | PASS | Still 47 V1 active-index-generation rows; no V2 entry added there |
| Active V2 alias | PASS | Remains the approved digest above; no alias mutation |
| Models | PASS | Not loaded, downloaded, or modified |

The V2 database was opened with SQLite `mode=ro&immutable=1` for the preflight. Its current file hash is `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`.

## 6. Required remediation before evaluation

This is a narrowly scoped implementation prerequisite, not an invitation to expose V2 publicly:

1. Add a governed, internal-only V2 runtime composition/factory that resolves the active V2 alias set and builds `FullMultilingualRetrievalApplicationV2` from the exact active profile, vector space, authorized storage adapters, central authorizer, shared `RerankerCandidateBuilderV1`, public reranker, query-language resolver, admission policy, and advanced projector.
2. Add an internal evaluator entry point that accepts only this application service and emits the required runtime-parity evidence. It must have no direct provider access and no arbitrary candidate-construction facility.
3. Add focused tests proving alias-to-runtime resolution, evaluator/production parity, authorization-before-enumeration, active-set/vector-space rejection, title-only rejection, and fail-closed behavior when the composed V2 service is absent.
4. Obtain a separate controlled authorization to execute grounded cases through that internal service. Keep `EXPOSED` false; no HTTP/MCP/SSE/stdio exposure is required for this internal evaluation route.

After these prerequisites, the next phase may create a disposable evaluation namespace, freeze grounded evidence-level qrels, and execute the active V2 application to produce raw rankings and metrics. It must not rebuild, alter, or reactivate the V2 index.

## 7. Final lifecycle

```text
DECLARED: PASS
IMPLEMENTED: PASS
CONFIGURED: PASS
BUILDABLE: PASS
READY: PASS
ACTIVE: PASS

EXPOSED: FALSE
EVALUATED: FALSE (BLOCKED: no composed, parity-preserving active V2 application)
VERIFIED: FALSE
CERTIFIED: FALSE
```

No retrieval evaluation, Decision-7 evaluation, WP-16 run, benchmark, provider inference, qrel creation, transport exposure, verification, or certification occurred in this phase.

