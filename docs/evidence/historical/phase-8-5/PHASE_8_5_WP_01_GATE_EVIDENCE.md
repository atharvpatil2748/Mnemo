# Phase 8.5 WP-01 Gate Evidence

**Date:** 2026-08-26  
**Scope:** WP-01 runtime composition and capability activation only  
**Verdict:** WP-01 COMPLETE

## Implementation

- Added the additive `Phase85RuntimeV1` and provider-readiness protocols.
- Added immutable capability, model-profile, provider-readiness, and runtime-readiness snapshots.
- Implemented the ordered `DECLARED -> CONFIGURED -> BUILDABLE -> READY -> ACTIVE -> EXPOSED -> VERIFIED -> CERTIFIED` lifecycle with invalid-state rejection.
- Added deterministic configuration fingerprinting and exact profile resolution from `MnemoConfig`/`mnemo.toml`.
- Added explicit provider registration and provider-owned readiness probes. Probe failures are isolated to the optional profile and expose safe reason codes.
- Added service registration with dependency, active-generation, exposure, behavioral-verification, security-verification, and certification gates.
- Composed exactly one `Phase85Runtime` inside `KnowledgeEngine`; V1 provider resolution remains the prerequisite and source of truth for active V1 profiles.
- Migrated the Phase 8.5.11 ingestion runner from the obsolete second model-file argument to the same engine-owned `mnemo.toml` profile snapshot.
- Exposed the runtime additively as `KnowledgeEngine.phase85` only while the engine is `READY`.
- Registered an available asset catalog as a buildable service, but dependency gating prevents false activation when its complete authorization/service bundle is not composed.
- Left derived providers configured but not ready/active when no production adapter and readiness probe is registered.

No schema migration, HTTP/MCP handler, projection build, corpus ingestion, benchmark,
model download, Phase 11 planning behavior, or release action was performed.

## Runtime truth at WP-01

The engine activates the already validated V1 ingestion/retrieval profiles and the
internal runtime/provenance registry. Optional OCR, Vision, visual-vector,
multilingual, multimodal, structured, exact-delivery, processing-worker, and
Final-QA V2 capabilities remain inactive unless their exact service/provider,
dependencies, policy, and generation requirements are supplied. Exposure,
verification, and certification are never inferred.

`mnemo.toml` resolves these configured, non-certified candidate profiles:

- Vision: `qwen2.5vl:latest`
- Multilingual embedding: `BAAI/bge-m3` (1024 dimensions)
- Multilingual reranker: `BAAI/bge-reranker-v2-m3`
- Visual embedding: `openai/clip-vit-large-patch14` (768 dimensions)
- V1 general LLM roles: `gemma4:e4b`

No OCR model profile exists in the authoritative production configuration, so the
runtime truthfully reports OCR as declared but not configured.

## Configuration and lifecycle evidence

- Equal `MnemoConfig` inputs produce the same SHA-256 configuration fingerprint.
- Model declaration, configuration, local availability, loadability,
  initialization, and activation are independent explicit states.
- Capability lifecycle transitions are monotonic.
- Certification requires both behavioral and security verification.
- Generation-backed capabilities cannot activate without a named active generation.
- Capability dependencies are evaluated fail-closed.
- An optional provider probe exception leaves required V1 capability readiness intact.
- Shutdown removes runtime access and resets optional provider readiness.

## Governance synchronization

The machine-readable capability matrix now includes every runtime capability ID,
including multilingual OCR/Vision and the independent behavioral/security
verification capabilities. Its `runtime_mapping` records how dynamic buildable,
ready, and active state maps to the governance snapshot without adding unsupported
`PASS` or `SUPPORTED` claims.

## Focused validation

Commands and results:

```text
uv run --project mnemo-core pytest --no-cov mnemo-core/tests/unit/test_phase85_runtime.py mnemo-core/tests/unit/test_engine.py tests/governance/test_phase8_5_wp00_contracts.py -q
36 passed

uv run ruff format <WP-01 Python files>
3 files reformatted; remaining files unchanged

uv run ruff check --fix <WP-01 Python files>
6 pre-existing/order findings in edited export/import blocks fixed; 0 remaining

uv run mypy --strict mnemo-core/mnemo/phase85 mnemo-core/mnemo/interfaces/phase85.py mnemo-core/mnemo/engine.py scripts/phase8_5_11_ingest.py
Success: no issues found in 6 source files
```

Pytest emitted an environment-specific cache cleanup warning for a denied Windows
temporary-directory symlink. It did not affect collection or test results.

Per the WP-01 execution policy, the full repository suite, corpus ingestion,
external provider calls, benchmarks, package builds, and behavioral MCP tests were
not run.

## Compatibility

- `StorageInterfaceV1` was not widened or changed.
- V1 engine provider resolution, retrieval, citation, Final-QA, HTTP/MCP, identity,
  and Qdrant-optional contracts were not changed.
- Existing engine focused tests pass with legacy protocol-shaped provider doubles.
- No production or Golden Corpus database was read, migrated, or modified by WP-01.
- No Phase 11 autonomous planning/replanning behavior was introduced.

## Remaining ownership

- WP-02 owns derived projection generation and atomic activation.
- WP-03/WP-13 own MCP/HTTP capability exposure.
- WP-14 owns the complete security verification matrix.
- WP-15 owns production feature-flag/profile operationalization beyond the current
  authoritative `mnemo.toml` contract.
- WP-16 owns behavioral verification; WP-17 owns certification.
