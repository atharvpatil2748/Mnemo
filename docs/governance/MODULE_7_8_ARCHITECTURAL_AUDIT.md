# Module 7.8 — Architectural Audit: Authentication Middleware, CLI & Server Packaging

- **Module:** Phase 7, Module 7.8 (Authentication Middleware, CLI & Server Packaging)
- **Status:** GREEN
- **Date:** 2026-08-16

---

## 1. Scope Analysis & Authoritative Basis

### Authoritative Requirements:
1. **Engineering Roadmap §Phase 7, Module 7.8:**
   - Implement `AuthMiddleware` with three operating modes:
     - `none`: Pass-through, default for local-first single-user workflows.
     - `api-key`: Static key validation via `Authorization: Bearer <key>` or `X-API-Key`.
     - `jwt`: Cryptographic token verification (HMAC-SHA256/384/512), checking signature, expiration (`exp`), and activation (`nbf`).
   - CLI execution (`mnemo` console script):
     - `mnemo serve`: Uvicorn ASGI server runner with `--host`, `--port`, `--log-level`, `--auth-mode`, `--api-key`, `--jwt-secret`.
     - `mnemo provision-tokenizer`: Tokenizer asset provisioning utility.
     - `mnemo --version`: Version introspection.
     - `mnemo check`: Configuration validation and secret-redacted introspection.
   - Server packaging & Container integration:
     - `docker/server.Dockerfile` entrypoint and healthcheck configuration pointing to canonical `/health` endpoint.
     - Wheel packaging and console_scripts entrypoint verification.

---

## 2. Frozen Core Boundary Audit

| Capability | Module / Layer | Core Status |
|---|---|---|
| Domain Logic | `mnemo-core/` | **Frozen / Untouched (0 changes)** |
| Plugins | `plugins/` | **Frozen / Untouched (0 changes)** |
| Historical ADRs | `docs/adr/ADR-0001` through `ADR-0051` | **Frozen / Untouched (0 changes)** |
| Auth & Transport | `mnemo-server/mnemo_server/auth.py` | **Server Layer Implementation** |
| CLI Entrypoint | `mnemo-server/mnemo_server/cli.py` | **Server Layer Implementation** |

**FROZEN_CORE_MODIFICATIONS_REQUIRED:** `NO` (0 modifications to `mnemo-core/` or `plugins/`).

---

## 3. Server Layer Architecture

### Authentication Middleware Flow:
```
Incoming HTTP / WebSocket Request
           │
           ▼
    Is path exempt?
 (e.g., /health, /v1/health, /docs, /openapi.json)
    ├── YES ──► Pass through to route handler
    └── NO
           │
     Auth Mode?
    ├── none ───────► Pass through
    ├── api-key ────► Verify Authorization: Bearer <key> / X-API-Key
    │                  ├── MATCH ──► Pass through
    │                  └── MISMATCH ─► Return 401 Unauthorized (auth.unauthorized)
    └── jwt ────────► Verify JWT Signature, exp, nbf
                       ├── VALID ──► Pass through (inject claims to request.state.auth)
                       └── INVALID ─► Return 401 Unauthorized (auth.unauthorized)
```

### CLI Subcommand Architecture:
- `mnemo serve`: Launches Uvicorn server applying CLI args overlaid on `ServerConfig.from_env()`.
- `mnemo provision-tokenizer`: Off-thread or CLI provisioning of BPE tokenizer assets.
- `mnemo check`: Validates configuration integrity and reports redacted active settings.
- `mnemo --version`: Displays server version matching `__version__`.

---

## 4. Governance & Risk Matrix

| Audit Dimension | Evaluation |
|---|---|
| **MODULE_7_8_STATUS** | READY FOR IMPLEMENTATION |
| **FROZEN_CORE_MODIFICATIONS_REQUIRED** | NO |
| **NEW_ADR_REQUIRED** | NO (ADR-0049 and Roadmap §7.8 govern implementation) |
| **IMPLEMENTATION_READY** | YES |
| **BLOCKING_ISSUES** | None |
| **HIGH_RISKS** | None |
| **MEDIUM_RISKS** | Health check endpoints must remain accessible without auth to support container probes |
| **LOW_RISKS** | Clock skew in JWT expiration checks (mitigated by tolerance window) |

---

## 5. Architectural Verdict

**VERDICT: GREEN** — Proceed to implementation readiness audit and implementation.
