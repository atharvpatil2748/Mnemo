# V2 Production Runtime Evaluation Preflight Report

**Preflight Determination:** PREFLIGHT: PASS  
**Date:** 2026-09-02  
**Preflight Mode:** READ-ONLY EVALUATION PREFLIGHT (Zero evaluation queries executed, zero provider inference, zero embeddings regenerated, zero alias mutation, zero code changes)  

---

## 1. Executive Summary

This preflight report evaluates the readiness, security boundaries, runtime identity bindings, and dataset integrity of the internal Full Multilingual V2 production retrieval runtime before any controlled benchmark evaluation is executed.

Following the independent completion and verification of the five production adapters documented in `docs/governance/proposals/phase8_5_full_multilingual_architecture/V2_PRODUCTION_ADAPTER_SOURCE_AUDIT_REPORT.md`, this preflight audit traces the exact production execution graph from the server-owned registration root down to storage, candidate projection, and provider interfaces.

All 15 governing hard-stop conditions were evaluated against the active source tree and disk state. None were triggered. The runtime composition path is constructible, strictly server-owned, dynamically bound to the active V2 alias and canonical database identity, and fail-closed across all authorization, generation, and evidence boundaries.

No evaluation queries, model inference, embeddings, or state mutations were executed during this preflight.

---

## 2. Lifecycle State

The current lifecycle state is preserved without advancement:

```text
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
```

- `ACTIVE: PASS`: The V2 database and 4-generation alias set are active and validated read-only.
- `EXPOSED: FALSE`: No public transport (FastAPI router, MCP stdio/SSE) exposes the V2 retrieval path.
- `EVALUATED: FALSE`: No evaluation has been run; metrics remain unmeasured pending the authorized evaluation step.
- `VERIFIED: FALSE`: Verification requires post-evaluation analysis and audit.
- `CERTIFIED: FALSE`: Final certification requires ADR-0070 formal sign-off.

---

## 3. Production Composition Trace

The complete production composition trace was verified directly from the server-owned boundary:

```text
ServerOwnedFullMultilingualV2RegistrationV1
  [mnemo-server/mnemo_server/services/full_multilingual_v2_registration.py#L30-L70]
    │
    ├─► Instantiates CentralAuthorizationServiceV1(engine)
    │
    └─► ProductionFullMultilingualV2ServerDependencyAssemblerV1.assemble_v2_runtime_dependencies(...)
          [mnemo-server/mnemo_server/services/full_multilingual_v2_production.py#L158-L256]
            │
            ├─► GovernedV2DatabaseIdentityVerifier.verify(expected_database_identity)
            │     [mnemo-core/mnemo/phase85/v2_database_identity.py#L129-L135]
            │
            ├─► SQLiteV2ReadOnlyRuntimeStore(artifact.target_path) [mode=ro&immutable=1]
            │     [mnemo-core/mnemo/storage/v2_runtime.py#L36-L50]
            │
            ├─► GovernedActiveV2GenerationInspector (Adapter 1)
            │     [mnemo-core/mnemo/phase85/v2_production_adapters.py#L48-L89]
            │     └─► store.resolve_active_multilingual_v2_generation_set()
            │     └─► verifier.resolve_vector_embedding_generation(...) via index_generation_sources
            │
            ├─► CentralV2RetrievalAuthorizerV1 (Adapter 2)
            │     [mnemo-server/mnemo_server/services/full_multilingual_v2_production.py#L56-L139]
            │     └─► CentralAuthorizationServiceV1.authorize_notebook(...)
            │     └─► Emits V2RetrievalAuthorizationDecisionV1
            │
            ├─► AuthorizedV2SourceStorageEnumerator (Adapter 3)
            │     [mnemo-core/mnemo/phase85/v2_production_adapters.py#L92-L197]
            │     └─► store.list_authorized_v2_semantic_rows(...)
            │
            ├─► AuthorizedV2EvidenceResolver (Adapter 4)
            │     [mnemo-core/mnemo/phase85/v2_production_adapters.py#L199-L271]
            │     └─► store.get_authorized_v2_semantic_row(...)
            │     └─► store.get_authorized_v2_transformation(...)
            │     └─► Emits AuthorizedV2EvidenceResolutionV1
            │
            ├─► GovernedV2CandidateProjector (Adapter 5)
            │     [mnemo-core/mnemo/phase85/v2_production_adapters.py#L273-L401]
            │     └─► Emits AuthorizedRerankerEvidenceV1 & AdvancedRetrievalCandidate
            │
            └─► Returns V2RuntimeCompositionDependencies
                  │
                  ▼
FullMultilingualV2EvaluationRuntimeFactory.compose()
  [mnemo-core/mnemo/phase85/v2_evaluation_runtime.py#L167-L239]
    │
    ├─► AuthorizedMultilingualDenseRetrievalV2 (bound to resolved embedding generation ID)
    ├─► AuthorizedMultilingualSparseRetrievalV2 (bound to LANGUAGE_TEXT generation ID)
    ├─► FullMultilingualRetrievalApplicationV2
    ├─► FullMultilingualAdvancedSourceV2
    │
    └─► Returns ComposedFullMultilingualV2Runtime
          │
          ▼
InternalFullMultilingualV2Evaluator(runtime)
  [mnemo-core/mnemo/phase85/v2_evaluation_runtime.py#L149-L165]
```

---

## 4. Evaluator Boundary Audit

An audit of the evaluator boundary (`mnemo-core/mnemo/phase85/v2_evaluation_runtime.py` and `mnemo-server/mnemo_server/evaluation/multilingual_v2.py`) confirmed:

1. **No Evaluator-Owned Composition:** The evaluator receives only `ComposedFullMultilingualV2Runtime` (`v2_evaluation_runtime.py#L139-L147`). It possesses no factory, assembler, or constructor to manufacture a parallel runtime.
2. **No Production Adapter Instantiation:** The evaluator does not instantiate any of the five adapters independently.
3. **No Raw Identity / Scope Injection:** The evaluator cannot inject `actor_id`, `AuthorizationScopeV1`, or arbitrary `RetrievalScopeV2` directly into storage or retrieval layers.
4. **No Direct SQLite Access:** The evaluator owns no database connection, file handle, or SQL execution capability.
5. **No Direct Provider Access:** The evaluator owns no embedding model, tokenizer, or reranker instance; `RuntimeParityEvidenceV1` asserts `direct_provider_calls=false` and `private_runtime_access=false`.
6. **No Candidate Construction:** Candidate building is executed solely by `RerankerCandidateBuilderV1` and `GovernedV2CandidateProjector`.
7. **No Registration Bypass:** Runtime construction is gated behind `ServerOwnedFullMultilingualV2RegistrationV1`.

---

## 5. Runtime Identity Binding

The production runtime dynamically resolves and binds all required governed identity parameters:

| Binding Dimension | Canonical Value | Resolution Mechanism | Source Citation |
|---|---|---|---|
| **Active Alias Digest** | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | `store.resolve_active_multilingual_v2_alias_digest()` queries `active_multilingual_v2_alias_set` (`WHERE singleton=1`) | `mnemo-core/mnemo/storage/v2_runtime.py#L51-L57` |
| **Active 4-Generation Set** | `representation`: `81f673bb-...`<br>`language_text`: `a7220adf-...`<br>`embedding`: `62243160-...`<br>`vector`: `2b26443e-...` | `store.resolve_active_multilingual_v2_generation_set()` dynamically resolves and sorts 4 distinct capabilities | `mnemo-core/mnemo/storage/multilingual.py#L594-L641` |
| **Profile ID / Fingerprint** | `full_multilingual_v2_local_prebuild`<br>`51eb57f1f252d4e3e771668be8a70316303ede40c97cf0d3d25f7d20ed728034` | Bound from `V2RuntimeIdentityV1`; verified against database build row by `GovernedV2DatabaseIdentityVerifier` | `mnemo-core/mnemo/phase85/v2_database_identity.py#L129-L135` |
| **Vector Space Identity** | `7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7` | Verified from persisted embedding metadata; checked against runtime identity | `mnemo-core/mnemo/phase85/v2_database_identity.py#L150-L157` |
| **Canonical DB Identity** | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` | Computed deterministically from build row and generation envelopes by `GovernedV2DatabaseIdentityVerifier` | `mnemo-core/mnemo/phase85/v2_database_identity.py#L86-L127` |
| **Build Run ID** | `0b04f05c-a3d5-5879-b878-cd5f8e84ff2f` | Extracted from `v2_build_runs` table; verified against manifest | `mnemo-core/mnemo/phase85/v2_database_identity.py#L90-L98` |
| **Vector → Embedding Relation** | Vector `2b26443e...` maps to source embedding `62243160...` | Dynamically queried from `index_generation_sources` (`source_kind='generation'`); dense retrieval receives embedding ID | `mnemo-core/mnemo/phase85/v2_database_identity.py#L173-L224` |

---

## 6. Authorization Boundary

The authorization path was traced through static analysis without invoking provider inference:

1. **Principal Ingress:** The entry point `FullMultilingualRetrievalApplicationV2.retrieve(...)` (`full_multilingual_v2.py#L140`) receives `principal: PrincipalContextV1` and `plan: RetrievalPlanV2`.
2. **Central Authority Delegation:** It calls `self._retrieval_authorizer.authorize_v2_retrieval(principal=principal, plan=plan)`.
3. **Server-Owned Evaluation:** `CentralV2RetrievalAuthorizerV1.authorize_v2_retrieval` (`full_multilingual_v2_production.py#L77-L139`):
   - Asserts `principal.authenticated == True` (`#L80-L81`), raising `PermissionError("PRINCIPAL_MISSING")` if false.
   - Invokes `CentralAuthorizationServiceV1.authorize_notebook(principal, plan.scope.notebook_id, AuthorizationOperationV1.RETRIEVE)`.
   - Validates active runtime binding against dynamically resolved alias and generation set.
   - Issues immutable `V2RetrievalAuthorizationDecisionV1`.
4. **Downstream Invariance:**
   - Downstream components (`AuthorizedMultilingualDenseRetrievalV2`, `AuthorizedMultilingualSparseRetrievalV2`, `AuthorizedV2SourceStorageEnumerator`, `AuthorizedV2EvidenceResolver`, `RerankerCandidateBuilderV1`, `GovernedV2CandidateProjector`) accept only `V2RetrievalAuthorizationDecisionV1`.
   - No downstream component extracts raw `actor_id` or `plan.security_scope_identity` for authorization.
   - The evaluator cannot fabricate, alter, or inject a permissive decision.

---

## 7. Evidence and Semantic Text Boundary

The evidence retrieval and semantic text pipeline was verified:

1. **Storage Read:** `AuthorizedV2EvidenceResolver.resolve_v2_evidence(...)` (`v2_production_adapters.py#L205-L270`) invokes `store.get_authorized_v2_semantic_row(...)`.
2. **Table Origin:** Reads exclusively from `language_text_projection_rows_v2` (`v2_runtime.py#L204-L208`).
3. **Payload Verification:** Deserializes `payload` into `MultilingualTextProjectionRowV2` and verifies SHA-256 against stored `payload_hash`.
4. **Content Hash Verification:** Asserts that SHA-256 of `semantic_text` exactly matches `representation_reference.content_hash` (`multilingual_reranking.py#L96-L98`).
5. **Title / Metadata Exclusion:**
   - `GovernedV2CandidateProjector` sets `title_metadata = None` and `document_title = None` (`v2_production_adapters.py#L333, #L393`).
   - `AuthorizedRerankerEvidenceV1.__post_init__` (`multilingual_reranking.py#L105-L108`) raises `ValueError("title-only authorized reranker evidence is forbidden")` if `semantic_text == title_metadata`.
   - Semantic text cannot originate from filename, title, metadata, document label, or OCR label.
6. **Transformation Lineage:** For derived representations (`RepresentationAuthority.REPRESENTATION_DERIVED`), `store.get_authorized_v2_transformation(...)` reads `representation_transformations_v1` and populates `V2TransformationLineageV1`. Missing lineage fails closed with `LookupError("EVIDENCE_LINEAGE_INVALID")`.
7. **No Evaluator Access:** Evaluator code contains zero SQL queries and zero direct storage reads.

---

## 8. Evaluation Dataset Integrity

The cryptographic hashes of the Phase 8.5 evaluation corpus documents and V2 database were re-verified from physical disk bytes:

| Dataset Target | File Path | Expected SHA-256 | Actual Disk SHA-256 | Status |
|---|---|---|---|---|
| **Marathi Evidence Target** | `goldenDataset/Phase 8.5 Evaluation Corpus/manuscript.pdf` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | **MATCH / IMMUTABLE** |
| **Hindi/Sanskrit Evidence Target** | `goldenDataset/Phase 8.5 Evaluation Corpus/Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf` | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | **MATCH / IMMUTABLE** |
| **V2 Target Database** | `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | **MATCH / IMMUTABLE** |
| **Canonical DB Identity** | Governed build envelope identity | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` | **MATCH / GOVERNED** |

Neither document has been transformed, replaced, re-indexed, or modified.

---

## 9. Provider / Inference Boundary

The execution boundary for all inference operations was audited:

1. **Query Embedding:** Occurs in `MultilingualQueryEmbedderV2.embed_query(query)` inside `AuthorizedMultilingualDenseRetrievalV2.retrieve(...)`. Injected via `V2ProductionRuntimeSupportV1.query_embedder`.
2. **Dense Vector Search:** Executed by `SQLiteV2ReadOnlyRuntimeStore` via `AuthorizedMultilingualDenseRetrievalV2.retrieve(...)` against the active vector generation.
3. **Sparse FTS5 Search:** Executed by `SQLiteV2ReadOnlyRuntimeStore` via `AuthorizedMultilingualSparseRetrievalV2.retrieve(...)` against the active language-text generation.
4. **Candidate Tokenization:** Executed by `RerankerCandidateBuilderV1.build(...)` using the frozen tokenizer protocol.
5. **Reranker Scoring:** Occurs in `MultilingualCandidateRerankerV3.score_candidates(...)` inside `FullMultilingualRetrievalApplicationV2.retrieve(...)`. Injected via `V2ProductionRuntimeSupportV1.reranker`.

The evaluator owns none of these provider boundaries. It cannot bypass candidate construction or invoke embedding/reranker models directly.

---

## 10. Fail-Closed Verification

The 12 fail-closed security invariants were confirmed in source code:

| Invariant | Trigger Condition | Source Location | Exact Behavior |
|---|---|---|---|
| **1. Active Alias Missing** | Database has no active alias set | `full_multilingual_v2_production.py#L90-L92` | Raises `PermissionError("ACTIVE_ALIAS_MISSING")` |
| **2. Alias Digest Mismatch** | Alias digest differs from runtime identity | `v2_production_adapters.py#L70-L72` | Raises `RuntimeError("ACTIVE_GENERATION_MISMATCH")` |
| **3. Database Identity Mismatch** | Build rows or envelope deviate from canonical hash | `v2_production_adapters.py#L73` / `v2_database_identity.py#L130` | Raises `DatabaseIdentityMismatchError` |
| **4. Vector Space Mismatch** | Vector space differs from runtime identity | `v2_production_adapters.py#L86-L88` / `v2_evaluation_runtime.py#L293` | Raises `V2RuntimeCompositionError("VECTOR_SPACE_IDENTITY_MISMATCH")` |
| **5. Generation Set Invalid** | Generation count != 4 or capabilities missing | `storage/v2_runtime.py#L62, #L86` / `multilingual.py#L612, #L639` | Raises `StorageError("ACTIVE_GENERATION_INVALID" / "MISSING")` |
| **6. Vector/Embedding Mismatch** | Vector generation does not map to embedding generation | `v2_database_identity.py#L210-L215` / `v2_production_adapters.py#L80-L84` | Raises `VectorEmbeddingBindingError` / `RuntimeError` |
| **7. Principal Unauthenticated** | `principal.authenticated is False` | `full_multilingual_v2_production.py#L80-L81` | Raises `PermissionError("PRINCIPAL_MISSING")` |
| **8. Authorization Mismatch** | Decision runtime binding tampered | `v2_production_adapters.py#L129-L130` | Raises `PermissionError("AUTHORIZATION_RUNTIME_MISMATCH")` |
| **9. Unauthorized Evidence** | Evidence digest not in authorized handles | `v2_production_adapters.py#L194-L195` | Raises `PermissionError("EVIDENCE_UNAUTHORIZED")` |
| **10. Missing Semantic Text** | No projection row for authorized handle | `v2_production_adapters.py#L221-L224` | Raises `LookupError("SEMANTIC_TEXT_MISSING")` |
| **11. Content Hash Conflict** | Text SHA-256 differs from reference hash | `multilingual_reranking.py#L96-L98` / `v2_evidence_resolution.py#L254` | Raises `ValueError("resolved text conflicts with representation content hash")` |
| **12. Lineage Missing** | Derived representation lacks transformation row | `v2_production_adapters.py#L234-L235` / `v2_evidence_resolution.py#L267` | Raises `LookupError("EVIDENCE_LINEAGE_INVALID")` |

---

## 11. Static Search Results

Repository-wide static pattern analysis was executed across all production and evaluation code:

1. **Hardcoded Generation UUIDs in Production Logic:** None. Found only in documentation and static JSON metadata (**PASS**).
2. **Vector Generation ID as Embedding ID:** None. Resolved dynamically via `index_generation_sources` (**PASS**).
3. **Raw `actor_id` as Downstream Authorization:** None. Gated behind `V2RetrievalAuthorizationDecisionV1` (**PASS**).
4. **Raw `AuthorizationScopeV1` as Downstream Authorization:** None in V2. Preserved only in legacy V1 `RepresentationPipelineV1` (**PASS**).
5. **`RetrievalPlanV2.security_scope_identity` as Actor:** None in V2. `FullMultilingualAdvancedSourceV2` uses server `PrincipalContextV1` (**PASS**).
6. **Private SQLite Joins in V2 Application Code:** None. Encapsulated in `SQLiteV2ReadOnlyRuntimeStore` (**PASS**).
7. **Title-Only Candidate Construction:** Explicitly prohibited and blocked by value checks (**PASS**).
8. **Direct Provider Access in Evaluation Logic:** None. Routed through governed runtime interfaces (**PASS**).
9. **Evaluator-Owned Production Composition:** None. Composition is server-owned (**PASS**).
10. **V1 Fallback from V2:** Ranked mode executes strictly through V2; exhaustive mode delegates to governed fallback (**PASS**).

---

## 12. Tests / Checks Executed

1. **Focused Adapter Tests:**
   `uv run pytest mnemo-core/tests/unit/test_v2_production_adapters.py mnemo-server/tests/test_v2_production_adapters_registration.py --no-cov`
   **Result:** `4 passed in 2.32s`
2. **Complete V2 Unit Test Suite (11 files):**
   `uv run pytest mnemo-core/tests/unit/test_v2_*.py mnemo-server/tests/test_v2_*.py mnemo-core/tests/unit/test_full_multilingual_v2.py --no-cov`
   **Result:** `75 passed in 3.18s`
3. **Linter:**
   `uv run ruff check ...`
   **Result:** `0 errors`
4. **Strict Type Checker:**
   `uv run mypy ...`
   **Result:** `Success: no issues found in 8 source files`
5. **Bytecode Compilation:**
   `uv run python -m compileall -q mnemo-core mnemo-server`
   **Result:** `Exit code 0`
6. **JSON Schema Draft 2020-12:**
   Validated 33 schemas with `jsonschema.Draft202012Validator.check_schema`
   **Result:** `33 valid`
7. **Git Whitespace Hygiene:**
   `git diff --check`
   **Result:** `Clean`

---

## 13. Findings

1. **Architectural Coherence:** The separation of core contracts from server-owned dependency assembly is clean and fully realized. Core has zero dependencies on server; server injects central authorization into the production adapters.
2. **Evaluation Parity:** `InternalFullMultilingualV2Evaluator` is constrained to observe the exact application service composed for production. It cannot construct, mock, or subvert the retrieval path.
3. **Corpus Preparedness:** `manuscript.pdf` is present, verified, and ready for Marathi evaluation without any patching or corpus mutation.

---

## 14. Hard-Stop Assessment

| # | Condition | Evaluation Result |
|---|---|---|
| 1 | Evaluator owns production composition | **NO** — Server-owned via `ServerOwnedFullMultilingualV2RegistrationV1` |
| 2 | Evaluator can bypass server-owned registration | **NO** — Gated behind registration port |
| 3 | Evaluator supplies actor identity | **NO** — Derived server-side via `PrincipalContextV1` |
| 4 | Evaluator supplies authorization scope/decision | **NO** — Issued solely by `CentralV2RetrievalAuthorizerV1` |
| 5 | Production runtime is not constructible | **NO** — Verified constructible and tested |
| 6 | Runtime does not bind to active V2 identity | **NO** — Bound to active alias and verified against manifest |
| 7 | Generation IDs are hardcoded in runtime | **NO** — Dynamically resolved from DB |
| 8 | Vector generation is treated as embedding generation | **NO** — Disambiguated via `index_generation_sources` |
| 9 | Semantic text can come from title/filename/metadata | **NO** — Prohibited and fail-closed |
| 10 | Evaluator accesses SQLite directly | **NO** — Encapsulated in runtime store |
| 11 | Evaluator constructs production candidates | **NO** — Constructed by shared builder/projector |
| 12 | Provider inference can be invoked outside runtime | **NO** — Injected through governed support |
| 13 | Protected corpus hash mismatch | **NO** — All hashes match bit-for-bit |
| 14 | Canonical V2 DB identity mismatch | **NO** — Matches `0c6c73f9...` |
| 15 | Any required fail-closed boundary is missing | **NO** — All 12 fail-closed checks verified |

**Outcome:** Zero hard-stop conditions triggered.

---

## 15. Final Determination

# PREFLIGHT: PASS

Production runtime evaluation is authorized to proceed to the next controlled evaluation step. No evaluation was executed during this preflight.

**Lifecycle Invariants Preserved:**
```text
EXPOSED: FALSE
EVALUATED: FALSE
VERIFIED: FALSE
CERTIFIED: FALSE
```
