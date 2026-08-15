# ADR-0048: Diversity-Aware Cross-Encoder Reranking and Constrained Query-Adaptive Prompt Routing

- **Status:** Accepted
- **Date:** 2026-08-15
- **Deciders:** Antigravity AI Engineering Team
- **Consulted:** Architecture Review Board, Retrieval & NLP Systems
- **Informed:** Core Engineering, Milestone Validation

---

## 1. Context and Problem Statement

In Milestone M6, evaluation across a heterogeneous multi-document corpus (comprising PDFs, DOCX lab reports, PPTX decks, CSV tabular data, and JavaScript code) exposed two critical retrieval and generation challenges:

1. **Cross-Encoder Single-Source Bias on Multi-Document Queries:**
   Under standard Cross-Encoder reranking (ADR-0042), candidates are scored in isolation. When queries target relationships between two documents (e.g. comparing a student's resume with a large tabular CSV or comparing a lab report with lecture slides), dense chunks from one document can monopolize all Top-K context positions, pushing vital evidence from the second document out of the context window.
2. **Monolithic Prompt Limitations vs Universal Routing Failures:**
   While monolithic prompt framing struggled with verbatim Sanskrit verses and code syntax, experimental evaluations (`EXP-M6-PROMOTION-GATE-003`) revealed that universal prompt routing (R3) reduced generation accuracy from 89.3% to 78.6% by forcing rigid key-value extraction on broad conceptual questions.

**Empirical Decision:**
R3 / full universal routing was **NOT** promoted because it degraded generation accuracy on general conceptual queries. Instead, a dual enhancement is adopted:
1. **Promote** relevance-aware multi-source diversity selection within the Cross-Encoder reranker.
2. **Promote** a constrained, intent-adaptive prompt routing policy where `PROMPT_S1` (Fluent Semantic QA) remains the default.

---

## 2. Decision Drivers

- **Zero Multi-Source Context Exclusion:** Ensure all documents genuinely relevant to a multi-source query are represented in Top-K context.
- **No Artificial Forcing of Irrelevant Documents:** For single-document queries, diversity selection must never force low-scoring or irrelevant documents into context.
- **Preserve Fluent Semantic QA:** Conceptual and broad questions must not be degraded into terse key-value fragments.
- **Verbatim Precision for Exact Directives:** Exact verses, formulas, tolerances, routes, and CSV records must be extracted with high fidelity.
- **100% Negative Grounding Invariant:** Refusals for non-existent entities, verses, or routes must remain at 100% with zero hallucination.
- **Deterministic Repeatability:** Chunk selection and routing must be 100% deterministic across repeated evaluations.

---

## 3. Considered Options

- **Option 1: Retain Pure Score-Based Cross-Encoder Reranking (Status Quo / ADR-0042)**
  - *Cons:* Fails on cross-document synthesis (e.g. `ADV_13`); single-source bias displaces critical secondary documents.
- **Option 2: Universal S1–S4 Prompt Routing (Experimental R3)**
  - *Cons:* Reduced generation accuracy on regression suite (-10.7% combined effect) due to overly aggressive structured extraction on broad queries.
- **Option 3: Multi-Source Diversity Reranking + Constrained Intent-Aware Prompt Routing (Selected)**
  - *Pros:* Achieves 100% multi-source context inclusion, maintains 89.3% regression accuracy and 81.2% adversarial accuracy, preserves 100% negative grounding, and speeds up inference by -1.50s.

---

## 4. Architectural Specification

```
                                  [ Fused Candidates (A+B+C+D) ]
                                                |
                                                v
                              [ Cross-Encoder Candidate Scoring ]
                                                |
                                                v
                              [ Relevant Source Detection & Quota ]
                                                |
                                                +--> If 1 source: Pure Score Order
                                                |
                                                +--> If >= 2 sources: Guarantee Top-1/Top-2 per source
                                                |
                                                v
                              [ Top-K Context Construction ]
                                                |
                                                v
                              [ Conservative Intent Classifier ]
                                                |
                                                +--> Cross-Doc Query?   -> PROMPT S4
                                                +--> Exact Verse/Num?   -> PROMPT S2
                                                +--> Code / Table?      -> PROMPT S3
                                                +--> Default / General  -> PROMPT S1 (Fluent QA)
                                                |
                                                v
                              [ Grounded Generation & Citation Engine ]
```

### A. Diversity-Aware Cross-Encoder Reranker (`mnemo.retrieval.reranker`)
- Relevant source documents are detected via entity signature matching and high candidate scores ($\ge 0.50$).
- When $\ge 2$ sources are detected, Top-1 (or Top-2 for dual-source comparisons) representation is guaranteed for each relevant source before filling remaining slots strictly by descending Cross-Encoder score.
- Implements `FusionRerankingInterfaceV1` with zero contract changes.

### B. Constrained Prompt Routing Policy (`mnemo.retrieval.answer`)
- **`PROMPT_S1` (Fluent Semantic QA - DEFAULT):** Standard natural-language explanation. Used for all general, conceptual, and ambiguous queries.
- **`PROMPT_S2` (Structured Extraction):** Strict verbatim extraction. Engaged ONLY for explicit verse numbers, tolerances, or formulas.
- **`PROMPT_S3` (Code/Table Extraction):** Exact code route and CSV record lookups. Engaged ONLY for explicit source code or tabular queries.
- **`PROMPT_S4` (Cross-Document Synthesis):** Multi-source attribution. Engaged ONLY when query requires synthesis across $\ge 2$ documents.

---

## 5. Empirical Validation Evidence

| Metric | Baseline Control (R0) | Promoted Production Architecture |
| :--- | :---: | :---: |
| Regression Generation Accuracy (28 Qs) | 89.3% | **89.3%** |
| Adversarial Generation Accuracy (32 Qs) | 75.0% | **81.2%** |
| Adversarial Context Inclusion | 96.9% | **100.0%** (On explicit multi-source) |
| Negative Grounding (Refusal) | 100.0% | **100.0%** |
| Router Boundary Accuracy (10 Qs) | — | **100.0% (10/10)** |
| 3x Stability Determinism | — | **100.0% (10/10)** |
| Average Total Latency | 20.99s | **19.49s** (-1.50s) |

---

## 6. Consequences & Rollback Strategy

### Positive Consequences:
- Multi-document queries (e.g. Resume vs CSV) retrieve and synthesize evidence from all relevant documents without single-source starvation.
- Exact Sanskrit verses, numerical tolerances, and JavaScript endpoints preserve exact tokens without paraphrasing.
- General and conceptual questions retain high fluent accuracy.
- Zero regressions on negative grounding or existing test suites.

### Rollback Strategy:
If unexpected behavior occurs in production, diversity ordering can be bypassed by setting `len(relevant_sources) <= 1` or reverting `_apply_diversity_ordering` to standard `sorted()`. Prompt routing defaults to `PROMPT_S1` safely in all uncertain conditions.
