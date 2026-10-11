# Independent Mnemo complete-resource reconstruction verification

Use only the actual connected Mnemo MCP tools to obtain Mnemo data. Do not use web search, memory, earlier claimed results, simulated calls, private paths or guessed credentials. Local computation on bytes actually received is allowed for reconstruction, SHA-256, PDF parsing, image decoding and comparisons. If this client cannot access the actual bytes, report that boundary explicitly; metadata-only success is not reconstruction.

Start with get_capabilities({}) and list_notebooks({"limit":1}). Record UTC start/end timestamps, request/correlation IDs when exposed, exact safe responses and visible tool inventory. Never print credentials.

Compare runtime-reported targets:
- production database SHA-256: 3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c
- governed database identity: 0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d
- effective binding: 56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d

Operator-only deployed-source target is 832fad3b4a3a26bf3f5bb3e3b124a067997b2d5c9fc580a4a9c3828cf5391d32 (291 product Python files). MCP does not independently expose this source manifest. Do not infer source loading or protected-database integrity merely from a reported database hash.

The owner authorizes read-only testing of notebook df9c20cf-85fe-529c-902e-2e9e68193fbe (44 sources; historical display name “Phase 8.5 Evaluation Corpus”). That display name does not identify the separately isolated evaluation databases. Check the notebook and scoped get_capabilities; stop resource calls if authorization or certified production identities do not match.

Authorized PDF:
document_id 135b4fd5-15cd-5a22-89db-096dcc9b55bc
version_id d49eb763-3bf3-54d1-aec4-bfd66ca43fe8
size 3821824 bytes, 6 pages
SHA-256 eb4fe330163f7d89535ca48f792204a16da042bb2e4895a6030102df20a63984

Authorized JPEG occurrence:
occurrence_id 7c31fd63-a975-51f3-bc27-0a6505649ffe
size 704901 bytes, JPEG 3576 x 2512
SHA-256 cab6378eeb056237af3b785d9421e8fb0c6c889b730b37e719dcea8247acb19a
Expected ancestry is the PDF document/version above.

1. PDF one-call:
get_document({"notebook_id":"df9c20cf-85fe-529c-902e-2e9e68193fbe","document_id":"135b4fd5-15cd-5a22-89db-096dcc9b55bc","version_id":"d49eb763-3bf3-54d1-aec4-bfd66ca43fe8","mode":"original","max_bytes":4000000})
Materialize THIS response's actual embedded-resource bytes, not an older mounted file. Decode its native base64 once if exposed. Check byte count, advertised/independently computed hash, PDF signature, decoding and six pages.

2. PDF multipart:
Repeat that request with max_bytes:524288 and no cursor. Save every received page independently. Continue with the exact returned nextCursor, leaving all other arguments identical. Never guess/retype/decode/re-encode the cursor. Complete eight expected calls (at least five required).
For each call record rangeStart, rangeEnd, rangeEndExclusive, returnedBytes, totalBytes, contentHash, snapshotIdentity, originalMediaType, notebook/source/document/version ancestry, completeness and timestamp/request ID.
Ranges are [start,end), end exclusive. Require first start0, next start=previous end, no gaps/overlap, actual received count=end-start, stable hash/size/identity, truncated pages with cursor and final complete page with null cursor.
The range-specific mnemo:// URI is an opaque identity, not a public download URL. Do not try to open a local path or invent a resources/read endpoint.
Concatenate saved received ranges in order; verify 3821824 bytes, expected SHA, PDF decoding/six pages and byte-for-byte equality with the one-call PDF. Publish a transfer manifest and reconstructed artifact only if actual received bytes are accessible.

3. JPEG one-call:
get_asset({"notebook_id":"df9c20cf-85fe-529c-902e-2e9e68193fbe","occurrence_id":"7c31fd63-a975-51f3-bc27-0a6505649ffe","max_bytes":1000000})
Materialize the fresh native ImageContent bytes if available. Independently check 704901 bytes, expected SHA, JPEG decoding, dimensions and ancestry.
If the image display/attachment hides original bytes, the additive negotiated native blob form is:
get_asset({"notebook_id":"df9c20cf-85fe-529c-902e-2e9e68193fbe","occurrence_id":"7c31fd63-a975-51f3-bc27-0a6505649ffe","max_bytes":1000000,"binary_format":"resource"})
Use only if the connected tool schema accepts this field; if stale, report schema/connection refresh needed. Never claim success from a preview or an unrelated mounted attachment.

4. JPEG multipart:
get_asset({"notebook_id":"df9c20cf-85fe-529c-902e-2e9e68193fbe","occurrence_id":"7c31fd63-a975-51f3-bc27-0a6505649ffe","max_bytes":65536,"binary_format":"resource"})
Continue unchanged with nextCursor. Save each received blob independently; eleven expected ranges. Partial-image blobs use application/octet-stream with originalMediaType:image/jpeg; decode only after complete reconstruction. Apply the PDF range/security invariants. Verify size, hash and dimensions; compare byte-for-byte against fresh one-call JPEG AND JPEG extracted from page1 of the verified PDF. Do not blame a previous corrupt mounted file on this response without linking it to exact request/bytes.

5. Ordered document text and blocks:
Use get_document with the authorized PDF IDs, mode:"text", selector:{"kind":"full"}, max_items:20,max_bytes:50000. If representation parsed_text/v1 exists, continue unchanged until terminal completion. Require stable snapshot/total_items/representation and sequential unique indices. Reconstruct by appending each item's payload.text + payload.separator_after in returned order. This is the documented persisted-block text rendering (table cells tab-separated, rows newline-separated, text/code/LaTeX/image alt text, newline between blocks), not original-file byte equivalence or query-ranked chunk reconstruction.
Repeat with mode:"blocks",selector:{"kind":"full"} for ordered parsed-block delivery when available.
The currently certified PDF and code versions lack this persisted representation. Expected truthful result is capability_unavailable / delivery.representation_unavailable, not contract.not_found. This is NOT successful full-text delivery. Record it as an unavailable production fixture requiring separately authorized staging/certification. Do not create a representation or claim completeness by combining search_evidence snippets.
Also test authorized code document 8abc6c73-7d1c-5248-8c28-4157de5ca51a, version7882f1db-a197-5c84-9b10-66b1fe2d3689, using both views. If a different authorized version with persisted blocks is discovered legitimately, traverse it; do not invent IDs.

6. Persisted analysis:
get_image_analysis({"notebook_id":"df9c20cf-85fe-529c-902e-2e9e68193fbe","occurrence_id":"7c31fd63-a975-51f3-bc27-0a6505649ffe","selection":"latest_ready","modalities":["ocr","vision"]})
Inspect actual text payloads, not just inventory. Check two records, OCR/Vision derivation and generation IDs, occurrence/document/version ancestry, completeness and omissions. Operator observations were one OCR region/five Vision observations; independently recheck, do not assume. Persisted delivery is distinct from configured generation providers.
Record if limits apply: current per-record ceilings256 OCR regions/256 Vision observations plus byte ceiling; oversized analysis has explicit bounded/limit behavior and no content continuation. Do not mark bounded content complete.

7. Cross-tool checks:
Use only already authorized discovered IDs with get_document_chunk for a canonical chunk, bounded search_evidence, scope-qualified get_capabilities, and query_structured for a discovered READY projection or its safe exact-version unavailability. Compare notebook/source/document/version/occurrence/generation IDs and source_metadata. Search results do not prove full document enumeration.
For a fresh small binary traversal, attempt one changed max_bytes continuation and one tampered cursor; require safe cursor conflict/invalid errors. Then resume the original valid cursor unchanged to prove no side effects. Do not probe other users or invent secondary credentials; local disposable tests, not this principal, provide cross-principal evidence.

Report a detailed evidence matrix: tool/arguments, UTC intervals, request/correlation IDs, schema, ancestry, actual materialized bytes, every range, computed SHA, completeness, safe error, result classification. Separate API/adapter evidence from connector materialization. If raw payloads cannot be obtained, identify ImageContent vs EmbeddedResource vs attachment handling and mark reconstruction NOT VERIFIED. Do not substitute reported hashes for computed hashes.

Verdicts:
RESOURCE_RECONSTRUCTION_EXTERNALLY_VERIFIED only for actual received PDF/JPEG one-call/multipart reconstruction plus required available representation checks.
RESOURCE_RECONSTRUCTION_EXTERNAL_ACTION_REQUIRED if materialization or full-text availability prevents a required workflow; identify exact boundary/action.
Do not award full Stage6 acceptance, four-transport certification or protected-state immutability from these MCP calls. Product Stage7 and tool15/search_image are out of scope. No writes, credential changes, evaluation federation or production promotion.
