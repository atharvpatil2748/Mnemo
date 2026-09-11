# 0049b — Phase 7, Module 7.1: Application Foundation

- **Date:** 2026-08-16
- **Status:** COMPLETED
- **Module:** Phase 7, Module 7.1 (Application Foundation)

---

## 1. Overview & Objectives

Module 7.1 established the application foundation for `mnemo-server` (Layer 2), implementing the FastAPI application factory, asynchronous ASGI lifespan context manager, dependency injection architecture, CORS middleware, and deterministic ADR-0049 error translation.

---

## 2. Key Deliverables

- **Application Factory (`create_app`):** Configures FastAPI with OpenAPI metadata, CORS middleware, and ADR-0049 exception handlers.
- **Lifespan Manager (`lifespan`):** Manages single `KnowledgeEngine` process singleton, executes off-thread BPE tokenizer provisioning, transitions engine state, and gracefully shuts down on termination.
- **Dependency Injection (`get_engine`, `get_token_counter`, `get_job_service`):** Provides safe access to initialized engine components without mutating domain boundaries.
- **Standard Error Mapping (ADR-0049):** Translates all `mnemo-core` domain exceptions (`ContractValidationError`, `NotFoundError`, `ConflictError`, `StorageError`, etc.) into structured JSON error envelopes with standardized status codes.
- **Process Configuration (`ServerConfig`):** Independent Pydantic V2 configuration model loaded from `MNEMO_SERVER_*` environment variables.
