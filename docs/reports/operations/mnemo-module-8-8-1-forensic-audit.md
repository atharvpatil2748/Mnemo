# Module 8.8.1 — independent forensic audit and documentation closure

**Audit date:** 2026-09-24. **Disposition:** Module 8.8.1 certified for
server-owned runtime identity and four-transport startup convergence, with the
external-request provenance limitation below. Phase 8.8 remains **in progress / not
verified**; Module 8.8.2 and Phase 9 have not started.

## Authority and scope

The [current roadmap](../../architecture/current/mnemo_engineering_roadmap.md)
defines 8.8.1a–d in dependency order: one certified production startup binding;
reject configuration forks before tool exposure; bind the existing tunnel to
server-owned startup after (a); capture HTTP/stdio/SSE/tunnel effective identity
and configuration digest after (b). [ADR-0076](../../adr/active/ADR-0076-project-owner-engineering-certification-standard.md)
governs the frozen 44-document corpus, BGE identities, evaluation floors and
WP-17 evidence. [ADR-0078](../../adr/active/ADR-0078-generation-aware-production-credential-lifecycle.md)
governs the later re-key required after loss of the original signing credential;
[ADR-0077](../../adr/active/ADR-0077-governed-mutable-workspace-boundary.md)
keeps mutable workspace storage separately governed. The historical `/1`
certificate was not promoted into the new `/3` authority.

The generation-aware credential registry, restricted pre-certification observer,
isolated WP-17 rehearsal, `/3` pre-activation certificate, final evidence and
atomic promotion are implementation prerequisites for this re-keyed production
instance, not new claims that all Phase 8.8 tool behavior is certified.

| Requirement / prerequisite | Executable implementation and tests | Observed evidence | Audit disposition |
|---|---|---|---|
| 8.8.1a: one server-owned production binding | `ServerConfig`, `resolve_certified_production_binding`, HTTP `app.py`/`certified_http.py`, MCP `cli.py`/`server.py`; `test_production_runtime_binding.py`, `test_generation_runtime_binding.py` | Active registry and full signed chain resolve; certified HTTP, stdio, SSE and tunnel startup records contain one binding ID | **VERIFIED** |
| 8.8.1b: reject forks before exposure | `reject_uncertified_corpus_startup`, manifest/profile/DB/activation/certificate/final checks in `production_runtime_binding.py`; generation and transition negative tests | Binding verifier rejects wrong or incomplete identity; no client DB/model/registry selector in governed MCP CLI | **VERIFIED** (negative behavior tested; no claim every future input is proved safe) |
| 8.8.1c: existing tunnel uses server-owned startup | `scripts/start_certified_mcp_tunnel.bat` → `mnemo_server.mcp.cli certified-tunnel-stdio`; MCP server binds before tool registration; launcher/tool tests | Live Mnemo tunnel process (PID 47184) → certified launcher (PID 45352) → certified stdio (PIDs 18816, 45520); separate CodexPro tunnel untouched; external ChatGPT read-only calls succeeded | **VERIFIED WITH DOCUMENTED LIMITATION**: external request is correlated to the live process operationally, not individually signed |
| 8.8.1d: exact four-transport runtime identity | `record_certified_transport_startup` and `collect_certified_convergence`; `test_production_runtime_binding.py` | Four HMAC-signed startup records independently reverified; complete binding payloads equal; governed result `PASS` | **VERIFIED** for startup semantic identity, not all-tool behavioral parity |
| Re-key and observation admission | `production_credentials.py`, `production_authority_transition.py`, `pre_certification_observation.py`, generation/observation tests | One active generation; historical artifacts retained; earlier four signed pre-certification observations and convergence reverified | **VERIFIED** |
| Fresh WP-17 and pre-activation authorization | `scratch/run_wp17_generation_rehearsal.py`, `v2_certification.py`, `production_generation_evidence.py`; generation certificate/evidence tests | Five fresh signed records, raw evaluation inputs rehashed, `/3` certificate and final evidence independently verified | **VERIFIED**; isolated rehearsal final state did not assert global `ACTIVE`/`EXPOSED` |
| Protected corpus and later capability contracts | ADR-0076/0077 and roadmap Phase 8.8 matrix | Both protected DBs match certified hash, size and mtime; no sidecars at audit checkpoint | Corpus preservation **VERIFIED**; 8.8.2–8.8.14d behavior **OUT OF MODULE SCOPE** |

## Verified generation and evidence graph

The manifest's sole configuration authority is the server-owned credential
registry. Its one record and active pointer both identify
`fc85192e-f672-4cc0-9539-b4b063bb8f41` as `ACTIVE`; secret material resides
only in the Windows-backed store. The signed chain was independently reopened
with the governed `complete_wp17_generation_certification.py verify` operation,
using the actual registry-selected secret references:

| Artifact | Independently recomputed SHA-256 |
|---|---|
| New signed activation | `c17a7f5531cc75795fb63c6f53682d30eb6ed831127db95038d3d1741cd25525` |
| Signed pre-certification four-transport convergence | `b5ccccb9787773ef10f5a6364bbc80ed98324640ea5438da604ebfaf2b7c2b23` |
| Fresh WP-17 evaluation | `4d53676f840e0fe86f314e35647432e07c85d7eb21e86e80c687c1d45023d13a` |
| Fresh WP-17 activation | `e5b42539415ff6b9eafbd064f8122d21d605fc9f104a635dd0a35f5a0aa3bf57` |
| Fresh WP-17 security | `04d6536b487aff29b80fa081f6706d7b2b3a078cdeb2ef230db8e589d545c2d7` |
| Fresh WP-17 rollback/reactivation | `4882bf642e5950080b0c53b343748899c0ee6dfb46d909c7f34782db2f52b3d2` |
| Fresh WP-17 rehearsal final BGE state | `485fcf5d4cd61474c892390a74cf2d6a23d46658e599083611d473bead8acbe4` |
| `/3` pre-activation certificate | `1a69e95796b98abcc1f4f6484692481058bff776b454a14e3a0b35d86f16312a` |
| Generation-bound final evidence | `0255160992fc1ed2fdc5b5c6bfb55bb442b55018655f511274d698569a06230c` |
| Post-promotion convergence JSON | `57f6aa5ec5a92916d38a09600793068924a6967de53dbfb3490145cd47dd53a8` |

The accepted rehearsal run is
`scratch/phase8_5_full_multilingual_v2/operational/wp17_rehearsal/fc85192e-f672-4cc0-9539-b4b063bb8f41/8d8269fa-c52d-460d-b521-741ee3ee66b1/`.
Its raw `evaluation.json`, `checkpoint.json`, `mapping.json`, and
`per-query.json` recomputed hashes match the references in signed
`wp17-evaluation.json`. The real CUDA evaluation completed 18 queries against
the governed 50-candidate pool: R@1 0.8333 ≥ 0.75; R@5/R@10 0.8889 ≥ 0.85;
MRR 0.8474 ≥ 0.78; nDCG@10 0.8548 ≥ 0.80. The security evidence records
authorized 200, anonymous/invalid-auth 401, chat/mutation 404 and only
`observe_runtime` during rehearsal. The rollback record binds an isolated
activation, and the final-state record contains actual CUDA BGE reranker scores
at revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` with CPU fallback
false. These are separate from global production activation. Earlier blocked
runs were not substituted for this accepted run.

The certificate `/3` has `PRE_ACTIVATION_CERTIFIED` and lifecycle `ACTIVE=false`,
`EXPOSED=false`; the actual registry was promoted only after the signed final
evidence verified. Certified startup subsequently required both the complete
chain and the active pointer. Historical signed activation, certificate and
final evidence retain SHA-256 `b4aa8088c143418432bc228f7130d413c62908e706aa109f5ff75d3100b3fb09`,
`777c1a4f1d352a9ba219293b6afbb230778b97801b764c10fccd1afe5993fb15`,
and `b37f8c1667581d5bae97436aa8527a92b255544f6c7b644c67472dc2627df03d`.
No cryptographic continuity with the lost original secret is claimed.

## Runtime and external-client evidence

The governed read-only `collect_certified_convergence` operation reloaded
HTTP, `mcp_stdio`, `mcp_sse`, and `external_tunnel` startup records, verified
each HMAC with the active server-owned secret, and compared their **entire**
binding payloads. Result: `PASS`; shared binding ID
`56b64e879eb64a251a45ab9beabaa5d9dfd8afee760bd5b8f18383a6df510a1d`.
This ID is an HMAC-derived semantic **runtime binding identity**, not a file
hash or a digest of the convergence JSON. Its payload binds generation,
configuration, protected database, model profile and exact revisions,
reranker mode, activation, operational store and composition.
The signed records bind configuration digest
`1ae97d46b66cb37a00bbd6249c0c83b9e2752be7bc8ebbe84fdc80467fe31af6`,
database identity `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`,
embedding `BAAI/bge-m3` revision
`5617a9f61b028005a4858fdac845db406aefb181`, and reranker
`BAAI/bge-reranker-v2-m3` revision
`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` in `BGE_V2_M3` mode.
The convergence JSON is a derived comparison containing the four signed
records; it has no separate signature of its own. Its PASS must be re-established
by the governed verifier, not trusted merely because the JSON says PASS.

The external startup record was signed at 2026-09-24 15:47:35 UTC by certified
stdio PID 45520 in the live Mnemo tunnel ancestry. The user-supplied ChatGPT
tool report records `get_capabilities` success at 16:18:30–16:18:33 UTC and
`list_notebooks` success at 16:18:48–16:18:50 UTC, with request ID
`fecb2129-5989-4fc7-a328-28d92ca317f7` and one authorized 44-source
evaluation notebook. ChatGPT saw the 14 production tools rather than the
restricted observer. These **request** results were not independently
cryptographically attested: the request ID is absent from the signed startup
record. Therefore the signed proof is four-way **startup identity** convergence;
the external calls and process ancestry are separate operational corroboration.
The current 8.8.1 contract does not require signed per-request provenance or
all-tool behavior, which remain later Phase 8.8 concerns.

`get_capabilities` truthfully returned a candidate model profile and unavailable
individual capabilities. The absent mutable-workspace configuration enforces
ADR-0077 read-only fallback; it does not revoke the scoped runtime binding.
The local certified launcher diagnostic was not counted as an external call.

## Protected state, validation and operational boundary

| Protected database | SHA-256 | Size | Certified mtime | Audit sidecars |
|---|---|---:|---|---|
| Production | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 189,804,544 B | `2026-09-01T11:09:20.1047581Z` | None |
| WP16 | `18835883dc3a01b588e4c43f44fba1156941d0807d7c08c2a41fd11a802bf55d` | 37,195,776 B | `2026-08-29T13:37:31.2308106Z` | None |

The certified production launcher is `scripts/start_certified_mcp_tunnel.bat`.
Do not start it in a second competing tunnel or use the historical V1 launcher
as production authority. Read-only operational checks should inspect the
manifest's registry reference, its exactly one `ACTIVE` pointer, and the
generation's artifact hashes; use the governed
`complete_wp17_generation_certification.py verify <accepted-run-directory>`
chain verifier only when its existing certification plan is present. Use
`collect_certified_convergence` with the resolved `ServerConfig` and expected
binding ID to reverify the four startup records **without publishing replacement
evidence**. Missing secrets, wrong generation, invalid signatures or divergent
transport identity must fail closed; do not regenerate or relabel evidence to
force PASS. Rollback to the historical cryptographic generation is unavailable
because its signing credential is lost; do not switch the tunnel back and call
that a certified recovery.

The preceding certification report records the full CI-safe run as 2,493 passed,
18 skipped, 90.01% repository-wide coverage, with Ruff, strict mypy,
compileall, lockfile and diff checks passing. This documentation-only audit
did not rerun that full suite. Focused local checks passed (118 tests plus
13 tests requiring their plugin fixture loaded separately); the first combined
invocation yielded seven fixture-collection errors and was corrected by running
that group separately. No production code, manifest, registry, tunnel, signed
artifact, database, model or corpus was changed for this audit.

Module 8.8.2 immutable-schema readers, 8.8.3 all-remote-tool authorization,
8.8.4–8.8.8 tool contracts, 8.8.9 behavioral/long-running parity, 8.8.12 image
discovery, 8.8.13 end-to-end provenance, and 8.8.14d phase-wide readiness remain
open. The 14 registered tools are not 14 individually certified capabilities.
Phase 8.8 cannot issue Phase 9 GO on this scoped result alone.
