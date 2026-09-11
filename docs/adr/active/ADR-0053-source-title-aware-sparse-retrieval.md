# ADR-0053: Source-Title-Aware Sparse Retrieval

- **Status:** Accepted
- **Date:** 2026-08-20
- **Extends:** ADR-0039, ADR-0041, ADR-0042

## Context

The canonical exact-version title is stored in `DocumentVersion.metadata.title`
and reaches context labels/citations, but SQLite `fts_chunks` indexes only
chunk text and heading path.  `Source` stores association identities, not a
title.  Thus a sparse query such as “skills in the resume” cannot discover the
canonical resume title unless its body happens to contain those words; dense
retrieval is explicitly disabled in the local configuration.

## Decision

Add a non-authoritative, exact-version source-title retrieval projection to the
SQLite sparse index.  It is derived only from
`DocumentVersion.metadata.title`, keyed by `(document_id, version_id)`, and is
updated/rebuilt transactionally with the existing version-aware sparse
projection.  It is searchable alongside chunk text and heading path.  It does
not change `Chunk`, `StorageInterfaceV1`, `MetadataFilter`, `ScoredChunk`, or
the canonical source/document models.

The sparse query continues to use escaped term matching, SQL-side filters,
raw FTS BM25 provenance, bounded top-k, and chunk-ID tie-breaking.  A matching
title contributes generic candidate recall and ranking weight; it never
creates a filename rule, a personal-data rule, or an unconditional source
prior.  A title-only hit returns canonical chunks from that exact version using
the same deterministic bounded selection policy.  Reranking receives the
existing canonical chunks; it remains generic and does not receive hard-coded
document signatures.

## Migration and lifecycle

The SQLite adapter owns an additive schema migration that backfills the
projection from canonical `document_versions` and rebuilds only derived FTS
content.  It is executed by normal storage open/migration, not by manual SQL
repair or corpus re-ingestion.  A failed migration leaves the schema
transactionally unchanged.  Composite storage projects the same title into its
derived vector metadata for consistency, although title search does not make a
disabled vector backend active.

An absent title is indexed as no title signal and body/heading retrieval keeps
its existing behavior.  Source membership and notebook filters remain live
relational constraints as ADR-0039 requires.

## Dense deployment semantics

Qdrant remains an optional deployment capability.  When disabled, health must
report vector search unavailable while SQLite/FTS health can remain healthy;
the application must not describe that configuration as vector-backed hybrid
retrieval.  Enabling Qdrant is a deployment choice, not a test workaround.

## Consequences

This fixes a generic recall gap for titles such as document names, reports,
slides, code files, and resumes without changing corpus content or injecting
metadata into canonical chunk text.  Acceptance requires migration/backfill,
title/body ranking, filters, deterministic ordering, no stale projections, and
cross-document retrieval tests across heterogeneous documents.
