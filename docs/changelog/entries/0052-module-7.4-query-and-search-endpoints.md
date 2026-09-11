# Module 7.4 Query and Search REST Endpoints

- Implemented transport-layer Pydantic V2 DTOs with strict validation and extra field rejection:
  - `mnemo-server/mnemo_server/schemas/query.py`: `QueryFilters`, `RetrievalConfig`, `SynthesisConfig`, `QueryRequest`, `CitationResponse`, `RetrievalMetadataResponse`, `QueryResponse`.
  - `mnemo-server/mnemo_server/schemas/search.py`: `SearchRequest`, `SearchResultItem`, `SearchResponse`.
- Implemented `QueryService` in `mnemo-server/mnemo_server/services/query.py`:
  - Validates notebook scope (when `notebook_id` is provided; supports `notebook_id: null` for cross-notebook global query).
  - Translates REST filter schemas into immutable core `MetadataFilter`.
  - Generates subqueries and builds `RetrievalPlan` (`intent=RetrievalIntent.SYNTHESIS`).
  - Executes `MultiSourceRetriever` with RRF fusion across specified retrieval modes (`dense`, `sparse`, `hybrid`).
  - Executes `RerankingModule` (cross-encoder scoring with deterministic RRF fallback).
  - Constructs bounded prompt context with `ContextBuilder` respecting token budgets and system prompts.
  - Implements grounded answer generation via `GroundedAnswerGenerator` when `synthesis.enabled: true`.
  - Implements marker-accurate citation extraction (`[source:X]`) mapping citations to referenced chunks with document title resolution.
  - Implements evidence-only query mode when `synthesis.enabled: false`, extracting citations directly from retrieved context items without invoking LLM synthesis.
- Implemented `SearchService` in `mnemo-server/mnemo_server/services/search.py`:
  - Executes global or notebook-scoped multi-mode search (`dense`, `sparse`, `hybrid`) without LLM answer generation.
  - Coordinates `MultiSourceRetriever` and optional `RerankingModule`.
  - Returns ranked list of `SearchResultItem` containing chunk IDs, scores, global/reranked ranks, retrieval modes, heading paths, page numbers, and chunk metadata.
- Implemented REST router endpoints in `mnemo-server/mnemo_server/routers/`:
  - `POST /v1/query`: Full RAG query endpoint with grounded synthesis and citation tracking.
  - `POST /v1/search`: Pure multi-mode retrieval and search endpoint.
- Registered `query_router` and `search_router` in `mnemo_server/app.py` under the `/v1` prefix.
- Added comprehensive integration and validation test suites:
  - `mnemo-server/tests/test_server_query.py`: 10 test cases covering synthesis, evidence-only mode, global query, 404 missing notebook, 422 validations, 503 dependency errors, and metadata filtering.
  - `mnemo-server/tests/test_server_search.py`: 9 test cases covering global search, scoped search, RRF score preservation, limit bounds, missing notebook 404, 422 validations, 503 errors, and verifying search never calls LLM completion.
- Maintained 100% boundary isolation: `mnemo-core`, `plugins/`, and ADRs 0001–0051 remain completely frozen and untouched.

Module 7.4 is complete and verified.
