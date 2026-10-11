# Mnemo — independent ordered-text and public-metadata certification

Use ONLY the actual connected Mnemo MCP tools for Mnemo observations. Do not use web search, memory, old reports, simulated calls, or local engineer results as fresh external proof. A local byte-processing facility may hash/materialize bytes actually received; it must not substitute locally sourced files for MCP payloads. Never disclose credentials or internal paths. All calls are bounded and read-only. Product Stage 7 and search_image are out of scope.

FIRST make these actual calls:
1. get_capabilities({})
2. list_notebooks({"limit":1})
Record raw safe responses, UTC start/end times (or explicitly unavailable client timing), request/correlation IDs, client-visible tool names, and nonsecret runtime identities. A server tools/list result must be distinguished from the client-visible inventory.

Production targets supplied independently by the owner:
- Database SHA-256: 3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c
- Governed database identity: 0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d
- Runtime binding: 56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d
- Authorized production notebook: df9c20cf-85fe-529c-902e-2e9e68193fbe; 44 sources; historical display name “Phase 8.5 Evaluation Corpus” is not a serving-role decision.
Compare only fields actually returned. A runtime-reported hash is not independent verification of database bytes. The operator's deployed product-content attestation is cdf4bc9b3140d5b0b8063766e7b0bdd7f4154df9190b42aa17fec77b63d2313d; do not claim MCP independently proves that digest or loaded code.

Call get_capabilities({"notebook_id":"df9c20cf-85fe-529c-902e-2e9e68193fbe"}).

A. PUBLIC SCHEMA AND SAFE MISSING-REPRESENTATION CHECKS
Inspect the connected get_document argument contract, if exposed. It must accept mode original | blocks | text. Record the actual visible enum, or that tool-schema inspection is unavailable.
Call get_document separately with mode="blocks" and mode="text", selector={"kind":"full"}, max_items=1, max_bytes=8192, using each authorized tuple:
- PDF document 135b4fd5-15cd-5a22-89db-096dcc9b55bc / version d49eb763-3bf3-54d1-aec4-bfd66ca43fe8.
- Code document 8abc6c73-7d1c-5248-8c28-4157de5ca51a / version 7882f1db-a197-5c84-9b10-66b1fe2d3689.
Use the production notebook above. Their parsed representations were absent at preparation time. Expected authorized result: capability_unavailable / delivery.representation_unavailable, not fabricated text or resource-not-found. Distinguish client-side enum rejection (server never called) from the server's typed unavailability.
If text is rejected by the connector schema, stop only the text-dependent checks. Ask the owner to refresh/reconnect the existing Mnemo integration and open a NEW conversation so tool definitions are fetched again; verify the three-value enum after refresh. Do not repeatedly submit a client-invalid argument or infer server behavior from it.

B. POSITIVE ORDERED FIXTURE — EXPLICIT PREREQUISITE
At handoff time NO disposable fixture is authorized on the production connection. The local 12-block fixture is NOT an external production resource. Do not submit local test UUIDs to the production connection or invent fixture IDs.
Proceed with positive reconstruction ONLY after the owner supplies an independently authorized isolated fixture connection/allowlist and its actual notebook, source, document, version, representation and expected-truth manifest. Match that connection's identity and discover the same authorized tuple through its real tools. Do not expect its database identity to equal the production target.
The supplied local expected-truth artifact is mnemo-ordered-text-fixture-manifest.json. For an exact copy of that fixture, the expected item count is 12 and UTF-8 rendered-text SHA-256 is 70f933e57255937afc39612ac54a311f7653ab9c1c7d91c20106a4db12a83493. These values apply ONLY if the owner attests the externally provisioned fixture has that same persisted content. Otherwise use its independently supplied truth.
If no approved external fixture is supplied, mark positive ordered-text certification NOT TESTED — authorized fixture exposure required. Do not pass it from local tests.

For an approved fixture:
1. Call global and fixture-scoped get_capabilities; verify authority and exact ancestry.
2. get_document with its actual notebook/document/version, mode="blocks", selector={"kind":"full"}, max_items=1, max_bytes=8192. Follow every next_cursor unchanged with IDENTICAL remaining arguments. Preserve every page independently.
3. Require stable snapshot and representation parsed_blocks/v1, total_items=12 when applicable, sequential indices/ordinals 0..11, canonical ancestry, no gaps/duplicates/reordering, truncated+cursor on nonterminal pages, complete+null cursor at termination. Stable block identity is exact version + immutable snapshot + ordinal, not a fabricated block UUID.
4. Compare typed block payload fields against the independent expected sequence, including headings, table rows/header counts, code/language, equations, image alt text, Unicode, blank lines and page numbers. Full-selector items may be kind canonical_block; inspect payload rather than assuming class names are emitted.
5. Repeat with max_items=3 using a fresh traversal; require identical final block sequence.
6. Repeat both fresh page sizes with mode="text", full selector, max_bytes=8192. Representation must be parsed_text/v1. Concatenate EACH payload.text followed by THAT item's payload.separator_after without trimming, Unicode normalization, added Markdown, or invented trailing newline. Compare exact UTF-8 bytes/digest and complete sequence to independent truth.
7. Plain text intentionally omits heading levels, code-language labels, table-header annotations and graphical/layout formatting; table cells use tabs, rows/block separators newlines, equations retain stored LaTeX and images their stored alt text. Structural fidelity comes from blocks, not search snippets.
8. Reuse a returned cursor with only max_items changed, then only max_bytes changed, then mode changed, then selector changed. Require safe invalid_input cursor conflict or the documented selector-validation rejection, never successful continuation under altered binding. Tamper one token character and require a safe invalid cursor. Repeat an unchanged page and verify identical content; do not consume or overwrite the continuation state.
Never test cross-user/resource IDs without separately authorized fixtures. Actor replay, expiry, protected immutability and old/new schema behavior remain separately supplied local evidence unless actually testable here.

C. PUBLIC BINARY METADATA — REPRESENTATIVE FRESH CALLS
The prior independent external session already reconstructed the PDF in eight parts and JPEG in eleven with matching hashes. Do not relabel that history as new evidence.
Call get_document with production tuple above, mode="original", max_bytes=524288. Call get_asset with notebook above, occurrence_id="7c31fd63-a975-51f3-bc27-0a6505649ffe", binary_format="resource", max_bytes=65536.
Inspect the STRUCTURED resource companion and native resource metadata separately. Require:
rangeStart; rangeEndExclusive; returnedBytes; totalBytes; contentHash; snapshotIdentity; originalMediaType; canonical notebook/source/document/version identity; occurrence/asset ancestry for the image; completeness; nextCursor.
IMPORTANT: rangeEnd is the exclusive numeric offset; rangeEndExclusive is a BOOLEAN declaring that convention, not a second numeric endpoint. Verify returnedBytes = rangeEnd - rangeStart. Do not treat true as an offset.
Expected PDF total 3821824, hash eb4fe330163f7d89535ca48f792204a16da042bb2e4895a6030102df20a63984, MIME application/pdf.
Expected JPEG total 704901, hash cab6378eeb056237af3b785d9421e8fb0c6c889b730b37e719dcea8247acb19a, MIME image/jpeg, dimensions 3576×2512.
Follow one unchanged continuation for each and verify adjacency, stable identity/hash/total/snapshot and correct completeness. Native partial image resources may use application/octet-stream; originalMediaType must retain image/jpeg.
If metadata is absent from structured content but present natively, report that distinction. If the connector hides both, report client presentation limitations; do not claim bytes or ranges were verified from a success label.
Only repeat complete downloads if needed to resolve integrity: independently preserve every received range, assemble actual bytes in range order, verify exact total/hash/PDF six pages/JPEG dimensions and compare one-call/multipart/PDF-embedded JPEG. Do not use an older mounted file or a locally supplied original as a received response.
Call get_image_analysis for the authorized occurrence with selection="latest_ready"; inspect complete persisted OCR/Vision payload, derivation/generation IDs and exact ancestry. Persisted analysis is not proof a generation provider is configured.

OUTPUT
Return an evidence matrix separating fresh external MCP calls, owner/operator attestations, earlier independently accepted binary reconstruction, local disposable security tests, local transport evidence and unverified internal invariants. Include exact safe arguments, timings, IDs, schema observations, ancestry, page counts, errors, reconstruction/hash results and unmet prerequisites.
Use ORDERED_TEXT_EXTERNALLY_CERTIFIED only if actual authorized external blocks and text reconstruction both match independent truth at both page sizes and public metadata/schema checks pass. Otherwise use ORDERED_TEXT_EXTERNAL_CERTIFICATION_REQUIRES_SPECIFIC_ACTION and name the exact missing fixture, schema refresh, payload access or defect.
Do not award Stage 6/Stage 7 acceptance or four-transport certification from this narrow external session. Do not change production content, credentials, serving roles or configuration.
