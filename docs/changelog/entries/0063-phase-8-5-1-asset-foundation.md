# Phase 8.5.1 — Asset Foundation

Implemented and tested the additive foundation governed by ADR-0059, ADR-0068,
and ADR-0071:

- retained exact uploaded bytes as content-addressed assets for new ingestions;
- added exact-version `DocumentBinaryReference`, typed `AssetOccurrence`, and
  foundational `AssetDerivation` records;
- added strongly typed PDF/PPTX/DOCX/XLSX/DOM/standalone locators without
  fabricating unavailable geometry;
- added occurrence-scoped notebook authorization and reference-aware GC;
- added transactional SQLite schema version 7 and atomic index-generation
  promotion;
- preserved all Phase 0–8 models, chunks, embeddings, retrieval, APIs, Final QA,
  and six MCP tools.

OCR, VLM, visual embeddings, multilingual/structured retrieval, asset delivery,
and Phase 9 UI remain pending.
