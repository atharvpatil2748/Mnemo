# Engineering Changelog 0001: Domain Models

- **Module:** Phase 1, Module 1.1
- **Status:** Complete and frozen
- **Released:** 2026-08-06
- **Specification:** [ADR-0001: Module 1.1 Domain Model Specification](../adr/ADR-0001-domain-model-specification.md)

## Summary

Module 1.1 establishes the immutable, strictly typed domain vocabulary shared
by Mnemo's ingestion, indexing, retrieval, graph, conversation, and notebook
subsystems. The module contains data structures and structural validation only;
it introduces no parsing, storage, retrieval, plugin, transport, or database
behavior.

## Public models introduced

- Content and parsing: `Asset`, `Block`, `TextBlock`, `HeadingBlock`,
  `TableBlock`, `ImageBlock`, `CodeBlock`, `EquationBlock`, `CaptionBlock`,
  `ParsedDocument`, and `DocumentMetadata`.
- Document registry: `Document`, `DocumentVersion`, `DocumentStatus`,
  `DocumentVersionStatus`, and `DocType`.
- Chunking and retrieval: `Chunk`, `ChunkPosition`, `ChunkType`,
  `MetadataFilter`, and `ScoredChunk`.
- Knowledge graph: `Entity` and `GraphEdge`.
- Notebook and conversation: `Notebook`, `Source`, `Note`, `NoteOrigin`,
  `Insight`, `InsightType`, `Session`, `Turn`, `TurnRole`, and `Citation`.
- Shared public value types: `FrozenMetadata`, `BoundingBox`, `JSONPrimitive`,
  and `JSONValue`.

## Architectural decisions recorded

- Domain snapshots are immutable and hashable wherever their value or stable
  identity semantics permit.
- Stable document and record identities are UUID-based; content integrity uses
  canonical lowercase SHA-256 hashes.
- Chunk identity excludes headings and text offsets. Its canonical inputs are
  the document version, source block-ordinal span, and chunk text.
- Assets are storage-independent records referenced by `asset_id`.
- Citations identify both the document and the exact document version.
- Notebook membership is represented by `Source`; `Document` does not duplicate
  notebook membership.
- Metadata is immutable and observes reserved core and plugin namespaces.
- `MetadataFilter` is the sole Pydantic model in this module; other domain
  structures are frozen dataclasses.

The complete schemas, invariants, equality rules, hashing rules, and
serialization contract are maintained in ADR-0001 rather than repeated here.

## Dependencies introduced

- Runtime: `pydantic>=2.11,<3`, required for immutable validated
  `MetadataFilter` construction.
- Internal: all Module 1.1 models depend only on Python 3.12 standard-library
  facilities and the module's shared immutable value types.
- External storage, parser, HTTP, database, plugin-loading, and model-provider
  dependencies: none.

## Downstream dependencies

These models form the public data boundary for:

- Module 1.2 interface contracts and Module 1.3 plugin registry slots;
- Module 1.4 configuration wiring and Module 1.5 `KnowledgeEngine` composition;
- Phase 2 blob, keyword, vector, graph, metadata, and composite storage;
- Phase 3 parsers and the normalized parsed-document pipeline;
- Phase 4 adaptive chunkers;
- Phase 5 embedding and embedding-cache pipelines;
- Phase 6 retrieval, reranking, context, and citation pipelines;
- later REST, MCP, notebook, conversation-memory, insight, and knowledge-graph
  features that exchange these records through core contracts.
