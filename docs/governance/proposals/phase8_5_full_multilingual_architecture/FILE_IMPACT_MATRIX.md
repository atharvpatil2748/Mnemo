# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Full Multilingual V2 File Impact Matrix

No listed change is authorized by this proposal. Paths marked “new” are conceptual future modules and may be adjusted during Stage 0 review.

## A. MUST CHANGE

| Priority | File/module | Current responsibility / defect | Required future change | Risk and required tests | Frozen-state contact |
|---|---|---|---|---|---|
| P0 | `mnemo-core/mnemo/models/multilingual.py` | Generic source/embedding records, flat capability state, current candidate wrapper | Add operation-scoped language capability facts and typed `MultilingualRerankCandidateV3`/audit records without replacing V1/V2 models | Serialization/identity risk; property, compatibility, title-only rejection tests | None; models only |
| P0 | `mnemo-core/mnemo/interfaces/multilingual.py` | Provider protocols; reranker accepts `MultilingualCandidate` | Add capability, detector/script, representation, candidate-builder protocols; version rather than break existing protocols | Adapter compatibility and type tests | None |
| P0 | `mnemo-core/mnemo/retrieval/multilingual.py` | EN/HI/MR detector, two-script detection, Devanagari planner branch, fusion/rerank | Consume registries/capabilities and shared candidate builder; retain baseline detector/transliterator plugin | High behavior risk; EN/HI/MR regression, ambiguity, auth, vector separation, RRF tests | Reads immutable evidence only |
| P0 | **new** `mnemo-core/mnemo/retrieval/reranker_candidates.py` | Candidate construction is duplicated; evaluation could pass title-only text | Central deterministic builder and audit; semantic text required; exact provenance/preprocessing/truncation | Critical; positive actual-content test and all invalid-input invariants | None |
| P0 | `mnemo-core/mnemo/retrieval/multilingual_providers.py` | BGE adapter uses candidate content but cannot enforce all external call sites; profile language list may be overread | Accept typed candidate contract only; expose provider claims separately; retain exact BGE behavior/revisions | Model contract/readiness/tie/truncation tests; no V1 fallback | Models read-only |
| P0 | **new governed V2 evaluator modules** | Historical scripts independently render candidate text and are invalid as a V2 production-parity harness | Use shared builder/application service; retain input hashes/audits | Evaluation validity; title-only regression and production/eval parity | Historical scripts and output untouched |
| P0 | `mnemo-server/mnemo_server/services/capabilities_v2.py` | Static `("en", "hi", "mr")` public semantics | Derive per-operation language/script/representation state from runtime registry; retain aggregate compatibility summary | False-advertisement/no-leakage/runtime consistency tests | None |
| P0 | `mnemo-core/mnemo/phase85/runtime.py`, `phase85/models.py` | Aggregate ADR-0074 lifecycle | Derive exact language-operation capability records from existing runtime/profile/generation authority | Lifecycle drift risk; implication and degradation tests | None |
| P1 | **new** `mnemo-core/mnemo/models/text_representations.py` | No first-class generic legacy/font/normalization representation | Add immutable representation observation/reference/transformation records | Provenance/security risk; strict validation/hash tests | Never mutates source |
| P1 | **new** `mnemo-core/mnemo/interfaces/text_representations.py` | No representation detector/transform protocols | Add `RepresentationDetectorV1`, `RepresentationTransformerV1`, registry/readiness protocols | Provider trust and lifecycle tests | None |
| P1 | **new** `mnemo-core/mnemo/retrieval/representations.py` | Only direct normalization/Devanagari transliteration | Capability/policy-driven representation detection/selection; no filename/language hard-code | Legacy fixture, unknown, mixed, no-script→language tests | Derived-only |
| P1 | `mnemo-core/mnemo/phase85/multilingual.py` | Fixed detector/transliteration generation plan | Manifest-driven dependency/coverage; consume representation generation; retain old identities | Generation compatibility/idempotency tests | New isolated DB only |
| P1 | **new** `mnemo-core/mnemo/phase85/representations.py` | No governed generic transform builder | Authorized, restart-safe representation generation | Crash/resume, checksum, source binding, authorization | New isolated DB only |
| P1 | `mnemo-core/mnemo/storage/multilingual.py` | Immutable multilingual records, no representation/capability coverage storage | Add storage APIs or derived manifest records; preserve existing payloads | Schema/migration/authorization tests | Never current/frozen DB |
| P1 | `mnemo-core/mnemo/storage/projection_generations.py` | Generic generations but limited coverage dimensions | Validate representation/language/script/operation coverage and transform dependencies before READY/alias | Partial/stale/rollback tests | New isolated DB only |
| P1 | `mnemo-core/mnemo/retrieval/multilingual_advanced.py` | Constructor receives fixed target languages | Resolve authorized active targets/capabilities; truthful unavailable/degraded outcome | Bounds/cursor/provenance tests | None |
| P1 | `mnemo-core/mnemo/engine.py` and production composition | Composes current fixed services | Compose one registry/builder/transform set through `Phase85RuntimeV1`; no adapter-local services | Duplicate provider/startup/shutdown tests | None |
| P1 | `config/model_profiles/model_profile.schema.json` plus a **new future profile** | Static current languages/scripts | Represent provider claims, detector/transform requirements and evidence source/version | Config digest/no-secret validation | Existing frozen profile unchanged |
| P1 | `mnemo-server/mnemo_server/schemas/capabilities_v2.py` | Flat `supported_languages` | Add versioned per-operation language/representation facts and reasons | Strict schema/JSON fallback parity | None |
| P1 | MCP/HTTP retrieval/capability adapters if schema extension requires | Stable public surface | Pass through shared services only; no transport business logic | HTTP/MCP and stdio/SSE parity | None |
| P2 | `mnemo-server/mnemo_server/evaluation/blind_agent.py`, evaluation schemas/harness | Behavioral layer lacks full stage diagnostics | Consume governed manifest and stage trace; keep blindness and protected transcripts | Redaction/oracle/no-private-hint tests | Historical transcripts immutable |
| P2 | `evaluation/` future V2 manifests/qrels | EN/HI/MR-specific evaluation | Topic-grounded scalable cohorts, failure taxonomy, raw-input retention | Schema/digest/metric/failure attribution tests | V1 pack immutable |
| P2 | multilingual/core/server test files | Baseline examples encode current scope | Retain baseline tests; add generic parameterized and representation/reranker regressions | Full targeted regression | Fixtures only |

## B. SHOULD CHANGE

| Priority | File/module | Why | Constraint |
|---|---|---|---|
| P2 | PDF parser metadata adapter (`mnemo-core/mnemo/parsers/pdf.py` or separate analyzer) | Surface font/encoding metadata needed by representation detection if not already available | Add metadata/derived analyzer only; do not alter extracted canonical text |
| P2 | OCR/Vision integration adapters | Map existing derived text into generic representation/language observations | Do not modify frozen OCR/Vision records or claim detector metadata as authoritative |
| P2 | operational diagnostics/observability modules | Emit redacted stage counts, profile/generation IDs, failure codes and hashes | No raw protected text, filesystem paths, credentials or cross-scope IDs |
| P2 | model profile interfaces/tests | Validate provider-claim source/revision and operation intersection | Claims are not readiness |

## C. MAY CHANGE ONLY IF A CONCRETE DEFECT IS FOUND

- Advanced retrieval candidate models: only if the typed reranker contract cannot wrap existing `EvidenceCandidateV2` without loss.
- SQLite base schema/bootstrap: only for additive tables in isolated V2 databases, never migration of protected databases.
- MCP request DTOs: only if an optional versioned language/representation hint is necessary; arbitrary client input remains untrusted.
- Final-QA language policy: only if capability lookup cannot be injected through the existing profile gate.

## D. MUST NOT CHANGE

- `goldenDataset/Phase 8.5 Evaluation Corpus/**`, including `manuscript.pdf`, the Ramayana PDF, and all filenames.
- `scratch/phase8_5_wp16/eval-20260828-01/mnemo.db`, its WAL/SHM and `multimodal_freeze_manifest.json`.
- `scratch/phase8_5_wp10_stage2/eval-20260829-01/mnemo.db` and retained current evaluation evidence.
- Canonical `Chunk.text`, source hashes, original assets, frozen OCR/Vision/CLIP outputs and generation identities.
- V1 vector space/Qdrant collection/retrieval semantics.
- `mnemo-core/mnemo/cursors.py` / CursorCodecV2 semantics.
- WP-14 principal, notebook/version/occurrence authorization and non-enumerating denial semantics.
- Existing MCP tool names and canonical structuredContent/JSON-fallback equivalence.
- The fields, validation and serialized meaning of `LanguageEvidenceReferenceV2`; only a separate V3 type and lossless V2→V3 adapter may be added.

## E. Modules reusable without semantic redesign

`ProjectionGenerationSpec`, active alias/rollback mechanics, `LanguageEvidenceCatalogV2`, `LanguageEvidenceReferenceV2`, `EvidenceCandidateV2`, dense cosine/vector isolation, deterministic RRF, provider lifecycle methods, server-owned principal resolution, provenance validation, completeness envelopes, and V2 cursor contracts.
## F. P0 correction to implementation scope

| Priority | File/module | Required V2 work | Compatibility rule |
|---|---|---|---|
| P0 | `mnemo-core/mnemo/storage/multimodal_search.py` | Apply requested source/document/version/position/occurrence/derivation scope before projected multilingual FTS enumeration and revalidate lineage after retrieval. | Preserve existing authorized V1 semantics; V2 remains unexposed until negative tests pass. |
| P0 | `mnemo-core/mnemo/models/multilingual.py` or additive sibling | Add V3 evidence reference and V2 adapter; do not redefine/remove V2. | Existing V2 values and persisted identities remain valid. |
| P0 | new `mnemo-core/mnemo/models/text_representations.py` and service/provider modules | Typed observations, profiles, registry and derived references. | Canonical evidence and OCR/Vision records are read-only inputs. |
| P0 | new shared reranker candidate-builder module plus existing provider call sites | Resolve authorized semantic evidence and emit V3 candidate/audit. | Existing public provider interface may be versioned additively; title metadata cannot substitute. |
| P0 | new governed V2 evaluator modules | Invoke shared application path; evidence qrels and stage records. | Historical scratch evaluators/reports are immutable and excluded from V2 certification. |
| P0 | `mnemo-server/mnemo_server/mcp/contracts.py`, `mnemo-server/mnemo_server/schemas/retrieval_v2.py`, OpenAPI/capability schema generation | Canonical representation vocabulary and cross-transport parity. | Tool names and existing meanings do not change; additive `multilingual_text` support only. |
| P0 | Phase85 runtime/generation coordinator modules | Combined readiness snapshot and atomic alias-set transition. | `Phase85RuntimeV1` remains sole authority; no second registry/state machine. |

Historical files under `scratch/phase8_5_wp10_multilingual_evaluation_pack/` MUST NOT be edited into the V2 evaluator. They remain evidence of the defect and are not a production implementation seam.
