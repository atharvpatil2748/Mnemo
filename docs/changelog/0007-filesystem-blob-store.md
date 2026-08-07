# Engineering Changelog 0007: Phase 2, Module 2.1 — Filesystem Blob Store

- **Scope:** Phase 2, Module 2.1
- **Status:** Complete
- **Recorded:** 2026-08-07
- **Release:** 0.6.0
- **Previous baseline:** Phase 1 baseline audit (0.5.1)
- **Next module:** Phase 2, Module 2.2 — SQLite FTS5 Store (not started)

## Summary

Implements the content-addressed filesystem blob store as the first concrete
storage backend in the Mnemo storage layer. This satisfies the `BlobStore`
contract from ADR-0002 §5.2 and the Module 2.1 task table from the engineering
roadmap.

## New package: `mnemo.storage`

The `mnemo/storage/` package is introduced at Phase 2. This entry point will
collect all storage-backend implementations. Only `FilesystemBlobStore` is
exported in this release; `CompositeStorage` (Module 2.5) will compose it with
the other backends.

## New module: `mnemo.storage.filesystem`

### `FilesystemBlobStore`

A concrete implementation of the ADR-0002 §5.2 `BlobStore` contract backed by
the local filesystem. It does not inherit from `StorageInterfaceV1`; the full
`CompositeStorage` facade (Module 2.5) will assemble and delegate to it.

**BlobStore contract methods:**

- `put_asset(data, mime_type, metadata) -> Asset` — Content-addresses raw bytes
  by SHA-256, writes atomically via sibling-temp-file + `os.replace`, and
  returns an immutable `Asset`. The `asset_id` is derived deterministically via
  UUID5 so identical bytes are idempotent across any number of writes.
- `get_asset(asset_id) -> bytes | None` — Resolves the asset UUID to a content
  hash via a side-car JSON index, reads the blob file, and verifies the SHA-256
  digest on every read. Returns `None` if the asset was never stored.
- `delete_asset(asset_id) -> bool` — Removes the index entry and blob file.
  Returns `True` if the asset existed, `False` otherwise. Shard directories are
  pruned when empty.
- `put_parsed_document(version_id, document) -> None` — Serializes a
  `ParsedDocument` to a versioned canonical JSON envelope and writes it
  atomically under `<root>/parsed/<vid[:8]>/<version_id>.ir.json`. Idempotent
  for identical content; raises `ConflictError` for content changes.
- `get_parsed_document(version_id) -> ParsedDocument | None` — Deserializes the
  stored IR JSON and returns the reconstituted `ParsedDocument`, or `None` if
  absent.
- `contains_hash(content_hash) -> bool` — Returns `True` if the
  content-addressed shard directory exists.

**Lifecycle methods:** `open()`, `close()` (both idempotent), `health_check()`,
`capabilities()`.

### Atomic write discipline

All writes use `tempfile.mkstemp()` in the same parent directory as the target,
followed by `os.replace()`. On POSIX this is atomic; on Windows `os.replace()`
handles overwrites safely. Partial or failed writes leave no corrupt state.

### Content-addressed path layout

```
<root>/
    <hash[:2]>/<hash[2:]>/
        raw.<ext>               — original asset bytes (extension from MIME)
    parsed/<vid[:8]>/
        <version_id>.ir.json    — ParsedDocument IR envelope
    _index/assets/
        <asset_uuid>.json       — side-car: UUID → content_hash + MIME mapping
```

This matches the architecture §13 specification exactly.

### ParsedDocument IR serialization

The IR JSON envelope uses a `"model": "parsed_document"` discriminator and a
`"schema_version": 1` guard per ADR-0002 §4.7. All seven Block subtypes
(`TextBlock`, `HeadingBlock`, `TableBlock`, `ImageBlock`, `CodeBlock`,
`EquationBlock`, `CaptionBlock`) survive a serialize → deserialize round-trip.
Full `DocumentMetadata` fields including `publication_date`, `authors`, DOI, and
ISBN are preserved.

## Tests added

`mnemo-core/tests/unit/test_filesystem_blob_store.py` — 58 tests covering:
- Round-trip blob and IR storage
- Content-addressed SHA-256 path layout verification
- Idempotency of repeated writes
- ConflictError on differing ParsedDocument for same version_id
- IntegrityError on corrupt blob and UUID index collision
- All Block subtypes and all DocType enum values
- Large blob (1 MB) round-trip
- Empty-bytes blob
- Multiple independent assets and IR documents
- Lifecycle guards (LifecycleError before open, after close)
- health_check and capabilities flags
- Internal helpers (_compute_sha256, _asset_id_for_hash)
- Storage URI opaqueness

## Compatibility

No Phase 1 public contract changed. `FilesystemBlobStore` is additive;
`StorageInterfaceV1` and all existing Phase 1 exports are unchanged.

## Version

`mnemo-core` version bumped from `0.5.1` to `0.6.0` to mark the first Phase 2
storage implementation milestone.
