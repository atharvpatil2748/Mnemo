# Ordered-text independent external handoff — 2026-09-28

ISOLATED_TEXT_FIXTURE_REQUIRES_OWNER_ACTION

The isolated server is publicly retrievable with owner authentication and has
passed complete external-style MCP reconstruction. The owner must configure its
actual ChatGPT connection and refresh the production tool definitions. No external
ChatGPT certification is claimed. This verdict concerns those exact remaining
connection/discovery dependencies, not an unresolved delivery implementation defect.

Use [fixture evidence](mnemo-isolated-external-text-fixture.md),
[schema readiness](mnemo-public-text-schema-readiness.md) and the
[independent truth manifest](mnemo-ordered-text-fixture-manifest.json).
The fixture auto-expires2026-09-30T12:31:23.150652Z and must be removed within7 days.

## Owner connection step

Refresh the existing production connection using its supported Refresh control,
confirm mode original|blocks|text, then start a new conversation. Add a separately
named authenticated test connection to the fixture's /mcp/ URL if secure Bearer
configuration is supported. Never paste credentials into chat or a URL.
Otherwise, an owner-admin must create a separate temporary Secure MCP Tunnel
scoped to the owner's actual workspace, obtain its runtime management credential
through the approved control plane, and use the prepared inactive test-tunnel
template and isolated stdio launcher. Do not reuse the production tunnel ID or
change its credential. No admin CRUD credential is available to this run.
The inactive template is not a running second OpenAI connection.

Ensure the production and test connections are distinguishable in the client.
If names collide, connect/test one at a time and label each evidence set. Do not
assume that the fixture is present in the44-source production inventory.

## Complete copy-paste verification prompt

```text
Independently certify Mnemo ordered document-text delivery using ONLY actual
connected Mnemo MCP calls for data retrieval. Do not use web search, memory,
prior claimed passes or simulated calls. Offline computation may be used to
preserve received payloads, reconstruct UTF-8 bytes and calculate SHA-256; do not
invent a hash if no byte-accurate computation is available. Never print secrets.

There are TWO separate scopes: certified production and a disposable isolated
text fixture. They are not federated. Identify the actual connected tools and
their connection names. If ambiguous, ask the owner to select the appropriate
connection; do not send fixture IDs to production as a positive test.

FIRST, on the ISOLATED FIXTURE connection call get_capabilities({}) and
list_notebooks({"limit":1}). Record exact responses, client UTC start/end and
request/correlation IDs where exposed. Then call scoped get_capabilities with
the discovered notebook ID. Require isolated_certification, mutation disabled,
fixture database digest below and a still-valid lease. Do not demand production
model/certification identity from this explicitly model-free test endpoint.

Expected test endpoint (owner-connected; do not fetch it with web tools):
https://rotary-tobago-michelle-filter.trycloudflare.com/mcp/
Lease expires 2026-09-30T12:31:23.150652Z. After expiry report owner re-provisioning
needed, not permission to change protected production data.
Expected discovered identities:
notebook_id: 434043e6-7149-4232-86af-e72e0f8434ef
source_id: 215543fc-70aa-4ae7-8cda-870e925d1177
document_id: cf43cabc-08f8-4ca6-ad4d-f35cbf25bf69
version_id: b8183755-55d4-4771-8d84-2ffd0e741cee
database_sha256: acb5635fd0b0056205f16d739966613d3df46ac6ae89057ef560645d05eacc35
If discovery differs, stop the affected fixture test and record the mismatch.

Inspect the ACTUAL client-visible get_document argument schema. It must allow
original, blocks and text. Distinguish visible client schema from server
tools/list, which may not be available through your interface. If text is rejected
before an invocation, report stale/incorrect connection metadata and ask the
owner to Refresh/reconnect and start a new conversation. Do not claim that a
server error occurred or substitute search_evidence for full text enumeration.

Make FOUR fresh full traversals: mode blocks then text, each with max_items1
and max_items3. For every first page use this exact scope and full selector:
{"notebook_id":"434043e6-7149-4232-86af-e72e0f8434ef",
 "document_id":"cf43cabc-08f8-4ca6-ad4d-f35cbf25bf69",
 "version_id":"b8183755-55d4-4771-8d84-2ffd0e741cee",
 "mode":"blocks","selector":{"kind":"full"},"max_items":1,"max_bytes":8192}
Change mode/page size only when BEGINNING a separate fresh traversal. Follow
each returned next_cursor verbatim, with every other argument unchanged.
Preserve each actual page independently. Expect12 pages at size1 and4 at size3,
total_items12, indices/ordinals0..11, page_number1..12, canonical source ancestry,
no duplicates/gaps/reordering, truncated intermediate pages and a complete
terminal page with no cursor. Snapshots must stay stable within each mode:
blocks: 4e5d9f73a2a38754865a2057587591317590a3dd28d59883a11abcb6e69d735f
text: 7405a9cd9e6139be0ce596e761e9a59075edbcfb332ceecffcc204d0ed4f8e97
Representations: parsed_blocks/v1 and parsed_text/v1 respectively.

Independently supplied typed source truth, in exact ordinal order:
0 HeadingBlock: text="Ordered fixture", level1.
1 TextBlock: text="Paragraph α — नमस्ते\n\nIntentional blank line."
2 TableBlock: rows=[["Name","Value"],["Café","東京"]], header_row_count1.
3 CodeBlock: code="def greeting():\n    return '🙂'", code_language="python".
4 EquationBlock: latex="E = mc^2", display=true.
5 ImageBlock: alt_text="Image alt: diagram → result",
  asset_id="00000000-0000-0000-0000-000000000032" (alt-text fixture, not a binary asset).
6 TextBlock: text="Page seven: résumé".
7 HeadingBlock: text="Second heading", level2.
8 TextBlock: text="Tabs\tand newlines\nare retained."
9 TableBlock: rows=[["Final table","2"],["Δ","3"]], header_row_count0.
10 EquationBlock: latex="\\int_0^1 x\\,dx = \\frac12", display=true.
11 TextBlock: text="Final paragraph."
Compare every actual typed field and page reference with this truth, not with
a second delivery call as the sole oracle. Public item kind canonical_block
is the envelope kind; do not confuse it with these persisted block classes.

For each text traversal concatenate every actual payload.text immediately
followed by THAT item's payload.separator_after. Do not trim whitespace,
normalize Unicode, remove blank lines or add Markdown/trailing newlines.
Expected independent rendered text is newline-join of this JSON string array:
["Ordered fixture","Paragraph α — नमस्ते\n\nIntentional blank line.",
 "Name\tValue\nCafé\t東京","def greeting():\n    return '🙂'","E = mc^2",
 "Image alt: diagram → result","Page seven: résumé","Second heading",
 "Tabs\tand newlines\nare retained.","Final table\t2\nΔ\t3",
 "\\int_0^1 x\\,dx = \\frac12","Final paragraph."]
Require exact UTF-8 bytes and SHA-256:
70f933e57255937afc39612ac54a311f7653ab9c1c7d91c20106a4db12a83493.
Both page sizes must reconstruct identically. Rendered text intentionally omits
heading levels, code-language labels, table-header metadata and equation display
flags, but blocks retain them. Never infer available image bytes from alt text.

Using ONLY this disposable fixture, preserve a first-page cursor and independently
try changed max_items, changed max_bytes, changed mode, changed selector, changed
document/version with synthetic unknown IDs and a one-character cursor tamper.
Require safe typed failures with correlation IDs, not content leakage. Distinguish
client-side schema rejection from server-side typed error. Replay an unchanged
page and require identical items; replay must not consume server state. Do not
create another principal, use unrelated IDs or claim cross-user/expiry proof
without an authorized test facility. Resume the valid cursor unchanged afterwards.

SEPARATELY, on the PRODUCTION connection call get_capabilities({}) and
list_notebooks({"limit":1}), then notebook-scoped capabilities using discovery.
Compare runtime-reported targets:
database SHA-256 3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c
database identity 0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d
binding ID 56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d
notebook df9c20cf-85fe-529c-902e-2e9e68193fbe,44 sources.
Historical display name Phase 8.5 Evaluation Corpus is not proof of federation.

Use two adjacent bounded original PDF deliveries, max_bytes524288, on:
document135b4fd5-15cd-5a22-89db-096dcc9b55bc,
versiond49eb763-3bf3-54d1-aec4-bfd66ca43fe8.
Use two adjacent get_asset deliveries, max_bytes65536,binary_format="resource",
occurrence7c31fd63-a975-51f3-bc27-0a6505649ffe in the production notebook.
Follow each cursor unchanged. Verify public structured resource metadata:
numeric rangeStart/rangeEnd, BOOLEAN rangeEndExclusive=true, returnedBytes,
totalBytes, contentHash,snapshotIdentity,originalMediaType and canonical ancestry.
PDF ranges[0,524288),[524288,1048576),total3821824,
hash eb4fe330163f7d89535ca48f792204a16da042bb2e4895a6030102df20a63984.
JPEG ranges[0,65536),[65536,131072),total704901,
hash cab6378eeb056237af3b785d9421e8fb0c6c889b730b37e719dcea8247acb19a.
Partial JPEG transport MIME may be application/octet-stream; originalMediaType
must remain image/jpeg. Adjacent ranges must not overlap or leave a gap.
Do not repeat full downloads unnecessarily or claim full reconstruction from
these metadata checks. Earlier independent8-part PDF/11-part JPEG reconstruction
is historical external evidence, not a fresh result of this session.

For the production PDF above and code document8abc6c73-7d1c-5248-8c28-4157de5ca51a,
version7882f1db-a197-5c84-9b10-66b1fe2d3689, invoke blocks/full and text/full with
max_items3,max_bytes8192. Expect safe capability_unavailable with code
delivery.representation_unavailable unless actual readiness has changed.
Do not create/backfill representations or treat searchable chunks as full text.
If the production connection is unavailable, mark this section NOT TESTED;
do not invent it from fixture results or previous reports.

Return a page-by-page evidence matrix: actual arguments (opaque cursors may be
redacted in presentation but must be preserved for use), UTC times, request IDs,
scope/representation/snapshot, item indices, completeness, safe errors and exact
reconstruction hashes. Separate client-visible observations, external-style
operator evidence, local security tests and internal file-integrity attestation.
Public MCP does not independently prove source revision, protected DB immutability
or four-transport certification. Product Stage7 and search_image are out of scope.

Issue ORDERED_TEXT_EXTERNALLY_CERTIFIED only if actual connected calls provide
all12 typed blocks and exact rendered bytes/hash at both page sizes with valid
terminal/cursor behavior. Otherwise issue ORDERED_TEXT_EXTERNAL_CERTIFICATION_PENDING
with the exact schema, authentication, fixture-access, expiry or byte-computation
dependency. Never award certification based only on tool visibility/status fields.
```
