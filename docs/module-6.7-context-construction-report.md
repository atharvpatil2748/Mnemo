# Module 6.7 Context Construction Report

## Status and scope

Module 6.7 is complete under accepted ADR-0043. It implements only deterministic
provenance-preserving context construction. Modules 6.8â€“6.10 remain not
started, and milestone M6 remains not verified. Version 0.20.1 is unchanged;
no commit, push, tag, or release was created.

## Implementation

- Added frozen, slotted context models for exact-version display labels,
  verbatim/compressed items, compression evidence, typed empty outcomes, and
  the complete Module 6.8 handoff.
- Added `ContextBuilder` with the exact ADR-0043 method signature and a frozen
  registry plus existing token-counter dependency. It has no storage or
  backend dependency.
- Implemented canonical fixed-input serialization, whole-render token counting,
  exact-fit acceptance, and the 1â€“1,000,000 budget contract.
- Implemented the mandatory all-or-empty top-three verbatim prefix, sequential
  skip-over selection, and no-truncation semantics.
- Reused `llm/extractor` with the exact prompt, compact canonical JSON input,
  strict one-field schema, 100-token target, 120-token maximum, sequential
  calls, and fail-closed registered-provider behavior.
- Preserved each exact `RerankedChunkResult` and the complete top-level
  `RetrievalRerankResult`; selected and omitted identities partition the input.

No frozen Phase 1 or prior Phase 6 contract was modified. Module 6.7 performs
no retrieval, reranking, RRF recomputation, candidate expansion, context
storage, or Module 6.8 behavior.

## Validation

| Gate | Result |
|---|---|
| Focused Module 6.7 tests | PASS â€” 34 tests |
| Phase 6.1â€“6.7 tests | PASS â€” 258 tests |
| Full `uv run pytest` | PASS â€” 1,038 passed, 1 skipped |
| Coverage | PASS â€” 90.15% |
| `uv run ruff format --check .` | PASS â€” 163 files formatted |
| `uv run ruff check .` | PASS |
| Production strict mypy | PASS â€” 87 source files |
| `uv run pre-commit run --all-files` | PASS |
| Package builds | PASS â€” core, server, email-ingestion |

The skipped test is the existing opt-in live Phase 4/5 acceptance. Pytest also
reported the existing Windows cache-cleanup permission warning after successful
test execution; it did not change the passing exit status.

## Real golden acceptance

Command:

```text
uv run python scripts/verify_module_6_7_context.py
```

Evidence: `docs/milestone-evidence/module-6.7-context.json`

| Measurement | Actual result |
|---|---|
| Corpus | `goldenDataset/Bhagavad-gita-As-It-Is.pdf` |
| SHA-256 | `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583` |
| Query | `What does the Bhagavad Gita teach about duty?` |
| Module 6.6 candidates | 10 |
| Selected / omitted | 4 / 6 |
| Verbatim / compressed | 3 / 1 |
| Total / fixed / available / used tokens | 1,621 / 25 / 1,596 / 1,596 |
| Extractor calls per repeat | 7 / 7 |
| First / second context build | 0.0661 s / 0.0645 s |
| Total real acceptance | 23.1964 s |
| Deterministic controlled-output repeat | PASS |
| Exact provenance and partition | PASS |
| Canonical chunks unchanged | PASS |
| Module 6.7 backend access | NONE |

The runner regenerated the real Module 6.5 and pinned Module 6.6 handoff using
the existing dedicated acceptance state. Compression used a controlled,
deterministic Extractor that retained leading canonical passage text; this
validates Module 6.7 orchestration and does not claim universal LLM byte-level
determinism. Historical M4/M5 evidence and collections were not modified.
