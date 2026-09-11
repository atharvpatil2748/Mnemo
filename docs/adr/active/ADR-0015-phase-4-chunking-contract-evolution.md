# ADR-0015: Phase 4 Chunking Contract Evolution

**Status:** Accepted
**Date:** 2026-08-11
**Decision owners:** Mnemo maintainers
**Approval:** Approved for Module 4.1 implementation
**Depends on:** ADR-0001, ADR-0002, ADR-0014

## Context

ADR-0014 completes the transient-to-canonical ingestion boundary and makes an
immutable `ParsedDocument` available to Phase 4. The released
`ChunkerInterfaceV1` accepts that document, a `version_id`, and
`ChunkingOptions`, then returns final `Chunk` values.

Pre-implementation review found that this contract cannot construct or verify
the frozen `Chunk` schema. A chunk requires `document_id`, but V1 receives no
authoritative document binding. Its identity requires the canonical source
block-ordinal span, but that span is hidden generation state and is neither
stored nor returned. Strategies also cannot describe parent relationships
before permanent chunk IDs exist. Finally, the repository defines token limits
without defining a tokenizer, while a dispatcher cannot safely perform
strategy-independent text splitting without violating semantic atomicity.

The original architecture used an earlier shape:
`chunk(ParsedDocument, ChunkConfig) -> list[Chunk]`, with identity described as
text, document identity, and position. ADR-0001 replaced that identity with
`version_id`, canonical block span, and text. ADR-0002 introduced
`ChunkingOptions` and V1, but omitted `document_id` and public provenance. The
ADRs are authoritative over the historical sketch, and this proposal evolves
their incomplete Phase 4 boundary rather than restoring the older contract.

## Problem

Phase 4 needs a contract that allows every semantic strategy to:

- use the document/version identity owned by the registry workflow;
- preserve independently inspectable canonical-block provenance;
- describe a single-parent hierarchy without knowing final chunk IDs;
- use one deterministic local token-counting definition;
- perform only strategy-safe semantic splitting; and
- return immutable chunks whose identity and relationships are finalized and
  validated centrally before indexing.

It must not add identity to `ParsedDocument`, make chunkers perform storage or
network I/O, use offsets or headings in identity, or silently mutate V1.

## Options considered

### Put document identity on `ParsedDocument`

Rejected. `ParsedDocument` is the canonical content IR. Registry identity is
owned by `Document` and `DocumentVersion`, assigned outside parsing and
canonicalization.

### Pass independent `document_id` and `version_id` values

Rejected in favor of reusing `DocumentVersion`, which already binds those
values and the content hash immutably and prevents mismatched identities.

### Resolve document identity through storage

Rejected. It would add storage I/O and a hidden dependency to pure chunking.

### Keep the source span in metadata or private implementation state

Rejected. Identity provenance must be required, immutable, serializable, and
independently available to tests, persistence adapters, and later citations.

### Use text or token offsets as provenance identity

Rejected. Offsets are navigation coordinates and are explicitly excluded from
chunk identity by ADR-0001.

### Let strategies emit final IDs and relationships

Rejected. It duplicates canonical hashing and graph validation across every
built-in and third-party strategy.

### Identify draft parents with opaque keys or relationship objects

Rejected for V2. Strategy output is already an ordered immutable tuple; an
earlier tuple index expresses the required single-parent forest with less
surface area and makes dangling references and cycles structurally invalid.

### Let the dispatcher split oversized text mechanically

Rejected. No universal mechanical splitter can preserve tables, equations,
functions, procedures, abstracts, slides, and other semantic atomic units.

### Permit per-strategy tokenizers or a whitespace fallback

Rejected. Universal size invariants require one comparable definition. A
whitespace count is not an approved substitute for model-like tokenization.

### Modify `ChunkerInterfaceV1` in place

Rejected by ADR-0002 section 4.1. The new Phase 4 contract is V2; V1 remains
deprecated during its compatibility window.

## Decision

The following Phase 4 contracts are frozen. The tokenizer asset is deliberately
not a Mnemo distribution artifact: it is acquired only through an explicit,
user-initiated provisioning operation and verified before local installation.

### `ChunkingContext`

`ChunkingContext` is an immutable, non-serialized operation record containing:

| Field | Type | Rule |
|---|---|---|
| `document_version` | `DocumentVersion` | Authoritative `document_id`, `version_id`, and content-hash binding. |
| `options` | `ChunkingOptions` | Immutable limits for one chunking operation. |

The dispatcher SHALL verify
`ParsedDocument.metadata.content_hash == DocumentVersion.content_hash` before
strategy invocation. `ParsedDocument` does not gain registry identity.

### `BlockSpan`

`BlockSpan` is an immutable domain value containing inclusive
`start_ordinal` and `end_ordinal` integers. Both are non-negative,
`start_ordinal <= end_ordinal`, and both SHALL resolve within the supplied
`ParsedDocument.blocks` tuple.

A V2 span is contiguous. One chunk cannot claim multiple disjoint spans.
Multiple chunks MAY legitimately share the same `BlockSpan`. A split inside one
source block retains the same one-block span. A split of a multi-block draft
MAY narrow each result to the smaller contiguous range that actually
contributed; a boundary block may therefore appear in more than one span.

These concepts remain distinct:

- `BlockSpan` identifies contributing canonical blocks;
- `Chunk.text` is the finalized semantic text boundary; and
- `ChunkPosition.start_offset` and `end_offset` are optional navigation
  coordinates into canonical extracted text.

Offsets and headings do not replace source provenance and do not participate in
identity. Independent identity verification requires only stored
`version_id`, `source_span`, and `text`; verifying the quality of the semantic
derivation remains a strategy conformance test.

### Canonical `Chunk.source_span`

`Chunk` gains required `source_span: BlockSpan`. It participates in validation
and identity generation but does not change equality semantics: equality and
hashing remain based on `Chunk.id`.

The span SHALL be persisted by every chunk store and survive SQLite and Qdrant
round trips and CompositeStorage compensation. Legacy chunks without source
provenance SHALL NOT receive fabricated spans. They are derived data and require
explicit re-chunking from their retained `ParsedDocument`.

### `ChunkDraft`

`ChunkDraft` is an immutable, non-persisted contract record containing:

| Field | Type | Rule |
|---|---|---|
| `text` | string | Non-empty semantic content. |
| `chunk_type` | `ChunkType` | Existing ADR-0001 enum. |
| `position` | `ChunkPosition` | Navigation metadata only. |
| `heading_path` | immutable string sequence | Strategy-derived hierarchy context. |
| `source_span` | `BlockSpan` | Required provenance. |
| `metadata` | `FrozenMetadata` | Namespaced strategy metadata. |
| `parent_index` | integer or null | Null for a root; otherwise references an earlier draft. |

It contains no permanent ID, document/version UUID fields, sibling IDs, or
embedding. Strategies emit drafts in deterministic preorder. A non-null
`parent_index` SHALL satisfy `0 <= parent_index < current_index`. This permits
multiple roots and arbitrary depth while guaranteeing parent-before-child
ordering and excluding forward references and cycles.

### `ChunkerInterfaceV2`

V2 is the Phase 4 strategy contract:

```text
supported_doc_types -> immutable sequence of DocType
capabilities() -> ChunkerCapabilities

chunk(
    document: ParsedDocument,
    context: ChunkingContext,
    token_counter: TokenCounterInterfaceV1,
) -> immutable ordered sequence of ChunkDraft
```

It is synchronous, deterministic, stateless, concurrently safe, local, and
storage-free. It performs no network calls, UUID generation, embedding,
retrieval, indexing, or final relationship-ID generation.

`ChunkerInterfaceV1` remains documented and deprecated. Phase 4 implementations
SHALL implement V2 rather than V1.

### Registry interface-version isolation

Chunker registration identity includes capability kind, document-type slot,
and interface version. The public APIs are:

```text
register_chunker(
    doc_type: DocType,
    implementation: ChunkerInterfaceV1,
    *, priority: int,
    plugin_name: str | null = null,
) -> none

resolve_chunker(doc_type: DocType) -> ChunkerInterfaceV1 | null

register_chunker_v2(
    doc_type: DocType,
    implementation: ChunkerInterfaceV2,
    *, priority: int,
    plugin_name: str | null = null,
) -> none

resolve_chunker_v2(doc_type: DocType) -> ChunkerInterfaceV2 | null
```

The existing unversioned registry methods remain the V1 methods for the entire
ADR-0002 two-minor-release compatibility window. The exported unversioned
`ChunkerInterface` alias likewise continues to refer to
`ChunkerInterfaceV1`; callers opt into V2 through its explicit name. Changing
that alias after the compatibility window requires a separately documented
public-API change. The generic `resolve(CapabilityKind.CHUNKER, slot)` lookup
also retains its released V1 meaning; V2 resolution is available only through
the explicit V2 method.

Registry storage and conflict identity SHALL be
`(CapabilityKind.CHUNKER, doc_type.value, interface_version)`. The same
version qualifier applies to the registry's internal identity for all
capability families, although only chunking introduces a second version here.
V1 and V2 candidates never compete for priority and an equal-priority candidate
in V1 cannot conflict with V2. Within one version-qualified key, existing
priority, equal-priority conflict, and identical-registration idempotency rules
remain unchanged.

The active registration is computed independently per version-qualified key.
`list_registrations()` continues to expose both versions through the existing
`RegistrationDescriptor.interface_version`; its deterministic order is
`capability`, `slot`, `interface_version`, descending `priority`,
`provider_name`, then `plugin_name`. The Phase 4 dispatcher calls only
`resolve_chunker_v2()`.

This requirement is limited to contract-version isolation. It does not change
plugin discovery, plugin semantic-version compatibility, priority ordering, or
other public capability-family methods. It requires a narrow PluginRegistry
implementation evolution during Module 4.1, but no existing public method or
V1 behavior changes.

### Canonical `TokenCounter`

`TokenCounterInterfaceV1` is a synchronous, deterministic, thread-safe, local
contract exposing a stable `tokenizer_id` and `count(text) -> non-negative
integer`. `tokenizer_id` SHALL bind the tokenization algorithm, Mnemo adapter
contract version, and exact vocabulary/merge asset SHA-256; changing any of
those creates a new identity. The same instance SHALL be passed to the selected
strategy and used by dispatcher validation. Phase 4 has no per-call or
per-strategy tokenizer selection and no fallback. Missing or corrupt tokenizer
resources cause `DependencyUnavailableError` before strategy work.

Tokenization operates on the stored Unicode string without normalization or
case folding. Token-like special strings are ordinary document content. It
performs no network access or runtime download.

The repository currently has no tokenizer dependency, configuration section,
vendored vocabulary, license record, or approved tokenizer ADR. The exact
technical candidate is:

- engine dependency: `tiktoken==0.13.0`;
- encoding: `o200k_base`;
- encoding asset: `o200k_base.tiktoken`;
- upstream expected asset SHA-256:
  `446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`;
- Mnemo adapter contract: `v1`;
- frozen upstream URL:
  `https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken`;
- expected byte size: `3,613,922`; and
- stable identity:
  `mnemo/o200k_base;adapter=v1;engine=tiktoken-0.13.0;asset-sha256=446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`.

The adapter SHALL construct the encoding from the verified local asset and use
ordinary-text encoding semantics: special-token-like strings are document text,
not control tokens. It performs no normalization or case folding. A Python
string containing an unpaired surrogate is rejected with
`ContractValidationError`; valid Unicode, including composed and decomposed
forms, is counted exactly as supplied. Empty text counts as zero. A missing or
hash-mismatched provisioned asset raises non-retryable
`DependencyUnavailableError` before strategy invocation.

The expected supported runtime is CPython 3.12. Golden counts must be identical
on Mnemo's documented Windows environment and Ubuntu CI; any additional
supported wheel platform must pass the same vectors before being claimed as a
supported release target. The frozen golden corpus SHALL cover empty text,
ASCII, composed/decomposed Unicode, CJK, Indic scripts, combining marks,
emoji/ZWJ sequences, source code, mathematics, newlines, and special-token-like
text, plus rejection vectors for unpaired surrogates and missing/corrupt assets.

Mnemo SHALL NOT vendor, commit, bundle, or redistribute the encoding asset in
its repository, wheel, sdist, Docker image, or packaged installer. The
installation/deployment layer exposes the explicit
`mnemo provision-tokenizer` operation. Only that user-initiated operation may
download the asset directly from the frozen upstream URL. It verifies byte
size and SHA-256 and atomically installs the bytes into a user-local,
content-addressed Mnemo tokenizer directory. It is not a package installation
hook and never runs implicitly.

Air-gapped administrators may import an independently obtained file through
the same provisioner; identical size and hash checks apply. Deployments may
mount the provisioned directory into containers, but normal Mnemo build
artifacts remain asset-free. Runtime chunking and `TokenCounterInterfaceV1`
perform no network access, provisioning, repair, or fallback. A missing or
corrupt asset requires an explicit provisioning/repair action.

This distribution boundary avoids Mnemo redistributing the separately hosted
asset. It is an engineering distribution decision, not a legal conclusion
about the asset. Operators remain responsible for compliance when acquiring
and using upstream resources.

### `ChunkingOptions`

The released `ChunkingOptions` constructor and V1 semantics remain unchanged.
It owns the existing type and base-value checks: positive `target_tokens` and
`max_tokens`, non-negative `overlap_tokens`, `target_tokens <= max_tokens`,
`overlap_tokens < target_tokens`, and immutable metadata.

`ChunkingContext` owns the additional V2 validation. When constructed it SHALL
require a `DocumentVersion` and `ChunkingOptions`, revalidate the base relations
defensively, and enforce:

- `target_tokens >= 15`;
- `max_tokens >= target_tokens`;
- `overlap_tokens >= 0` and `< target_tokens`;
- and no tokenizer override field exists.

`target_tokens` is the desired strategy size. `max_tokens` is the configured
absolute ceiling. Overlap is a strategy hint and SHALL NOT cross a semantic
boundary. Module 4.1 accepts only a valid `ChunkingContext`, computes the
effective hard maximum as `min(max_tokens, 2 * target_tokens)`, applies token
limits to `ChunkDraft.text`, and enforces the final size/failure sequence. It
does not weaken or reinterpret either constructor's validation.

### Semantic splitting and failure

Each strategy owns all semantic splitting and uses the supplied canonical token
counter while doing so. The dispatcher never blindly word-splits arbitrary
semantic content. If an atomic source unit exceeds the effective maximum and
has no legal strategy-specific split, the strategy raises `UnsupportedError`.
It does not truncate, return partial output, or emit an oversized chunk.

The dispatcher treats an oversized returned draft as `IntegrityError` because
the strategy violated its V2 contract.

### Parent and sibling semantics

Chunk hierarchy is a single-parent forest. A root has no parent; a non-root has
exactly one real parent chunk. Cross-links belong in graph metadata/storage.
Strategies emit parent drafts explicitly, and the dispatcher never synthesizes
semantic parent text. No hierarchy is inferred from `section_index` or
`heading_path`. A strategy declaring `supports_parent_child=False` may emit all
roots.

Two final chunks are siblings only when they share the same non-null parent.
Root chunks are not siblings merely because both have no parent. Sibling links
are symmetric, exclude self, and follow final dispatcher order. A single child
has an empty sibling tuple. A parent is not its child's sibling.

### Dispatcher finalization

Module 4.1 SHALL execute exactly this sequence:

1. validate the `ParsedDocument` and `ChunkingContext`;
2. verify the parsed-document and `DocumentVersion` content hashes match;
3. resolve the V2 strategy by `ParsedDocument.doc_type`;
4. validate the strategy's supported types and capabilities;
5. invoke it with the canonical token counter;
6. validate drafts and their `BlockSpan` values against the document;
7. validate the parent-index forest;
8. token-count every draft with the same token counter;
9. reject oversized returned drafts;
10. identify drafts below 15 tokens;
11. reject a short draft that is a parent of any child;
12. remove short leaf drafts;
13. remap surviving parent indexes;
14. compute canonical chunk IDs;
15. reject duplicate IDs;
16. materialize parent IDs;
17. materialize symmetric, deterministically ordered sibling IDs; and
18. return an immutable ordered tuple of `Chunk`.

The dispatcher performs no storage or network I/O, UUID generation, embedding,
retrieval, indexing, semantic splitting, or semantic parent synthesis.
An empty canonical document or a strategy that emits no drafts produces an
empty immutable chunk tuple; no `BlockSpan` is fabricated.

### Identity

The existing ADR-0001 identity formula is preserved. The ID is SHA-256 over the
UTF-8 canonical JSON array:

```text
[
  lowercase canonical version_id,
  [source_span.start_ordinal, source_span.end_ordinal],
  chunk text
]
```

`heading_path`, text offsets, `document_id`, tokenizer identity, chunk type,
metadata, relationships, embedding, and random UUIDs do not participate.
Multiple chunks may share a span, but two drafts producing the same version,
span, and text produce the same identity; duplicate identities in one dispatch
are an integrity failure rather than silently collapsed records.

### Heading paths

`heading_path` remains navigation and interpretation metadata. It is derived by
each semantic strategy from canonical headings and strategy-specific hierarchy.
It may be empty only when the represented source has no applicable hierarchy.
Module 4.1 validates field shape and provenance; sufficiency is enforced by
per-strategy acceptance tests because implicit code, resume, slide, email, and
documentation hierarchies cannot be inferred universally by the dispatcher.

### Storage and re-chunking

SQLite requires source start/end ordinal columns, and Qdrant payloads require a
serialized source span. Snapshot/restore logic SHALL preserve the complete
field. This is derived-data schema evolution and requires an explicit migration
that re-chunks or rejects legacy rows rather than inventing provenance.

ADR-0002 currently defines affected-ID upsert: identities omitted from a batch
remain untouched. It therefore cannot atomically replace an entire old chunk
set after re-chunking. ADR-0015 does not silently change that contract. Atomic
full-set replacement is a later storage/indexing contract prerequisite before
incremental re-chunk publication is implemented.

### Email strategy ownership

Architecture section 10.6 and frozen `DocType.EMAIL` require a thread-aware
Phase 4 strategy. The roadmap promises nine strategies but historically listed
only eight. Before implementation, Email becomes Module 4.7 and the currently
unimplemented Resume, Slides, and Documentation modules shift to 4.8, 4.9, and
4.10. Generic fallback is not a substitute for thread-aware semantics.

ADR-0016 identifies the required upstream Email semantic boundary. Module 4.7
may begin only after an approved `email-ingestion` parser has produced
canonical `ParsedDocument` values carrying valid `parser.email.*` metadata.
That prerequisite is implemented and validated. The Email strategy consumes
that metadata only; it does not parse MIME, assemble independently ingested
documents, or infer lost thread structure.

### Chunk types and LLM-derived content

The ADR-0001 `ChunkType` enum is unchanged. Architecture shorthand such as
`IMAGE`, `EQUATION_DESCRIPTION`, and `PROFILE_SUMMARY` maps to an existing
semantic type plus `chunker.*` subtype metadata. For example, a profile summary
uses `SUMMARY`; generated image or equation descriptions use an appropriate
existing type with explicit subtype metadata. No ad hoc enum member is added.

Phase 4 is deterministic and local. It makes no LLM or network call and emits
no fake summary or description placeholder. LLM-generated book/profile
summaries, image descriptions, and equation explanations belong to a future
post-chunk enrichment pipeline that must receive its own roadmap assignment and
contract before implementation. Base strategies emit only content they can
derive deterministically from the canonical document.

## Invariants

- Context identity comes only from one `DocumentVersion`.
- The context and parsed document describe the same content hash.
- Source spans are contiguous, inclusive, in range, immutable, and persisted.
- Multiple chunks may share a source span.
- Draft order is deterministic and parents precede children.
- Final hierarchy is acyclic and single-parent.
- Sibling links are symmetric and derived only from a shared non-null parent.
- One canonical token counter governs strategy generation and validation.
- All returned chunk text is between 15 and the effective maximum tokens.
- No semantic boundary is crossed to satisfy a size target.
- Returned chunks are immutable and carry no embedding.
- Canonical IDs are reproducible from stored public fields.
- Contract failure returns no partial chunk sequence.

## Ownership and phase boundaries

| Owner | Responsibility |
|---|---|
| Document registry workflow | Create and retain `DocumentVersion`. |
| Phase 3.9 | Produce and persist canonical `ParsedDocument`; no chunking. |
| Phase 4 strategies | Semantic hierarchy, text generation, heading context, source spans, safe splitting, draft parent indexes. |
| Module 4.1 dispatcher | V2 selection, invariant validation, short-leaf filtering, identity and relationship finalization. |
| Canonical token counter | Local deterministic counting only. |
| Phase 5 | Add embeddings without changing chunk identity or provenance. |
| Indexer | Publish a complete validated chunk result through storage contracts. |
| Storage adapters | Persist and restore every canonical chunk field. |
| Phase 6 ParentRetriever | Promote stored child families to their real stored parent. |
| Future post-chunk enrichment pipeline | Optional LLM-derived summaries and descriptions under a later ADR/roadmap assignment. |

## Compatibility and versioning

This is a breaking chunker-contract and chunk-record evolution. It introduces
V2 rather than changing V1. The registry isolates versions. V1 remains
deprecated for at least the ADR-0002 compatibility window, but Phase 4 consumes
only V2.

Adding required `Chunk.source_span` and a V2 public contract requires a future
pre-1.0 minor release when implementation begins. This proposal itself changes
no package version.

## Migration

- Add source-span persistence to SQLite and Qdrant during the designated
  implementation work.
- Preserve spans in CompositeStorage snapshots and rollback.
- Do not fabricate source spans for legacy chunks.
- Re-create legacy derived chunks from retained canonical documents.
- Specify atomic full-version chunk-set replacement separately before
  incremental re-chunk indexing.

## Consequences

Positive consequences:

- every Phase 4 strategy can remain semantic and storage-independent;
- identity generation and relationship integrity are centralized;
- provenance is inspectable after persistence;
- ParentRetriever receives an explicit, deterministic family graph; and
- Phase 5 and Phase 6 can preserve chunk identity without another schema
  redesign.

Costs and deferred decisions:

- chunk records and storage schemas gain required provenance;
- V1/V2 coexistence adds registry-version handling;
- deployments require an explicit tokenizer-provisioning step;
- strategy-specific parent content requires each strategy's own acceptance
  specification; and
- atomic full-set replacement remains later storage/indexer work.

## Acceptance prerequisites

ADR acceptance requires:

- approval of `ChunkingContext`, `BlockSpan`, `ChunkDraft`, and
  `Chunk.source_span`;
- approval of parent, sibling, splitting, and failure semantics;
- a frozen tokenizer implementation, asset checksum, offline behavior,
  user-side provisioning behavior, adapter identity, dependency version, and
  golden expected counts from the verified upstream artifact;
- approved V1/V2 registry isolation;
- specified storage provenance migration;
- resolved Email module ownership and numbering;
- resolved later ownership of LLM enrichment; and
- approved contract, tokenizer, dispatcher, persistence, and downstream
  acceptance-test specifications.

## Required acceptance tests

Contract and model tests SHALL establish:

- `ChunkingContext` uses the supplied `DocumentVersion` and rejects a content-
  hash mismatch without invoking a strategy;
- `BlockSpan` rejects negative, reversed, out-of-range, and disjoint claims,
  while permitting multiple chunks and same-block splits to share one span;
- identity is exactly reproducible from persisted `version_id`, `source_span`,
  and text, changes with text/version/span, and is unchanged by heading paths,
  navigation offsets, tokenizer identity, metadata, or relationships;
- `ChunkDraft` is immutable and has none of the prohibited persisted/final
  fields;
- explicit V1 and V2 methods resolve independently; priorities, conflicts, and
  active flags cannot cross versions; listing order includes interface version;
  V1 aliases remain V1; and the dispatcher never resolves V1 as V2;
- parent indexes reject dangling, forward, and cyclic structures while
  allowing deterministic preorder, multiple roots, and multiple levels;
- sibling links are symmetric, ordered by final output, self-excluding, empty
  for a sole child, and never group unrelated roots;
- tokenizer golden vectors are identical on every supported offline platform
  and corrupt or missing assets fail before strategy invocation;
- both strategy and dispatcher receive/use the identical counter instance;
- V1 option construction remains unchanged, while `ChunkingContext` enforces
  every additional V2 constraint and has no tokenizer override;
- short leaves are removed and indexes remapped, while a short parent with any
  child fails without partial output;
- oversized drafts and unsplittable atomic content fail with the specified
  exception, with no truncation, mechanical splitting, or partial success;
- SQLite, Qdrant, and CompositeStorage round trips/snapshots preserve source
  spans exactly and do not fabricate legacy provenance; and
- every `DocType`, including `EMAIL`, has the intended V2 strategy resolution
  or the documented unsupported result during staged implementation.

## Relationship to existing ADRs

- Preserves ADR-0001 identity inputs, immutability, equality, and `ChunkType`;
  once accepted, it supersedes only the statement that block-span provenance is
  non-public and adds required `Chunk.source_span`.
- Preserves ADR-0002 conventions, errors, dependency inversion, and V1
  compatibility; once accepted, its V2 contract supersedes only section 6.2 for
  Phase 4 use and adds version-isolated chunker registration.
- Preserves ADR-0011 through ADR-0014. `ParsedDocument` remains the sole
  canonical Phase 4 content input, while registry identity arrives separately
  through `ChunkingContext`.

## Tokenizer review references

- Published `tiktoken` package versions and Python 3.12 wheels:
  <https://pypi.org/project/tiktoken/>
- OpenAI `tiktoken` source license:
  <https://github.com/openai/tiktoken/blob/main/LICENSE>
- Upstream `o200k_base` constructor and expected asset hash:
  <https://github.com/openai/tiktoken/blob/main/tiktoken_ext/openai_public.py>

These references identify the frozen engine and upstream encoding artifact.
Mnemo does not redistribute the asset.

## Implementation status

Accepted and implemented. Module 4.1 provides the contract infrastructure and
dispatcher. Modules 4.2 through 4.10 provide all nine built-in V2 semantic
strategies. Every strategy remains synchronous, deterministic, local, and
identity-free; final IDs and relationships remain dispatcher-owned.
