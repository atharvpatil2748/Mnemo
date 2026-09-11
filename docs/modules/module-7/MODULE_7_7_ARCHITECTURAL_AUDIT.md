# Module 7.7 — Architectural Audit: WebSocket Streaming

- **Module:** Phase 7, Module 7.7 (WebSocket Streaming)
- **Status:** GREEN
- **Date:** 2026-08-16

---

## 1. Scope Analysis & Authoritative Basis

### Authoritative Requirements:
1. **Engineering Roadmap §Phase 7, Module 7.7:**
   - Implement `/ws/query` (and `/v1/ws/query`) WebSocket endpoint following Architecture §5.3 5-event protocol.
   - Event serialization (JSON events conforming to typed schemas).
   - Streaming token forwarding (`LLMInterfaceV1.stream()` → WebSocket send).
   - Connection lifecycle management (auth verification, heartbeat/ping-pong, disconnect cleanup).
2. **Architecture Specification v2.0 §5.3:**
   - 5-event streaming protocol:
     1. `retrieval_start`: Notification of retrieval initiation.
     2. `chunk_retrieved`: Evidence candidate notifications with `chunk_id` and `score`.
     3. `synthesis_token`: Real-time streaming LLM tokens.
     4. `citations_ready`: Complete resolved `CitationResponse` list.
     5. `done`: Completion event with execution and retrieval metadata.
   - Diagnostic and lifecycle events: `error` and `pong`.

---

## 2. Frozen Core Boundary & Implementation Support

| Required Capability | Core Primitive / Provider | Core Status |
|---|---|---|
| Streaming LLM Provider | `LLMInterfaceV1.stream(system, messages, max_tokens)` | **Frozen / Ready** |
| Multi-Source Retrieval | `MultiSourceRetriever.execute(plan, global_limit)` | **Frozen / Ready** |
| Cross-Encoder Reranking | `RerankingModule.execute(query, fusion_result)` | **Frozen / Ready** |
| Budget-Constrained Context | `ContextBuilder.build(rerank_result, budget, prompt)` | **Frozen / Ready** |
| Prompt Intent Routing | `classify_prompt_template(query, context_result)` | **Frozen / Ready** |
| Token Counter Provisioning | `TokenCounterInterfaceV1` / `O200KBaseTokenCounter` | **Frozen / Ready** |

**FROZEN_CORE_MODIFICATIONS_REQUIRED:** `NO` (0 modifications to `mnemo-core/` or `plugins/`).

---

## 3. Server Layer Architecture

### Transport & Service Structure:
```
mnemo-server/mnemo_server/
├── schemas/
│   └── streaming.py       # Pydantic V2 schemas for WebSocket messages and 5-event protocol
├── services/
│   └── streaming.py       # StreamingQueryService orchestrating async token forwarding and citations
├── routers/
│   └── streaming.py       # WebSocket router (/ws/query, /v1/ws/query) and SSE endpoint (/v1/query/stream)
```

### Event Lifecycle & Protocol Schema:
1. Client connects via `WebSocket` to `/ws/query` or `/v1/ws/query`.
2. Client sends query payload JSON conforming to `QueryRequest` (or `ping`).
3. Server validates notebook existence and request structure.
4. Server emits `{"event": "retrieval_start"}`.
5. Multi-source retrieval & reranking execute. Server emits `{"event": "chunk_retrieved", "data": {"chunk_id": "<id>", "score": <score>}}` for retrieved chunks.
6. Context is assembled within `context_budget`.
7. Synthesizer streams tokens via `LLMInterfaceV1.stream()`. Server emits `{"event": "synthesis_token", "data": {"token": "<chunk>"}}`.
8. Complete answer is analyzed for `[source:N]` citations. Server emits `{"event": "citations_ready", "data": {"citations": [...]}}`.
9. Server emits `{"event": "done", "data": {"retrieval_metadata": {...}}}`.
10. Connection remains open for subsequent queries or heartbeat. Disconnections are cleanly handled without resource leaks.

---

## 4. Governance & Risk Matrix

| Audit Dimension | Evaluation |
|---|---|
| **MODULE_7_7_STATUS** | READY FOR IMPLEMENTATION |
| **FROZEN_CORE_MODIFICATIONS_REQUIRED** | NO |
| **NEW_ADR_REQUIRED** | NO (Architecture §5.3 and ADR-0049 provide complete specification) |
| **IMPLEMENTATION_READY** | YES |
| **BLOCKING_ISSUES** | None |
| **HIGH_RISKS** | None |
| **MEDIUM_RISKS** | Slow LLM streaming connection drop handling (mitigated by `WebSocketDisconnect` guards) |
| **LOW_RISKS** | Non-synthesis evidence-only streaming queries (handled with graceful token skip) |

---

## 5. Architectural Verdict

**VERDICT: GREEN** — Proceed to implementation readiness audit and implementation.
