# Direct image integrity — 2026-09-28

Final post-restart stdio and authenticated loopback SSE repeated all four byte comparisons successfully, including exact JPEG hash and 3576×2512 decode. The current [transfer manifest](mnemo-resource-transfer-manifest.json) records the fresh stdio ranges; supplemental SSE received artifacts are retained at C:/Users/athar/AppData/Local/Temp/mnemo-reconstruction-g0y3ty7d/transfer-manifest.json. External connector materialization remains pending.

Authorized occurrence7c31fd63-a975-51f3-bc27-0a6505649ffe in document135b4fd5-15cd-5a22-89db-096dcc9b55bc/versiond49eb763-3bf3-54d1-aec4-bfd66ca43fe8/notebookdf9c20cf-85fe-529c-902e-2e9e68193fbe.

Fresh real stdio and authenticated loopback SSE retrieved actual original bytes, not previews:
- one-call ImageContent,704901 bytes;
- one-call negotiated EmbeddedResource blob,704901 bytes;
- eleven65536-byte-ceiling pages,704901 reconstructed bytes;
- original JPEG extracted from reconstructed PDF page1.
All four byte sequences match exactly; SHA256 cab6378eeb056237af3b785d9421e8fb0c6c889b730b37e719dcea8247acb19a; Pillow full decode JPEG3576×2512. PyMuPDF validates PDF six pages and extraction. The PDF skill also prompted a read-only render/visual check of the reconstructed first page; no PDF was authored or altered.

D-03 does not establish server corruption: the earlier corrupt mounted attachment lacks a demonstrated association with the fresh response. Server/MCP bytes pass these local checks. External attachment handling remains independently unverified. Range-qualified resource URIs and explicit native-blob negotiation provide an additive compatible byte-access option without claiming control over ChatGPT.

Persisted image analysis: complete OCR derivation2b206dff-9a47-563c-b0f8-6a50f7715a28/generationf2a394f0-57c1-52eb-a56f-f360d11cdcf7 (one region,2875 payload bytes) and Vision derivationee4dbd89-ba0b-54bc-9618-786cd3d3793d/generationc5e11f9d-54f0-5f00-98fb-1f38b005e872 (five observations,2835 payload bytes). Actual payloads saved privately alongside the [transfer manifest](mnemo-resource-transfer-manifest.json); manifest records provenance/counts, not private analysis prose. Fresh request ed3904ad-d73e-4535-92b7-fe86eef754aa.

Large-record behavior remains explicitly bounded:256 OCR regions/256 Vision observations and response byte ceiling. Count truncation reports bounded and analysis_item_bounds_applied; byte overflow raises delivery limit. No analysis-content cursor is promised. This satisfies the specified explicit-limit alternative, not unlimited analysis delivery.
