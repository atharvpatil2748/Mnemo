# ADR-0072: Propagate Notebook Identity and Safely Resolve Notebook Context for MCP Document Retrieval

- **Status:** Accepted
- **Implementation:** Implemented and tested in Phase 8.5 Post-Evaluation Hardening
- **Date:** 2026-08-26
- **Extends:** ADR-0065, ADR-0066, ADR-0069
- **Supersedes:** Nothing

## Context

In Mnemo Phase 8.5, cross-notebook search and document delivery tools are exposed via MCP (`search_all_notebooks`, `get_document`, `get_document_chunk`, `get_asset`, `get_image_analysis`). 

During live integration with external MCP clients (e.g., ChatGPT via persistent tunnel and Antigravity IDE), a critical ergonomics and composability gap was identified:

1. `search_all_notebooks` returned `chunk_id`, `document_id`, and `version_id`, but omitted the parent `notebook_id`.
2. `get_document` and `get_document_chunk` strictly required `notebook_id`, `document_id`, and `version_id` in their tool input schemas.

When an MCP client searched for a document (e.g., `manuscript.pdf`), the search succeeded and identified the document and version UUIDs. However, when the client attempted to retrieve the document blocks to perform linear cursor traversal, the call failed because the client had no mechanism to know the parent `notebook_id` without independently calling `list_notebooks` and iterating through every notebook's sources.

Semantic search alone is inherently bounded and score-ranked; it cannot reliably answer structural or exhaustive queries such as *"What is the final paragraph of manuscript.pdf?"* without exact document traversal via cursor pagination.

## Problem

Requiring downstream MCP tools to receive a `notebook_id` that is not propagated by search tools breaks tool chaining and multi-hop agent workflows. Conversely, completely removing `notebook_id` checks without validation would break notebook multi-tenant isolation and security boundaries.

## Decision

We implement a two-part architectural solution that preserves strict security boundaries while enabling seamless tool composition:

### 1. Search Result Identity Propagation (Fix #1)
Extend `SearchResultItem` and the MCP `search_all_notebooks` tool response to include `notebook_id: UUID | None`.
- The search service resolves the canonical parent notebook for each retrieved chunk/document via the storage interface (`list_sources_for_document`).
- The returned JSON payload exposes `notebook_id`, `document_id`, and `version_id` alongside `chunk_id`.

### 2. Safe Server-Side Notebook Auto-Resolution (Fix #2)
Make `notebook_id` optional in the MCP tool schemas and handlers for `get_document` and `get_document_chunk`.
- **When `notebook_id` is supplied:** It is used directly and verified against the document version authorization boundary (`_authorize_version`).
- **When `notebook_id` is omitted:**
  1. The server queries `storage.list_sources_for_document(document_id)`.
  2. If 0 sources are found, it raises `NotFoundError("Document was not found in any notebook")`.
  3. If sources span more than one distinct notebook, it raises `ContractValidationError("Document belongs to multiple notebooks. Explicit 'notebook_id' parameter is required for authorization.")`.
  4. If exactly one distinct notebook is associated, that `notebook_id` is deterministically resolved and passed into `DeliveryRequest`.

## Security Decision

Notebook isolation and fail-closed authorization remain strictly enforced:
- Automatic resolution does **not** bypass `_authorize_version`, notebook existence checks, or document-to-version integrity checks.
- If a document is shared across multiple notebooks, automatic resolution refuses to guess and forces the caller to provide an explicit `notebook_id`.
- Tampered or cross-scope access attempts are rejected with `DeliveryAuthorizationError` or `NotFoundError`.

## Alternatives Considered

1. **Keep `notebook_id` strictly mandatory everywhere and force clients to call `list_notebooks`:**
   - *Rejected:* Causes severe agent friction and failure in automated tool calling, requiring excessive extra roundtrips.
2. **Make `get_document` operate on `document_id` alone without notebook authorization checks:**
   - *Rejected:* Breaks notebook isolation and circumvents the authorization boundary.
3. **Propagate `notebook_id` in search results AND provide safe server-side auto-resolution:**
   - *Selected:* Provides complete tool composability for agents that pass IDs forward, while seamlessly handling agents that only pass `document_id` and `version_id`.

## Consequences

### Positive
- `search_all_notebooks` $\rightarrow$ `get_document` $\rightarrow$ cursor pagination forms a natural, zero-friction pipeline.
- External agents (ChatGPT, Antigravity) can perform full-document cursor traversals to read whole documents, sections, or concluding passages.
- Single-notebook documents resolve instantly without redundant parameters.
- Multi-notebook security and tenant isolation remain completely intact.

### Tradeoffs
- Search result payload includes one additional UUID field (`notebook_id`).
- Storage interface contract (`StorageInterfaceV1`) is extended with `list_sources_for_document`.

## Compatibility

- Backwards-compatible: Existing callers supplying `notebook_id` continue to work without change.
- HTTP REST API (`/v1/delivery/documents/...`) contracts remain consistent.

## Testing Requirements

- Unit tests for search DTO serialization and MCP search tool execution.
- Unit tests for `get_document` and `get_document_chunk` with omitted `notebook_id`, multi-notebook ambiguity, and missing document errors.
- End-to-end integration test executing `search_all_notebooks("manuscript.pdf")` $\rightarrow$ `get_document(mode="blocks")` with omitted `notebook_id` $\rightarrow$ cursor pagination through all blocks to final passage.

## References

- Implementation files:
  - `mnemo-core/mnemo/interfaces/storage.py`
  - `mnemo-core/mnemo/storage/sqlite.py`
  - `mnemo-core/mnemo/storage/composite.py`
  - `mnemo-server/mnemo_server/schemas/search.py`
  - `mnemo-server/mnemo_server/services/search.py`
  - `mnemo-server/mnemo_server/mcp/tools.py`
- Test files:
  - `mnemo-server/tests/test_mcp_delivery.py`
  - `mnemo-server/tests/test_mcp_tools.py`
  - `scratch/test_mcp_search_traversal_integration.py`
