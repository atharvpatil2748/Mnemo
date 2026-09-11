# Mnemo MCP Failure and Contract Audit

**Status:** `COMPLETE_READ_ONLY_WITH_RUNTIME_CONFIGURATION_DRIFT`  
**Date:** 2026-09-08  
**Scope:** Decision-grade pre-Phase-8.8 audit only. No implementation, configuration, database, model, registry, activation, certification, or tunnel changes were made.

## 1. Executive Summary

The external client's results were real observations, but they did not all describe the same architecture that Mnemo certified. There are currently two materially different MCP compositions:

1. The certified composition is defined by `mnemo.toml` and `config/production/full_multilingual_v2.production.json`. It binds the immutable 44-document store, governed BGE-M3/BGE-v2-m3 path, authenticated V2 authorization, durable activation, and separate FinalQA operational SQLite.
2. The live tunnel invokes `C:/Tools/start-mnemo.bat`. That launcher pins `scratch/phase8_5_11/eval-20260825-02/mnemo.db`, `ollama/nomic-embed-text` (768 dimensions), and `cross-encoder/ms-marco-MiniLM-L6-v2`. It does not enable production mode, Full Multilingual V2, SSE/API authentication, or the server-owned stdio principal.

This **runtime configuration fork is the primary Phase 8.8 defect**. It explains why a client can see 14 current tool definitions while receiving historical V1 capabilities and behavior.

The reported `sq-2:sparse` and `canonical_text:source_failure:OperationalError` also expose a genuine compatibility defect. The immutable certified corpus predates additive `chunks.position_page_start` and `chunks.position_page_end` columns. FTS5 successfully finds rows, but the generic `SQLiteStore.get_chunk()` reader then selects those absent columns and raises `sqlite3.OperationalError: no such column: position_page_start`. The dedicated V2 read-only store already contains a compatibility reader, but the retained V1 sparse, canonical-text, and delivery paths do not use it.

The external FinalQA `mcp_network_error` is not a returned Mnemo tool error and does not prove a FinalQA service failure. Real retained HTTP, MCP stdio, and MCP SSE FinalQA executions all passed. However, the tunnel launcher does not compose certified FinalQA at all. Phase 8.8 must converge the launcher first and then repeat the long-running tunneled call with correlated server and client timeout evidence.

The filename complaint is valid. Stable identities are generally preserved, and `get_notebook_summary` provides document titles, but source-oriented responses lack one consistent authorized `source_metadata` envelope. The correct change is additive: retain stable source/document/version/chunk/occurrence/asset IDs and attach human-readable display metadata. A filename must never become authorization or canonical identity.

## 2. Actual MCP Tool Inventory

`tools/list` returned exactly 14 tools from `mnemo_server.mcp.tools.get_mcp_tools()`:

| Tool | Contract/path | Authorization in handler | Audit result |
|---|---|---|---|
| `query_notebook` | Retained V1 query + optional synthesis | No central authorization call | Store compatibility defect in certified topology; passes current historical tunnel store |
| `search_all_notebooks` | Retained V1 search | No central authorization call | Same defect; passes current tunnel store |
| `list_notebooks` | Direct storage inventory | No central authorization call | Functional, authorization design gap for remote tunnel |
| `get_notebook_summary` | Direct source/insight inventory | Existence only | Pass; empty summary is truthful |
| `get_source_insights` | Direct source/insight inventory | Existence only | Pass; empty insights are truthful |
| `get_timeline` | Direct source/note/session inventory | Existence only | Pass |
| `get_document` | Shared delivery service | Principal-aware scope resolution | Original mode passes; blocks mode has certified-schema defect |
| `get_document_chunk` | Shared exact delivery | Principal-aware scope resolution | Valid ID fails on certified schema; invalid external ID was client error |
| `get_asset` | Shared asset delivery | Authorized delivery boundary | Pass |
| `get_image_analysis` | Existing derivation delivery | Authorized delivery boundary | Pass for known ready derivations; unavailable selector is expected |
| `search_evidence` | V2 application contract | Central authorization in production | Canonical source has schema defect; governed multilingual V2 evidence previously passes |
| `query_structured` | Typed V2 structured service | Central authorization in production | Registered; availability is store/version-specific |
| `run_final_qa_v2` | V2 FinalQA + operational store | Central/V2 authorization in production | Certified service passes; current tunnel does not compose it |
| `get_capabilities` | Phase85 runtime snapshot | Metadata, not authorization | Functional; process-local and not scope-qualified |

Registration is unconditional (`tools.py` builds the ten retained definitions plus four additive definitions). Registration therefore means only that a schema and dispatcher branch exist. It does not prove configured, ready, active, exposed, or certified.

The full input schemas remain in `scratch/mnemo-mcp-tool-inventory.json`; the focused status matrix is `scratch/mnemo-mcp-tool-status-matrix.json`.

## 3. External Observation vs Independent Reproduction

Two read-only real stdio sessions were used:

- A default process resolving the current certified database from `mnemo.toml` reproduced both V1 failures and the canonical-text failed representation report.
- A process launched through the exact command configured in `C:/Users/athar/AppData/Roaming/tunnel-client/mnemo.yaml` (`cmd /d /c C:/Tools/start-mnemo.bat`) returned successful V1 `search_all_notebooks`, successful V1 `query_notebook`, and successful canonical-text `search_evidence` (`examined=10`, one returned item).

This apparent contradiction is deterministic: the launchers bind different databases and profiles. The tunnel target's historical DB has `position_page_start/end`; the certified immutable DB does not.

Other independent valid calls established:

- one notebook and 44 source memberships;
- `summary=null`, `status=empty`, `completeness=unknown` is a normal no-summary result;
- empty source insights are a normal no-insight result;
- timeline succeeds;
- original document delivery succeeds;
- actual asset inventory succeeds;
- a real occurrence with persisted OCR and Vision returned two analysis items with complete status;
- the Phase 8.6 notebook ID is not present in the production store and returns not found;
- a real exact chunk call against the certified DB fails at the additive page-range columns.

The external invalid document/version and placeholder chunk tests are not defects. The server intentionally collapses unauthorized/not-found delivery to avoid an existence oracle.

## 4. Tool-by-Tool Status

For counting purposes, a tool is “healthy” only if its intended valid behavior is not currently blocked in the certified topology. Eight are healthy: notebook listing, notebook summary, source insights, timeline, asset delivery, known derivation delivery, capability discovery, and the certified FinalQA implementation. Five tools/modes have one real shared schema-reader defect: the two retained V1 retrieval tools, canonical-text `search_evidence`, block-mode document delivery, and exact chunk delivery. `query_structured` is the one expectedly unavailable tool in the observed historical runtime.

These categories are tool-level and deliberately separate from individual-call classification. Two reported calls used intentionally invalid IDs, while the FinalQA network failure occurred outside the tool error contract.

## 5. `sq-2:sparse` Root-Cause Analysis

Call chain:

```text
query_notebook / search_all_notebooks
  -> QueryService / SearchService
  -> MultiSourceRetriever.execute
  -> one HYBRID SubQuery expands in deterministic order
       sq-1:dense
       sq-2:sparse
  -> SparseRetriever.retrieve
  -> CompositeStorage.search_sparse
  -> SQLiteStore.search_sparse
  -> FTS5 MATCH and BM25 succeed
  -> SQLiteStore.get_chunk
  -> SELECT position_page_start, position_page_end
  -> sqlite3.OperationalError: no such column: position_page_start
  -> PluginError("retriever invocation failed: sq-2:sparse")
```

`sq-2` is not a table, generation, or server. It is `SubQuery` 1's second effective invocation after HYBRID expands to dense and sparse (`fusion.py`, `_Invocation.invocation_id`).

The certified DB is healthy: integrity is `ok`; FTS has 2,658 canonical rows and 2,658 title rows; a direct read-only FTS/BM25 query returns candidates. This is neither missing FTS data, authorization filtering, nor an MCP adapter failure. It is a generic reader versus immutable-schema compatibility failure.

The V2-specific `SQLiteV2ReadOnlyRuntimeStore._get_governed_artifact_chunk()` explicitly documents and handles this exact older schema by selecting only physically governed columns. Phase 8.8 should consolidate that compatibility at an appropriate read-model boundary without migrating or mutating the certified DB.

## 6. `search_evidence` OperationalError Root Cause

For `representations=["canonical_text"]`, `CanonicalTextAdvancedSource` wraps the same V1 sparse retriever. It therefore reaches the same `SQLiteStore.get_chunk()` failure. `AdvancedRetrievalService` catches the source exception and emits a failed representation report:

```text
canonical_text -> failed -> source_failure:OperationalError
examined=0, returned=0, completeness=unknown
```

That translation is fail-visible and correct; it does not manufacture a no-match. The underlying failure is not correct.

This does **not** prove the governed `multilingual_text` V2 source is broken. That source uses `FullMultilingualAdvancedSourceV2`, the read-only V2 store, identity-bound candidates, BGE-M3, FTS5 fusion, and the governed reranker. Retained real certification evidence passed HTTP, stdio, and SSE. The current tunnel cannot exercise that production route because its launcher disables Full Multilingual V2.

## 7. FinalQA Network Failure Root Cause

The external error was `mcp_network_error / network_error / Connection failed`, not a structured Mnemo MCP error. There is no matching server traceback or request correlation ID in the supplied evidence. Consequently the precise socket/connector sub-cause is `EVIDENCE_INCONCLUSIVE`.

What is proven:

- `scratch/http-finalqa-e2e-result.json`: HTTP 200, cited result.
- `scratch/mcp-stdio-finalqa-e2e-result.json`: `is_error=false`, cited result.
- `scratch/mcp-sse-finalqa-e2e-result.json`: `is_error=false`, cited result.
- Those runs took about 19–47 seconds, so a connector timeout is credible.
- The tunnel health service currently reports `live` and `ready`.
- The configured tunnel command launches historical V1 mode and does not open the separate production FinalQA operational store.

Verdict: the reported network error is client/transport-side, not evidence of a broken FinalQA implementation. The **launcher composition drift is nevertheless a real Mnemo deployment defect**. After convergence, Phase 8.8 must run one correlated tunnel request and capture client deadline, server start/completion, process exit, and MCP error envelope.

## 8. Source Filename / Metadata Contract Audit

### Identity model

- `source_id`: stable identity of one notebook-to-document membership (`Source` contains only source, notebook, document, and creation time).
- `document_id`: stable logical document identity.
- `version_id`: immutable exact-content version identity.
- `chunk_id`: SHA-256 identity of canonical chunk content/provenance.
- `asset_id`: content-addressed asset identity.
- `occurrence_id`: occurrence of an asset in an exact document version.
- filename: ingestion/display metadata, not canonical identity and not authority.
- document title: exact-version descriptive metadata; often filename-like, but not guaranteed to equal the original filename.

`SourceResponse` in the HTTP ingestion service already defines `filename`, `content_hash`, `mime_type`, `doc_type`, and metadata. It resolves filename from parsed-document nested metadata and otherwise emits `source_file`. In the certified corpus, document-version `title` commonly contains a filename, but the nested metadata does not consistently retain `filename`. Therefore the MCP layer cannot truthfully rename every title to `filename`.

### Current MCP output

| Tool | Stable IDs | Human name | MIME | Provenance gap |
|---|---|---|---|---|
| `list_notebooks` | notebook | notebook title | no | Does not list source metadata |
| `get_notebook_summary` | notebook/source/document | document title | no | No version ID, filename, MIME, hash |
| `get_source_insights` | source/notebook | no | no | No source metadata envelope |
| `get_timeline` | source event + document | generic event title | no | No document title/filename/version |
| `query_notebook` | citation/chunk | document title | no | No source/document/version in citation DTO |
| `search_all_notebooks` | notebook/document/version/chunk | only indirectly in metadata | no | Inconsistent discoverability |
| `search_evidence` | full notebook/source/document/version/chunk/occurrence/derivation | `document_title` | no | No source display name |
| `get_document` / chunk | resource IDs and block provenance | no consistent source name | original MIME only | No authorized source envelope |
| `get_asset` | full attribution IDs | no source name | yes | No filename/title |
| `get_image_analysis` | occurrence/derivation provenance | no source name | derived type only | No filename/title |
| FinalQA citations | full stable IDs | field exists but retained evidence contains `document_title=null` | no | Human source identity lost |

### Minimal Phase 8.8 contract

Add a backward-compatible `source_metadata` object after authorization:

```json
{
  "source_id": "...",
  "document_id": "...",
  "version_id": "...",
  "display_name": "Act 2. panch-parmeshwar-by-munshi-premchand.pdf",
  "original_filename": null,
  "document_title": "Act 2. panch-parmeshwar-by-munshi-premchand.pdf",
  "mime_type": "application/pdf",
  "content_hash": "..."
}
```

`display_name` is the safe presentation fallback. `original_filename` must be nullable and emitted only when actually persisted. Stable IDs remain mandatory. Do not expose local paths or use names in authorization. Add a bounded `get_source_metadata`/`list_sources` operation or enrich the existing summary inventory so a client can resolve `source_id` without retrieving the whole document.

## 9. Notebook Exposure Audit

### Phase 8.5

One Phase 8.5 notebook ID is visible in both the historical tunnel database and certified production corpus. This masks the composition drift: the logical notebook looks identical while its store/model/lifecycle bindings differ.

### Phase 8.6

The server-owned **evaluation** registry allowlists `phase8_5` and `phase8_6`, but its only production use is the evaluation transport/runtime tooling. Normal `KnowledgeEngine` startup resolves one SQLite path from configuration; it does not federate `scratch/evaluation_notebooks/registry.json` into MCP. A direct production lookup of the Phase 8.6 notebook correctly returns not found.

Phase 8.6 should **not** be exposed now. It is explicitly evaluation-only and has a distinct manifest/store identity. Safe future promotion needs a governance decision, a serving-role/allowlist boundary, authenticated authorization, read-model compatibility, capability/lifecycle binding, and fresh HTTP/stdio/SSE provenance certification. It must remain separate from the 44-document certified corpus.

## 10. Structured Retrieval Audit

The current tunnel DB has zero structured table projections, so unavailable is expected there. The certified DB contains 105 structured table projections and 14,372 cells, but a global runtime capability still does not guarantee that a requested version has a structured generation. A valid `describe` call for a non-tabular PDF returned partial with `version:<id>:structured_generation_unavailable`, which is correct.

The tool's additive registration is not misleading if clients consult capability and per-scope results, but the distinction needs clearer schema/docs. Phase 8.8 should fix reporting, not activate structured retrieval as a new product promise. Phase 9 does not require this capability.

## 11. Vision/OCR/CLIP/Multimodal Audit

Three different data realities exist:

| Store | Occurrences | OCR | Vision | visual embeddings |
|---|---:|---:|---:|---:|
| Certified production | 464 | 463 | 463 | 463 |
| Current historical tunnel | 464 | 14 | 26 | 16 |
| Phase 8.6 evaluation | 161 | 161 | 161 | 161 |

`get_asset` is intentionally independent: it delivers original source truth by known occurrence. `get_image_analysis` delivers existing derivations by known occurrence/selector and also works independently of semantic image search. A valid current call returned ready OCR and Vision data even though profile-based Vision generation was not configured for new processing.

Multimodal semantic discovery is a separate generation-backed capability and is not active in the current tunnel. This is not a reason to activate it in Phase 8.8. Preserve delivery, correct capability wording, and defer semantic multimodal activation until a consuming feature and certification contract exist.

## 12. Capability Reporting Audit

The implementation accurately derives a **process-local** `Phase85RuntimeV1` snapshot. The external “profile not configured” and “active generation unavailable” messages therefore match its historical launcher.

Gaps:

1. It does not attest that the process is bound to the certified production manifest/store/activation digest.
2. `scope_qualified=false`; global active state cannot guarantee a requested notebook/version has data.
3. Tool registration is unconditional, so a client can see callable schemas for uncomposed services.
4. The tunnel configuration drift means locally truthful status is misleading when the endpoint is presented as certified production.

Phase 8.8 should report effective store/configuration identity and explicitly separate `registered`, `callable`, `available_for_scope`, `active`, and `certified`.

## 13. V1/V2 Routing Audit

- `query_notebook`, `search_all_notebooks`: frozen V1 retrieval and V1 optional synthesis.
- notebook inventory, summary, insights, timeline: retained storage handlers.
- document/asset/image delivery: additive V2 shared delivery contracts, with principal-aware scope resolution in production.
- `search_evidence`: V2 transport contract; `canonical_text` adapts V1 sparse, while `multilingual_text` uses governed V2 only after production installation.
- `query_structured`: V2 typed structured service.
- `run_final_qa_v2`: V2 FinalQA.
- `get_capabilities`: Phase 8.5 runtime snapshot.

The answer is not to blindly route all tools through V2. Retained V1 contracts may stay if they receive an immutable-schema-compatible reader and a production authorization boundary. The external tunnel must not silently substitute its old V1 profiles for certified V2 operations.

## 14. Transport Parity Audit

Prior controlled certification established V2 semantic parity across HTTP, MCP stdio, and MCP SSE. This audit did not alter that evidence.

The current tunnel topology has no parity proof: its command launches stdio only, against a historical DB/profile set. It cannot be compared to the certified HTTP/SSE runtime as the same composition. External FinalQA transport behavior is therefore not covered by the certification evidence despite the underlying service having passed.

Phase 8.8 must generate one evidence bundle that binds HTTP, stdio, SSE, and the existing tunnel to the same store identity, configuration digest, principal policy, generation set, and model revisions.

## 15. Authorization Audit

Production V2 has the intended chain:

```text
authenticated server principal
  -> CentralAuthorizationServiceV1
  -> CentralV2RetrievalAuthorizerV1
  -> identity-bound production store
```

The current tunnel starts `auth_mode=none`, `production_mode=false`, and `full_multilingual_v2_enabled=false`. The retained V1 handlers for query, search, notebook inventory, summary, insights, and timeline do not call `CentralAuthorizationServiceV1`. They query the process store directly. A control-plane tunnel identity is not a replacement for a typed Mnemo principal.

This is a real authorization defect for remote tunneled use. Phase 8.8 must either bind these tools to the central service with a server-authenticated principal or intentionally remove the retained tools from the remote production surface. Delivery handlers already normalize unauthorized/missing results and should retain that non-disclosure behavior.

## 16. Provenance Audit

The V2 evidence path preserves notebook, source, document, version, chunk/occurrence/derivation, locator, retrieval paths, and scores. Delivery preserves attribution IDs and content hash. The principal provenance loss is human readability at the MCP boundary. Retained FinalQA evidence even contains `document_title=null` despite resolvable version metadata.

The source metadata improvement should be implemented once in an authorized resolver and reused across retrieval, delivery, asset, analysis, and citation responses. Transport adapters must not independently query or guess filenames.

## 17. MCP Contract Defects

- Registered/callable/available/active/certified are not cleanly distinguishable from `tools/list` alone.
- No consistent authorized source metadata resolver/envelope.
- Underlying storage errors lose their exact safe reason in MCP responses (`sq-2:sparse` is too coarse).
- Capabilities are process-local and not certified-composition-attested or scope-qualified.
- Current tunnel exposes retained V1 handlers without central authorization.

## 18. Underlying Service Defects

- Generic chunk readers require additive page-range columns that the immutable certified corpus intentionally lacks.
- The compatibility reader exists only in `SQLiteV2ReadOnlyRuntimeStore` and is not shared by V1 sparse/canonical delivery paths.
- Current tunnel startup is a separate historical composition and omits durable BGE/FinalQA production startup.

## 19. Client/Test-Input Errors

- `get_document`: intentionally invalid document/version pair; correct not-found behavior.
- `get_document_chunk`: placeholder/non-SHA-256 or nonexistent chunk; correct validation/not-found behavior.
- `run_final_qa_v2`: generic network error was generated outside Mnemo's tool contract. It is client/transport-side unless correlated server evidence later proves a server crash.

## 20. Documentation Defects

- Current documentation says production is certified BGE V2 while the live tunnel launcher selects historical V1 models and DB.
- Roadmap text still emphasizes six original MCP tools while the server exposes 14.
- Capability/tool descriptions do not sufficiently explain that derivation delivery may work while generation/semantic discovery is unavailable.
- Source, membership, document, version, asset, and occurrence terminology lacks one client-facing identity guide.

## 21. Phase 8.8 Required Fixes

1. Converge tunnel/MCP startup on the canonical certified production configuration, immutable store identity, durable BGE activation, FinalQA operational store, and exact model/policy identities.
2. Make all exposed retained read paths compatible with the immutable certified chunk schema without modifying that DB.
3. Enforce a server-authenticated principal and central authorization for remotely exposed retained V1 inventory/retrieval, or withdraw those tools from that surface.
4. Fail startup when configured store/model/runtime identity differs from the advertised certified identity.
5. Re-run real HTTP, MCP stdio, MCP SSE, and existing-tunnel parity with one bound configuration digest, including long-running FinalQA diagnostics.

## 22. Phase 8.8 Recommended Fixes

1. Add an authorized, additive `source_metadata` response contract and bounded resolver.
2. Attest effective serving identity in capabilities and distinguish global from scope-specific availability.
3. Preserve typed safe underlying error codes through MCP without leaking unauthorized existence.
4. Make conditional tool availability explicit in discovery/documentation.

## 23. Deferred Work

- Phase 8.6 production exposure: remain evaluation-only.
- Structured feature activation: defer until a Phase 9+ use case requires it.
- Semantic multimodal activation: defer; keep exact asset/derivation delivery.
- Qdrant and SurrealDB: unrelated and deferred per the post-Phase-8 architecture audit.

## 24. Risk Register

| Risk | Severity | Evidence | Control |
|---|---|---|---|
| Endpoint advertised as certified but launches historical V1 | Critical | `mnemo.yaml` -> `start-mnemo.bat` | Identity-bound production startup |
| Remote V1 tools bypass central authorization | Critical | `execute_mcp_tool` retained branches | Principal-aware central authorization or withdrawal |
| Immutable store incompatible with generic readers | High | exact OperationalError traceback | Compatible read model, no DB mutation |
| FinalQA connector timeout/crash remains uncorrelated | High | generic network error; 19–47s valid runs | Correlation and explicit deadlines |
| Opaque source identities impair client grounding | Medium | MCP response matrix | Additive source metadata |
| Capabilities mistaken for scope readiness | Medium | `scope_qualified=false` | Scope-aware availability semantics |
| Premature Phase 8.6/structured/multimodal activation | High | separate roles/generation states | Defer and govern promotion |

## 25. Recommended Phase 8.8 Scope

Phase 8.8 should be a bounded **MCP production-composition and contract-correctness release**, not a feature expansion. It should converge startup, make immutable-schema reads compatible, secure retained tools, add human-readable authorized provenance, improve capability/error semantics, and certify transport parity including the existing tunnel. It should not activate Phase 8.6, structured semantic features, multimodal semantic retrieval, Qdrant, or SurrealDB.

## 26. Phase 9 Readiness Impact

Phase 9 is `READY_AFTER_PHASE_8_8`. UI scaffolding may proceed, but production integration should wait for:

1. this audit's MCP startup/auth/read compatibility corrections;
2. the already identified mutable notebook/upload boundary (or a read-only first release);
3. the already identified authenticated V2 FinalQA or versioned certified V2 streaming decision.

## 27. Final Decision

CURRENT MCP STATE:
Mnemo registers 14 tools, but the external tunnel and certified V2 production are different compositions. The tunnel currently launches a historical V1 store/model profile with no Mnemo production principal; the certified immutable store exposes a real generic-reader schema incompatibility. Core V2 FinalQA and multilingual retrieval have valid prior transport evidence, while current tunnel parity is unproven.

HOW MANY MCP TOOLS ARE ACTUALLY EXPOSED?
14

HOW MANY ARE HEALTHY?
8

HOW MANY HAVE REAL MNEMO DEFECTS?
5

HOW MANY ARE EXPECTEDLY UNAVAILABLE?
1

HOW MANY FAILURES ARE CLIENT/TEST-INPUT ERRORS?
2

IS sq-2:sparse A REAL MNEMO BUG?
YES
Reason:
FTS5 returns valid candidates, but the certified immutable DB lacks two additive columns selected by the generic chunk reader. The wrapper hides the exact `OperationalError` behind the invocation ID.

IS search_evidence OperationalError A REAL MNEMO BUG?
YES
Reason:
The canonical-text source adapts the same sparse reader and hits the same missing-column defect. It is not the governed multilingual V2 source.

IS run_final_qa_v2 NETWORK FAILURE A REAL MNEMO BUG?
CLIENT-SIDE
Reason:
The supplied error is outside the Mnemo tool envelope and no server failure evidence accompanies it; real HTTP, stdio, and SSE FinalQA runs passed. Separately, the tunnel's non-certified startup composition is a real Mnemo deployment defect that must be fixed and retested.

IS SOURCE FILENAME EXPOSURE A REAL MCP CONTRACT GAP?
YES
Reason:
Stable IDs are present, but source-oriented responses lack a consistent authorized display-name/filename/MIME/version metadata envelope, and retained citations can carry a null title.

SHOULD PHASE 8.6 BE EXPOSED NOW?
NO
Reason:
It is a validated evaluation-only store in a separate server-owned evaluation registry, not an authorized/certified production serving store.

SHOULD STRUCTURED RETRIEVAL BE ACTIVATED IN PHASE 8.8?
NO
Reason:
Availability is store/version-specific and Phase 9 does not depend on it. Fix composition and capability truthfulness first.

SHOULD MULTIMODAL RETRIEVAL BE ACTIVATED IN PHASE 8.8?
NO
Reason:
Exact assets and persisted derivations already have valid delivery paths; semantic multimodal search is a separate generation-backed feature with no Phase 9 prerequisite.

PHASE 8.8 MUST FIX:
1. Certified production startup convergence for the tunnel and every MCP transport.
2. Immutable certified-schema reader compatibility for V1 sparse, canonical evidence, block, and chunk delivery.
3. Authenticated principal and central authorization for every remotely exposed retained tool.
4. Startup identity fail-closed checks.
5. Same-composition HTTP/stdio/SSE/tunnel parity, including correlated FinalQA timeout evidence.

PHASE 8.8 SHOULD FIX:
1. Authorized source metadata/display-name contract.
2. Configuration/store identity and scope-aware capability reporting.
3. Typed safe error propagation.
4. Conditional availability semantics in tool discovery/docs.

DEFER:
1. Phase 8.6 production exposure.
2. Structured and semantic multimodal activation.
3. Qdrant and SurrealDB/graph work.

PHASE 9 BLOCKERS:
1. The bounded Phase 8.8 production MCP convergence above.
2. Mutable notebook/upload separation or explicit read-only UI scope.
3. Authenticated certified V2 FinalQA transport or a certified V2 streaming contract.

PHASE 9 READINESS:
READY_AFTER_PHASE_8_8

RECOMMENDED PHASE 8.8 SCOPE:
Converge the real MCP deployment on certified V2; repair read compatibility without touching the corpus; secure retained tools; add source display metadata; make capabilities/errors precise; and certify one identity-bound HTTP/stdio/SSE/tunnel matrix.

FINAL RECOMMENDATION:
Implement the bounded Phase 8.8 scope above, keep Phase 8.6 and new structured/multimodal capabilities unpromoted, then proceed to Phase 9 after the existing mutable-storage and authenticated-chat boundaries are resolved.

FINAL STATUS:
PHASE_8_8_REQUIRED_BEFORE_PHASE_9

## Evidence

Primary code evidence:

- `mnemo-server/mnemo_server/mcp/tools.py`: tool registration and dispatch at lines 629–682; retained handlers at 1159–1571; delivery handlers at 813–1156.
- `mnemo-core/mnemo/retrieval/fusion.py`: hybrid expansion, invocation IDs, fail-fast orchestration, and plugin error wrapping.
- `mnemo-core/mnemo/storage/sqlite.py`: `get_chunk` around line 2991 and `search_sparse` around line 3383.
- `mnemo-core/mnemo/storage/v2_runtime.py`: immutable compatibility reader around lines 251–279.
- `mnemo-server/mnemo_server/services/retrieval_v2.py`: shared HTTP/MCP V2 authorization and retrieval.
- `mnemo-server/mnemo_server/services/capabilities_v2.py`: process-local and non-scope-qualified capability projection.
- `mnemo-server/mnemo_server/schemas/sources.py`: existing rich HTTP `SourceResponse`.
- `mnemo-core/mnemo/models/notebook.py`: stable source-membership model.
- `mnemo-server/mnemo_server/evaluation/notebook_registry.py`: evaluation-only alias registry.
- `C:/Users/athar/AppData/Roaming/tunnel-client/mnemo.yaml` and `C:/Tools/start-mnemo.bat`: actual external startup chain (credentials redacted during inspection).

Protected-state hashes after all probes:

- Production: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`
- Phase 8.5 notebook: `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`
- Phase 8.6 notebook: `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`

Only this report and the two requested scratch audit artifacts were created.
