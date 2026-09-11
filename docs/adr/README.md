# Mnemo Architecture Decision Record Index

ADRs are immutable decision history. A later ADR may extend or narrowly
supersede an earlier decision; it does not rewrite the earlier record. Missing
numbers are historical and are not reused.

## Phase 0–8 accepted decisions

| Range | Subject |
|---|---|
| [ADR-0001](active/ADR-0001-domain-model-specification.md)–[ADR-0006](active/ADR-0006-document-deduplication.md) | domain, interfaces, configuration, composition, graph identity, deduplication |
| [ADR-0008](superseded/ADR-0008-parser-image-extraction-and-headers.md) | historical parser image/header decision; superseded where stated by ADR-0011 |
| [ADR-0011](active/ADR-0011-raw-parse-result-boundary.md)–[ADR-0018](active/ADR-0018-embedding-initialization-lifecycle.md) | parsing, cleaning, classification, canonicalization, chunking, ingestion semantics, embeddings |
| [ADR-0036](active/ADR-0036-slides-ingestion-semantic-boundary.md)–[ADR-0037](active/ADR-0037-documentation-ingestion-semantic-boundary.md) | slide and documentation ingestion boundaries |
| [ADR-0038](active/ADR-0038-version-aware-retrieval-filter-projection.md)–[ADR-0048](active/ADR-0048-diversity-aware-reranking-and-constrained-prompt-routing.md) | retrieval, fusion, reranking, context, citations, Final QA, routing |
| [ADR-0049](active/ADR-0049-phase-7-server-application-architecture.md)–[ADR-0051](active/ADR-0051-sources-and-document-ingestion-rest-api.md) | server and REST boundaries |
| [ADR-0052](active/ADR-0052-citation-compliance-and-final-qa-publication.md)–[ADR-0057](active/ADR-0057-title-aware-cross-encoder-reranking.md) | citation compliance, title-aware retrieval, persisted Final QA replay, reranking |

## Phase 8.5 decisions and certified deployment

Historical module gates report the state observed when each workstream ran.
ADR-0073–ADR-0075 froze the remediation contracts. ADR-0076 subsequently
accepted the project-owner engineering certification standard for the exact
44-document Mnemo V2 production snapshot. Its signed WP-17 evidence records
that the scoped deployment is evaluated, verified, and certified. Broader
research claims outside ADR-0076 remain governed by ADR-0070.

Earlier gate and evaluation documents remain valid only for the exact direct,
unit, model, or corpus behavior they measured. They do not by themselves prove
that a capability is configured, active, exposed, discoverable, behaviorally
verified, or currently certified. The machine-readable WP-00 capability matrix
is the current status authority.

All decisions below are accepted architectural contracts. Acceptance alone
does not advertise an implemented capability.

| ADR | Decision |
|---|---|
| [ADR-0058](active/ADR-0058-advanced-retrieval-completeness-and-result-sets.md) | Advanced retrieval completeness and result sets |
| [ADR-0059](active/ADR-0059-original-document-assets-and-occurrence-provenance.md) | Original document assets and occurrence provenance |
| [ADR-0060](active/ADR-0060-durable-processing-jobs-and-cost-governance.md) | Durable processing jobs and cost governance |
| [ADR-0061](active/ADR-0061-ocr-and-derived-text-representations.md) | OCR and derived text representations |
| [ADR-0062](active/ADR-0062-vision-analysis-and-visual-embedding-spaces.md) | Vision analysis and visual embedding spaces |
| [ADR-0063](active/ADR-0063-structured-retrieval-and-safe-aggregation.md) | Structured retrieval and safe aggregation |
| [ADR-0064](active/ADR-0064-multimodal-evidence-context-and-final-qa-v2.md) | Multimodal evidence, context, and Final QA V2 |
| [ADR-0065](active/ADR-0065-bounded-document-expansion-and-resource-delivery.md) | Bounded document expansion and resource delivery |
| [ADR-0066](active/ADR-0066-mcp-document-and-asset-capability-expansion.md) | MCP document and asset capability expansion |
| [ADR-0067](active/ADR-0067-multilingual-retrieval-and-derived-translation.md) | Multilingual retrieval and derived translation |
| [ADR-0068](active/ADR-0068-asset-authorization-and-provider-trust-boundaries.md) | Asset authorization and provider trust boundaries |
| [ADR-0069](active/ADR-0069-phase-8-5-http-api-and-ui-capability-contract.md) | Phase 8.5 HTTP API and UI capability contract |
| [ADR-0070](active/ADR-0070-phase-8-5-evaluation-and-certification-governance.md) | Phase 8.5 evaluation and certification governance |
| [ADR-0071](active/ADR-0071-phase-8-5-additive-migration-and-index-generation-lifecycle.md) | Additive migration and index-generation lifecycle |
| [ADR-0072](superseded/ADR-0072-propagate-notebook-identity-and-safely-resolve-notebook-context-for-mcp-document-retrieval.md) | Propagate notebook identity and safely resolve notebook context for MCP document retrieval; scope-resolution mechanism superseded by ADR-0075 |
| [ADR-0073](active/ADR-0073-mcp-native-retrieval-and-delivery-contracts.md) | MCP-native retrieval and delivery contracts |
| [ADR-0074](active/ADR-0074-phase-8-5-runtime-and-profile-activation.md) | Phase 8.5 runtime and profile activation |
| [ADR-0075](active/ADR-0075-additive-document-scope-resolution.md) | Additive document scope resolution; supersedes ADR-0072 mechanism |
| [ADR-0076](active/ADR-0076-project-owner-engineering-certification-standard.md) | Accepted project-owner engineering certification standard for the exact Mnemo V2 production snapshot |

The next available ADR number is **ADR-0077**.

## Phase 8.5 references

- [Architecture blueprint](../architecture/historical/phase8.5_architecture.md)
- [Dedicated engineering roadmap](../architecture/historical/mnemo_phase8_5_engineering_roadmap.md)
- [Contradiction audit](../reports/architecture/PHASE_8_5_ARCHITECTURAL_CONTRADICTION_AUDIT.md)
- [Phase 8.5.11 evaluation](../reports/evaluation/PHASE_8_5_11_EVALUATION_REPORT.md)
- [Complete implementation plan](../governance/historical/PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md)
- [WP-00 capability matrix](../governance/contracts/phase8_5_capability_matrix.json)
- [WP-00 MCP contract freeze](../governance/contracts/phase8_5_mcp_contracts.json)
- [WP-06 asset-delivery gate evidence](../evidence/historical/phase-8-5/PHASE_8_5_WP_06_GATE_EVIDENCE.md)
- [WP-07 advanced-retrieval exposure gate evidence](../evidence/historical/phase-8-5/PHASE_8_5_WP_07_GATE_EVIDENCE.md)
- [WP-08 structured projection/query exposure gate evidence](../evidence/historical/phase-8-5/PHASE_8_5_WP_08_GATE_EVIDENCE.md)
- [Final Mnemo V2 certification](../reports/certification/current/mnemo-v2-final-certification.md)
- [Post-certification single-path audit](../reports/architecture/mnemo-v2-single-production-path-audit.md)
