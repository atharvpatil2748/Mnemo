# Full Multilingual V2 Implementation Report

Date: 2026-08-31  
Status: engineering architecture implemented; runtime remains fail-closed  
Actual lifecycle: **DECLARED / IMPLEMENTED, not CONFIGURED, not BUILDABLE, not READY, not ACTIVE, not EXPOSED, not EVALUATED, not VERIFIED, not CERTIFIED**

This report records an additive, side-by-side implementation. It does not promote V2, create a V2 index, run a model, change a protected database, or claim language support from provider marketing metadata.

## 1. Files modified

The repository was already materially dirty before this implementation. The following tracked or pre-existing implementation files were intentionally changed for Full Multilingual V2:

- `config/model_profiles/model_profile.schema.json`
- `docs/governance/contracts/phase8_5_capability_matrix.json`
- `mnemo-core/mnemo/engine.py`
- `mnemo-core/mnemo/interfaces/__init__.py`
- `mnemo-core/mnemo/interfaces/multilingual.py`
- `mnemo-core/mnemo/models/__init__.py`
- `mnemo-core/mnemo/models/multilingual.py`
- `mnemo-core/mnemo/phase85/__init__.py`
- `mnemo-core/mnemo/phase85/profiles.py`
- `mnemo-core/mnemo/phase85/runtime.py`
- `mnemo-core/mnemo/retrieval/__init__.py`
- `mnemo-core/mnemo/retrieval/multilingual_providers.py`
- `mnemo-core/mnemo/storage/multilingual.py`
- `mnemo-core/mnemo/storage/multimodal_search.py`
- `mnemo-core/mnemo/storage/sqlite.py`
- `mnemo-server/mnemo_server/evaluation/__init__.py`
- `mnemo-server/mnemo_server/mcp/contracts.py`
- `mnemo-server/mnemo_server/mcp/tools.py`
- `mnemo-server/mnemo_server/services/capabilities_v2.py`
- `mnemo-core/tests/unit/test_model_profiles.py`
- `mnemo-core/tests/unit/test_multilingual.py`
- `mnemo-server/tests/test_capabilities_v2.py`
- `mnemo-server/tests/test_mcp_tools.py`

No unrelated dirty-worktree changes were reverted or rewritten.

## 2. Files created

- `mnemo-core/mnemo/models/text_representations.py`
- `mnemo-core/mnemo/models/multilingual_embeddings.py`
- `mnemo-core/mnemo/models/multilingual_evaluation.py`
- `mnemo-core/mnemo/models/multilingual_generation.py`
- `mnemo-core/mnemo/models/multilingual_index.py`
- `mnemo-core/mnemo/models/multilingual_reranking.py`
- `mnemo-core/mnemo/interfaces/text_representations.py`
- `mnemo-core/mnemo/retrieval/language_detection.py`
- `mnemo-core/mnemo/retrieval/text_representations.py`
- `mnemo-core/mnemo/retrieval/reranker_candidates.py`
- `mnemo-core/mnemo/retrieval/multilingual_dense_v2.py`
- `mnemo-core/mnemo/retrieval/multilingual_sparse_v2.py`
- `mnemo-core/mnemo/retrieval/full_multilingual_v2.py`
- `mnemo-core/mnemo/retrieval/full_multilingual_advanced_v2.py`
- `mnemo-core/mnemo/phase85/full_multilingual_v2.py`
- `mnemo-core/mnemo/phase85/language_capabilities.py`
- `mnemo-core/mnemo/phase85/v2_readiness.py`
- `mnemo-server/mnemo_server/evaluation/multilingual_v2.py`
- `mnemo-core/tests/unit/test_full_multilingual_v2.py`
- this report

## 3. Contract-to-code mapping

| Contract | Implementation |
|---|---|
| Language evidence V3 | `models/multilingual.py` |
| Representation observation/transformation | `models/text_representations.py`, `interfaces/text_representations.py`, `retrieval/text_representations.py` |
| Reranker candidate V3 | `models/multilingual_reranking.py`, `retrieval/reranker_candidates.py` |
| Multilingual embedding V3 | `models/multilingual_embeddings.py`, `retrieval/multilingual_providers.py` |
| Independent language/script detection | `retrieval/language_detection.py` |
| Authorized exact-cosine dense retrieval | `retrieval/multilingual_dense_v2.py` |
| Authorized sparse retrieval | `retrieval/multilingual_sparse_v2.py`, `storage/multilingual.py` |
| Shared fusion/rerank path | `retrieval/full_multilingual_v2.py`, `retrieval/full_multilingual_advanced_v2.py` |
| Four-generation dependency graph | `phase85/full_multilingual_v2.py`, `models/multilingual_generation.py` |
| Derived readiness/activation | `phase85/v2_readiness.py`, `storage/multilingual.py` |
| Operation-scoped capabilities | `phase85/language_capabilities.py`, `phase85/profiles.py` |
| Grounded evaluator/runtime parity | `models/multilingual_evaluation.py`, `mnemo-server/.../evaluation/multilingual_v2.py` |
| Public representation parity | MCP contracts/tools and capability service |

## 4. P0 implementation status

All eight resolved P0 contracts have production representations:

1. V3 evidence reference is additive and preserves non-UUID evidence identities.
2. Representation observation/transformation is typed, deterministic, authorization-bound, and never rewrites canonical text.
3. V3 reranker candidates can only be built from resolved semantic evidence; blank/title-only content and scope mismatch fail before provider use.
4. The V2 evaluator calls the shared `EvidenceRetrievalApplicationService`; it has no provider/private-runtime entry point.
5. Semantic evaluation requires grounded queries, evidence qrels, raw-ranking identity, and census-proven corpus absence.
6. Existing projected FTS applies supported source/document/version scope before enumeration and fails closed on unsupported positional scope; additive V2 sparse/vector reads enumerate only an exact pre-authorized V3 identity set and revalidate returned lineage.
7. `multilingual_text` is aligned across internal request and MCP vocabulary without renaming tools.
8. READY/ACTIVE/EXPOSED are derived from one readiness snapshot; four V2 aliases promote atomically only with complete coverage manifests and a digest-bound four-generation rollback set.

P0 contract implementation is complete. This is not evidence that later runtime or assurance gates pass.

## 5. P1 implementation status

Implemented: versioned language/script observations; baseline detectors as plugins; generic representation registry; governed provider-claim schema; embedding lineage; authorized embedding/sparse reads; generation coverage manifests; exact vector-space isolation; normal advanced-retrieval adapter; engine exposure gate; dynamic capability projection; stable MCP/HTTP application boundary.

Deliberately still unconfigured:

- the frozen existing profile contains legacy EN/HI/MR arrays but no governed V2 per-operation provider claims;
- no approved Full Multilingual V2 model-profile entry has been created;
- no real legacy-font transformation mapping/profile has been supplied, because guessing one is prohibited;
- no V2 generation/alias set exists;
- no production composition root can select V2 until those governed inputs exist.

These are evidence/configuration prerequisites, not reasons to weaken the implementation.

## 6. P2 implementation status

The V2 evaluator retains grounded-query, qrel, corpus-census, runtime-parity, ranking-digest, stage and failure contracts. Sanitized stage observability exists at the application boundary. Full corpus-specific qrels, full per-stage instrumentation, scalable cohort materialization, PDF font metadata adapters, and future OCR/Vision observation adapters remain post-configuration/evaluation work. Historical WP-10/WP-16 scripts and transcripts were not edited.

## 7. Language-genericity audit

New production modules contain no hard-coded English/Hindi/Marathi language branch or allowlist. A focused source scan returned `NO_HARDCODED_EN_HI_MR_MATCHES_IN_NEW_V2_PRODUCTION_MODULES`. BCP-47-compatible language values and ISO-15924-compatible script values are separate types. Registries select implementations from governed observations/profiles, not filename, title, language, or script shortcuts.

Legacy profile arrays and V1 regression implementations remain intact. They are explicitly not projected as governed V2 claims.

## 8. Hardcoded-language audit

EN/HI/MR occurrences remain only where they are legitimate historical profile scope, V1 behavior, fixtures, or regression examples. `provider_language_claims_from_profile()` ignores legacy arrays and projects only explicit claim records. A provider claim is evidence of `MODEL_SUPPORTED` only; it does not admit retrieval or advance runtime lifecycle.

## 9. Representation/transformation audit

The implementation independently models language, script, and representation. It supports Unicode semantic text, legacy-font encoded text, PDF encoding anomalies, OCR, Vision, transliteration, normalization, and unknown representation types. The generic mapping transformer is deterministic and profile-bound; it contains no document/language/filename special case. Unknown, unmatched, unavailable, or failed transforms produce no guessed output. Canonical source hashes remain immutable.

No production legacy-font mapping was invented. Consequently, affected evidence remains unavailable until an approved mapping/profile is configured and tested.

## 10. Reranker candidate-builder audit

`RerankerCandidateBuilderV1` is the V3 construction path. It validates exact notebook/source/document/version/occurrence/derivation scope before resolution, verifies authorization provenance after resolution, excludes title metadata, requires semantic tokens, applies the governed 256-token pair algorithm, and records tokenizer/model/preprocessing/token/hash audit fields. Stable ranking uses score, input ordinal, then candidate identity. The evaluator cannot submit arbitrary candidate text.

## 11. Authorization/scope audit

Authorization occurs before dense or sparse enumeration. The dense universe is capped at 10,000 authorized vectors and returned candidates at 1,000. Sparse enumeration joins an exact authorized evidence-reference digest set and applies page/section/heading constraints in SQL. Reconstructed records are checked against the authorized V3 reference. Candidate building repeats exact scope and provenance validation. Existing central authorization semantics were not changed.

The focused WP-14 security suite passed. V2 remains unexposed, so no new authorization surface is active.

## 12. Generation/activation audit

V2 uses four deterministic, side-by-side capabilities: representation derivation, language text, multilingual embedding, and multilingual vector. Source-generation dependencies, provider/model revision, preprocessing, vector space, profile fingerprint, coverage/checksum, provenance, authorization compatibility, and rollback metadata are represented. Coverage manifests bind the exact build item checksum. Alias promotion requires four complete READY generations plus four retained READY rollback generations and a rollback digest that binds the exact set. Compare-and-swap prevents concurrent active-alias drift.

No V2 generation or alias was created or activated in this work.

## 13. Capability projection audit

Capability records are operation/language/script/representation scoped and distinguish provider support, implementation, configuration, buildability, runtime state, exposure, evaluation, verification, and certification. Admission requires an available active-or-later record. Provider claims alone cannot admit work. The runtime matrix truthfully records V2 as code-present but not configured/buildable/ready/active/exposed/verified/certified.

## 14. HTTP/MCP parity audit

The stable `search_evidence` tool name is unchanged. The MCP request vocabulary includes `multilingual_text` and the pre-existing `asset_metadata` value, matching the internal Pydantic representation enum. Structured content and canonical fallback continue through the same service. Focused HTTP/capability/MCP contract and conformance tests passed. No stdio/SSE live behavioral run was performed; therefore transport verification and exposure remain false.

## 15. Evaluation/runtime parity audit

`MultilingualEvaluatorV2` accepts only a shared application protocol and an authenticated principal. `SharedRetrievalEvaluationApplicationV2` calls the same `EvidenceRetrievalApplicationService` used by HTTP/MCP. Runtime parity records forbid direct provider calls, private runtime access, and caller-built reranker inputs. Ungrounded cases are excluded; semantic cases require evidence qrels and raw rankings; `CORPUS_ABSENT` is invalid without census-proven absence.

No evaluation pack was executed and no quality score was created.

## 16. Test results

- Focused V2/runtime/storage/capability/MCP/governance run: **85 passed**.
- Updated model-profile and V2 unit run: **24 passed**.
- Final V2 unit run after activation/scope additions: **17 passed**.
- Directly affected regression run: **215 passed, 1 failed**; the sole failure was a stale expected schema version (`14` versus additive schema `15`).
- Smallest affected rerun after correcting that test: **1 passed**.
- WP-14 focused security regression: **3 passed**.
- Proposal JSON schemas: **8 Draft 2020-12 schemas passed meta-schema validation**.
- Capability matrix instance/schema: **PASS**.
- Model-profile schema: **PASS**.
- MCP contract JSON parse: **PASS**.
- `compileall`: **PASS**.
- Ruff over production and affected tests: **PASS**.
- strict mypy over 26 affected production modules: **PASS**.
- `git diff --check`: **PASS**.

Pytest emitted only local cache/temp cleanup permission warnings after results were recorded; they did not change test verdicts.

## 17. Regression results

V1 engine composition, existing multilingual V1 tests, advanced retrieval, projection generations, model profiles, SQLite storage, Phase85 runtime, capability discovery, MCP schemas/tools/conformance/server/SSE, and WP-14 security remained green in focused regression coverage. CursorCodecV2 was neither edited nor exercised through a new code path. No full repository suite or expensive benchmark was run.

## 18. Protected-state verification

Post-implementation SHA-256 values exactly match the recorded pre-implementation baseline:

| Protected artifact | SHA-256 |
|---|---|
| Frozen multimodal DB | `18835883DC3A01B588E4C43F44FBA1156941D0807D7C08C2A41FD11A802BF55D` |
| Multimodal freeze manifest | `17977EFC87D3D95BB1E2E6E6C8025E78B63A4C3A0A301F98869B44724FEF5A8F` |
| Current WP-10 evaluation DB | `8FFBB367B35A313C8866E89E21F499AEEF92153D5EF6E57D362208F0C05BCA0D` |
| Golden `manuscript.pdf` | `31ADDF387D13DE26E3B155E1FC6EE65D5F554CFDFB4281951C56E9482B6F8085` |
| Golden Ramayana comparison PDF | `759F2ADBFD2FC1191FF8576401D1CBC34BBFEFA79A573E8747C53D4C858AF75` |

Protected databases were not opened by the implementation or tests; tests used disposable temporary SQLite files. Existing WAL/SHM files were not targeted. No Golden Dataset file, canonical text, OCR/Vision/CLIP artifact, V1 vector space, model artifact, freeze manifest, MCP configuration, or CursorCodecV2 code was changed. Models loaded/downloaded: **NO**. Benchmarks executed: **NO**.

## 19. Known limitations and concrete blockers

1. No governed V2 provider claims are present in the selected frozen profile. Legacy `languages`/`scripts` arrays intentionally do not count.
2. No approved generic transformation profile exists for the corpus's legacy-font evidence; implementation cannot guess its mapping.
3. No isolated V2 database/generation set exists.
4. No real provider readiness or artifact-identity probe was run in this implementation pass.
5. No complete corpus/evidence census, V2 qrels, or post-implementation quality evaluation exists.
6. No live HTTP/stdio/SSE parity evidence or pre-exposure security certification exists for V2.
7. Numeric quality/certification gates remain separately governed and open.

These blockers keep the actual runtime fail-closed. They do not justify substituting models, adding corpus files, fabricating transformations, or promoting historical evaluation results.

## 20. Is V2 indexing authorized to begin?

**NO.** The implementation has reached a safe code checkpoint, but the authoritative runtime is not CONFIGURED or BUILDABLE for V2. Before isolated indexing can be authorized, governance/operator configuration must supply and approve:

1. a separate V2 model profile with explicit per-operation provider claims and immutable claim-source digests;
2. approved representation/transformation profiles required by the immutable corpus;
3. provider artifact/readiness evidence bound to exact model revisions;
4. a named disposable V2 database target verified not to be any protected database;
5. completion of the remaining provider, transformation, generation interruption/recovery, negative scope, and live transport preflight tests applicable to that configuration.

Only after those prerequisites pass may the four V2 generations be built in the isolated database. READY, ACTIVE, EXPOSED, EVALUATED, VERIFIED, SECURITY VERIFIED, BEHAVIORALLY VERIFIED, and CERTIFIED remain false until their distinct evidence gates are satisfied.
