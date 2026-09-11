# Phase 8.5 WP-10 — Forensic Evidence Audit & Governance Report
## Multilingual Capability, Directional Cohorts, Krutidev Mechanics & Behavioral Verification

---

### Executive Summary

| Category | Forensic Status | Finding |
| :--- | :--- | :--- |
| **Lifecycle State** | **`EXPOSED` / `VERIFIED WITH EVIDENCE GAPS`** | Pipeline operationalized and exposed; behavioral and directional evidence gaps prevent full quality verification. |
| **Certification State** | **`NOT_CERTIFIED`** | No numeric certification thresholds have been approved by human governance. |
| **Decision-7 Coverage** | **6 Measured / 3 Unmeasured** | 18 queries across 6 directions; 3 Hindi-target directions (`EN→HI`, `HI→HI`, `MR→HI`) have $n=0$ cases and are strictly **UNMEASURED**. |
| **Reranker Pairwise Accuracy** | **`UNVERIFIED`** | No ground-truth decisive-pair dataset or pairwise evaluations exist in retained artifacts. |
| **WP-16 Behavioral Harness** | **`BEHAVIORAL VERIFICATION INSUFFICIENT`** | Scenarios P85-B-16..19 fail due to corpus translation status and generic prompt design; P85-B-20 passes on image OCR provenance. |
| **Ramayana / Krutidev Status** | **Legacy Font Encoded Body** | Thesis body is Krutidev 010 ANSI text; canonical chunks cannot be searched via Unicode embeddings without additive derivation. |

---

### 1. Valid Hindi Corpus Evidence vs. Evaluation Cases

Forensic analysis of the 44-document frozen Golden Dataset confirms the following distribution of Hindi evidence:

1. **`Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf`**
   * **Document ID:** `c59d2d22-66ca-52a2-93e7-9c5fa692a597` | **Version ID:** `5eb01752-1157-5250-b03b-712483cdf945`
   * **Total Canonical Chunks:** 502 chunks.
   * **Semantic Content:** Doctoral thesis by Dr. Karuna Sharma comparing Valmiki Ramayana and Thai Ramakien.
   * **Encoding State:** Authored in **legacy Krutidev 010 ANSI font encoding** (e.g., `,d rqyukRed v/;;u` represents "एक तुलनात्मक अध्ययन").
   * **OCR Region (Page 1):** Scanned embassy letterhead ("भारत का राजदूतावास, बेंकाक... सत्यमेव जयते... आमुख") contains **genuine Unicode Devanagari Hindi text** (`hi-Deva`).
2. **`Act 2. panch-parmeshwar-by-munshi-premchand.pdf`**
   * **Document ID:** `858ee588-466d-5ba2-ba26-1b489a2da38e`
   * **Language State:** English translation by T. C. Ghai (`en-Latn`). Contains zero Hindi source chunks.
3. **Other Hindi Evidence:**
   * Isolated OCR text in `Atharv_Patil_240740.pdf`, `Coordinator Application 2026–27`, `PHYSICS_JEE_ADVANCED.pdf`, and `Bhagavad-gita-As-It-Is.pdf` (Sanskrit/Hindi glosses).

---

### 2. Valid Hindi Decision-7 Cases & Actual Directional Counts

In the governed Decision-7 evaluation pack (`multilingual_evaluation_results.json`), exactly **18 legacy queries** exist across **6 directional cohorts**.

#### Actual Directional Case Counts ($n$):
* **`EN → EN`:** $n = 5$ cases (`MBSEL-01`, `MBSEL-07`, `MBSEL-10`, `MBSEL-13`, `MBSEL-16`)
* **`HI → EN`:** $n = 5$ cases (`MBSEL-02`, `MBSEL-08`, `MBSEL-11`, `MBSEL-14`, `MBSEL-17`)
* **`MR → EN`:** $n = 5$ cases (`MBSEL-03`, `MBSEL-09`, `MBSEL-12`, `MBSEL-15`, `MBSEL-18`)
* **`EN → MR`:** $n = 1$ case (`MBSEL-04`)
* **`HI → MR`:** $n = 1$ case (`MBSEL-05`)
* **`MR → MR`:** $n = 1$ case (`MBSEL-06`)
* **`EN → HI`:** $n = 0$ cases $\rightarrow$ **`UNMEASURED`**
* **`HI → HI`:** $n = 0$ cases $\rightarrow$ **`UNMEASURED`**
* **`MR → HI`:** $n = 0$ cases $\rightarrow$ **`UNMEASURED`**

> [!IMPORTANT]
> **Strict Governance Ruling:**
> Even though Hindi material exists in the corpus, **zero ($n=0$) valid governed qrels/evaluation cases** targeting Hindi chunks currently exist in the Decision-7 evaluation pack. Therefore, `EN→HI`, `HI→HI`, and `MR→HI` are strictly **`UNMEASURED`**. They must NOT be marked as "measured" or "partially measurable" until governed query-qrel pairs are constructed and audited.

---

### 3. Nine-Direction Coverage Matrix

| Direction | Cases ($n$) | Recall@1 | Recall@1 (95% Wilson CI) | MRR | nDCG@10 | Governed Classification |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **EN $\rightarrow$ EN** | 5 | 0.800 | `[0.376, 0.964]` | 0.800 | 0.800 | **MEASURED** |
| **EN $\rightarrow$ MR** | 1 | 0.000 | `[0.000, 0.793]` | 0.000 | 0.000 | **MEASURED** ($n=1$, wide interval) |
| **HI $\rightarrow$ EN** | 5 | 0.800 | `[0.376, 0.964]` | 0.867 | 0.900 | **MEASURED** |
| **HI $\rightarrow$ MR** | 1 | 0.000 | `[0.000, 0.793]` | 0.167 | 0.356 | **MEASURED** ($n=1$, wide interval) |
| **MR $\rightarrow$ EN** | 5 | 0.600 | `[0.231, 0.882]` | 0.700 | 0.726 | **MEASURED** |
| **MR $\rightarrow$ MR** | 1 | 1.000 | `[0.207, 1.000]` | 1.000 | 1.000 | **MEASURED** ($n=1$, wide interval) |
| **EN $\rightarrow$ HI** | **0** | — | — | — | — | **UNMEASURED** |
| **HI $\rightarrow$ HI** | **0** | — | — | — | — | **UNMEASURED** |
| **MR $\rightarrow$ HI** | **0** | — | — | — | — | **UNMEASURED** |

---

### 4. Krutidev Technical & Architectural Analysis

1. **Verification of Krutidev 010 Encoding:**
   * Canonical chunk byte inspection confirms standard Krutidev font mapping:
     * `,d` = `एक`
     * `rqyukRed` = `तुलनात्मक`
     * `v/;;u` = `अध्ययन`
     * `izLrkouk` = `प्रस्तावना`
   * The text in PDF stream is standard 8-bit Latin ASCII codepoints, not Unicode Devanagari (`U+0900..U+097F`).
2. **Immutability of Frozen Canonical Chunks:**
   * In accordance with ADR-0072 and Mnemo corpus invariants, canonical chunks in `chunks` table MUST NOT be rewritten or modified.
3. **Feasibility of Additive Krutidev $\rightarrow$ Unicode Derivation:**
   * A deterministic font transcode can be executed additively via `language_derivations` (e.g. `kind="font_transcode"`), preserving:
     * Original canonical chunk `text` untouched.
     * Exact `document_id`, `version_id`, `chunk_id`, and `occurrence_id`.
     * Transcoded UTF-8 Devanagari text projected into `language_text_projection_rows` and `multilingual_embeddings`.
4. **Architectural / Evaluation Consequence:**
   * **Without Additive Derivation:** Dense multilingual encoders (BGE-M3) cannot semantically match modern UTF-8 Hindi queries to Krutidev ASCII body text. Canonical Hindi body retrieval is therefore functionally degraded.
   * **With Additive Derivation:** Modern UTF-8 Hindi queries align cleanly with the transcoded Devanagari representation while maintaining 100% database immutability.
   * **Governance Status:** This derivation requires a future work package and governance specification before implementation.

---

### 5. Forensic Audit of Reranker Pairwise Accuracy

* **Audit Result:** **`RERANKER PAIRWISE ACCURACY: UNVERIFIED`**
* **Forensic Findings:**
  1. No pairwise judgment dataset or decisive-pair ground truth annotations exist in `multilingual_evaluation_results.json` or the evaluation package.
  2. No calculation runner computed pairwise win/loss ratios.
  3. The previous claim of "100% pairwise preference consistency" is an unverified assumption and is **formally retracted**.
  4. Pairwise accuracy remains **UNVERIFIED** until a formal human-labeled pair dataset ($A \succ B$) is constructed and evaluated.

---

### 6. WP-16 Multilingual Behavioral Scenarios (P85-B-16..20)

| Scenario ID | Prompt | Oracle Tool Sequence | Required Provenance | Audit Verdict | Root Cause / Forensic Reason |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P85-B-16** | "In English, find the Hindi material about Panch Parmeshwar." | `get_capabilities` $\rightarrow$ `search_evidence` | `document_id`, `version_id`, `language` | **`FAIL (SEMANTIC MISMATCH)`** | Corpus document is the English translation by T. C. Ghai (`en-Latn`). An English document cannot satisfy a request for Hindi material. |
| **P85-B-17** | "In English, find the Marathi material about the Ramayana comparison." | `get_capabilities` $\rightarrow$ `search_evidence` | `document_id`, `version_id`, `language` | **`FAIL (SEMANTIC MISMATCH)`** | `Valmiki Ramayana...pdf` is a Hindi thesis (Dr. Karuna Sharma), not Marathi material. A Hindi document cannot satisfy a request for Marathi material. |
| **P85-B-18** | `"इस हिंदी प्रश्न के लिए संबंधित अंग्रेज़ी सामग्री खोजें।"` | `get_capabilities` $\rightarrow$ `search_evidence` | `document_id`, `version_id`, `language` | **`FAIL (GENERIC / UNSPECIFIED)`** | Prompt contains no topical entity ("Find related English material for this Hindi question"). Returns low-score noise candidates. |
| **P85-B-19** | `"या मराठी प्रश्नासाठी संबंधित इंग्रजी पुरावा शोधा."` | `get_capabilities` $\rightarrow$ `search_evidence` | `document_id`, `version_id`, `language` | **`FAIL (GENERIC / UNSPECIFIED)`** | Prompt contains no topical entity ("Find related English evidence for this Marathi question"). Returns low-score noise candidates. |
| **P85-B-20** | "Retrieve the Marathi or Hindi text visible only inside an image." | `get_capabilities` $\rightarrow$ `search_evidence` $\rightarrow$ `get_image_analysis` | `document_id`, `version_id`, `occurrence_id`, `derivation_id`, `language` | **`PASS (PROVENANCE QUALIFIED)`** | Successfully retrieves OCR region containing genuine visible Indic text (e.g., Hindi embassy seal in Ramayana p.1 or Marathi diagrams in ME361) with complete image provenance chain. |

---

### 7. Lifecycle State Assessment & Downgrades

* **`BUILDABLE`:** **CONFIRMED** (All 4 projection layers compile and execute without errors).
* **`READY`:** **CONFIRMED** (All generation artifacts indexed, checksummed, and verified idempotent).
* **`ACTIVE`:** **CONFIRMED** (Active generation aliases registered in `active_index_generations`).
* **`EXPOSED`:** **CONFIRMED** (`CapabilityDiscoveryService` dynamically discovers and advertises `multilingual_retrieval`).
* **`VERIFIED`:** **DOWNGRADED TO `VERIFIED WITH EVIDENCE GAPS`**
  * **Behavioral Verification:** `BEHAVIORAL VERIFICATION INSUFFICIENT` (4 of 5 behavioral scenarios fail due to corpus mismatch / generic prompts).
  * **Directional Verification:** 3 of 9 directional cohorts (`EN→HI`, `HI→HI`, `MR→HI`) are `UNMEASURED` ($n=0$).
  * **Reranker Verification:** Pairwise accuracy is `UNVERIFIED`.
* **`CERTIFIED`:** **`NOT_CERTIFIED`**
  * Numeric Decision-7 certification floors remain open pending human governance calibration.

---

### 8. Exact Remaining Blockers for WP-17 Certification Gate

1. **Zero Hindi-Target Cases ($n=0$):**
   * Construction of governed Decision-7 evaluation cases targeting valid Hindi evidence (e.g. OCR front matter or additive transliterations) with explicit qrels.
2. **Krutidev Encoding Impedance:**
   * Canonical body chunks in the Ramayana thesis require an authorized additive Krutidev $\rightarrow$ Unicode derivation pass to enable dense semantic matching against modern Devanagari query vectors.
3. **Behavioral Manifest Topical Realignment:**
   * Revision of P85-B-16..19 prompts in `behavioral_manifest.json` to reference valid corpus topics and languages.
4. **Reranker Pairwise Dataset:**
   * Creation and evaluation of a ground-truth pairwise preference dataset to establish reranker pairwise accuracy.
5. **Governance Threshold Approval:**
   * Formal human governance approval of Decision-7 numeric utility floors.
