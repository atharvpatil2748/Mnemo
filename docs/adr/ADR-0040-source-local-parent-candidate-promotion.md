# ADR-0040: Source-Local Parent Candidate Promotion

- **Status:** Accepted
- **Date:** 2026-08-13
- **Decision owners:** Mnemo maintainers
- **Extends:** ADR-0002, ADR-0015, ADR-0038, ADR-0039
- **Resolves:** `module-6.4-parent-retriever-contradiction-report.md`

## Context

The retrieval architecture promotes retrieved child chunks to their canonical
parent when at least half of the parent's stored child family is represented.
This is a transformation over retrieval results, not a query against a search
backend.

`RetrieverInterfaceV1.retrieve()` accepts query text, an optional vector,
`MetadataFilter`, and `top_k`; it cannot receive already-retrieved candidates.
Its implementations also promise one raw, source-specific score scale.
Overloading the query, rerunning dense/sparse retrieval, or using hidden state
would violate accepted contracts. The earlier Module 6.2 and Module 6.4
contradiction reports correctly stopped implementation at this boundary.

ADR-0015 already supplies an explicit single-parent forest: a child's
`parent_chunk_id` points to its canonical parent, while `sibling_ids` is
symmetric, deterministic, self-excluding, and contains exactly the other
stored children sharing that non-null parent. ADR-0038 and ADR-0039 make
retrieval filters document/version scoped and require exact-version identity.

## Problem

Module 6.4 needs a typed candidate input and deterministic replacement rules.
The architecture must define candidate scope, score/source/rank provenance,
top-k timing, ordering, duplicate handling, integrity failures, storage access,
and plugin resolution without prematurely implementing Module 6.5 fusion.

The `RetrievalMode.PARENT` enum value is retained for deserialization
compatibility, but it does not make parent promotion a query-executing
retriever. Parent promotion is an invariant pipeline stage over each executable
retriever's result stream. The planner must not emit new parent-mode
subqueries, and Module 6.5 must reject a legacy parent-mode subquery explicitly
rather than dispatching it to `RetrieverInterfaceV1` or silently ignoring it.

## Existing constraints

- `RetrieverInterfaceV1`, `StorageInterfaceV1`, `MetadataFilter`,
  `ScoredChunk`, and `Chunk` remain unchanged.
- Dense and sparse results carry raw, mutually incomparable score scales.
- Retrieval streams contain at most upstream `top_k` unique chunks, ordered by
  descending raw score with chunk-ID tie-breaking and contiguous one-based
  ranks.
- All hard metadata filters execute before backend ranking/top-k.
- Parent/sibling identity comes only from stored Chunk relationships.
- Module 6.5 owns parallel dispatch, cross-source deduplication, RRF/fusion,
  and global ranking.

## Considered alternatives

| Option | Assessment | Decision |
|---|---|---|
| A. Typed candidate-promotion contract | Models the actual input, preserves V1 contracts, remains backend-neutral, and is independently testable. | Selected |
| B. Decorator over one `RetrieverInterfaceV1` | Hides retrieval inside promotion, couples lifecycle and failure semantics, and cannot cleanly serve every source without duplicate wrappers. | Rejected |
| C. Implement promotion inside Module 6.5 | Exposes candidates but collapses the 6.4 boundary into fusion and prevents independent plugin/testing semantics. | Rejected |
| D. `RetrieverInterfaceV2` | Adds irrelevant candidate inputs to ordinary retrievers and creates unnecessary migration/versioning cost. | Rejected |

## Decision

Module 6.4 introduces a new additive Phase 6 protocol,
`ParentPromotionInterfaceV1`. The roadmap implementation remains named
`ParentRetriever`, but that class implements the promotion protocol rather than
`RetrieverInterfaceV1`.

Promotion is **source-local and single-pass**. Each already bounded output
stream from one retriever invocation is promoted independently before Module
6.5 combines streams. Dense evidence cannot combine with sparse evidence to
satisfy the 50-percent threshold. Thus, for a four-child family where dense
returns C1 and sparse returns C2, each stream represents 1/4 and neither
promotes. This is the smallest rule that preserves raw score provenance and
does not pre-implement fusion.

## Candidate contract

The implementation contract is conceptually:

```python
@runtime_checkable
class ParentPromotionInterfaceV1(Protocol):
    @property
    def promotion_mode(self) -> str: ...  # "parent"

    def capabilities(self) -> ParentPromotionCapabilities: ...

    async def promote(
        self,
        candidates: tuple[ScoredChunk, ...],
    ) -> tuple[ScoredChunk, ...]: ...
```

The promoter receives `StorageInterfaceV1` as a constructor dependency for
canonical lookups. It receives no query, embedding, filter, or backend client.
An empty tuple returns an empty tuple without storage work.

Non-empty input must be one valid upstream stream: unique chunk IDs, one
non-empty `source`, contiguous one-based ranks in tuple order, and the
ADR-0002 deterministic descending-score order. Invalid input raises the common
contract/integrity error; it is never silently repaired.

## Candidate scope

One `promote()` call contains candidates from exactly one retriever invocation
and therefore one raw score/source domain. Multiple planner subqueries and
multiple retrievers remain separate calls. Module 6.5 will invoke promotion on
each successful source-local stream before cross-source combination.

Promotion is computed only from the input candidates. Newly emitted parents
are not recursively reconsidered for grandparent promotion during the same
call. An original candidate may itself participate as a child in another
qualifying family, so one deterministic pass may emit context from adjacent
hierarchy levels without treating a newly promoted result as new evidence.

## Family and threshold semantics

For a candidate with non-null `parent_chunk_id`, its complete stored family is:

```text
{candidate.id} union set(candidate.sibling_ids)
```

All members must exist and share the same non-null parent, document, and
version; every member's sibling set must equal the family minus itself.
Qualification uses unique original candidate identities:

```text
represented family members / complete stored family size >= 0.5
```

Therefore 1/4 does not promote, while 2/4, 3/4, and 4/4 promote. A sole child
with a real parent has a family size of one and promotes at 1/1. Roots are
ignored and may not form a sibling family. Duplicate input chunks are invalid
and never increase the numerator.

## Score semantics

For each qualifying family, the canonical representative is its earliest
represented child in input rank order. The promoted parent inherits that
representative's score **without transformation**. No mean, sum,
normalization, or cross-source comparison occurs.

The inherited value remains the upstream source's raw evidence score; it is
not asserted to be a score produced by independently searching for the parent.
If the same parent already occurs as an original candidate, duplicate handling
below selects the earliest surviving occurrence and its unchanged score.

## Source semantics

The promoted result retains the representative candidate's `source`. It does
not use `source="parent"`, because `ScoredChunk.source` identifies the score's
ranking domain and the inherited score came from the upstream retriever.
`promotion_mode="parent"` identifies the transformation capability itself.
No new provenance field is added to the frozen model.

## Rank semantics

Replacement preserves input positions: a qualifying parent is inserted at the
position of the family's earliest represented child, and all represented
children in that family are removed. Unpromoted candidates retain relative
order. After all replacements and local duplicate elimination, ranks are
recomputed contiguously from one in output order.

Rank remains local to this upstream stream. Module 6.5 later owns global/fused
rank.

## Top-k semantics

Backend `top_k` is applied before promotion by DenseRetriever or
SparseRetriever. `ParentPromotionInterfaceV1` has no `top_k` argument because
replacement and local deduplication never increase result count. It does not
refill candidates or perform another search. Module 6.5 owns any later global
candidate bound.

## Ordering semantics

The promoter scans the original stream in rank order and substitutes a
qualifying family at its first represented-child position. A parent inherits
that position's unchanged score, so source-local descending order is
preserved. When the same output chunk could be emitted more than once, the
first surviving occurrence wins. Ties therefore retain upstream chunk-ID
determinism; no new score comparison is introduced.

Promotion is single-pass over the original candidate graph. The implementation
must not iterate promoted results to a fixed point.

## Duplicate handling

- Duplicate input chunk IDs are an integrity failure.
- Multiple represented children of one qualifying family emit exactly one
  parent.
- If a canonical parent is also an original candidate, output contains it once
  at the earliest surviving position among the direct occurrence and promoted
  replacement; that occurrence's score/source wins unchanged.
- Independent families remain independent even if display text or headings
  match.
- Cross-source duplicates are not visible to one call and remain Module 6.5's
  responsibility.

## Integrity and error semantics

The following raise `IntegrityError` and produce no successful partial result:

- a referenced parent or sibling is missing;
- a parent or sibling belongs to another document or version;
- sibling links are asymmetric, contain self, disagree on parent, or describe
  different family sets;
- a root advertises siblings;
- a loaded chunk ID does not equal the requested canonical ID;
- the canonical parent is one of its own children; or
- input identities, sources, ranks, or ordering violate the candidate contract.

Storage exceptions propagate according to the existing common error model.
No family is silently skipped because canonical state is corrupt.

## Version and filter semantics

Parent and every family member must share the exact `(document_id, version_id)`
of the candidate child. Cross-version or cross-document promotion is forbidden,
including between current and superseded versions of one logical document.

The promoter receives no `MetadataFilter`. ADR-0038/0039 filters are already
enforced before retrieval top-k, and every filter field is document-level or
exact-version-level. A verified same-document/same-version parent therefore
has identical eligibility. Promotion must not perform a new unfiltered search.

## Storage semantics

`StorageInterfaceV1.get_chunk()` is sufficient. The promoter gathers unique
parent and sibling IDs referenced by the bounded candidate stream and performs
deduplicated asynchronous lookups through the storage abstraction. The lookup
set is finite and explicitly named by canonical Chunk relationships; it is not
an unbounded scan or N lookups for duplicate references.

No direct Qdrant, SQLite, or SurrealDB dependency is permitted. A future batch
lookup may be proposed only with measured need; it is not required for Module
6.4 correctness and does not justify changing `StorageInterfaceV1` now.

## Registry and capability semantics

Parent promotion must not use the existing `retriever` capability family,
because it does not implement `RetrieverInterfaceV1`. Module 6.4 will add an
additive, versioned `parent_promotion` capability family to PluginRegistry with
typed registration and resolution, conceptually:

```text
register_parent_promoter("default", implementation, priority=...)
resolve_parent_promoter("default")
```

The registry retains its existing priority, conflict, freeze, plugin
compatibility, and deterministic descriptor rules. Existing retriever slots
and interface versions are unchanged. ADR-0002's table entry describing
ParentRetriever as a RetrieverInterface specialization is superseded only for
ParentRetriever by this decision.

## Module 6.4 boundary

Module 6.4 owns:

- the new candidate-promotion protocol and capability metadata;
- ParentRetriever's source-local transformation;
- canonical family validation and 50-percent calculation;
- parent/sibling lookups through StorageInterfaceV1;
- local replacement, duplicate elimination, rank recomputation, and errors;
- registry registration/resolution for the new capability; and
- unit, real-storage, performance, and golden-family acceptance.

It does not execute queries or embeddings and does not invoke another
retriever.

## Module 6.5 boundary

Module 6.5 will own:

- executing planner subqueries through query retrievers;
- invoking the configured parent promoter once per source-local result stream;
- parallel scheduling and failure policy;
- combining streams;
- cross-source chunk-ID deduplication;
- RRF or other approved fusion;
- global ordering/rank and later candidate bounds; and
- explicit rejection of a reserved planner `parent` mode subquery.

This ADR does not define RRF mathematics, weighted fusion, global ranking,
reranker fallback, or cross-source score comparison.

## Compatibility impact

All frozen contracts and existing DenseRetriever/SparseRetriever behavior stay
unchanged. The new protocol and registry family are additive Phase 6 API.
Plugins claiming the old `retriever/parent` slot do not satisfy the new
capability and are not silently adapted.

`RetrievalMode.PARENT` remains deserializable for compatibility but is not a
query-executing RetrieverInterface dispatch target. New planner output must not
contain it; later orchestration fails explicitly if legacy input does.

## Migration requirements

No data, Chunk, SQLite, Qdrant, or SurrealDB migration is required. Existing
stored parent and sibling relationships are sufficient. Plugin implementations
must register under the new capability when Module 6.4 is implemented; no
existing registration is rewritten automatically.

## Testing requirements

Implementation acceptance must cover:

- empty input, roots, sole children, and unrelated candidates;
- 1/4, 2/4, 3/4, and 4/4 thresholds;
- multiple qualifying/nonqualifying families;
- direct-parent duplicates and multi-level original candidates;
- one-pass non-recursion;
- exact document/version isolation, including current and superseded versions;
- inherited score/source, contiguous ranks, deterministic ordering, and no
  normalization;
- every integrity and storage failure above;
- registry priority/conflict/freeze semantics;
- deduplicated bounded storage lookups;
- real SQLite/CompositeStorage parent lookup; and
- real Bhagavad Gita family promotion with measured lookup/total time.

## Consequences

Positive consequences:

- ParentRetriever receives its actual typed input.
- Raw score provenance is preserved without comparing dense and sparse scales.
- Module 6.4 remains independently testable and backend-neutral.
- Module 6.5 receives already promoted source-local streams but retains all
  fusion and global-ranking responsibilities.
- No frozen domain or storage contract changes.

Costs and limitations:

- Dense and sparse evidence cannot jointly satisfy a parent threshold before
  fusion; this is intentional to preserve score domains.
- Parent promotion adds canonical relationship lookups.
- A new registry capability family is required.
- Legacy planner `parent` tokens are rejected explicitly rather than adapted.

## Acceptance criteria

This ADR resolves the architecture gate when documentation agrees that:

1. ParentRetriever implements `ParentPromotionInterfaceV1`, not
   `RetrieverInterfaceV1`;
2. promotion is source-local, pre-fusion, and single-pass;
3. the first-ranked represented child supplies unchanged score/source;
4. replacements preserve position and receive recomputed local ranks;
5. upstream top-k precedes promotion and global bounds remain Module 6.5;
6. canonical families and exact-version integrity are fully validated;
7. storage access uses only `StorageInterfaceV1.get_chunk()`;
8. a separate versioned registry capability is used; and
9. no Module 6.5 fusion behavior is implemented during Module 6.4.

Module 6.4 implementation remains not started until a later implementation
task executes these criteria.
