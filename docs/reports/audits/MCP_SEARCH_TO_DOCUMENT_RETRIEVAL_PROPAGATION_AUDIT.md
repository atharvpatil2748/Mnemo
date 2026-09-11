# Mnemo MCP Search-to-Document Retrieval ID Propagation & Governance Audit

- **Document ID:** `GOV-MCP-20260826-01`
- **Related ADR:** [ADR-0072](../../adr/superseded/ADR-0072-propagate-notebook-identity-and-safely-resolve-notebook-context-for-mcp-document-retrieval.md)
- **Status:** **APPROVED & CERTIFIED**
- **Date:** 2026-08-26
- **Test Corpus:** Phase 8.5 Production Evaluation Corpus (44 documents, `df9c20cf-85fe-529c-902e-2e9e68193fbe`)

---

## 1. Executive Summary

This audit formalizes, certifies, and verifies the end-to-end resolution of the Search $\rightarrow$ Document Retrieval ID propagation gap in Mnemo's native Model Context Protocol (MCP) server. External AI agents (including ChatGPT via persistent tunnel and Antigravity IDE) can now search across all notebooks, receive the full identifier tuple (`notebook_id`, `document_id`, `version_id`), and immediately execute bounded full-document cursor pagination (with or without explicitly specifying `notebook_id`) while preserving strict multi-tenant authorization boundaries.

---

## 2. ADR Created

- **File:** [`docs/adr/superseded/ADR-0072-propagate-notebook-identity-and-safely-resolve-notebook-context-for-mcp-document-retrieval.md`](../../adr/superseded/ADR-0072-propagate-notebook-identity-and-safely-resolve-notebook-context-for-mcp-document-retrieval.md)
- **Title:** *Propagate Notebook Identity and Safely Resolve Notebook Context for MCP Document Retrieval*
- **Status:** `Accepted` (Implemented & Certified)
- **Indexed In:** [`docs/adr/README.md`](../../adr/README.md) (Next available ADR incremented to `ADR-0073`).

---

## 3. Documentation Synchronized

1. **[`docs/adr/README.md`](../../adr/README.md):** Indexed ADR-0072.
2. **[`docs/architecture/current/mnemo_architecture_v2.md`](../../architecture/current/mnemo_architecture_v2.md):**
   - Updated `search_all_notebooks` contract to document `SearchResultItem` containing `notebook_id`.
   - Updated `get_document` and `get_document_chunk` contracts documenting optional `notebook_id` with safe server-side resolution.
3. **[`docs/reports/evaluation/PHASE_8_5_11_EVALUATION_REPORT.md`](../evaluation/PHASE_8_5_11_EVALUATION_REPORT.md):**
   - Updated Section 8 to reference ADR-0072 conformance and ID propagation.
4. **`C:\Users\athar\.gemini\config\mcp_config.json`:**
   - Synchronized Antigravity MCP runtime configuration to the 44-document production evaluation database (`scratch/phase8_5_11/eval-20260825-02/mnemo.db`).

---

## 4. Code & Schema Changes

| Component | File | Changes Made |
| :--- | :--- | :--- |
| **Storage Contract** | `mnemo-core/mnemo/interfaces/storage.py` | Added `list_sources_for_document(document_id: UUID) -> tuple[Source, ...]` to `StorageInterfaceV1`. |
| **SQLite Storage** | `mnemo-core/mnemo/storage/sqlite.py` | Exposed public `list_sources_for_document` querying canonical `sources` table. |
| **Composite Storage** | `mnemo-core/mnemo/storage/composite.py` | Delegated `list_sources_for_document` to internal SQL store. |
| **Search DTO** | `mnemo-server/mnemo_server/schemas/search.py` | Added `notebook_id: UUID \| None = None` to `SearchResultItem`. |
| **Search Service** | `mnemo-server/mnemo_server/services/search.py` | Resolved parent notebook IDs from storage for all retrieved chunks. |
| **MCP Tools** | `mnemo-server/mnemo_server/mcp/tools.py` | Added `_resolve_notebook_id_for_document`; serialized `notebook_id` in `_handle_search_all_notebooks`; updated tool definitions and handlers for `get_document` and `get_document_chunk` to make `notebook_id` optional. |

---

## 5. Antigravity MCP Client Verification

- **Config File:** `C:\Users\athar\.gemini\config\mcp_config.json`
- **Server Command:** `uv --directory c:\Users\athar\Desktop\Mnemo run mnemo-mcp stdio`
- **Active Database:** `scratch/phase8_5_11/eval-20260825-02/mnemo.db` (44 documents)
- **Status:** Initialized and validated.

---

## 6. ChatGPT MCP Persistent Tunnel Verification

- **Tunnel Binary:** `tunnel-client.exe` (PID: `85972`, Status: `Running / Responding: True`)
- **Tunnel Identity:** `tunnel_6a85b493e6a48191b925e1f4d850c48c`
- **Config Path:** `C:\Users\athar\AppData\Roaming\tunnel-client\mnemo.yaml`
- **Persistence:** Windows Task Scheduler (`Mnemo Tunnel`, At logon, restart on failure, hidden).
- **Control Plane Status:** Connected and serving stdio MCP transport to ChatGPT.

---

## 7. Discovered MCP Toolset & Schema Validation

All **10 MCP tools** are exposed and verified:

1. `query_notebook`
2. `search_all_notebooks` (Outputs `chunk_id`, `notebook_id`, `document_id`, `version_id`, `text`, `score`, `rank`, `retrieval_mode`, `heading_path`, `page_number`, `metadata`)
3. `list_notebooks`
4. `get_notebook_summary`
5. `get_source_insights`
6. `get_timeline`
7. `get_document` (Required: `["document_id", "version_id"]`; Optional: `["notebook_id", "mode", "cursor", "max_bytes", "max_items"]`)
8. `get_document_chunk` (Required: `["document_id", "version_id", "chunk_id"]`; Optional: `["notebook_id"]`)
9. `get_asset`
10. `get_image_analysis`

---

## 8. Full End-to-End Traversal Validation: `manuscript.pdf`

### 8.1 Search Discovery
- **Tool:** `search_all_notebooks("manuscript.pdf")`
- **Returned Data:**
  - `notebook_id`: `df9c20cf-85fe-529c-902e-2e9e68193fbe`
  - `document_id`: `cb86bb2f-8af6-5a0e-8bde-ae70fb22aac3`
  - `version_id`: `64488aa1-2d45-5320-8cbf-318fb1dc98d8`
  - `retrieval_mode`: `sparse` (Score: `0.998804`)

### 8.2 Path A: Omitted `notebook_id` (Automatic Resolution)
- **First Call:** `get_document(document_id=..., version_id=..., mode="blocks", max_items=4)` (no `notebook_id`).
- **Server Action:** Auto-resolved `notebook_id` $\rightarrow$ `df9c20cf-85fe-529c-902e-2e9e68193fbe` $\rightarrow$ verified authorization.
- **Cursor Traversal:** 29 pagination requests across 116 total blocks.
- **Final Page Completeness:** `complete` (`next_cursor: null`).
- **Final Block (Ordinal 115, Page 5):**
  ```text
  "निश्चित करणारी, की तिचे हसे आणि तिच्या डोळ्यांतील चमक फक्त माझा असेल!"
  ```

### 8.3 Path B: Explicit `notebook_id`
- **Call:** `get_document(notebook_id=..., document_id=..., version_id=..., mode="blocks", max_items=4)`.
- **Result:** Exact bit-for-bit equivalence with Path A (29 pages, 116 blocks, identical sequence).

---

## 9. Security & Boundary Conformance

| Test Case | Tool Call Input | Expected & Actual Behavior | Status |
| :--- | :--- | :--- | :---: |
| **Invalid Document ID** | Random non-existent UUID | `NotFoundError("Document ... was not found in any notebook")` | ✅ PASS |
| **Invalid Version ID** | Random non-existent UUID | `NotFoundError("exact document version was not found")` | ✅ PASS |
| **Unauthorized Notebook ID** | Random notebook UUID | `NotFoundError("notebook was not found")` / fail-closed | ✅ PASS |
| **Tampered Cursor** | `"invalid_tampered_cursor_data"` | `DeliveryCursorError("Continuation cursor is invalid or stale")` | ✅ PASS |

---

## 10. Test Suite Execution Summary

- **MCP Delivery & Tools Tests (`pytest`):** 21/21 passed.
- **E2E Traversal Integration (`verify_all_mcp_clients_e2e.py`):** 6/6 verification steps passed (100%).
- **Evaluation Corpus Integrity:** No databases modified, no documents re-ingested, no models reconfigured.

---

## 11. Final Assessment

The Search-to-Document Retrieval ID Propagation and Safe Notebook Auto-Resolution capability is **fully production-ready, verified on live MCP clients, and certified under ADR-0072**.
