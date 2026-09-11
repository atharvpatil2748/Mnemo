# Phase 8.5 WP-06 Gate Evidence

**Status:** COMPLETE  
**Date:** 2026-08-27  
**Scope:** Asset inventory, authorized derivation discovery, and original binary delivery only

## Implemented contract

WP-06 adds `AuthorizedAssetAnalysisCatalogV1` and `AssetDeliveryV2` without
widening `StorageInterfaceV1` or changing canonical asset/occurrence identities.
The SQLite/composite catalog resolves derivations only through an authorized
occurrence and returns lifecycle-bearing descriptors containing occurrence,
modality, operation, provider/model/configuration, result availability,
generation/profile/state, confidence, language, timestamps, and normalized
ready/stale/failed/pending/unavailable availability.

Bounded exact-version asset inventory now returns, in physical occurrence order:

- original asset metadata and its distinct occurrence identity;
- notebook/source/document/version provenance;
- locator and extraction provenance;
- all authorized derivation descriptors needed for subsequent analysis delivery;
- truthful `complete`/`truncated` state, omissions, usage, and `CursorCodecV2`
  continuation.

Repeated occurrences of one content-addressed asset remain separate. A shared
hash is never treated as authorization.

## Analysis selection and original/derived distinction

`AssetAnalysisSelector` supports:

| Selection | Behavior |
|---|---|
| `explicit` | Resolves only the supplied authorized immutable derivation IDs. |
| `latest_ready` | Deterministically selects the newest ready derivation per requested modality, breaking timestamp ties by derivation ID. |
| `all` | Returns every ready requested derivation in catalog order. |

Optional modality and generation-profile filters are exact. Missing, stale,
failed, or unavailable analysis is reported as `unavailable`; it is never
represented as an empty image. OCR/Vision results remain explicitly derived and
retain original asset/occurrence plus derivation/generation provenance. Visual
embedding descriptors are discoverable metadata but are not misrepresented as
human-readable analysis payloads.

## Binary, cursor, completeness, and security behavior

Original delivery continues through the one governed `BinaryDelivery` path. It
validates retained bytes against catalog SHA-256/length/MIME metadata, authorizes
the occurrence and exact document version on every call, and binds continuation
to scope, occurrence, snapshot, content hash, and server bounds through
`CursorCodecV2`.

HTTP returns `206` for truncated ranges and exposes range, total length, hash,
snapshot, next cursor, completeness, and notebook/source/document/version/
asset/occurrence provenance headers. MCP resource metadata carries the same
information. Only a complete, signature-recognizable PNG/JPEG/GIF/WebP is emitted
as MCP `ImageContent`; partial, malformed, or unsupported media is an opaque
resource with its original MIME recorded separately. Thus clients never attempt
to decode a byte prefix as a complete image.

Cross-notebook occurrences and derivations fail closed. Bare asset or derivation
IDs do not grant access, storage URIs/paths are never returned, and invalid
selector combinations are typed contract failures. WP-14 still owns actor-level
authorization centralization and final security certification; WP-06 preserves
the current fail-closed notebook/source/version/occurrence boundary.

## MCP and HTTP behavior

- Retained `get_asset` remains backward compatible in inventory and selected-
  occurrence modes. Inventory now contains derivation descriptors and explains
  binary continuation.
- Retained `get_image_analysis` preserves explicit OCR/Vision IDs and adds
  optional `selection`, `modalities`, and `profile` fields.
- Tool descriptions distinguish original delivery, existing derived analysis,
  and future semantic image discovery, and recommend occurrence/derivation IDs
  directly returned by inventory.
- Existing `/v2` inventory, content, and analysis routes use the same application
  service and error mapping.

No new tool or route was added.

## Focused validation

Final affected regression command:

```text
.venv/Scripts/python.exe -m pytest --no-cov \
  mnemo-core/tests/unit/test_asset_catalog_store.py \
  mnemo-core/tests/unit/test_delivery.py \
  mnemo-core/tests/unit/test_composite_storage.py \
  mnemo-core/tests/unit/test_ocr.py \
  mnemo-core/tests/unit/test_vision.py \
  mnemo-server/tests/test_mcp_delivery.py \
  mnemo-server/tests/test_server_delivery.py \
  mnemo-server/tests/test_mcp_wp03_contracts.py \
  mnemo-server/tests/test_mcp_conformance.py -q
```

Result: **114 passed**. Pytest also reported a non-test Windows cache-cleanup
permission warning after the successful run; no test failed.

After the final false-completeness correction (one requested analysis modality
ready while another is unavailable), the directly affected delivery suite was
rerun: **15 passed**.

The focused matrix covers authorized derivation scope, shared-document access,
missing/stale/failed/ready states, explicit/latest/all selection, deterministic
ties/order, repeated occurrences, count/response/range bounds, cursor continuation,
hash/MIME/length/provenance, PNG/JPEG partial resources, malformed image media,
HTTP 206 metadata, MCP native content, legacy explicit-ID compatibility, and
blind-client workflow guidance.

Static and governance validation:

- Ruff format check: passed for 16 affected Python files.
- Ruff check: passed for 16 affected Python files.
- Strict mypy: passed for 9 affected production modules.
- Both governance JSON documents parse successfully.
- Governance/MCP contract validation: 9 passed.
- `git diff --check`: passed.

## Compatibility and boundaries

- No database migration was required; existing asset, OCR, Vision, visual-
  embedding, and generation tables are reused.
- No corpus, runtime database, projection, model, provider, ingestion, benchmark,
  or external-agent state was read or mutated.
- V1 retrieval, citations, Final-QA V1, `Chunk.text`, canonical identities,
  Qdrant optionality, existing GET/no-selector behavior, and all ten MCP tool
  names remain unchanged.
- Semantic/exact asset-metadata discovery is WP-09, exhaustive evidence is WP-07,
  structured querying is WP-08, multimodal composition is WP-09/WP-12,
  capability exposure is WP-13, authorization certification is WP-14, blind-agent
  verification is WP-16, and final certification is WP-17.
- No Phase 11 planning, replanning, routing, or recursive traversal was added.

No new ADR was required. ADR-0066 and ADR-0073 already govern the implementation.
No contradiction with WP-00 through WP-05 was found.

## Gate

All mandatory WP-06 implementation criteria are satisfied with focused evidence.
This does not certify Phase 8.5.

**WP-06 COMPLETE**
