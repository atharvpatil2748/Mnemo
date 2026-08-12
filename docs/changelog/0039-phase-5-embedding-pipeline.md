# Phase 5 — Embedding Pipeline

**Release:** v0.20.0  
**Date:** 2026-08-12  
**Modules:** 5.1, 5.2, 5.3  
**ADR:** ADR-0018 (Embedding Initialization Lifecycle)

---

## Summary

Phase 5 delivers the complete embedding pipeline for `mnemo-core`. Chunks can
now be converted to float vectors via a locally running Ollama instance, cached
content-addressably in SQLite, and orchestrated in parallel batches through the
`EmbedderModule`.

---

## Module 5.1 — Ollama Embedding Provider

**File:** `mnemo/embeddings/ollama.py`

Implements `OllamaEmbedder`, a concrete `EmbeddingProviderV1` that calls the
Ollama `/api/embeddings` endpoint via `httpx`.

### Key decisions

- **ADR-0018 Option D**: Rather than modifying the frozen `EmbeddingProviderV1`
  interface, `OllamaEmbedder.initialize()` is registered as a startup hook via
  `PluginRegistry.register_startup_hook()`. The engine awaits all hooks before
  calling `_resolve_providers()`, ensuring dimension discovery happens before
  capability validation.
- `dimensions` raises `RuntimeError` if accessed before `initialize()`, making
  premature access fail explicitly.
- Exponential backoff with 3 retries on transient `httpx.ConnectError` or
  `httpx.TimeoutException`. Deterministic 4xx/5xx errors are not retried.
- `health_check()` probes the `/api/tags` endpoint and verifies the configured
  model is listed.

### Lifecycle order (verified)

```
_compose_runtime()
    ↓  hooks registered
await execute_startup_hooks()
    ↓  OllamaEmbedder.initialize()
    ↓  health_check → probe → _discovered_dimensions set
_resolve_providers()
    ↓  dimensions read (safe)
engine READY
```

---

## Module 5.2 — Embedding Cache

**Files:** `mnemo/interfaces/cache.py`, `mnemo/storage/cache.py`,
`mnemo/embeddings/cached.py`

### `CacheInterfaceV1`

Generic `Protocol[K, V]` for any content-addressable cache. Supports `get`,
`put`, `delete`, `clear_namespace`.

### `SQLiteEmbeddingCache`

SQLite-backed cache storing vectors as little-endian `struct`-packed BLOBs.

- Schema: `embedding_cache(key TEXT PK, dimensions INT, vector BLOB, expires_at TEXT)`
- WAL mode and `NORMAL` synchronous mode for performance.
- Optional TTL via ISO 8601 `expires_at`.
- `BEGIN IMMEDIATE` write transactions for concurrency safety.
- Blob integrity validation on read — raises `IntegrityError` on corruption.

### `CachedEmbeddingProvider`

Decorator wrapping any `EmbeddingProviderV1` with transparent caching.

- Cache key: `sha256(text.encode("utf-8")).hexdigest() + "::" + model_name`
- Single embed: cache lookup → provider call on miss → cache write.
- Batch embed: per-item lookup, collect misses, one provider call for miss
  batch, write results, reconstruct ordered output.
- Dimension validation on every vector (cached or live) raises `IntegrityError`.

---

## Module 5.3 — Embedder Module

**File:** `mnemo/embeddings/embedder.py`  
**Export:** `mnemo/embeddings/__init__.py` → `EmbedderModule`

`EmbedderModule` orchestrates bulk embedding of `Chunk` sequences.

- Skips chunks that already have `embedding` set (idempotent).
- Splits remaining chunks into batches of `provider.capabilities().max_batch`.
- Dispatches all batches concurrently via `anyio.create_task_group` with an
  `anyio.CapacityLimiter` enforcing `max_concurrency`.
- Preserves the exact input order in the returned `tuple[Chunk, ...]`.
- Returns new frozen `Chunk` instances (via `dataclasses.replace`) — originals
  are not mutated.

---

## Registry Changes

**File:** `mnemo/registry.py`

- `register_startup_hook(hook: Callable[[], Awaitable[None]]) -> None`
- `execute_startup_hooks() -> None` (sequential)

**File:** `mnemo/engine.py`

- `CoreEmbeddingPlugin.register()` now calls `registry.register_startup_hook(ollama.initialize)`.
- `KnowledgeEngine.initialize()` awaits hooks between `_compose_runtime()` and
  `_resolve_providers()`.

---

## Dependency Change

- `anyio>=4.0` added as an explicit runtime dependency in `pyproject.toml`
  (was previously only transitive via `httpx`).

---

## Tests

| File | Tests | Coverage |
|---|---|---|
| `tests/unit/test_ollama_embedder.py` | 12 | OllamaEmbedder lifecycle, retry, health |
| `tests/unit/test_embedding_cache.py` | 10 | SQLiteCache CRUD/TTL/concurrency, CachedProvider |
| `tests/unit/test_embedder_module.py` | 5 | EmbedderModule batching, concurrency, idempotency |

All 27 Phase 5 tests pass. Full suite: 697 passed.

---

## Known Deferral

- **Question embedding** (roadmap task 5.3c): Generating separate question
  embeddings for named-vector storage in Qdrant is deferred to Phase 6, where
  the indexer and retriever implementations will define the concrete contract.
  The `EmbedderModule` API is designed to accommodate this extension without
  interface changes.

---

## Release Blockers

- M5 milestone exit criterion ("1000 chunks embedded via Ollama, stored in
  Qdrant") requires a live Ollama instance and is an integration-level
  acceptance test, not a unit test. It must be executed before the Phase 5
  release tag is applied.
- Version bump: `_version.py` and `pyproject.toml` must be updated from
  `0.19.0` → `0.20.0` at release time.
