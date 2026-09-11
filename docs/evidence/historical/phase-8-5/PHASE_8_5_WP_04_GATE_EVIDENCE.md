# Phase 8.5 WP-04 Gate Evidence

**Date:** 2026-08-27  
**Scope:** WP-04 cursor and completeness unification only  
**Verdict:** WP-04 COMPLETE

## Implementation

- Added one shared `CursorCodecV2` contract. Its canonical envelope contains an
  explicit format version, domain, signing-key ID, issuance/expiry timestamps,
  immutable snapshot identity, request/scope binding, continuation position,
  and effective limits.
- V2 tokens use the explicit `mnc2.<key-id>.<payload>.<signature>` format and
  HMAC-SHA256. All client-controlled state is covered by the signature.
- Added stable typed failures for invalid/tampered, expired, request/snapshot
  conflict, and unavailable/retired signing-key cases. Delivery maps those to
  sanitized `delivery.cursor_*` errors while retaining HTTP/MCP handling.
- Migrated advanced exhaustive retrieval to the shared codec. Its plan/query,
  notebook, representation position, per-representation snapshots, and budgets
  are bound to the token.
- Migrated exact block delivery, original-document byte ranges, asset
  inventories, asset byte ranges, and immutable Final-QA V2 evidence pages to
  V2 issuance. Existing authorization runs before every continuation decode.
- Effective delivery bounds are part of the signed request fingerprint. A
  cursor therefore cannot widen or silently change `max_items`/`max_bytes`.
- Added terminal offset rejection: a supplied cursor at or after proven
  exhaustion is a conflict; successful terminal pages return `complete` with a
  null cursor.
- Added `CoverageResponseV2` and a lossless mapping that preserves
  complete/partial/bounded/ranked/truncated/empty/unavailable/failed/unknown and
  prevents unavailable paths or omissions from being upgraded to complete.

## Expiry and key rotation

- Default V2 TTL is 15 minutes and is configurable from 1 second through one
  day. Expiry is fail-closed at the exact expiry boundary and tells the caller
  to restart traversal.
- The active named key is the only issuer. Named verification keys form an
  explicit rotation-overlap set. Unexpired cursors signed by an overlap key are
  accepted; after that key is removed, they fail with `cursor.key_unavailable`.
- Delivery-v1 tokens are decode-only. The server calculates one absolute
  legacy acceptance deadline when configuration is loaded; rebuilding a
  request-scoped delivery service does not extend the overlap. All issuance is
  V2. A zero-second overlap disables the legacy decoder immediately.
- Authenticated (`api-key`/`jwt`) and explicit production profiles reject the
  built-in/short cursor secret at configuration validation. Development with
  authentication disabled retains a compatibility default but derives a
  256-bit V2 key from it; this is not accepted as production configuration.

## Snapshot and security properties

- Document cursors bind notebook, document, exact version, parsed-block digest,
  canonical version content hash, continuation offset, and effective bounds.
- Original/asset cursors bind authorized occurrence or exact version plus
  original content hash, byte offset, and effective byte ceilings.
- Advanced cursors bind notebook, complete plan fingerprint (query/scope/
  representations/policies), budgets, source snapshots, and representation
  position.
- Cross-domain, cross-notebook, cross-document/version, cross-query,
  cross-snapshot, cross-budget, malformed, tampered, expired, future-issued,
  retired-key, and terminal-offset reuse fail closed.
- No server-side cursor state, schema migration, filesystem path, content,
  credential, model call, or corpus mutation was introduced.

## External-client contract

The WP-03 MCP output remains the machine-facing continuation contract:
`completeness=truncated` plus non-null `next_cursor` means the client passes the
opaque cursor unchanged to the same operation; terminal `complete` has no
cursor. WP-04 makes that advertised behavior cryptographically enforceable and
adds stable restart semantics for expiry/conflict. Live ChatGPT/Antigravity
behavior is deliberately not claimed; it remains WP-16.

## Focused validation

```text
uv run pytest --no-cov \
  mnemo-core/tests/unit/test_cursors.py \
  mnemo-core/tests/unit/test_delivery.py \
  mnemo-core/tests/unit/test_advanced_retrieval.py \
  mnemo-server/tests/test_server_delivery.py \
  mnemo-server/tests/test_mcp_delivery.py \
  mnemo-server/tests/test_mcp_wp03_contracts.py \
  mnemo-server/tests/test_server_config.py \
  tests/governance/test_phase8_5_wp00_contracts.py -q

91 passed
```

An additional directly affected authentication/SSE run passed `15 passed`.
Tests cover canonical round trips, tamper, malformed input, exact expiry,
future issuance, active/overlap/retired keys, wrong domain/scope/snapshot/
limits, deterministic advanced resume, source mutation, delivery V1 overlap,
first/middle/final pages, empty and single-block documents, byte/item bounds,
final/after-final offsets, MCP continuation metadata, configuration validation,
and governance JSON/schema consistency.

```text
uv run ruff format --check <17 affected Python files>
17 files already formatted

uv run ruff check <affected Python files>
All checks passed

uv run mypy <9 affected production modules>
Success: no issues found in 9 source files

python -m json.tool docs/governance/contracts/phase8_5_capability_matrix.json
python -m json.tool docs/governance/contracts/phase8_5_mcp_contracts.json
valid
```

The known Windows pytest cache-cleanup ACL warning occurred after successful
execution and did not affect test results. Per the WP-04 testing policy, no full
repository suite, coverage gate, model benchmark, ingestion, build, or external
agent evaluation was run.

## Compatibility and boundaries

- Frozen canonical IDs, `Chunk.text`, V1 retrieval/plans, V1 Final-QA,
  citations, HTTP V1, six V1 MCP tools, storage contracts, and Qdrant
  optionality were not changed.
- No database migration was required.
- The Golden Corpus and 44-document evaluation corpus were not read, written,
  ingested, indexed, or regenerated.
- Structured retrieval currently exposes an internal `next_offset`, not a
  callable MCP/HTTP cursor surface. The shared domain-separated codec is the
  required foundation; WP-08 must use it when that adapter is exposed rather
  than inventing another cursor format.
- Page/range/from-end selectors remain WP-05. Asset derivation selection is
  WP-06. Actor-level consolidated authorization remains WP-14. These omissions
  do not weaken the existing notebook/version/occurrence reauthorization path.
- No Phase 11 planning, decomposition, replanning, or graph traversal was
  introduced.

## Contradiction audit

No contradiction with WP-00 through WP-03, ADR-0058/0065/0068/0073–0075, or a
frozen V1 contract was found. The implementation replaces the two divergent
cursor encodings with the additive successor contract already prescribed by
the authoritative plan.
