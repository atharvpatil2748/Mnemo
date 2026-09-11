# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Hybrid Stratified Multilingual Evaluation Contract Amendment

**Document ID:** `mnemo.hybrid-stratified-evaluation-contract-amendment/1`  
**Date:** 2026-09-02  
**Scope:** Mnemo Phase 8.5 WP-10 Decision 7 — Directional Sample-Size and Cohort Amendment  
**Status:** **PROPOSAL — AWAITING HUMAN GOVERNANCE APPROVAL**  
**Parent Contract:** `multilingual_evaluation_contract.proposed.md`  

---

## 1. Amendment Rationale and Authority

The forensic readiness audit (`V2_GOVERNED_EVALUATION_PACK_READINESS_REPORT.md`) and decision audit (`V2_EVALUATION_DESIGN_GOVERNANCE_DECISION_AUDIT.md`) proved that the previously proposed uniform sample size heuristic ($\ge 30$ cases per direction across all 9 primary directions) conflicts directly with the physical reality of the immutable 44-document Phase 8.5 evaluation corpus:
- **Marathi Evidence Scarcity:** Only **10 chunks** exist in the entire V2 database (`language_text_projection_rows_v2`), all originating from a single file (`manuscript.pdf`). Enforcing 30 cases each for `en->mr`, `hi->mr`, and `mr->mr` ($90$ total queries) requires generating an average of 9 queries per 500-character chunk. This artificial repetition violates statistical case independence, produces extreme inter-query correlation, and risks evaluating chunk memorization rather than generalized retrieval.
- **Hindi Evidence Distribution:** Only ~90 chunks containing Devanagari Hindi text exist across the entire V2 database, concentrated in `PHYSICS_JEE_ADVANCED.pdf` (39 OCR chunks), `Bhagavad-gita` (46 chunks), `Atharv_Patil_240740.pdf` (6 chunks), and `Valmiki Ramayana` (2 chunks).
- **English Evidence Abundance:** Approximately 2,500 chunks across 38+ documents.

As established in `multilingual_evaluation_manifest.proposed.json` (line 112), the 30-case figure was a statistical heuristic, not an architectural mandate (`"Neither count is an existing architecture mandate."`).

This amendment formally establishes the **Hybrid Stratified Directional Policy (Option D)** for Phase 8.5 provisional evaluation.

---

## 2. Amended Directional Sample-Size Matrix

The uniform 30-case provisional evaluation requirement is hereby amended. For Phase 8.5 provisional evaluation, directional cohorts are stratified according to physical evidence availability in the immutable candidate universe:

| Target Language | Direction | Cohort Classification | Answerable Cases ($n$) | Target Evidence Universe | Statistical Characterization |
|---|---|---|---:|---|---|
| **English** | `en->en` | `STANDARD_PROVISIONAL` | **30** | ~2,500 chunks across 38+ docs | 3.33% rate resolution; Wilson 95% interval |
| **English** | `hi->en` | `STANDARD_PROVISIONAL` | **30** | ~2,500 chunks across 38+ docs | 3.33% rate resolution; Wilson 95% interval |
| **English** | `mr->en` | `STANDARD_PROVISIONAL` | **30** | ~2,500 chunks across 38+ docs | 3.33% rate resolution; Wilson 95% interval |
| **Hindi** | `en->hi` | `STANDARD_PROVISIONAL` | **30** | ~90 Devanagari chunks in V2 | 3.33% rate resolution; Wilson 95% interval |
| **Hindi** | `hi->hi` | `STANDARD_PROVISIONAL` | **30** | ~90 Devanagari chunks in V2 | 3.33% rate resolution; Wilson 95% interval |
| **Hindi** | `mr->hi` | `STANDARD_PROVISIONAL` | **30** | ~90 Devanagari chunks in V2 | 3.33% rate resolution; Wilson 95% interval |
| **Marathi** | `en->mr` | `CORPUS_CONSTRAINED_CENSUS` | **10** | **All 10 eligible Marathi chunks** | 10.0% rate resolution; exact census |
| **Marathi** | `hi->mr` | `CORPUS_CONSTRAINED_CENSUS` | **10** | **All 10 eligible Marathi chunks** | 10.0% rate resolution; exact census |
| **Marathi** | `mr->mr` | `CORPUS_CONSTRAINED_CENSUS` | **10** | **All 10 eligible Marathi chunks** | 10.0% rate resolution; exact census |
| **Total Answerable** | **9 Directions** | — | **210** | 3,019 V2 projection rows | Stratified Directional Baseline |
| **Negative Controls**| No-Answer | `NEGATIVE_CONTROL` | **30** | Whole candidate universe | False-support rate / publication rate |
| **Total Pack** | — | — | **240** | — | Phase 8.5 Master Evaluation Pack |

---

## 3. Marathi Corpus-Constrained Census Policy

For all three Marathi-target directions (`en->mr`, `hi->mr`, `mr->mr`), the following strict governance rules apply:

1. **Census Characterization:**  
   The Marathi cohort is an exhaustive census of all available canonical Marathi evidence chunks in the Phase 8.5 database (`document_id: cb86bb2f-8af6-5a0e-8bde-ae70fb22aac3`, `manuscript.pdf`).
2. **One Query per Chunk per Direction:**  
   In each directional cohort, exactly **one** answerable query is authored per chunk. For `en->mr`, 10 distinct queries test the 10 chunks; for `hi->mr`, 10 distinct queries test the 10 chunks; for `mr->mr`, 10 distinct queries test the 10 chunks.
3. **No Repeated-Query Inflation:**  
   It is strictly forbidden to author multiple queries targeting the same Marathi chunk within the same directional cohort to artificially satisfy a sample size of 30.
4. **No Statistical Equivalence Claim:**  
   A sample of $n=10$ provides 10.0 percentage-point resolution and a worst-case Wilson 95% interval of $[0.722, 1.000]$ at 100% observed success. The 10-case Marathi cohort must **never** be described as possessing statistical power equivalent to an $n=30$ cohort.
5. **Mandatory Uncertainty Disclosure:**  
   All evaluation reports and publications must report the exact Wilson 95% confidence intervals alongside raw point estimates for Marathi target retrieval.

---

## 4. Directional Independence and Non-Generalization

1. **Directional States are Non-Fungible:**  
   Retrieval scores on English-target directions (`en->en`, `hi->en`, `mr->en`) must never be averaged with or substituted for Marathi-target or Hindi-target scores to claim generalized multilingual performance.
2. **Independent Status Reporting:**  
   Every directional edge must be reported as an independent metric block with its own point estimates, sample size, and confidence interval.
3. **No Cross-Language Extrapolation:**  
   High performance on `en->mr` ($n=10$) does not prove high performance on `en->hi` ($n=30$), and vice versa. Each directional capability must stand on its own empirical evidence.

---

## 5. Certification Boundary

1. **Provisional Evaluation Only:**  
   This amendment defines the criteria for Phase 8.5 provisional evaluation. It authorizes the measurement required for `EVALUATED: PASS` eligibility within the documented scope of Phase 8.5.
2. **Certification Target Preserved:**  
   The full certification target remains governed at **75 answerable cases per direction** ($675$ total answerable cases).
3. **No Automatic Certification:**  
   Adoption of this amendment and successful execution of the 240-case evaluation does **NOT** grant `CERTIFIED` status. Full certification is deferred until multi-document corpus expansion is executed under a future governed phase.
