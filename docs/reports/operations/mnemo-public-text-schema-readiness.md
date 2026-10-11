# Public ordered-text schema readiness — 2026-09-28

PUBLIC ISOLATED SCHEMA VERIFIED; PRODUCTION CHATGPT REFRESH/CONNECTION PENDING.

## Proven boundary, not an invented cache diagnosis

Canonical [tool declarations](../../../mnemo-server/mnemo_server/mcp/tools.py),
handler validation and governance contract already permit original|blocks|text.
The deployed production editable module resolves to the current workspace and
the product-content digest remains cdf4bc9b3140d5b0b8063766e7b0bdd7f4154df9190b42aa17fec77b63d2313d.
Fresh certified stdio and authenticated loopback SSE discovery advertise all3.
The owner-reported external client still advertised only blocks|original.

Fresh tools/list over the NEW authenticated public HTTPS fixture endpoint also
advertises blocks|text|original, and actual text calls reconstructed the expected
digest. This eliminates implementation-side uncertainty for that endpoint.
It does NOT establish fresh tools/list on the existing OpenAI production tunnel:
this environment has a runtime control-plane key, not an authenticated ChatGPT
client or general Responses/admin key. Tunnel metadata and local process/module
inspection are not external tool discovery. A stale client definition, unrefreshed
connection or incorrect client connection remains a bounded diagnosis; the exact
proprietary connector cache mechanism was not independently inspected.

No gratuitous production enum change, schema-validation bypass or new production
endpoint was introduced. The fixture reuses canonical input schemas and delivery
output DTOs; its explicitly different capability schema avoids false production
identity/certification claims. Public authenticated tests verify native schema
validation, not only internal Python acceptance.

| Layer | Current evidence |
| --- | --- |
| Canonical input schema | enum blocks,text,original |
| Server delivery request/adapter | text accepted; ordered persisted IR traversal |
| Certified stdio/SSE discovery | fresh all3 modes; all14 tools exercised |
| Isolated public streamable MCP | fresh all3 modes; four complete traversals passed |
| Existing public production tunnel discovery | fresh owner-side verification required |
| Owner's ChatGPT schema | last supplied observation two modes; no refreshed observation yet |

Mode original returns original bytes; blocks returns typed persisted blocks with
supported positional selectors; text supports full or omitted selector and
rendered persisted IR items. Text is not query-dependent chunk enumeration or
on-demand parsing of an immutable production file. Reconstruct payload.text plus
payload.separator_after exactly. Mode, selector, scope, exact requested limits,
actor and snapshot are cursor-bound. Never change arguments mid-traversal.

## Public verification evidence

Endpoint https://rotary-tobago-michelle-filter.trycloudflare.com/mcp/.
Final fresh public run 2026-09-28T14:45:22.458752Z–14:45:41.291534Z:
schema enum blocks,text,original; two text traversals (12/4 pages), exact UTF-8
SHA-25670f933e57255937afc39612ac54a311f7653ab9c1c7d91c20106a4db12a83493.
Missing/wrong authentication401. No schema refresh inside the owner's ChatGPT
session was performed or claimed. Public SSE did not pass; use the tested
streamable endpoint, not its /sse route through the temporary HTTPS companion.

## Exact owner action

For an existing developer-mode connection, open ChatGPT Settings → Plugins →
the Mnemo connection → Refresh; confirm the updated metadata, then start a NEW
conversation. This workflow is documented in the official
[ChatGPT connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).
If the connection is managed differently, use that integration's supported
refresh/reconnect control; do not revoke or rotate credentials to refresh schemas.
Confirm the actual visible mode enum has all3 values before testing text.
For a published connection, follow its supported metadata update/review path
rather than assuming the developer-mode refresh control is available.

Create a separately named isolated fixture connection, NOT a replacement
production connection. If the connector can securely configure an existing
owner Bearer header, use the tested /mcp/ URL and enter it only in the private
credential UI. Do not paste keys into conversation/report/URL. This report does
not assert that ChatGPT's connector supports arbitrary API-key headers.
If it does not, an owner-admin must create a separately scoped temporary Secure
MCP Tunnel and runtime connection using the prepared test template/stdio launcher.
That administrative credential and connection are not available here. No anonymous
proxy, broad ACL, production tunnel substitution or credential rotation is proposed.

Then use the [complete external handoff](mnemo-ordered-text-external-handoff.md)
before the fixture expires at2026-09-30T12:31:23.150652Z. The source fixture
currently has no production parsed-representation counterpart, intentionally.
