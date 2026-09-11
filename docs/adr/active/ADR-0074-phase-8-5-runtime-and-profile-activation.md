# ADR-0074: Phase 8.5 Runtime and Profile Activation

- **Status:** Accepted
- **Implementation:** WP-01 runtime composition, WP-02 generation discovery,
  dependency gating, coverage validation, and atomic activation are implemented
  and focused-tested. WP-15 adds the authoritative strict profile document,
  deterministic precedence, immutable redacted snapshot, exact profile/generation
  binding, and V1-only/disabled modes. Behavioral verification and final
  certification remain WP-16/WP-17 gates.
- **Date:** 2026-08-26
- **Extends:** ADR-0003, ADR-0004, ADR-0018, ADR-0060–ADR-0064, ADR-0067, ADR-0070, ADR-0071
- **Supersedes:** Nothing

## Context

Phase 8.5 contains provider-neutral models, stores, and services for assets,
jobs, OCR, Vision, visual embeddings, advanced/structured/multilingual/
multimodal retrieval, and Final-QA V2. Their existence does not prove that a
provider is configured, a projection is active, a server exposes the service,
or an evaluation certified its behavior. Evaluation scripts and the production
engine currently construct different subsets.

## Decision

### `Phase85RuntimeV1`

An additive `Phase85RuntimeV1` is the immutable, engine-owned service bundle
for Phase 8.5. Its contract exposes typed accessors/readiness for:

- asset catalog, authorization, and bounded delivery;
- processing job store/worker policy and cost governance;
- OCR, Vision, visual embedding, and derived projection builders;
- advanced/exhaustive, structured, multilingual, multimodal, and bounded
  multi-document retrieval;
- Final-QA V2 execution and replay;
- document-scope resolution;
- capability/readiness reporting.

The production composition root alone resolves stores, providers, profiles,
generation aliases, authorizers, cursor codecs, and services. HTTP, MCP,
workers, and evaluation scripts consume this runtime rather than construct
parallel graphs. Initialization is lazy: disabled or unavailable Phase 8.5
providers do not break V1 startup and do not load large models.

`StorageInterfaceV1` and V1 engine provider resolution remain unchanged. New
capabilities depend on additive protocols/stores.

### Capability lifecycle

Each capability progresses monotonically for one exact profile/generation and
deployment snapshot:

```text
DECLARED → CONFIGURED → BUILDABLE → READY → ACTIVE → EXPOSED → VERIFIED → CERTIFIED
```

- **DECLARED:** contract and owner exist.
- **CONFIGURED:** a syntactically valid enabled profile selects exact provider,
  model/revision, policy, and bounds.
- **BUILDABLE:** dependencies, assets, authorization, provider capability, and
  resource admission allow a generation to be built.
- **READY:** required artifacts/projections passed integrity and coverage checks.
- **ACTIVE:** an atomic alias selects one READY generation; BUILDING/FAILED/
  SUPERSEDED/RETIRED generations are not served.
- **EXPOSED:** a configured HTTP/MCP adapter advertises the active capability.
- **VERIFIED:** deterministic service/protocol/behavior and security gates pass
  for the exact deployment snapshot.
- **CERTIFIED:** ADR-0070 governance evidence approves the exact profile,
  generation, hardware/trust scope, and corpus/evaluation version.

A state may be `DISABLED`, `UNAVAILABLE`, `POLICY_DENIED`, `BUDGET_DENIED`,
`FAILED`, or `UNVALIDATED` with a safe reason. No later state is inferred from
an earlier state. In particular, a configured model is not ready, an existing
class is not active, and a direct-call test is not behavioral certification.

### Provider/profile registry

Profiles are provider-neutral records keyed by stable profile ID and include
operation, provider/trust class, model and immutable revision, dimensions/
metric where applicable, preprocessing/analyzer/schema versions, language and
media capabilities, cost/resource policy, generation identity, and
certification evidence. Secrets are referenced through the existing secret
mechanism and never stored in profiles/manifests.

There is one authoritative production profile source with documented
environment precedence. Evaluation candidates and local defaults are labeled
`NON_CERTIFIED_DEFAULT` or `CANDIDATE`; they do not silently become production
certified. Cloud/paid fallback is never implicit.

### Optional backends and V1/V2 separation

Qdrant, cloud providers, GPUs, OCR/VLM, translations, and visual spaces remain
optional. An unavailable backend produces a truthful capability state and
completeness omission; it never converts to no-match or silently changes
provider. V1 text embedding/reranker identities and configuration remain
separate from Phase 8.5 profiles and are not replaced by activation of V2.

### Phase 11 boundary

Phase 11 receives model-neutral typed service interfaces, result sets,
evidence, completeness, capability states, and opaque cursors. It does not
receive SQLite tables, blob paths, projection aliases, provider credentials,
or model-specific control flow. Phase 11 owns adaptive planning, not runtime
composition.

## Alternatives

- Treat configuration/class presence as support: rejected as false capability
  advertisement.
- Compose services independently in each adapter/script: rejected because
  identity, policy, and provider state drift.
- Replace V1 provider configuration: rejected by the frozen boundary.
- Require every backend at startup: rejected because optionality is accepted.

## Consequences

Capability reporting becomes reproducible and truthful. Runtime composition
gains an additive abstraction and lifecycle bookkeeping, while model loading
and derived generation activation remain explicit operational steps.

WP-02 maps a generation-backed service into this runtime only when its active
alias selects an exact profile-compatible `READY` generation whose immutable
coverage manifest is complete and whose count/checksum matches the generation.
Provider readiness without this projection state remains insufficient.

## Security

The runtime must make authorizer, consent, trust, budget, resource admission,
and safe logging mandatory dependencies for expensive operations. Capability
discovery is actor/scope aware and does not reveal inaccessible resources or
provider secrets.

## Rollback

Disable exposure, move the active alias to the prior READY generation, and
stop workers while retaining recoverable state. V1 continues independently.

## Required tests

- Lifecycle implication/property tests and invalid-state rejection.
- Composition with complete, partial, disabled, and unavailable dependencies.
- Exact provider/profile/generation identity and no hidden fallback.
- Lazy initialization/shutdown and optional-Qdrant behavior.
- Capability advertisement agrees with runtime state.
- Legacy engine and storage doubles remain compatible.

## References

- `docs/governance/historical/PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md`
- `docs/governance/contracts/phase8_5_capability_matrix.json`
- ADR-0003, ADR-0004, ADR-0018, ADR-0070, ADR-0071
