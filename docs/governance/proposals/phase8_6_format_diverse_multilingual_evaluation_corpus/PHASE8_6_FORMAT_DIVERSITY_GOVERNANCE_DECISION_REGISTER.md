# PHASE 8.6 — FORMAT DIVERSITY GOVERNANCE DECISION REGISTER
**Classification:** GOVERNANCE DECISION REGISTER — RATIFIED & ACTIVE DECISIONS  
**Created:** 2026-09-03  
**Last Updated:** 2026-09-03 (Post-Human Ratification Gate)  
**Status:** ACTIVE GOVERNANCE REGISTER  
**Phase:** Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus  

---

> [!IMPORTANT]
> Decisions marked **RATIFIED / APPROVED** have received explicit human governance approval.
> Decisions marked **EXECUTED** have completed their operational directives.
> Decisions marked **PROPOSED** remain under governance evaluation.

---

## PART A — FORMAT DIVERSITY MANDATE & BASELINE DECISIONS

### DEC-P8.6-FD-01: Format Diversity Governing Principle

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-01** |
| Date Proposed | 2026-09-03 |
| Date Ratified | 2026-09-03 |
| Status | **RATIFIED / APPROVED BY HUMAN GOVERNANCE** |
| Approver | User Human Governance Ratification Gate |

**Decision Text:**
The governing principle of Phase 8.6 is officially established as follows:
> *"Phase 8.6 must contain authentic documents spanning multiple natively supported formats, with multilingual coverage prioritized. A format does NOT need to exist for every language. No synthetic format conversion is permitted solely to satisfy format coverage."*

Authenticity, semantic density, and retrieval-evaluation value strictly supersede superficial format counts or rigid matrix-filling.

---

### DEC-P8.6-FD-02: Deletion of Obsolete TXT-Only Datasets (`Politics`, `Science`)

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-02** |
| Date Proposed | 2026-09-03 |
| Date Executed | 2026-09-03 |
| Status | **EXECUTED / COMPLETE** |
| Directive | Phase 8.6 Part A Directive |

**Decision Text:**
The previously acquired plain-text archives:
- `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/Politics.zip` (59,972,294 bytes)
- `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/Science & Technology.zip` (15,073,261 bytes)

have been **permanently deleted from disk**. Neither archive was extracted or ingested into any database.

---

### DEC-P8.6-FD-03: Termination and Deletion of Partial `MNATD.zip`

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-03** |
| Date Proposed | 2026-09-03 |
| Date Executed | 2026-09-03 |
| Status | **EXECUTED / COMPLETE** |
| Directive | Phase 8.6 Part A Directive |

**Decision Text:**
The partially downloaded archive `MNATD.zip` (759,169,024 bytes, 70.3% incomplete stream) was terminated via task management and **permanently deleted from disk**. It shall not be resumed.

---

### DEC-P8.6-FD-04: Minimum Format-Diversity Baseline

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-04** |
| Date Proposed | 2026-09-03 |
| Date Ratified | 2026-09-03 |
| Status | **RATIFIED / APPROVED WITH CLARIFICATION** |
| Approver | User Human Governance Ratification Gate |

**Decision Text (Approved Clarification):**
The four-format baseline is a **GOVERNANCE TARGET for overall parser coverage, not a mandatory per-language acquisition matrix**:
1. The overall Mnemo evaluation suite should exercise multiple distinct native parser families.
2. Phase 8.6 must add meaningful multilingual parser coverage.
3. At least Hindi and Marathi must have substantial authentic representation.
4. At least one meaningful non-PDF parser path should be represented in the Phase 8.6 expansion if an authentic, high-quality multilingual source can be found.
5. DOCX/PPTX/XLSX must NOT be artificially forced when suitable authentic multilingual sources do not exist.
6. Synthetic conversion of documents solely to satisfy format coverage is prohibited.
7. Numeric-heavy spreadsheets must not be admitted merely to claim XLSX coverage.

---

### DEC-P8.6-FD-05: Supplementary Plain-Text Policy

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-05** |
| Date Proposed | 2026-09-03 |
| Status | **PROPOSED — REQUIRES FUTURE REVIEW** |

**Decision Text:**
Plain text (`.txt`) documents or archives may only be admitted as a supplementary expansion layer *after* the multi-format baseline defined in DEC-P8.6-FD-04 is established and certified. Any admitted plain text must satisfy both the constituent-level and parent-dataset 20% concentration ceilings.

---

## PART B — COMPLIANCE AND ACQUISITION GATING DECISIONS

### DEC-P8.6-FD-06: NCERT Copyright Determination for Evaluation-Only Use

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-06** |
| Date Proposed | 2026-09-03 |
| Status | **PROPOSED — REQUIRES HUMAN RATIFICATION** |
| Candidate Impacted | `CAND-FD-HI-PDF-02` (NCERT Kshitij Bhag-2) |

**Decision Text:**
NCERT publications carry an explicit copyright restriction prohibiting "electronic redistribution" and "inclusion in digital packages". To preserve open-source reproducibility, recommendation is to avoid NCERT textbooks in automated test suites unless explicit fair-use determination is recorded.

---

### DEC-P8.6-FD-07: Balbharati License Determination for Evaluation-Only Use

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-07** |
| Date Proposed | 2026-09-03 |
| Status | **PROPOSED — REQUIRES HUMAN RATIFICATION** |
| Candidate Impacted | `CAND-FD-MR-PDF-02` (Balbharati Kumarbharati Class 10) |

**Decision Text:**
Balbharati textbooks are free downloads for educational use but restrict commercial distribution. Evaluation admission requires explicit attribution and internal-benchmarking-only status.

---

### DEC-P8.6-FD-08: Pre-Acquisition Direct Binary URL Verification Gate

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-08** |
| Date Proposed | 2026-09-03 |
| Date Ratified | 2026-09-03 |
| Status | **RATIFIED / APPROVED BY HUMAN GOVERNANCE** |
| Approver | User Human Governance Ratification Gate |

**Decision Text:**
For every downloaded artifact:
- verify exact source identity;
- verify expected file type;
- verify byte size where available;
- compute SHA-256;
- record provenance;
- record licensing/compliance evidence;
- preserve original bytes;
- do not silently substitute another artifact.

If the artifact differs from the approved source, STOP.

---

### DEC-P8.6-FD-09: Authorization of First Batch Acquisition — Marathi PDF (`CAND-FD-MR-PDF-01`)

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-09** |
| Date Proposed | 2026-09-03 |
| Date Ratified | 2026-09-03 |
| Status | **RATIFIED / EXECUTED (ADMISSION HALTED ON FORENSIC ANOMALY)** |
| Candidate | `CAND-FD-MR-PDF-01` (Economic Survey of Maharashtra 2023-24) |

**Decision Text & Execution Finding:**
Authorized acquisition of `CAND-FD-MR-PDF-01`. The file was acquired (`dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf`, 12,764,759 bytes, SHA-256: `a55e99f584ea0c1a5b9dece668c57e423c223a54dbcc0836ed683a6cb59345db`).
Forensic inspection revealed the document is the **English Edition** (`PREFACE_23_24_E_30524.doc`, 0.0% Devanagari).
Admission to evaluation corpus was **HALTED**. The raw artifact is preserved as source evidence.

---

### DEC-P8.6-FD-10: Authorization of First Batch Acquisition — Hindi PDF (`CAND-FD-HI-PDF-01`)

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-10** |
| Date Proposed | 2026-09-03 |
| Date Ratified | 2026-09-03 |
| Status | **RATIFIED / EXECUTED (DOWNLOAD HALTED PER DIRECTIVE)** |
| Candidate | `CAND-FD-HI-PDF-01` (MoE Annual Report 2023-24 — Hindi) |

**Decision Text & Execution Finding:**
Authorized acquisition of `CAND-FD-HI-PDF-01` with explicit directive: *"If and only if the exact approved artifact cannot be reproducibly retrieved, STOP and report the failure. Do NOT automatically substitute CAND-FD-HI-PDF-03 unless separately approved."*
Preflight inspection confirmed the document exists on the portal, but binary retrieval is mediated by a client-side token-gated microservice where direct scripted HTTP queries time out. Download was **HALTED** pending human review.

---

### DEC-P8.6-FD-11: Authorization of Second-Round Targeted Discovery for Non-PDF Formats

| Field | Value |
| :--- | :--- |
| Decision ID | **DEC-P8.6-FD-11** |
| Date Proposed | 2026-09-03 |
| Date Ratified | 2026-09-03 |
| Status | **RATIFIED / EXECUTED (DISCOVERY COMPLETE — READ-ONLY)** |

**Decision Text & Execution Finding:**
Authorized read-only discovery for authentic non-PDF multilingual sources. Completed without downloading any file. Documented in `PHASE8_6_NON_PDF_MULTILINGUAL_DISCOVERY_REPORT.md`.

---

## 3. DECISION SUMMARY TABLE

| Decision ID | Title | Governed Status |
| :--- | :--- | :---: |
| **DEC-P8.6-FD-01** | Format Diversity Governing Principle | **RATIFIED / APPROVED** |
| **DEC-P8.6-FD-02** | Deletion of Obsolete TXT Datasets (`Politics`, `Science`) | **EXECUTED / COMPLETE** |
| **DEC-P8.6-FD-03** | Termination and Deletion of Partial `MNATD.zip` | **EXECUTED / COMPLETE** |
| **DEC-P8.6-FD-04** | Minimum Format-Diversity Baseline (Clarified) | **RATIFIED / APPROVED** |
| **DEC-P8.6-FD-05** | Supplementary Plain-Text Policy | **PROPOSED** |
| **DEC-P8.6-FD-06** | NCERT Copyright Determination for Evaluation | **PROPOSED** |
| **DEC-P8.6-FD-07** | Balbharati License Determination for Evaluation | **PROPOSED** |
| **DEC-P8.6-FD-08** | Pre-Acquisition Direct Binary URL Verification Gate | **RATIFIED / APPROVED** |
| **DEC-P8.6-FD-09** | First Batch Authorization: Marathi PDF (`CAND-FD-MR-PDF-01`) | **EXECUTED (ADMISSION HALTED)** |
| **DEC-P8.6-FD-10** | First Batch Authorization: Hindi PDF (`CAND-FD-HI-PDF-01`) | **EXECUTED (DOWNLOAD HALTED)** |
| **DEC-P8.6-FD-11** | Second-Round Targeted Discovery Authorization (Non-PDF) | **EXECUTED (DISCOVERY COMPLETE)** |

---

## 4. FINAL STATE ASSERTION

```
================================================================================
PHASE 8.6 FORMAT-DIVERSITY GOVERNANCE DECISION REGISTER: STATE SUMMARY
================================================================================
PHASE NAME:
Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus

RATIFIED GOVERNANCE DECISIONS:
DEC-P8.6-FD-01 = RATIFIED / APPROVED
DEC-P8.6-FD-04 = RATIFIED / APPROVED WITH CLARIFICATION
DEC-P8.6-FD-08 = RATIFIED / APPROVED
DEC-P8.6-FD-09 = RATIFIED / EXECUTED (FORENSIC ANOMALY HALTED ADMISSION)
DEC-P8.6-FD-10 = RATIFIED / EXECUTED (ENDPOINT TIMEOUT HALTED DOWNLOAD)
DEC-P8.6-FD-11 = RATIFIED / EXECUTED (READ-ONLY DISCOVERY COMPLETE)

ACQUISITION STATE:
CAND-FD-MR-PDF-01 = ACQUIRED (12,764,759 bytes, SHA-256: a55e99f584ea0c...)
                    ADMISSION TO EVALUATION CORPUS = FALSE (0.0% Devanagari)
CAND-FD-HI-PDF-01 = NOT DOWNLOADED (TOKEN-GATED ENDPOINT / TIMEOUT)

OTHER DOWNLOADS            = 0
NEW DATASET EXTRACTION     = FALSE
INGESTION                  = FALSE
INDEXING                   = FALSE
EMBEDDING                  = FALSE
EVALUATION                 = FALSE
QREL CREATION              = FALSE

PHASE 8.5 GOLDEN CORPUS    = UNCHANGED / FROZEN
V2 RUNTIME (mnemo.db)      = UNCHANGED / FROZEN
ACTIVE ALIAS SET           = UNCHANGED (b3479aeaf423630abc48436ea3d23c7d37a7fdee...)
================================================================================
```
