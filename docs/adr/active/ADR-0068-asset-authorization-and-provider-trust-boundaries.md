# ADR-0068: Asset Authorization and Provider Trust Boundaries

- **Status:** Accepted
- **Implementation:** Partial — occurrence/notebook authorization implemented
  in 8.5.1; consent/budget/provider-trust enforcement implemented for durable,
  OCR, vision, and image-embedding jobs in 8.5.3–8.5.5; delivery remains pending
- **Date:** 2026-08-24
- **Extends:** ADR-0049, ADR-0059, ADR-0060, ADR-0065 and the frozen Phase 8
  MCP authorization contract
- **Supersedes:** Nothing

## Context

Content-addressed assets may be physically deduplicated across documents and
notebooks. Processing and delivery add cloud egress, binary parsing, and
prompt-injection risks.

## Problem

Authorizing by asset hash/ID leaks shared content. Silent cloud fallback and
unbounded decoders can violate confidentiality, budget, and availability.

## Decision

Every asset read, derivation, search result, and delivery is authorized through
`actor -> notebook -> document -> exact version -> AssetOccurrence`. Physical
deduplication never grants logical access. Denials use non-enumerating typed
errors and are rechecked for cursor pages, jobs, cache hits, and publication.

Provider profiles declare local/cloud trust class, permitted data categories,
region/retention terms, secret reference, model capabilities, and hard resource
limits. Cloud use requires ADR-0060 consent/policy. No silent local-to-cloud
fallback is allowed. Derived content is untrusted, cannot issue instructions,
and cannot confer access to originals.

Binary safety policy covers MIME sniffing, archive/decompression ratios,
decoded pixels, SVG external references/scripts, parser isolation, CPU/memory/
time quotas, quarantine, and typed omissions. Cache namespace binds tenant
policy and trusted immutable inputs; cached outputs are reauthorized.

## Alternatives

- Asset ID as capability: rejected due to cross-notebook leakage.
- Disable deduplication: rejected because it does not solve provider trust.
- One global provider policy: rejected because data sensitivity differs.

## Consequences

Authorization and policy checks occur at more boundaries and need common
services. Some provider operations are correctly blocked despite availability.

## Compatibility

Existing notebook/auth contracts remain. This ADR strengthens only new asset
and processing capabilities and must not broaden old access.

## Migration

Add occurrence ACL/policy references and audit events. Existing assets without
an authorized occurrence are unavailable through Phase 8.5 APIs.

## Security implications

This ADR is the security boundary. Threat models include cross-tenant leakage,
cache poisoning, replay, malicious media, prompt injection, cost DoS, secret
leakage, and stale authorization.

## Testing requirements

Test all cross-scope paths, shared hashes, revoked access, cache hits, cursor
continuation, cloud denial, secrets/logs, malicious formats, quotas, replay, and
concurrent policy change.

## Observability

Audit actor, scoped resource IDs, operation, policy decision, provider trust
class, budgets, and outcome; never content, secrets, or raw tokens.

## Rollback/recovery

Fail closed by disabling asset/processing capability advertisement. Existing
text access remains under its current authorization contract.

## Future-phase impact

Phase 9 must display consent/trust state; Phase 12 providers conform to these
boundaries; Phase 13 audits deployment policies.

## Explicit non-goals

This ADR does not define organization billing or legal retention terms.
