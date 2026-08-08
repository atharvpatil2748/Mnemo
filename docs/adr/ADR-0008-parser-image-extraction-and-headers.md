# ADR-0008: Parser Image Extraction and Header Detection

**Status:** Superseded by ADR-0011
**Date:** 2026-08-08

## Context

During the implementation of Phase 3, Module 3.2 (PDF Parser), two explicit architectural contradictions and ambiguities were discovered between the Engineering Roadmap, Architecture V2, and established ADRs (ADR-0001, ADR-0002).

### Ambiguity 1: Image Extraction and Persistence

The Engineering Roadmap tasks the PDF Parser with extracting images:
> Extract images | Save as blob, attach caption if present

However, `ParserInterfaceV1` (ADR-0002) explicitly forbids parsers from performing I/O or persistence:
> "Convert raw bytes into a parsed document without I/O side effects... Parse bytes synchronously without network or persistent writes."

Furthermore, the output model `ParsedDocument` and its `ImageBlock` (ADR-0001) only hold an `asset_id` (UUID), without any fields for holding the extracted raw bytes in memory. 

**Conflict:** If the parser cannot perform persistent writes, and the return model cannot hold raw bytes in memory, any images extracted by the parser cannot be saved or returned to the caller, resulting in data loss for extracted images.

### Ambiguity 2: Running Headers/Footers

The Engineering Roadmap tasks the PDF Parser with:
> Detect running headers/footers | Frequency analysis across pages | Architecture §4.1 Cleaner note

However, Architecture V2 (§4.1) explicitly assigns this responsibility to the **Cleaner** (Module 3.7):
> "Cleaner: Normalizes the ParsedDocument. Removes duplicate whitespace, page number artifacts, running headers/footers (detected via frequency analysis across pages)..."

**Conflict:** It is ambiguous whether the PDF Parser should perform frequency analysis to detect and remove running headers/footers, or if it should preserve all text (including headers/footers) and leave the detection and removal to the Cleaner in Module 3.7.

## Decision

We need to resolve these conflicts before implementing the PDF Parser.

**For Ambiguity 1 (Image Extraction), potential resolutions:**
1. **Update `ParserInterface` and `ParsedDocument`**: Allow the parser to return a tuple of `(ParsedDocument, list[AssetData])` or add a mechanism to temporarily hold extracted bytes in the parsed representation so the orchestrator can persist them.
2. **Delegate Image Extraction**: Remove image extraction from the parser's responsibilities, or provide the parser with an injected callback/interface specifically for saving blobs (though this violates the pure functional nature of the parser).

**For Ambiguity 2 (Headers/Footers), potential resolutions:**
1. **Defer to Cleaner**: Remove header/footer detection from the PDF Parser roadmap and strictly enforce it in Module 3.7 (Cleaner).
2. **Parser-Specific Detection**: Allow the PDF parser to remove headers/footers natively since PDF layout offers unique hints (like absolute coordinates) that the generic Cleaner might lack.

## Consequences

Depending on the resolution, we may need to amend ADR-0001, ADR-0002, or the Engineering Roadmap. No implementation of Module 3.2 will proceed until these ambiguities are resolved.
