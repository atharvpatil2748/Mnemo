# Phase 8.5.1 Gate Evidence

## Scope

Original document retention, exact-version binary references, typed asset
occurrences, derivation foundations, occurrence-scoped authorization,
reference-aware garbage collection, and additive generation lifecycle.

## Executable evidence

- Transactional SQLite schema version 7: fresh, upgrade, repeated, failure
  rollback, and retry after interruption.
- Isolated original-byte retention: PDF, PPTX, DOCX, XLSX, and standalone PNG.
- Security: traversal rejection, MIME/hash/size enforcement, cross-notebook
  denial, revoked-source denial, shared-asset isolation, and opaque lookup.
- Lifecycle: derivation conditional transitions; BUILDING generations are not
  active; READY promotion is atomic and supersedes the prior generation.
- Frozen-corpus migration rehearsal on a SQLite backup retained `(15, 15, 15,
  1514, 1514, 1514)` document/version/source/chunk/FTS/title counts and identical
  canonical chunk/document digests. Historical original availability remained
  `UNAVAILABLE`; no bytes were fabricated.
- Read-only final Golden Corpus verification retained 15 documents, 15
  versions, 15 sources, 1,514 chunks, 1,514 FTS rows, and 1,514 title rows,
  with zero orphan or duplicate rows. The pre/post canonical chunk digest was
  `2f95689797c0da844cfb00425c8c2a25786035af82dd07ec48b35f928a51079e`.
- An isolated real application run exercised HTTP notebook creation and the
  production Markdown ingestion pipeline. It retained byte-exact original
  content, verified SHA-256/MIME/size, created one exact-version binary
  reference, reached `indexed`, and left Qdrant disabled.
- Phase 0–8 regression: 1,449 passed, 1 skipped, 90.02% coverage. Focused MCP
  conformance/SSE/tool regression: 20 passed.
- Ruff format/check, strict mypy across all production packages, all three
  package builds, and `git diff --check` passed.
- Local 8 MiB measurement: 93.24 MiB/s initial retention, 55.6 ms deduplicated
  repeat, 1.15 ms mean exact-version metadata lookup, and 0.02 MiB measured
  service allocation overhead (input buffer excluded).

## Compatibility

No canonical `Document`, `DocumentVersion`, `Source`, `Chunk`, FTS, embedding,
retrieval, V1 citation/Final-QA, HTTP, or MCP contract was changed. No Golden
Corpus purge or re-ingestion was performed.

## Deferred work

OCR, VLM, visual embeddings, parser extraction V2, durable processing jobs,
advanced/structured/multilingual retrieval, V2 evidence delivery, expanded MCP,
and Phase 9 UI are not implemented by this gate.
