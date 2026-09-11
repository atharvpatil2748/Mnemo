# Mnemo Pre-Phase-8.8 Coverage Hardening

Status: **BLOCKED — configured coverage gate not yet satisfied**

## Result

The authoritative full suite is functionally green: **2,041 passed, 1 skipped, 0
functional failures**. Aggregate coverage improved from **81.79%** to **83.46%**, but
the unchanged configured gate is **90%**. No exclusion, pragma, source-selection, or
threshold change was made.

Coverage.py measures 44,305 statement-plus-branch opportunities. The final run covered
36,976, while a 90% result requires 39,875. The remaining deficit is therefore **2,899
covered opportunities**. This is too large to close truthfully with incidental line
execution; it requires additional behavioral suites across the remaining production
and build modules.

## Coverage Evidence

| Measure | Initial | Final | Change |
| --- | ---: | ---: | ---: |
| Aggregate coverage | 81.79% | 83.46% | +1.67 points |
| Covered statements | 28,708 | 29,280 | +572 |
| Missing statements | 4,939 | 4,367 | -572 |
| Covered branches | 7,529 | 7,696 | +167 |
| Missing branches | 3,129 | 2,962 | -167 |
| Branch-only coverage | 70.64% | 72.21% | +1.57 points |

Authoritative machine output: `scratch/mnemo-coverage-final.json` and `coverage.xml`.

## Tests Added

The full suite collected **44 additional behavioral scenarios**. Two test modules were
added and two existing modules were expanded:

- `mnemo-server/tests/test_evaluation_notebook_reindex.py`
- `mnemo-server/tests/test_evaluation_transport_runtime.py`
- `mnemo-core/tests/unit/test_multimodal_search_store.py`
- `mnemo-core/tests/unit/test_v2_index_build_operator.py`

The tests prove:

- retained-store count, integrity, foreign-key, FTS, and multimodal audits;
- all retained BGE-M3 embedding rejection boundaries (orphan, identity, model,
  dimensions, digest, and numeric validity);
- deterministic Unicode inventory hashing;
- exact allowlisting of managed and staging paths;
- governed manifest status, registry, deletion, repair, and failure evidence behavior;
- atomic notebook publication and retained diagnostic checkpoints;
- repair-only, validation-only, successful pipeline, smoke, and repair orchestration;
- production transport configuration for registry and validation candidates;
- HTTP, MCP stdio, and MCP SSE construction, lifecycle, dynamic-k, and semantic parity;
- multimodal generation selection, multilingual paging, OCR/Vision records, asset
  filtering, visual-vector compatibility, positional scopes, and cosine/dot behavior;
- V2 build helper contracts and success/failure resource cleanup.

No test merely asserts execution, and no production behavior was changed for coverage.

## Largest Remaining Coverage Areas

| Module | Initial coverage | Initial missed branches | Tests added here | Final state / reason |
| --- | ---: | ---: | --- | --- |
| evaluation notebook reindex tool | 27.62% | 214 | 31 scenarios | Improved to about 67%; GPU embedding and live MCP client exception matrices remain |
| Phase 8.5 V2 index build | 30.85% | 113 | 3 scenarios | Governed stage sequencing covered; full 3,523-item projection build internals remain |
| multilingual providers | 52.66% | 85 | none in this pass | Offline model/runtime failure matrix requires a dedicated provider suite |
| core engine | 71.34% | 96 | none in this pass | Alternate composition and lifecycle branches remain |
| multimodal search store | 13.06% | 60 | 6 scenarios | Major read/dispatch paths covered; exhaustive paging/integrity combinations remain |
| multilingual SQLite storage | 62.65% | 68 | none in this pass | Immutable conflict, alias upgrade, and authorization combinations remain |
| projection/build helpers | 73.21% | 52 | partial through V2 build tests | Recovery and coverage failure matrices remain |

The remaining paths are legitimate behaviors, especially authorization denials,
lifecycle failures, compatibility handling, provider initialization errors, and build
recovery. They should be covered in subsequent focused batches rather than hidden.

## Validation

| Gate | Result |
| --- | --- |
| Full pytest functional result | PASS — 2,041 passed, 1 skipped |
| Configured coverage gate | **FAIL — 83.46% < 90%** |
| Ruff | PASS |
| strict mypy (279 source files) | PASS |
| compileall | PASS |
| UI Biome | PASS |
| UI typecheck | PASS |
| UI tests and coverage | PASS — 1 passed, 100% |
| JSON parse validation | PASS |
| `git diff --check` | PASS |
| Protected database hashes | PASS |

## Protected State and Phase Boundary

- Production DB: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- Phase 8.5 DB: `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`
- Phase 8.6 DB: `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`

All hashes match their protected values. No ingestion, embedding, multimodal generation,
database mutation, commit, push, stash, reset, or staging operation occurred. The MCP
contract remains 14 tools. `search_images` is not implemented, and Phase 8.8 has not
started.

## Exact Blocker

`PYTHON_COVERAGE_GATE_FAILED`: aggregate coverage is 83.46%, leaving a 6.54-point
shortfall and 2,899 additional statement/branch opportunities required for the 90%
gate. The next highest-value work is dedicated testing of multilingual providers,
engine alternate composition, multilingual SQLite authorization/alias transitions,
the remaining V2 projection builder internals, and reindex live-client failure paths.
