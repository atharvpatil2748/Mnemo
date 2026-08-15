# ADR-0039: Version-Aware Sparse Retrieval

- Status: Accepted
- Date: 2026-08-13
- Decision owners: Mnemo maintainers
- Supersedes: the stale `documents.type` sparse-filter implementation
- Extends: ADR-0001, ADR-0002, ADR-0038

## Context

`StorageInterfaceV1.search_sparse()` promises bounded, filtered results, but the
SQLite adapter queried a nonexistent `documents.type` column, did not enforce
publication dates, and converted FTS5 scores with `abs()`. ADR-0038 established
that type and date belong to the exact `(document_id, version_id)` represented
by a chunk and that search metadata is rebuildable derived state.

## Frozen contracts and canonical sources

`RetrieverInterfaceV1`, `StorageInterfaceV1`, `MetadataFilter`, `ScoredChunk`,
and `Chunk` remain unchanged. `ParsedDocument.doc_type` is canonical for an
exact version, `DocumentVersion.metadata.publication_date` is the canonical
publication date, and `Source` remains the canonical notebook/document
association.

## Decision

SQLite owns a derived `retrieval_version_metadata` table keyed by
`(document_id, version_id)`. `CompositeStorage` derives the same
`RetrievalMetadataProjection` used by Qdrant and atomically writes it with the
chunk rows. Sparse queries join this exact-version projection before ranking.
Notebook and source filters use live relational `EXISTS` predicates over
canonical `Source` rows; source IDs are ORed within the field, and distinct
filter fields intersect. This avoids duplicated results when relational rows
overlap and makes source/notebook mutation immediately visible without a
second sparse membership projection.

Date bounds are inclusive. A null publication date fails any date-bounded
query and remains eligible when no date filter exists. A missing derived row
fails closed for version fields rather than broadening the query. Empty
`MetadataFilter()` keeps the direct FTS path.

SQLite FTS5's `bm25()` returns a negative cost where smaller values rank
better. The adapter maps it once as `-bm25(fts_chunks)`, without calibration or
normalization, so ADR-0002's descending-score contract is preserved. Chunk ID
ascending is the deterministic tie-break. Sparse and dense scores remain
incomparable until the later fusion stage.

Filtering is part of SQL before `ORDER BY ... LIMIT`, preserving true top-k.
`SparseRetriever` only validates the frozen interface boundary, delegates to
storage, preserves scores/order/identity, and labels source/rank. It imports no
SQLite implementation.

## Synchronization and failure semantics

FTS content remains synchronized transactionally by the existing chunk
insert/update/delete triggers. Version projection and chunk upsert share one
SQLite transaction. If a later Qdrant write fails, `CompositeStorage` restores
both the affected chunk snapshot and the prior sparse projection. SQLite or
canonical-store failures propagate; no unfiltered fallback exists.

Document/version cascade deletion removes chunks, FTS rows through triggers,
and projection rows through foreign keys. Source and notebook changes are read
from canonical relational rows at query time. Rebuild consists of replaying
canonical parsed documents, document versions, and chunks through
`CompositeStorage.upsert_chunks()`.

## Migration and compatibility

Schema migration 4 adds only the derived table and indexes. Existing databases
are preserved, but historical chunks have no version projection until rebuilt;
type/date filters therefore fail closed for those rows. Empty, notebook, and
source filters remain usable. No historical M5 database or evidence is mutated
by acceptance; validation uses a new temporary SQLite database.

## Alternatives rejected

- `documents.type`: the column does not exist and logical-document type would
  violate exact-version semantics.
- Python post-filtering or overfetching: breaks top-k correctness.
- Adding fields to `Chunk` or changing a public interface: violates frozen
  contracts.
- Duplicating notebook/source arrays in the sparse projection: creates avoidable
  mutable derived state when bounded relational `EXISTS` predicates already run
  before ranking.
- Normalizing BM25 to 0–1: contradicts ADR-0002 and destroys raw provenance.

## Consequences

Sparse search gains one indexed exact-version join and bounded relational
existence checks. The projection is non-authoritative and requires replay for
pre-migration type/date filtering. Module 6.3 does not implement fusion,
parents, reranking, or Module 6.4/6.5 behavior.
