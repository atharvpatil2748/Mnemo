# Module 6.10 Implementation Contradiction Report

**Status:** BLOCKED BEFORE PRODUCTION IMPLEMENTATION  
**Date:** 2026-08-13

## Requirement

Accepted ADR-0046 requires `KnowledgeEngine` to own and expose a configured
`FinalQAOrchestrator` after normal registry startup. The orchestrator must use
the implemented planner, multi-source retrieval, reranking, context, answer,
and citation stages without initializing providers itself.

## Actual runtime composition

`KnowledgeEngine._builtin_plugins()` currently composes storage, parsers,
chunkers, the embedding provider, and optionally the fusion reranker. It does
not compose/register the implemented dense retriever, sparse retriever, parent
promoter, planner, context builder, grounded answer generator, citation engine,
or final orchestrator.

More importantly, `ContextBuilder` and `GroundedAnswerGenerator` require one
`TokenCounterInterfaceV1`. The runtime config and registry contain no tokenizer
asset path, token-counter instance, token-counter capability, or authorized
composition hook. `O200KBaseTokenCounter` requires an explicitly provisioned
asset path and must not discover or download one implicitly.

## Contradiction

ADR-0046 defines final orchestration semantics but not the executable source of
the token counter or the mechanism by which `KnowledgeEngine` obtains the
already-completed Phase 6 component graph. Therefore the required
`KnowledgeEngine` property cannot be constructed from its current configured
state.

Choosing any of the following would invent public architecture:

1. add a tokenizer path/asset section to `MnemoConfig` and make
   `KnowledgeEngine` construct every Phase 6 component;
2. add a token-counter registry capability;
3. add constructor/setter/factory injection for a token counter or complete
   final-QA component bundle;
4. hard-code a machine/cache path or download the tokenizer at startup;
5. expose only a standalone orchestrator and omit the ADR-required
   `KnowledgeEngine` ownership.

Options 4 and 5 directly violate accepted architecture. Options 1–3 are
plausible additive resolutions but have different lifecycle, configuration,
plugin, and compatibility consequences and require an explicit decision.

## Affected contracts

The gap affects `KnowledgeEngine`, `MnemoConfig`, `PluginRegistry`,
`TokenCounterInterfaceV1`, and Phase 6 component composition. No frozen model,
interface, storage contract, or production implementation was modified.

## Smallest recommended resolution

Add a narrow ADR-0046 clarification selecting one composition mechanism. The
smallest option is an additive immutable `FinalQAComponents`/factory supplied
to `KnowledgeEngine` at construction, containing the provisioned token counter
and clock while allowing the engine, after registry startup, to construct and
own the stage orchestrator from resolved providers and registered retrieval
capabilities. This avoids a new registry family and avoids hard-coded tokenizer
paths, but its exact API, validation, and lifecycle must be approved before
implementation.

## Gate conclusion

Standalone final-QA models/orchestration could be coded in isolation, but doing
so would knowingly leave the mandatory `KnowledgeEngine` contract impossible.
Module 6.10 therefore remains **ARCHITECTURE RESOLVED BUT IMPLEMENTATION
BLOCKED** pending the composition clarification. M6 remains not verified.

## Resolution addendum (2026-08-13)

ADR-0047 is accepted. It selects optional immutable
`FinalQAComponents(token_counter, clock)` constructor injection, explicit
offline tokenizer provisioning by the application composition root,
engine-owned registration of dense/sparse/parent built-ins through existing
capability families, and engine-owned post-startup construction of the complete
Phase 6 graph. Existing `KnowledgeEngine(config)` remains valid without final QA;
no config, registry family, storage, schema, frozen contract, or historical
release changes. Module 6.10 is now **ARCHITECTURE RESOLVED / IMPLEMENTATION NOT
STARTED**; M6 remains not verified.

## Implementation addendum (2026-08-13)

ADR-0047 is implemented by immutable `FinalQAComponents` injection and
engine-owned graph composition after registry startup. Existing construction
without final-QA components remains compatible, requested dependency failures
abort initialization, and shutdown drops the graph after registry cleanup.
Module 6.10 is **COMPLETE** under local implementation validation. No M6
milestone or comprehensive Phase 6 audit was run.
