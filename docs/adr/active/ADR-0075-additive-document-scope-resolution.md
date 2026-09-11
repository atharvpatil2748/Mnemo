# ADR-0075: Additive Document Scope Resolution

- **Status:** Accepted
- **Implementation:** Complete in Phase 8.5 WP-14; consumers use the additive resolver and the frozen V1 storage protocol is restored
- **Date:** 2026-08-26
- **Extends:** ADR-0065, ADR-0066, ADR-0068, ADR-0069
- **Supersedes:** ADR-0072 mechanism only; ADR-0072 behavioral outcome remains required

## Context

ADR-0072 correctly repaired an MCP composition failure: search results now
propagate `notebook_id`, and exact document/chunk delivery may resolve an
omitted notebook when association is unique while failing closed on ambiguity.
It implemented resolution by adding `list_sources_for_document` to
`StorageInterfaceV1`.

The Phase 0–8 contract freezes `StorageInterfaceV1`. ADR-0058 and the Phase 8.5
roadmap require new storage capabilities to use additive protocols. Therefore
ADR-0072's behavior is correct, but its mechanism is architectural drift.

## Decision

### Preserve the behavior

The following remains mandatory:

```text
search result with notebook_id/document_id/version_id
  → explicit notebook when supplied, or safe unambiguous resolution
  → exact document/version association check
  → notebook authorization
  → delivery
```

- Search and retrieval results propagate `notebook_id` whenever resolved.
- If a caller supplies a notebook, the document/version/source relationship is
  verified; possession of IDs is not authorization.
- If omitted and exactly one authorized notebook association exists, resolution
  is deterministic.
- Zero associations returns the repository-standard not-found result.
- Multiple possible associations fail closed and require explicit notebook
  identity. The resolver never guesses.

### Supersede the mechanism

Introduce the additive `DocumentScopeResolverV1` contract:

```text
resolve_document_scope(
    actor_scope,
    document_id,
    version_id,
    requested_notebook_id | null,
) → ResolvedDocumentScope(
    notebook_id,
    document_id,
    version_id,
    resolution = EXPLICIT | UNIQUE_ASSOCIATION,
)
```

The resolver depends on a narrow additive source-association reader and the
existing authorization service. It validates exact version ownership and
returns only an authorized scope. Its typed outcomes distinguish invalid ID,
not found, forbidden, ambiguous scope, and version mismatch without exposing a
cross-notebook existence oracle.

No new method is added to `StorageInterfaceV1`. The pre-ADR-0072 method set is
the frozen signature baseline.

### Compatibility and migration

Migration is staged:

1. WP-00 records the frozen pre-ADR-0072 signature and this resolver contract.
2. WP-01 adds the resolver protocol/implementation and composition dependency.
3. Search and delivery consumers move from `engine.storage` association lookup
   to the resolver.
4. Existing concrete SQLite/Composite helper methods may remain temporarily as
   implementation details for compatibility; they are not V1 protocol members.
5. After type, legacy-double, HTTP, MCP, ambiguity, and isolation tests pass,
   remove the accidental method from the `StorageInterfaceV1` protocol if it is
   still present. Concrete compatibility methods may be retired separately.

No public HTTP/MCP input is made stricter: explicit `notebook_id` continues to
work, omission continues to auto-resolve only when safe, and propagated search
identity remains additive.

## What ADR-0072 got right

- It identified missing notebook identity as a real tool-composition defect.
- It propagated the complete notebook/document/version chain.
- It rejected ambiguity and retained downstream authorization.
- It did not make an asset/document ID a bearer capability.

Only the widening of the frozen storage protocol is superseded. ADR-0072 is
preserved unchanged as historical decision evidence.

## Alternatives

- Keep the widened V1 protocol: rejected because it normalizes frozen-contract
  drift and breaks legacy structural implementations.
- Require `notebook_id` always: rejected because it discards ADR-0072's useful
  composability result.
- Resolve from `document_id` without authorization: rejected as an isolation
  failure.
- Put lookup logic directly in MCP handlers: rejected because HTTP, MCP, and
  Phase 11 would diverge.

## Consequences

Scope resolution becomes reusable and testable without contaminating storage
V1. A temporary compatibility window is required while consumers migrate.

## Security

Resolution and authorization are one fail-closed application boundary. Shared
content hashes, document IDs, or source associations never grant access. Error
mapping follows the existing non-enumeration policy, and every continuation or
delivery call reauthorizes the resolved scope.

## Rollback

Before consumer cutover, rollback is documentation-only. During migration,
restore consumers to the concrete compatibility helper while retaining
explicit notebook propagation and ambiguity checks. Never roll back to
unauthorized document-only delivery.

## Required tests

- Frozen pre-ADR-0072 `StorageInterfaceV1` signature snapshot.
- Explicit, unique, missing, ambiguous, version-mismatch, revoked, and
  cross-notebook resolution.
- Legacy storage double compatibility.
- Search-to-document and search-to-chunk identifier propagation.
- HTTP/MCP error mapping without existence leakage.
- Reauthorization on cursor continuation.

## References

- ADR-0002, ADR-0004, ADR-0058, ADR-0065, ADR-0066, ADR-0068, ADR-0072
- `docs/governance/historical/PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md`
- `docs/governance/contracts/phase8_5_capability_matrix.json`
