# Module 6.9 Citation Resolution and Persistence Report

## Status and scope

Module 6.9 is complete under accepted ADR-0045. It implements only typed
citation resolution and per-citation persistence. Module 6.10 final QA
integration remains not started, and milestone M6 remains not verified. Version
0.20.1 is unchanged; no commit, push, tag, or release was created.

## Implementation

- Added frozen, slotted `CitationResolutionStatus` and
  `CitationResolutionResult` models retaining the exact
  `GroundedAnswerResult` and caller-supplied assistant `Turn`.
- Added backend-neutral `CitationEngine` depending only on
  `StorageInterfaceV1` and an injected UTC clock.
- Implemented ADR-0045's strict ASCII `[source:N]` grammar, malformed and
  unknown marker rejection, repeat deduplication, and first-occurrence order.
- Resolved markers exclusively through retained typed `ContextItem` provenance
  and exact document/version labels.
- Constructed deterministic UUIDv5 citations with full canonical `Chunk.text`,
  including compressed and parent-promoted context items.
- Fully validated each invocation before sequential `upsert_citation` calls;
  storage failures and cancellation propagate without rollback or partial
  result construction.
- Preserved typed `NO_CONTEXT` and `UNMARKED` outcomes without clock or storage
  work.

No frozen interface or previous Phase 6 contract was modified. The engine has
no direct SQLite, Qdrant, SurrealDB, registry, retrieval, reranking, context,
answer-generation, or Module 6.10 dependency.

## Validation

| Gate | Result |
|---|---|
| Focused Module 6.9 tests | PASS — 33 tests |
| Phase 6.1–6.9 tests | PASS — 322 tests |
| Full `uv run pytest` | PASS — 1,100 passed, 1 skipped |
| Coverage | PASS — 90.104% |
| `uv run ruff format --check .` | PASS |
| `uv run ruff check .` | PASS |
| Production strict mypy | PASS — 85 source files |
| `uv run pre-commit run --all-files` | PASS |
| `git diff --check` | PASS |
| Package builds | PASS — core, server, email-ingestion |

The skipped test is the existing opt-in live Phase 4/5 acceptance. Pytest also
reported the existing Windows cache-cleanup permission warning after successful
execution; it did not change the passing test result.

## Real golden and persistence acceptance

Command:

```text
uv run python scripts/verify_module_6_9_citations.py
```

Evidence: `docs/milestone-evidence/module-6.9-citations.json`

| Measurement | Actual result |
|---|---|
| Corpus | `goldenDataset/Bhagavad-gita-As-It-Is.pdf` |
| SHA-256 | `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583` |
| Pipeline | real Modules 6.5 → 6.6 → 6.7 → 6.8 → 6.9 |
| Query | `What does the Bhagavad Gita teach about duty?` |
| Selected context items | 3 |
| Answer markers | repeated `[source:1]` |
| Citation count after deduplication | 1 |
| Citation ID | `8ccf1949-c704-5d44-8c31-4c23382100eb` |
| Canonical chunk | `3c8dcb0bfba173029ff590e6a064178743aefe9ee0b73dbcd5821ad9efef53dd` |
| Exact page / quote characters | 24 / 1,768 |
| Persistence route | `CompositeStorage` → `SQLiteStore` |
| SQLite reload count | 1 |
| Deterministic repeated upsert | PASS |
| Exact quote and document/version | PASS |
| Exact provenance object retention | PASS |
| Citation resolution | 0.0014 s |
| Total acceptance | 15.3100 s |

The runner rebuilt the real Module 6.5 fusion, pinned Module 6.6 reranking,
ADR-0043 context, and ADR-0044 answer handoff. It provisioned a separate
temporary SQLite database, persisted the caller-owned assistant turn first,
then exercised citation writes and reloads through `CompositeStorage`.
Historical M4/M5 and retrieval acceptance databases were not mutated.
