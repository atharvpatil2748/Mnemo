# Phase 8.5.10 Gate Evidence

**Gate:** PASS  
**Baseline:** v0.25.0; Phase 0–8 frozen  
**Schema:** unchanged (delivery is an additive service/adapter layer)

## Implementation

`DocumentExpansionServiceV1` is the shared authorization and bounds boundary
used by HTTP and MCP. Its typed responses preserve notebook, source, document,
exact version, chunk, asset, occurrence, derivation, modality/authority,
generation, completeness, snapshot identity, omissions, and usage.

Supported delivery operations are:

- cursor-bounded typed document blocks;
- exact original bytes with stored length/hash/MIME verification;
- exact canonical chunks with parent ancestry;
- ordered asset-occurrence inventory and authorized original asset bytes;
- bounded OCR and vision derivation evidence, kept distinct from source truth;
- immutable Final-QA V2 snapshot evidence with zero generation;
- truthful capability negotiation.

Cursors are HMAC-signed, exact-scope bound, and reauthorized on every page.
Hard byte/item ceilings are deployment configuration. Binary adapters use
native streaming/resource content, safe response headers, explicit range and
completeness metadata, and never expose a storage path.

## HTTP contract

The additive routes are:

- `GET /v2/capabilities`
- `GET /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}`
- `GET .../original`
- `GET .../chunks/{chunk_id}`
- `GET .../assets`
- `GET /v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content`
- `GET .../analysis`
- `GET /v2/notebooks/{notebook_id}/final-qa/{assistant_turn_id}/evidence`

Tests cover authentication, UUID validation, bounds, JSON DTOs, binary
streaming, safe headers, typed 403/413 responses, attribution, and OpenAPI
registration. Existing V1 routes and streaming semantics are unchanged.

## MCP contract

The original six tools remain in their original order and retain their input
and output contracts. Four read-only tools are appended:

- `get_document`
- `get_document_chunk`
- `get_asset`
- `get_image_analysis`

Tests cover discovery, deterministic dispatch, validation, bounded JSON,
native `EmbeddedResource`, native `ImageContent`, original-byte delivery, and
the `mnemo://capabilities` resource. The same implementation is used by stdio
and SSE transports.

## Authorization, integrity, and security

- Notebook → source → document → exact version → occurrence authorization is
  checked before data enters a response.
- Shared content-addressed assets do not confer access.
- Cursor tampering/cross-scope replay fails closed.
- Stored binary size and SHA-256 are verified before publication.
- Response/item/asset ceilings prevent unbounded delivery.
- Error responses sanitize authorization and size details.
- Tests cover cross-notebook denial, missing/revoked references, stale or
  mismatched derivations, malformed cursors, and no arbitrary path access.
- No provider calls, hidden cloud egress, or binary/content logging were added.

## Test and quality evidence

Commands executed:

```text
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict mnemo-core/mnemo mnemo-server/mnemo_server plugins/email-ingestion/email_ingestion
uv build --package mnemo-core
uv build --package mnemo-server
uv build --package mnemo-email-ingestion
git diff --check
```

Results:

- pytest: **1,652 passed, 1 skipped**, 8 dependency/deprecation warnings;
- coverage: **90.05%** (required 90%);
- Ruff format/check: PASS;
- strict mypy: PASS, 190 source files;
- all three packages: source distribution and wheel PASS;
- focused delivery/HTTP/MCP regression: PASS.

## Golden Corpus and compatibility

The certified database was opened read-only (`mode=ro&immutable=1`). Evidence:

```text
documents=15, document_versions=15, sources=15
chunks=1514, fts_chunks=1514, fts_chunk_titles=1514
orphan_versions=0, orphan_chunks=0, orphan_fts=0
sha256(ordered chunk id + text)=1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66
```

No corpus row, canonical chunk/text/identity, FTS projection, embedding, or
Qdrant configuration was changed. StorageInterfaceV1, V1 retrieval,
Final-QA V1, ADR-0054/0056 behavior, V1 HTTP, and the original six MCP tools
remain compatible.

## Known limitations and rollback

- Concrete OCR/VLM/multilingual provider quality remains `UNVALIDATED` until
  Phase 8.5.11; delivery does not advertise model quality.
- Phase 9 UI implementation is pending.
- Rollback is additive: remove V2 router/capability advertisement and the four
  additive MCP definitions. Existing V1 routes and six MCP tools continue
  without data migration.

## Verdict

PHASE 8.5.10 GATE: PASS
