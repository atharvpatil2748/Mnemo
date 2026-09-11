# ADR-0049: Phase 7 Server Application Architecture

- **Status:** ACCEPTED
- **Date:** 2026-08-16
- **Scope:** Phase 7 Module 7.1
- **Clarifies:** `mnemo_architecture_v2.md` §5 (Layer 2 — mnemo-server)
- **Extends:** ADR-0002, ADR-0003, ADR-0004, ADR-0046, ADR-0047

## Context

Phase 7 introduces `mnemo-server` as the HTTP/ASGI transport adapter over the
frozen `mnemo-core` M0–M6 baseline. The core domain library (`mnemo-core`) is
pure Python and contains no HTTP, ASGI, or transport logic. `mnemo-server`
serves as Layer 2 in the 4-layer architecture, translating HTTP/REST and
WebSocket requests into typed `mnemo-core` function invocations.

Phases 0 through 6 are formally closed and frozen. `mnemo-server` must adapt
to the existing frozen contracts and composition root (`KnowledgeEngine`)
without modifying any code or ADR in Phases 0–6.

## Decisions

### 1. Framework and ASGI Host
`mnemo-server` is built using **FastAPI** (Python 3.12+) and hosted on **Uvicorn**
as the ASGI server.

### 2. Application Lifespan
The FastAPI root application manages its lifecycle using an ASGI `lifespan`
context manager. The lifespan is entered once upon ASGI startup and exited upon
ASGI shutdown.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 1. Load ServerConfig and MnemoConfig
    # 2. Provision tokenizer off-thread if needed
    # 3. Instantiate KnowledgeEngine(config, final_qa_components=...)
    # 4. await engine.initialize()
    # 5. Store engine in app.state.engine
    yield
    # 6. await engine.shutdown()
```

### 3. KnowledgeEngine Ownership and Process Singleton
The ASGI `lifespan` owns exactly one `KnowledgeEngine` instance per server
process. `KnowledgeEngine` remains the sole domain composition root.
`mnemo-server` does not bypass `KnowledgeEngine` or instantiate core domain
components directly.

`app.state.engine` is assigned only after `engine.initialize()` succeeds and the
engine reaches `EngineState.READY`. If initialization fails, the engine is
cleaned up via frozen lifecycle semantics, `app.state.engine` remains unset, and
the lifespan startup raises to prevent serving traffic in a partial or broken state.

During shutdown, `await engine.shutdown()` is called, transitioning the engine to
`EngineState.STOPPED`.

### 4. Thin Adapter Boundary
`mnemo-server` contains **no domain business logic**. It performs no retrieval,
parsing, chunking, reranking, storage mutations, or QA generation directly.
Every endpoint handler is strictly a translation layer between HTTP requests and
`mnemo-core` calls. Any domain logic discovered in `mnemo-server` is a bug.

### 5. Server Configuration Separation
`ServerConfig` is strictly separated from `MnemoConfig`. Under ADR-0003 §10,
`MnemoConfig` must not depend on or include server/HTTP configuration.
`ServerConfig` manages process-level transport settings:
- `host: str` (default: `"127.0.0.1"`)
- `port: int` (default: `8000`)
- `cors_origins: tuple[str, ...]` (default: `("http://localhost:3000", "http://127.0.0.1:3000")`)
- `log_level: str` (default: `"info"`)

`ServerConfig` is a frozen Pydantic model loaded from environment variables
prefixed with `MNEMO_SERVER_` or explicit constructor arguments.

### 6. Dependency Injection via `get_engine`
Route handlers obtain the engine via FastAPI dependency injection:

```python
def get_engine(request: Request) -> KnowledgeEngine:
    engine = getattr(request.app.state, "engine", None)
    if engine is None or engine.state is not EngineState.READY:
        raise DependencyUnavailableError("KnowledgeEngine is not ready")
    return engine
```

`get_engine` never instantiates or mutates an engine. If the engine is missing
or not `READY`, it raises `DependencyUnavailableError`, which the global
exception handler translates to `503 Service Unavailable`.

### 7. Tokenizer Provisioning Safety
`O200KBaseTokenCounter` requires the canonical tokenizer asset. The provisioning
utility (`provision_tokenizer()`) performs file and network I/O.
**Blocking tokenizer provisioning MUST NOT execute directly on the asyncio event
loop.** When invoked during asynchronous startup, it must run via
`asyncio.to_thread` or in a synchronous pre-startup phase.

### 8. Multi-Worker and Concurrency Semantics
- **Single-Worker Default:** Single-worker deployment (`uvicorn --workers 1`) is
  the recommended default for local-first deployment.
- **Multi-Worker Considerations:** Running multiple Uvicorn worker processes
  creates separate Python processes, each with its own `KnowledgeEngine` instance.
  All instances share the underlying storage (SQLite WAL, Qdrant, SurrealDB).
  SQLite WAL mode allows concurrent readers but serializes writers (guarded by
  `PRAGMA busy_timeout = 30000`). Multi-worker deployment is not forbidden by
  the architecture, but operators must account for SQLite write serialization.

### 9. WebSocket Lifecycle Compatibility
WebSocket endpoints (Module 7.7) share the same FastAPI application and
`KnowledgeEngine` lifecycle as REST endpoints. WebSocket streaming details are
deferred to Module 7.7.

### 10. HTTP Error Envelope and Mapping
All exceptions originating from `mnemo-core` or the HTTP transport layer are
translated into a standard JSON error response:

```json
{
  "error": {
    "code": "contract.validation",
    "message": "Detailed error message",
    "details": {},
    "retryable": false
  }
}
```

The error mapping table is defined as follows:

| Exception Class | HTTP Status Code | Default `code` | Retryable | Rationale |
|---|---|---|---|---|
| `ContractValidationError` | `422 Unprocessable Entity` | `contract.validation` | `false` | Caller provided invalid data violating contract invariants. |
| `NotFoundError` | `404 Not Found` | `contract.not_found` | `false` | Requested resource/identity does not exist. |
| `ConflictError` | `409 Conflict` | `contract.conflict` | `false` | Optimistic locking or state conflict. |
| `UnsupportedError` | `400 Bad Request` | `contract.unsupported` | `false` | Requested capability or format is unsupported by configuration. |
| `IntegrityError` | `500 Internal Server Error` | `contract.integrity` | `false` | Internal data or relationship integrity violation. |
| `LifecycleError` / `EngineLifecycleError` | `503 Service Unavailable` | `contract.lifecycle` / `engine.lifecycle` | `true` | Component or engine is not in a valid state to handle requests. |
| `DependencyUnavailableError` / `EngineInitializationError` | `503 Service Unavailable` | `contract.dependency_unavailable` / `engine.initialization` | `true` | Required backend/provider or engine initialization is unavailable. |
| `OperationTimeoutError` | `504 Gateway Timeout` | `contract.timeout` | `true` | Operation deadline expired. |
| `OperationCancelledError` | `499 Client Closed Request` | `contract.cancelled` | `false` | Request was cancelled by caller or context. |
| `StorageError` | `503 Service Unavailable` | `contract.storage` | `true` | Storage backend connection or operation failure. |
| `PluginError` | `500 Internal Server Error` | `contract.plugin` | `false` | Plugin boundary failure. |
| `KnowledgeEngineError` (base) | `500 Internal Server Error` | `engine.error` | `false` | Unclassified engine error. |
| `MnemoInterfaceError` (base) | `500 Internal Server Error` | `interface.error` | `false` | Unclassified core interface error. |
| `RequestValidationError` (FastAPI) | `422 Unprocessable Entity` | `http.validation` | `false` | HTTP schema validation failure. Details contains field errors. |
| `HTTPException` / `StarletteHTTPException` | `status_code` | `http.error` | `502/503/504` | Standard HTTP exceptions passed with original status code. |
| `Exception` (unexpected) | `500 Internal Server Error` | `internal.error` | `false` | Unhandled error. Message is sanitized; stack traces/paths are omitted. |

### 11. Immutability of Frozen Phases
No file or ADR in Phases 0 through 6 is modified. `mnemo-core` has no dependency
on `mnemo-server`, `FastAPI`, `Starlette`, or `Uvicorn`.

## Dependency Boundaries

```
Layer 3: mnemo-ui
   │ HTTP / JSON / WebSocket
Layer 2: mnemo-server (FastAPI, ServerConfig, dependencies, error handlers)
   │ Python API calls
Layer 1: mnemo-core (KnowledgeEngine, frozen models, interfaces, storage)
```

## Consequences

- `mnemo-server` provides a clean, decoupled transport adapter over `mnemo-core`.
- Exception translation is uniform, deterministic, and preserves frozen core error codes.
- Engine lifecycle is tightly managed through ASGI lifespan without global singletons.
- Local deployment remains lightweight, private, and offline-capable.
