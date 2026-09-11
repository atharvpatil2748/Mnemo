# Phase 8.5 WP-02 Gate Evidence

**Date:** 2026-08-26  
**Scope:** WP-02 derived projection generation and activation only  
**Verdict:** WP-02 COMPLETE

## Implementation

- Added `DerivedProjectionBuilderV1` and `DerivedProjectionStoreV1` without
  changing `StorageInterfaceV1`.
- Added deterministic `ProjectionGenerationSpec`, explicit `NOT_REQUIRED`,
  `PENDING`, `RUNNING`, `READY`, `STALE`, `FAILED`, and `INVALID` operational
  states, and explicit complete/partial coverage.
- Added one coordinator over the existing `index_generations` and
  `active_index_generations` registry. It validates exact profile/schema/scope/
  provider/model/revision/configuration/dimension/source identity before
  activation.
- Added immutable count/checksum coverage and source-generation/source-version
  manifests. A table being present or non-empty is not readiness evidence.
- Added idempotent builders for OCR FTS, Vision text FTS, visual vectors,
  language text FTS, and activation of existing multilingual vector rows.
- Operationalized structured table projection with complete coverage and a
  per-version active alias.
- Added governed `derived_projection_build` manifests and a lease-aware,
  checkpointed `ProcessingWorker` operation. Duplicate submissions converge;
  interrupted BUILDING rows can resume; cancellation/lease loss is checked
  before promotion.
- Added atomic rollback to a retained, checksum-valid complete generation.
- Integrated validated projection state with `Phase85RuntimeV1`. Provider
  readiness alone cannot activate a generation-backed service, and WP-02 does
  not set verification or certification.

## Schema and migration

The production implementation schema advances additively from v13 to v14.
Fresh creation and v13 upgrade create:

- `index_generation_sources`
- `index_generation_coverage`
- `vision_text_projection_rows` and `vision_text_fts`
- `language_text_projection_rows` and `language_text_fts`

Existing OCR, Vision, visual-embedding, multilingual-embedding, structured,
processing-job, canonical, and V1 tables are reused. Schema creation is
transactional; derived data is not built inside migration.

## Empty-projection diagnosis

The earlier evaluation path persisted some OCR/Vision/visual derivations but did
not consistently create a matching index generation, projection rows, coverage,
or active alias, and the WP-01 runtime intentionally had no generation-backed
service registration. Thus empty meant *not generated/not activated*, not a
successful zero-result projection. WP-02 now distinguishes that from a valid
generated-empty projection using an immutable zero-count coverage record.

No production/evaluation database was populated by WP-02. Current advanced
capabilities therefore remain inactive until an authorized operator submits the
exact configured generation.

## Safety and compatibility

- BUILDING, partial, failed, stale, coverage-missing, and checksum/count-mismatch
  generations cannot activate.
- Projection rows retain exact source generation/version IDs; OCR and visual
  stores reject source artifacts outside that immutable contract.
- Original and derived representations remain separate. Canonical documents,
  versions, sources, chunks, `Chunk.text`, FTS/title rows, and V1 embeddings are
  untouched by the new builders.
- Optional projection/provider failure is isolated from V1 retrieval.
- No HTTP/MCP behavior, model selection, Phase 11 planning, release metadata,
  or Qdrant enablement was added.
- Tests use temporary databases. A representative evaluation-corpus source is
  hashed before/after the isolated test; no corpus source was written.

## Focused validation

```text
uv run --project mnemo-core pytest --no-cov \
  mnemo-core/tests/unit/test_projection_generations.py \
  mnemo-core/tests/unit/test_processing_jobs.py \
  mnemo-core/tests/unit/test_ocr.py \
  mnemo-core/tests/unit/test_vision.py \
  mnemo-core/tests/unit/test_multilingual.py \
  mnemo-core/tests/unit/test_structured_retrieval.py \
  mnemo-core/tests/unit/test_phase85_runtime.py \
  mnemo-core/tests/unit/test_engine.py \
  mnemo-core/tests/unit/test_sqlite_store.py \
  mnemo-core/tests/unit/test_composite_storage.py -q
189 passed
```

The matrix covers identity changes, stale detection, missing/failed/partial/
empty generation semantics, dependency gating, optional-failure isolation,
concurrent duplicate build coordination, interrupted BUILDING resume,
processing-job idempotency/checkpoint/completion, source-contract enforcement,
checksum mismatch, promotion/rollback, schema fresh/upgrade/repeat/failure
rollback, OCR/Vision/visual/language/structured projections, runtime gating,
and engine/storage regressions.

```text
uv run --project mnemo-core pytest --no-cov \
  tests/governance/test_phase8_5_wp00_contracts.py -q
8 passed

uv run --project mnemo-core ruff format <WP-02 Python files>
17 files unchanged on the final pass

uv run --project mnemo-core ruff check <WP-02 Python files>
All checks passed

uv run --project mnemo-core mypy --strict <WP-02 production modules>
Success: no issues found in 10 source files

python -m json.tool docs/governance/contracts/phase8_5_capability_matrix.json
valid

git diff --check
passed
```

Pytest emitted only the known Windows cache-cleanup permission warning after
successful test completion.

## Not tested in WP-02

- No full 44-document generation/re-ingestion or model benchmark.
- No real external OCR/VLM/embedding provider invocation.
- No HTTP/MCP adapter or blind-agent behavior.
- No full repository regression, coverage gate, package build, or Phase 8.5
  certification; those remain later work packages and WP-17.

## Remaining ownership

- WP-03: MCP contracts/adapters.
- WP-04–WP-13: cursor, exact delivery, retrieval, multimodal/multilingual,
  multi-document, Final-QA V2, and HTTP application behavior.
- WP-14/WP-15: consolidated security and production profile/feature activation.
- WP-16/WP-17: behavioral verification and final certification.
