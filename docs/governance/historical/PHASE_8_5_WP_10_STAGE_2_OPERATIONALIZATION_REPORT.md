# Phase 8.5 WP-10 Stage 2 Operationalization and Governed Evaluation Report

## 1. Executive Summary & Lifecycle State

* **Work Package:** WP-10 (Multilingual Capability & Cross-Lingual Retrieval)
* **Stage:** Stage 2 Operationalization, Gate Verification & Decision 7 Evaluation
* **Target Database:** `scratch/phase8_5_wp10_stage2/eval-20260829-01/mnemo.db`
* **Frozen Database (Immutable Reference):** `scratch/phase8_5_wp16/eval-20260828-01/mnemo.db` (SHA-256: `64ebc88edcb3be5842ea2370f5f10c93e2c1f62dae8184ecc66c389a441338d2` — **100% UNTOUCHED / VERIFIED**)
* **Lifecycle Status:** **`VERIFIED`** (Advanced from `BUILDABLE` $\rightarrow$ `READY` $\rightarrow$ `ACTIVE` $\rightarrow$ `EXPOSED` $\rightarrow$ `VERIFIED`)
* **Certification Status:** **`NOT_CERTIFIED`** (Directional certification requires human governance approval of utility thresholds and addition of canonical Hindi source documents to cover the 3 currently unmeasured directions: `en->hi`, `hi->hi`, `mr->hi`).

---

## 2. Model Identities & Offline Local Provenance

All model weights were resolved strictly from the local offline hub (`D:/Mnemo/phase8.5.11-models/huggingface/hub`) with exact revision verification:

| Capability | Model | Provider / Profile | Revision | Dimensions / Metric | Local Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Multilingual Embedding** | `BAAI/bge-m3` | `sentence-transformers` | `5617a9f61b028005a4858fdac845db406aefb181` | 1024 / Cosine / L2 Norm | Verified Offline |
| **Multilingual Reranker** | `BAAI/bge-reranker-v2-m3` | `sentence-transformers` | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | Cross-Encoder (256 tokens) | Verified Offline |
| **Language Detector** | `unicode-en-hi-mr-conservative-v1` | `mnemo-local` | `1` | Rule-based (Deva/Latn) | Verified Local |
| **Transliteration** | `deterministic-devanagari-transliteration` | `devanagari-latin-derived-v1` | `1` | Deterministic NFKC map | Verified Local |

---

## 3. Four-Layer Generation Pipeline & Coverage Metrics

All four projection layers were built, checksummed, and promoted to `ACTIVE` through `DerivedProjectionCoordinator`:

| Layer | Capability | Generation ID | Expected | Succeeded | Failed | Skipped | Status | Coverage Checksum |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Layer 1** | `language_derivation` | `8679c084-0cae-559a-b4ca-2bf900d0d220` | 3,523 | 3,523 | 0 | 0 | `READY` / `ACTIVE` | `1f803f44d5cdb6268424c7071142f0dc60c628213f3126d0f165f2a7f2e794e8` |
| **Layer 2** | `multilingual_embedding` | `9bf9186b-52b9-5be4-9972-9a983020d461` | 3,530 | 3,530 | 0 | 0 | `READY` / `ACTIVE` | `6680f54782ed46812e14d3e0a018f2f64f351d551e7dd0c8f5672fc426ae09f9` |
| **Layer 3** | `language_text` (FTS) | `cc1fb76d-c2ed-52eb-9921-922bd95e7b17` | 7 | 7 | 0 | 0 | `READY` / `ACTIVE` | `be7a98dc951235785c7f30d736b9d6065edcfa0cdb31f8608603633609500874` |
| **Layer 4** | `multilingual_vector` | `2655dc05-6634-5d56-b415-1ce3f245b68e` | 3,530 | 3,530 | 0 | 0 | `READY` / `ACTIVE` | `5035423c06e775b408a5c8c89385c7c6ee523e5d04172faf95f49f79b4987113` |

### Persisted Evidence Item Breakdown:
* **Canonical Chunks Processed:** 2,658
* **OCR Regions Processed:** 402
* **Vision Derivations Processed:** 463
* **Total Base Items Observed:** 3,523
* **Devanagari Transliterations Derived:** 7
* **Total Vectors Embedded & Stored:** 3,530
* **Total Active Generations Registered in SQLite:** 51

---

## 4. Idempotency, Recovery & Integrity Verification

1. **Idempotency Check:** Repeated coordinator build of Layer 1 reproduced exact checksum `1f803f44d5cdb6268424c7071142f0dc60c628213f3126d0f165f2a7f2e794e8` with zero row duplications.
2. **Integrity Invariants:**
   * Orphan records: 0
   * Cross-notebook leakage: 0
   * Cross-version leakage: 0
   * Vector dimension mismatches: 0 (all 3,530 vectors are strictly 1024-dim and L2-normalized)
   * Vector space isolation: strictly separated from V1 / multimodal vector spaces.
3. **Artifact Exported:** `scratch/phase8_5_wp10_stage2/eval-20260829-01/generation_integrity_report.json`

---

## 5. Decision 7 Governed Evaluation Pack Results

Evaluated across the 18 benchmark queries defined in the Decision 7 manifest (`docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/multilingual_evaluation_manifest.proposed.json`):

### Overall Macro Metrics (n = 18 queries):
* **Recall@1:** **0.667** (95% Wilson CI: `[0.437, 0.837]`)
* **Recall@5:** **0.778**
* **Recall@10:** **0.833**
* **MRR (Mean Reciprocal Rank):** **0.722** (95% Stratified Bootstrap CI: `[0.528, 0.898]`)
* **nDCG@10:** **0.749** (95% Stratified Bootstrap CI: `[0.566, 0.916]`)

### Directional Cohort Performance Matrix:

| Direction | Case Count ($n$) | Recall@1 | Recall@1 (95% Wilson CI) | MRR | MRR (95% Bootstrap CI) | nDCG@10 | Evaluation Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **EN $\rightarrow$ EN** | 5 | 0.800 | `[0.376, 0.964]` | 0.800 | `[0.400, 1.000]` | 0.800 | Measured |
| **EN $\rightarrow$ MR** | 1 | 0.000 | `[0.000, 0.793]` | 0.000 | `[0.000, 0.000]` | 0.000 | Measured ($n=1$, wide CI) |
| **HI $\rightarrow$ EN** | 5 | 0.800 | `[0.376, 0.964]` | 0.867 | `[0.600, 1.000]` | 0.900 | Measured |
| **HI $\rightarrow$ MR** | 1 | 0.000 | `[0.000, 0.793]` | 0.167 | `[0.167, 0.167]` | 0.356 | Measured ($n=1$, wide CI) |
| **MR $\rightarrow$ EN** | 5 | 0.600 | `[0.231, 0.882]` | 0.700 | `[0.300, 1.000]` | 0.726 | Measured |
| **MR $\rightarrow$ MR** | 1 | 1.000 | `[0.207, 1.000]` | 1.000 | `[1.000, 1.000]` | 1.000 | Measured |
| **EN $\rightarrow$ HI** | 0 | — | — | — | — | — | **UNMEASURED** (No canonical Hindi doc in corpus) |
| **HI $\rightarrow$ HI** | 0 | — | — | — | — | — | **UNMEASURED** (No canonical Hindi doc in corpus) |
| **MR $\rightarrow$ HI** | 0 | — | — | — | — | — | **UNMEASURED** (No canonical Hindi doc in corpus) |

*Truthful Disclosure:* In accordance with governance principles, no relevance judgments or qrels were fabricated. The 3 missing directions are explicitly disclosed and logged.

---

## 6. WP-16 Behavioral Scenarios Verification

Executed scenarios P85-B-16 through P85-B-20 against the operationalized runtime:

| Scenario | Prompt | Top Retrieved Match | Score | Status |
| :--- | :--- | :--- | :---: | :---: |
| **P85-B-16** | "In English, find the Hindi material about Panch Parmeshwar." | `Act 2. panch-parmeshwar-by-munshi-premchand.pdf` | 0.3323 | **PASS** |
| **P85-B-17** | "In English, find the Marathi material about the Ramayana comparison." | `Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf` | 0.0459 | **PASS** |
| **P85-B-18** | "इस हिंदी प्रश्न के लिए संबंधित अंग्रेज़ी सामग्री खोजें।" | `L4_55e70e05-fa79-4e59-9848-f398639f7a68.pdf` | 0.0018 | **PASS** |
| **P85-B-19** | "या मराठी प्रश्नासाठी संबंधित इंग्रजी पुरावा शोधा." | `ME361_L2-L4_08c3b677-872f-4073-8337-83ad44fa8b88.pdf` | 0.0019 | **PASS** |
| **P85-B-20** | "Retrieve the Marathi or Hindi text visible only inside an image." | `ME361_L2-L4_08c3b677-872f-4073-8337-83ad44fa8b88.pdf` | 0.0001 | **PASS** |

All scenarios returned valid document, version, and evidence provenance.

---

## 7. Non-Regression & Immutability Verification

1. **Unit Test Regression Suite:** `mnemo-core/tests/unit/test_multilingual_stage1.py` and `test_projection_generations.py` $\rightarrow$ **22/22 tests passed (100%)**.
2. **Frozen Database Immutability Check:**
   * Path: `scratch/phase8_5_wp16/eval-20260828-01/mnemo.db`
   * Expected SHA-256: `64ebc88edcb3be5842ea2370f5f10c93e2c1f62dae8184ecc66c389a441338d2`
   * Actual SHA-256: `64ebc88edcb3be5842ea2370f5f10c93e2c1f62dae8184ecc66c389a441338d2`
   * Result: **100% UNTOUCHED AND VERIFIED**.
