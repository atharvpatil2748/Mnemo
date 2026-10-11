# Binary structured metadata exposure — 2026-09-28

IMPLEMENTATION_OMISSION_CORRECTED; EXTERNAL_PRESENTATION_RETEST_PENDING

## Failing-first defect and compatible fix

Native MCP EmbeddedResource/Image metadata already contained transfer fields. structured_content_for discarded most of them; therefore ADR-0073's authoritative structured companion did not expose the full reconstruction metadata. New regression with actual native range metadata failed before correction with KeyError rangeStart. It passes after the allowlist copy.

The structured resource now exposes existing camelCase names: rangeStart, rangeEnd, rangeEndExclusive, returnedBytes, totalBytes, contentHash, snapshotIdentity, originalMediaType, notebookId, sourceId, documentId, versionId, assetId, occurrenceId, completeness, nextCursor when present. Compatible snake_case ancestry aliases remain; source_id is emitted only when verified source metadata exists, preserving old metadata-free response shapes. Additive outputSchema properties declare types. Unknown privatePath/internal metadata and raw byte content are not copied into structured JSON.

IMPORTANT: rangeEnd is the numeric endpoint; rangeEndExclusive is a boolean convention flag. A received range is [rangeStart,rangeEnd), and returnedBytes must equal rangeEnd-rangeStart. This preserves native naming rather than inventing an incompatible numeric meaning for the flag. The full hash is original-content hash, not the current part hash. Each part also has independently calculated received-byte SHA in the evidence manifest.

## Final-source transport observations

[Actual range manifest](mnemo-ordered-text-binary-transfer-manifest.json) includes both certified stdio (11:07:04–11:07:27UTC) and authenticated loopback SSE (11:08:47–11:08:48UTC; exact timestamps in artifact). Every page asserted equality of structured companion fields and native transfer metadata, byte count, stable snapshot/hash/ancestry, no gaps/overlaps and terminal completeness. Actual received part files were independently materialized before concatenation, not reconstructed from advertised metadata.

| Resource | One call | Multipart | Exact final integrity |
| --- | --- | --- | --- |
| PDF | 3821824 bytes | 8 pages, max_bytes524288 | SHAeb4fe330163f7d89535ca48f792204a16da042bb2e4895a6030102df20a63984; valid PDF6 pages |
| JPEG | 704901 bytes, native image and binary_format=resource | 11 pages, max_bytes65536 | SHAcab6378eeb056237af3b785d9421e8fb0c6c889b730b37e719dcea8247acb19a; JPEG3576×2512 |
| Embedded PDF JPEG comparison | Extracted from actual reconstructed PDF | Compared with one-call and multipart asset | Byte-identical |

PDF final range[3670016,3821824),151808bytes. JPEG final range[655360,704901),49541bytes. Both final cursors null and completeness complete. Partial JPEG blob MIME may be application/octet-stream while originalMediaType remains image/jpeg. Native full image content and negotiated resource bytes are identical. An older corrupt mounted image was not used as a fresh response.

Persisted get_image_analysis returned2 OCR/Vision items, complete, through both final certified transports; record identities/ancestry preserved. Generation provider availability remains separate from persisted analysis delivery. Analysis is bounded by existing count/byte ceilings; this task does not add an undocumented analysis cursor.

## External boundary

The owner's earlier independent eight/eleven-part reconstruction is accepted history. This task has no owner-connected external MCP automation. The corrected fields have not been freshly observed in the external connector. The [prompt](mnemo-final-external-text-certification-prompt.md) asks it to inspect structured and native metadata independently and report any client presentation omissions without attributing them to the server automatically.

No binary transformation, protected asset mutation, public unauthenticated byte endpoint, credential disclosure, new tool or connector modification was introduced. Local tests do not prove proprietary connector attachment handling.
