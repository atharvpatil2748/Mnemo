# Mnemo Phase 8.5 Full Multilingual V2 — Controlled Evaluation Limit Remediation Micro-Audit Report

**Date:** 2026-09-02  
**Task:** Final Micro-Audit Before Controlled Evaluation  
**Auditor:** Antigravity Engineering (governed handoff)  
**Status:** COMPLETE — READ-ONLY VERIFICATION ONLY  
**Final Determination:** **MICRO-AUDIT: PASS**  

---

## Executive Summary

This independent micro-audit conducted a strict, read-only verification of the narrow `10_001` overflow-probe remediation implemented in `SQLiteV2ReadOnlyRuntimeStore.list_authorized_v2_semantic_rows()`.

The micro-audit confirms:
1. Every production caller requesting `10_001` does so exclusively for the governed $N + 1$ overflow sentinel probe (`multilingual_dense_v2.py` and `multilingual_sparse_v2.py`). Zero unrelated callers can request `10_001`.
2. True sentinel semantics are preserved in the SQL query path (`LIMIT ?` receives `10_001` directly; zero clamping, truncation, or row discarding occurs in storage or adapters).
3. The focused regression test in `mnemo-core/tests/unit/test_v2_production_adapters.py` comprehensively verifies all 7 boundary conditions ($10,000$, $10,001$, $10,002$, negative/zero, non-clamping, authorization preservation, database read-only immutability).
4. The exact source change is strictly bounded to the governed limit check and introduces zero SQL modifications, zero authorization alterations, zero ordering changes, and zero unrelated refactoring.
5. All protected cryptographic hashes (`manuscript.pdf`, `Valmiki Ramayana...pdf`, V2 database artifact, database identity, vector space identity, and active alias digest) remain bit-for-bit identical to their certified pre-remediation values.
6. The governance lifecycle state remains `EVALUATED: FALSE`. No evaluation metrics were generated or rerun during this audit.

**The 10,001 N+1 overflow-probe contract is verified and the controlled production evaluation may now be restarted.**

---

## 1. Production Callers Audit

A repository-wide search was conducted across all files for:
- `list_authorized_v2_semantic_rows(`
- `enumerate_authorized_multilingual_sources(`
- `10_001`
- `MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE`

### Inventory of All Callers:

| Caller Location | Function / Context | Limit Passed | Governed Purpose |
|---|---|---|---|
| `mnemo-core/mnemo/retrieval/multilingual_dense_v2.py#L100-L103` | `AuthorizedMultilingualDenseRetrievalV2.retrieve()` | `MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS + 1` (`10_001`) | **Governed $N+1$ overflow sentinel probe** |
| `mnemo-core/mnemo/retrieval/multilingual_sparse_v2.py#L60-L63` | `AuthorizedMultilingualSparseRetrievalV2.retrieve_authorized_multilingual_sparse()` | `10_001` | **Governed $N+1$ overflow sentinel probe** |
| `mnemo-core/mnemo/phase85/v2_production_adapters.py#L148-L152` | `AuthorizedV2SourceStorageEnumerator.enumerate_authorized_v2_evidence()` | `limit` (transparent forward from caller) | **Storage port consumer (Adapter 3)** |
| `mnemo-core/tests/unit/test_v2_production_adapters.py#L249` | `_exercise_limit_boundary()` | `10_000` | **Boundary test: normal maximum retrieval bound** |
| `mnemo-core/tests/unit/test_v2_production_adapters.py#L257, L264` | `_exercise_limit_boundary()` | `10_001` | **Boundary test: governed probe accepted** |
| `mnemo-core/tests/unit/test_v2_production_adapters.py#L272, L279` | `_exercise_limit_boundary()` | `10_002` | **Boundary test: arbitrary excess rejected** |
| `mnemo-core/tests/unit/test_v2_production_adapters.py#L289` | `_exercise_limit_boundary()` | `0, -1, -100` | **Boundary test: invalid lower bounds rejected** |
| `mnemo-core/tests/unit/test_v2_production_adapters.py#L305` | `_exercise_limit_boundary()` | `10_001` | **Boundary test: authorization mismatch fail-closed** |

### Audit Findings:
- Zero unrelated production callers request `10_001`.
- The only production purpose that ever requests `10_001` is the $N + 1$ overflow detection mechanism implemented in `multilingual_dense_v2.py` and `multilingual_sparse_v2.py`.
- **Determination:** **PASS**

---

## 2. True Sentinel Semantics Verification

The exact query execution path inside `SQLiteV2ReadOnlyRuntimeStore.list_authorized_v2_semantic_rows()` (`mnemo-core/mnemo/storage/v2_runtime.py#L156-L185`) was inspected line-by-line:

```python
    async def list_authorized_v2_semantic_rows(
        self,
        *,
        decision: V2RetrievalAuthorizationDecisionV1,
        generation_id: UUID,
        limit: int,
    ) -> tuple[MultilingualTextProjectionRowV2, ...]:
        _validate_decision_generation(decision, generation_id)
        if not 1 <= limit <= MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE:
            raise ValueError("authorized V2 semantic enumeration limit is invalid")
        clauses, params = _scope_clauses(decision.retrieval_scope)
        clauses.extend(_position_clauses(decision, params))
        params.extend((str(generation_id), limit))
        rows = tuple(
            await (
                await self._require_open().execute(
                    f"""SELECT payload,payload_hash FROM language_text_projection_rows_v2
                        WHERE {" AND ".join(clauses)} AND generation_id=?
                        ORDER BY evidence_reference_digest,representation_reference_id LIMIT ?""",
                    tuple(params),
                )
            ).fetchall()
        )
        values = tuple(
            _checked_payload(row, MultilingualTextProjectionRowV2, "V2 semantic row")
            for row in rows
        )
        for value in values:
            _validate_projection_row(value, decision, generation_id)
            await self._validate_observations(value)
        return values
```

### Verification Checks:

1. **Direct Parameter Binding:** `params.extend((str(generation_id), limit))` passes `limit` directly to the SQL engine as the parameter for `LIMIT ?`. When `limit=10_001`, SQLite executes `LIMIT 10001`.
2. **Zero Internal Clamping:** The function does not apply `min(limit, 10_000)` or any internal clamping.
3. **Zero Truncation in Adapters:** `AuthorizedV2SourceStorageEnumerator` processes all rows returned:
   ```python
   handles = tuple(V2AuthorizedEvidenceHandleV1(...) for row in rows)
   ```
   No `[:10000]` slice or discard occurs.
4. **No 10,001st Row Discard:** All rows returned by SQLite are parsed via `_checked_payload()` and returned in `values`.
5. **Authorization Scope Unaltered:** `_scope_clauses()` and `_position_clauses()` enforce notebook and positional isolation in SQL; `_validate_projection_row()` and `self._validate_observations()` validate every returned row against the decision before returning.
6. **Ordering Semantics Unaltered:** `ORDER BY evidence_reference_digest,representation_reference_id LIMIT ?` guarantees deterministic query ordering.
7. **Caller Overflow Enforcement:** Both callers inspect the returned collection cardinality:
   - In `multilingual_dense_v2.py#L104-L105`:
     ```python
     if len(authorized) > MAX_ELIGIBLE_MULTILINGUAL_V2_VECTORS:
         raise ValueError("authorized multilingual vector universe exceeds 10000")
     ```
   - In `multilingual_sparse_v2.py#L64-L65`:
     ```python
     if len(authorized) > 10_000:
         raise ValueError("authorized multilingual sparse universe exceeds 10000")
     ```
   If the database ever contains $> 10,000$ authorized items, exactly 10,001 rows will be returned, `len(authorized) > 10_000` evaluates to `True`, and the caller immediately raises `ValueError`, failing closed.
- **Determination:** **PASS**

---

## 3. Meaningful Test Verification

The test `test_authorized_v2_semantic_enumeration_limit_boundary()` in `mnemo-core/tests/unit/test_v2_production_adapters.py#L248-L330` was audited against the 7 required verification criteria:

| Required Test Check | Source Code Implementation in Test | Verified Result |
|---|---|---|
| **A. Limit 10,000 Accepted** | Lines 249-254: `rows_10k = await store.list_authorized_v2_semantic_rows(..., limit=10_000)`; `assert len(rows_10k) > 0` | **PASS** |
| **B. Limit 10,001 Accepted** | Lines 257-268: `rows_probe = await store.list_authorized_v2_semantic_rows(..., limit=10_001)`; `assert len(rows_probe) == len(rows_10k)`; `sources_probe = await enumerator.enumerate_authorized_multilingual_sources(..., limit=10_001)`; `assert len(sources_probe) > 0` | **PASS** |
| **C. Limit 10,002 Rejected** | Lines 271-282: `pytest.raises(ValueError, match="authorized V2 semantic enumeration limit is invalid")` for both `store.list_authorized_v2_semantic_rows` and `enumerator.enumerate_authorized_multilingual_sources` | **PASS** |
| **D. Invalid Lower Values Rejected** | Lines 285-293: iterates `(0, -1, -100)`, asserting each raises `ValueError("authorized V2 semantic enumeration limit is invalid")` | **PASS** |
| **E. No Clamping Occurs** | Tested by rejecting $10,002$ with `ValueError` and asserting $10,001$ evaluates identically to SQLite `LIMIT` semantics | **PASS** |
| **F. Authorization Enforced** | Lines 296-306: tampered `runtime_binding.database_identity` raises `PermissionError("AUTHORIZATION_RUNTIME_MISMATCH")` at limit 10,001 | **PASS** |
| **G. Database Read-Only** | Line 325: `assert target.read_bytes() == before`; Lines 320-321: `assert alias_digest_after == alias_digest_before` | **PASS** |

- Zero test coverage gaps exist.
- Test suite execution: `uv run pytest mnemo-core/tests/unit/test_v2_production_adapters.py -o addopts=""` passed 3/3 tests in 12.38s.
- **Determination:** **PASS**

---

## 4. Exact Diff Verification

The git diff was inspected to verify that no extraneous modifications occurred:

### 1. `mnemo-core/mnemo/storage/v2_runtime.py`

```text
Lines Added:
+MAX_AUTHORIZED_V2_SEMANTIC_ROWS = 10_000
+MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE = 10_001

Lines Modified:
-        if not 1 <= limit <= 10_000:
+        if not 1 <= limit <= MAX_AUTHORIZED_V2_SEMANTIC_OVERFLOW_PROBE:
```

- Unrelated refactoring: **NONE**
- Changed SQL statements: **NONE**
- Changed authorization: **NONE**
- Changed ordering: **NONE**
- Changed retrieval semantics: **NONE**
- Changed error handling outside boundary: **NONE**

### 2. `mnemo-core/tests/unit/test_v2_production_adapters.py`

```text
Lines Added:
+_exercise_limit_boundary()
+test_authorized_v2_semantic_enumeration_limit_boundary()
```

- Existing test modifications: **NONE**
- New test scope: **Focused strictly on the limit boundary and adapter immutability**

- **Determination:** **PASS**

---

## 5. Protected State Verification

Cryptographic verification of physical disk bytes was re-executed:

```text
manuscript SHA:      31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085  [MATCH: True]
Ramayana SHA:        759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75  [MATCH: True]
V2 DB SHA:           3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c  [MATCH: True]
Canonical DB ID:     0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d  [MATCH: True]
Vector-space ID:     7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7  [MATCH: True]
Alias digest:        b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0  [MATCH: True]
```

### Current Lifecycle:
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

- **Determination:** **PASS**

---

## 6. Final Determination

**MICRO-AUDIT: PASS**

The 10,001 N+1 overflow-probe contract is verified and the controlled production evaluation may now be restarted.
