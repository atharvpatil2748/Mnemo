# ADR-0045: Deterministic Citation Resolution and Persistence

- **Status:** Accepted
- **Date:** 2026-08-13
- **Decision owners:** Mnemo maintainers
- **Extends:** ADR-0001, ADR-0002, ADR-0044
- **Preserves:** ADR-0040, ADR-0041, ADR-0042, ADR-0043
- **Resolves:** `module-6.9-citation-resolution-contradiction-report.md`

## Context

ADR-0044 established the executable order `ContextBuildResult ->
GroundedAnswerResult -> Citation Engine` and intentionally deferred all
Module 6.9 details. The exact `GroundedAnswerResult` retains every selected
`ContextItem` and its canonical versioned `Chunk`, so citation provenance does
not require parsing context headers or querying retrieval storage.

The frozen ADR-0001 `Citation` additionally requires an assistant turn, a
non-empty title, a verbatim quote, stable identity, and resolution timestamp.
Those values are not all present in `GroundedAnswerResult`. The frozen storage
facade offers only individual citation upserts; its concrete composite routes
conversation data to SQLite, while corresponding SurrealDB methods are stubs.

## Problem

Module 6.9 cannot be implemented without deciding marker grammar and errors,
title and quote sources, assistant-turn ownership, citation identity/time,
duplicate behavior, persistence ordering, partial failure, and the typed
Module 6.10 handoff. It also cannot promise atomic turn-plus-citation or
multi-citation persistence through `StorageInterfaceV1`.

## Scope and constraints

Module 6.9 owns only marker validation/resolution, immutable citation snapshot
construction, per-citation persistence, and its typed handoff. It does not
generate answers, reconstruct context, access a concrete backend, create or
sequence turns, present a final QA response, stream, retry, or implement Module
6.10.

`Chunk`, `Citation`, `Turn`, `GroundedAnswerResult`, `ContextBuildResult`, and
all frozen Phase 1 and prior Phase 6 interfaces remain unchanged. The design is
additive and depends only on `StorageInterfaceV1`.

## Alternatives considered

- A new transactional `StorageInterfaceV2` or modification to V1: rejected as
  unnecessary and breaking.
- Direct SQLite/SurrealDB transactions: rejected as backend leakage.
- Citation resolution during generation: rejected by ADR-0044.
- Reparse rendered source headers or query storage: rejected because typed
  provenance is already retained and titles must be explicit.
- Persist compressed text as a quote: rejected because it is not canonical
  verbatim evidence.
- Create the assistant turn in Module 6.9: rejected because conversation
  sequencing and combined atomicity are unavailable at this boundary.

## Decision

Add a backend-neutral `CitationEngine` and immutable Module 6.9 result models.
The engine receives the exact `GroundedAnswerResult`, an already-persisted
assistant `Turn` for generated answers, and caller-supplied exact-version
`DocumentContextLabel` values. It resolves markers exclusively against retained
`ContextItem.source_number`, constructs deterministic ADR-0001 `Citation`
records from canonical chunks, and persists each through
`StorageInterfaceV1.upsert_citation()`.

## Input contract

The canonical operation is conceptually:

```python
async def resolve_and_persist(
    answer_result: GroundedAnswerResult,
    *,
    assistant_turn: Turn | None,
    document_labels: tuple[DocumentContextLabel, ...] = (),
) -> CitationResolutionResult
```

`CitationEngine` is constructed with one `StorageInterfaceV1` and a UTC clock.
The clock is invoked exactly once after complete validation when at least one
citation will be constructed. It is not invoked for `NO_CONTEXT` or unmarked
answers.

For `GENERATED`, `assistant_turn` is required, must have role `ASSISTANT`, and
its content must equal `answer_result.answer` exactly. The caller owns UUID,
session, sequence, creation time, and prior persistence of that exact turn.
Module 6.9 neither appends nor reloads it. For `NO_CONTEXT`, `assistant_turn`
must be `None`, labels must be empty, and no storage or clock work occurs.

Labels use the existing `DocumentContextLabel`. Keys `(document_id,
version_id)` must be unique. Extra keys are invalid unless that exact version
appears among selected context items. Every referenced source number requires
one matching label. The caller must pass the same authoritative labels used by
the surrounding orchestration; Module 6.9 never parses rendered headers to
recover them.

## Output contract

Add:

```text
CitationResolutionStatus = RESOLVED | UNMARKED | NO_CONTEXT

CitationResolutionResult
  answer_result: exact GroundedAnswerResult
  assistant_turn: exact Turn | None
  status: CitationResolutionStatus
  citations: tuple[Citation, ...]
  persisted: bool
```

`RESOLVED` requires a generated answer, a retained assistant turn, one or more
citations, and `persisted=True`. `UNMARKED` requires a generated answer and
assistant turn, an empty citation tuple, and `persisted=False`. `NO_CONTEXT`
requires the exact no-context answer result, no turn, no citations, and
`persisted=False`.

Module 6.10 consumes the complete `CitationResolutionResult`; it does not
reparse answer markers or reconstruct retrieval provenance.

## Marker grammar and parsing

The only V1 marker grammar is ASCII and case-sensitive:

```text
marker = "[source:" positive-decimal "]"
positive-decimal = nonzero-digit *digit
nonzero-digit = "1" … "9"
digit = "0" … "9"
```

The answer is scanned left-to-right. Every exact `[source:` prefix is reserved
and must begin a complete marker at that position. Zero, signs, whitespace,
leading zeroes, missing digits/brackets, or any other suffix are malformed and
raise `IntegrityError`. Case variants and strings without the exact reserved
prefix are ordinary answer text.

A syntactically valid number must equal one selected
`ContextItem.source_number`. Unknown numbers—including numbers that could only
refer to omitted candidates—raise `IntegrityError`. Source numbers are positive
and contiguous by ADR-0043, but the resolver uses the typed item map rather
than assuming tuple offsets.

Repeated markers are valid. Each unique source number contributes exactly one
citation. The first textual occurrence determines citation tuple and
persistence order; later occurrences do not create duplicates. Different
source numbers remain distinct even when they share a document or version.
Unused selected context items are valid. A generated answer with no markers is
a valid `UNMARKED` result; Module 6.9 does not judge whether uncited prose is a
supported claim.

## Citation mapping

For each first-occurring unique source number, map directly to the exact
selected `ContextItem`, then its retained canonical chunk:

| `Citation` field | V1 source |
|---|---|
| `turn_id` | supplied assistant turn |
| `source_number` | parsed marker number |
| `chunk_id` | `ContextItem.reranked_result.fused_result.chunk.id` |
| `document_id` | canonical chunk `document_id` |
| `version_id` | canonical chunk `version_id` |
| `document_title` | matching exact-version `DocumentContextLabel.title` |
| `page_number` | canonical chunk `position.page_number` |
| `heading_path` | canonical chunk `heading_path` |
| `verbatim_quote` | complete canonical `Chunk.text` |
| `created_at` | one UTC resolution time shared by the invocation |

The full canonical chunk text is the deterministic V1 verbatim excerpt. A
compressed `ContextItem` still cites its original canonical chunk text, never
the query-transient compressed summary. No title comes from storage, chunk
metadata, rendered headers, or a placeholder.

Parent-promoted chunks cite the promoted canonical chunk retained in the item.
Dense, sparse, hybrid, RRF, reranking, and compression evidence remain nested
in the exact retained answer result and are not duplicated into `Citation`.

## Citation identity and duplicates

`citation_id` is deterministic:

```python
uuid5(
    NAMESPACE_URL,
    f"mnemo:citation:v1:{turn_id}:{source_number}:{chunk_id}",
)
```

UUIDs use canonical lowercase string formatting in the name. This makes repeat
execution converge through existing storage upsert semantics. Repeated markers
within one answer never cause repeated writes. Different turns, source numbers,
or chunks produce different identities. Existing identical identities are
idempotently replaced by the same resolved snapshot.

## Timestamp ownership

The engine-owned injected clock returns a timezone-aware UTC `datetime`.
Naive/non-UTC values or a resolution time earlier than the assistant turn's
creation time raise `IntegrityError` before persistence. All citations from one
invocation share that single timestamp. No persistent timestamp is inferred
from generation metadata or storage.

## Persistence backend and transaction semantics

The engine depends only on `StorageInterfaceV1`. For Phase 6, the canonical
conversation/citation implementation is SQLite behind `CompositeStorage`.
Direct SQLite and SurrealDB access are forbidden. Active architecture claims
that SurrealDB currently owns citation persistence are superseded; its citation
methods remain unimplemented future adapter work.

All markers, labels, turn invariants, identities, timestamps, and `Citation`
records are validated and constructed before the first write. Citations are
then upserted sequentially in first-marker order. Each
`upsert_citation(citation)` is one atomic persistence unit under the frozen V1
facade. There is no false claim of atomicity across the tuple or with the
pre-existing turn.

If a later upsert fails or cancellation arrives, earlier successful upserts may
remain. No rollback is attempted because V1 has neither citation deletion nor a
public batch transaction. No partial result is returned. The exception or
cancellation propagates. Retrying the same validated inputs converges because
identities are deterministic and upserts are idempotent. Module 6.9 performs no
automatic retry, timeout, or compensation.

## Failure semantics

- Wrong input types, invalid generated/no-context combinations, missing or
  mismatched assistant turn, duplicate/out-of-scope labels, and missing cited
  titles raise `ContractValidationError` before storage.
- Malformed or unknown markers, inconsistent retained item/chunk identity,
  invalid clock output, and invalid constructed snapshots raise
  `IntegrityError` before storage.
- A referenced assistant turn, chunk, document, or version missing from
  persistence surfaces the existing storage-layer failure. Module 6.9 does not
  query or silently repair it.
- Citation ID conflicts are resolved only by the deterministic identity and
  existing upsert contract; no alternate random identity is generated.
- Storage errors and provider-independent infrastructure failures propagate.
- Caller cancellation propagates. No partial `CitationResolutionResult` is
  returned.
- `NO_CONTEXT` and `UNMARKED` are valid typed outcomes, not failures.

## Determinism and provenance

Given identical immutable inputs and clock output, parsing, unique-marker
order, citation identities, snapshots, persistence call order, and result are
identical. Storage scheduling never determines output order.

The exact chain remains:

```text
CitationResolutionResult
  -> GroundedAnswerResult
    -> ContextBuildResult
      -> ContextItem
        -> RerankedChunkResult
          -> FusedChunkResult
            -> FusionEvidence
              -> ScoredChunk
```

No provenance is reconstructed from answer/context text, queried by chunk ID,
or copied into canonical metadata. Multi-document and multi-version evidence
remains distinct by source number and exact canonical chunk/version identity.

## Compatibility and migration

This decision is additive. No frozen model, interface, registry capability, or
storage schema changes. No data migration is required. Existing
`StorageInterfaceV1.upsert_citation()` and SQLite schema are sufficient for the
explicit per-record transaction model.

The operational consequence is visible partial persistence on failure. A
future atomic batch capability would require a separate additive storage ADR;
it is not smuggled into Module 6.9.

## Module 6.10 boundary

Module 6.10 coordinates creation/persistence of the assistant turn before a
generated answer enters Module 6.9 and supplies the exact labels used by its
query flow. It consumes `CitationResolutionResult` and owns final QA response,
typed no-context presentation, and any streaming delivery. ADR-0045 does not
implement those responsibilities or prescribe an API beyond the required
handoff.

## Testing and acceptance requirements

Implementation must test:

- the exact marker grammar, malformed/unknown/omitted numbers, first-occurrence
  ordering, repeats, and unmarked answers;
- all four upstream no-context reasons without clock/storage work;
- turn role/content/identity preconditions and label completeness/uniqueness;
- exact field mapping for verbatim and compressed items, titles, pages,
  headings, parent-promoted chunks, documents, and versions;
- deterministic IDs, one shared UTC timestamp, retry convergence, and
  sequential call order;
- storage failure/cancellation with no partial result and documented durable
  prefix behavior;
- exact object-identity provenance retention and immutable outputs;
- real `CompositeStorage`/SQLite persistence using an already-persisted
  assistant turn and real Module 6.8 golden handoff.

Acceptance must verify marker-to-item mapping, stored/reloaded citation
snapshots, multiple documents/versions where available, deterministic retry,
no direct backend access, and no mutation of historical evidence.

## Consequences

Positive:

- Module 6.9 becomes executable without modifying frozen contracts.
- Citation snapshots use exact canonical versioned evidence and remain usable
  when context was compressed.
- Deterministic IDs make existing per-record upserts retry-convergent.
- SQLite reality and architecture documentation agree.

Trade-offs:

- Callers must supply an already-persisted assistant turn and complete titles
  for cited versions.
- V1 cannot offer all-or-nothing multi-citation persistence; partial durable
  prefixes are explicit rather than hidden.
- Semantic detection of unsupported uncited claims remains outside mechanical
  citation resolution.

## Acceptance criteria

This ADR is accepted because it defines the complete Module 6.9 input/output,
marker, mapping, title, quote, identity, timestamp, persistence, duplicate,
failure, cancellation, provenance, and Module 6.10 handoff semantics; preserves
all frozen contracts; requires no migration; and leaves production
implementation for a separate task.
