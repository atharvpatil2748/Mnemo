# ADR-0065: Bounded Document Expansion and Resource Delivery

- **Status:** Accepted
- **Implementation:** Delivery implemented in Phase 8.5.10; cursor security unified under `CursorCodecV2` by WP-04 and exact/positional selectors implemented additively by WP-05 on 2026-08-27
- **Date:** 2026-08-24
- **Extends:** ADR-0049, ADR-0051, ADR-0058, ADR-0059
- **Supersedes:** Nothing

## Context

Clients need more than ranked snippets: bounded documents, page/slide/chunk
ranges, images, and original assets. Current HTTP/MCP surfaces do not provide a
versioned resource-delivery contract.

## Problem

Unbounded expansion risks memory, context, data leakage, and denial of service.
Text descriptions are not substitutes for original image inspection.

## Decision

Add a shared `DocumentExpansionServiceV1` used by thin HTTP and MCP adapters.
Requests select an authorized exact version and one bounded view: typed blocks,
page range, slide range, chunk range, occurrence inventory, selected assets,
derived analysis, or original bytes. Responses include a snapshot identity,
ordered typed items, attribution, completeness, omissions, byte/token/page/
slide/asset/pixel consumption, and an opaque continuation cursor.

Hard server ceilings apply before configurable lower request limits. Initial
ceilings are configuration values validated by security/performance benchmarks,
not promises in this ADR. Cursor pages reauthorize scope. Binary transport uses
HTTP streaming with safe MIME/disposition headers and MCP native
`ImageContent`, embedded resources, or resource links according to negotiated
capability. A description request never returns original bytes implicitly.

## Alternatives

- Return complete documents in one response: rejected as unbounded.
- Encode all binaries as JSON base64: rejected for overhead and memory risk.
- Add adapter-specific implementations: rejected because policy would drift.

## Consequences

Clients gain controlled expansion and visual inspection. Continuations may
expire; the error is typed and never silently restarts against a new snapshot.

## Compatibility

Existing source/query endpoints and six MCP tools retain their schemas. New
versioned routes/resources are additive.

## Migration

No canonical migration beyond ADR-0059. Capability advertisement occurs only
after the service and authorization tests pass.

## Security implications

Authorize notebook/version/occurrence on every request; enforce decompressed
and transferred-byte limits, range validation, rate limits, and non-sniffable
downloads. Asset IDs are not bearer capabilities.

## Testing requirements

Test all ranges, cursors, limits, disconnect/cancellation, MIME, original versus
description separation, malformed IDs, cross-notebook denial, and live MCP
stdio/SSE clients.

## Observability

Record resource kind, counts/bytes, truncation, cursor outcome, authorization
class, latency, and disconnects without names or content.

## Rollback/recovery

Stop advertising new routes/resources. Existing retrieval and MCP tools remain.

## Future-phase impact

Phase 9 uses this service for document and asset viewers; Phase 13 publishes
benchmarked limits and deployment guidance.

## Explicit non-goals

This ADR does not provide unrestricted filesystem access or automatic prompt
insertion of full documents.
