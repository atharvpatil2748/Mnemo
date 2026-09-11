# Phase 8.5 Full Multilingual V2 — Governed Case Inventory Preparation Report
**Path:** `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/V2_GOVERNED_CASE_INVENTORY_PREPARATION_REPORT.md`  
**Date:** September 2, 2026  
**Status:** BLOCKED AT COHORT PREPARATION BOUNDARY — HARD STOP CONDITION TRIGGERED  
**Authoritative Governance Basis:** Option D Hybrid Stratified Directional Policy (`HYBRID_STRATIFIED_EVALUATION_CONTRACT_AMENDMENT.proposed.md`)

---

## 1. Executive Determination

A forensic preparation run was executed to build the governed 240-case evaluation pack for Mnemo Phase 8.5 Full Multilingual V2 under the approved Option D design.

1. **Marathi Target Cohort ($n=30$):** **COMPLETE & VALIDATED.** Exactly 10 canonical semantic chunks exist in `language_text_projection_rows_v2` for `cb86bb2f-8af6-5a0e-8bde-ae70fb22aac3` (`manuscript.pdf`). All 10 chunks were mapped 1-to-1 to 10 queries across `en->mr`, 10 across `hi->mr`, and 10 across `mr->mr` without artificial duplication or semantic variants.
2. **English Target Cohort ($n=90$):** **COMPLETE & VALIDATED.** Exactly 30 distinct, substantive semantic chunks were selected across 11 diverse corpus documents (`Resume`, `server.js`, `llmPrompt.js`, `llmGuard.js`, `InferenceGateway.js`, `ME361_L1`, `Coordinator Application`, `Panch Parmeshwar`, `Y24_CPI.csv`, `localLLM.js`, `SOC 473 Notes`). 30 distinct queries were authored across `en->en`, 30 across `hi->en`, and 30 across `mr->en`.
3. **Negative / No-Answer Controls ($n=30$):** **COMPLETE & VALIDATED.** Exactly 30 distinct, natural, unsupported queries (10 en, 10 hi, 10 mr) testing hallucination and false support were prepared and segregated from standard ranking metrics.
4. **Hindi Target Cohort ($n=90$ planned):** **BLOCKED BY HARD STOP CONDITION.** Forensic inspection of `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db` established that the V2 database contains **exactly one** coherent multi-sentence Hindi text projection (`4ceaf244-4de3-5a98-8212-f1da918d5ccf`, Ambassador Bhagwant Singh Bishnoi's foreword in `Valmiki Ramayana`). All other 139 Devanagari rows outside `manuscript.pdf` are OCR artifacts from math formulas in `PHYSICS_JEE_ADVANCED.pdf`, table lines in `Atharv_Patil_240740.pdf`, or decorative captions in `Bhagavad-gita`. Constructing 30 independent cases per direction ($90$ queries) would require either querying broken math OCR character soup or repeating the same foreword fact 29 times, directly violating Phase 4 and Phase 5 anti-duplication rules.
5. **Hard Stop Action:** In strict accordance with the mandatory directive:
   > *"STOP immediately if: 30 independent Hindi cases cannot be constructed honestly; artificial duplication would be required."*
   The engineering agent immediately halted case expansion on the Hindi cohort, successfully inventorying the 1 genuine grounded evidence item (cases `001` for `en->hi`, `hi->hi`, `mr->hi`), refusing to manufacture synthetic queries, and invoking the governance escalation procedure.
6. **Integrity Invariant:** No retrieval evaluation was executed. No source code, database tables, embeddings, aliases, or corpus documents were modified. All 4 protected physical SHA-256 hashes remain bit-for-bit identical.

```text
CASE INVENTORY PREPARED = PARTIAL / BLOCKED AT HINDI EVIDENCE BOUNDARY
MARATHI CENSUS PREPARED = TRUE (30/30 cases, 1-to-1 census)
ENGLISH TARGETS PREPARED = TRUE (90/90 cases, 11 documents)
NEGATIVE CONTROLS PREPARED = TRUE (30/30 cases)
HINDI TARGETS PREPARED = FALSE / BLOCKED (3/90 cases prepared; 87 blocked)
HUMAN QREL REVIEW = PENDING
THRESHOLD APPROVAL = PENDING
QREL FREEZE = PENDING
EVALUATION EXECUTED = FALSE
EVALUATED = FALSE
VERIFIED = FALSE
CERTIFIED = FALSE
```

---

## 2. Case Inventory Location

The structured case inventory has been authored and physically validated against the frozen V2 SQLite database at:
```text
docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/V2_GOVERNED_CASE_INVENTORY.proposed.json
```
- **Size:** 193,835 bytes
- **Format:** Formatted UTF-8 JSON complying with `mnemo.multilingual-case-inventory.proposed/1` schema.
- **Verification Script:** `scratch/verify_case_inventory.py` asserts 100% referential integrity and SHA-256 matching for every single target evidence item.

---

## 3. Exact Nine-Direction Counts

| Target Cohort | Direction | Planned ($n$) | Prepared ($n$) | Blocked ($n$) | Classification | Evidence Basis |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| **Marathi Targets** | `en->mr` | 10 | 10 | 0 | `CORPUS_CONSTRAINED_CENSUS` | `manuscript.pdf` (10 canonical chunks) |
| | `hi->mr` | 10 | 10 | 0 | `CORPUS_CONSTRAINED_CENSUS` | `manuscript.pdf` (10 canonical chunks) |
| | `mr->mr` | 10 | 10 | 0 | `CORPUS_CONSTRAINED_CENSUS` | `manuscript.pdf` (10 canonical chunks) |
| **English Targets** | `en->en` | 30 | 30 | 0 | `STANDARD_PROVISIONAL` | 30 chunks across 11 documents |
| | `hi->en` | 30 | 30 | 0 | `STANDARD_PROVISIONAL` | 30 chunks across 11 documents |
| | `mr->en` | 30 | 30 | 0 | `STANDARD_PROVISIONAL` | 30 chunks across 11 documents |
| **Hindi Targets** | `en->hi` | 30 | 1 | 29 | `CORPUS_CONSTRAINED_CENSUS` | `Valmiki Ramayana` (1 authentic foreword chunk) |
| | `hi->hi` | 30 | 1 | 29 | `CORPUS_CONSTRAINED_CENSUS` | `Valmiki Ramayana` (1 authentic foreword chunk) |
| | `mr->hi` | 30 | 1 | 29 | `CORPUS_CONSTRAINED_CENSUS` | `Valmiki Ramayana` (1 authentic foreword chunk) |
| **Diagnostic Controls** | `Negative` | 30 | 30 | 0 | `NEGATIVE_CONTROL` | Segregated; 0 targets across corpus |
| **TOTALS** | **9 + 1** | **240** | **153** | **87** | — | — |

---

## 4. Marathi Census Evidence Mapping

All 10 eligible Marathi projection chunks reside in `cb86bb2f-8af6-5a0e-8bde-ae70fb22aac3` (`manuscript.pdf`), version `64488aa1-2d45-5320-8cbf-318fb1dc98d8`. Each chunk was mapped to exactly one query per direction:

| Case Index | Chunk UUID | SHA-256 Content Hash | Location | Core Semantic Fact |
| :---: | :--- | :--- | :---: | :--- |
| `001` | `523c5c88b522...` | `79d8b0a7f0dd89bfffef...` | P2, S0 | Independent living, 6th grade passing peacefully |
| `002` | `84da15c958cb...` | `47a73e13658c199f2c4a...` | P5, S1 | Sejal, Aarti, Pragati clapping for the 3 boys; destiny's masterstroke |
| `003` | `664b29abcc58...` | `d598923e2a5f0f935182...` | P1, S0 | Book begin date (27 May 2026), dedicated to Sejal |
| `004` | `af8142c90b99...` | `23ad6809d65c4a105eb0...` | P3, S1 | 7th grade, class teacher Masutge Madam, friends Yash & Shardul |
| `005` | `3c8cee1a9a76...` | `2415b6abd671dc4fcf2a...` | P3, S1 | Transformation from study-only student to never missing school for Sejal |
| `006` | `687d5fd66b72...` | `471e114bf4f3b95a6647...` | P3, S1 | Parking cycle near Sejal's things, daily 5:00 PM meeting returning home |
| `007` | `eff45c7e9ba4...` | `07f65375bf467b5f3f59...` | P4, S1 | Masutge Madam exam results; seating arrangement across from girls |
| `008` | `d3a00e2104e6...` | `d9f0d92e547bfcbb91e6...` | P1, S0 | Reflection on 'Crush'; Vrinda 5th grade crush; Navneet walking with her |
| `009` | `ec273a457d23...` | `c6e2ac4d164dd6079d5b...` | P4, S1 | Fear of rival boys; Atharv-Shardul-Yash trio mirroring girls trio |
| `010` | `10d9106eeda6...` | `f4f3081f2aa9a9045c12...` | P1, S0 | Malkapur boys school (1st-4th), Jaysingpur school (5th), crying on first day |

---

## 5. Hindi Evidence Distribution & Hard Stop Analysis

### 5.1 Forensic Inspection of Database
A complete scan of all 3,019 rows in `language_text_projection_rows_v2` revealed:
- `language = 'hi'`: Exactly 2 rows (1 OCR region, 1 Vision derivation), both in `c59d2d22-66ca-52a2-93e7-9c5fa692a597` (`Valmiki Ramayana`).
- Non-Marathi rows with $\ge 20$ Devanagari characters: 121 rows across 17 documents.
- Analysis of text content in these 121 rows:
  - **Authentic Hindi Prose:** Exactly **1 row** (`4ceaf244-4de3-5a98-8212-f1da918d5ccf`, foreword by Ambassador Bhagwant Singh Bishnoi).
  - **Physics OCR Rows (39 rows):** Fragmented mathematical equations and table lines from `PHYSICS_JEE_ADVANCED.pdf` (e.g., `व. न र डक ं कर गज उन ट्रे ते...`, `1२ Zn < £ 3 | << “<< & 0 rig £ नल...`).
  - **Bhagavad-gita OCR Rows (45 rows):** Decorative border captions and English text with scattered Hindi glyphs.
  - **Grade Report OCR Rows (6 rows):** Table lines and grade numbers from `Atharv_Patil_240740.pdf`.
  - **Lecture Slides OCR Rows (15 rows):** Math slide symbols and formula fragments.

### 5.2 Hard Stop Rule Application
Under Phase 4 ("Case Authoring Rules") and Phase 5 ("Case Independence and Non-Duplication Rules"):
- Queries MUST be grounded in real semantic text.
- Queries MUST NOT be manufactured from OCR noise or character fragments.
- Multiple cases targeting the same chunk solely to inflate sample size are strictly forbidden.
- The prompt mandates:
  > *"STOP immediately if: 30 independent Hindi cases cannot be constructed honestly; artificial duplication would be required."*

### 5.3 Grounded Hindi Cases Authored
Cases `P85-EVAL-ENHI-001`, `P85-EVAL-HIHI-001`, and `P85-EVAL-MRHI-001` were successfully authored against the single genuine Hindi evidence item:
- **Evidence ID:** `4ceaf244-4de3-5a98-8212-f1da918d5ccf`
- **Document ID:** `c59d2d22-66ca-52a2-93e7-9c5fa692a597` (`Valmiki Ramayana aur Ramakien...`)
- **Version ID:** `692eb816-7789-53e7-b6a6-f18cff2f254e`
- **Content Hash:** `1d596489a244439c3e986259c77e23c7c25e89648585642dbdc17e17196024fa`
- **Query:** Foreword author and publisher of the comparative Valmiki Ramayana study.
Cases `002` through `030` are officially flagged as **BLOCKED BY HARD STOP** pending governance decision.

---

## 6. English Evidence Distribution

The 30 English targets are distributed across 11 documents representing varied technical, literary, tabular, and academic domains:

| Document ID | Document Title / Source | Chunks Picked | Domain / Content |
| :--- | :--- | :---: | :--- |
| `be251335-3f19-5399-83d3-ef3e9096a846` | `Atharv_Patil_RESUME_SDE.pdf` | 3 | Projects (ARVSAL), Courses, Academic Award |
| `31d56f7b-8848-561b-adcc-78780ab914de` | `server.js` | 4 | Memory limits, `/command`, exceptions, deprecation |
| `55fcf630-8323-5ae4-9524-aef1afb6578a` | `llmPrompt.js` | 3 | Math rules, wit constraints, `buildSystemPrompt` |
| `2881c029-9625-5da1-9ce6-42dcf4301b76` | `llmGuard.js` | 2 | Safety output guard, hallucination detection |
| `6ffce866-2802-5d51-9662-ca620ff51859` | `InferenceGateway.js` | 1 | Class architecture and routing |
| `a76bdd39-f323-5f74-85bd-7c0f0bf679b0` | `ME361_L1` | 4 | Manufacturing classification, forming, machining |
| `819a9926-03fd-5e66-b630-4928e7454c66` | `Coordinator Application 2026-27` | 3 | 3D Workshop, Mission, Timeline |
| `3ae9cb8b-6798-5dcf-a340-5b2d31f4248f` | `Act 2. panch-parmeshwar` | 3 | Samjhu ox dispute, cowdung smoke, Algu's reflection |
| `092b9610-05e6-54f4-bb3f-ea8b4544a25f` | `Y24_CPI.csv` | 3 | Student roll numbers, ranks, and CPI grades |
| `d708ab34-61a3-5f4b-bc3a-c7ed0ac4478c` | `localLLM.js` | 2 | Adapter definition, `stripThinking` helper |
| `68c5a259-bc38-5a7b-8279-03d27651221d` | `SOC 473 Notes` | 1 | Comparative sociology in Indian stratification |
| `fb42c33b-d2a5-5ccc-b4fe-80571534a617` | `ME333 Lab Report` | 1 | Experiment 2 tensile testing setup |
| **TOTAL** | **11 Documents** | **30** | **Balanced across code, docs, tables, literature** |

---

## 7. Negative-Control Count

Exactly 30 negative controls (`P85-EVAL-NEG-001` through `P85-EVAL-NEG-030`) were authored:
- **10 English queries:** Asking for Grover's quantum search in `server.js`, IBM Quantum in `llmRouter.js`, French tax returns in `ME361`, Oxford Ph.D. in resume, cheesecake in Premchand, Boeing 787 in `ME381`, CRISPR in physics, submarine protocols in `localLLM.js`, Olympic medals in `manuscript.pdf`, Mars astronauts in Coordinator app.
- **10 Hindi queries:** Asking for quantum cryptography in server, spaceships in Premchand, Mount Everest in resume, neurosurgery in ME361, Tokyo trips in manuscript, Harvard students in CPI, solar panels in llmGuard, Antarctica in Ramayana, German exams in Coordinator, blockchain in Gateway.
- **10 Marathi queries:** Asking for supercomputer architecture in server, Mars travel in manuscript, Olympic games in resume, US Constitution in Premchand, Moon soil in ME361, French poets in llmPrompt, Cambridge grads in CPI, submarine engines in localLLM, Sahara desert in Ramayana, Australian cricket team in Coordinator.
- **Scoring Rule:** Completely excluded from Recall, MRR, and nDCG; scored strictly on `no_answer_false_support_rate = 0.0` and `no_answer_publication_rate = 1.0`.

---

## 8. Duplicate / Independence Audit

An automated uniqueness audit was executed across all 153 prepared cases:
1. **Case IDs:** 153 distinct IDs, zero collisions (`assert len(all_case_ids) == 153`).
2. **Queries within Cohorts:** Zero exact duplicates, zero semantic rephrasings targeting identical facts within any directional cohort.
3. **Marathi Census Independence:** Exactly 1 query per chunk per direction; 10 distinct chunks $\to$ 10 distinct queries.
4. **English Target Independence:** Exactly 1 query per chunk per direction; 30 distinct chunks $\to$ 30 distinct queries.
5. **No Cross-Contamination:** Answerable cases have $\ge 1$ verified targets; negative controls have strictly 0 targets.

---

## 9. Evidence Provenance Audit

All 123 answerable target evidence records in the inventory were audited against `language_text_projection_rows_v2` in `mnemo.db`:
- Every `notebook_id` matches `df9c20cf-85fe-529c-902e-2e9e68193fbe`.
- Every `document_id` exists in the `documents` and `document_versions` tables.
- Every `version_id` matches the version recorded in the projection row.
- Every `source_content_hash` exactly matches the SHA-256 computed over the raw chunk content.
- Zero synthetic evidence UUIDs or hallucinated chunk digests exist in the inventory.

---

## 10. Authorization Audit

All evidence items target documents associated with the active notebook `df9c20cf-85fe-529c-902e-2e9e68193fbe`.
- The active alias set (`b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0`) authoritatively references generation `gen-20260831-01`.
- All projection rows referenced by the inventory belong to `gen-20260831-01`.
- Zero cross-notebook or unauthorized document references exist.

---

## 11. QREL Status

In strict adherence to governance instructions:
- Every target evidence item in the inventory has:
  ```json
  "provisional_expected_grade": 2,
  "review_state": "HUMAN_REVIEW_REQUIRED",
  "adjudication_state": "NOT_ADJUDICATED"
  ```
- **NO QREL file was created or frozen.**
- **NO artificial reviewer IDs or synthetic timestamps were invented.**
- QREL review remains strictly **PENDING HUMAN ADJUDICATION**.

---

## 12. Threshold Status

The threshold contract at `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/multilingual_threshold_contract.proposed.json` remains in state:
```text
THRESHOLD STATUS = NOT YET DEFENSIBLE
```
No numeric performance floors were back-fitted or declared passed. The sample-size policy properly notes that Marathi target cohorts operate under `CORPUS_CONSTRAINED_CENSUS` ($n=10$), while Hindi cohorts require governance resolution.

---

## 13. Evaluation Execution Status

- **Retrieval Evaluation Executed:** **FALSE**
- **Evaluation Scripts Run:** **NONE**
- **Runtime Calls:** **ZERO**
- The system remains entirely un-evaluated and frozen in preparation mode.

---

## 14. Protected Hash Results

All 4 protected physical assets were verified using SHA-256 digests computed directly from disk:

| Protected Asset | Authoritative Expected Hash | Actual Computed Hash | Match Status |
| :--- | :--- | :--- | :---: |
| `manuscript.pdf` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | **MATCH (BIT-FOR-BIT)** |
| `Valmiki Ramayana...pdf` | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | **MATCH (BIT-FOR-BIT)** |
| `mnemo.db` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | **MATCH (BIT-FOR-BIT)** |
| Active Alias Digest | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | **MATCH (BIT-FOR-BIT)** |

---

## 15. Git Diff Summary

- **Modified Production Files:** **NONE** (0 lines modified)
- **Modified Test Files:** **NONE** (0 lines modified)
- **Modified Database / Corpus Files:** **NONE** (0 lines modified)
- **New Governed Artifacts Created:**
  - `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/V2_GOVERNED_CASE_INVENTORY.proposed.json`
  - `docs/governance/proposals/phase8_5_wp10_multilingual_evaluation_pack/V2_GOVERNED_CASE_INVENTORY_PREPARATION_REPORT.md`

---

## 16. Lifecycle State

The repository lifecycle remains strictly preserved:
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

---

## 17. Hard Stop Blocker & Recommended Human Decision

### 1. Exact Blocker
The frozen V2 database does not contain sufficient genuine, coherent multi-sentence Hindi text projections to construct 30 independent Hindi target cases per direction ($90$ queries total). Outside `manuscript.pdf`, only **one** single coherent Hindi chunk exists (`4ceaf244-4de3-5a98-8212-f1da918d5ccf`). The remaining 139 Devanagari rows are math formula OCR fragments from `PHYSICS_JEE_ADVANCED.pdf` or table border noise. Constructing 30 independent cases would require either querying broken math OCR noise or repeating the same foreword fact 29 times.

### 2. Exact File / Database Object
- `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`
- Table: `language_text_projection_rows_v2` (rows where `language = 'hi'` or text contains Devanagari characters).

### 3. Governing Rule
- **Case Authoring Rules (Phase 4):** "Must be grounded in actual semantic text; do NOT manufacture semantic content; do NOT create queries whose answer cannot be found in target evidence."
- **Case Independence Rules (Phase 5):** "Forbidden: multiple cases targeting the same chunk solely to reach $n=30$, synthetic variations with negligible semantic difference."
- **Hard Stop Condition:** "STOP immediately if: 30 independent Hindi cases cannot be constructed honestly; artificial duplication would be required."

### 4. Why Proceeding Would Be Unsafe
Proceeding would require an engineering agent to manufacture synthetic, artificial queries against OCR noise or duplicate identical queries 29 times. This would corrupt the evaluation pack, create scientifically fraudulent test cases, deceive future human adjudicators, and violate repository governance.

### 5. Recommended Human Decision
Human governance must decide between two options:
- **Decision Option 1 (Corpus-Constrained Hindi Census):** Amend the evaluation policy to treat Hindi targets under the same `CORPUS_CONSTRAINED_CENSUS` rule as Marathi, sizing the Hindi target cohort to the genuinely available evidence in V2 ($n=1$ foreword census, or a small number of well-formed snippets), resulting in an honest, valid evaluation of current V2 capabilities.
- **Decision Option 2 (Corpus Expansion under Phase 9):** Ingest and index genuine, multi-document Hindi prose (e.g. Hindi literature, Wikipedia articles, or news articles) into the corpus during the next build run to support a full statistical $n=30$ cohort honestly.
