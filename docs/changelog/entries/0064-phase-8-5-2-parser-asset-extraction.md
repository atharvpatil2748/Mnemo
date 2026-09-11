# Phase 8.5.2 — Parser Asset Extraction

Implemented the additive parser V2 transport and bounded asset discovery for
PDF, DOCX, PPTX, XLSX, HTML/Markdown data URIs, and standalone images.
Occurrences retain deterministic typed locators, authored alt text where
available, exact parser provenance, and original extracted bytes. Optional
asset failures are typed and auditable; archive traversal/expansion, external
relationships, MIME spoofing, oversized assets, and active SVG are rejected.

The production ingestion pipeline continues to publish the frozen parser V1
canonical projection. V2 assets and occurrences are persisted through the
Phase 8.5.1 catalog as an additive side channel, so canonical chunks, retrieval,
Final-QA V1, HTTP, and the six MCP tools are unchanged.

OCR, VLM descriptions, visual embeddings, multimodal retrieval, and asset
delivery remain pending.
