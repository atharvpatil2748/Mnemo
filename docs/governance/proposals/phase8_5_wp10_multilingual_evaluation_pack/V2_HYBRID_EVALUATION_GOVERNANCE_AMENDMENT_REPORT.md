# V2 Hybrid Evaluation Governance Amendment Report

**Date:** 2026-09-02  
**Task:** Implement Approved Hybrid Stratified Evaluation Governance  
**Scope:** Phase 8.5 WP-10 Decision 7 — Directional Sample Size Amendment, Census Policy, and Authoring Rules  
**Author:** Antigravity Engineering (governed handoff)  
**Status:** **GOVERNANCE PREPARED — PENDING HUMAN APPROVAL & REVIEWER STAFFING**  
**Final Determination:** **AMENDMENT ENCODED; LIFECYCLE PRESERVED AT ACTIVE: PASS (EVALUATED: FALSE)**  

---

## 1. Executive Determination

In response to the authoritative governance decision audit (`V2_EVALUATION_DESIGN_GOVERNANCE_DECISION_AUDIT.md`), the repository has implemented the governance decision package adopting **Option D — Hybrid Stratified Directional Policy** for Mnemo Phase 8.5 provisional evaluation.

### Core Governance Determinations:
1. **Policy Status:** **GOVERNANCE PREPARED** (Awaiting formal human governance sign-off and qualified human reviewer staffing).
2. **Evaluation Status:** **NOT EXECUTED** (Zero retrieval queries, inference calls, or automated benchmarks were run).
3. **QREL Status:** **PENDING HUMAN REVIEWER EXECUTION** (Zero synthetic, AI-generated, or fabricated QREL records have been created).
4. **Threshold Status:** **QUALITY THRESHOLD NOT YET APPROVED** (`status: "not_yet_defensible"` strictly preserved; no numeric floors back-fitted or invented).
5. **Corpus & Database State:** **IMMUTABLE AND UNTOUCHED** (All 4 protected physical disk hashes verified bit-for-bit).
6. **Lifecycle State:** **ACTIVE: PASS** (Transition to `EVALUATED` is deferred until human QRELs are adjudicated and the governed run is executed).

---

## 2. Exact Governance Amendment

The uniform 30-case proposal originally articulated in `multilingual_evaluation_contract.proposed.md` is hereby amended by formal governance amendment `mnemo.hybrid-stratified-evaluation-contract-amendment/1`:

### Governing Amendment Terms:
- **A. Uniform Heuristic Amended:** The provisional requirement of $\ge 30$ cases per direction across all 9 directions is amended to a stratified directional allocation reflecting physical evidence availability in the candidate universe.
- **B. Stratified Directional Allocations:**
  - `en->en`: $n=30$ (Standard Provisional)
  - `hi->en`: $n=30$ (Standard Provisional)
  - `mr->en`: $n=30$ (Standard Provisional)
  - `en->hi`: $n=30$ (Standard Provisional)
  - `hi->hi`: $n=30$ (Standard Provisional)
  - `mr->hi`: $n=30$ (Standard Provisional)
  - `en->mr`: $n=10$ (`CORPUS_CONSTRAINED_CENSUS`)
  - `hi->mr`: $n=10$ (`CORPUS_CONSTRAINED_CENSUS`)
  - `mr->mr`: $n=10$ (`CORPUS_CONSTRAINED_CENSUS`)
- **C. Total Master Pack Size:** Exactly **210 answerable cases** plus **30 negative/no-answer controls** (Grand Total: **240 evaluation cases**).
- **D. Governance Artifacts:** Fully codified in:
  - `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/HYBRID_STRATIFIED_EVALUATION_CONTRACT_AMENDMENT.proposed.md`
  - `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/CASE_AUTHORING_POLICY.proposed.md`
  - `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/multilingual_evaluation_manifest.proposed.json`
  - `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/multilingual_evaluation_manifest.proposed.schema.json`
  - `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/multilingual_threshold_contract.proposed.json`

---

## 3. Nine-Direction Sample Matrix

| Target Language | Direction | Cohort Classification | Answerable Target ($n$) | Target Evidence Universe | Metric Resolution | Statistical Characterization |
|---|---|---|---:|---|---:|---|
| **English** | `en->en` | `STANDARD_PROVISIONAL` | **30** | ~2,500 chunks across 38+ docs | 3.33% | Wilson 95% interval; bootstrap nDCG/MRR |
| **English** | `hi->en` | `STANDARD_PROVISIONAL` | **30** | ~2,500 chunks across 38+ docs | 3.33% | Wilson 95% interval; bootstrap nDCG/MRR |
| **English** | `mr->en` | `STANDARD_PROVISIONAL` | **30** | ~2,500 chunks across 38+ docs | 3.33% | Wilson 95% interval; bootstrap nDCG/MRR |
| **Hindi** | `en->hi` | `STANDARD_PROVISIONAL` | **30** | ~90 Devanagari chunks in V2 | 3.33% | Wilson 95% interval; bootstrap nDCG/MRR |
| **Hindi** | `hi->hi` | `STANDARD_PROVISIONAL` | **30** | ~90 Devanagari chunks in V2 | 3.33% | Wilson 95% interval; bootstrap nDCG/MRR |
| **Hindi** | `mr->hi` | `STANDARD_PROVISIONAL` | **30** | ~90 Devanagari chunks in V2 | 3.33% | Wilson 95% interval; bootstrap nDCG/MRR |
| **Marathi** | `en->mr` | `CORPUS_CONSTRAINED_CENSUS` | **10** | **All 10 eligible Marathi chunks** | 10.0% | Exact census; Wilson 95% interval |
| **Marathi** | `hi->mr` | `CORPUS_CONSTRAINED_CENSUS` | **10** | **All 10 eligible Marathi chunks** | 10.0% | Exact census; Wilson 95% interval |
| **Marathi** | `mr->mr` | `CORPUS_CONSTRAINED_CENSUS` | **10** | **All 10 eligible Marathi chunks** | 10.0% | Exact census; Wilson 95% interval |
| **Total Answerable** | **9 Directions** | — | **210** | 3,019 V2 projection rows | — | Stratified Directional Baseline |
| **Negative Controls**| No-Answer | `NEGATIVE_CONTROL` | **30** | Whole candidate universe | — | False-support rate / publication rate |
| **Total Master Pack** | — | — | **240** | — | — | Phase 8.5 Evaluation Pack Target |

---

## 4. Marathi Census Policy

For all Marathi-target directions (`en->mr`, `hi->mr`, `mr->mr`), the following strict governance rules are now legally binding:

1. **Deterministic Census Definition:**  
   The Marathi cohort is defined as an exhaustive census of all 10 canonical Marathi chunks in `manuscript.pdf` (`document_id: cb86bb2f-8af6-5a0e-8bde-ae70fb22aac3`).
2. **Exact 1-to-1 Query-to-Chunk Mapping:**  
   In each directional cohort, exactly **one** natural, answerable query is authored per chunk:
   - Chunk 0 (`664b29abcc58...`): Beginning date (27 May 2026) and initial reflection on Sejal.
   - Chunk 1 (`10d9106eeda6...`): Malkapur primary school memories (1st to 4th grade, all-boys school).
   - Chunk 2 (`d3a00e2104e6...`): Reflections on the word 'Crush' and incomplete childhood memories.
   - Chunk 3 (`523c5c88b522...`): Starting to live life vividly and 6th-grade memories.
   - Chunk 4 (`af8142c90b99...`): Entering 7th grade, class teacher Masutge Madam, friends Yash & Shardul.
   - Chunk 5 (`3c8cee1a9a76...`): School attendance becoming the primary daily goal, golden memories.
   - Chunk 6 (`687d5fd66b72...`): Cycle stand memories, returning from school.
   - Chunk 7 (`ec273a457d23...`): Intense teenage anxieties, fear of rivals, possessiveness in love.
   - Chunk 8 (`eff45c7e9ba4...`): Stellar exam results, announcements by Masutge Madam.
   - Chunk 9 (`84da15c958cb...`): Friends applauding together, shared triumph.
3. **Absolute Prohibition of Artificial Inflation:**  
   Authoring multiple queries per chunk to artificially expand $n$ to 30 is strictly forbidden.
4. **No Equivalence Claim:**  
   The 10-case Marathi census must **never** be represented as possessing the statistical power of an $n=30$ cohort.
5. **Mandatory Uncertainty Disclosure:**  
   All reporting must publish exact Wilson 95% score intervals alongside observed point estimates.

---

## 5. 30 Negative / No-Answer Control Policy

A dedicated cohort of 30 negative/unanswerable queries is established under `CASE_AUTHORING_POLICY.proposed.md`:
1. **Unanswerable by Construction:** Queries must pose plausible, natural questions topically related to the corpus (e.g., asking about nonexistent characters or non-covered engineering topics) for which zero supporting evidence exists in the candidate universe.
2. **Strict Metric Separation:** Negative cases have no grade-2 relevant targets and must **never** enter Recall@k, MRR, or nDCG@10 calculations.
3. **Behavioral Restraint Telemetry:** Evaluated exclusively on:
   - `no_answer_false_support_rate`: Fraction of queries returning any candidate marked as supporting evidence.
   - `no_answer_publication_rate`: Fraction of queries publishing a grounded answer despite absent evidence.

---

## 6. QREL Human-Review Requirements

Under `multilingual_qrels.schema.json` and the judgment contract, the following requirements are mandatory before candidate execution:
1. **Evidence-Level Identification:** Every record must specify exact opaque identifiers for `notebook_id`, `document_id`, `version_id`, `evidence_id`, and `source_content_hash`.
2. **Relevance Scale:** Exactly three ordinal grades ($0$: Irrelevant/Invalid, $1$: Partially supportive, $2$: Directly relevant).
3. **Dual Independent Review:** Every candidate pair must be judged independently by at least two certified human evaluators fluent in the query and evidence languages.
4. **Reviewer Blinding:** Evaluators must not see system identities, rankings, scores, or candidate builders.
5. **Formal Adjudication:** Disagreements ($0$ vs $1$ or $1$ vs $2$) must be marked `disputed` and resolved by a qualified third senior adjudicator.
6. **Zero AI Fabrication:**  
   > **"QREL population is pending human reviewer execution."**  
   Synthetic or LLM-generated QRELs are strictly forbidden.

---

## 7. Threshold Approval Blocker

1. **Preservation of Non-Defensible Status:**  
   `multilingual_threshold_contract.proposed.json` strictly preserves `"status": "NOT YET DEFENSIBLE"`, with all directional numeric floors set to `null`.
2. **Mandatory Governance Notice:**  
   > **"Directional quality thresholds require independent human governance approval before evaluation execution."**
3. **Anti-Backfitting Invariant:**  
   Thresholds must not be derived from the 18-case smoke run, current model scores, or agent recommendations. They must be established by human governance prior to evaluation.

---

## 8. Golden Corpus Immutability Confirmation

The 44-document Phase 8.5 Evaluation Corpus remains an immutable, read-only benchmark:
- **Corpus Name:** `phase8.5-golden-44-plus-frozen-authorized-derived-evidence-v1`
- **Frozen Directory:** `goldenDataset/Phase 8.5 Evaluation Corpus/`
- **Corpus SHA-256 Digest:** `78b414e77603fa1ded285ecfd77184f83badfde03b3b633154b097053b929a81` (**VERIFIED UNCHANGED**)
- Zero files were added, deleted, renamed, or modified.

---

## 9. Ramayana Representation Boundary

The status of `Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf` is strictly preserved:
1. **Original PDF Unchanged:** Byte-for-byte identical on disk (`759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75`).
2. **Legacy Font Status:** Kruti Dev / ShreeLip representations remain in their raw state.
3. **No Unilateral Conversion:** No synthetic Unicode transcription was performed.
4. **Governed Transformation Boundary:** A future Kruti Dev $\to$ Unicode conversion requires an independent representation transformation contract, pipeline run, provenance tracking, and evaluation.

---

## 10. Future Corpus-Expansion Boundary

1. **Current Phase Scope:** Phase 8.5 is strictly bounded to the frozen 44-document corpus and V2 database `build-20260831-01`.
2. **Future Corpus Expansion:** A separate, multi-document evaluation corpus expansion may be proposed under Phase 9 to resolve Marathi and Hindi evidence scarcity, add domain breadth, and support full 75-case/direction certification.
3. **Isolation Invariant:** Any future expansion must be built in an isolated database namespace with a new build run and alias set.

---

## 11. Files Changed

The following governance artifacts under `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/` were created or modified:

| File Path | Action | Description of Change |
|---|:---:|---|
| `HYBRID_STRATIFIED_EVALUATION_CONTRACT_AMENDMENT.proposed.md` | **NEW** | Formal amendment document codifying terms A through K of Option D. |
| `CASE_AUTHORING_POLICY.proposed.md` | **NEW** | Formal policy specifying authoring rules for answerable, Marathi census, and negative control cases. |
| `multilingual_evaluation_manifest.proposed.schema.json` | **MODIFY** | Updated `directionalCohort` schema: allows `proposed_minimum_cases: [10, 30]`, adds `cohort_classification` and `census_chunk_count`. |
| `multilingual_evaluation_manifest.proposed.json` | **MODIFY** | Encoded Option D in `sample_size_policy`; updated `directional_cohorts` to specify 10 cases for Marathi targets and 30 for English/Hindi targets. |
| `multilingual_threshold_contract.proposed.json` | **MODIFY** | Updated `sample_size_policy` to reference amendment; added mandatory notice that thresholds require human approval before execution. |
| `V2_HYBRID_EVALUATION_GOVERNANCE_AMENDMENT_REPORT.md` | **NEW** | This authoritative summary report. |

---

## 12. Files Explicitly Not Changed

To maintain absolute repository integrity, the following categories of files were **NOT** modified:
1. **Zero Runtime Code:** No files in `mnemo-core/mnemo/`, `mnemo-server/mnemo_server/`, or `scripts/` were edited.
2. **Zero Adapters:** `multilingual_dense_v2.py`, `multilingual_sparse_v2.py`, `full_multilingual_advanced_v2.py`, and `v2_runtime.py` are untouched.
3. **Zero Storage / Database Files:** `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` was opened only in read-only immutable mode; zero bytes changed.
4. **Zero Corpus Files:** `goldenDataset/` remains 100% byte-for-byte identical.
5. **Zero Models / Aliases:** Offline HuggingFace cache and SQLite active alias table remain identical.

---

## 13. Validation Results

1. **JSON Schema Conformance:**  
   `jsonschema.validate()` was executed on `multilingual_evaluation_manifest.proposed.json` against `multilingual_evaluation_manifest.proposed.schema.json`.  
   **Result:** **PASS (Exit code 0 — strictly conforms)**.
2. **Threshold Contract Parsing:**  
   `multilingual_threshold_contract.proposed.json` was parsed and verified as strictly valid JSON.  
   **Result:** **PASS (Exit code 0)**.
3. **Git Diff Line Hygiene:**  
   `git diff --check` was executed across the entire repository.  
   **Result:** **PASS (Zero trailing whitespace or formatting defects)**.
4. **Execution Invariant:** Zero evaluation queries or provider inference calls were dispatched during this task.

---

## 14. Protected Physical Disk Hashes

All 4 protected cryptographic digests were verified immediately following governance edits:

| Protected Target | Governed Expected Digest | Recomputed Disk Digest | Verification Status |
|---|---|---|:---:|
| **`manuscript.pdf`** | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | **IDENTICAL** |
| **`Valmiki Ramayana...pdf`** | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | **IDENTICAL** |
| **`mnemo.db`** | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | **IDENTICAL** |
| **Active Alias Digest** | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | **IDENTICAL** |

---

## 15. Lifecycle State

The repository lifecycle remains bounded in its governed pre-evaluation active state:

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

### Clarification of Distinctions:
- **GOVERNANCE PREPARED:** **TRUE** (Option D codified in formal proposed contracts).
- **EVALUATION EXECUTED:** **FALSE** (Not executed in this phase).
- **EVALUATED:** **FALSE** (Pending human QRELs, threshold approval, and execution).
- **VERIFIED:** **FALSE** (Pending multi-reviewer judgment verification).
- **CERTIFIED:** **FALSE** (Deferred to full 75-case/direction certification).

---

## 16. Remaining Human Decisions Before Evaluation Execution

Execution of the 240-case evaluation pack requires the following sequential human governance actions:

1. **Formal Sign-off on Amendment:** Approve `HYBRID_STRATIFIED_EVALUATION_CONTRACT_AMENDMENT.proposed.md`.
2. **Approval of Directional Utility Floors:** Approve numeric thresholds in `multilingual_threshold_contract.proposed.json` independently of model scores.
3. **Staffing of Dual Bilingual Human Reviewers:** Appoint certified human evaluators for English, Hindi, and Marathi to execute blinded QREL judgments under `multilingual_qrels.schema.json`.
4. **Adjudication of Disputed Judgments:** Senior adjudicator signs off on final QREL dataset.
5. **Cryptographic Freeze of Master Evaluation Pack:** Compute and freeze the SHA-256 digest of queries and QRELs before authorizing execution.
