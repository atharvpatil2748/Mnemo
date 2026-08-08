# Parser Boundary Redesign (0.10.1)

**Date:** 2026-08-08

## Summary

The core parser interface boundary has been redesigned to preserve the pure functional nature of parsers while maintaining the strict immutability of the canonical document domain models.

### Why the redesign was necessary

During the start of Module 3.2 (PDF Parser), we encountered an architectural contradiction. The previous parser boundary (`ParserInterfaceV1`) expected parsers to directly return a `ParsedDocument` containing canonical `Block` objects. For `ImageBlock`, this model requires a permanent `asset_id` (UUID). 

However, parsers are pure transformation components. They perform no network I/O, no blob persistence, and generate no permanent identities. A pure parser cannot write to BlobStore to mint a permanent `asset_id` for an extracted image, leading to a conflict between the parser's capabilities and the required canonical output model.

### The new parser boundary

`ParserInterfaceV1` now returns a new transport object: `ParseResult`.

This result contains:
- `RawBlock`s (base class for `RawTextBlock`, `RawImageBlock`, etc.)
- `TransientAsset`s (representing raw bytes extracted from the document)

These transient models are NOT domain models. They are never persisted, never leave the ingestion pipeline, and are purely used to transport parsed data to the orchestration layer.

### Why ParsedDocument remains canonical

`ParsedDocument` and `ImageBlock` remain completely unchanged. Keeping them strict and immutable ensures that downstream components (Chunkers, Cleaners, Retrievers) can always assume a valid, persistent document state without dealing with transient parsing artifacts. 

### Why ParseResult is transient

`ParseResult` acts purely as a transport bridge. By encapsulating raw extracted bytes (like images) and parser-local references into `TransientAsset` and `RawBlock`s, parsers can fulfill their job of structural extraction without violating their pure functional constraints. The `ParseResult` disappears once the ingestion orchestrator has processed it.

### The responsibility of DocumentCanonicalizer

We have introduced the `DocumentCanonicalizer` component (part of the ingestion orchestration layer). Its sole responsibility is to translate the transient `ParseResult` into a canonical `ParsedDocument`. It achieves this by:
1. Persisting all `TransientAsset`s to the BlobStore.
2. Minting permanent `asset_id`s (UUIDs) for the persisted blobs.
3. Translating `RawImageBlock`s into canonical `ImageBlock`s using the generated `asset_id`s.
4. Validating and returning the final immutable `ParsedDocument`.
