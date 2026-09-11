# Phase 8.5.2 Gate Evidence

## Scope

Bounded parser-level asset discovery, exact transient bytes, deterministic
occurrence provenance, typed locators/omissions, standalone image ingestion,
and additive production-ingestion publication through the Phase 8.5.1 catalog.

## Implemented matrix

- PDF: embedded raster occurrences with physical page and reliable geometry.
- DOCX: ordered body drawing occurrences with relationship and inline position.
- PPTX: slide picture relationships with slide/shape order, alt text, and EMU geometry.
- XLSX: worksheet drawing images with sheet and cell-anchor ranges.
- HTML/Markdown: existing pure data-URI extraction with typed DOM/block locators.
- Standalone PNG/JPEG/GIF/WebP/TIFF/BMP/SVG: exact bytes, no automatic analysis.

Charts, SmartArt/OLE rendering, packaged-resource acquisition, OCR, VLM,
visual embeddings, multimodal retrieval, and asset delivery are not part of
this gate.

## Security and boundedness

In-memory archive preflight enforces entry count, total expansion, per-entry
expansion, compression ratio, traversal-safe names, and rejects encrypted
entries. Relationship resolution never fetches external targets. Asset count,
per-asset bytes, aggregate bytes, and container-unit limits are bounded.
Image signatures are checked against declared MIME; active/external SVG content
and malformed XML are rejected. Optional corrupt/unsupported assets produce
typed omissions without discarding valid text.

## Compatibility evidence

The ingestion pipeline publishes the exact V1 parse projection and retains V2
occurrence evidence separately. `StorageInterfaceV1`, canonical chunk text and
identity, retrieval V1, citation/Final-QA V1, existing HTTP routes, Qdrant
optionality, and the existing six MCP tools are unchanged.

The certified Golden Corpus was inspected read-only and retained 15 documents,
15 versions, 15 sources, 1,514 chunks, 1,514 FTS rows, and 1,514 title rows,
with zero orphan chunks and duplicate chunk IDs. It was not purged or
re-ingested.

## Performance observation

An isolated 1×1 PNG parser V2 measurement completed 1,000 operations in
0.132241 seconds (7,562 operations/second, 0.1322 ms/operation) with 107,927
bytes peak traced allocation. These are local observations, not frozen SLOs.

## Validation

- Focused parser V2 format/security matrix: 34 passed.
- Focused parser, ingestion, asset-catalog, and server-source regressions passed.
- Full regression: 1,485 passed, 1 skipped, 90.00% combined coverage.
- Ruff format/check, strict mypy across 155 production source files, all three
  package builds, and `git diff --check` passed.

## Deferred work

Phase 8.5.3+ retains durable processing jobs, OCR, VLM, visual embeddings,
multimodal/structured/multilingual retrieval, V2 resource delivery, expanded
MCP capabilities, and UI work.
