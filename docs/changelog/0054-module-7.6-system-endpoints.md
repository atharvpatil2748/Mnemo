# Changelog: 0054 — Module 7.6: System Endpoints

- **Date:** 2026-08-16
- **Module:** Phase 7, Module 7.6 (System Endpoints)
- **Status:** COMPLETED

---

## 1. Summary of Changes

Module 7.6 implements the complete suite of system-level REST endpoints for `mnemo-server` in strict compliance with Architecture §5.1, ADR-0049, ADR-0050, and ADR-0051:

1. **Subsystem Health Probing (`GET /v1/health` and `/health`):**
   - Implemented aggregated health check inspecting `KnowledgeEngine.state`, storage backend status (`StorageInterfaceV1.health_check()`), embedding provider status (`EmbeddingProviderV1.health_check()`), LLM provider status across primary roles, and tokenizer readiness.
   - Preserved `/health` top-level route as an alias for Kubernetes/container orchestration liveness and readiness probes.

2. **Configuration Serialization & Secret Redaction (`GET /v1/config`):**
   - Serialized active server transport settings (`host`, `port`, `cors_origins`, `log_level`, `max_upload_bytes`).
   - Serialized core storage, LLM, embedding, reranker, and plugin configurations while explicitly redacting all credentials and passwords (e.g. `api_key_configured: bool`, SurrealDB password masked).

3. **Model Inventory (`GET /v1/config/models`):**
   - Exposed structured breakdown of configured models across LLM roles (`planner`, `synthesizer`, `extractor`, `classifier`), embedding, and reranking.

4. **Runtime Hot Reload (`PATCH /v1/config`):**
   - Enabled in-place mutation of mutable server settings (`log_level`, `max_upload_bytes`, `cors_origins`).
   - Rejects empty payload with `422 Unprocessable Entity` (`ContractValidationError`).
   - Rejects unknown fields with `422 Unprocessable Entity` (`extra="forbid"`).

5. **Asynchronous Background Job Tracking (`GET /v1/jobs` and `GET /v1/jobs/{job_id}`):**
   - Implemented thread-safe in-memory `JobService` tracking lifecycle state (`queued`, `running`, `completed`, `failed`, `cancelled`), progress (0.0 to 1.0), status messages, and metadata.
   - Supported keyset pagination (`cursor`, `limit`) and status filtering.
   - Paved the transport interface for Phase 10 background worker integration.

---

## 2. Verification

- **Workspace Tests:** 1,277 passed, 1 skipped, 0 failures.
- **Coverage:** 90.33% total workspace line and branch coverage (enforcing $\ge 90.00\%$).
- **Linting & Formatting:** `ruff format` and `ruff check` 100% clean.
- **Static Typing:** `mypy --strict` 100% clean across all 131 source files.
- **Packaging:** `uv build --package mnemo-server` succeeded clean.
- **Frozen Boundaries:** 0 changes to `mnemo-core/`, `plugins/`, and `docs/adr/ADR-0001` through `ADR-0051`.
