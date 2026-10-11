# Multipart binary reconstruction — 2026-09-28

Local real-MCP evidence, not external ChatGPT connector certification.

Fresh post-forward-restart reconstruction also passed: real stdio 10:07:32.145990–10:08:24.509489 UTC (the indexed transfer manifest now contains this run); authenticated loopback SSE 10:13:51.475080–10:13:54 UTC, raw manifest C:/Users/athar/AppData/Local/Temp/mnemo-reconstruction-g0y3ty7d/transfer-manifest.json. Both independently materialized every range and reproduced the exact PDF/JPEG hashes. These later witnesses supplement, not erase, the earlier run record below.

Runner: `uv run --no-sync python scripts/verify_resource_reconstruction.py --model-cache D:\Mnemo\phase8.5.11-models\huggingface\hub`.
Repeat with `--sse-url http://127.0.0.1:8059/sse` against the isolated authenticated certified SSE worker.

The runner materializes each MCP native base64 payload to a separate temporary file, reopens every file, concatenates actual received bytes, checks every exclusive range boundary and stable resource identity/hash/snapshot, and compares against a fresh one-call result. Neither storage-only reads nor metadata-only success substitute for these assertions.

PDF:3821824 bytes; original MIME application/pdf; SHA256 eb4fe330163f7d89535ca48f792204a16da042bb2e4895a6030102df20a63984; six pages; valid PDF signature/decoding.524288-byte ceiling yields eight calls, seven524288-byte ranges and final151808 bytes, contiguous [0,3821824). One-call and multipart identical.

JPEG:704901 bytes;65536-byte ceiling yields eleven calls, ten65536-byte ranges and final49541 bytes. Multipart, complete ImageContent, negotiated complete native blob and PDF-extracted JPEG identical.

Evidence: [full transfer manifest](mnemo-resource-transfer-manifest.json) contains each actual range, received length, per-range hash, fresh temporary artifact path, provenance and snapshot. Stdio09:46:21.118913–09:46:57.895949Z. Final-source SSE manifest `C:\Users\athar\AppData\Local\Temp\mnemo-reconstruction-0qom3o8x\transfer-manifest.json`; ended09:48:54.281498Z. Earlier successful probes are not substituted for these final-source runs.

Public additive metadata:rangeStart,rangeEnd (exclusive),rangeEndExclusive=true,returnedBytes,totalBytes,contentHash,snapshotIdentity,originalMediaType,canonical ancestry,nextCursor,completeness. Range-specific opaque URI avoids reusing one attachment identity across distinct pages; it is not a download URL. Complete images may negotiate `binary_format:"resource"`; default ImageContent remains compatible. Partial images remain binary/octet-stream, never independently decodable image promises.

Request-local actor binding and exact requested byte/item limits now protect delivery cursors in HTTP/MCP; same-effective-limit substitutions are rejected. Old unbound public cursors require fresh traversal. Native resource encoding is not replaced with JSON base64 and no endpoint/tool was added.

Final external gate: owner must materialize these fresh actual response payloads through connected ChatGPT and reproduce the hashes. This task has no connected Mnemo MCP client and cannot certify the proprietary connector. See [handoff](mnemo-external-resource-reconstruction-prompt.md).
