# 0056 — Phase 7, Module 7.8: Authentication Middleware, CLI & Server Packaging

- **Date:** 2026-08-16
- **Status:** COMPLETED
- **Module:** Phase 7, Module 7.8 (Authentication Middleware, CLI & Server Packaging)

---

## 1. Overview & Objectives

Module 7.8 delivers authentication middleware (supporting `none`, `api-key`, and `jwt` modes), production CLI subcommands (`mnemo serve`, `mnemo check`, `mnemo provision-tokenizer`, `mnemo --version`), and containerized runtime deployment configuration for `mnemo-server`, completing Phase 7 and achieving **Milestone M7**.

---

## 2. Key Deliverables

### Authentication Middleware (`mnemo_server.auth.AuthMiddleware`):
- **`none` mode:** Default pass-through authentication for single-user local-first workflows.
- **`api-key` mode:** Constant-time `Authorization: Bearer <key>` or `X-API-Key: <key>` header validation using `hmac.compare_digest`.
- **`jwt` mode:** Cryptographic HMAC-SHA token verification (HS256, HS384, HS512) validating signatures, expiration (`exp`), and activation (`nbf`) claims.
- **Exempt Paths:** Health check (`/health`, `/v1/health`) and OpenAPI documentation routes (`/docs`, `/redoc`, `/openapi.json`) remain unauthenticated for monitoring and discovery.

### Production CLI (`mnemo_server.cli`):
- `mnemo serve`: Starts the Uvicorn ASGI server with configurable `--host`, `--port`, `--log-level`, `--auth-mode`, `--api-key`, `--jwt-secret`, `--reload`, and `--workers`.
- `mnemo check`: Introspects and validates server configuration, printing active settings with secret redaction.
- `mnemo provision-tokenizer`: Canonical BPE tokenizer asset downloader and importer.
- `mnemo --version`: Version output conforming to package version metadata.

### Deployment & Packaging:
- `docker/server.Dockerfile`: Production entrypoint configured with `mnemo serve --host 0.0.0.0 --port 8000` and HTTP health checking on `/health`.
- Distribution builds: Wheel and source distribution packages built cleanly via Hatchling.

---

## 3. Verification & Quality Gates

- **Test Suite:** 1,301 passed, 1 skipped, 0 failures.
- **Workspace Coverage:** 90.18% ($\ge 90.00\%$ requirement).
- **Linter & Formatter:** Ruff 100% clean across 236 files.
- **Type Checker:** Mypy `--strict` clean across 135 source files.
- **Package Build:** `uv build` succeeds across `mnemo-core`, `mnemo-server`, and `mnemo-email-ingestion`.
- **Frozen Core Boundary:** 0 modifications to `mnemo-core/`, `plugins/`, or `docs/adr/ADR-0001*`.
- **Milestone Achieved:** **[MILESTONE M7] All REST endpoints pass, WebSocket streaming works, Auth middleware verified.**
