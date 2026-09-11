# V2 Post-Evaluation Determination Audit

**Date:** 2026-09-02  
**Task:** Post-Evaluation Determination Audit — Read-Only Governance Audit  
**Auditor:** Antigravity Engineering (governed handoff)  
**Status:** COMPLETE — READ-ONLY GOVERNANCE AUDIT  
**Audit Scope:** `V2_CONTROLLED_PRODUCTION_EVALUATION_REPORT.md` and `V2_CONTROLLED_EVALUATION_RESULTS.json`  
**Final Determination:** **DETERMINATION AUDIT: FAIL** (Lifecycle transition to `EVALUATED: PASS` is **NOT YET JUSTIFIED**; lifecycle remains `ACTIVE: PASS`, `EVALUATED: FALSE`)  

---

## 1. Evaluation Execution Status

The physical execution of the controlled production evaluation was audited from raw execution logs, operating system process telemetry, and physical disk artifacts:

| Execution Dimension | Audit Finding | Status |
|---|---|:---:|
| **Provider Initialization** | Initialized `BAAI/bge-m3` (`5617a9...`) and `BAAI/bge-reranker-v2-m3` (`953dc6...`) from local cache `D:/Mnemo/phase8.5.11-models/huggingface/hub` in 9999.3ms with zero network requests. | **PASS** |
| **Runtime Composition** | Assembled server-owned production runtime through `ServerOwnedFullMultilingualV2RegistrationV1` and verified parity digest `f3c4f6041acfbf4ba9047b191e208f7207ee0877852e9b64eae478878ad6ace6`. | **PASS** |
| **Execution Completeness** | All 18 queries (`MBSEL-01` through `MBSEL-18`) were dispatched to and processed by `runtime.advanced_source.retrieve_authorized()`. Zero runtime crashes or unhandled exceptions occurred. | **PASS** |
| **Telemetry Capture** | All 18 query outcomes, candidate IDs, document IDs, ranks, scores, latencies, and candidate text previews were retained. | **PASS** |
| **V1 Fallback Invariant** | Zero silent fallbacks to V1 retrieval occurred (`_FailClosedFallback` was never invoked). | **PASS** |

---

## 2. Governed Definition of EVALUATED

To determine the exact governed conditions for lifecycle state `EVALUATED: PASS`, the authoritative governance suite was audited:
1. `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md` (Sections 2, 3, 7, 8, 9)
2. `multilingual_evaluation_contract.proposed.md` (Sections 1, 2, 3)
3. `multilingual_evaluation_manifest.proposed.json` (Lines 64–106, 108–133, 145–194)
4. `V2_ACTIVE_TO_EVALUATED_REPORT.md` (Sections 1, 3, 4, 7)
5. `FAILURE_TAXONOMY.proposed.json`

### Governed Distinctions:

| Evaluation Concept | Exact Governed Definition | Current Run Status |
|---|---|:---:|
| **A. Evaluation EXECUTED** | The evaluation harness actively dispatched test cases through the composed runtime rather than halting in preflight. | **ESTABLISHED** (18/18 queries executed) |
| **B. Evaluation COMPLETED** | All test cases reached final ranking and emitted complete execution telemetry without abnormal termination. | **ESTABLISHED** (18/18 queries completed) |
| **C. Evaluation QUALITY PASS** | Retrieval scores satisfy formal, approved numeric utility floors across all evaluated directions and cohorts. | **NOT ESTABLISHED** (Threshold contract is `"not_yet_defensible"`; 3 queries missed top 10 / Rank 1) |
| **D. Evaluation GOVERNANCE PASS** | Evaluation meets sample-size floors ($\ge 30$/dir), uses adjudicated evidence-level QRELs, and covers required certification cohorts. | **NOT ESTABLISHED** ($n=18$ total; uses document titles, not chunk QRELs; 3 directions have $n=0$) |
| **E. Evaluation INTEGRITY PASS** | Runtime is strictly read-only, database bytes and active alias digests remain bit-for-bit identical before and after. | **ESTABLISHED** (All hashes match bit-for-bit) |
| **F. Lifecycle EVALUATED: PASS** | Formal transition of repository governance lifecycle from `ACTIVE` to `EVALUATED`. | **NOT YET JUSTIFIED** |

---

## 3. Lifecycle Determination Audit

In `docs/governance/proposals/phase8_5_full_multilingual_architecture/V2_CONTROLLED_PRODUCTION_EVALUATION_REPORT.md` Section 17, the report asserted:
> `EVALUATED: PASS (Controlled evaluation executed, completed, and baseline captured)`

### Governance Audit Finding:
This statement is **NOT GOVERNED** and is **NOT SUPPORTED** by the authoritative evaluation contract:
1. **Scope Limitation:** The manifest (`multilingual_evaluation_manifest.proposed.json` line 65) explicitly designates `legacy_selection_cohort` as:
   `"purpose": "Model selection and future adapter-reproducibility smoke testing only; not certification."`
   It further classifies the cohort as `"governed": false, "immutable": false`.
2. **Sample Size Violation:** `multilingual_evaluation_contract.proposed.md` Section 2 mandates at least 30 answerable cases per direction for any provisional quality measurement, and 75 cases per direction for certification. The legacy cohort contains only 1 to 5 cases per direction across 6 directions, and 0 cases for `en->hi`, `hi->hi`, and `mr->hi`.
3. **QREL Format Incompatibility:** `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md` Section 9 explicitly mandates:
   *"Document-title-only qrels are invalid for semantic quality."*
   The legacy cohort uses `"relevance_label_scheme": "one expected document per query"`, which specifies whole-document file basenames rather than adjudicated chunk/occurrence evidence items.
4. **Retrieval Deficits:** Queries `MBSEL-02` (hi->en) and `MBSEL-03` (mr->en) were not retrieved within the top 10 candidates.

**Determination:**
```text
LIFECYCLE DETERMINATION: NOT YET JUSTIFIED
```
The repository lifecycle must remain:
```text
ACTIVE: PASS
EXPOSED: FALSE
EVALUATED: FALSE
VERIFIED: FALSE
CERTIFIED: FALSE
```

---

## 4. Evaluation Scope

The audited run evaluated exclusively the 18 queries of `legacy_selection_cohort`:
- **Total Queries in Manifest:** 18
- **Total Queries Executed:** 18
- **Total Queries Excluded:** 0
- **Total Queries Failed at Runtime:** 0

**Cohort Nature:**
The 18 queries represent an **initial / smoke reproducibility cohort**, NOT the complete authorized evaluation set and NOT a certification suite.

---

## 5. Query and Direction Completeness

| Direction | Minimum Required for Provisional Floor | Governed Cases in Certification Target | Cases Evaluated in Current Run | Directional Completeness |
|---|---:|---:|---:|:---:|
| `en->en` | 30 | 75 | 5 | **16.7%** |
| `en->hi` | 30 | 75 | 0 | **0.0% (UNTESTED)** |
| `en->mr` | 30 | 75 | 1 | **3.3%** |
| `hi->en` | 30 | 75 | 5 | **16.7%** |
| `hi->hi` | 30 | 75 | 0 | **0.0% (UNTESTED)** |
| `hi->mr` | 30 | 75 | 1 | **3.3%** |
| `mr->en` | 30 | 75 | 5 | **16.7%** |
| `mr->hi` | 30 | 75 | 0 | **0.0% (UNTESTED)** |
| `mr->mr` | 30 | 75 | 1 | **3.3%** |
| **TOTAL** | **270** | **675** | **18** | **6.7% (Provisional) / 2.7% (Cert)** |

The current evaluation provides coverage for only 6 of the 9 primary language directions, and does not reach the minimum statistical power ($n \ge 30$) for any direction.

---

## 6. Resume Failure Audit

Queries targeting `Atharv_Patil_RESUME_SDE.pdf` (`be251335-3f19-5399-83d3-ef3e9096a846`) produced the following raw telemetry:

### 1. `MBSEL-01` (`en->en`):
- **Query:** *"What technical skills are listed in Atharv's resume?"*
- **Target Found Rank:** **5** (Score: `0.03058`, Candidate ID: `be46ea61-65ba-58be-8f45-905b2181e59a`)
- **Candidates Ranked Ahead:**
  1. Rank 1: `Coordinator Application 2026–27` (Score: `0.03252`)
  2. Rank 2: `llmPrompt.js` (Score: `0.01493`)
  3. Rank 3: `boarding-pass-Atharv-Patil` (Score: `0.01408`)
  4. Rank 4: `New Doc 06-30-2026 20.31` (Score: `0.02814`)

### 2. `MBSEL-02` (`hi->en`):
- **Query:** *"अथर्व के रिज्यूमे में कौन से तकनीकी कौशल हैं?"*
- **Target Found Rank:** **null (>10)**
- **Top Candidates Returned:**
  1. Rank 1: `research_8b4fd9e3...md` (Score: `0.01471`)
  2. Rank 2: `Coordinator Application 2026–27` (Score: `0.01639`)
  3. Rank 3: `llmPrompt.js` (Score: `0.01515`)
  4. Rank 4: `research_8b4fd9e3...md` (Score: `0.01449`)
  5. Rank 5: `New Doc 06-30-2026 20.31` (Score: `0.01429`)

### 3. `MBSEL-03` (`mr->en`):
- **Query:** *"अथर्वच्या रिझ्युमेमध्ये कोणती तांत्रिक कौशल्ये आहेत?"*
- **Target Found Rank:** **null (>10)**
- **Top Candidates Returned:**
  1. Rank 1: `Bhagavad-gita As It Is with pics!` (Score: `0.01429`)
  2. Rank 2: `New Doc 06-30-2026 20.31` (Score: `0.01429`)
  3. Rank 3: `llmPrompt.js` (Score: `0.01493`)
  4. Rank 4: `arvsal_v3_complete.txt` (Score: `0.01587`)
  5. Rank 5: `arvsal_v3_complete.txt` (Score: `0.01562`)

### Causal Attribution Audit:
In `V2_CONTROLLED_PRODUCTION_EVALUATION_REPORT.md` Section 11, the report attributed the misses on `MBSEL-02` and `MBSEL-03` to:
> *"keyword competition from other technical application documents in the corpus."*

**Audit Correction:**  
The evaluation telemetry records fused and reranked scores, but does **not** record isolated sub-token embeddings, sparse BM25 term matrices, or cross-encoder attention maps for the candidate pairs. Attributing the failure specifically to "keyword competition" is an unverified hypothesis.

In accordance with audit instructions, this causal claim is replaced conceptually with:
> **"Observed retrieval failure; causal attribution not established by this evaluation."**

---

## 7. Baseline Comparability

The evaluation report compared measured results against published baselines from `multilingual_evaluation_manifest.proposed.json` (derived from `scripts/phase8_5_11_benchmark_models.py`):

| Comparability Dimension | Published Baseline Setting | V2 Production Runtime Setting | Comparability Assessment |
|---|---|---|:---:|
| **Query Inventory** | 18 queries (`MBSEL-01` to `MBSEL-18`) | 18 queries (`MBSEL-01` to `MBSEL-18`) | **IDENTICAL** |
| **Corpus** | 44 source documents | 44 source documents | **IDENTICAL** |
| **Models & Revisions** | `bge-m3@5617a9...`, `bge-reranker-v2-m3@953dc6...` | `bge-m3@5617a9...`, `bge-reranker-v2-m3@953dc6...` | **IDENTICAL** |
| **Candidate Universe** | 44 whole-document concatenated strings (first 2500 chars) | **2,658 discrete chunk projection rows** | **NOT COMPARABLE** |
| **Retrieval Architecture** | Single-stage full-universe matrix dot-product / full-universe pairwise rerank | **Two-stage retrieval: Dual-source (Dense + Sparse) fusion (RRF) to top 20, then Cross-Encoder rerank** | **NOT COMPARABLE** |
| **Relevance Labels** | Document filename string match | Document UUID via chunk projection | **PARTIALLY COMPARABLE** |
| **Metric Formulation** | `uncut_single_relevant_ndcg` | $\text{nDCG@10} = 1/\log_2(\text{rank}+1)$ | **PARTIALLY COMPARABLE** |

### Overall Comparability Determination:
**PARTIALLY COMPARABLE**

The models, query texts, and underlying corpus documents are identical. However, comparing retrieval over 44 whole-document concatenations against retrieval over 2,658 chunk projection rows through a two-stage fusion pipeline represents fundamentally different retrieval mechanics.

---

## 8. Marathi Semantic-Text Audit

The validation of candidate semantic text for queries targeting Marathi (`manuscript.pdf`) was audited against physical database rows:

1. **Candidate Content vs DB Projection:**
   Candidate `7d78d381-80fc-5835-9502-fb1e0ea28fc1` returned at Rank 1 for `MBSEL-04`, `MBSEL-05`, and `MBSEL-06` contains:
   *"त्यांच्याबद्दलचे प्रेम हे केवळ एक आकर्षण नव्हते, तर ती एक अशी भावना होती..."*
   This text was cross-referenced directly against SQLite `language_text_projection_rows_v2` for `manuscript.pdf` (`cb86bb2f-8af6-5a0e-8bde-ae70fb22aac3`). The text is verified to be an exact match with the stored projection chunk text.
2. **Title/Filename Substitution:**
   `is_filename_or_title` was verified `False` across all checked candidates.
3. **Number of Candidates Checked:**
   Exactly **5** candidates were audited in detail across `MBSEL-04`, `MBSEL-05`, and `MBSEL-06` (Ranks 1, 3, 5, 6, 7, 8).
4. **Reranked vs Retrieved Scope:**
   The validation covers **reranked** candidates returned by `runtime.advanced_source.retrieve_authorized()`, which incorporates the full pipeline (Dense + Sparse $\rightarrow$ RRF $\rightarrow$ BGE-Reranker $\rightarrow$ Projection).

**Determination:** **PASS**

---

## 9. Failure Classification

For all non-Rank-1 queries:

| Query ID | Outcome | Classification Category | Rationale |
|---|---|---|---|
| `MBSEL-01` | Found at Rank 5 | **retrieval-quality failure** | Execution, authorization, and provenance were intact; document was retrieved but scored lower than 4 other candidates. |
| `MBSEL-02` | Not found in top 10 | **retrieval-quality failure** | Execution, authorization, and provenance were intact; candidate did not achieve sufficient dense/sparse fusion score to enter top 10. |
| `MBSEL-03` | Not found in top 10 | **retrieval-quality failure** | Execution, authorization, and provenance were intact; candidate did not achieve sufficient dense/sparse fusion score to enter top 10. |

- Evidence / Provenance Failures: **0**
- Runtime / Composition Failures: **0**
- Authorization Failures: **0**
- Infrastructure Failures: **0**
- Governed Exclusions: **0**

All non-Rank-1 cases are strictly **retrieval-quality failures**.

---

## 10. Evidence Completeness

The structured results artifact (`V2_CONTROLLED_EVALUATION_RESULTS.json`) was audited against the fields required by `MULTILINGUAL_EVALUATION_CONTRACT.proposed.json` (`EvaluationCaseRecordV2`):

| Required Field | Present in Results Artifact? | Details / Gap |
|---|:---:|---|
| Query Text & ID | **YES** | `query_id`, `query_text` |
| Expected Target | **YES** | `expected_document_name`, `expected_document_id` |
| Relevance Labels | **PARTIAL** | Document-level name only; evidence-level graded QRELs missing |
| Retrieval Mode | **NO (Per-query)** | Recorded in report, omitted in per-query JSON records |
| Ranked Candidates | **YES** | `ranked_candidates` with ID, doc_id, rank, score, preview |
| Scores & Ranks | **YES** | `fused_score`, `rank`, `found_rank` |
| Provenance Details | **PARTIAL** | Candidate ID and doc ID present; version ID, chunk ID, and locator omitted |
| Runtime Identity | **NO (Per-query)** | Embedded in global report, omitted in per-query JSON records |
| Generation Binding | **NO (Per-query)** | Embedded in global report, omitted in per-query JSON records |
| Language & Script | **PARTIAL** | Language code and direction present; ISO-15924 script observation omitted |
| Failure Code | **YES** | `failure_code: null` |
| Metric Contribution | **YES** | `recall_at_1`, `recall_at_5`, `recall_at_10`, `mrr`, `ndcg` |

---

## 11. Protected State Verification

Recomputed physical disk hashes immediately following the audit:

```text
manuscript.pdf SHA:  31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085  [MATCH: True]
Ramayana PDF SHA:    759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75  [MATCH: True]
V2 Database SHA:     3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c  [MATCH: True]
Active Alias Digest: b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0  [MATCH: True]
Canonical DB ID:     0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d  [MATCH: True]
Vector-Space ID:     7dcba654e1c947145253ff65ef93e2b4ef1105cdf680b79218a446c79cc1a0d7  [MATCH: True]
```

---

## 12. Audit Findings

1. **Execution Integrity:** The production runtime composition, local offline providers, and 10,001 limit handling executed flawlessly without any runtime errors or V1 fallbacks.
2. **Marathi Grounding:** Candidate projection delivers authentic Devanagari manuscript chunks; title/metadata substitution is definitively disproven.
3. **Premature Lifecycle Advancement:** Transitioning the lifecycle to `EVALUATED: PASS` in the evaluation report was premature. The 18-query cohort is explicitly scoped in governance as an informal smoke/model-selection cohort, lacks evidence-level QRELs, lacks the 30-case/direction minimum power, and contains 2 misses in cross-lingual retrieval.
4. **Causal Speculation:** Attributing the resume retrieval misses to "keyword competition" was not supported by telemetry evidence.

---

## 13. Final Determination

**DETERMINATION AUDIT: FAIL**

### Explicit Ruling:
The current statement `EVALUATED: PASS` is **NOT YET JUSTIFIED** by governance.

The evaluation run successfully establishes:
- **Evaluation EXECUTED: PASS**
- **Evaluation COMPLETED: PASS**
- **Evaluation INTEGRITY: PASS**
- **Smoke Baseline Reproducibility: ESTABLISHED (83.3% R@1, 88.9% R@5/10)**

However, lifecycle advancement to `EVALUATED: PASS` requires:
1. Expansion to governed directional cohorts meeting the minimum sample size ($n \ge 30$ cases per direction).
2. Adjudicated evidence-level chunk QRELs rather than whole-document filename matching.
3. Formal human/governance approval of the threshold contract.

The governance lifecycle state MUST remain:
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
