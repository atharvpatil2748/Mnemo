# Repository Governance: Evaluation Harness & Production Alignment Policy

---

## 1. Authoritative Governance Rule

> **RULE:** Evaluation runners and test harnesses MUST invoke authoritative `mnemo-core` production retrieval, ranking, and context-construction interfaces. They MUST NOT independently reimplement, approximate, or diverge from production retrieval, reranking, diversity, Top-K selection, or context construction algorithms.

---

## 2. Context & Background: The M6 Evaluation Divergence Incident

During Milestone M6 live streaming test runs, an ad-hoc diversity selection loop was temporarily introduced into a test harness script (`scratch/generate_28_md.py`) to stream evaluation progress. The ad-hoc loop performed an unconditional round-robin selection across distinct document sources encountered in the candidate pool.

### Observed Failure
- For single-document queries (e.g. `Q14_ME333_MASS_CALC`, `Q15_ME333_OBSERVATIONS`), the ad-hoc loop selected 1 chunk from the target document, then forcibly allocated slots to unrelated documents (`ME361`, `server.js`, `Bhagavad Gita`) from the low-scoring tail of the candidate pool.
- This evicted valid, high-scoring answer-bearing chunks from the context window, causing the LLM to output *"The context is insufficient"*, masquerading as a retrieval regression.

### Forensic Finding
- The authoritative `mnemo-core` production diversity ranker ([`mnemo.retrieval.reranker._apply_diversity_ordering`](file:///c:/Users/athar/Desktop/Mnemo/mnemo-core/mnemo/retrieval/reranker.py#L595)) was completely intact and behaving strictly according to ADR-0048:
  - Single-source queries preserve pure relevance ordering.
  - Multi-source queries apply query-relevant source balancing.
  - Irrelevant documents are never forcibly inserted.
- When evaluated through the authoritative production pipeline with `top_k = 6`, accuracy is **96.4% (27/28)** with 100% negative grounding (0 hallucinations) and 100% ME333 correctness.

---

## 3. Mandatory Implementation Constraints for Evaluation Harnesses

1. **Direct Pipeline Invocation:** All evaluation runners must import and execute the production pipeline from `mnemo.retrieval` or `run_production_validation.py`.
2. **No Reimplemented Selection Loops:** Custom `for` loops that filter, rank, or reorder chunks based on custom heuristics are strictly prohibited in evaluation scripts.
3. **Parameter Consistency:** Context window sizes, reranking configurations, and prompt routing must match production defaults (`top_k = 6`, Universal Dynamic Prompt Router).
4. **Diagnostic Tracing:** Performance and recall diagnostics must be collected via instrumentation hooks around the production pipeline, rather than by constructing alternative mock pipelines.
