# Milestone M6: Heterogeneous Corpus Retrieval and Grounded QA Verification

**Verdict:** PASS  
**Executed:** 2026-08-15 15:30:00 UTC  
**Mnemo:** v0.21.1  
**Platform:** Windows 11, Python 3.12.10, Intel64 Family 6 Model 183  

---

## 1. Dataset & Production Pipeline

### Heterogeneous Multi-Document Corpus:
- `goldenDataset/Bhagavad-gita-As-It-Is.pdf` (952 pages, philosophical/theological text)
- `goldenDataset/Atharv_Patil_RESUME_SDE.pdf` (1 page, structured SDE resume)
- `goldenDataset/Coordinator Application 2026–27.pptx` (20 slides, budget line items & vision)
- `goldenDataset/ME333 - Exp2-LabReport_To_Submit.docx` (9 pages, mechanical vibration lab report)
- `goldenDataset/ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1).pptx` (28 slides, manufacturing engineering & CNC)
- `goldenDataset/Y24_CPI.csv` (1,234 rows, dense student CPI & rank records)
- `goldenDataset/server.js` (477 lines, Express backend & audio DSP pipelines)

### Executed Production Retrieval & Generation Pipeline:
```text
User Question
  → QueryPlanner (RetrievalPlan intent & sub-queries)
  → Parallel Hybrid Retrieval:
      ├─ DenseRetriever (Qdrant Cosine, 768-dim nomic-embed-text)
      └─ SparseRetriever (SQLite FTS5 BM25 conjunctive matching)
  → ParentRetriever (Source-local 50% family promotion)
  → FusionReranker (Unweighted RRF, k=60)
  → CrossEncoderReranker (ADR-0042 ms-marco-MiniLM-L-6-v2 + ADR-0048 Diversity Quota)
  → ContextBuilder (ADR-0043 token budget + top-3 verbatim preservation + [N] markers)
  → GroundedAnswerGenerator (ADR-0044 + ADR-0048 Constrained Intent Prompt Routing: S1/S2/S3/S4)
  → CitationEngine (ADR-0045 Deterministic marker resolution to SQLite citations table)
  → FinalQAPipeline (Composite answer delivery)
```

No mock models, mock parsers, or mock stores were used. Real local Ollama (`gemma4:e4b` for generation, `nomic-embed-text` for embedding) and real Qdrant/SQLite storage were executed.

---

## 2. Validation Metrics & Empirical Performance

| Evaluation Suite | Queries | Context Inclusion | Generation Accuracy | Negative Grounding Refusal | Avg Latency |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Suite 1: Regression Suite** | 28 | 92.9% (26/28) | 89.3% (25/28) | 100.0% (1/1) | 19.49s |
| **Suite 2: Adversarial Suite** | 32 | 87.5% (28/32) | 81.2% (26/32) | 100.0% (5/5) | 19.44s |
| **Suite 3: Router Boundary Suite** | 10 | N/A | 100.0% (10/10) | N/A | <0.01s |
| **Suite 4: Determinism (3x Runs)**| 30 | 100.0% | 100.0% Consistent | 100.0% | 19.12s |

### Core Behavioral Invariants Verified:
1. **Multi-Source Context Guarantee:** Dual-source queries (`ADV_13`, `ADV_14`, `ADV_15`, `ADV_16`) achieve 100% context inclusion across heterogeneous format pairs (PDF+CSV, PDF+PPTX, PDF+JS, PPTX+DOCX).
2. **Relevance-Aware Diversity:** Diversity reranking only allocates quotas to sources matching query keywords/signatures. Single-source queries strictly default to descending score order with zero irrelevant document forcing.
3. **Conservative Prompt Routing:** `PROMPT_S1` remains the default semantic QA prompt; `PROMPT_S2` handles exact verse/tolerance extraction; `PROMPT_S3` handles code/tabular records; `PROMPT_S4` handles cross-document synthesis.
4. **100% Negative Grounding Refusal:** Refusals on non-existent verses, fictitious students, absent endpoints, and fake entities achieved a 100% strict refusal invariant with zero hallucinations.
5. **100% Determinism:** 100% chunk rank determinism and 100% route determinism across 3 repeated runs.

---

## 3. Associated ADRs

- **`ADR-0038`:** Version-Aware Retrieval Filter Projection
- **`ADR-0039`:** Version-Aware Sparse Retrieval
- **`ADR-0040`:** Source-Local Parent Candidate Promotion
- **`ADR-0041`:** Deterministic Multi-Source Retrieval Fusion (RRF k=60)
- **`ADR-0042`:** Fusion-Aware Cross-Encoder Reranking
- **`ADR-0043`:** Deterministic Provenance-Preserving Context Construction
- **`ADR-0044`:** Grounded Answer Generation & Citation Pipeline
- **`ADR-0045`:** Deterministic Citation Resolution & Persistence
- **`ADR-0046`:** Final QA Integration Contracts
- **`ADR-0047`:** Final QA Runtime Composition
- **`ADR-0048`:** Diversity-Aware Reranking & Constrained Query-Adaptive Prompt Routing

---

## 4. Phase Boundary Confirmation

- **M6 Scope Completed:** Single-pass hybrid retrieval, diversity-aware multi-source reranking, constrained intent prompt routing, grounded generation, and citation persistence.
- **Phase 11 Scope Deferred:** Multi-hop entity graph reasoning, transitive knowledge graph traversals, and deep ontology extraction remain cleanly isolated for Phase 11.
