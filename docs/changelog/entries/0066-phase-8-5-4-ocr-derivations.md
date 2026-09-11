# 0066 — Phase 8.5.4 OCR Derivations

Implemented the accepted ADR-0061 OCR derivation foundation on additive SQLite
schema v9. The capability adds typed provider-neutral OCR requests/results,
ordered regions with optional geometry/confidence/language observations, a
conservative scanned-page detector, deterministic derivation and cache
identities, occurrence-scoped authorization, and an ADR-0060 governed worker
operation with consent, cost, cancellation, bounded retry, and crash-safe cache
replay.

OCR output is immutable untrusted derived evidence. It is stored and indexed in
an independent generation-aware OCR FTS projection and never changes parser IR,
canonical `Chunk.text`, canonical FTS, V1 embeddings, retrieval, citations, or
Final QA. The workstream does not bundle a benchmark-selected provider and does
not implement VLM, visual embeddings, multimodal retrieval, multilingual
retrieval, or new HTTP/MCP delivery.
