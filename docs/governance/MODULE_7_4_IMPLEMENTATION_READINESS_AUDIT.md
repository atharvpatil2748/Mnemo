# Module 7.4 Implementation Readiness Audit: Query and Search REST Endpoints

**Status:** COMPLETE & VERIFIED  
**Date:** 2026-08-16  
**Module:** Phase 7, Module 7.4 (Query & Search REST Endpoints)  
**Authoritative Specifications:**
- Architecture Specification V2 (§5.1 REST API Surface, §6 Retrieval Pipeline)
- Engineering Roadmap (Module 7.4: Query and Search Endpoints)
- Historical Governance & ADRs: ADR-0042, ADR-0043, ADR-0044, ADR-0045, ADR-0046, ADR-0048, ADR-0050, ADR-0051

---

## 1. Executive Summary & Readiness Verdict

This implementation readiness audit provides an exhaustive, adversarial evaluation of the contracts, core capabilities, dependency wiring, error mappings, and schema definitions required for Module 7.4 (`POST /v1/query` and `POST /v1/search`).

The audit confirms that all necessary domain models, retrieval orchestrators, fusion rerankers, context builders, answer generators, and storage search abstractions are fully present in frozen `mnemo-core` (Phases 0–6). Module 7.4 can be implemented strictly as a transport adapter layer inside `mnemo-server` without modifying frozen core packages or introducing a new ADR.

```
MODULE_7_4_IMPLEMENTATION_READINESS:
GREEN

FROZEN_PHASES_0_6:
UNCHANGED

ADR_COMPATIBILITY:
- ADR-0042 (Fusion-Aware Cross-Encoder Reranking)
- ADR-0043 (Deterministic Provenance-Preserving Context Construction)
- ADR-0044 (Grounded Answer Generation)
- ADR-0045 (Deterministic Citation Resolution and Persistence)
- ADR-0046 (Deterministic Final-QA Orchestration)
- ADR-0048 (Multi-Hop Query Planning & Context Allocation)
- ADR-0050 (Notebook & Graph REST Endpoints)
- ADR-0051 (Sources & Document Ingestion REST Endpoints)

NEW_ADR_REQUIRED:
NO

BLOCKING_ISSUES:
0

HIGH_RISKS:
0

MEDIUM_RISKS:
0

LOW_RISKS:
0
```

---

## 2. Core Call Chain Verification

### A. POST /v1/query Call Chain
1. **Request Intake & Validation:**
   - FastAPI parses and validates `QueryRequest` DTO.
   - If `notebook_id` is specified, `QueryService` verifies notebook existence in `StorageInterfaceV1` (raising `NotFoundError` / `404` if missing).
2. **Plan & SubQuery Preparation:**
   - Constructs `MetadataFilter(notebook_id=notebook_id, doc_types=..., date_after=..., date_before=..., source_ids=...)`.
   - Constructs `RetrievalPlan` using requested `retrieval_config.modes` (default: `[dense, sparse]` / hybrid) or calls `QueryPlanner.plan(question, ...)` when dynamic multi-query expansion is needed.
3. **Multi-Source Retrieval & Fusion:**
   - Invokes `MultiSourceRetriever(engine.registry, engine.embedding_provider).execute(plan, global_limit=top_k)`.
   - Performs concurrent dense vector search (Qdrant) and sparse BM25/FTS5 search (SQLite), applying RRF fusion ($k=60$) and parent chunk promotion.
4. **Cross-Encoder Reranking (Optional / Default True):**
   - Invokes `RerankingModule(engine.registry).execute(question, fusion_result)`.
5. **Context Construction:**
   - Invokes `ContextBuilder(engine.registry, token_counter).build(...)` to assemble token-budgeted, attributed context items.
6. **Grounded Synthesis & Citations:**
   - If `synthesis.enabled: true`:
     - Invokes `GroundedAnswerGenerator(engine.registry, token_counter).generate(context_result, max_output_tokens=...)`.
     - Invokes `CitationEngine(engine.storage, clock).resolve_and_persist(answer_result, assistant_turn=None, document_labels=...)` to extract verified `[source:N]` citations.
   - If `synthesis.enabled: false`:
     - Skips LLM generation; returns `answer: null`, deriving evidence citation records directly from context items.
7. **Response Serialization:**
   - Returns `QueryResponse` DTO with answer, citations list, and `retrieval_metadata` (chunks retrieved, chunks used, modes used, latency ms).

### B. POST /v1/search Call Chain
1. **Request Intake & Validation:**
   - FastAPI parses and validates `SearchRequest` DTO.
   - If `notebook_id` is specified, verifies notebook existence in storage (raising `NotFoundError` / `404` if missing).
2. **Plan & Retrieval Execution:**
   - Constructs `MetadataFilter(notebook_id=notebook_id, doc_types=..., date_after=..., date_before=..., source_ids=...)`.
   - Assembles `RetrievalPlan` with `SubQuery(query_text=query, retrieval_mode=mode, filters=metadata_filter, max_results=limit)`.
   - Invokes `MultiSourceRetriever(engine.registry, engine.embedding_provider).execute(plan, global_limit=limit)`.
3. **Optional Reranking:**
   - If `enable_reranking: true`, executes `RerankingModule(engine.registry).execute(query, fusion_result)`.
4. **Response Serialization (No Synthesis):**
   - Maps ranked chunks to `SearchResultItem` DTOs containing `chunk_id`, `document_id`, `version_id`, `text`, `score`, `rank`, `retrieval_mode`, `heading_path`, `page_number`, and metadata.
   - Returns `SearchResponse` DTO with results list, total count, and latency ms.

---

## 3. Verified API Contracts

### Endpoints
| Method | Path | Request Body | Response Body | HTTP Status | Description |
|---|---|---|---|---|---|
| `POST` | `/v1/query` | `QueryRequest` | `QueryResponse` | `200 OK` | Evidence retrieval + grounded synthesis |
| `POST` | `/v1/search` | `SearchRequest` | `SearchResponse` | `200 OK` | Global / scoped search without LLM synthesis |

### Request & Response DTO Specifications

#### `QueryRequest`
```python
class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=10000)
    notebook_id: UUID | None = None
    context_budget: int = Field(default=8000, ge=1, le=1_000_000)
    retrieval_config: RetrievalConfig = Field(default_factory=RetrievalConfig)
    synthesis: SynthesisConfig = Field(default_factory=SynthesisConfig)
```

#### `SearchRequest`
```python
class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=10000)
    notebook_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)
    modes: list[RetrievalMode] = Field(default_factory=lambda: [RetrievalMode.DENSE, RetrievalMode.SPARSE])
    filters: QueryFilters | None = None
    enable_reranking: bool = True
```

---

## 4. Key Architectural Invariants & Decisions

1. **Global vs. Scoped Invariance:**
   - Both `/v1/query` and `/v1/search` allow `notebook_id: null` to search globally across all notebooks, or a specific `UUID` to restrict results to a single notebook.
2. **Separation of Concerns:**
   - `/v1/query`: Full RAG pipeline (retrieval + context + answer synthesis + citations).
   - `/v1/search`: Pure search results (chunks + scores + metadata) without synthesis.
3. **Error Isolation & HTTP Mappings:**
   - `400 Bad Request`: Empty query strings, invalid filter dates (`date_after > date_before`), unsupported modes.
   - `404 Not Found`: Explicit `notebook_id` does not exist.
   - `422 Unprocessable Content`: Pydantic structural validation errors.
   - `503 Service Unavailable`: Storage or embedding/LLM dependency outages (`contract.dependency_unavailable`, `contract.storage`).
4. **Zero Frozen Core Modifications:**
   - `mnemo-core`, `plugins`, and ADRs 0001–0051 remain 100% frozen.
