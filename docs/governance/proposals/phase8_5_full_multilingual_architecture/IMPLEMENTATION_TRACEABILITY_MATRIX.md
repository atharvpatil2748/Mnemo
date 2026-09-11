# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Full Multilingual V2 Implementation Traceability Matrix

| Requirement / discovered defect | Architecture contract | Future module seam | Mandatory proof | Rollback |
|---|---|---|---|---|
| Marathi corpus falsely reported absent | `FAILURE_TAXONOMY.proposed.json`; layered evaluation | V2 evaluator/source census | Census → observations → embeddings → index trace; miss cannot emit `CORPUS_ABSENT` | Withdraw defective pack to `UNVALIDATED` |
| Title-only reranker input | `RERANKER_CANDIDATE_CONTRACT.proposed.json` | `retrieval/reranker_candidates.py`; BGE adapter; evaluator | Empty/title-only negative and actual-chunk positive tests; retained input hash | Disable V2 reranker, use explicit governed degraded RRF |
| Generic prompt treated as quality query | Evaluation architecture §4 | V2 manifest/qrel validator | `QUERY_UNGROUNDED`; excluded from ranking metrics | Correct/withdraw case, retain historical result |
| Legacy-font Hindi representation | `REPRESENTATION_TRANSFORMATION_MODEL.proposed.json` | representation detector/registry/builder/storage | Generic fixture, deterministic transform, source hash unchanged, full lineage | Disable transform generation/profile |
| EN/HI/MR hard-coded detector | Language capability model + detector protocol | `retrieval/language_detection.py`; planner | Arbitrary BCP-47, same-script ambiguity, mixed script, `und` | Select frozen baseline detector |
| Script conflated with language | Independent script observations | script detector plugin | Devanagari with multiple possible languages stays ambiguous absent language evidence | Disable language claim, preserve script observation |
| Provider support overclaimed | Operation-scoped capability schema | profile adapter/runtime/capability service | `MODEL_SUPPORTED` cannot imply READY/ACTIVE/EXPOSED | Remove provider claim/disable capability |
| Static capability advertisement | Runtime-derived capability record | capability service/schema/MCP | Runtime/HTTP/MCP parity; inactive not callable | Omit additive details/stop V2 exposure |
| Specialized transform routing | Transformation registry | phase85 representation builder/planner | Source/target compatibility and no filename/language special branch | Disable transform profile |
| Aggregate lifecycle hides language gaps | Per-record lifecycle | Phase85 runtime adapter | ADR-0074 implication tests per operation/language/representation | Return unavailable/unvalidated state |
| Evaluation layers collapse | Failure taxonomy and stage trace | evaluator/harness/observability | Inject one deterministic failure per stage and verify classification | Withdraw evaluator version |
| Authorization escape through derived text | Scope inheritance and pre-enumeration authorization | catalog, transform builder, dense source, result validator | Cross-notebook/version/occurrence denial at source and delivery | Disable V2 transform/retrieval capability |
| Vector-space mixing | Exact vector-space identity | embedding store/dense source/generation coverage | Reject V1/CLIP/wrong BGE profile vectors | Retain prior READY alias |
| L×L evaluation explosion | Stratified cohort graph | V2 manifest generator/governance | Same-language admission + approved sampled edges; unmeasured remains unvalidated | Reduce exposure, not evidence requirements |

## ADR compatibility checklist

- **ADR-0067:** original text remains authoritative; observations/transformations are derived; language-aware generations are side-by-side; authorization precedes transformation; translation stays optional.
- **ADR-0070:** evaluation is corpus/profile/hardware/direction scoped; unmeasured remains `UNVALIDATED`; mock/provider-selection results do not certify.
- **ADR-0072:** notebook identity remains propagated/resolved through existing server authorization; no transformed evidence bypass.
- **ADR-0073:** stable MCP tools, structuredContent/canonical JSON parity, provenance/completeness, signed scope-bound cursors and blind-agent verification remain.
- **ADR-0074:** one production composition root; exact profile/generation lifecycle; model presence is not readiness; capability state is runtime-derived.

## V1 compatibility checklist

- V1 storage/provider resolution and text vector space unchanged.
- Existing EN/HI/MR detector/profile/generations retained as frozen baseline.
- CursorCodecV2, citations, Final-QA replay, asset delivery and authorization semantics unchanged.
- No migration writes to protected databases; V2 construction is side-by-side.
## P0 contract-resolution traceability

| P0 | Exact production seam | Required implementation | Required tests | READY / ACTIVE / EXPOSED evidence |
|---|---|---|---|---|
| 01 | `mnemo-core/mnemo/models/multilingual.py` | Add V3 and V2→V3 adapter; preserve V2 | all kinds, non-UUID chunk IDs, lineage conditionals, round-trip | READY: typed lineage and digest validation; ACTIVE: generation rows bind V3; EXPOSED: response validation |
| 02 | new representation modules plus existing derivation stores/builders | observation/profile/registry/immutable derivation; no canonical rewrite | determinism, authority, auth, provenance, idempotency, failure | READY: registry/profile coverage; ACTIVE: complete compatible derivation generation; EXPOSED: security proof |
| 03 | provider/retrieval rerank call sites | shared builder, V3 candidate and audit; no direct text | blank/title-only rejection, token policy, hashes, stable ties, caller bypass denial | READY: builder/provider identity match; ACTIVE: shared path; EXPOSED: audit redaction/parity |
| 04 | new governed evaluator and shared application service | no private runtime/provider/auth bypass | evaluator/runtime digest parity, negative bypass tests | READY: shared path evidence; ACTIVE: retained runtime records; EXPOSED: transport parity |
| 05 | qrels/manifest/scorer V2 | evidence qrels, grounded gate, stage/census records | invalid qrel, ungrounded exclusion, corpus-absence predicate | not a READY input; VERIFIED requires governed qrels/rankings |
| 06 | `mnemo-core/mnemo/storage/multimodal_search.py` | scope before enumeration; revalidate results | cross-source/doc/version, positional, occurrence/derivation, count/timing non-enumeration | READY: authorization compatibility; ACTIVE: scoped integration; EXPOSED: WP-14 regression proof |
| 07 | `mnemo-server/mnemo_server/mcp/contracts.py`, HTTP/OpenAPI schemas, capability adapter | one vocabulary and semantic mapping | schema/digest/fixture parity across HTTP, stdio, SSE, structured/fallback | EXPOSED only after all parity checks |
| 08 | runtime/lifecycle/generation coordinator | derive combined readiness, atomic alias-set promotion/rollback | every failed dependency, concurrency, interruption, stale/mismatch, rollback | exact rules in activation-readiness schema |

Every row is additive. CursorCodecV2, MCP tool names, authorization semantics, V1 vector spaces and frozen artifacts remain unchanged.
