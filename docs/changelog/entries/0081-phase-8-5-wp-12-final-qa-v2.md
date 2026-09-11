# 0081 — Phase 8.5 WP-12 Final-QA V2

Completed the additive Final-QA V2 operational path through the existing
runtime, immutable execution store, and citation-compliant orchestrator.

- Added strict shared HTTP/MCP DTOs and `FinalQAV2ApplicationService`.
- Activated `POST /v2/notebooks/{notebook_id}/final-qa` and MCP
  `run_final_qa_v2`.
- Added governed provider-profile/modality gating and complete/partial
  publication enforcement.
- Added transport-level replay, fingerprint, principal, corrupt-snapshot,
  multimodal, multilingual, completeness, and citation-retry tests.
- Proved zero new provider calls for HTTP/MCP replay and replay after citation
  correction.

V1 Final-QA/retrieval/citation contracts are unchanged. WP-13 onward and final
Phase 8.5 certification remain pending.
