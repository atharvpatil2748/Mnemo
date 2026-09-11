# V2 Governed Evaluation Pack Readiness Report

**Date:** 2026-09-02  
**Task:** Prepare and Audit Governed Multilingual Evaluation Pack  
**Scope:** Mnemo Phase 8.5 WP-10 Decision 7 — Provisional 270-Case Cohort Readiness  
**Auditor:** Antigravity Engineering (governed handoff)  
**Status:** **COMPLETE — EVALUATION PACK AUDIT & DESIGN**  
**Final Determination:** **EVALUATION PACK NOT READY** (6 Concrete Blockers Identified)  

---

## 1. Existing Evaluation Assets

A comprehensive audit of `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/` and related governance repositories confirms the existence of the following foundational evaluation assets:

| Artifact Path | Formal Purpose | Current Governed Status |
|---|---|:---:|
| `multilingual_evaluation_contract.proposed.md` | Primary architectural and governance contract defining directional cohorts, sample-size policies, evidence grades, metrics, and uncertainty intervals. | **PROPOSED** (Awaiting human/governance sign-off) |
| `multilingual_evaluation_contract.proposed.schema.json` | JSON Schema validating structural compliance of evaluation contracts. | **ACTIVE SCHEMA** |
| `multilingual_evaluation_manifest.proposed.json` | Master evaluation manifest skeleton defining cohort metadata, metric policies, zero-tolerance gates, and the reconstructed 18-case `legacy_selection_cohort`. | **PROPOSED** (Contains empty query/judgment lists for all 9 directional cohorts) |
| `multilingual_evaluation_manifest.proposed.schema.json` | JSON Schema validating evaluation manifests. | **ACTIVE SCHEMA** |
| `multilingual_qrels.schema.json` | Strict normative JSON schema (`mnemo.multilingual-qrel/1`) for evidence-level judgments enforcing `notebook_id`, `document_id`, `version_id`, `evidence_kind`, `evidence_id`, `relevance_grade` ($0..2$), dual-reviewer metadata, and adjudication states. | **ACTIVE SCHEMA** |
| `multilingual_threshold_contract.proposed.json` | Defines provisional and certification utility floors. | **PROPOSED** (`status: "not_yet_defensible"`) |
| `MULTILINGUAL_EVALUATION_ARCHITECTURE.proposed.md` | Architectural blueprint mandating layered diagnostic gates, query classes, production-path parity, and evidence-level qrels. | **PROPOSED** |
| `FAILURE_TAXONOMY.proposed.json` | Standardized failure codes across corpus, detection, representation, provider, retrieval, fusion, reranking, and authorization. | **PROPOSED** |
| `V2_POST_EVALUATION_DETERMINATION_AUDIT.md` | Authoritative audit confirming that the 18-case smoke run does not establish governed `EVALUATED: PASS` status. | **PASS (Audit Complete)** |

---

## 2. Missing Governed Assets

The following mandatory assets do **not** exist in the repository and must be created before a governed evaluation can execute:

1. **Populated 270-Case Query Inventory:** All 9 directional cohorts in `multilingual_evaluation_manifest.proposed.json` have empty query arrays (`"queries": []`). No governed 270-query inventory exists.
2. **Populated Evidence-Level QREL Records:** All 9 directional cohorts have empty judgment arrays (`"judgments": []`). Zero `mnemo.multilingual-qrel/1` records exist in the repository.
3. **Independent Multi-Reviewer Adjudication Data:** Zero human judgments have been recorded. No dual-reviewer independent evaluation has occurred covering English, Hindi, and Marathi.
4. **Approved Numeric Quality Thresholds:** `threshold_contract.status` remains `"not_yet_defensible"`. Numeric floors (`recall_at_1_min`, `mrr_min`, `ndcg_at_10_min`) are all `null`.
5. **No-Answer / Negative Diagnostic Suite:** Zero unanswerable/negative queries have been authored to measure false-support publication rates.
6. **Corpus Evidence Balance:** The underlying 44-document V2 database contains severe target-evidence language asymmetry (only 10 Marathi chunks and ~90 Hindi chunks out of 3,019 total projection rows).

---

## 3. Nine-Direction Coverage Matrix

The governed requirement specifies at least 30 answerable cases for each of the 9 primary language directions (minimum provisional size: $9 \times 30 = 270$ cases; certification target: $9 \times 75 = 675$ cases):

| Direction | Source $\to$ Target Language | Existing Smoke Cases | Minimum Provisional Target | Certification Target | Provisional Deficit | Available Target Chunks in V2 | Feasibility & Saturation Assessment |
|---|---|---:|---:|---:|---:|---:|---|
| **`en->en`** | English $\to$ English | 5 | 30 | 75 | **+25** | ~2,500 | **FEASIBLE** (Abundant corpus evidence across 38+ docs) |
| **`en->hi`** | English $\to$ Hindi | 0 | 30 | 75 | **+30** | ~90 | **CONSTRAINED** (Restricted to Physics, Gita, Ramayana) |
| **`en->mr`** | English $\to$ Marathi | 1 | 30 | 75 | **+29** | **10** | **CRITICALLY CONSTRAINED** (3.0 queries/chunk across 1 doc) |
| **`hi->en`** | Hindi $\to$ English | 5 | 30 | 75 | **+25** | ~2,500 | **FEASIBLE** (Cross-lingual query over English corpus) |
| **`hi->hi`** | Hindi $\to$ Hindi | 0 | 30 | 75 | **+30** | ~90 | **CONSTRAINED** (Same-language retrieval on restricted Hindi chunks) |
| **`hi->mr`** | Hindi $\to$ Marathi | 1 | 30 | 75 | **+29** | **10** | **CRITICALLY CONSTRAINED** (3.0 queries/chunk across 1 doc) |
| **`mr->en`** | Marathi $\to$ English | 5 | 30 | 75 | **+25** | ~2,500 | **FEASIBLE** (Cross-lingual query over English corpus) |
| **`mr->hi`** | Marathi $\to$ Hindi | 0 | 30 | 75 | **+30** | ~90 | **CONSTRAINED** (Cross-lingual query over restricted Hindi chunks) |
| **`mr->mr`** | Marathi $\to$ Marathi | 1 | 30 | 75 | **+29** | **10** | **CRITICALLY CONSTRAINED** (3.0 queries/chunk across 1 doc) |
| **TOTAL** | **9 Directions** | **18** | **270** | **675** | **+252** | **3,019** | **BLOCKED BY MARATHI & HINDI TARGET ASYMMETRY** |

---

## 4. Proposed 270-Case Inventory Design

To achieve statistical power for the provisional evaluation, an inventory schema has been established. Every case is uniquely identified, linguistically typed, and bound directly to physical V2 evidence chunks.

### Proposed Cohort Distribution:
- **`en->en` (30 cases):** `P85-EVAL-ENEN-001` to `030` — Broad technical, syllabic, tabular, and resume queries targeting English chunks.
- **`en->hi` (30 cases):** `P85-EVAL-ENHI-001` to `030` — English queries targeting Hindi/Devanagari chunks in `PHYSICS_JEE_ADVANCED.pdf`, `Bhagavad-gita`, and `Atharv_Patil_240740.pdf`.
- **`en->mr` (30 cases):** `P85-EVAL-ENMR-001` to `030` — English queries targeting narrative autobiographical chunks in `manuscript.pdf`.
- **`hi->en` (30 cases):** `P85-EVAL-HIEN-001` to `030` — Hindi queries targeting English technical documentation, course notes, CSV data, and code.
- **`hi->hi` (30 cases):** `P85-EVAL-HIHI-001` to `030` — Hindi queries targeting Hindi/Devanagari physics, philosophical commentary, and institutional records.
- **`hi->mr` (30 cases):** `P85-EVAL-HIMR-001` to `030` — Hindi queries targeting Marathi narrative chunks in `manuscript.pdf`.
- **`mr->en` (30 cases):** `P85-EVAL-MREN-001` to `030` — Marathi queries targeting English technical documentation, course notes, CSV data, and code.
- **`mr->hi` (30 cases):** `P85-EVAL-MRHI-001` to `030` — Marathi queries targeting Hindi physics problems, Gita slokas, and institutional records.
- **`mr->mr` (30 cases):** `P85-EVAL-MRMR-001` to `030` — Marathi queries targeting Marathi narrative chunks in `manuscript.pdf`.

### Exemplar Concrete Cases Grounded in Verified Physical V2 Chunks:

#### Case 1: `P85-EVAL-ENMR-001` (`en->mr`)
- **Query Text:** "On what specific date did the author begin writing the Marathi book?"
- **Query Language:** `en`
- **Direction:** `en->mr`
- **Target Document:** `manuscript.pdf` (`cb86bb2f-8af6-5a0e-8bde-ae70fb22aac3`)
- **Target Version:** `0a97b233-0bb6-5da6-8332-6bf6f3a74341`
- **Authoritative Chunk ID:** `664b29abcc58434778be9b25a3371f457782b7db5c5132d43e5066db475871f3`
- **Source Content Hash:** `d598923e4eb665a3d70b74fb296ad5bb9c1cae8b15d26391d3680fe03c2bb6f4`
- **Target Chunk Text:** *"माझे पुस्तक\n\nसुरुवात: 27 May 2026\n\nमला आठवतं, मी सेजलला एक द..."*
- **Relevance Grade:** `2` (Direct Support)
- **Topic:** Marathi Memoir / Narrative
- **Expected Answerability:** `answerable`
- **Provenance Reference:** `native_v3` / `canonical_chunk`

#### Case 2: `P85-EVAL-HIEN-001` (`hi->en`)
- **Query Text:** "ME361 पाठ्यक्रम के व्याख्यान 1 में कौन सी विनिर्माण प्रक्रियाएं बताई गई हैं?"
- **Query Language:** `hi`
- **Direction:** `hi->en`
- **Target Document:** `ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1)` (`a76bdd39-f323-5f74-85bd-7c0f0bf679b0`)
- **Target Version:** `7f04ef05-df35-5a5f-9721-c4beaeef7e2c`
- **Authoritative Chunk ID:** `c2aaebbb5b8396e0db668fb4f9715a1a1f0a203f395da7741dcf94ee899cb6ca`
- **Source Content Hash:** `fe1b34e451b69234b41b4e062e7aa2db27699ca098cb9bfba8d88e0e37761005`
- **Target Chunk Text:** *"Manufacturing Science – I (ME361) ... Machining: Conventional and Non-conventional processes..."*
- **Relevance Grade:** `2` (Direct Support)
- **Topic:** Academic / Engineering Syllabus
- **Expected Answerability:** `answerable`
- **Provenance Reference:** `native_v3` / `canonical_chunk`

#### Case 3: `P85-EVAL-ENHI-001` (`en->hi`)
- **Query Text:** "In the Hindi physics problem, what is the formula for the escape velocity of a projectile?"
- **Query Language:** `en`
- **Direction:** `en->hi`
- **Target Document:** `PHYSICS_JEE_ADVANCED.pdf` (`fb0824c4-066d-5be5-9442-cdff2cea987e`)
- **Target Version:** `2a329be6-7a42-5f60-994c-83675a396263`
- **Authoritative Evidence ID:** `e08a6b25-0604-5853-90d2-dfc79219602e`
- **Evidence Kind:** `ocr_region`
- **Occurrence ID:** `b817f54c-cb14-5d51-87a2-dfb8a6e87902`
- **Source Content Hash:** `72ba54de56ab41029e84b3d819c961e598711e51381283c481aa42d4a2360b0e`
- **Target Chunk Text:** *"पलायन वेग: पृथ्वी की सतह से किसी पिण्ड को दिया गया वह न्यूनतम वेग..."*
- **Relevance Grade:** `2` (Direct Support)
- **Topic:** Physics / Science
- **Expected Answerability:** `answerable`
- **Provenance Reference:** `native_v3` / `ocr_region`

#### Case 4: `P85-EVAL-MRMR-001` (`mr->mr`)
- **Query Text:** "लेखकाने सातवीच्या वर्गात प्रवेश केला तेव्हा त्यांच्या वर्गशिक्षिका कोण होत्या?"
- **Query Language:** `mr`
- **Direction:** `mr->mr`
- **Target Document:** `manuscript.pdf` (`cb86bb2f-8af6-5a0e-8bde-ae70fb22aac3`)
- **Target Version:** `0a97b233-0bb6-5da6-8332-6bf6f3a74341`
- **Authoritative Chunk ID:** `af8142c90b991b8d27376c498394fe3d3b7bc4b83f47e335279621370aa25ba8`
- **Source Content Hash:** `23ad6809ae54308a383d47d4e3bbda35ef65fc8e19e782e3656ab10287ad41cb`
- **Target Chunk Text:** *"मी इयत्ता सातवीमध्ये प्रवेश केला. आमच्या वर्गशिक्षिका होत्या मसुटगे मॅडम; आणि त्याच जुन्या मित्रांसोबत..."*
- **Relevance Grade:** `2` (Direct Support)
- **Topic:** Marathi Memoir / Narrative
- **Expected Answerability:** `answerable`
- **Provenance Reference:** `native_v3` / `canonical_chunk`

---

## 5. Evidence-Level QREL Readiness

### Storage and Evidence Model Capabilities:
Inspection of SQLite `language_text_projection_rows_v2` and the `LanguageEvidenceReferenceV3` serialization reveals that **the storage model fully supports exact evidence-level resolution**:
- `notebook_id`: Governed UUID (`df9c20cf-85fe-529c-902e-2e9e68193fbe`).
- `document_id`: Governed UUID per file.
- `version_id`: Governed UUID per version.
- `evidence_kind`: Accurately resolved (`canonical_chunk`, `ocr_region`, `vision_derivation`).
- `evidence_id`: Exact UUID or content hash locator.
- `source_content_hash`: SHA-256 digest of exact projection text.

### Schema Alignment:
The existing schema `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/multilingual_qrels.schema.json` matches these fields directly with zero schema modification required.

### Contract Gap:
While the storage model and JSON schema are technically ready, **populated, adjudicated instances do not exist on disk**. The repository contains zero files conforming to `mnemo.multilingual-qrel/1`.

---

## 6. Adjudication Requirements

Under `multilingual_evaluation_contract.proposed.md` Section 4, the following human governance procedures are mandatory before any QREL file can be admitted:

1. **Dual Independent Human Review:** Every query-evidence candidate pair must be reviewed independently by at least two qualified evaluators.
2. **Linguistic Competency:** Evaluators must be certified fluent in both the query language and the evidence language. For cross-lingual pairs (e.g., `mr->en` or `en->hi`), evaluators must be competent across both languages.
3. **Blinded Evaluation:** Reviewers must not see candidate rankings, retrieval model scores, candidate builders, or system identifiers.
4. **Dispute Adjudication:** Where independent reviewers disagree ($0$ vs $1$, or $1$ vs $2$), the record must be marked `disputed` and submitted to a third senior adjudicator to produce the final `adjudicated` state.
5. **No Synthetic / Automated QRELs:** LLM-generated or heuristically generated QRELs are strictly forbidden by the governance contract.

---

## 7. Quality Threshold Status

### Governance Audit:
Inspection of `multilingual_threshold_contract.proposed.json` and `multilingual_evaluation_manifest.proposed.json` establishes:
- **Contract Status:** `"not_yet_defensible"`
- **Approval State:** `"proposal_requires_human_governance_approval"`
- **Numeric Floors:** All directional certification floors (`recall_at_1_min`, `mrr_min`, `ndcg_at_10_min`) remain `null`.

### Ruling:
```text
QUALITY THRESHOLD: NOT YET APPROVED
```
Under Section 7 of the evaluation contract, numeric thresholds cannot be retroactively fitted to observed candidate scores. They must be established by human governance prior to formal evaluation.

---

## 8. Corpus and Topic Coverage

The 44-document Phase 8.5 Evaluation Corpus contains 3,019 V2 projection rows distributed across distinct topics:

| Topic Area | Exemplar Documents | Language Representation | Chunk Count | Suitability for Evaluation |
|---|---|---|---:|---|
| **Software Architecture & Code** | `server.js`, `llmPrompt.js`, `llmGuard.js`, `llmRouter.js`, `aiSwitch.js` | English / Code | ~600 | High utility for `en->en`, `hi->en`, `mr->en`. |
| **Engineering Education** | `ME361_L1`, `ME361_L2-L4`, `ME381 Lab`, `ME333 Lab Report` | English | ~750 | High utility for technical terminology across all query languages. |
| **Philosophy & Classics** | `Bhagavad-gita As It Is with pics!`, `Valmiki Ramayana...` | English / Sanskrit / Hindi | ~1,150 | Contains 46 Devanagari chunks in Gita and 2 in Ramayana. |
| **Academic Records & Applications** | `Atharv_Patil_RESUME_SDE.pdf`, `Atharv_Patil_240740.pdf`, `Coordinator Application 2026–27` | English / Hindi (bilingual header) | ~100 | Contains realistic tabular/resume evidence. |
| **Tabular & Statistical Data** | `Y24_CPI.csv` | English / Numerical | 31 | High-precision lookup utility. |
| **Regional Literature / Memoir** | `manuscript.pdf` | **Marathi (Devanagari)** | **10** | **Sole source of Marathi evidence in entire corpus.** |
| **Sciences (Physics Problems)** | `PHYSICS_JEE_ADVANCED.pdf` | English / Hindi (OCR) | 78 | Contains 39 Hindi OCR chunks. |
| **Hindi Literature** | `Act 2. panch-parmeshwar-by-munshi-premchand.pdf` | **English Translation** | 11 | English translation only; zero Devanagari chunks. |

---

## 9. Resume Diagnostic Cases

The resume queries (`MBSEL-01`, `MBSEL-02`, `MBSEL-03`) are explicitly preserved in the proposed 270-case inventory:
- **`MBSEL-01` (`en->en`):** Preserved as `P85-EVAL-ENEN-005` (Found at Rank 5 in smoke run).
- **`MBSEL-02` (`hi->en`):** Preserved as `P85-EVAL-HIEN-005` (Missed top 10 in smoke run).
- **`MBSEL-03` (`mr->en`):** Preserved as `P85-EVAL-MREN-005` (Missed top 10 in smoke run).

**Governed Policy:**  
These cases represent legitimate cross-lingual diagnostic tests against competing candidate documents (`Coordinator Application 2026–27`, `ME361_L1`). They must **not** be removed, modified, or given special algorithmic overrides.

---

## 10. Concrete Blockers Preventing Pack Construction

The construction and execution of a governed 270-case evaluation pack is halted by **6 concrete blockers**:

1. **Blocker 1 (Corpus Asymmetry / Marathi Target Starvation):**  
   The frozen corpus contains only **10 chunks** of Marathi evidence (`manuscript.pdf`). Populating 30 cases each for `en->mr`, `hi->mr`, and `mr->mr` ($90$ total queries) requires an average saturation of 9 queries per 500-character chunk, violating evaluation independence and risking artificial memorization.
2. **Blocker 2 (Corpus Asymmetry / Hindi Target Starvation):**  
   The corpus contains only 2 chunks for Ramayana (legacy font unmapped), Panch Parmeshwar is an English translation, and total Devanagari Hindi chunks across Physics, Gita, and Grade Cards sum to only ~90. Allocating 90 queries across `en->hi`, `hi->hi`, and `mr->hi` creates severe topic skew towards physics problem sets and Gita verses.
3. **Blocker 3 (Unpopulated QREL Files):**  
   Zero files matching `multilingual_qrels.schema.json` exist in the repository. All 270 evidence-level judgments must be authored, validated, and serialized.
4. **Blocker 4 (Absence of Dual-Reviewer Human Adjudication):**  
   No certified bilingual human evaluators have independently reviewed and adjudicated query-evidence pairs.
5. **Blocker 5 (Unapproved Threshold Contract):**  
   `multilingual_threshold_contract.proposed.json` remains `"not_yet_defensible"` with all numeric criteria set to `null`.
6. **Blocker 6 (Unapproved Evaluation Manifest):**  
   `multilingual_evaluation_manifest.proposed.json` and its `sample_size_policy` are designated `"proposal_requires_human_governance_approval"`.

---

## 11. Protected State Verification

Physical disk SHA-256 digests were verified before and after this audit:

```text
manuscript.pdf SHA:  31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085  [MATCH: True]
Ramayana PDF SHA:    759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75  [MATCH: True]
V2 Database SHA:     3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c  [MATCH: True]
Active Alias Digest: b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0  [MATCH: True]
```

---

## 12. Readiness Determination

**EVALUATION PACK NOT READY**

### Determination Summary:
While the storage model and QREL schemas (`multilingual_qrels.schema.json`) are technically capable of representing evidence-level relevance judgments, the formal 270-case evaluation pack cannot be declared ready or executed because:
1. Target evidence in Marathi (10 chunks) and Hindi (~90 chunks) is severely constrained within the frozen 44-document corpus.
2. The 270 queries and their evidence-level QRELs have not been populated or adjudicated by dual human reviewers.
3. The evaluation manifest, sample size policy, and threshold contracts remain unapproved governance proposals.

The repository lifecycle remains strictly bounded:
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
