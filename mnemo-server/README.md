# mnemo-server

> Layer 2 Transport Adapter & API Server for the Mnemo Local Knowledge Engine.

`mnemo-server` provides the HTTP/REST, WebSocket, and SSE streaming transport adapters for `mnemo-core`. Built with **FastAPI** and hosted on **Uvicorn**, it exposes typed, authenticated endpoints for notebook management, multi-format source ingestion, hybrid query/search retrieval, conversation memory, notes, and system introspection.

---

## Capabilities

- **REST API (`/v1`):**
  - **Notebooks:** CRUD operations, activity timeline events, entity graph queries, and persisted summaries.
  - **Sources:** Multipart document ingestion with automatic deduplication, keyset pagination, deletion, and status polling.
  - **Query & Search:** Full grounded answer generation with deterministic citations (`POST /v1/query`) and hybrid vector/FTS search (`POST /v1/search`).
  - **Sessions & Notes:** Multi-turn conversation history, turn appending with citation retention, and note management with Last-Write-Wins timestamps.
  - **System & Jobs:** Subsystem health checks (`/health` & `/v1/health`), model inventory (`/v1/config/models`), secret-redacted config introspection and hot reload (`/v1/config`), and asynchronous job tracking (`/v1/jobs`).
- **Streaming Protocols:**
  - **WebSocket (`/ws/query`):** Real-time 5-event streaming query protocol (`retrieval_start`, `chunk_retrieved`, `synthesis_token`, `citations_ready`, `done`) with ping/pong heartbeat.
  - **Server-Sent Events (`POST /v1/query/stream`):** Standard HTTP SSE event streaming.
- **Authentication Middleware:**
  - Three configurable modes: `none` (local single-user default), `api-key` (constant-time header validation), and `jwt` (RFC 7519 HMAC-SHA verification).
- **CLI Utilities:**
  - `mnemo serve`: Start the Uvicorn ASGI server.
  - `mnemo check`: Validate server configuration and inspect active settings.
  - `mnemo provision-tokenizer`: Install the canonical BPE tokenizer asset.
  - `mnemo --version`: Display package version.

---

## Quick Start

### 1. Install & Provision Tokenizer

```console
# Provision the BPE tokenizer asset
mnemo provision-tokenizer
```

### 2. Start the Server

```console
# Start with default local configuration (port 8000)
mnemo serve

# Start with custom host, port, and API key authentication
mnemo serve --host 0.0.0.0 --port 8000 --auth-mode api-key --api-key my-secret-key
```

### 3. Check Server Health

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
