# ADR-0069: Phase 8.5 HTTP API and UI Capability Contract

- **Status:** Accepted
- **Implementation:** Delivery adapters implemented and tested in Phase 8.5.10; Phase 9 UI pending
- **Date:** 2026-08-24
- **Extends:** ADR-0049 through ADR-0051, ADR-0055, ADR-0060, ADR-0064 through ADR-0068
- **Supersedes:** Nothing

## Context

Phase 9 is the Web UI phase, but Phase 8.5 must define stable services and
explicit controls for expensive processing before UI implementation.

## Problem

Routes that hide job creation, cost, consent, completeness, or original versus
derived evidence would force the UI to guess and duplicate orchestration.

## Decision

Add versioned thin HTTP adapters for: asset/occurrence inventory and bounded
delivery; document expansion; processing estimate/submit/status/cancel; typed
advanced/structured retrieval; and persisted Multimodal Final QA V2. Exact
paths and DTOs are frozen in the implementation-stage API specification before
coding; all delegate to core interfaces and common authorization/error mapping.

Capability responses distinguish `available`, `disabled`, `unconfigured`,
`uncertified`, and `blocked_policy`. Estimates expose provider trust class,
cache state, time/resource/currency ranges, hard budgets, and consent needs.
The UI contract requires explicit selection among preserve-only, OCR, VLM,
structured analysis, visual embedding, translation, or selected combinations;
no expensive default is inferred from upload.

UI views show original and derived evidence separately, confidence/provenance,
job progress/cancel/retry, completeness, and bounded continuation. Phase 8.5
does not implement the Phase 9 frontend.

## Alternatives

- Hide work behind upload: rejected due to cost/consent.
- Put orchestration in routes/UI: rejected due to duplicated domain logic.
- Delay all contracts to Phase 9: rejected because providers/jobs need stable
  consumers during Phase 8.5 certification.

## Consequences

API design precedes UI, with more explicit states and DTOs. Processing remains
asynchronous; no persisted streaming Final QA is introduced implicitly.

## Compatibility

All existing routes, `/v1/query` preview semantics, `/v1/query/stream`, and
persisted Final QA V1 remain unchanged. New endpoints are versioned/additive.

## Migration

Advertise endpoints/capabilities only when dependencies are implemented and
certified. No data migration beyond dependent ADRs.

## Security implications

Authentication, notebook isolation, CSRF/CORS policy, rate limits, consent,
download headers, cursor integrity, and non-leaking errors are mandatory.

## Testing requirements

Test OpenAPI schemas, all capability states, auth/isolation, estimates/budgets,
job lifecycle, invalid DTOs/UUIDs, cursors, binary streaming/disconnect,
transient preview non-persistence, and UI contract mocks/accessibility.

## Observability

Record route/capability, status/error class, payload bounds, job ID, latency,
and disconnect; never content or secrets.

## Rollback/recovery

Stop advertising Phase 8.5 capabilities and retain V1 routes.

## Future-phase impact

Phase 9 may assume these certified contracts but not provider availability or
unbounded asset access.

## Explicit non-goals

This ADR does not implement UI, define visual styling, or replace preview APIs.
