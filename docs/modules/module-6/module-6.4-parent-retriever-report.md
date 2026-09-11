# Module 6.4 ParentRetriever Verification Report

## Status

Module 6.4 is **COMPLETE and locally validated** under accepted ADR-0040.
Module 6.5 is not started and milestone M6 is not verified.

## Architecture and implementation

- Added the runtime-checkable `ParentPromotionInterfaceV1` protocol and
  `ParentPromotionCapabilities`.
- `ParentRetriever` is a thin asynchronous transformation with only an injected
  `StorageInterfaceV1` dependency. It does not implement `RetrieverInterfaceV1`
  and has no backend-specific imports.
- Promotion is source-local, single-pass, deterministic, and non-recursive.
- Canonical parents and sibling families are loaded only through deduplicated,
  bounded `StorageInterfaceV1.get_chunk()` calls.
- Complete families use exact `(document_id, version_id)` identity and symmetric,
  self-excluding sibling sets. Corruption raises `IntegrityError`; storage
  failures propagate.
- The earliest represented child supplies the promoted parent's unchanged raw
  score and source. Replacement preserves position and recomputes contiguous
  local ranks without global sorting.
- PluginRegistry exposes a separate versioned `parent_promotion` family with
  the existing priority, conflict, descriptor, and freeze semantics.

Frozen `RetrieverInterfaceV1`, `StorageInterfaceV1`, `Chunk`, `ScoredChunk`,
and `MetadataFilter` contracts were not modified.

## Validation

Focused Module 6.4 unit tests:

- Command: `uv run pytest mnemo-core/tests/unit/test_parent_retriever.py -q --no-cov`
- Result: **34 passed**

Combined interface, registry, promoter, and real-storage focused tests:

- Command: `uv run pytest mnemo-core/tests/unit/test_parent_retriever.py mnemo-core/tests/integration/test_parent_retriever_storage.py mnemo-core/tests/unit/test_registry.py mnemo-core/tests/unit/test_interface_protocols.py mnemo-core/tests/unit/test_interface_types.py mnemo-core/tests/unit/test_phase1_baseline.py -q --no-cov`
- Result: **102 passed**

Real storage:

- Path: `ParentRetriever → CompositeStorage.get_chunk() → SQLiteStore.get_chunk()`
- Dedicated temporary SQLite tests: **2 passed**
- Validated stored parent/sibling reconstruction, exact version identity,
  unchanged score/source/rank, and explicit missing-relationship failure.

Full repository:

- `uv run pytest`: **887 passed, 1 skipped**
- Coverage: **90.42%**
- `uv run ruff format --check .`: PASS
- `uv run ruff check .`: PASS
- Production strict mypy: PASS
- `uv run pre-commit run --all-files`: PASS
- `git diff --check`: PASS

## Golden corpus acceptance

- Command: `uv run python scripts/verify_module_6_4_parent.py`
- Dataset: `goldenDataset/Bhagavad-gita-As-It-Is.pdf`
- SHA-256: `ff112b0b056d303b792f6f2e68cbd73a89adf612fa9113f932446cdea7741583`
- Document type: BOOK
- Real chunks stored in isolated SQLite: **1,275**
- Canonical stored parent families: **0**
- Candidate stream: first **100** real chunks
- Returned chunks: **100**, identities/order unchanged
- Relationship lookups: **0** per run
- Promotion latency: **0.000343 seconds**
- Full parse/chunk/store/validation time: **45.211 seconds**
- Deterministic repeat: PASS
- Verdict: **PASS for the hierarchy the corpus actually contains**

The verified M4 corpus deliberately has 1,275 roots: BookChunker advertises
`supports_parent_child=False` and preserves authored hierarchy in
`heading_path`. It therefore cannot honestly demonstrate a promoted family.
The mandatory 1/4, 2/4, 3/4, 4/4, sole-child, version, corruption, ordering,
and lookup-efficiency semantics are covered by controlled canonical fixtures,
including real SQLite persistence. No parent relationship was fabricated and
the golden corpus was not changed.

## Files

- `mnemo-core/mnemo/interfaces/parent_promotion.py`
- `mnemo-core/mnemo/interfaces/types.py`
- `mnemo-core/mnemo/interfaces/versions.py`
- `mnemo-core/mnemo/interfaces/__init__.py`
- `mnemo-core/mnemo/retrieval/parent.py`
- `mnemo-core/mnemo/retrieval/__init__.py`
- `mnemo-core/mnemo/registry.py`
- `mnemo-core/tests/unit/test_parent_retriever.py`
- `mnemo-core/tests/integration/test_parent_retriever_storage.py`
- `scripts/verify_module_6_4_parent.py`

No Module 6.5 implementation, fusion, RRF, global ranking, version bump, tag,
release, commit, or push was performed.
