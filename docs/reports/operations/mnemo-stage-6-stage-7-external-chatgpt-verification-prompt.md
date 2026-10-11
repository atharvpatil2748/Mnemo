# Final independent Stage 6 external retest prompt

Copy the block below into a **new** ChatGPT conversation connected to the
existing Mnemo MCP server. The operator's
[final contract audit](mnemo-stage-6-final-contract-and-acceptance-gate-audit.md)
is separate local evidence, not a substitute for these fresh calls.

```text
You are the FINAL independent external verifier of the connected Mnemo MCP
server. Use only actual connected Mnemo MCP tools for Mnemo observations.
Do not use web, memory, shell, simulated calls, earlier reports or this
prompt as evidence of live behavior. Never request writes, guess private
resource IDs, probe another user's data, or disclose credentials/paths.

First invoke get_capabilities({}), then list_notebooks({"limit":1}). Record
the exact UTC client-side start/end times, full safe responses and request
IDs when supplied. Record the Mnemo tool names visible to this client,
without equating client visibility with server-side tools/list or readiness.
Compare the reported production database SHA-256 with
3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c,
governed database identity with
0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d,
and runtime binding ID with
56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d.
These are comparison targets, not proof of the loaded source revision or
independent hashes of local protected files. Public MCP does not emit a
source-content manifest. Keep operator-side process/content attestation,
local forensic tests and signed transport artifacts in separate evidence
columns.
The operator's post-restart, nine-product-file content-manifest digest is
6dafd086decdef5d046aedc85695400c342fbade99533951c47eb81e018127e1.
That value is **not** returned by MCP and cannot be independently matched
to a running process from this client; record it only as supplied operator
evidence, not as a successful external check.

Rediscover the authorized production notebook. Its historical display name
is “Phase 8.5 Evaluation Corpus,” its canonical ID was
df9c20cf-85fe-529c-902e-2e9e68193fbe, and it had 44 sources. Its name
is not proof of separate evaluation-store federation. Confirm the identity
through live inventory and the certified production binding before using it.
Discover the codePrompt.js document/version from actual authorized tool
results. The prior document ID was
8abc6c73-7d1c-5248-8c28-4157de5ca51a; use that ID only if the live
result confirms it is still in your scope. Do not invent a version ID.

Cursor contract retest, once those IDs are confirmed:
1. Call search_evidence with exactly:
   {"query":"buildCodePrompt","mode":"exhaustive","scope":{"notebook_id":"df9c20cf-85fe-529c-902e-2e9e68193fbe","document_ids":["8abc6c73-7d1c-5248-8c28-4157de5ca51a"]},"representations":["canonical_text"],"candidate_budget":3,"evidence_budget":1,"max_content_characters":80}
   Record completeness, item IDs/content lengths, next_cursor presence,
   request ID and timing. Continue with the returned next_cursor as the
   top-level cursor, unchanged, and all other arguments identical. Record
   the full safe error envelope. If the next complete item exceeds 80
   characters, a terminal invalid_input/contract.validation result is the
   current bounded contract; it is not by itself a failed cursor signature.
   Do not publish opaque cursor bytes; record length or digest if possible.
2. Start a NEW traversal with no cursor and otherwise identical arguments
   except max_content_characters:2000. Pass each next_cursor unchanged,
   keeping every other argument fixed. Continue to terminal next_cursor:null,
   at most five pages. Record canonical chunk/version IDs, content lengths,
   ordering, completeness, representation state and any duplicate/omitted
   IDs. Do not reuse the 80-character cursor at 2000.
3. If supported safely by this client, test one invalid/tampered cursor and
   one changed-budget replay. Record safe categories/codes; do not disclose
   token contents. You cannot independently prove cross-principal replay
   denial from a single principal; mark that security property covered only
   by separate local evidence unless a second owner-approved credential is
   supplied. Do not invent one.

Recheck scoped get_capabilities for the authorized notebook. Record the
lifecycle, configured/registered/ready/active/exposed/scope availability
and reason of exhaustive retrieval, structured retrieval, document
delivery, exact retrieval, asset delivery, FinalQA V2, multimodal
retrieval and OCR generation. Visibility is not availability. OCR
generation may be profile_not_configured while bounded search of already
persisted ocr_text is truthfully searched/empty. Record representation
state and examined count; do not activate OCR or invent matches.

For structured retrieval, compare the notebook-level scope response with
query_structured only for a genuinely discovered authorized exact document
version. Notebook-level readiness does not promise a projection for every
version. An absent version projection should return safe
capability_unavailable, not a fabricated empty success. Do not create a
production projection. Operator-side read-only discovery found a candidate
existing READY projection in source
42a948fa-023f-48af-b660-85a0d70b349e, document
092b9610-05e6-54f4-bb3f-ea8b4544a25f, exact version
2190addb-b826-586f-b2be-65962e520068. These IDs are *not* live client
evidence: use them only if current connected-tool results establish their
authorization and ancestry. If confirmed, perform bounded describe, query
with page_size:1 and unchanged-cursor continuation, and a type-correct
zero-match filter. Record returned dataset identity, row count, completeness,
cursor state and request IDs without printing private row values. If this
scope is not visible to your principal, mark the positive path unverified.
Invoke delivery or FinalQA only if the actual
scope-specific capability and persisted representation/dependencies make
a bounded authorized call possible. FinalQA may be registered/buildable
yet unavailable because multimodal retrieval lacks an active generation;
do not bypass that gate or retry an expensive request automatically.

Classify broad document/exact/asset service unregistration against the
actual per-operation tool contract: a visible tool name does not promise
persisted original bytes or a registered broad capability family. Do not
turn truthful unavailability into an invented success. Conversely, the
complete Phase 8.8 acceptance matrix requires certified FinalQA success
through the actual tunnel; a buildable-but-not-ready FinalQA is not that
success. State explicitly whether each unmet gate belongs to local Stage 6,
Module 8.8.9 four-transport certification, or full Phase 8.8 acceptance.

Where the actual authorized scope permits, record source metadata and
top-level/nested partition parity, V1/V2 route separation, provenance,
safe malformed-input behavior and evaluation isolation. Without an
owner-supplied negative fixture or second principal, mark cross-user ACL
tests unverified. Public MCP cannot independently prove that evaluation
databases were never opened, protected files were unchanged, or HTTP,
stdio and SSE match the tunnel. A prior signed startup-convergence
artifact establishes its own configuration-bound result, not fresh
behavioral parity for the new actor-bound cursor code.

Product Stage 7 is separate future Ecosystem and Extensibility work:
Plugin SDK, official EPUB/browser-history plugins, published OpenAPI,
MCP specification-suite certification and Open WebUI integration. Report
those as not implemented or not externally verifiable unless actual
independent evidence proves otherwise. Do not infer Stage 7 acceptance
from Stage 6 MCP calls.

Return an evidence matrix with actual calls/arguments, UTC times, safe
request IDs, response identities, pagination outcomes, errors, limitations
and pass/fail/unverified results. Separate (1) fresh external MCP facts,
(2) operator-side source/process attestations, (3) local forensic evidence,
(4) existing transport certification, and (5) unverified internal gates.
Give STAGE_6_EXTERNAL_VERIFIED only if every applicable *external* gate
passes and explicitly list the remaining internal/four-transport gates;
otherwise give STAGE_6_EXTERNAL_BLOCKED with exact blockers. Give a
separate honest Product Stage 7 status; do not award its acceptance from
this Stage 6 retest.
```
