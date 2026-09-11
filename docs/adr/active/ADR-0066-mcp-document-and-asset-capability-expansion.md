# ADR-0066: MCP Document and Asset Capability Expansion

- **Status:** Accepted
- **Implementation:** Implemented in Phase 8.5.10; WP-06 (2026-08-27) added authorized derivation inventory/selection and provenance-bearing safe binary ranges
- **Date:** 2026-08-24
- **Extends:** Frozen Phase 8 MCP six-tool/stdio/SSE contracts, ADR-0065
- **Supersedes:** Nothing

## Context

Phase 8 exposes six read-only tools over stdio and SSE. MCP protocol types can
carry images/resources, but Mnemo does not expose documents, chunks, or assets.

## Problem

Adding resource delivery independently in each transport would risk schema,
limit, and authorization drift.

## Decision

Keep all existing tools unchanged and add four read-only tools backed by
`DocumentExpansionServiceV1`:

- `get_document` for bounded typed document/range expansion;
- `get_document_chunk` for an exact authorized chunk and ancestry;
- `get_asset` for occurrence inventory, selected original asset, or safe
  derivative according to explicit mode;
- `get_image_analysis` for OCR/VLM derivations and provenance.

Servers also advertise stable MCP resources/resource templates for authorized
document versions and asset occurrences when the negotiated client supports
them. Binary results use native MCP content/resources, not text placeholders.
Every schema exposes limits, cursor, completeness, MIME, and attribution.
stdio and SSE call the same application services and error mapper.

## Alternatives

- Overload `query_notebook`: rejected because retrieval and resource delivery
  have different bounds and security.
- Add transport-specific tools: rejected because behavior would diverge.
- Replace six tools: rejected because Phase 8 is frozen.

## Consequences

Tool count grows from six to ten when the capability is enabled. Clients can
visually inspect authorized evidence without confusing it with a description.

## Compatibility

Existing initialize, capability negotiation, tools, attribution, errors,
stdio, and SSE behavior remain unchanged.

## Migration

No database migration beyond dependencies. Tools/resources are advertised only
when backing services are enabled and certified.

## Security implications

The MCP session identity is mapped to the same application authorization as
HTTP. Limits and occurrence-based ACLs cannot be overridden by tool arguments.

## Testing requirements

Run schema/contract tests, malformed and cross-scope IDs, resource negotiation,
pagination, binary payloads, disconnects, and live invocations of all old/new
tools over both transports.

## Observability

Record tool/resource name, outcome, bounded payload size, completeness, and
latency without content.

## Rollback/recovery

Remove new capabilities from advertisement. Old tools continue unaffected.

## Future-phase impact

Phase 9 may use HTTP while external agents use equivalent MCP capabilities;
Phase 12 plugins can add providers behind services, not new trust boundaries.

## Explicit non-goals

This ADR does not make MCP mutating, run processing jobs implicitly, or expose
arbitrary files.
