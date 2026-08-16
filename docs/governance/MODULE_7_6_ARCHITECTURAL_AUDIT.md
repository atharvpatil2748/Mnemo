# Module 7.6 — Architectural Audit

- **Module:** Phase 7, Module 7.6 (System Endpoints)
- **Status:** GREEN / READY FOR IMPLEMENTATION
- **Authoritative References:**
  - `docs/mnemo_engineering_roadmap.md` (Module 7.6)
  - `docs/mnemo_architecture_v2.md` §5.1 (System endpoints: health, config, config/models, jobs)
  - ADR-0049 (Phase 7 Server Application Architecture)
  - ADR-0050 (Notebook and Knowledge Graph REST API)
  - ADR-0051 (Sources and Document Ingestion REST API)
- **Date:** 2026-08-16

---

## 1. Scope Definition

Module 7.6 implements the complete suite of system-level REST endpoints in `mnemo-server`:

1. **`GET /v1/health` (and `/health` alias):**
   - Liveness and readiness inspection across system layers.
   - Probes `KnowledgeEngine.state`, storage backend connectivity (`StorageInterfaceV1.health_check()`), embedding provider connectivity (`EmbeddingProviderV1.health_check()`), language model connectivity (`LLMInterfaceV1.health_check()`), and tokenizer readiness.
   - Returns structured `HealthResponse` with per-component health statuses.

2. **`GET /v1/config`:**
   - Reads the active runtime configuration from `KnowledgeEngine.config` (`MnemoConfig`) and `ServerConfig`.
   - Redacts sensitive credentials (e.g. `api_key`, `password`) to prevent credential leakage.

3. **`GET /v1/config/models`:**
   - Provides an inventory of all active and configured models (LLM planner, synthesizer, extractor, classifier; embedding model & dimensions; reranker model).

4. **`PATCH /v1/config`:**
   - Updates mutable server-level configuration settings (`log_level`, `max_upload_bytes`, `cors_origins`).
   - Rejects empty payloads with `422 Unprocessable Entity`.
   - Reconfigures logging levels and server limits in-place.

5. **`GET /v1/jobs` & `GET /v1/jobs/{job_id}`:**
   - Returns status and progress for asynchronous background tasks.
   - Managed via an in-memory `JobService` in `mnemo-server` for Phase 7 single-process deployment, with keyset pagination and filtering, fully prepared for Phase 10 background worker infrastructure integration.

---

## 2. Core Capabilities & Existing Primitives Audit

| Requirement | Core / Server Primitive | Status |
|---|---|---|
| Engine State Inspection | `KnowledgeEngine.state` (`EngineState.READY`, `UNINITIALIZED`, etc.) | **AVAILABLE** |
| Storage Backend Health | `StorageInterfaceV1.health_check() -> tuple[HealthStatus, ...]` | **AVAILABLE** |
| Embedding Provider Health | `EmbeddingProviderV1.health_check() -> HealthStatus` | **AVAILABLE** |
| LLM Provider Health | `LLMInterfaceV1.health_check() -> HealthStatus` | **AVAILABLE** |
| Core Configuration | `KnowledgeEngine.config` (`MnemoConfig`) | **AVAILABLE** |
| Server Configuration | `ServerConfig.from_env()`, `app.state.server_config` | **AVAILABLE** |
| Background Job Tracking | `JobService` (in-memory state manager in `mnemo-server`) | **TO IMPLEMENT IN SERVER** |

---

## 3. Discrepancy & Reconciliation Analysis

1. **Inline Health Check Stub:**
   - *Finding:* Module 7.1 registered a minimal inline stub in `app.py` returning basic dictionary fields.
   - *Resolution:* Replace the inline stub with a dedicated `system_router` mounted at `/v1` and maintain the legacy top-level `/health` alias redirect/handler for backward compatibility.
2. **Secret Redaction in Config Endpoints:**
   - *Finding:* `MnemoConfig` contains storage configuration which may carry database passwords (`surrealdb.password`) or API keys (`qdrant.api_key`).
   - *Resolution:* Redact all secrets in DTO responses (`api_key_configured: bool`, passwords omitted or masked as `***`).
3. **Background Jobs vs Phase 10 Workers:**
   - *Finding:* Phase 10 (`Module 10.1 — Background Job Worker`) schedules the distributed job worker infrastructure (Celery/Redis/queues).
   - *Resolution:* Module 7.6 provides an in-memory `JobService` for tracking local async jobs (such as background ingestion/indexing), establishing the exact REST contract specified in Architecture §5.1 without prematurely introducing external queue dependencies.

---

## 4. Governance & Architecture Checklist

- **`MODULE_7_6_STATUS`**: READY FOR IMPLEMENTATION
- **`FROZEN_CORE_MODIFICATIONS_REQUIRED`**: NO (0 files in `mnemo-core/` to modify)
- **`NEW_ADR_REQUIRED`**: NO (Governed by Architecture §5.1, ADR-0049, ADR-0050, ADR-0051)
- **`IMPLEMENTATION_READY`**: YES
- **`BLOCKING_ISSUES`**: None
- **`HIGH_RISKS`**: None
- **`MEDIUM_RISKS`**: None
- **`LOW_RISKS`**: Ensuring clean secret redaction in config serialization.
