# Module 6.10 Final QA Integration Contradiction Report

**Status:** BLOCKED AT THE ARCHITECTURE GATE  
**Date:** 2026-08-13  
**Scope:** architecture evidence only; no Module 6.10 production implementation

## Requirement and existing authority

Module 6.10 must compose the completed Phase 6 stages, return a typed final QA
result with complete provenance, present typed no-context outcomes, sequence the
assistant turn required by ADR-0045, and own final streaming delivery. ADR-0041
also preserves `requires_multi_hop=True` for Module 6.10.

ADR-0041 returns one bounded first-stage `RetrievalFusionResult` but does not
define later hops. ADR-0044 explicitly defers no-context presentation and
streaming to Module 6.10. ADR-0045 returns `CitationResolutionResult` but
requires the caller to supply an already-persisted assistant `Turn` and does not
create, sequence, or persist it. `KnowledgeEngine` currently owns lifecycle and
provider resolution but exposes no canonical query/final-QA operation.

## Genuine contradictions and omissions

1. **No orchestration input contract.** There is no canonical request defining
   query/planner inputs, notebook/session identity, filters, retrieval bounds,
   context inputs, labels, output bound, or turn-persistence inputs.
2. **No final output/status contract.** No immutable final result defines how
   `RESOLVED`, `UNMARKED`, and `NO_CONTEXT` map to final QA outcomes. Treatment
   of a generated but unmarked answer is undefined.
3. **Assistant-turn sequencing is circular.** ADR-0045 requires the exact
   answer in an already-persisted turn, while Module 6.10 nominally owns
   sequencing. Turn UUID/time ownership, user-turn handling, atomic next
   sequence under concurrency, and turn-success/citation-failure behavior are
   unspecified. The frozen facade has no compare-and-append or combined
   turn/citation transaction.
4. **No-context presentation is undefined.** No final text/status, persistence,
   assistant-turn, or citation behavior exists for ADR-0043's four empty
   reasons.
5. **Streaming is undefined.** There is no event schema, ordering, completion
   boundary, citation timing, buffering, cancellation, partial-output, or
   persistence policy. `LLMInterfaceV1.stream()` cannot alone construct the
   validated immutable downstream results.
6. **Multi-hop is undefined.** Entity extraction, hop query construction,
   filter inheritance, bounds, fusion, termination, failure, and multi-hop
   provenance are unspecified. A one-plan `RetrievalFusionResult` cannot be
   silently reinterpreted as multi-hop evidence.
7. **Composition ownership is undefined.** The documents do not decide whether
   to extend `KnowledgeEngine`, inject a separate orchestrator, or register a
   versioned capability, nor define cross-stage concurrency/cancellation.

## Affected contracts

The ambiguity touches `KnowledgeEngine`, `RetrievalPlan`,
`RetrievalFusionResult`, `RetrievalRerankResult`, `ContextBuildResult`,
`GroundedAnswerResult`, `CitationResolutionResult`, `Turn`, `Session`, and
`StorageInterfaceV1`. None was modified.

## Smallest compatible resolution

One focused additive ADR is required before implementation. It must define:

1. an immutable final QA request containing every caller input and bound;
2. an immutable final QA result retaining the exact
   `CitationResolutionResult`, with generated/unmarked/no-context semantics;
3. a canonical non-streaming V1 method and dependency ownership;
4. turn UUID, timestamp, sequence, persistence, concurrency, and partial-failure
   semantics compatible with ADR-0045;
5. exact no-context and unmarked-answer presentation;
6. either a complete versioned streaming contract or explicit deferral;
7. either a complete multi-hop contract or typed rejection/defer behavior for
   `requires_multi_hop=True`;
8. stage failure/cancellation and `KnowledgeEngine` integration boundaries.

The preferred solution is additive and retains every accepted nested result.
Turn sequencing may require an additive storage operation or an explicitly
single-writer policy; that decision requires approval.

## Compatibility and gate conclusion

No frozen contract, production code, schema, version, or historical evidence
was modified. Module 6.10 cannot be implemented without inventing public API,
persistence, streaming, no-context, and multi-hop behavior. It remains
**BLOCKED / NOT IMPLEMENTED**. Modules 6.1–6.9 remain complete, and M6 remains
not verified.

## Resolution addendum (2026-08-13)

ADR-0046 is accepted and resolves all blockers above with an additive immutable
request/result, one non-streaming final-QA orchestrator, caller-stable turn IDs
and per-session single-writer sequencing, typed `NO_CONTEXT` and `UNMARKED`
outcomes, pre-retrieval `UnsupportedError` for multi-hop plans, fail-fast
cancellation/failure semantics, and exact nested provenance retention.
Streaming and complete multi-hop execution are explicitly deferred to future
versioned contracts. No frozen contract or production code changed. Module 6.10
is now **ARCHITECTURE RESOLVED / IMPLEMENTATION NOT STARTED**; M6 remains not
verified.

## Implementation addendum (2026-08-13)

ADR-0046 and ADR-0047 are implemented. The additive final-QA contracts and
orchestrator compose the complete typed Phase 6 chain, preserve nested
provenance, reject multi-hop before downstream work, and implement
single-writer assistant-turn sequencing. Module 6.10 is **COMPLETE** under
local implementation validation. The comprehensive Phase 6 audit and M6
milestone were not run; M6 remains not verified.
