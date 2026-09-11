# Mnemo production corpus and serving-path resolution

**Date:** 2026-09-05

**Scope:** forensic decision only; no activation, exposure, configuration change, build, or database mutation

**Corpus decision:** `PRODUCTION_CORPUS_44_CONFIRMED`

**Serving decision:** `SERVING_PATH_REQUIRES_REMEDIATION`

**K decision:** `K50_NOT_YET_GOVERNED`

## 1. Executive summary

The governed Full Multilingual V2 production corpus is the 44-document Phase 8.5 corpus. This is not an inference from size or recency. The active V2 database contains exactly the 44 distinct content hashes in the protected Phase 8.5 manifest, and its READY/ACTIVE governance explicitly binds the build to 44 documents and 2,658 canonical chunks. The 67-document database is the union of the 44 Phase 8.5 files and 24 Phase 8.6 evaluation-source memberships, with one cross-corpus duplicate content hash; therefore it has 67 distinct documents and 68 source memberships. Phase 8.6 governance calls those additions an isolated evaluation corpus and requires Phase 8.5 to remain frozen.

The name `data/canonical_production` and the fact that `mnemo.toml` currently points to that database do not promote Phase 8.6 evidence into the governed V2 corpus. They describe the current legacy/canonical serving configuration. The canonical database has no V2 alias and no V2 generation rows; it cannot be the active V2 artifact without a separately governed build and promotion.

HTTP and MCP already converge on the same server application service, but that service invokes `KnowledgeEngine.advanced_retrieval`, not `FullMultilingualRetrievalApplicationV2`. The server-owned V2 assembler and registration boundary exist and are testable, but application startup does not instantiate them, and the active V2 runtime remains intentionally unexposed. Serving therefore requires controlled remediation before any promotion.

The corrected A/B results are useful model-selection evidence only. They used the canonical evaluation database, a custom `forensic-v1` candidate path, K=50, and each CrossEncoder's native maximum (512 for ms-marco, 8,192 for BGE). The governed V2 BGE contract is an audited 256-token pair with at most 96 query content tokens. A production-parity A/B under that exact contract remains a certification gate.

## 2. Corpus identity analysis: 44 versus 67

### Method

The two SQLite databases use different UUID namespaces, so UUID equality cannot establish corpus equivalence. The comparison joined each current document to its current version and used the version `content_hash` as the cross-database identity key. Source memberships and each database's document/version UUIDs were retained as provenance.

Results:

| Finding | Count |
|---|---:|
| Active V2 distinct documents / versions / sources | 44 / 44 / 44 |
| Canonical distinct documents / versions / sources | 67 / 67 / 68 |
| Content hashes shared by both databases | 44 |
| Active-V2-only content hashes | 0 |
| Canonical-only content hashes | 23 |
| Phase 8.5 manifest files / unique hashes | 44 / 44 |
| Phase 8.6 manifest files / unique hashes | 24 / 24 |
| Cross-manifest duplicate hashes | 1 |

The duplicate is `ME333 - Exp2-LabReport_To_Submit.docx` (Phase 8.5) / `engineering_lab_report_heat_transfer.docx` (Phase 8.6), SHA-256 `3948068a479ef85b2a5202a9ad29425aff7416f85988b9c65c5515d4163b23be`. In the canonical database it is one document/version with two source memberships, one in each evaluation notebook. Thus `44 + 24 - 1 = 67` distinct document identities and `44 + 24 = 68` source memberships.

### Why active V2 contains 44 documents

- `scratch/phase8_5_full_multilingual_v2/configuration_package/build_configuration_artifacts.py` selects `goldenDataset/Phase 8.5 Evaluation Corpus` as its corpus root.
- `V2_INDEX_BUILD_AND_READY_REPORT.md` records expected and actual `44 / 44` documents/versions and `2,658 / 2,658` canonical chunks, with the protected corpus and representation exclusions explicitly reconciled.
- The ACTIVE report binds the four generation identities and alias digest to that isolated build.
- The current active database contains all 44 Phase 8.5 content hashes and no content hash outside that set.

The 504 transformation-dependent exclusions described in READY governance do not remove source documents. The Ramayana and encoding-anomaly chunks remain preserved and provenance-bound; only unsupported transformed/vector evidence is excluded.

### Why the canonical database contains 67 documents

`data/canonical_production/mnemo_canonical.db` contains both evaluation notebooks. Its 23 additional distinct documents are exactly the Phase 8.6-only content hashes. Phase 8.6 governance designates them under `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/`, requires physical/cryptographic/generation isolation, and says Phase 8.5 remains frozen while Phase 8.6 progresses independently. Several additions are themselves evaluation/governance artifacts; one (`dcfa97c8-...pdf`) was retained as negative forensic evidence in acquisition governance. These facts are incompatible with silently treating the 67-document union as a promoted production V2 corpus.

### Exact canonical-only document/version diff

Every row below has Phase 8.6 integrity-manifest status `PASS`, belongs to notebook `86868686-8686-8686-8686-868686868686`, is absent from active V2 by content hash, and has no repository evidence of production promotion.

| # | Source file | SHA-256 | Canonical document ID | Canonical version ID | Production status |
|---:|---|---|---|---|---|
| 1 | CAND-FD-HI-HTML-01-godan.html | `9ec8a82b8795c1c09261a0f862e76f7319b1adde64ac5d02079bf9b3fa397a0f` | `7e3b8bdb-0121-402d-a11d-017a7622ffa5` | `bb44d3f7-c1a0-4c22-88b8-c815fbbc6fbe` | Evaluation-only; not promoted |
| 2 | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | `e0212854739433ca78b0fb12a855fb809476db2589af49f0509b3a56f9eff01d` | `c4cccf07-6c9a-4c25-8b50-88faaf4db783` | `76301e1d-a4d4-48d7-a054-dc648ff88320` | Evaluation-only; not promoted |
| 3 | country_codes_iso3166.csv | `67b009b529330b0a6043551189f43faa785c9c3cc0011ad2bdb4eac876356c43` | `619e6228-0ffd-4070-98bd-786a2c2f9c62` | `6653e98c-2fa7-44dc-98f2-cec478c157d2` | Evaluation-only; not promoted |
| 4 | dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf | `a55e99f584ea0c1a5b9dece668c57e423c223a54dbcc0836ed683a6cb59345db` | `ba83cdf3-dcab-40c3-9fdc-6fa3d9759a2c` | `01732d59-e11b-404d-a9b6-95116f1f7f45` | Negative forensic evidence; not promoted |
| 5 | godan_chapter_2_hindi.html | `8af70f1353c9256936234f0678e435d9f5cc7c080578eb39cc7fe3372c9b8279` | `1d0c3656-d3d6-4848-93d7-a70746a95966` | `1d6c6c24-c9f6-4029-bb9b-b2c1eb2b6003` | Evaluation-only; not promoted |
| 6 | godan_chapter_3_hindi.html | `7e144e26e1347e0717b81072ae95aa8946dff5a75c5d7a108148755a056302c7` | `ac447d04-24a2-4bee-8bd1-e14beb47451a` | `fb2df722-19af-4f33-92a5-0175d77dc4d2` | Evaluation-only; not promoted |
| 7 | mahades_economic_survey_ch1_marathi.pdf | `fb8fe6e0185476875342de5140388ddfc0c467c412a10343e84011f2351914a0` | `b7772f9c-4b1f-4c25-8e30-1d1b85b0b9e1` | `4339c4cc-10c9-4c63-a1a6-adddc5a20cfd` | Evaluation-only; not promoted |
| 8 | mahades_economic_survey_ch2_marathi.pdf | `38bb74635f120c6d34e48a838f83b488cfabdabdcbc506525b9b6169f6ad6a59` | `5083333e-4741-49db-b6f1-62338e635efa` | `c189a32c-359c-448b-99e0-74da3c2f7888` | Evaluation-only; not promoted |
| 9 | mahades_economic_survey_highlights_marathi.pdf | `53f94cdb7acb9caa2066aca6061d3ddff83407a20da5cabfd990df3815ab1e9e` | `be66dc63-1370-4932-ac33-39da3b554718` | `56aecdd5-421e-4b0d-9f6e-5068d7b6186e` | Evaluation-only; not promoted |
| 10 | ml_decision_tree.pptx | `5ba07e5df8a57f9c102df3b28796f8555f17f5cde6be1ef68d77b5572d0c6039` | `a51f28fe-0a1c-43d9-9de4-6cc6745bed8c` | `3d2884d2-2272-4b52-953c-1b087fee7f8b` | Evaluation-only; not promoted |
| 11 | ml_linear_regression.pptx | `003f90fd83a6d24b39245e5c7246b186b95004a3f22a4210d37ab72bbaf4e150` | `a8b9e26d-cf11-4333-af41-ad3adb429b2a` | `168f3e73-c962-4048-96e4-e0b91192660a` | Evaluation-only; not promoted |
| 12 | ons_uk_consumer_price_inflation.xlsx | `a4da62c5e91e6ae728c06268bf408d11aa9e5d6a9b5d756e159b88836cee8843` | `a4c4688a-ec2c-46a4-84ef-b2ba300150a3` | `c491536a-d13d-4b65-bf3d-e24932aa3fcd` | Evaluation-only; not promoted |
| 13 | ons_uk_gdp_quarterly_tables.xlsx | `f70f12a1773a39e714c3959a6c687911c86f7f2e1c4047cdbd47e8756d59f5b6` | `8682bc44-fc06-4cbf-afe2-0b8aceb190ed` | `666a7c38-e903-45cf-829c-14709d6a59c5` | Evaluation-only; not promoted |
| 14 | pep8_python_style_guide.md | `6028935c6cb2c674d5f4d512c7ba6ce2923713b1c47ce1a78adc690db817fc5d` | `df647d28-08b2-4a17-b9a7-9b8589874989` | `f5af8bf0-7c71-48bc-9be7-e914d0bbcd01` | Evaluation-only; not promoted |
| 15 | PHASE8_6_ACQUISITION_MANIFEST.proposed.json | `ad08573444cf7c42a611f2509fc131f0966eaa3e303b59fad266427b1b9fe550` | `27b4720f-63d6-4843-aa79-649fb95c3c05` | `3d2027bd-5e5c-419a-85be-72d768ccd0df` | Governance/evaluation artifact; not promoted |
| 16 | PHASE8_6_EVALUATION_REPORT.md | `3014042e8c71cb24e9ee619f152116a97271686f786599f17bb07493cd47963b` | `bf342e28-0335-44c4-9bce-421a78ef9fe2` | `c2d30234-dd0c-451e-b08f-f757899370e9` | Evaluation artifact; not promoted |
| 17 | PHASE8_6_GENERALIZATION_TEST_REPORT.md | `08dcc0d39f357d35739f278af6028ebf61b86d7be79b4e210deb3d8fdf67a3d9` | `e63dbca3-f16b-4e56-a018-730df2bade07` | `2ae42bf8-7df3-49f0-a633-0bd1fd4b64be` | Evaluation artifact; not promoted |
| 18 | rbi_annual_report_hindi_governance_2024.pdf | `15ad4104558638d4746c2f1a94e4736e72f92062cd0dfd7383259d8ed510e7cb` | `18bf8cfb-e6c7-40c4-9e87-65d89e39fea8` | `61b820de-d45e-46b2-9387-7b041cdffe6f` | Evaluation-only; not promoted |
| 19 | rbi_annual_report_hindi_payment_systems_2024.pdf | `4d480e13305506df7f74db96ebee0078576848963c650c74c94d1587bbff5f2b` | `6f0c5e4c-6540-4090-824a-9e6831ad8f96` | `c2ef3430-7d9b-416c-a4bb-5b32b9c4ca57` | Evaluation-only; not promoted |
| 20 | shetkaryacha_asud_pan_2_marathi.html | `f651a9366caffa9a17b582b665385dd046111c735868c362c5d3f0513b8ca764` | `bb9b60d2-24f6-4111-b523-f601ac27dea6` | `d68b0b67-f882-4812-bcd5-d111f237bb34` | Evaluation-only; not promoted |
| 21 | shetkaryacha_asud_pan_3_marathi.html | `1d7fa4ea71970097139b898cbced77a88ef676cb70bb9e5ec80d8f9694c2d1a2` | `fe0b67bf-1365-4fb8-a1cd-905a3d00f365` | `e94f8421-1253-4ce7-88b7-222508099c39` | Evaluation-only; not promoted |
| 22 | world_countries_metadata.json | `99e62411349a991d0e26725aec22375ccd7e3381c723d92004a4fcb6aac1c34e` | `3c4b543a-b9fc-4a26-9239-bb29c40f5ead` | `2f80042c-75db-4795-8183-ca05ffdf6c82` | Evaluation-only; not promoted |
| 23 | world_gdp_historical.csv | `8d84ef6bcaccf740c01c5ed7566aae8f7b149d0e2c20001e441efd3cb5b2fa86` | `84aee9d5-43ac-4bfc-8505-18909b4f2a88` | `39bd22be-93c2-4abd-ab44-ccd1246ce554` | Evaluation-only; not promoted |

The machine-readable artifact includes the source UUID for each row and the duplicate's two source memberships.

## 3. Corpus decision

`PRODUCTION_CORPUS_44_CONFIRMED`

This decision is specifically the authoritative corpus for the governed active Full Multilingual V2 generations. It does not claim the current public server already serves that corpus. The current public server points at the 67-document canonical evaluation/legacy database, which is one of the serving-path discrepancies to remediate. Adding Phase 8.6 documents to production would require a new isolated governed build and controlled promotion; it must not mutate the active 44-document build.

## 4. Current HTTP serving path

### Ranked evidence endpoint

```text
POST /v2/retrieval/evidence
  -> routers.retrieval_v2.search_evidence
  -> principal_from_claims(request.state.auth)
  -> EvidenceRetrievalApplicationService.execute
  -> CentralAuthorizationServiceV1.authorize_notebook(RETRIEVE)
  -> EvidenceSearchRequest.to_plan
  -> KnowledgeEngine.advanced_retrieval.execute
  -> AdvancedRetrievalService (canonical/projected sources)
  -> configured canonical reranker (mnemo.toml: ms-marco)
  -> EvidenceSearchResponse
```

This endpoint returns ranked evidence. It does not invoke ContextBuilder or answer generation.

### Grounded-answer endpoint

```text
POST /v2/notebooks/{notebook_id}/final-qa
  -> FinalQAV2ApplicationService.execute
  -> CentralAuthorizationServiceV1.authorize_notebook(FINAL_QA)
  -> FinalQAV2ApplicationService._retrieval_result
  -> KnowledgeEngine.advanced_retrieval.execute
  -> candidates_from_retrieval
  -> KnowledgeEngine.final_qa_v2
  -> MultimodalContextBuilder
  -> LLMFinalQAV2Provider
  -> persisted Final-QA response
```

The Final-QA retrieval call constructs its retrieval plan without propagating the server principal into the Full Multilingual V2 authorization boundary. This is safe only because the active V2 path is not currently installed; it is not suitable for exposing that path unchanged.

## 5. Current MCP serving path

```text
search_evidence
  -> mcp.tools._handle_search_evidence
  -> EvidenceRetrievalApplicationService.execute
  -> same KnowledgeEngine.advanced_retrieval path as HTTP

run_final_qa_v2
  -> mcp.tools._handle_final_qa_v2
  -> FinalQAV2ApplicationService.execute
  -> same retrieval/context/answer path as HTTP
```

HTTP and MCP share services today, which is good. The shared service is the wrong service for Full Multilingual V2 serving parity.

## 6. Full Multilingual V2 application path

`FullMultilingualRetrievalApplicationV2` and all five production adapters are buildable. `ProductionFullMultilingualV2ServerDependencyAssemblerV1` composes the read-only V2 store, active-generation inspector, central principal-based authorizer, authorized enumerator, evidence resolver, governed candidate projector/builder, embedder, reranker, admission, and query-language resolver. `ServerOwnedFullMultilingualV2RegistrationV1` can compose an internal runtime.

However:

- `mnemo_server.app` constructs `KnowledgeEngine` without a V2 source, V2 readiness snapshot, server assembler, or server registration.
- No non-test startup path instantiates the server-owned V2 assembler/registration.
- `KnowledgeEngine` only adds the Full Multilingual V2 source when readiness says `v2_exposed`; otherwise it retains the canonical/projected sources.
- Governance still says `EXPOSED: FALSE`.

Therefore the V2 application is buildable and internally composable, but is not initialized by production startup, reachable through HTTP/MCP, or exposed. Existing tests prove composition with fakes, not a real transport traversal.

## 7. Future serving target (defined, not activated)

Repository package direction and the server-owned registration contract support one future target:

```text
HTTP search / MCP search
  -> one server-owned retrieval application service
  -> server-derived PrincipalContextV1
  -> CentralAuthorizationServiceV1 + V2 bounded authorization
  -> active 44-document V2 alias/generation binding
  -> authorized BGE-M3 + V2 language-text retrieval
  -> RRF k=60
  -> governed 256-token candidate contract
  -> governed BGE reranker runtime
  -> evidence response

HTTP Final-QA / MCP Final-QA
  -> the same retrieval application service
  -> one reconciled ContextBuilder contract
  -> grounded answer generation
```

This target does not authorize routing, exposure, model activation, or configuration changes.

## 8. Reranker contract reconciliation

| Item | Current governed production contract | Corrected A/B evaluation contract |
|---|---|---|
| Model | BGE-reranker-v2-m3 revision `953dc6f...` | Same BGE revision in candidate arm; ms-marco revision `233902d...` in control |
| Model context ceiling | 8,192 | Native CrossEncoder ceiling: BGE 8,192; ms-marco 512 |
| Pair ceiling | 256 audited tokens | Not applied |
| Query content cap | 96 tokens | Not applied as the V2 audited-pair algorithm |
| Candidate text | Governed semantic text, token IDs audited by `RerankerCandidateBuilderV1` | Same contextual source text between arms, then model-native tokenization/truncation |
| Provenance | V2 candidate contract and runtime binding | Identity-bound evaluation record, not V2 runtime binding |

`CURRENT_GOVERNED_CONTRACT`: `bge-reranker-v2-m3-pair-256-v2`; 256 total pair tokens, query content capped at 96, special-token accounting explicit, no silent title-only substitution.

`EVALUATION_CONTRACT`: `forensic-v1` candidate generation at K=50, contextual provider text, raw `sentence_transformers.CrossEncoder` scoring, BGE maximum 8,192 and ms-marco maximum 512.

`DISCREPANCY`: the evaluation bypassed the governed V2 pair builder/audit and did not constrain both arms to the production pair contract. It also used different model-native maximum lengths. Hence its identity-bound relevance and frozen-candidate comparison are valid within that experiment, but its scores do not establish behavior under production's 256-token inputs.

`REQUIRED_VALIDATION`: rerun paired identity-bound A/B through the exact production candidate builder/token audit at 256 tokens, with the selected 44-document V2 artifact and otherwise identical candidate pools. Then run the selected reranker through the composed V2 application.

## 9. Production BGE runtime discrepancy

Current governed/code behavior is CPU, not CUDA:

- `BGE_RERANKER_MAX_BATCH = 16`.
- `CrossEncoder(..., device="cpu", max_length=256)`.
- prediction batches use 16.
- the architecture audit explicitly describes CPU and says device should become a governed execution-profile field.

The validated evaluation behavior was CUDA on an RTX 4060 with batch size 2 and no CPU fallback. No repository governance currently makes that evaluation execution profile the production execution profile.

To achieve parity later, the server must receive an explicit, governed, validated execution profile containing device, batch size, fallback policy, resource limits, and model snapshot identity. The provider adapter must consume that profile instead of hard-coded CPU/16, while preserving the 256-token candidate contract. CUDA batch 2 should not be installed by implication from an evaluation script.

## 10. K=50 status

`K50_NOT_YET_GOVERNED`

K=50 belongs to the corrected A/B experiment. The production interface exposes request budgets: `candidate_budget` defaults to 100, `evidence_budget` defaults to 50, the server caps candidates at 1,000, and `RetrievalPlanV2` derives recall/fusion/rerank limits (rerank maximum 200). The Full Multilingual V2 application consumes those plan budgets. There is no frozen production K=50 setting or approved K=50 promotion record. ContextBuilder consumes reranked results and does not establish the retrieval candidate-pool K.

## 11. ContextBuilder failures

The authoritative compression contract remains ADR-0043:

- target 100 tokens;
- hard maximum 120 tokens;
- provider `max_tokens=120`;
- malformed output, registered provider failure, and input-window violation propagate with no partial result;
- only provider absence is graceful compression degradation;
- a valid compression that does not fit is omitted.

Current `retrieval/context.py` has drifted to hard maximum 200, output budget 300, and catches `IntegrityError`/`ContractValidationError` to omit candidates. `CompressionEvidence` and the tests still enforce ADR-0043's 120/fail-hard contract.

| Failing test | Expected contract | Actual behavior/root cause | Smallest correction | Affected component |
|---|---|---|---|---|
| `test_compression_uses_exact_prompt_schema_and_canonical_json` | Provider `max_tokens` equals hard max 120 | Call uses output budget 300 while runtime hard max is 200 | Restore `max_tokens=120` and hard max 120 | ContextBuilder provider call |
| `test_compression_over_hard_maximum_is_rejected_without_truncation` | 121 tokens raises `IntegrityError` at builder boundary | 200-token check accepts it, then `CompressionEvidence` raises raw `ValueError` at 120 | Restore 120 check and mapped `IntegrityError` | Validation/model boundary |
| `test_malformed_compression_output_fails[""]` | Malformed output propagates `IntegrityError` | Error caught and candidate omitted | Remove validation-error omission catch | ContextBuilder failure policy |
| `test_malformed_compression_output_fails[42]` | Same | Same | Same | Same |
| `test_malformed_compression_output_fails[surrogate]` | Same | Same | Same | Same |
| `test_extra_or_missing_structured_fields_fail` | Schema violation propagates `IntegrityError` | Error caught and candidate omitted | Remove validation-error omission catch | Structured output validation |
| `test_context_window_rejection_occurs_before_provider_call` | Pre-call `ContractValidationError` propagates | Error caught and candidate omitted | Remove contract-error omission catch; retain pre-call check | Context-window enforcement |

Classification: implementation/contract drift, not seven test defects. The smallest correction is to restore the accepted ADR-0043 values and propagation semantics. Any desired 200/300/graceful-failure policy would require a new governed ADR/version rather than silently changing V1.

Focused rerun: **27 passed, 7 failed** (`pytest ... test_context_builder.py --no-cov`). The earlier broader focused suite remains **80 passed, 7 failed**; its separate coverage failure is not a functional test failure.

## 12. Evaluation versus production parity matrix

| Component | Evaluation state | Production state | Match? | Required action |
|---|---|---|---|---|
| Corpus | 67-document Phase 8.5+8.6 union | Governed active V2 corpus is 44 Phase 8.5 documents; current public legacy DB is 67 | No | Certify against 44; do not promote Phase 8.6 without a new build decision |
| Database | `mnemo_canonical.db`, no V2 generations/alias | Isolated active V2 `mnemo.db`, four active generations | No | Use active read-only V2 artifact for parity evaluation |
| Embeddings | Canonical NPZ/cache, BGE-M3 | 3,019 governed `multilingual_embeddings_v2`, BGE-M3 | Model yes; artifact/path no | Exercise production store/generation resolver |
| FTS5 | Canonical `fts_chunks` | V2 `language_text_fts_v2` | No | Exercise authorized V2 sparse source |
| Candidate generation | Evaluation `forensic-v1` | Full V2 dense+sparse enumerators and authorized evidence resolution | No | Run through composed application |
| RRF | k=60 | k=60 | Algorithm constant yes; inputs/path no | Assert identical production-path fusion |
| K | Experimental 50 | Request-driven default candidate budget 100; rerank cap 200 | No | Govern K only after production-parity evidence |
| Reranker | A/B ms-marco vs BGE | Public legacy uses ms-marco; unexposed V2 profile selects BGE | No | Complete parity gate, then separate promotion decision |
| Reranker tokens | Native 512/8,192 | Audited pair max 256, query max 96 | No | Rerun at governed pair contract |
| Reranker device | CUDA | V2 BGE adapter hard-coded CPU | No | Govern execution profile; validate resources/no fallback |
| Reranker batch | 2 | 16 | No | Govern and validate production batch setting |
| ContextBuilder | Not part of reranker A/B | V1 ContextBuilder is inconsistent; Final-QA V2 uses MultimodalContextBuilder | No | Restore/approve one authoritative contract and test it |
| Answer generation | Not evaluated by A/B | Ollama synthesizer through Final-QA paths | No | Run grounded-answer parity after context reconciliation |
| Authorization | Evaluation harness, no serving principal | Central authorization plus V2 bounded decision exists internally | No | Test server principal through real V2 transport path |
| HTTP | Not exercised | Routes to `KnowledgeEngine.advanced_retrieval` | No | Route shared service only after pre-exposure approval |
| MCP | Not exercised | Same legacy service as HTTP | No | Keep shared service and validate parity after remediation |
| Multimodal | Row/linkage audit only; no quality A/B | Canonical projected multimodal path; active V2 has separate governed evidence | No | Run authorized modality-specific retrieval tests |
| Model aliases | Explicit local A/B revisions | Root production reranker remains ms-marco; V2 profile has BGE | No | Do not activate until gates pass |
| Configuration | Scratch CLI experiment | `mnemo.toml` points to canonical DB and ms-marco | No | Controlled configuration package after authorization |
| Manifests | Phase 8.5/8.6 integrity manifests | Active V2 build/coverage/alias manifests | No | Bind all certification evidence to active V2 manifests |

## 13. Remaining certification gates

1. **Corpus authority gate — resolved here:** 44-document Phase 8.5 corpus is the governed V2 production corpus.
2. **Context contract gate:** restore ADR-0043 or approve a new version; make all context tests pass.
3. **Production-pair reranker gate:** rerun paired evaluation at the exact 256-token candidate contract on the 44-document active V2 corpus.
4. **Production runtime gate:** govern and validate the BGE execution profile (device, batch, memory, offline snapshot, no silent fallback).
5. **K/budget gate:** decide and freeze production candidate budgets; K=50 is not yet governed.
6. **Application composition gate:** instantiate the server-owned V2 assembler at startup against the active alias without exposing it.
7. **Authorization gate:** prove server-derived principals and bounded V2 decisions precede all enumeration in the composed runtime.
8. **Retrieval parity gate:** run identity/qrel evaluation through `FullMultilingualRetrievalApplicationV2`, including dense, sparse, RRF, provenance, failure taxonomy, determinism, and latency.
9. **Multimodal gate:** test authorized visual/OCR/Vision retrieval quality where evidence exists; do not infer quality from row counts.
10. **Shared transport gate:** prove HTTP and MCP invoke the same application and return equivalent authorized evidence; prove Final-QA reuses it.
11. **Controlled exposure/activation gate:** only after preceding gates, authorize configuration/alias changes and post-change smoke tests.
12. **Rollback and certification gate:** exercise rollback, reverify protected state, and issue a separate lifecycle certification decision.

## 14. Exact decisions

```text
PRODUCTION_CORPUS_44_CONFIRMED
SERVING_PATH_REQUIRES_REMEDIATION
K50_NOT_YET_GOVERNED
```

Lifecycle remains:

```text
DECLARED: PASS
IMPLEMENTED: PASS
CONFIGURED: PASS
BUILDABLE: PASS
READY: PASS
ACTIVE: PASS

EXPOSED: FALSE
EVALUATED: FALSE
VERIFIED: FALSE
CERTIFIED: FALSE
```

## 15. Protected-state verification

This task performed read-only SQLite queries, source inspection, and one focused test run. It changed only this report and its machine-readable companion.

| Artifact | Before/after evidence |
|---|---|
| Phase 8.5 corpus | 44 files, 192,641,461 bytes, tree digest `77ba2eca242c8d7486e87e1c5f08b554494785c795d3c93abaa4c2c3aa282e5b` |
| Phase 8.6 corpus | 24 files, 29,956,652 bytes, tree digest `137e14f24f99fa415fc36bc38d363ca2329a74c2fc9c92933d192f638d96e0d4` |
| Canonical DB | `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`; integrity `ok`; FK violations 0 |
| Active V2 DB | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`; integrity `ok`; FK violations 0 |
| Active V2 alias | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` |
| Root production configuration | `mnemo.toml` SHA-256 `7d94649efe9540eac1abfc197769c0875f48161d4c9ec191b73560e97d499083` |
| Model snapshots | Governed BGE-M3, BGE reranker, and ms-marco revisions remain present; no model file was opened for inference or written |

No ingestion, indexing, embedding generation, provider inference, evaluation, alias update, configuration change, exposure, or activation occurred.
