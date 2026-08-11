# ADR-0016: Email Ingestion Semantic Boundary

**Status:** Accepted
**Date:** 2026-08-11
**Decision owners:** Mnemo maintainers
**Approval:** Approved for Email ingestion boundary implementation
**Depends on:** ADR-0001, ADR-0002, ADR-0011, ADR-0014, ADR-0015

## Context

Architecture section 10.6 assigns Phase 4 a thread-aware Email strategy, while
ADR-0015 requires every Phase 4 strategy to consume only a canonical
`ParsedDocument`. The released parser boundary accepts one immutable byte
payload and returns one `ParseResult`; the ingestion pipeline then cleans,
classifies, canonicalizes, and publishes exactly one `ParsedDocument`.

The repository currently has no Email parser, no `email-ingestion` plugin, no
Email parser registration, and no `parser.email.*` metadata contract. Filename
classification recognizes `.eml` and `.msg`, but classification does not parse
MIME or recover message and thread structure. Consequently, an Email chunker
cannot observe ordered messages, source headers, reply relationships, quoted
content, signatures, or attachment correlation without reparsing source or
inventing information.

This is an information-boundary gap. It cannot be repaired inside Module 4.7
without violating ADR-0011, ADR-0014, and ADR-0015.

## Problem

Mnemo needs a deterministic Email parsing boundary that:

- fits `ParserInterfaceV1`'s one-payload/one-result contract;
- preserves message and thread semantics through cleaning and canonicalization;
- gives Module 4.7 sufficient canonical input without source reparsing;
- assigns no UUID or permanent storage identity during parsing;
- supports valid block-ordinal provenance after cleaning;
- distinguishes source correlation from canonical chunk identity; and
- states which Email containers and MIME behavior V1 actually supports.

The decision must also avoid implying that independently ingested messages are
already assembled transactionally into one canonical thread document.

## Architectural constraints

- `ParserInterfaceV1`, `ParseResult`, `RawBlock`, `DocumentMetadata`, and
  `ParsedDocument` remain unchanged.
- A parser is synchronous, deterministic, local, and free of network and
  persistent-storage I/O.
- The parser may create deterministic parser-local correlation strings but no
  UUIDs or permanent document, asset, or chunk identities.
- `DocumentCleaner` may normalize typed block content. Approved immutable
  parser metadata must survive unchanged.
- `DocumentCanonicalizer` copies approved metadata without interpreting Email.
- `ChunkerInterfaceV2` continues to accept one `ParsedDocument`, one
  `ChunkingContext`, and the canonical token counter.
- Thread, message, header, and attachment correlation never participates in the
  ADR-0001 chunk identity formula.
- Acquisition from IMAP, Microsoft Graph, mail servers, or user accounts is
  external I/O and remains outside parser and chunker contracts.

## Options considered

### A. One message equals one ParsedDocument

This maps directly to `.eml` and supports incremental ingestion and simple
deduplication. It cannot express parent-child relationships between messages
inside `ChunkerInterfaceV2`, because each dispatch sees only one document.
Cross-document ParentRetriever relationships would require a later indexing
contract. Alone, this option does not satisfy section 10.6 for a supplied
multi-message thread.

### B. One entire thread equals one ParsedDocument

This gives Module 4.7 the ideal input and permits message reply relationships
through draft `parent_index`. It is not a complete input contract: `.eml`
normally contains one top-level message, and neither the parser interface nor
the repository defines a standard thread payload or an acquisition-time thread
object. Requiring exactly one thread would also make ordinary mailbox exports
unrepresentable without a new pre-parser interface.

### C. One message equals one ParsedDocument plus a later thread assembler

An assembler after canonicalization would need to create a new canonical
document/version, remap block ordinals, define storage publication and rollback,
and bind multiple source identities. An assembler before canonicalization would
need a new multi-result ingestion contract. Both add a new stage and identity
semantics that Phase 3.9 does not define. This is rejected for V1.

### D. One source Email container equals one ParsedDocument

The existing parser contract can parse one source container into one ordered
result. A single-message `.eml` yields one message. A multi-message `mbox`
container yields one or more source-correlated thread components. The parser
orders messages deterministically and records their relationships; Module 4.7
partitions by thread correlation and never merges different components.

This option preserves source-level deduplication and canonicalization, requires
no new interface or orchestration stage, and supports both ordinary single
messages and exported multi-message collections. Its limitation is explicit:
messages ingested from separate source containers are not assembled into one
`ParsedDocument` by V1.

## Decision

Adopt **Option D: one source Email container equals one `ParsedDocument`**.

The `email-ingestion` plugin implements the existing `ParserInterfaceV1`. It
parses the complete supplied container, identifies its messages and source
relationships, emits ordered raw blocks, and records the schema below. It does
not acquire Email from a remote service and does not combine independently
ingested documents.

One canonical Email document may therefore contain:

- one message and one thread component (`.eml`);
- multiple related messages (`mbox` thread export); or
- multiple independent thread components (`mbox` mailbox export).

Module 4.7 SHALL partition messages by `thread_correlation`; it SHALL NOT merge
different correlations. A message with no retrievable textual body remains in
the document manifest but produces no fabricated or empty chunk draft.

## Document granularity and lifecycle

The source container bytes own content-addressed document/version identity.
Re-ingesting identical container bytes follows the existing ParserRouter
deduplication path. A changed container is a new document version under the
existing ingestion policy; the Email parser does not perform message-level
deduplication or storage lookup.

Repeated message occurrences in one container are preserved in source order.
Source `Message-ID` values are not assumed unique. If a parent reference matches
zero or multiple contained messages, no local parent is fabricated; the source
headers remain available in metadata.

Parsing and canonical publication are all-or-nothing at container granularity.
A fatal MIME, decoding, or structural error raises the existing parser error
taxonomy and produces no partial `ParseResult`.

## Thread ownership

Ownership is divided as follows:

| Responsibility | Owner |
|---|---|
| Remote account/API/IMAP acquisition | External adapter or future ingestion orchestration |
| Decode one supplied Email container | `email-ingestion` parser plugin |
| Identify contained message relationships and stable source correlation | `email-ingestion` parser plugin |
| Clean typed textual blocks without changing Email metadata | `DocumentCleaner` |
| Convert raw blocks and preserve metadata | `DocumentCanonicalizer` |
| Partition contained threads and emit message drafts | Module 4.7 `EmailChunker` |
| Materialize chunk IDs, parents, and siblings | Module 4.1 dispatcher |
| Correlate separately ingested Email documents | Later indexing/retrieval orchestration |

The Email chunker is never a parser or thread assembler. V1 defines no stage
that combines independent `ParsedDocument` values before chunking.

## Thread correlation

Header identifiers are parsed using RFC 5322 message-identifier syntax. A
canonical message identifier removes surrounding comments, folding whitespace,
and angle brackets, preserves the `id-left` value, lowercases only the
`id-right` domain, and serializes as `id-left@id-right`. Invalid identifiers are
treated as unavailable and do not appear in canonical identifier fields or
participate in correlation.

Within one container, the parser builds an identifier graph from valid
`Message-ID`, `In-Reply-To`, and ordered `References` values. Consecutive
`References` identifiers form parent-to-child edges; the last reference or
`In-Reply-To` identifier forms an edge to the message's own identifier. The
immediate local parent is the canonical `In-Reply-To` identifier when it
resolves uniquely; otherwise it is the last `References` identifier when that
resolves uniquely. Dangling, ambiguous, self-referential, and cyclic
relationships have no resolved local parent.

Each connected component receives a deterministic source-thread correlation:

```text
SHA-256(UTF-8("mnemo-email-thread-v1\0" + correlation_seed))
```

The seed is selected from identifier nodes with no incoming graph edge. The
parser visits header identifiers in original message order and, within one
message, `References`, `In-Reply-To`, then `Message-ID` order; the first visited
root is used. If a component has identifiers but no root because its source
headers form a cycle, the lexicographically smallest canonical identifier is
used. When a component contains no valid identifier, its seed is
`raw-sha256:<SHA-256 of the exact contained message bytes>`. Normalized subject
text never creates or merges a thread; it is display/context metadata only.

Thread correlation is deterministic source metadata, not a UUID, document
identity, or chunk identity. A later cross-document correlation owner may use
the same normalized header evidence but is not implemented by this decision.

## Canonical message ordering

Threads are ordered by the first source occurrence of any contained message.
Within each thread, messages use a stable parent-before-child topological order;
ties use original container order. Records with unresolved or invalid parent
relationships retain source order as roots. Cyclic source relationships are
retained as header metadata but contribute no resolved local parent edge.

The parser emits blocks in this canonical message order. Parser-local message
keys are assigned after ordering as `message-000000`, `message-000001`, and so
on. The order is reproducible and enables Module 4.7 to produce earlier-only
draft `parent_index` relationships.

## Email metadata schema

The schema uses existing recursively immutable, JSON-serializable metadata.
Nested objects become `FrozenMetadata` and sequences become tuples. Unknown
schema keys are rejected by the future Email parser's boundary validation.

### Document metadata

| Key | Type | Meaning |
|---|---|---|
| `parser.email.schema_version` | integer | Exactly `1`. |
| `parser.email.container_format` | string | `eml` or `mbox`. |
| `parser.email.messages` | tuple of message objects | Messages in canonical order. |

Each message object contains exactly:

| Field | Type | Meaning |
|---|---|---|
| `local_id` | string | Deterministic parser-local message key. |
| `source_index` | non-negative integer | Original position inside the source container. |
| `thread_correlation` | lowercase SHA-256 string | Source-thread component correlation. |
| `message_id` | string or null | Canonical valid source `Message-ID`. |
| `in_reply_to` | string or null | Canonical valid source `In-Reply-To`. |
| `references` | tuple of strings | Canonical valid `References` identifiers in source order. |
| `reply_to_local_id` | string or null | Uniquely resolved parent message inside this document. |
| `subject` | string or null | RFC-decoded and unfolded source subject. |
| `sender` | tuple of address objects | RFC-decoded source `From` addresses in source order. |
| `recipients` | recipient object | Ordered `to`, `cc`, and `bcc` address tuples. |
| `timestamp` | string or null | Valid source timestamp serialized as RFC 3339 with its parsed offset. |
| `attachments` | tuple of attachment objects | Source-order attachment correlation records. |

An address object contains exactly `name: string or null` and `address: string`.
The recipient object contains exactly `to`, `cc`, and `bcc`, each a tuple of
address objects.

An attachment object contains exactly:

| Field | Type | Meaning |
|---|---|---|
| `local_id` | string | Deterministic key formed from the owning message key and MIME-part preorder index. |
| `filename` | string or null | RFC-decoded source filename. |
| `mime_type` | string | Lowercase MIME type. |
| `content_id` | string or null | Canonical source Content-ID. |
| `disposition` | string or null | Lowercase source disposition. |
| `inline` | boolean | Whether the MIME part is source-designated inline. |

No manifest record stores canonical block ordinal ranges. The cleaner may
remove blocks and reassign ordinals; persisting pre-cleaning ranges would become
stale. Message-to-block correlation is therefore carried on each block, and
Module 4.7 derives current contiguous `BlockSpan` values from canonical blocks.

### Block metadata

Every Email-produced raw block contains:

| Key | Type | Meaning |
|---|---|---|
| `parser.email.message_local_id` | string | Correlates the block to one manifest message. |
| `parser.email.region` | string | One of `body`, `quoted`, or `signature`. |
| `parser.email.body_format` | string | One of `plain`, `html`, or `markdown`. |

An inline `RawImageBlock` additionally carries
`parser.email.attachment_local_id`, which must identify exactly one attachment
record belonging to the same message. No block contains a storage URI, remote
URL, UUID, MIME parser object, or mutable value.

Header values remain document manifest metadata and are not duplicated on
every block. Module 4.7 copies only the required source context into its own
`chunker.email.*` draft metadata. Neither parser nor chunker metadata changes
the canonical chunk identity formula.

## MIME and body semantics

The Email parser owns MIME interpretation. The ADR freezes behavior, not a
specific parsing algorithm:

- `multipart/alternative`: select exactly one textual representation. Prefer a
  valid `text/plain` part; otherwise select a valid `text/html` part. Never emit
  duplicate alternative bodies.
- `multipart/mixed`: emit the selected textual body and record remaining MIME
  parts as attachments in source order.
- `multipart/related`: select the root textual body and correlate inline parts
  by Content-ID where available.
- `message/rfc822` nested parts are attachment/forwarded-message content, not
  automatically members of the enclosing source thread.
- HTML-only bodies undergo deterministic local semantic text extraction owned
  by the Email parser and are marked `body_format=html`. The parser does not
  invoke another registered parser or perform registry resolution.
- Newsletter/announcement content remains a flat Email message. Module 4.7 may
  reuse local Markdown-safe splitting utilities after extraction, but it does
  not redispatch the document or reparse original HTML.
- Transfer encodings are decoded before charset decoding.
- A declared supported charset is authoritative. With no declared charset,
  UTF-8 is attempted. An unknown charset or undecodable selected textual body
  is a fatal parser error; bytes are never silently discarded or replaced.
- RFC-encoded headers are unfolded and decoded deterministically. Missing or
  invalid optional headers become null/empty metadata and do not invent values.
- Malformed MIME that prevents unambiguous message/body/attachment boundaries
  fails the complete parse. There is no partial result.

## Quote and signature semantics

The parser owns region recognition while it has MIME and source-line context.
It emits separate contiguous blocks for recognized regions.

- Plain-text quote recognition uses explicit source quote markers and standard
  reply/forward delimiters; ambiguous prose remains `body`.
- HTML quote recognition uses explicit quotation elements/attributes; visual
  similarity alone is insufficient.
- A plain-text signature begins only at an explicit standard signature
  delimiter. HTML signatures require explicit structural markers. Ambiguous
  closings remain body content.
- Region detection is deterministic, never LLM-assisted, and never deletes
  source-authored textual content.

Module 4.7 may keep regions separate or exclude signatures according to section
10.6, but it may not rediscover or override parser region boundaries.

## Attachment semantics

The Email parser records attachment correlation and may emit `TransientAsset`
plus `RawImageBlock` only for inline images supported by the existing raw asset
contract. `StorageInterfaceV1` remains the sole owner of permanent Asset IDs
during Phase 3.9 ingestion.

Non-inline and non-image attachment bytes are not forced into the image asset
contract. Their extraction and ingestion as independent documents belongs to a
later acquisition/indexing workflow. ADR-0016 records only source metadata and
does not introduce attachment storage, paths, URLs, or permanent identities.

## Supported formats

V1 of the `email-ingestion` plugin supports:

- `.eml` and MIME `message/rfc822` for one top-level RFC message; and
- `.mbox` and MIME `application/mbox` for an ordered multi-message source
  container. The parser may accept standard mbox variants within that container
  contract but does not advertise invented variant MIME types.

The implementation SHALL use Python's standard-library Email/MIME facilities
where they satisfy this contract. No external dependency is architecturally
required for V1.

Outlook `.msg` is explicitly unsupported and deferred. It requires a separately
reviewed parser dependency and compound-binary format contract. The current
classifier's `.msg` heuristic indicates likely document type only; parser
resolution must still raise `UnsupportedError` when no `.msg` parser is
installed. Documentation must not claim built-in or V1 plugin support.

## Parser and plugin ownership

`email-ingestion` is a Layer 4 optional plugin implementing
`ParserInterfaceV1`. It registers only its approved extension and MIME slots
through existing `PluginRegistry.register_parser()`. It does not change parser
interface versioning, registry conflict rules, built-in parser registration, or
the unversioned parser alias.

Plugin registration performs no long-running I/O. Parsing operates only on the
supplied immutable bytes and `FileMetadata`; remote acquisition, credentials,
mailbox synchronization, and watch behavior remain outside the plugin parser.

## Determinism and provenance

For identical bytes, filename, and `FileMetadata`, the parser returns logically
identical ordered `ParseResult` values. It uses no clocks, randomness, UUIDs,
network, storage, filesystem, environment-sensitive ordering, or mutable global
state.

Raw blocks use contiguous ordinals in canonical message order. Cleaner and
canonicalizer preserve `parser.email.*` metadata. Module 4.7 derives each
draft's contiguous `BlockSpan` exclusively from the canonical blocks belonging
to that message and region. It must not combine disjoint spans or different
thread correlations. Multiple drafts may retain the same source span under
ADR-0015 secondary-splitting semantics.

## Rejected alternatives

- **Reparse Email inside Module 4.7:** violates the canonical Phase 4 boundary.
- **Put an Email hierarchy on `ParsedDocument`:** introduces format-specific
  fields into the canonical content model when namespaced metadata is sufficient.
- **Change `ParserInterfaceV1` to return multiple documents:** breaks every
  parser plugin and is unnecessary for source-container granularity.
- **Combine independent documents inside `IngestionPipeline`:** adds undefined
  version identity, publication, rollback, and ordinal-remapping semantics.
- **Infer threads from normalized subjects:** risks merging unrelated messages.
- **Use UUIDs for messages or threads:** creates parser-owned permanent identity.
- **Treat `.msg` as supported because classification recognizes it:** confuses
  classification with parser availability.
- **Store pre-cleaning ordinal spans in document metadata:** cleaner filtering
  would invalidate them.
- **Let the parser access IMAP or remote APIs:** violates parser purity and core
  product boundaries.

## Consequences

### Positive

- Module 4.7 receives sufficient immutable Email semantics without reparsing.
- Existing parser, canonical, chunker, storage, and identity schemas remain
  unchanged.
- `.eml` supports incremental single-message ingestion, while `mbox` supports
  deterministic multi-message and multi-thread chunking.
- Parent-before-child ordering can be expressed through draft `parent_index`
  when a source parent exists in the same container.
- Metadata is independently serializable and testable.

### Limitations

- V1 does not assemble separately ingested `.eml` documents into one canonical
  thread or create cross-document parent chunk IDs.
- Correlation quality depends on valid source message headers.
- Subject-only threading is deliberately unsupported.
- Attachment documents require later ingestion/indexing work.
- `.msg` remains unsupported.
- Strict charset and MIME failures may reject malformed legacy mail rather than
  silently changing content.

## Compatibility and versioning

This is an additive parser-metadata contract. It does not change public domain
model fields, parser signatures, chunker signatures, chunk identity, or storage
interfaces. `parser.email.schema_version=1` identifies the metadata schema.

A future incompatible metadata shape requires a new schema version and a
compatibility decision for EmailChunker. Adding a new supported container or
`.msg` provider requires its own dependency and capability review but does not
implicitly alter this V1 schema.

## Migration implications

No persisted Email documents currently satisfy this schema. Existing documents
classified as `DocType.EMAIL` without valid schema metadata cannot be processed
by Module 4.7 and must be reparsed through an approved Email parser. Metadata or
provenance must never be fabricated for legacy documents.

No database migration, version bump, lockfile change, or chunk migration occurs
as part of this proposed decision.

## Required acceptance tests

Before the Email ingestion boundary is complete, tests must prove:

1. `.eml`, `message/rfc822`, `.mbox`, and `application/mbox` registration and
   routing.
2. Explicit `.msg` unsupported behavior.
3. Deterministic message extraction and canonical ordering.
4. Single-message and multi-thread-container behavior.
5. Parent-before-child ordering and dangling/ambiguous/cyclic reply handling.
6. Duplicate `Message-ID` and repeated-message preservation.
7. Exact correlation normalization and golden SHA-256 vectors.
8. Header decoding, address ordering, timestamps, and missing headers.
9. Plain, HTML, alternative, mixed, related, and nested-message MIME handling.
10. Quote, signature, and body region metadata.
11. Inline and ordinary attachment correlation.
12. Charset, transfer-encoding, malformed MIME, and all-or-nothing failures.
13. Recursive metadata immutability and deterministic JSON serialization.
14. Repeated parsing produces equal `ParseResult` values.
15. Cleaner preserves Email metadata while normalizing typed content.
16. Canonicalizer preserves document and block Email metadata exactly.
17. End-to-end `ParseResult -> ParsedDocument` preservation.
18. No parser storage, network, filesystem, UUID, or clock access.
19. No changes to Phase 3.9 identity and asset ownership.
20. Contract fixtures suitable for future Module 4.7 tests.

## Module 4.7 implementation prerequisites

Module 4.7 was blocked until all of these prerequisites were satisfied:

- ADR-0016 is reviewed and Accepted;
- the `email-ingestion` V1 parser plugin implements this schema;
- all boundary acceptance tests pass; and
- a canonical `ParsedDocument` fixture proves the metadata survives cleaner and
  canonicalizer unchanged.

After those prerequisites, Module 4.7 may consume only the approved canonical
metadata. It must not parse Email source, assemble independent documents, access
storage or network services, or generate permanent identities.

## Implementation status

Accepted and implemented. The optional `email-ingestion` V1 parser produces the
schema above, metadata preservation is covered through canonicalization, and
Module 4.7 consumes only the resulting canonical `parser.email.*` metadata.
