# ADR-0047: Final QA Runtime Composition

- **Status:** ACCEPTED — AMENDED 2026-08-14 (see §Amendment)
- **Date:** 2026-08-13
- **Amendment date:** 2026-08-14
- **Clarifies:** ADR-0046
- **Resolves:** `module-6.10-implementation-contradiction-report.md`
- **Resolves (amendment):** `phase-6-comprehensive-audit-contradiction-report.md`

## Context and problem

ADR-0046 requires `KnowledgeEngine` to own the Module 6.10 orchestrator after
normal provider startup. The current engine has no token-counter source and
does not register the implemented dense, sparse, or parent-promotion built-ins.
`O200KBaseTokenCounter` requires an explicitly provisioned verified asset, so
implicit discovery or download is forbidden.

## Decision

Select additive constructor injection of immutable runtime resources, combined
with engine-owned construction of the Phase 6 graph.

```python
@dataclass(frozen=True, slots=True)
class FinalQAComponents:
    token_counter: TokenCounterInterfaceV1
    clock: Callable[[], datetime]

KnowledgeEngine(
    config: MnemoConfig,
    *,
    final_qa_components: FinalQAComponents | None = None,
)
```

This is not a provider factory and owns no lifecycle. It supplies only the two
local runtime resources that cannot lawfully be resolved from existing registry
families. Existing one-argument `KnowledgeEngine(config)` construction remains
valid and preserves pre-Phase-6 behavior; its `final_qa` property raises
`DependencyUnavailableError`. When components are supplied, final QA becomes a
mandatory startup capability and invalid composition fails initialization.

No `MnemoConfig` field and no registry capability is added.

## Tokenizer provisioning

The application composition root explicitly provisions the canonical asset path
and constructs `O200KBaseTokenCounter(asset_path)` before supplying
`FinalQAComponents`. The adapter verifies the fixed asset size/SHA-256 and loads
it offline. Missing, corrupt, incompatible, or unloadable assets raise existing
`DependencyUnavailableError`; no download, cache search, environment probing,
or hard-coded machine path is allowed.

At engine startup, supplied components are validated before final graph
construction: `token_counter` must satisfy `TokenCounterInterfaceV1`, its
`tokenizer_id` must equal the ADR-0015/O200K canonical identity, and a
deterministic `count("") == 0` smoke check must succeed. A missing counter when
final QA was requested is initialization failure.

## Clock

The application supplies a callable UTC clock in `FinalQAComponents` (normally
`lambda: datetime.now(UTC)`). Construction validates callability but does not
consume it. Modules 6.9/6.10 validate each produced value when architecturally
required. The engine never replaces it with an implicit clock.

## Composition ownership

`KnowledgeEngine` owns these inert built-in registrations before registry
freeze, sharing its single primary `CompositeStorage` instance:

- `retriever/dense`: `DenseRetriever(primary_storage)`;
- `retriever/sparse`: `SparseRetriever(primary_storage)`;
- `parent_promotion/default`: `ParentRetriever(primary_storage)`.

They use existing registry priority/conflict/version/freeze semantics and may be
replaced only by an explicitly higher-priority compatible plugin. Equal
priority conflicts fail normally. No new capability family is introduced.

_(Amendment 2026-08-14: the slot name above was `parent_promotion/primary` in
the original accepted text. ADR-0040 §Registry and capability semantics and
ADR-0041 §Constraints both establish `parent_promotion/default` as the
canonical slot. The original slot name was a drafting error in this ADR. No new
capability family is introduced; the canonical slot name is corrected here.)_

After plugin loading, startup hooks, registry freeze, and provider resolution,
`KnowledgeEngine` constructs exactly one graph when `FinalQAComponents` exists:

- `QueryPlanner(resolved llm/planner, resolved embedding_provider/primary)`;
- `MultiSourceRetriever(frozen registry, resolved embedding provider)`;
- `RerankingModule(frozen registry)`;
- `ContextBuilder(frozen registry, injected token counter)`;
- `GroundedAnswerGenerator(frozen registry, injected token counter)`;
- `CitationEngine(resolved storage/primary, injected clock)`;
- `FinalQAOrchestrator` from those exact components, storage, and clock.

The engine stores and exposes that exact orchestrator through a read-only
`final_qa: FinalQAInterfaceV1` property only while `READY`. The orchestrator
does not initialize, register, resolve, or close providers.

## Provider validation

When final QA components are supplied, initialization fails atomically if any
mandatory dependency is absent or incompatible:

- primary storage or embedding provider;
- `llm/planner`, `llm/synthesizer`, or `llm/extractor`;
- `retriever/dense`, `retriever/sparse`, or
  `parent_promotion/default`;
- canonical token counter or callable clock.

_(Amendment 2026-08-14: `parent_promotion/primary` corrected to
`parent_promotion/default` to match ADR-0040/ADR-0041.)_

Existing constructors/capability checks remain authoritative. Fusion reranker
absence is not a composition failure because ADR-0042 explicitly defines typed
RRF fallback. Citation persistence is satisfied by `StorageInterfaceV1`; no
backend probing or direct SQLite dependency is introduced. Failure discards the
partial graph and follows existing engine initialization cleanup/error wrapping.

## Lifecycle

Provider/plugin construction and registration remain inert. `KnowledgeEngine`
loads plugins, freezes the registry, executes registered startup hooks, resolves
and validates providers/resources, then constructs the final graph. Thus models
are loaded before use. On shutdown, existing registry hooks run in their
deterministic reverse order; afterward the engine drops the orchestrator and
resolved graph. `FinalQAComponents`, the token counter, clock, and orchestrator
have no independent startup/shutdown hooks.

## Alternatives rejected

- Add tokenizer path to `MnemoConfig`: couples provider-neutral runtime config
  to one local adapter and changes every configuration surface.
- Add a token-counter registry family: unnecessary for a mandatory local
  immutable utility with no provider lifecycle.
- Inject a fully constructed Phase 6 graph/factory: weakens engine ownership,
  duplicates provider resolution, and permits lifecycle-incompatible graphs.
- Discover/download/hard-code the asset: violates offline deterministic
  provisioning.
- Expose only a standalone orchestrator: violates ADR-0046 engine ownership.

## Compatibility and migration

The constructor keyword is optional, so existing construction remains source
compatible. Existing runtime behavior is unchanged unless final QA composition
is explicitly requested. `MnemoConfig`, registry families, storage/schema, and
historical releases require no migration.

No frozen Phase 1 or accepted Phase 6 contract changes: `Chunk`, `ScoredChunk`,
all frozen provider/retrieval/token interfaces, and all existing stage result
models remain unchanged. `KnowledgeEngine` and its built-in composition are not
frozen provider contracts.

## Testing and acceptance requirements

Implementation must test optional backward-compatible construction, component
validation, canonical tokenizer identity/smoke count, no clock consumption at
startup, built-in retrieval registrations and plugin override/conflict rules,
missing/incompatible dependency startup failure, graph identity/readiness,
shutdown graph removal, and absence of new registry/config/storage behavior.

## Consequences and acceptance

The decision supplies the missing runtime resources explicitly while keeping
provider resolution and lifecycle in `KnowledgeEngine`. It is the smallest
mechanism that makes ADR-0046 executable without hidden discovery, a new
registry family, configuration/schema migration, or frozen-contract change.
Module 6.10 architecture is resolved; implementation and M6 verification remain
separate tasks.
