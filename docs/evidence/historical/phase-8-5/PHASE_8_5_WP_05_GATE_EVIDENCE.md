# Phase 8.5 WP-05 Gate Evidence

**Status:** COMPLETE  
**Date:** 2026-08-27  
**Scope:** Exact and positional document retrieval only

## Implemented contract

WP-05 adds `DocumentExpansionServiceV2` without changing `StorageInterfaceV1`, V1
retrieval, canonical identities, `Chunk.text`, V1 HTTP routes, or no-selector MCP
behavior. Requests contain exactly one tagged selector and resolve against one
authorized document/version snapshot in deterministic physical order. No selector
uses sparse search, dense search, reranking, or top-k ranking.

The selector matrix is:

| Selector | Authoritative universe | Result when representation is absent |
|---|---|---|
| `full` | all canonical parsed blocks | `empty` for an empty parsed document |
| `page_range` | authoritative block page numbers | `unavailable` |
| `slide_range` | slide-document page/slide numbers | `unavailable` |
| `sheet_range` | authoritative workbook sheet headings/order | `unavailable` |
| `block_range` | zero-based canonical block ordinals | typed validation error if outside bounds |
| `chunk_range` | zero-based physical chunk order | typed validation error if outside bounds |
| `section` | exact heading ancestry/path | `unavailable` without hierarchy; `empty` if no exact match |
| `from_end` | page, slide, sheet, block, chunk, section, or paragraph | `unavailable` where its position kind is absent |
| `adjacent` | bounded canonical block ordinal or exact chunk ID | typed validation error for an invalid anchor |

Ranges are inclusive. Tail and adjacent results are returned in forward physical
order. Chunk enumeration is provided by the additive `ExactDocumentReaderV1` and
the SQLite/composite implementations; the frozen storage interface was not widened.

## Cursor, completeness, and security

All V2 selector continuation uses WP-04 `CursorCodecV2` under the
`mnemo-document-expansion/v2` domain. The signed cursor binds notebook, document,
version, exact selector, immutable parsed/chunk snapshot digests, continuation
offset, and effective item/byte limits. Selector, scope, version, snapshot, bound,
domain, expiry, key, and signature conflicts fail closed. Authorization is repeated
before every continuation.

`truncated` always carries `next_cursor`; terminal `complete`, `empty`, and
`unavailable` never do. `complete` is emitted only after the selected exact universe
is exhausted. Missing physical metadata is not confused with an empty match and is
never fabricated.

## Transport behavior

- Added typed `POST /v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/expand`.
- Extended retained MCP `get_document` with an optional, discriminated `selector`.
- Preserved existing GET delivery and no-selector MCP behavior.
- MCP descriptions identify search as discovery, positional expansion as exact
  traversal, and require the same selector/bounds plus the opaque cursor on
  continuation.
- Results include exact physical index, heading path, sheet name, overlapping chunk
  IDs, and canonical image asset IDs where present.

## Focused validation

The final focused validation set executed:

```text
python -m pytest \
  mnemo-core/tests/unit/test_document_expansion_v2.py \
  mnemo-core/tests/unit/test_delivery.py \
  mnemo-core/tests/unit/test_cursors.py \
  mnemo-core/tests/unit/test_sqlite_store.py::test_exact_document_chunk_reader_uses_physical_order_and_version_scope \
  mnemo-server/tests/test_mcp_wp03_contracts.py \
  mnemo-server/tests/test_mcp_delivery.py \
  mnemo-server/tests/test_server_delivery.py -q --no-cov
```

Result: **49 passed**. The focused set covers selector validation and ordering,
multilingual blocks, image references, absent position metadata, full continuation,
snapshot/selector/bounds/tamper rejection, WP-04 cursor security/expiry/rotation,
SQLite exact version ordering, typed HTTP validation, MCP schemas, and MCP routing.

Targeted static validation:

- Ruff format/check: passed for all WP-05 affected files.
- Strict mypy: passed for the affected core and server modules.
- Governance JSON/schema checks: passed.
- `git diff --check`: passed for the WP-05 diff.

The full repository suite, corpus ingestion, model inference, benchmark suite, and
external ChatGPT/Antigravity behavioral certification were intentionally not run;
the authoritative plan assigns the latter certification to WP-16/WP-17 and WP-05
explicitly calls for focused validation.

## Compatibility and limitations

- No corpus source or certified Golden Corpus database was read or modified.
- Existing V1 and no-selector delivery contracts remain compatible.
- Page/slide/sheet selectors require authoritative parser metadata. Mnemo never
  synthesizes physical positions from text length.
- Canonical spreadsheet row/cell coordinates are not yet an authoritative document
  traversal representation; `sheet_range` is supported, while structured row/cell
  predicates remain WP-08.
- Image asset identities are preserved, but occurrence inventory/derivation discovery
  and semantic image retrieval remain WP-06/WP-09.
- ADR-0075's `DocumentScopeResolverV1` migration remains assigned to WP-14. Existing
  MCP notebook resolution and delivery authorization continue to fail closed.
- Blind external-agent behavior is not certified by this gate.

No new ADR was required. ADR-0065 and ADR-0073 already govern the additive service
and MCP contract.

## Gate

All mandatory WP-05 implementation criteria are satisfied with focused evidence.
This does not certify Phase 8.5.

**WP-05 COMPLETE**
