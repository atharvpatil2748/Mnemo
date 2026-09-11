# ADR-0046: Deterministic Final QA Integration

- **Status:** ACCEPTED
- **Date:** 2026-08-13
- **Scope:** Phase 6 Module 6.10
- **Resolves:** `module-6.10-final-qa-integration-contradiction-report.md`

## Context

Modules 6.1–6.9 expose immutable typed stages through
`CitationResolutionResult`. Module 6.10 must compose them without flattening
provenance. ADR-0044 deferred final no-context presentation and streaming;
ADR-0045 requires an already-persisted assistant turn. ADR-0041 preserves
planner `requires_multi_hop` state without defining later hops.

## Decision

Module 6.10 V1 is one additive, non-streaming, fail-fast orchestration boundary:

```python
@runtime_checkable
class FinalQAInterfaceV1(Protocol):
    async def execute(self, request: FinalQARequest) -> FinalQAResult: ...
```

`FinalQAOrchestrator` implements it. `KnowledgeEngine` owns and exposes the
orchestrator after normal registry startup, but is not itself a provider and no
new registry capability is added. Implementation is deferred.

## Immutable request contract

`FinalQARequest` is frozen and slotted and contains exactly:

- `query: str` — normalized with `" ".join(query.split())`, non-empty;
- `metadata_filter: MetadataFilter` — caller hard constraints;
- `global_limit: int` — 1 through 100;
- `context_budget: int` — 1 through 1,000,000;
- `system_prompt: str` — non-empty Module 6.7 fixed-budget input;
- `max_output_tokens: int` — 1 through 4,096;
- `session_id: UUID` — existing session;
- `user_turn_id: UUID` — already-persisted final user turn for this query;
- `assistant_turn_id: UUID` — caller-owned stable idempotency identity;
- `table_of_contents: tuple[str, ...] = ()`;
- `source_titles: tuple[str, ...] = ()`;
- `document_labels: tuple[DocumentContextLabel, ...] = ()`.

The orchestrator loads the session once at the start. The identified user turn
must exist, be `USER`, have content exactly equal to normalized `query`, and be
the session's last turn. Its complete persisted turn prefix through that user
turn is canonical history: it is passed to `QueryPlanner` as `recent_turns` and
converted in order to `Message(role, content)` for `ContextBuilder`. No separate
history representation is accepted.

The planner receives query, table of contents, source titles, and history. The
request filter is projected as a hard constraint onto every returned
`SubQuery.filters`: notebook IDs must agree; non-empty enum/ID sets intersect
(empty intersection is `ContractValidationError`); otherwise the non-empty set
is retained; `date_after` uses the later bound and `date_before` the earlier
bound; an inverted range is invalid. A new immutable effective
`RetrievalPlan` retains planner intent, flags, ordered queries, modes, and
bounds. This is the sole plan executed.

## Canonical execution

After complete request/session preflight:

1. `QueryPlanner.plan()` creates the plan.
2. If `requires_multi_hop` is true, raise `UnsupportedError` immediately after
   planning and before embedding, retrieval, or any write.
3. `MultiSourceRetrievalInterfaceV1.execute(effective_plan, global_limit)` owns
   embedding, retrieval dispatch, source-local promotion, RRF, and global bound.
4. `FusionRerankingInterfaceV1`/`RerankingModule` reranks the exact fusion
   result using the original normalized query.
5. `ContextBuilder.build()` uses the request budget, system prompt, derived
   history, and labels.
6. `GroundedAnswerGenerator.generate()` uses the request output bound.
7. For no context, call `CitationEngine` with no turn and no labels.
8. For a generated answer, persist/reuse the assistant turn as specified below,
   then call `CitationEngine` with only exact-version labels occurring in
   selected context.
9. Return `FinalQAResult` retaining the exact citation result.

The orchestrator dependencies are the existing planner, multi-source
retriever, fusion reranker, context builder, grounded answer generator,
citation engine, `StorageInterfaceV1`, and injected UTC clock. Registry and
provider startup/shutdown remain owned by `KnowledgeEngine`; the orchestrator
does not initialize or close providers.

## Immutable result contract

`FinalQAStatus` has exactly:

- `CITATION_RESOLVED`
- `UNMARKED`
- `NO_CONTEXT`

`FinalQAResult` is frozen/slotted and contains:

- `citation_result: CitationResolutionResult` — the exact object;
- `status: FinalQAStatus`.

Read-only derived properties expose `query`, `answer`, and `citations` from the
nested result without duplicating them. Status maps one-to-one from
`CitationResolutionStatus.RESOLVED`, `UNMARKED`, and `NO_CONTEXT`. Exceptions
are not converted into result states; no additional failure status is needed.

## Assistant-turn sequencing and persistence

The caller persists the user turn and supplies stable session, user-turn, and
assistant-turn UUIDs. The orchestrator owns assistant sequence and timestamp.
V1 is explicitly single-process/single-writer per session: one orchestrator
maintains a per-session async lock from the authoritative session reload through
assistant append and citation resolution. All application writes for that
session must use that composition root. Multi-process writers are unsupported.
No additive storage contract is required for V1.

For a generated answer, under the lock the session is reloaded. If
`assistant_turn_id` is absent, the identified user turn must still be last; the
orchestrator calls its injected clock once, requires timezone-aware UTC not
earlier than the user turn, constructs an `ASSISTANT` turn with sequence
`user.sequence + 1` and exact generated answer content, and persists it with
`StorageInterfaceV1.append_turn()` before citation resolution.

If that assistant ID already exists, it is reused only when session, role,
sequence, and content exactly match the required turn and it immediately follows
the identified user turn; otherwise `ConflictError` is raised. This makes retry
convergent for identical generated output. A later citation failure leaves the
assistant turn and any ADR-0045 citation prefix durable. No rollback or
compensation occurs. Retry uses the same IDs; changed regenerated content
conflicts instead of rewriting conversation history.

## NO_CONTEXT

All four ADR-0043 reasons map to `FinalQAStatus.NO_CONTEXT`. Final `answer` is
`None`; no assistant turn is created or persisted; `CitationEngine` is invoked
with `assistant_turn=None` and empty labels and returns its exact typed
`NO_CONTEXT` result without clock/storage work. Complete nested retrieval,
reranking, context, and empty-reason provenance is retained. No canned factual
or presentation text is invented; transports may render the typed state later.

## UNMARKED

A generated answer without markers is valid with `FinalQAStatus.UNMARKED`. The
answer is returned unchanged, the assistant turn is persisted normally, and
`CitationEngine` returns exact `UNMARKED` with no citation writes. This is a
successful warning state, not an exception or citation-resolved success.

## Streaming

Streaming is explicitly deferred from V1. Module 6.10 uses the completed
`LLMInterfaceV1.complete()` path and exposes no partial answer. The frozen
`LLMInterfaceV1.stream()` remains available but unused. Any future streaming
operation requires a separate versioned contract/ADR defining events,
cancellation, validation, marker resolution, and persistence boundaries.

## Multi-hop

V1 does not implement incomplete multi-hop behavior. When the validated planner
result has `requires_multi_hop=True`, the orchestrator raises
`UnsupportedError` before embedding, retrieval, reranking, generation, clock,
or storage writes. The plan may be attached to error details using existing
immutable metadata, but no partial final result is returned. A future multi-hop
contract must add typed hop provenance and bounds before this behavior changes.

## Failure and cancellation

All stages are sequential and fail-fast. Planner, embedding, retrieval,
promotion, fusion, reranking, context, synthesis, turn persistence, citation
resolution, and citation persistence failures propagate in their existing
types. Caller cancellation propagates. V1 adds no retry, timeout, fallback,
partial result, or compensation. Before assistant append there is no new durable
state. After append, the turn remains durable; after citation writes, any
ADR-0045 prefix remains durable. The per-session lock is always released.

## Provenance and determinism

The exact chain remains:

```text
FinalQAResult -> CitationResolutionResult -> GroundedAnswerResult
  -> ContextBuildResult -> RetrievalRerankResult
  -> RetrievalFusionResult -> FusionEvidence -> ScoredChunk
```

Nothing is reconstructed from rendered context, answer, or citation text, and
nothing is copied into `Chunk.metadata`. Given identical validated provider
outputs, request, session state, and clock values, orchestration and result
construction are deterministic. Provider wording itself is not claimed to be
deterministic.

## Compatibility and migration

This decision is additive. It does not modify `Chunk`, `ScoredChunk`,
`RetrieverInterfaceV1`, `RerankerInterfaceV1`, `StorageInterfaceV1`,
`EmbeddingProviderV1`, `LLMInterfaceV1`, `ParentPromotionInterfaceV1`,
`MultiSourceRetrievalInterfaceV1`, `TokenCounterInterfaceV1`, `RetrievalPlan`,
`RetrievalFusionResult`, `RetrievalRerankResult`, `ContextBuildResult`,
`GroundedAnswerResult`, or `CitationResolutionResult`. No schema, data,
provider, registry, or historical-evidence migration is required.

## Testing and acceptance implications

Implementation must test request/result invariants, filter projection, exact
stage order and object identity, session/user-turn preconditions, assistant
append/reuse/conflict, no-context and unmarked behavior, multi-hop pre-retrieval
rejection, fail-fast/cancellation, durable turn/citation-prefix failures, and
the absence of streaming, retry, timeout, compensation, and provenance loss.
The M6 milestone remains a separate post-implementation audit.

## Alternatives rejected

- Modify frozen stage or storage contracts: unnecessary.
- Generate a canned no-context answer: invents unsupported content.
- Treat unmarked as resolved or as an exception: loses ADR-0045's typed state.
- Implement streaming by forwarding raw tokens: bypasses validated answer and
  citation boundaries.
- Ignore or partially execute multi-hop: misrepresents the plan.
- Random assistant IDs: prevents deterministic retry after citation failure.

## Consequences and acceptance

The complete Phase 6 V1 pipeline now has an executable additive boundary while
honestly deferring streaming and multi-hop. The single-writer constraint is
explicit; multi-process turn sequencing will require a future additive storage
decision. This ADR is accepted because it resolves every Module 6.10 blocker
without changing a frozen contract. Production implementation and M6
verification remain separate tasks.
