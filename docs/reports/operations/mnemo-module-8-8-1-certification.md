# Module 8.8.1 — certified runtime convergence

**Result:** `MODULE_8_8_1_CERTIFIED` on 2026-09-24. This certifies one server-owned production composition across HTTP, MCP stdio, MCP SSE, and the existing external Mnemo tunnel. It does not certify the readiness of every advertised MCP capability, all of Phase 8.8, Module 8.8.2, or Phase 9.

The [independent forensic audit](mnemo-module-8-8-1-forensic-audit.md) reopened
the signed chain and four startup records, checked the raw rehearsal inputs,
and records the external request-to-startup correlation limitation. This report
remains the certification event record; the audit is its later read-only review.

## Authority and signed chain

- Active credential generation: `fc85192e-f672-4cc0-9539-b4b063bb8f41`; exactly one registry generation is ACTIVE. The original unavailable signing credential was not reused. Actual new secret material is held in the Windows-backed store, not in this report or the registry metadata.
- Signed activation SHA-256: `c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525`.
- Signed pre-certification four-transport convergence SHA-256: `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23`.
- Fresh generation-bound WP-17 rehearsal: `scratch/phase8_5_full_multilingual_v2/operational/wp17_rehearsal/fc85192e-f672-4cc0-9539-b4b063bb8f41/8d8269fa-c52d-460d-b521-741ee3ee66b1/`; independently verified. Production-parity scoring completed on 18 queries and exceeded all five governed thresholds without changing the corpus, model revisions, or criteria.
- New `/3` pre-activation certificate SHA-256: `1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a`.
- New generation-bound final evidence SHA-256: `0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c`.
- The complete signed rehearsal, certificate, and final-evidence chain was reopened and independently verified after promotion. Certified runtime binding admitted the active generation only after that chain verified.

The historical activation (`b4aa8088c143418432bc228f7130d413c62908e706aa109f5ff75d3100b3fb09`), certificate (`777c1a4f1d352a9ba219293b6afbb230778b97801b764c10fccd1afe5993fb15`), and final evidence (`b37f8c1667581d5bae97436aa8527a92b255544f6c7b644c67472dc2627df03d`) retain their original hashes. No cryptographic continuity with the lost secret is asserted.

## Post-promotion runtime observations

The certified server-owned binding ID is `56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d`. Its signed transport observations are in `scratch/phase8_8_1_runtime_convergence/`:

| Transport | Actual execution | Signed binding |
|---|---|---|
| HTTP | Certified app startup; authenticated `/v2/capabilities` returned 200 and unauthenticated request returned 401 | Match |
| MCP stdio | Real client initialized; 14 certified tools listed; `get_capabilities` succeeded | Match |
| MCP SSE | Real loopback SSE client initialized; 14 certified tools listed; `get_capabilities` succeeded | Match |
| External tunnel | Existing Mnemo tunnel uses `start_certified_mcp_tunnel.bat`; ChatGPT's connected Mnemo client called `get_capabilities` and `list_notebooks` successfully | Match |

The external startup observation was signed at 2026-09-24 15:47:35 UTC by PID 45520, a live `certified-tunnel-stdio` child of the certified launcher under the existing Mnemo tunnel process. ChatGPT's real calls followed at 16:18:30–16:18:50 UTC. The server-side startup record is not a per-request signature: the client report establishes the calls, while the process ancestry and signed startup record establish the runtime serving that tunnel. The client returned request ID `fecb2129-5989-4fc7-a328-28d92ca317f7` for `list_notebooks`; that ID is not present in the startup record and is not claimed to be cryptographically bound to it.

The governed verifier reloaded and verified all four HMAC-signed startup records against the active server credential, required exact equality of their complete binding payloads, and returned `PASS`. Machine-readable derived comparison: `scratch/phase8_8_1_runtime_convergence/convergence.json`, SHA-256 `57f6aa5ec5a92916d38a09600793068924a6967de53dbfb3490145cd47dd53a8`. The comparison JSON itself is not separately signed; its result is established by reverifying the four embedded signed observations. A separate **local** test of the batch launcher was quarantined as `local-certified-launcher-diagnostic.json`; it was not used as an external observation.

ChatGPT saw the certified 14-tool surface, not `observe_runtime`, and completed one authorized read-only notebook discovery call. Its `get_capabilities` snapshot describes individual features as candidate, declared, or unavailable, and reports no mutable workspace. Those are truthful capability states; this certificate does not upgrade them or authorize implementation of later Phase 8.8 modules.

## Protected state and validation

- Production DB: SHA-256 `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`, 189,804,544 bytes, mtime `2026-09-01T11:09:20.1047581Z`.
- WP16 DB: SHA-256 `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d`, 37,195,776 bytes, mtime `2026-08-29T13:37:31.2308106Z`.
- Both retain their certified hash, size, and timestamp and have no WAL, SHM, or journal sidecars at the protected-state checkpoint. Earlier orphaned sidecars were quarantined recoverably after exclusive-handle checks; no protected DB was written to clear them.
- CI-safe pytest: 2,493 passed, 18 skipped; repository-wide coverage 90.01% (required ≥90%). Ruff check and format, strict mypy, compileall, `uv lock --check`, and `git diff --check` passed.
- Git HEAD: `c76254271d895fd2680e047d9b39cd167940c9f4`. The existing dirty working tree was preserved; no commit, push, reset, clean, or stash was performed.

Module 8.8.2 was not started. Phase 8.8 remains **IN PROGRESS / NOT VERIFIED**.
