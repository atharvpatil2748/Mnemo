# ADR-0001: Module 1.1 Domain Model Specification

- **Status:** Accepted
- **Date:** 2026-08-06
- **Decision owners:** Mnemo maintainers
- **Scope:** Phase 1, Module 1.1 only
- **Supersedes:** Nothing
- **Related documents:** `mnemo_architecture_v2.md`, `mnemo_engineering_roadmap.md`

## 1. Context

The architecture and engineering roadmap identify the domain models required by
Module 1.1, but intentionally leave several public schemas incomplete. In
particular, they do not fully specify block fields, notebook records,
conversation records, document versions, serialization, equality, or hashing.

This ADR defines the complete public contract for those models before any
Python implementation is written. It does not modify the source-of-truth
architecture or roadmap. It was approved with the revisions recorded in section
16 and is the implementation specification for Module 1.1.

The frozen Phase 1 decisions supplied after the architecture take precedence
where they resolve older shorthand in the documents.

## 2. Non-goals

This ADR does not define:

- parsing, cleaning, chunking, retrieval, or indexing behavior;
- persistence schemas or database-specific identifiers;
- API request or response models;
- plugin interfaces or discovery;
- object factories, validation functions, or serialization code;
- business operations on notebooks, documents, sessions, or notes;
- models assigned to later modules, including `RetrievalPlan` and `SubQuery`.

## 3. Proposed compatibility resolutions

The following names resolve conflicts between older roadmap shorthand and the
frozen Phase 1 decisions:

1. `document_id` is the canonical field name. Legacy `doc_id` wording is not a
   second field or serialization alias.
2. `version_id` identifies one immutable document version and is present on
   every `Chunk`.
3. `content_hash` is the canonical SHA-256 field name. The roadmap's
   `source_file_hash` and architecture's `current_hash` remain only where noted
   as compatibility descriptions; duplicate hash fields are avoided except for
   the explicitly denormalized `Document.current_hash` registry value.
4. `Chunk.id` is based on `version_id`, the canonical source block-ordinal span,
   and `text`. Heading paths and navigational offsets are excluded.
5. `Document` does not contain `notebook_ids`. Notebook membership is owned
   exclusively by `Source` association records.
6. `ScoredChunk` exposes raw `score`, `source`, and `rank`. The roadmap's
   `retrieval_mode` field is represented by `source`; no calibrated confidence
   field is added.
7. Collection-valued fields use immutable sequences in the domain model and
   JSON arrays on the wire. This preserves architecture-level cardinality while
   making immutable value objects possible.

## 4. Shared schema conventions

### 4.1 Type vocabulary

| Type | Meaning |
|---|---|
| `UUID` | RFC 4122 UUID value; serialized as a lowercase canonical hyphenated string. |
| `SHA256` | Exactly 64 lowercase hexadecimal characters representing a SHA-256 digest. |
| `Date` | Calendar date without a timezone; serialized as ISO 8601 `YYYY-MM-DD`. |
| `Timestamp` | Timezone-aware UTC instant; serialized as RFC 3339 with a trailing `Z`. |
| `JSONScalar` | String, finite number, boolean, or null. |
| `JSONValue` | A JSON scalar, immutable sequence of JSON values, or immutable string-keyed mapping of JSON values. |
| `Metadata` | Immutable string-keyed mapping of `JSONValue`; defaults to empty. |
| `BoundingBox` | Four finite numbers `(x0, y0, x1, y1)` in source-page coordinates. |

NaN and positive or negative infinity are not valid numbers in any model.
Booleans are not accepted where an integer or number is required.

### 4.2 Required and optional fields

`Required` means the caller must supply a value. `Optional` means the value may
be null. A field with a default may be omitted during construction or
deserialization. Optionality and omission are independent: an optional field
without a default is still required to be present.

### 4.3 Immutability

All Module 1.1 domain models are immutable snapshots. Changes are represented by
constructing a new snapshot. Collections are immutable sequences or immutable
mappings; callers cannot mutate a model through a referenced collection.

`MetadataFilter` is also immutable even though it is the one Module 1.1 model
explicitly required to use Pydantic validation.

### 4.4 Equality and hashing categories

Models use one of two semantics:

- **Value semantics:** Equality compares every public field recursively. The
  hash is derived from the same complete immutable field set.
- **Identity semantics:** Equality and hashing use only the model's declared
  UUID or stable content identifier. Two snapshots carrying the same identity
  represent the same logical record. A repository must reject conflicting
  records that reuse an identity for a different logical record.

No model uses object identity for equality. Models whose identifiers are UUIDs
remain hashable even when their snapshots contain metadata.

### 4.5 Serialization

All models have a lossless JSON representation governed by these rules:

These are persistence and transport serialization rules for later serializer
and storage modules. Module 1.1 implements the immutable in-memory schemas and
Pydantic serialization for `MetadataFilter`; it does not expose a generic
dataclass serialization service or per-model serialization methods.

- Field names in this ADR are the canonical serialized keys.
- UUIDs, hashes, dates, timestamps, enums, tuples, and mappings serialize using
  the representations in this section.
- Enum values serialize as the lowercase values defined in their enum tables.
- Immutable sequences serialize as JSON arrays.
- Metadata serializes as a JSON object with string keys.
- Null is emitted for an optional field whose value is null. Fields with
  defaults are not implicitly omitted; complete persisted records remain
  self-describing.
- Unknown fields are rejected when reading schema version 1. Forward-compatible
  data belongs in a model's `metadata` field, where one is defined.
- Block objects include a `type` discriminator. The discriminator is
  serialization metadata, not an additional runtime field.
- A persisted top-level object includes serialization envelope values
  `model` and `schema_version`, with schema version `1`. These envelope values
  are not domain fields and do not participate in equality or hashing.
- Serialization preserves field values; it never computes IDs, timestamps, or
  defaults on read.

The canonical JSON used for deterministic hashing sorts mapping keys, uses UTF-8,
and emits no insignificant whitespace.

### 4.6 Metadata namespaces

Metadata keys are non-empty strings. The following dotted prefixes are reserved
to prevent collisions between subsystems and plugins:

| Namespace | Owner |
|---|---|
| `parser.*` | Parser-produced metadata. |
| `layout.*` | Page-layout and geometry metadata. |
| `ocr.*` | OCR-produced metadata. |
| `vision.*` | Vision-model-produced metadata. |
| `chunker.*` | Chunker-produced metadata. |
| `plugin.<plugin_name>.*` | Metadata private to the named plugin. |

Plugin names in metadata are lowercase and use ASCII letters, digits,
underscores, and hyphens. Plugins must not write keys in another plugin's
namespace. Unnamespaced keys are reserved for fields produced by Mnemo core and
must not duplicate or override a model's public fields. Namespace ownership is a
schema convention; enforcement at plugin registration belongs to Module 1.3.

### 4.7 Validation boundary

These schemas define invariants, but no validation behavior or exception type is
selected here. Module 1.1 may enforce structural invariants during construction.
Cross-record invariants requiring storage access belong to later modules.

## 5. Enumerations

### 5.1 `DocType`

Purpose: classify a parsed document for chunker selection.

| Member | Serialized value |
|---|---|
| `BOOK` | `book` |
| `PAPER` | `paper` |
| `CODE` | `code` |
| `EMAIL` | `email` |
| `RESUME` | `resume` |
| `SLIDES` | `slides` |
| `MARKDOWN` | `markdown` |
| `DOCUMENTATION` | `documentation` |
| `GENERIC` | `generic` |

It is immutable, uses enum-member equality and hashing, and rejects unknown
values. Adding a document type requires review because it affects chunker
selection; `GENERIC` is the fallback rather than an open-ended string.

### 5.2 `ChunkType`

Purpose: identify the semantic role of a chunk.

| Member | Serialized value |
|---|---|
| `PASSAGE` | `passage` |
| `SUMMARY` | `summary` |
| `VERBATIM` | `verbatim` |
| `QUESTION` | `question` |
| `CODE` | `code` |
| `CAPTION` | `caption` |
| `EQUATION` | `equation` |

It is immutable, uses enum-member equality and hashing, and rejects unknown
values. New semantic chunk roles require review; subtype details belong in
`Chunk.metadata` rather than ad hoc enum values.

### 5.3 `DocumentStatus`

Purpose: expose the ingestion state of the document's current version.

| Member | Serialized value | Meaning |
|---|---|---|
| `PENDING` | `pending` | Registered but indexing has not started. |
| `INDEXING` | `indexing` | Fast-path processing is in progress. |
| `INDEXED` | `indexed` | Fast path is complete and the document is searchable. |
| `ENRICHED` | `enriched` | Slow-path enrichment is complete. |
| `FAILED` | `failed` | Processing of the current version failed. |

Deletion is represented by record removal, not a status. Status-transition
rules are business logic and are intentionally outside Module 1.1.

### 5.4 `DocumentVersionStatus`

Purpose: distinguish the version selected by a `Document` from retained older
versions.

| Member | Serialized value |
|---|---|
| `CURRENT` | `current` |
| `SUPERSEDED` | `superseded` |

Exactly one version in a non-empty `Document.versions` collection is current.

### 5.5 `TurnRole`

Purpose: identify who produced a persisted conversational turn.

| Member | Serialized value |
|---|---|
| `USER` | `user` |
| `ASSISTANT` | `assistant` |

System instructions are runtime orchestration inputs, not persisted user
conversation turns.

### 5.6 `NoteOrigin`

Purpose: distinguish user-created notes from generated session or notebook
notes without implying a user identity system in core.

| Member | Serialized value |
|---|---|
| `USER` | `user` |
| `GENERATED` | `generated` |

### 5.7 `InsightType`

Purpose: classify the insight categories explicitly named by the architecture.

| Member | Serialized value |
|---|---|
| `KEY_FACT` | `key_fact` |
| `CLAIM` | `claim` |
| `ENTITY` | `entity` |
| `SUMMARY` | `summary` |

New insight categories require review. Provider-specific details belong in
`Insight.metadata`.

## 6. Document and parsing models

### 6.1 `DocumentMetadata`

**Purpose and responsibility:** Store descriptive and provenance metadata
extracted from a document. It does not own document identity or notebook
membership.

**Semantics:** Immutable value object; structural equality and hashing.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `content_hash` | `SHA256` | Required | None | SHA-256 of the original raw bytes; used only for deduplication. |
| `title` | string or null | Optional | null | Non-empty after trimming when present. |
| `authors` | immutable sequence of strings | Required | empty | Author order is preserved; entries are non-empty. |
| `publication_date` | `Date` or null | Optional | null | The document's publication date, not ingestion time. |
| `url` | string or null | Optional | null | Absolute source URL when known. No network access is implied. |
| `doi` | string or null | Optional | null | DOI text in normalized identifier form when known. |
| `isbn` | string or null | Optional | null | ISBN text when known; checksum validation is outside this model. |
| `page_count` | integer or null | Optional | null | Must be at least 1 when present. |
| `metadata` | `Metadata` | Required | empty | Format-specific descriptive values not promoted to public fields. |

**Serialization:** Uses the shared rules. `source_file_hash` is not emitted or
accepted; `content_hash` is canonical.

**Relationships:** Embedded by `ParsedDocument` and `DocumentVersion`.

**Invariants:** The content hash never serves as `document_id` or `version_id`.
Metadata must not contain a second authoritative value for a named public field.

**Future extension points:** New universally applicable bibliographic fields may
be proposed as explicit fields. Parser-specific fields remain in `metadata`.

### 6.2 `ParsedDocument`

**Purpose and responsibility:** Represent the canonical, storage-independent
intermediate representation of a document. Produced by the Module 3.9
`IngestionPipeline` through its pure `DocumentCanonicalizer`, NOT directly by
parsers.

**Semantics:** Immutable value object; structural equality and hashing.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `blocks` | immutable sequence of `Block` | Required | None | Ordered by each block's `ordinal`; may be empty for a structurally empty source. |
| `metadata` | `DocumentMetadata` | Required | None | Describes the same raw document parsed into `blocks`. |
| `language` | string | Required | None | BCP 47 language tag or `und` when undetermined. |
| `doc_type` | `DocType` | Required | None | Classification used by later chunker selection. |

**Relationships:** Owns block snapshots and document metadata by value. It does
not own `Document`, `DocumentVersion`, or `Source` records.

**Invariants:** Block ordinals are unique, contiguous, begin at zero, and match
sequence order. Block page numbers cannot exceed `metadata.page_count` when the
page count is known.

**Future extension points:** Parsed-format details belong in block or document
metadata. New processing state does not belong in this immutable IR.

### 6.3 `DocumentVersion`

**Purpose and responsibility:** Identify one immutable version of a logical
document and bind that version to its raw-byte hash and metadata.

**Semantics:** Immutable identity record; equality and hashing use `version_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `version_id` | `UUID` | Required | None | Unique identity for this version. |
| `document_id` | `UUID` | Required | None | Stable logical document identity. |
| `content_hash` | `SHA256` | Required | None | SHA-256 of this version's raw bytes. |
| `metadata` | `DocumentMetadata` | Required | None | Metadata extracted for this exact version. |
| `status` | `DocumentVersionStatus` | Required | None | Current or superseded within its owning document. |
| `created_at` | `Timestamp` | Required | None | When this version record was created. |

**Relationships:** Belongs to exactly one `Document`. Chunks reference its
`version_id` and `document_id`.

**Invariants:** `content_hash` equals `metadata.content_hash`. A `version_id`
cannot be reused for different bytes or a different document.

**Future extension points:** Storage locations and processing diagnostics belong
in storage-layer records, not this public identity model.

### 6.4 `Document`

**Purpose and responsibility:** Represent the stable registry entry for a
logical document across versions.

**Semantics:** Immutable identity record; equality and hashing use
`document_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `document_id` | `UUID` | Required | None | Stable identity that never changes across versions. |
| `versions` | immutable sequence of `DocumentVersion` | Required | None | Non-empty, ordered oldest to newest. |
| `current_version_id` | `UUID` | Required | None | Identifies exactly one member of `versions`. |
| `current_hash` | `SHA256` | Required | None | Registry lookup value matching the current version's `content_hash`. |
| `status` | `DocumentStatus` | Required | None | Ingestion status of the current version. |
| `created_at` | `Timestamp` | Required | None | Creation time of the logical document. |
| `updated_at` | `Timestamp` | Required | None | Time the registry snapshot last changed. |

**Relationships:** Owns versions by value. It is associated with notebooks only
through `Source`; it never stores notebook IDs.

**Invariants:** Every version has the same `document_id`; version IDs and content
hashes are unique within the document; exactly one version has status `CURRENT`;
that version matches `current_version_id` and `current_hash`; `created_at` is not
later than `updated_at`.

**Serialization:** Versions are emitted in their defined order. `current_hash`
is intentionally serialized even though it is derivable, because the
architecture names it as a registry lookup field; its consistency is validated.

**Future extension points:** Version-retention policy and archival behavior are
later business logic. Notebook relationships remain external through `Source`.

## 7. Block hierarchy

### 7.1 `Asset`

**Purpose and responsibility:** Represent immutable metadata for a locally
stored binary asset independently of any storage backend or block subtype.

**Semantics:** Immutable identity record; equality and hashing use `asset_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `asset_id` | `UUID` | Required | None | Stable asset identity; never derived from a storage path. |
| `mime_type` | string | Required | None | Non-empty media type. |
| `content_hash` | `SHA256` | Required | None | SHA-256 of the asset's raw bytes. |
| `storage_uri` | string | Required | None | Non-empty opaque local URI interpreted only by the storage layer. |
| `width` | integer or null | Optional | null | Positive pixels when applicable. |
| `height` | integer or null | Optional | null | Positive pixels when applicable. |
| `metadata` | `Metadata` | Required | empty | Namespaced asset metadata. |

**Relationships:** `ImageBlock` references an asset by `asset_id`. Other future
asset consumers may reference the same asset without changing this model.

**Invariants:** Width and height are independently optional and positive when
present. `storage_uri` is not a remote-fetch instruction and does not expose a
filesystem-path contract to core models. An asset ID cannot be reused for
different bytes.

**Future extension points:** The generic model can represent images, figures,
audio, video, extracted diagrams, and thumbnails. Media-specific dimensions or
duration values belong in namespaced metadata until separately standardized.

### 7.2 `Block`

**Purpose and responsibility:** Define the common spatial, ordering, language,
and extension fields shared by every parsed block. `Block` is an abstract schema
and cannot be instantiated directly.

**Semantics:** Immutable value object; concrete blocks use structural equality
and hashing including all common and subtype fields.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `ordinal` | integer | Required | None | Zero-based global order within `ParsedDocument`; non-negative. |
| `page_number` | integer or null | Optional | null | One-based source page when applicable; at least 1 when present. |
| `bounding_box` | `BoundingBox` or null | Optional | null | `x0 <= x1` and `y0 <= y1`; null for non-layout formats. |
| `language` | string or null | Optional | null | BCP 47 natural-language tag or `und`; null means not evaluated at block level. |
| `metadata` | `Metadata` | Required | empty | Parser-specific values that do not change the block's semantic subtype. |

**Serialization:** Every concrete block emits a lowercase `type` discriminator:
`text`, `heading`, `table`, `image`, `code`, `equation`, or `caption`.

**Relationships:** Belongs by value to one `ParsedDocument`. Cross-block
references use ordinals only where explicitly defined.

**Invariants:** Metadata cannot override `type` or any public field. A bounding
box is meaningful only when `page_number` is present.

**Future extension points:** New block subtypes require review. Parser-specific
layout data belongs in `metadata` until it is universal enough for a public
field.

Every concrete block below inherits `Block`'s responsibility, common fields,
immutability, structural equality and hashing, serialization rules,
`ParsedDocument` relationship, invariants, and extension policy. Each subtype
section specifies only its additional public fields and subtype-specific rules.

### 7.3 `TextBlock`

**Purpose:** Represent prose or other plain textual content.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| All `Block` fields | As above | As above | As above | Common block contract. |
| `text` | string | Required | None | Must not be empty. Whitespace normalization belongs to the cleaner. |

It has immutable value semantics. Future text classifications belong in
`metadata`, not new subclasses without review.

### 7.4 `HeadingBlock`

**Purpose:** Represent a hierarchy-bearing document heading.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| All `Block` fields | As above | As above | As above | Common block contract. |
| `text` | string | Required | None | Must not be empty. |
| `level` | integer | Required | None | Inclusive range 1 through 6. |

It has immutable value semantics. Format-specific heading styles belong in
`metadata`.

### 7.5 `TableBlock`

**Purpose:** Preserve a table's rectangular cell structure without committing
to a rendering format.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| All `Block` fields | As above | As above | As above | Common block contract. |
| `rows` | immutable sequence of immutable sequences of strings | Required | None | At least one row and one column; every row has equal width. |
| `header_row_count` | integer | Required | `0` | Between zero and the number of rows, inclusive. |

It has immutable value semantics. Captions are separate `CaptionBlock` records;
rendered Markdown or natural-language descriptions are later derived artifacts,
not fields on the parsed table.

### 7.6 `ImageBlock`

**Purpose:** Associate an extracted or source image occurrence with a
storage-independent asset identity without embedding binary data inside parsed
IR.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| All `Block` fields | As above | As above | As above | Common block contract. |
| `asset_id` | `UUID` | Required | None | References exactly one `Asset`. |
| `alt_text` | string or null | Optional | null | Source-provided alternative text; non-empty when present. |

It has immutable value semantics. Asset media type, dimensions, content hash,
and storage URI remain authoritative on `Asset`. Generated vision descriptions
are later derived content and do not mutate this block.

### 7.7 `CodeBlock`

**Purpose:** Preserve a source code fragment as an atomic parsed block.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| All `Block` fields | As above | As above | As above | Common block contract. |
| `code` | string | Required | None | Must not be empty; preserved verbatim. |
| `code_language` | string or null | Optional | null | Programming-language identifier when known. |

The inherited `language` field continues to mean natural language, while
`code_language` identifies the programming language. The model has immutable
value semantics. AST and call-graph data belong to later chunking metadata.

### 7.8 `EquationBlock`

**Purpose:** Preserve a mathematical expression without generating an
interpretation.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| All `Block` fields | As above | As above | As above | Common block contract. |
| `latex` | string | Required | None | Non-empty LaTeX preserved verbatim. |
| `display` | boolean | Required | `true` | Whether the source treats the equation as display rather than inline math. |

It has immutable value semantics. Plain-language descriptions are later sibling
chunks, not fields on this block.

### 7.9 `CaptionBlock`

**Purpose:** Preserve a caption and, when known, its relationship to an image,
table, or equation block.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| All `Block` fields | As above | As above | As above | Common block contract. |
| `text` | string | Required | None | Must not be empty. |
| `target_ordinal` | integer or null | Optional | null | Non-negative ordinal of another block in the same `ParsedDocument`. |

It has immutable value semantics. If present, `target_ordinal` cannot equal the
caption's own ordinal and must resolve within the owning parsed document.

## 8. Chunk and retrieval models

### 8.1 `ChunkPosition`

**Purpose and responsibility:** Locate a chunk within its source version without
participating in chunk identity.

**Semantics:** Immutable value object; structural equality and hashing.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `page_number` | integer or null | Optional | null | One-based page where the chunk begins; at least 1 when present. |
| `section_index` | integer | Required | None | Zero-based section order; non-negative. |
| `chunk_index_in_section` | integer | Required | None | Zero-based order within the section; non-negative. |
| `start_offset` | integer or null | Optional | null | Zero-based inclusive offset into canonical extracted text; non-negative when present. |
| `end_offset` | integer or null | Optional | null | Zero-based exclusive offset into canonical extracted text; non-negative when present. |

Additional page-range and geometry anchors may be proposed later if parsers can
provide them consistently. Start and end offsets are either both null or both
present; when present, `start_offset < end_offset`. Position fields are
navigation and display metadata and do not participate in chunk identity.

### 8.2 `Chunk`

**Purpose and responsibility:** Represent a self-contained semantic retrieval
unit tied to one exact document version.

**Semantics:** Immutable identity record; equality and hashing use `id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `id` | `SHA256` | Required | None | Stable content-derived chunk identity. |
| `text` | string | Required | None | Must not be empty. |
| `document_id` | `UUID` | Required | None | Stable logical document identity. |
| `version_id` | `UUID` | Required | None | Exact document version from which the chunk was produced. |
| `chunk_type` | `ChunkType` | Required | None | Semantic role of the chunk. |
| `position` | `ChunkPosition` | Required | None | Navigational position only. |
| `heading_path` | immutable sequence of strings | Required | None | May be empty only when the source has no hierarchy; entries are non-empty. |
| `parent_chunk_id` | `SHA256` or null | Optional | null | Parent chunk; null only for a root parent chunk. |
| `sibling_ids` | immutable sequence of `SHA256` | Required | empty | Other chunks sharing the same parent; excludes `id`. |
| `metadata` | `Metadata` | Required | empty | Chunker-specific structured values. |
| `embedding` | immutable sequence of finite numbers or null | Optional | null | Populated by the embedder; non-empty when present. |

**Chunk ID canonicalization:** During chunk creation, the chunker supplies the
inclusive ordinal of the first source block and the inclusive ordinal of the
last source block contributing content. The ID is the SHA-256 digest of the
UTF-8 bytes of a canonical JSON array containing, in order, the lowercase
canonical `version_id` string, a two-integer array containing those block
ordinals, and `text`. JSON uses the shared canonical form. The block-ordinal span
is generation provenance rather than a public `Chunk` field in the released V1
schema. `heading_path`, all
`ChunkPosition` fields (including text offsets), `document_id`, chunk type,
metadata, relationships, and embedding do not participate.

**Relationships:** Belongs to one `DocumentVersion`; parent and sibling IDs
refer to chunks from the same version. A real parent is created on the fast path.
A root parent may have no parent; every non-root chunk has a parent.

**Invariants:** The chunker must generate `id` from a valid non-negative block
span whose start is not greater than its end. Parent ID differs from `id`;
sibling IDs are unique and exclude `id`; all vectors contain only finite
numbers. Parent and reciprocal sibling existence and chunk-ID provenance are
cross-record invariants for the chunking/storage modules.

**Future extension points:** Named embeddings belong in storage payloads until a
later ADR changes the public model. Chunker-specific fields belong in metadata.

**Phase 4 evolution:** ADR-0015 makes the already-required
inclusive block-ordinal provenance a first-class immutable `BlockSpan` and a
required persisted `Chunk.source_span`. It does not change the identity formula
above. V1 remains available during its compatibility window, while Phase 4
uses the evolved persisted schema.

### 8.3 `ScoredChunk`

**Purpose and responsibility:** Attach one retriever's raw result information to
a chunk without changing the chunk.

**Semantics:** Immutable value object; structural equality and hashing.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `chunk` | `Chunk` | Required | None | Retrieved chunk snapshot. |
| `score` | finite number | Required | None | Raw provider score; no normalization or probability interpretation. |
| `source` | string | Required | None | Non-empty retriever or ranking-source identifier such as `dense`, `sparse`, or `reranker`. |
| `rank` | integer | Required | None | One-based rank assigned by `source`; at least 1. |

Different sources may produce different score scales. Consumers must use
`source` and `rank` rather than compare unrelated raw scales. Additional
fusion provenance would require a later schema proposal.

### 8.4 `MetadataFilter`

**Purpose and responsibility:** Carry validated hard constraints for retrieval.
It does not execute filtering.

**Representation:** Immutable Pydantic model, as explicitly required by the
roadmap. It has structural equality and hashing.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `notebook_id` | `UUID` or null | Optional | null | Restricts results through `Source` associations. |
| `doc_types` | immutable sequence of `DocType` | Required | empty | Empty means no document-type restriction; values are unique. |
| `date_after` | `Date` or null | Optional | null | Inclusive lower publication-date bound. |
| `date_before` | `Date` or null | Optional | null | Inclusive upper publication-date bound. |
| `source_ids` | immutable sequence of `UUID` | Required | empty | Empty means no source restriction; values are unique. |

**Invariants:** `date_after` is not later than `date_before` when both are
present. Repeated enum values or source IDs are invalid rather than silently
deduplicated.

**Serialization:** Canonical keys are plural: `doc_types` and `source_ids`.
Legacy singular roadmap notation is not a serialization alias.

**Relationships:** Source filtering resolves through `Source`, not directly
through a notebook-ID field on `Document`.

**Future extension points:** New universal hard filters require review. Backend-
specific query syntax is forbidden from this model.

## 9. Graph models

### 9.1 `Entity`

**Purpose and responsibility:** Represent one normalized entity occurrence
derived from a document.

**Semantics:** Immutable value object; structural equality and hashing.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `entity_id` | `UUID` | Required | None | Stable identity for this entity. |
| `canonical_name` | string | Required | None | Non-empty normalized display name. |
| `type` | string | Required | None | Non-empty provider-independent entity category. |
| `confidence` | finite number | Required | None | Raw extractor confidence in the inclusive range 0 through 1. |
| `document_id` | `UUID` | Required | None | Document from which this occurrence was derived. |
| `aliases` | immutable sequence of strings | Required | empty | Deterministic alternate names for this entity. |

**Relationships:** `GraphEdge.source` and `GraphEdge.target` refer to normalized
entity names. Entity normalization and cross-document merging are later logic.

**Invariants:** `canonical_name`, `type`, and alias entries are non-empty after trimming.
Aliases are unique, preserve deterministic input order, and cannot equal `canonical_name`.
Confidence is extractor provenance, not retrieval confidence or a calibrated
user-facing probability.

**Future extension points:** Provider-specific labels and mention offsets belong
in later enrichment records; adding them here requires evidence that they are
universal.

### 9.2 `GraphEdge`

**Purpose and responsibility:** Represent a weighted directed relationship
between two normalized entities.

**Semantics:** Immutable value object; structural equality and hashing.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `source_id` | `UUID` | Required | None | UUID of the source entity. |
| `target_id` | `UUID` | Required | None | UUID of the target entity. |
| `relation` | string | Required | None | Non-empty normalized relationship label. |
| `weight` | finite number | Required | None | Raw relationship strength in the inclusive range 0 through 1. |

**Relationships:** Source and target resolve to graph entities through the graph
store's normalization policy. This minimal model follows the architecture's
four-field contract; evidence provenance remains in the enrichment/storage
layer until separately specified.

**Invariants:** Self-edges are permitted because reflexive relationships can be
meaningful. Direction is significant; reversing source and target produces a
different edge.

**Future extension points:** Evidence chunk IDs, extraction provenance, and
temporal validity require a later ADR because they change graph persistence.

## 10. Conversation and citation models

### 10.1 `Session`

**Purpose and responsibility:** Represent a conversation thread attached to one
notebook.

**Semantics:** Immutable identity record; equality and hashing use `session_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `session_id` | `UUID` | Required | None | Stable session identity. |
| `notebook_id` | `UUID` | Required | None | Notebook whose knowledge scope owns the session. |
| `title` | string or null | Optional | null | Non-empty when present. |
| `turns` | immutable sequence of `Turn` | Required | empty | Ordered chronologically, then by sequence number. |
| `created_at` | `Timestamp` | Required | None | Session creation time. |
| `updated_at` | `Timestamp` | Required | None | Time the session snapshot last changed. |
| `metadata` | `Metadata` | Required | empty | Session presentation or extension values. |

**Relationships:** Belongs to one `Notebook`; owns ordered turn snapshots by
value. Citations reference individual assistant turns separately.

**Invariants:** Every turn has the same `session_id`; turn sequence numbers are
unique and contiguous from zero; timestamps are non-decreasing by sequence;
`created_at` is not later than `updated_at`.

**Future extension points:** Session summaries are represented as generated
`Note` or later indexed documents, not mutable fields on a session.

### 10.2 `Turn`

**Purpose and responsibility:** Represent one persisted user or assistant
message in a session.

**Semantics:** Immutable identity record; equality and hashing use `turn_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `turn_id` | `UUID` | Required | None | Stable turn identity. |
| `session_id` | `UUID` | Required | None | Owning session identity. |
| `sequence` | integer | Required | None | Zero-based order within the session; non-negative. |
| `role` | `TurnRole` | Required | None | User or assistant. |
| `content` | string | Required | None | Must not be empty. |
| `created_at` | `Timestamp` | Required | None | Persisted creation time. |
| `metadata` | `Metadata` | Required | empty | Non-authoritative presentation or model provenance. |

**Relationships:** Belongs to one `Session`. `Citation.turn_id` may reference an
assistant turn. Citation records are not duplicated inside `Turn`.

**Invariants:** Only assistant turns may be citation targets. Enforcing that
cross-record invariant belongs to session/citation persistence.

**Future extension points:** Token counts and model identifiers may use metadata
until they become stable cross-provider concepts.

### 10.3 `Citation`

**Purpose and responsibility:** Persist the provenance resolution of one
canonical `[source:N]` marker in an assistant turn.

**Semantics:** Immutable identity record; equality and hashing use
`citation_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `citation_id` | `UUID` | Required | None | Stable citation-record identity. |
| `turn_id` | `UUID` | Required | None | Assistant turn containing the marker. |
| `source_number` | integer | Required | None | Positive `N` from `[source:N]`. |
| `chunk_id` | `SHA256` | Required | None | Exact evidence chunk. |
| `document_id` | `UUID` | Required | None | Stable logical source document. |
| `version_id` | `UUID` | Required | None | Exact document version containing the evidence chunk. |
| `document_title` | string | Required | None | Non-empty title snapshot used for display. |
| `page_number` | integer or null | Optional | null | One-based source page when known. |
| `heading_path` | immutable sequence of strings | Required | empty | Heading snapshot used for navigation. |
| `verbatim_quote` | string | Required | None | Non-empty evidence excerpt copied from the chunk. |
| `created_at` | `Timestamp` | Required | None | Citation resolution time. |

**Serialization:** The canonical marker is derivable as `[source:N]` from
`source_number` and is not stored as a second field. No confidence probability
is serialized.

**Relationships:** Belongs to one assistant `Turn` and refers to one `Chunk`, its
exact `DocumentVersion`, and its logical `Document`. The title, page, path, and
quote are intentional snapshots so a citation remains displayable after later
document updates.

**Invariants:** Within a turn, a source number resolves consistently to one
chunk. The quote must be verbatim evidence from the referenced chunk; checking
that fact is later Citation Engine logic.

**Future extension points:** Character or geometry anchors may be proposed for
more precise source navigation.

## 11. Notebook models

### 11.1 `Notebook`

**Purpose and responsibility:** Represent a named organizational collection.
Membership is not embedded in this record.

**Semantics:** Immutable identity record; equality and hashing use
`notebook_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `notebook_id` | `UUID` | Required | None | Stable notebook identity. |
| `title` | string | Required | None | Non-empty display name. |
| `description` | string or null | Optional | null | Non-empty when present. |
| `created_at` | `Timestamp` | Required | None | Creation time. |
| `updated_at` | `Timestamp` | Required | None | Last metadata-change time. |
| `metadata` | `Metadata` | Required | empty | Presentation and future extension values. |

**Relationships:** Documents are related through `Source`; sessions, notes, and
insights carry `notebook_id` explicitly where applicable.

**Invariants:** `created_at` is not later than `updated_at`. Source counts and
summaries are derived data, not authoritative fields.

**Future extension points:** Multi-user ownership and permissions remain outside
core. Derived summaries belong to generated notes or later models.

### 11.2 `Source`

**Purpose and responsibility:** Represent only the association between one
notebook and one logical document.

**Semantics:** Immutable identity record; equality and hashing use `source_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `source_id` | `UUID` | Required | None | Stable association identity. |
| `notebook_id` | `UUID` | Required | None | Associated notebook. |
| `document_id` | `UUID` | Required | None | Associated logical document. |
| `created_at` | `Timestamp` | Required | None | Time the association was created. |

**Relationships:** Belongs to exactly one notebook and references exactly one
document. Multiple sources may reference the same document from different
notebooks.

**Invariants:** The pair `(notebook_id, document_id)` is unique. Deleting a
notebook removes its source records only. A document becomes garbage-collection
eligible only when no source references it. Those deletion operations are later
business logic.

**Serialization:** No title, document bytes, version, ingestion status, or
metadata is duplicated into the association.

**Future extension points:** Per-notebook display overrides would require review
because they expand `Source` beyond a pure association.

### 11.3 `Note`

**Purpose and responsibility:** Represent first-class notebook-authored content,
whether written by the user or generated by Mnemo.

**Semantics:** Immutable identity record; equality and hashing use `note_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `note_id` | `UUID` | Required | None | Stable note identity. |
| `notebook_id` | `UUID` | Required | None | Owning notebook. |
| `title` | string or null | Optional | null | Non-empty when present. |
| `content` | string | Required | None | Must not be empty. |
| `origin` | `NoteOrigin` | Required | None | User-created or generated. |
| `created_at` | `Timestamp` | Required | None | Creation time. |
| `updated_at` | `Timestamp` | Required | None | Last content or title change. |
| `metadata` | `Metadata` | Required | empty | Generation or presentation provenance. |

**Relationships:** Belongs to one notebook. It does not directly own document
or source records.

**Invariants:** `created_at` is not later than `updated_at`. Generated notes may
record provenance in metadata, but metadata cannot replace citations when
claims require evidence.

**Future extension points:** Explicit source links or note versioning require a
later proposal.

### 11.4 `Insight`

**Purpose and responsibility:** Represent one extracted claim, key fact, entity
observation, or summary derived from a notebook source.

**Semantics:** Immutable identity record; equality and hashing use `insight_id`.

| Field | Type | Presence | Default | Rules |
|---|---|---|---|---|
| `insight_id` | `UUID` | Required | None | Stable insight identity. |
| `notebook_id` | `UUID` | Required | None | Notebook context in which the insight was produced. |
| `source_id` | `UUID` | Required | None | Source association from which it was derived. |
| `type` | `InsightType` | Required | None | Insight category. |
| `content` | string | Required | None | Non-empty extracted content. |
| `confidence` | finite number or null | Optional | null | Raw extractor confidence in the inclusive range 0 through 1 when supplied. |
| `created_at` | `Timestamp` | Required | None | Extraction time. |
| `metadata` | `Metadata` | Required | empty | Extractor provenance and type-specific data. |

**Relationships:** Belongs to a notebook and a `Source`. Through the source it
resolves to the underlying document without duplicating `document_id`.

**Invariants:** The source's notebook matches `notebook_id`. Confidence is raw
extractor output, not a calibrated probability. Cross-record relationship
validation belongs to storage.

**Future extension points:** Direct evidence chunk IDs and explicit insight
revision history require later review.

## 12. Model relationship summary

The authoritative ownership graph proposed by this ADR is:

```text
Notebook ──< Source >── Document ──< DocumentVersion ──< Chunk
    │
    ├──< Session ──< Turn ──< Citation >── Chunk
    ├──< Note
    └──< Insight >── Source

ParsedDocument ──< Block >── ImageBlock ─── Asset
ParsedDocument ─── DocumentMetadata
DocumentVersion ─── DocumentMetadata

ScoredChunk ─── Chunk
MetadataFilter ──references──> Notebook / Source / DocType
Entity ──participates through normalized name──> GraphEdge
```

Angle brackets indicate the many side of a relationship. `Source` is the only
notebook-document association. Filesystem blobs and parsed IR are authoritative
storage artifacts but are not ownership nodes in Module 1.1.

## 13. Invariant enforcement by boundary

| Boundary | Invariants it can enforce |
|---|---|
| Model construction | Field types, enum membership, local ranges, non-empty values, immutable collection shape, local date ordering. |
| Aggregate construction | Parsed block ordering, document version consistency, session turn ordering. |
| Storage layer | Foreign-key existence, unique source association, reciprocal chunk relationships, identity reuse conflicts. |
| Later business modules | Status transitions, garbage collection, citation quote resolution, chunk-ID generation, parent construction. |

This division keeps Module 1.1 free of parsing, retrieval, storage, and business
logic while still making invalid standalone values unrepresentable.

## 14. Consequences if approved

### Positive

- Module 1.1 gains a complete, testable public contract.
- Stable document and version identities are represented separately.
- Notebook ownership follows the frozen `Source` association decision.
- Immutable collections make most models safely hashable.
- Persisted JSON has deterministic, versioned rules.
- Raw retrieval scoring cannot be confused with calibrated confidence.
- Parsed IR contains no embedded image bytes or storage implementation details.

### Costs and constraints

- Implementing immutable JSON metadata requires a deliberate representation.
- Identity-based equality means conflicting snapshots with the same ID must be
  detected at repository boundaries rather than through equality comparisons.
- `Document.current_hash` is deliberately denormalized and must be validated
  against the current version.
- Enum expansion is a reviewed schema change rather than a free-form extension.
- Graph-edge evidence provenance remains intentionally deferred because the
  architecture's Module 1.1 contract does not define it.

## 15. Approval record

The accepted review confirmed:

1. the compatibility resolutions in section 3;
2. immutable sequence types instead of mutable lists in domain snapshots;
3. the proposed block common fields and image-reference representation;
4. the split between document ingestion status and version current/superseded
   status;
5. identity-based equality and hashing for UUID/content-identified records;
6. the exact notebook, conversation, citation, note, and insight fields;
7. the canonical JSON rules and the revised block-ordinal-span chunk-ID
   preimage;
8. the supporting enums introduced by this proposal.

## 16. Approved revisions

The accepting review required and this version incorporates exactly these
changes:

1. `heading_path` was removed from chunk identity and replaced by the canonical
   source block-ordinal span.
2. `ChunkPosition` gained optional canonical-text `start_offset` and
   `end_offset` fields, which do not participate in chunk identity.
3. The generic immutable `Asset` model was introduced and `ImageBlock` now
   references `asset_id` rather than a storage path.
4. `Citation` gained `version_id` for reproducible versioned evidence.
5. `Entity` gained deterministic immutable aliases.
6. Metadata namespace ownership conventions were reserved for core subsystems
   and plugins.

All other accepted schema decisions remain unchanged. Module 1.1 implementation
is authorized against this accepted revision.
