# Phase 8.5 pre-8.5.11 reconciliation

Date: 2026-08-25  
Baseline: Mnemo 0.25.0  
Scope: Phase 0–8 compatibility and Phase 8.5.1–8.5.10 reconciliation  
Decision: model benchmarking, provider selection, release, and Phase 8.5.11 implementation are out of scope.

## 1. Executive summary

The implemented Phase 8.5 stack is additive and has a coherent handoff to Phase 8.5.11. The audit found no frozen Phase 0–8 identity, storage, retrieval, citation, Final-QA, HTTP, MCP, or Qdrant contract changes. Four contained delivery defects were corrected: MCP delivery now uses its composed server limits, MCP delivery failures no longer expose internal exception detail, derived-result completeness is preserved through delivery, and document continuation cursors bind the parsed representation as well as the document version. Active documentation was reconciled with the implementation.

No P0 or unresolved P1 finding remains. No model or provider is certified by this checkpoint.

## 2. Phase 0–8 frozen compatibility

| Contract | Audit result | Evidence |
|---|---|---|
| Document, version, source, and chunk identities | PASS | Phase 8.5 models and tables are additive; canonical identity code is unchanged. |
| Canonical `Chunk.text` and digest | PASS | Derived OCR, vision, structured, and translated data remain separate projections. |
| `StorageInterfaceV1` and V1 storage | PASS | New capabilities use additive protocols and `CompositeStorage` delegation. |
| Canonical SQLite FTS/title and text embeddings | PASS | Phase 8.5 projections have independent tables/generations; canonical indexes are not rewritten. |
| V1 retrieval/reranking | PASS | V2 orchestration is additive; V1 metadata-preservation regressions remain covered. |
| V1 citations and Final-QA | PASS | V2 reuses ADR-0054 compliance and ADR-0056 publication/replay without replacing V1. |
| HTTP V1 and streaming | PASS | Delivery is under additive `/v2`; V1 routes retain their schemas and semantics. |
| Six MCP tools | PASS | Their definitions and dispatch remain stable; four delivery tools are appended. |
| Qdrant optionality | PASS | No Phase 8.5 module enables or requires Qdrant. |

## 3. Phase 8.5.1–8.5.10 matrix

| Workstream | Architecture/ADR | Implementation and tests | Status |
|---|---|---|---|
| 8.5.1 Asset foundation | ADR-0059, 0068, 0071 | Original-byte references, occurrence/derivation identities, typed locators, catalog storage, authorization, schema v7 | PASS |
| 8.5.2 Parser extraction | ADR-0059, 0068 | Bounded PDF/PPTX/DOCX/XLSX/HTML/Markdown and image extraction with deterministic occurrence provenance | PASS |
| 8.5.3 Durable processing | ADR-0060, 0068, 0071 | Jobs, attempts, leases, checkpoints, policy, cost ledger, cleanup, schema v8 | PASS |
| 8.5.4 OCR | ADR-0061 | Provider-neutral OCR, derivations/projection/cache, job governance, schema v9 | PASS |
| 8.5.5 Vision/vectors | ADR-0062 | Vision and visual-vector profiles, derivations/generations, governed execution, schema v10 | PASS |
| 8.5.6 Advanced retrieval | ADR-0058 | Ranked/exhaustive modes, budgets, completeness, diagnostics, provenance-safe expansion/fusion | PASS |
| 8.5.7 Structured retrieval | ADR-0063 | Typed schemas/records/aggregates, safe expressions, projections, schema v11 | PASS |
| 8.5.8 Multimodal Final-QA V2 | ADR-0064 | Typed fusion/context/evidence/citations, immutable publication/replay, schema v12 | PASS after current reconciliation |
| 8.5.9 Multilingual | ADR-0067 | Language evidence, translation/transliteration derivations, multilingual retrieval, schema v13 | PASS |
| 8.5.10 Delivery | ADR-0065, 0066, 0069 | Bounded HTTP/MCP document, asset, analysis, and evidence delivery | PASS after fixes in this audit |

The historical 8.5.8 gate document records `READY FOR REVIEW`; it is retained as historical evidence. This reconciliation validates its present implementation and downstream compatibility rather than rewriting that report.

## 4. ADR compliance matrix

| ADR | Implemented contract | Result |
|---|---|---|
| 0058 | Advanced result sets, ranked/exhaustive distinction, completeness and bounds | PASS |
| 0059 | Original assets, binary references, occurrences, derivations | PASS |
| 0060 | Durable governed jobs, leases, recovery, consent and accounting | PASS |
| 0061 | OCR as derived provenance and independent projection | PASS |
| 0062 | Vision analysis and named visual-vector generations | PASS |
| 0063 | Structured projection/query/aggregation | PASS |
| 0064 | Typed multimodal evidence and Final-QA V2 | PASS |
| 0065 | Bounded expansion, integrity, completeness, signed snapshot cursors | PASS after cursor/completeness fixes |
| 0066 | Additive MCP resources and four delivery tools | PASS |
| 0067 | Original-language preservation and derived translation/transliteration | PASS |
| 0068 | Occurrence-scoped authorization and provider trust boundaries | PASS |
| 0069 | Additive HTTP capability contract; UI remains Phase 9 | PASS |
| 0070 | Evaluation/certification governance reserved for 8.5.11 | READY |
| 0071 | Additive migrations and atomic generation lifecycle | PASS |

## 5. Architecture compliance matrix

| Layer boundary | Result |
|---|---|
| Original bytes → asset/reference/occurrence | Exact bytes and content identity retained; authorization follows notebook → document → exact version → occurrence. |
| Occurrence → OCR/vision/translation | Derived records retain original and derivation identities; source truth is not overwritten. |
| Derivation → projection/generation | Independent generation identity and lifecycle; BUILDING data is not active. |
| Projections → retrieval | Representation identity, availability, completeness, scope, and diagnostics remain typed. |
| Retrieval → fusion/rerank/context | Runtime provenance, title evidence, parent promotion, modality, completeness, and authorization are preserved. |
| Context → citation/publication/replay | Evidence V2 remains typed; immutable snapshot is the replay source. |
| Publication → HTTP/MCP delivery | Resources are integrity-checked, bounded, cursor-bound, and authorized before content delivery. |

## 6. Roadmap compliance

All implementation tasks assigned to 8.5.1–8.5.10 have corresponding production modules and focused tests. Phase 8.5.11 remains the sole authority for benchmark datasets, quality thresholds, candidate comparison, production provider/model selection, and certified profiles. Phase 9 UI, later provider integrations, deployment, and ecosystem work remain outside Phase 8.5.

## 7. Implementation drift findings

| Severity | Finding | Resolution |
|---|---|---|
| P1 | Delivery collapsed partial/unknown derivation and Final-QA completeness to `COMPLETE`; bounded analysis lists were sliced silently. | Expanded delivery completeness states, propagated aggregate/context completeness, and reports `BOUNDED` plus an omission when item limits apply. |
| P2 | MCP delivery constructed default limits instead of using the composed server configuration. | Propagated `ServerConfig` through MCP creation and dispatch into the shared delivery service. |
| P2 | MCP delivery returned raw authorization/integrity exception strings. | Added typed safe MCP error messages without internal details. |
| P2 | Document continuation snapshots bound the version content hash but not the current parsed representation. | Added a canonical parsed-block digest to the snapshot identity; stale cursors now fail closed. |
| P3 | Active README/roadmap/architecture text understated implemented delivery and MCP capabilities or described nonexistent job routes. | Reconciled active documentation; historical evidence/changelog entries remain immutable history. |

No corpus-specific ranking, filename, identity, or authorization rule was found.

## 8. Early-bird findings

The Phase 8.5 durable job substrate overlaps a narrow responsibility later consumed by Phase 10. This is an intentional reusable foundation, not provider coupling. Delivery includes provider/profile metadata but no provider selection. Multilingual, OCR, vision, and vector modules contain deterministic fakes/contracts and configurable profiles, not certified model winners. No Phase 9 UI behavior or client-specific MCP coupling was found.

## 9. Provenance audit

The chain `document → version → chunk/asset → occurrence → derivation → generation → retrieval candidate → fusion/reranking → typed evidence → Final-QA V2 snapshot → HTTP/MCP` retains opaque identities and original-versus-derived authority. Focused tests cover prior failure classes: title metadata loss, parent promotion, fusion/deduplication, diversity, positional provenance, derived citations, and delivery attribution. Content-addressed deduplication never substitutes for occurrence authorization.

## 10. Authorization audit

Every Phase 8.5 entry point scopes lookup through notebook/document/version or an authorized occurrence. Derived cache hits and delivery reauthorize their occurrence; asset hashes, asset IDs, blob locations, derivation IDs, and cursors are not bearer capabilities. Shared-content cross-notebook tests and delivery denial tests pass. No arbitrary filesystem delivery endpoint exists.

## 11. Completeness audit

Ranked and exhaustive retrieval are distinct. Unavailable/disabled representations remain distinct from no-match. Advanced, structured, multimodal, multilingual, Final-QA, and delivery layers propagate complete, partial, bounded/truncated, unavailable, unknown, or failed states as applicable. Delivery bounds now explicitly mark analysis-item omissions and preserve underlying derivation/context completeness.

## 12. Cost/governance audit

OCR, vision, visual embedding, and translation provider execution use the durable processing policy boundary. Deterministic fingerprints, consent/cloud-egress policy, admission/budget checks, conditional claims, leases, checkpoints, cancellation, bounded retries, recovery, progress events, and append-only cost records are covered. No hidden provider invocation or credential-bearing manifest was found.

## 13. Security audit

The reviewed paths enforce archive/member limits, MIME/hash/size validation, safe locators, output bounds, provider-result validation, prompt/content separation, signed cursors, immutable snapshot hashes, and notebook/occurrence authorization. Binary APIs expose neither storage paths nor arbitrary reads. MCP error sanitization was strengthened during this audit. Focused security tests cover traversal, shared assets, malformed media/provider data, resource exhaustion, stale generations/cursors, and snapshot tampering.

## 14. HTTP audit

V1 routes remain unchanged. Additive `/v2` endpoints expose capabilities, bounded document/original/asset resources, OCR/vision analyses, and Final-QA V2 evidence through the shared delivery service. UUID validation, typed error mapping, response limits, cursor binding, cancellation, and authorization precede delivery.

## 15. MCP audit

The six frozen tools retain their schemas and semantics. Four additive tools (`get_full_document`, `get_asset`, `get_image_analysis`, `get_final_qa_v2_evidence`) and typed resources reuse the HTTP delivery service. Capability discovery distinguishes support from unavailable/unvalidated capability. MCP now honors composed delivery limits and sanitizes failure detail.

## 16. Storage/migration audit

SQLite schema version 13 comprises additive migrations v7–v13 for assets, processing, OCR, vision, structured, multimodal, and multilingual data. Fresh creation contains the same statements. Each migration runs transactionally and has repeated-upgrade/rollback coverage. Foreign keys, uniqueness, immutable-result semantics, active-generation promotion, and orphan checks are present. No migration destructively rewrites Phase 0–8 canonical tables.

## 17. Documentation consistency audit

Active README, server README, Phase 8.5 architecture, Phase 8.5 roadmap, master architecture/roadmap, ADR index/status, and current changelog now distinguish the six frozen plus four additive MCP tools, implemented `/v2` delivery, and pending 8.5.11 certification. Local-link and duplicate-ADR scans found no active defects. Historical reports were not rewritten to erase their original state.

## 18. Phase 8.5.11 readiness

The code exposes provider-neutral capability/profile identities, deterministic derivations and caches, independent generation spaces, retrieval diagnostics/completeness, governed cost/resource accounting, language/script metadata, and immutable evaluation inputs. These are sufficient inputs for reproducible OCR, vision, visual-embedding, multilingual-reranker, retrieval, Final-QA, latency, memory/VRAM, and cost evaluation. Phase 8.5.11 must add benchmark datasets/profiles, thresholds, candidate registration/results, and certified pinned model profiles; no current default is a certification decision.

## 19. Future-phase compatibility

Phase 9 may consume capability discovery without core UI assumptions. Phases 10–13 can reuse provider-neutral jobs, policy, profiles, delivery, and observability without inheriting a fixed vendor or vector space. Visual vector generations name dimension/metric/profile, multilingual data preserves source language, and MCP delivery is protocol/client-neutral.

## 20. Remaining risks

- Real-provider quality, hardware envelopes, latency, VRAM, monetary cost, and multilingual/multimodal quality remain deliberately unvalidated until 8.5.11.
- Delivery capability `UNVALIDATED` is used where a contract exists without a certified execution profile; clients must not interpret it as production model support.
- Runtime provider availability remains deployment-specific and must be evaluated without changing frozen identities.

## 21. Changes made

- Propagated configured limits and cursor secrets through MCP composition.
- Sanitized MCP delivery errors.
- Added complete delivery completeness semantics and bounded-analysis omissions.
- Bound document cursors to canonical parsed-block snapshots.
- Added focused regressions for each corrected boundary.
- Reconciled active architecture, roadmap, README, ADR status, changelog, and gate evidence claims.

## 22. Tests and validation

Focused delivery/MCP reconciliation suite: **24 passed**.  
Full suite: **1,654 passed, 1 skipped**.  
Coverage: **90.06%** (required minimum 90%).  
Ruff format: **PASS** (316 files); Ruff lint: **PASS**.  
Strict mypy: **PASS** (190 source files).  
Package builds: **PASS** for `mnemo-core`, `mnemo-server`, and `mnemo-email-ingestion`, all at 0.25.0.  
`git diff --check`: **PASS**.

The Golden Corpus was opened with SQLite URI `mode=ro&immutable=1`; no migration or write was attempted. It remains at its certified Phase 0–8 schema v6 with **15 documents, 15 versions, 15 sources, 1,514 chunks, 1,514 FTS rows, and 1,514 title rows**. Duplicate document/version/chunk identities, orphan sources/versions/chunks/title rows, stale or missing FTS rows, and missing title rows are all zero. The ordered chunk-ID/text digest remains:

`1997852deb381869d1ff72f511fa22b97bdea5287e5f6632ef1292405bbf4e66`

The production schema implementation is v13; the certified corpus intentionally remains unmigrated because this audit was strictly read-only.

## 23. Final recommendation

Phase 8.5.11 has a clean architectural starting point. Begin it only as the accepted evaluation/model-certification workstream. No benchmarking, provider selection, corpus mutation, version change, commit, push, tag, or release was performed.

**PRE-8.5.11 RECONCILIATION: PASS**
