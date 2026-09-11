# PROPOSED — REQUIRES HUMAN/GOVERNANCE APPROVAL
# Phase 8.5 Multilingual 240-Case Evaluation Authoring Policy

**Document ID:** `mnemo.multilingual-case-authoring-policy/1`  
**Date:** 2026-09-02  
**Scope:** Rules for Authoring Queries, QRELs, and Controls for the 240-Case Governed Evaluation Pack  
**Status:** **PROPOSAL — AWAITING HUMAN GOVERNANCE APPROVAL**  

---

## 1. General Principles for Answerable Cases

Every answerable semantic retrieval case in the 210-case answerable inventory must satisfy the following criteria:

1. **Existence in Candidate Universe:**  
   The supporting evidence must physically exist within the frozen Phase 8.5 V2 database (`scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`) under active generation `a7220adf-202c-536e-8e7c-c09d4d4c563f`.
2. **Strict Authorization Scope:**  
   The evidence must be bounded by the governed notebook ID (`df9c20cf-85fe-529c-902e-2e9e68193fbe`) and pass `CentralAuthorizationServiceV1` validation.
3. **Genuine Semantic Content:**  
   The evidence must contain authentic text content. Metadata substitution, document titles, file basenames, page headers, and blank chunks are strictly prohibited as grade-2 supporting evidence.
4. **Defensible Grade-2 Target:**  
   The query must pose a natural, information-seeking question whose complete or direct factual answer is contained within the targeted evidence chunk.
5. **Evidence-Level Identification:**  
   Relevance must be established at the chunk/evidence level (UUID / content hash), never at the document level. Multiple chunks in the same document must not be presumed relevant unless individually evaluated.
6. **No Artificial Duplication:**  
   Cases must represent genuinely distinct information needs. Authoring trivial syntactic rephrasings of the same question to meet sample-size counts is prohibited.

---

## 2. Marathi Target Case Authoring (30 Cases: `en->mr`, `hi->mr`, `mr->mr`)

Because Marathi evidence is confined to the 10 canonical chunks of `manuscript.pdf`, authoring must follow a **deterministic census protocol**:

1. **Exact 1-to-1 Mapping:**  
   Each directional cohort (`en->mr`, `hi->mr`, `mr->mr`) contains exactly **10 queries**, each uniquely mapped to one of the 10 canonical Marathi chunks:
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
2. **Linguistic Naturalness:**  
   Queries in English (`en->mr`) and Hindi (`hi->mr`) must represent natural cross-lingual formulations, not robotic word-for-word glosses. Queries in Marathi (`mr->mr`) must use idiomatic Marathi syntax.

---

## 3. English and Hindi Target Case Authoring (180 Cases: 6 Directions $\times$ 30)

For directions targeting English (~2,500 chunks) and Hindi (~90 chunks):

1. **Topic and Document Diversity:**  
   Queries must be distributed across diverse domains in the corpus:
   - Technical Architecture & Code (`server.js`, `llmPrompt.js`, `llmGuard.js`)
   - Engineering Coursework & Manufacturing Processes (`ME361_L1`, `ME361_L2-L4`, `ME381 Lab`)
   - Tabular Statistics & CPI Metrics (`Y24_CPI.csv`)
   - Academic Qualifications & Transcripts (`Atharv_Patil_RESUME_SDE.pdf`, `Atharv_Patil_240740.pdf`, `Coordinator Application 2026–27`)
   - Hindi Physics Problems (`PHYSICS_JEE_ADVANCED.pdf`)
   - Philosophical & Classical Commentary (`Bhagavad-gita As It Is with pics!`)
2. **Chunk Concentration Limits:**  
   No single evidence chunk may serve as the primary grade-2 target for more than two queries within the same directional cohort.
3. **Preservation of Diagnostic Cases:**  
   The three historical resume cases (`MBSEL-01`, `MBSEL-02`, `MBSEL-03`) targeting `Atharv_Patil_RESUME_SDE.pdf` (`be46ea61-65ba-58be-8f45-905b2181e59a`) must be preserved unchanged within `en->en`, `hi->en`, and `mr->en` to track longitudinal performance.

---

## 4. Negative / No-Answer Control Cohort (30 Cases)

A dedicated cohort of 30 negative/unanswerable queries must be maintained to evaluate hallucination resistance and retrieval restraint:

1. **Plausible but Absent Facts:**  
   Queries must be phrased naturally and appear topically relevant to the corpus (e.g., asking about advanced deep learning topics not in ME361, or nonexistent characters in `manuscript.pdf`), but have **zero** supporting evidence in the candidate universe.
2. **Exclusion from Quality Ranking Metrics:**  
   Negative cases have no grade-2 targets. They must **never** be included in macro Recall@k, MRR, or nDCG@10 calculations.
3. **Dedicated Metric Scoring:**  
   Negative cases are scored exclusively on:
   - `no_answer_false_support_rate`: Percentage of queries where any returned candidate is represented as direct support.
   - `no_answer_publication_rate`: Percentage of queries where a grounded answer is published despite absent evidence.
