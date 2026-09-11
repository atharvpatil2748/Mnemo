# mnemo-server

> Layer 2 Transport Adapter, REST API & Model Context Protocol (MCP) Server for the Mnemo Local Knowledge Engine.

`mnemo-server` provides HTTP/REST, legacy V1 WebSocket/SSE, and **Model Context Protocol (MCP)** transport adapters for `mnemo-core`. Built with **FastAPI**, **Uvicorn**, and the standard **Model Context Protocol SDK**, it also contains the server-owned certified V2 composition, principal/authorization boundary, capability reporting, delivery adapters, and separate FinalQA operational-store wiring. Phase 8.8 must converge every externally exposed transport and tunnel on that certified composition; code registration alone is not readiness or certification evidence.

---

## Capabilities

- **REST API (`/v1`):**
  - **Notebooks:** CRUD operations, activity timeline events, entity graph queries, and persisted summaries.
  - **Sources:** Multipart document ingestion with automatic deduplication, keyset pagination, deletion, and status polling.
  - **Query & Search:** Transient preview retrieval/synthesis (`POST /v1/query`), persisted citation-strict publication (`POST /v1/notebooks/{id}/final-qa`), and configured sparse/optional-dense search (`POST /v1/search`).
  - **Sessions & Notes:** Multi-turn conversation history, turn appending with citation retention, and note management with Last-Write-Wins timestamps.
  - **System:** Subsystem health checks (`/health` and `/v1/health`), model inventory (`/v1/config/models`), and secret-redacted configuration introspection/reload (`/v1/config`).
  - **Bounded delivery (`/v2`):** Exact-version document blocks, original bytes, chunks, asset occurrences/content, OCR/vision evidence, Final-QA V2 snapshot evidence, and capability discovery.
- **Streaming Protocols:**
  - **Legacy V1 WebSocket (`/ws/query`):** Real-time 5-event streaming query protocol (`retrieval_start`, `chunk_retrieved`, `synthesis_token`, `citations_ready`, `done`) with ping/pong heartbeat. It is not silently treated as the authenticated V2 chat contract required before Phase 9.
  - **Server-Sent Events (`POST /v1/query/stream`):** Standard HTTP SSE event streaming.
- **Model Context Protocol (MCP) Server:**
  - Registers six retained knowledge tools for AI assistants:
    - `query_notebook`: Grounded question-answering with citations and optional evidence-only retrieval (`synthesize=false`).
    - `search_all_notebooks`: Ranked semantic/keyword search across all notebooks.
    - `list_notebooks`: Discovers accessible notebooks with source counts.
    - `get_notebook_summary`: Retrieves persisted notebook summaries and source inventories.
    - `get_source_insights`: Extracts structured insights for a specific source.
    - `get_timeline`: Retrieves chronologically sorted notebook activity events.
  - Adds four bounded delivery tools without changing the original six:
    - `get_document`
    - `get_document_chunk`
    - `get_asset`
    - `get_image_analysis`
  - Adds four V2 tools without changing the retained ten:
    - `search_evidence`
    - `query_structured`
    - `run_final_qa_v2`
    - `get_capabilities`
  - Current registered total: **14 tools**. Phase 8.8 plans `search_images` as
    the fifteenth tool for OCR, caption/Vision, CLIP text-to-image, and governed
    hybrid discovery. It is not currently registered or exposed.
  - Dual-transport support: standard input/output (`stdio`) and Server-Sent Events (`sse`).
- **Authentication Middleware:**
  - Three configurable modes: `none` (local single-user default), `api-key` (constant-time header validation), and `jwt` (RFC 7519 HMAC-SHA verification).
  - Certified V2 remote operations require a transport-authenticated,
    server-derived principal. Phase 8.8 completes central authorization across
    the full remotely exposed MCP surface and rejects client principal/model/
    reranker/store policy overrides.
- **CLI Utilities:**
  - `mnemo serve`: Start the HTTP/REST and WebSocket ASGI server.
  - `mnemo-mcp`: Run the Model Context Protocol (MCP) server (`--transport stdio` or `--transport sse`).
  - `mnemo check`: Validate server configuration and inspect active settings.
  - `mnemo provision-tokenizer`: Install the canonical BPE tokenizer asset.
  - `mnemo --version`: Display package version.

---

## Current phase boundary

- Phase 8.5: completed and certified for the exact 44-document V2 production identity.
- Phase 8.6: validated evaluation notebook; not production-exposed.
- Phase 8.7: completed retrospective 14-tool capability milestone.
- Phase 8.8: designed, not implemented; owns runtime convergence, compatible
  readers, authorization, metadata, capability/error truth, tunnel parity,
  `search_images`, and Phase 9 readiness.
- Phase 9: planned and blocked until `Phase 8.8 VERIFIED → Phase 9 GO`.

See the [current architecture](../docs/architecture/current/mnemo_architecture_v2.md)
and [engineering roadmap](../docs/architecture/current/mnemo_engineering_roadmap.md).

---

## Quick Start

### 1. Install & Provision Tokenizer

```console
# Provision the BPE tokenizer asset
mnemo provision-tokenizer
```

### 2. Start the HTTP/REST Server

```console
# Start with default local configuration (port 8000)
mnemo serve

# Start with custom host, port, and API key authentication
mnemo serve --host 0.0.0.0 --port 8000 --auth-mode api-key --api-key my-secret-key
```

### 3. Run the Native MCP Server

```console
# Run over stdio (for Antigravity, Claude Desktop, Cursor)
mnemo-mcp --transport stdio

# Run over SSE (port 8001)
mnemo-mcp --transport sse --host 127.0.0.1 --port 8001
```

### 4. Check Server Health

```console
curl -s http://127.0.0.1:8000/health
```

---

## Configuration

`mnemo-server` is configured via `MNEMO_SERVER_*` environment variables:

| Variable | Default | Description |
|---|---|---|
| `MNEMO_SERVER_HOST` | `127.0.0.1` | Host address to bind. |
| `MNEMO_SERVER_PORT` | `8000` | Port to listen on. |
| `MNEMO_SERVER_CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | Allowed CORS origins. |
| `MNEMO_SERVER_LOG_LEVEL` | `info` | Server log verbosity (`info`, `debug`, etc.). |
| `MNEMO_SERVER_MAX_UPLOAD_BYTES` | `52428800` (50MB) | Max upload payload size in bytes. |
| `MNEMO_SERVER_AUTH_MODE` | `none` | Authentication mode (`none`, `api-key`, `jwt`). |
| `MNEMO_SERVER_API_KEY` | `None` | Static key for `api-key` auth mode. |
| `MNEMO_SERVER_JWT_SECRET` | `None` | Shared HMAC secret for `jwt` auth mode. |
| `MNEMO_SERVER_JWT_ALGORITHMS` | `HS256` | Allowed JWT signing algorithms. |
| `MNEMO_MCP_TRANSPORT` | `stdio` | Default transport for MCP server (`stdio`, `sse`). |
| `MNEMO_MCP_HOST` | `127.0.0.1` | Host address for MCP SSE transport. |
| `MNEMO_MCP_PORT` | `8001` | Port for MCP SSE transport. |
