# Mnemo Phase 8.5 Full Multilingual V2 — Controlled Evaluation Limit Remediation Report

**Date:** 2026-09-02  
**Task:** Controlled Production Evaluation — Narrow Contract Remediation Only  
**Author:** Antigravity Engineering (governed handoff)  
**Status:** REMEDIATION COMPLETE — HARD STOP OBSERVED — EVALUATION NOT RERUN  

---

## 1. Discovered Contract Mismatch

During the initial invocation of the controlled evaluation using the server-owned production runtime (`ServerOwnedFullMultilingualV2RegistrationV1` → `ProductionFullMultilingualV2ServerDependencyAssemblerV1` → `FullMultilingualV2EvaluationRuntimeFactory` → `ComposedFullMultilingualV2Runtime`), all queries failed closed immediately with:

```text
RuntimeError: all Full Multilingual V2 retrieval sources are unavailable
```

Forensic investigation of internal stage exceptions revealed the following exact failure chain:

1. **Dense Retrieval:** `AuthorizedMultilingualDenseRetrievalV2.retrieve()` (`mnemo-core/mnemo/retrieval/multilingual_dense_v2.py#L100-L103`) called:
   ```python
   authorized = await self._source_enumerator.enumerate_authorized_multilingual_sources(
       decision=decision,
       limit=MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS + 1,  # 10_000 + 1 = 10_001
   )
   ```
2. **Sparse Retrieval:** `AuthorizedMultilingualSparseRetrievalV2.retrieve_authorized_multilingual_sparse()` (`mnemo-core/mnemo/retrieval/multilingual_sparse_v2.py#L60-L63`) called:
   ```python
   authorized = await self._source_enumerator.enumerate_authorized_multilingual_sources(
       decision=decision,
       limit=10_001,
   )
   ```
3. **Storage Enumeration Adapter (Adapter 3):** `AuthorizedV2SourceStorageEnumerator.enumerate_authorized_v2_evidence()` (`mnemo-core/mnemo/phase85/v2_production_adapters.py#L148-L152`) forwarded `limit` directly to storage:
   ```python
   rows = await self._store.list_authorized_v2_semantic_rows(
       decision=decision,
       generation_id=generations.language_text_generation_id,
       limit=limit,
   )
   ```
4. **Storage Engine Rejection:** `SQLiteV2ReadOnlyRuntimeStore.list_authorized_v2_semantic_rows()` (`mnemo-core/mnemo/storage/v2_runtime.py#L161-L162`) enforced:
   ```python
   if not 1 <= limit <= 10_000:
       raise ValueError("authorized V2 semantic enumeration limit is invalid")
   ```

Because `10_001 > 10_000`, `list_authorized_v2_semantic_rows()` raised `ValueError("authorized V2 semantic enumeration limit is invalid")` on both dense and sparse retrieval attempts. As a consequence, `FullMultilingualRetrievalApplicationV2.retrieve()` correctly caught both source errors, recorded `dense_unavailable:ValueError` and `sparse_unavailable:ValueError` in omissions, and failed closed with `RuntimeError("all Full Multilingual V2 retrieval sources are unavailable")` before any candidate scoring could take place.

---

## 2. Governed Intent for 10,001

An inspection of the repository source code and governance verified the governed intent behind the `10_001` limit:

1. **Universe Upper Bound ($N = 10,000$):**
   - `MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS = 10_000` is defined in `mnemo-core/mnemo/retrieval/multilingual_dense_v2.py#L18`.
   - `mnemo-core/mnemo/storage/multilingual.py` lines 788, 861, and 1136 enforce `if len(authorized_sources) > 10_000: raise ValueError(...)`.
2. **Sentinel Overflow Detection ($N + 1 = 10,001$):**
   - In `multilingual_dense_v2.py#L102-L105`:
     ```python
     authorized = await self._source_enumerator.enumerate_authorized_multilingual_sources(
         decision=decision,
         limit=MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS + 1,
     )
     if len(authorized) > MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS:
         raise ValueError("authorized multilingual vector universe exceeds 10000")
     ```
   - In `multilingual_sparse_v2.py#L60-L65`:
     ```python
     authorized = await self._source_enumerator.enumerate_authorized_multilingual_sources(
         decision=decision,
         limit=10_001,
     )
     if len(authorized) > 10_000:
         raise ValueError("authorized multilingual sparse universe exceeds 10000")
     ```
3. **Conclusion:**
   The request for `10_001` items is **not** an arbitrary caller limit, nor a broader retrieval request. It is an explicit, bounded sentinel probe designed to detect whether the eligible authorized evidence universe strictly exceeds the 10,000-vector ceiling without performing an unbounded scan.

---

## 3. Exact Source Change

The production contract was remediated in `mnemo-core/mnemo/storage/v2_runtime.py` with the minimum necessary change to recognize the governed probe:

```diff
--- a/mnemo-core/mnemo/storage/v2_runtime.py
+++ b/mnemo-core/mnemo/storage/v2_runtime.py
@@ -27,6 +27,10 @@
 from mnemo.storage.sqlite import SQLiteStore
 
 
+MAX_AUTHORIZED_V2_SEMANTIC_ROWS = 10_000
+MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE = 10_001
+
+
 def _digest(value: object) -> str:
     return hashlib.sha256(
         json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
@@ -161,7 +165,7 @@
         limit: int,
     ) -> tuple[MultilingualTextProjectionRowV2, ...]:
         _validate_decision_generation(decision, generation_id)
-        if not 1 <= limit <= 10_000:
+        if not 1 <= limit <= MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE:
             raise ValueError("authorized V2 semantic enumeration limit is invalid")
         clauses, params = _scope_clauses(decision.retrieval_scope)
         clauses.extend(_position_clauses(decision, params))
```

### Guarantees of this Change:
- `10_000` remains the documented maximum authorized evidence universe.
- `10_001` is accepted **only** as the explicit bounded overflow-detection probe (`MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE`).
- `10_002` and any larger limits remain strictly rejected with `ValueError`.
- `0`, negative numbers, and invalid limits remain strictly rejected with `ValueError`.
- Zero SQL queries were modified or added.
- Zero database write paths were introduced (SQLite remains opened `mode=ro&immutable=1`, `PRAGMA query_only=ON`).
- Zero evaluator-specific bypasses of authorization were introduced.

---

## 4. Why Clamping to 10,000 Was Rejected

The alternative approach of silently clamping `limit = min(limit, 10_000)` in `AuthorizedV2SourceStorageEnumerator` or `v2_runtime.py` was **explicitly rejected** for the following governance and security reasons:

1. **Hiding the Overflow Condition:** If the storage layer silently truncated the request from 10,001 to 10,000, `len(authorized)` could never exceed 10,000 even if the underlying database contained 15,000 valid records.
2. **Defeating the Fail-Closed Invariant:** The checks in `multilingual_dense_v2.py#L104` and `multilingual_sparse_v2.py#L64` (`if len(authorized) > 10_000: raise ValueError(...)`) would become completely unreachable dead code.
3. **Violating Semantic Truth:** Silently clamping a probe request is an ad-hoc semantic mutation. The storage engine must return up to 10,001 rows when probed so that the caller can definitively detect if the universe is out of bounds.

---

## 5. Verification Tests

A focused regression test `test_authorized_v2_semantic_enumeration_limit_boundary()` was added to `mnemo-core/tests/unit/test_v2_production_adapters.py`.

The test rigorously verifies the 9 required conditions:
1. **Limit 10,000:** Accepted as the normal maximum retrieval bound.
2. **Limit 10,001:** Accepted as the explicit governed overflow-detection probe.
3. **Limit 10,002:** Rejected with `ValueError("authorized V2 semantic enumeration limit is invalid")`.
4. **Negative / Zero Limits:** Limits `0`, `-1`, `-100` rejected with `ValueError`.
5. **Authorization Intact:** Rejecting unauthorized runtime bindings fails closed with `PermissionError("AUTHORIZATION_RUNTIME_MISMATCH")`.
6. **Semantic Text Resolution Intact:** `resolution.semantic_text` resolves genuine content and matches database identity.
7. **No Private SQL:** All storage queries proceed through existing read-only statements.
8. **Database Immutability:** Bit-for-bit SHA-256 comparison of the target SQLite file before and after execution proves zero mutations.
9. **Alias Immutability:** `active_multilingual_v2_alias_set` digest is identical before and after.

### Test Execution Results:

| Test Suite | Command | Result |
|---|---|---|
| **Focused Adapter Tests** | `uv run pytest mnemo-core/tests/unit/test_v2_production_adapters.py -o addopts=""` | **3 passed in 12.38s (Exit code 0)** |
| **Server Registration Suites** | `uv run pytest mnemo-server/tests/test_v2_production_adapters_registration.py mnemo-server/tests/test_v2_production_registration_contract.py mnemo-core/tests/unit/test_v2_evaluation_runtime.py mnemo-core/tests/unit/test_v2_authorization_boundary.py` | **10 passed in 10.00s (Exit code 0)** |
| **Code Linter (ruff)** | `uv run ruff check mnemo-core/mnemo/storage/v2_runtime.py mnemo-core/tests/unit/test_v2_production_adapters.py` | **All checks passed!** |
| **Type Checker (mypy)** | `uv run mypy mnemo-core/mnemo/storage/v2_runtime.py mnemo-core/tests/unit/test_v2_production_adapters.py` | **Success: no issues found in 2 source files** |
| **Bytecode Compilation** | `uv run python -m compileall mnemo-core/mnemo/storage/v2_runtime.py mnemo-core/tests/unit/test_v2_production_adapters.py` | **Clean compilation (Exit code 0)** |
| **Git Diff Check** | `git diff --check mnemo-core/mnemo/storage/v2_runtime.py mnemo-core/tests/unit/test_v2_production_adapters.py` | **Zero trailing whitespace / formatting anomalies** |

---

## 6. Protected Artifact Hashes

All protected cryptographic hashes were computed directly from physical disk bytes following the remediation:

| Protected Target | Expected SHA-256 Digest | Actual Disk SHA-256 Digest | Verification Status |
|---|---|---|---|
| **Marathi Evidence Target (`manuscript.pdf`)** | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | **MATCH (BIT-FOR-BIT IDENTICAL)** |
| **Hindi Evidence Target (`Valmiki Ramayana...pdf`)** | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | **MATCH (BIT-FOR-BIT IDENTICAL)** |
| **V2 Database File (`mnemo.db`)** | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | **MATCH (BIT-FOR-BIT IDENTICAL)** |
| **Canonical DB Identity** | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` | `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d` | **MATCH (IMMUTABLE ENVELOPE)** |
| **Vector-Space Identity** | `7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7` | `7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7` | **MATCH (GOVERNED BGE-M3 V2)** |
| **Active Alias Set Digest** | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | **MATCH (SINGLETON UNTOUCHED)** |

---

## 7. Current Governance Lifecycle

In strict compliance with user instructions:

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

**`EVALUATED` HAS NOT BEEN ADVANCED.** It remains `EVALUATED: FALSE`.

---

## 8. Explicit Statement on Evaluation Execution

**THE CONTROLLED EVALUATION WAS NOT RERUN.**

Following the completion and verification of this narrow contract remediation:
- No evaluation metrics were generated or recorded.
- No ground truth comparisons were executed.
- No ranked metrics (Recall@K, MRR, nDCG) were computed.
- The evaluation harness is in a stopped state awaiting user review and explicit command to initiate the controlled evaluation run.
