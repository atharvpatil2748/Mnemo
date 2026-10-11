# Public MCP schema verification — 2026-09-28

SERVER_SCHEMA_VERIFIED_LOCALLY; EXTERNAL_CLIENT_REFRESH_PENDING

## Root-cause boundary

The initial repository tool declaration already advertised mode enum ["blocks","text","original"]; handler validation already accepted text and persisted-block rendering existed. The prior external client's two-value enum therefore did not describe the checked-out canonical declaration. Fresh real tools/list from final certified stdio and authenticated SSE exposes all three values. The exact external connector cache/discovery mechanism is outside this environment, so it is a bounded diagnosis of schema mismatch, not a proven defect inside ChatGPT.

The deployment uses .venv editable workspace imports and certified-tunnel-stdio under the unchanged launcher. Final content digest cdf4bc9b3140d5b0b8063766e7b0bdd7f4154df9190b42aa17fec77b63d2313d. Final runtime tree33680→22920→79880→54892 admitted the existing main channel. Operator import path evidence and fresh local tools/list are not independently exposed source revision evidence.

## Implementation-controlled corrections

[tools.py](../../../mnemo-server/mnemo_server/mcp/tools.py) makes text mode guidance explicit. [contracts.py](../../../mnemo-server/mnemo_server/mcp/contracts.py) describes selectors, lossiness, exact separators, and additive structured resource properties. The [governance machine contract](../../governance/contracts/phase8_5_mcp_contracts.json) now lists modes, selectors, reconstruction rules and binary metadata. Capability matrix includes ordered text without implying every version has a parsed representation.

| Mode | Supported public use |
| --- | --- |
| original | Original bytes; bounded max_bytes and unchanged continuation. Binary range metadata is end-exclusive. |
| blocks | Full ordered persisted blocks or accepted positional structural selectors (where supported by persisted document type). |
| text | Full or omitted selector only; rendered ordered persisted blocks with payload.text and payload.separator_after. Not query-dependent chunk stitching. |

Default blocks and earlier original behavior remain compatible. No new required argument. Missing exact-version parsed representation returns delivery.representation_unavailable. An unchanged text invocation reaching that error proves server acceptance, not positive content availability.

## Evidence

New test_public_document_schema_advertises_ordered_text asserts enum all3 and public binary outputSchema. The reconstruction probe captures actual get_document_input_schema and checks enum all3 for final certified stdio/SSE; raw schemas are in the [transfer evidence](mnemo-ordered-text-binary-transfer-manifest.json). Four mixed-content real transport tests exercise blocks and text positively on older/newer disposable scopes. Final full suite2,790 passes.

There is no separate generated schema source that needs an invented new enum: canonical tool registration applies retained guidance to the same declaration used by stdio/SSE. External connection refresh remains an owner-side action; do not claim external text availability until a fresh actual tool call succeeds.

## Owner action

Refresh/reconnect the existing Mnemo integration and create a NEW connected conversation so client tool definitions are fetched again. Verify the client-visible get_document schema explicitly permits original|blocks|text. If still two values, preserve that exact client-side rejection and discovery time; inspect the refreshed integration rather than changing secure server execution. No credential rotation or new endpoint is required for schema refresh.

Positive text needs the separately approved isolated fixture described in the [remediation plan](mnemo-ordered-text-delivery-remediation.md). Production missing representation is not fixed by refreshing a schema.
