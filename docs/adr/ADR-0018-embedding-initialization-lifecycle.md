# ADR-0018: Phase 5 Embedding Initialization Lifecycle

- **Status:** Accepted
- **Date:** 2026-08-12
- **Decision owners:** Mnemo maintainers
- **Scope:** Phase 5, Module 5.1
- **Depends on:** ADR-0002, ADR-0004
- **Related documents:** `mnemo_architecture_v2.md`, `mnemo_engineering_roadmap.md`

## 1. Context

Module 5.1 requires `OllamaEmbedder` to perform a real asynchronous probe of
the Ollama model during engine startup to discover and cache the actual vector
dimensions — rather than blindly trusting a statically configured value.

This created a lifecycle contradiction with the frozen Phase 1 architecture:

- `EmbeddingProviderV1.dimensions` is a **synchronous** property.
- `KnowledgeEngine._compose_runtime()` is synchronous and calls
  `_resolve_providers()`, which reads `provider.dimensions` synchronously.
- Actual Ollama dimension discovery requires **asynchronous** network I/O.
- `asyncio.run()` cannot be called inside an already-running event loop.

The constraint is: Phase 1 contracts are frozen. `EmbeddingProviderV1` may not
be modified. `KnowledgeEngine` must not perform blocking I/O.

## 2. Candidate Solutions

### Option A — Lazy Dimension Discovery (Provisional)

Return the configured value from `dimensions` until the first `embed()` call,
then perform lazy discovery and validate. Fails fast only on first use, not on
startup.

- **Does not satisfy** the roadmap requirement: "Query the model on init".
- Defers failures to ingestion time rather than startup.

### Option B — Modify `EmbeddingProviderV1`

Add `async def initialize() -> None` to `EmbeddingProviderV1` and have
`KnowledgeEngine.initialize()` await it before resolving providers.

- **Rejected**: Modifies frozen Phase 1 contract.

### Option C — Preflight Discovery Interface

Introduce a separate discovery protocol called before provider resolution.

- **Rejected**: High engine impact, modifies plugin resolution flow, breaks
  Phase 1 lifecycle semantics.

### Option D — Startup Hooks at Registry/Engine Boundary

Extend `PluginRegistry` with an **async startup hook** mechanism:

- Plugins register async callbacks via `register_startup_hook(coro_fn)`.
- `KnowledgeEngine.initialize()` awaits all hooks between `_compose_runtime()`
  and `_resolve_providers()`.
- `OllamaEmbedder` registers `initialize()` as a startup hook and uses it to
  perform the Ollama probe and cache `_discovered_dimensions`.
- `provider.dimensions` is **not accessed until after hooks complete**.

This satisfies all constraints:

- `EmbeddingProviderV1` is not modified.
- `KnowledgeEngine` initialization remains semantically clean.
- Hooks run before capability validation — exactly as required.
- Plugin authors gain a general safe async startup mechanism.

## 3. Decision

**Option D** is accepted and implemented.

### Implemented lifecycle (verified in code)

```
KnowledgeEngine.initialize()
    ↓
_compose_runtime()
    ↓  plugins discovered, startup hooks registered
await execute_startup_hooks()
    ↓
OllamaEmbedder.initialize()
    ↓  health_check → probe → discover real dimensions
_discovered_dimensions populated
    ↓
_resolve_providers()
    ↓  provider.dimensions read (now safe)
dimension compatibility validated
    ↓
engine READY
```

### Invariant

`OllamaEmbedder.dimensions` raises `RuntimeError` if accessed before
`initialize()` completes. This prevents accidental lazy fallback.

### Implementation files

- `mnemo/registry.py` — `register_startup_hook()`, `execute_startup_hooks()`
- `mnemo/engine.py` — `_builtin_plugins()` registers the hook; `initialize()`
  awaits hooks before `_resolve_providers()`
- `mnemo/embeddings/ollama.py` — `initialize()` probes model and caches
  `_discovered_dimensions`

## 4. Consequences

- **Positive**: No frozen contract changes. Fails fast on misconfigured
  models or unreachable Ollama at startup.
- **Positive**: Startup hook mechanism is general — future async providers
  can use the same pattern.
- **Neutral**: Hook execution is sequential. Parallel hooks can be added
  later if needed.
- **Negative**: Plugin authors must know to use `register_startup_hook` for
  any async initialization that precedes capability validation.
