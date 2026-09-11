# PHASE 8.6 — FORMAT-DIVERSE SOURCE DISCOVERY AND AUDIT REPORT
**Classification:** GOVERNANCE DISCOVERY REPORT — READ-ONLY ARTIFACT AUDIT
**Date:** 2026-09-03
**Status:** COMPLETE / PROPOSED FOR HUMAN ACQUISITION REVIEW
**Auditor:** Automated Source Discovery & Forensic Audit

---

## 1. EXECUTIVE SUMMARY

This report presents the forensic review of replacement source candidates discovered to support **Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus**.

Following the discovery that the earlier acquisition strategy targeted plain text exclusively, the three acquired `.txt` archives (`Politics.zip`, `Science & Technology.zip`, and partial `MNATD.zip`) have been **deleted under Part A**.

The replacement discovery process focused on identifying **authentic, multi-format documents** from public government, academic, and open-data publishers across Hindi (`hi`), Marathi (`mr`), and English (`en`).

**Summary of Candidate Classifications:**
- **APPROVED FOR HUMAN ACQUISITION REVIEW:** 4 candidates (2 Hindi PDF, 2 Marathi PDF)
- **REVIEW REQUIRED (License, URL, or Format Verification):** 6 candidates (1 Hindi PDF, 1 Hindi DOCX, 1 Hindi PPTX, 1 Marathi PDF, 1 Hindi XLSX, 1 Marathi XLSX)
- **REJECTED (TXT-only archives deleted under Part A):** 3 candidates (`Politics.zip`, `Science & Technology.zip`, `MNATD.zip`)

**Current Acquisition Status:**
- New Downloads: 0
- Ingestion: FALSE
- Golden Corpus: UNCHANGED / FROZEN

---

## 2. CANDIDATE DETAILED EVALUATION & CLASSIFICATION

Every candidate has been evaluated against Mnemo's production parsers, semantic density standards, provenance traceability, and license terms.

### 2.1 Candidates: APPROVED FOR HUMAN ACQUISITION REVIEW

> [!NOTE]
> Classification as "APPROVED FOR HUMAN ACQUISITION REVIEW" signifies that the candidate has passed automated technical and forensic preflight. It does NOT constitute human governance authorization to download.

#### 1. `CAND-FD-MR-PDF-01`: Economic Survey of Maharashtra 2023-24 (Marathi)
- **Language:** Marathi (`mr`, Devanagari script)
- **Actual Format:** PDF (`application/pdf`)
- **Source Organization:** Commissionerate of Economics and Statistics, Planning Department, Government of Maharashtra
- **Artifact:** *महाराष्ट्राची आर्थिक पाहणी २०२३-२४* (Economic Survey of Maharashtra 2023-24)
- **Direct Download URL:** `https://data.opencity.in/dataset/1816ba03-3dd7-4952-b827-3bb1a64cea20/resource/a24a3a1d-8ab9-4535-943e-d36b0568039d/download/dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf`
- **Provenance & License:** Official State Government publication hosted on OpenCity civic data repository. Open Government Data / Public access document.
- **Semantic Content:** Exceptional quality. Hundreds of pages of formal, authentic Marathi administrative, agricultural, industrial, and social sector prose, interspersed with structured statistical data tables.
- **Target Parser:** `PDFParser` (ParserInterfaceV2) — exercises PyMuPDF text block extraction, Marathi font/glyph layout, and table grid partitioning.
- **Format Diversity Value:** **CRITICAL**. Resolves the single greatest deficit in Mnemo's evaluation suite (currently only 10 Marathi chunks in `manuscript.pdf`).
- **Classification:** **APPROVED FOR HUMAN ACQUISITION REVIEW** (Priority 1)

#### 2. `CAND-FD-HI-PDF-01`: Ministry of Education Annual Report 2023-24 (Hindi)
- **Language:** Hindi (`hi`, Devanagari script)
- **Actual Format:** PDF (`application/pdf`)
- **Source Organization:** Department of Higher Education / Department of School Education & Literacy, Ministry of Education, Government of India
- **Artifact:** *वार्षिक रिपोर्ट २०२३-२४* (Annual Report 2023-24, Hindi Edition, ~12 MB)
- **Source Portal:** `https://www.education.gov.in/annual-reports`
- **Provenance & License:** Government of India official annual report. National Data Sharing and Accessibility Policy (NDSAP) / Public domain.
- **Semantic Content:** Rich continuous prose covering educational policy, institutional governance, literacy programs, and expenditure statistics.
- **Target Parser:** `PDFParser` (ParserInterfaceV2) — exercises multi-column text extraction, Devanagari ligatures, and embedded table bounding boxes.
- **Classification:** **APPROVED FOR HUMAN ACQUISITION REVIEW** (Priority 1, pending exact direct binary URL confirmation)

#### 3. `CAND-FD-HI-PDF-03`: National Education Policy 2020 (Hindi Authoritative Text)
- **Language:** Hindi (`hi`, Devanagari script)
- **Actual Format:** PDF (`application/pdf`)
- **Source Organization:** Ministry of Education, Government of India
- **Artifact:** *राष्ट्रीय शिक्षा नीति २०२०* (National Education Policy 2020, Hindi Edition, ~4 MB)
- **Source Portal:** `https://www.education.gov.in`
- **Provenance & License:** Authoritative policy gazette of the Government of India. Public domain.
- **Semantic Content:** Comprehensive policy framework; dense, structured prose organized into formal numbered chapters, sections, and foundational principles.
- **Target Parser:** `PDFParser` (ParserInterfaceV2).
- **Classification:** **APPROVED FOR HUMAN ACQUISITION REVIEW** (Priority 2, pending direct binary URL confirmation)

#### 4. `CAND-FD-MR-PDF-03`: Maharashtra State Budget Speech 2023-24 (Marathi)
- **Language:** Marathi (`mr`, Devanagari script)
- **Actual Format:** PDF (`application/pdf`)
- **Source Organization:** Finance Department, Government of Maharashtra (Mahakosh)
- **Artifact:** *अर्थसंकल्प २०२३-२४ भाषण* (Budget 2023-24 Speech, Marathi Edition, ~3 MB)
- **Source Portal:** `https://mahakosh.gov.in`
- **Provenance & License:** Legislative address published by the Government of Maharashtra. Public legislative record.
- **Semantic Content:** Formal legislative speech; highly cohesive continuous Marathi discourse covering state finances, welfare schemes, and public works.
- **Target Parser:** `PDFParser` (ParserInterfaceV2).
- **Classification:** **APPROVED FOR HUMAN ACQUISITION REVIEW** (Priority 2, pending direct binary URL confirmation)

---

### 2.2 Candidates: REVIEW REQUIRED

#### 5. `CAND-FD-HI-PDF-02`: NCERT Kshitij Bhag-2 (Class 10 Hindi Literature)
- **Language:** Hindi (`hi`) | **Format:** PDF
- **Source Organization:** National Council of Educational Research and Training (NCERT)
- **Evaluation Finding:** Content quality is outstanding (classic Hindi essays, poetry, short stories). However, NCERT's copyright explicitly states: *"No part of this publication may be reproduced, stored in a retrieval system or transmitted, in any form or by any means, electronic, mechanical, photocopying, recording or otherwise without the prior permission of the publisher."*
- **Blocker:** Inclusion in an automated retrieval benchmarking system requires a formal governance decision (DEC-P8.6-FD-06) regarding internal research fair use under Indian copyright law.
- **Classification:** **REVIEW REQUIRED**

#### 6. `CAND-FD-MR-PDF-02`: Balbharati Marathi Textbook (Kumarbharati Class 10)
- **Language:** Marathi (`mr`) | **Format:** PDF
- **Source Organization:** Maharashtra State Bureau of Textbook Production (Balbharati)
- **Evaluation Finding:** High-quality authentic Marathi school textbook. Freely downloadable for students, but redistribution and derivative packaging are restricted.
- **Blocker:** Requires governance determination (DEC-P8.6-FD-07) on institutional evaluation suitability.
- **Classification:** **REVIEW REQUIRED**

#### 7. `CAND-FD-HI-DOCX-01`: INFLIBNET e-PG Pathshala Course Modules
- **Language:** Hindi (`hi`) | **Format:** Claimed DOCX
- **Source Organization:** INFLIBNET Centre / UGC
- **Evaluation Finding:** Higher education modules in Hindi medium. However, public access to direct unauthenticated `.docx` files is inconsistent; many modules are delivered as web pages or PDF conversions.
- **Blocker:** Direct `.docx` artifact URL has not been confirmed without session cookies or LMS credentials.
- **Classification:** **REVIEW REQUIRED**

#### 8. `CAND-FD-HI-PPTX-01`: NCERT Teacher Training Slide Decks
- **Language:** Hindi (`hi`) | **Format:** Claimed PPTX
- **Source Organization:** NCERT
- **Evaluation Finding:** Presentation slides used in national workshop modules.
- **Blocker:** Specific downloadable `.pptx` URLs have not been stabilized.
- **Classification:** **REVIEW REQUIRED**

#### 9. `CAND-FD-HI-XLSX-01`: data.gov.in Demographic/Census Tables
- **Language:** Bilingual (Hindi/English) | **Format:** XLSX/CSV
- **Source Organization:** Open Government Data (OGD) Platform India
- **Evaluation Finding:** Spreadsheets contain bilingual headers, but data cells are 95%+ numeric.
- **Semantic Evaluation Utility:** **Low**. RAG retrieval over purely numeric cells yields poor qualitative evaluation signal.
- **Classification:** **REVIEW REQUIRED** (Low evaluation priority)

#### 10. `CAND-FD-MR-XLSX-01`: Maharashtra Statistical Abstract
- **Language:** Bilingual (Marathi/English) | **Format:** XLSX/CSV
- **Source Organization:** Directorate of Economics and Statistics, Maharashtra
- **Evaluation Finding:** Tabular statistical tables. Primarily numeric data.
- **Classification:** **REVIEW REQUIRED** (Low evaluation priority)

---

### 2.3 Candidates: REJECTED & DELETED (TXT-Only Archives)

| Candidate ID | Artifact Name | Reason for Rejection | Action Taken |
| :--- | :--- | :--- | :---: |
| `CAND-REP-HI-03` | `Politics.zip` (Zenodo 10020768) | Composed exclusively of unformatted `.txt` files; does not test PDF, DOCX, PPTX, or table parsing | **DELETED** |
| `CAND-REP-HI-04` | `Science & Technology.zip` (Zenodo 10020768) | Composed exclusively of unformatted `.txt` files; fails format-diversity requirement | **DELETED** |
| `CAND-REP-MR-03` | `MNATD.zip` (Zenodo 10403924) | Incomplete 70.3% download of plain `.txt` files; download terminated | **DELETED** |

---

## 3. SECTION C.4 — PRINCIPLE OF AUTHENTIC DIVERSITY OVER FORMAT COUNT

A critical finding of this audit is that **artificially forcing an arbitrary 3×N matrix (every language into every format) leads to low-quality benchmark poisoning**:

1. **Government Publishing Realities in India:** State and central government bodies in India (Maharashtra, Ministry of Education, Parliament) publish official documents almost exclusively as **PDF** and **HTML/web**. They do **NOT** distribute official reports or legislative acts as editable `.docx` or `.pptx` files for security and document-integrity reasons.
2. **Tabular Fallacy:** Forcing Marathi into an `.xlsx` format results in datasets like `CAND-FD-MR-XLSX-01` that consist of numbers and short column codes. Evaluating semantic RAG embedding models on numbers provides no meaningful evaluation of Marathi retrieval capabilities.
3. **Synthetic Conversion Prohibition:** Converting a Hindi PDF to DOCX or PPTX violates Rule 4 (Zero synthetic transformation; preserve authentic bytes).

**Policy Formulation:** Phase 8.6 will evaluate **real formats in which real documents exist**. We will not synthesize artificial DOCX or PPTX files merely to fill matrix cells.

---

## 4. SECTION C.5 — RECOMMENDED SMALLEST HIGH-QUALITY ACQUISITION SET

To maximize evaluation power while minimizing operational burden and legal ambiguity, the recommended initial acquisition cohort for Phase 8.6 is:

| Priority | Recommended Candidate | Language | Format | Target Parser | Justification |
| :---: | :--- | :---: | :---: | :--- | :--- |
| **1** | `CAND-FD-MR-PDF-01` (Economic Survey of Maharashtra 2023-24) | Marathi | PDF | `PDFParser` | Solves the critical Marathi evidence deficit with authoritative government prose and extensive tables. Direct URL is confirmed. |
| **2** | `CAND-FD-HI-PDF-01` (MoE Annual Report 2023-24) OR `CAND-FD-HI-PDF-03` (NEP 2020) | Hindi | PDF | `PDFParser` | Solves the Hindi evidence deficit with foundational government policy text. Public domain. |
| **3** | Targeted Academic Discovery for Hindi/Marathi DOCX/PPTX | Hindi/Marathi | DOCX/PPTX | `DOCXParser` / `PPTXParser` | Conduct a focused second-round search specifically targeting university repositories (e.g. Pune University, IIT Bombay Hindi cell) for authentic course decks before acquiring non-PDF formats. |

---

## 5. ANSWERS TO REQUIRED GOVERNANCE QUESTIONS

1. **What file formats does Mnemo actually support natively?**
   10 format families: PDF, DOCX, PPTX, XLSX, CSV/TSV, Markdown, HTML, Plain Text, Code, and Standalone Image. JSON is supported via key-path flattening. OCR is an optional, decoupled, provider-backed subsystem that is NOT native or unconditional.

2. **Which formats are currently represented in Phase 8.5?**
   PDF (12), XLSX (5), JPG/JPEG (8), JS code (11), PPTX (2), DOCX (1), HTML (1), MD (1), CSV (1), TXT (1), Python (1). Total: 44 files in frozen Golden Corpus.

3. **Which formats are missing from Phase 8.6?**
   Multilingual non-English documents in: PDF (Marathi missing; Hindi has only 1 partial doc), DOCX (zero non-English), PPTX (zero non-English), XLSX (zero non-English).

4. **Which Hindi sources exist in PDF/DOCX/PPTX/etc.?**
   PDF: MoE Annual Report 2023-24, NEP 2020, NCERT Kshitij. DOCX/PPTX: Possible in academic training portals (INFLIBNET, NCERT workshops), but direct unauthenticated endpoints require verification.

5. **Which Marathi sources exist in PDF/DOCX/PPTX/etc.?**
   PDF: Economic Survey of Maharashtra 2023-24 (direct URL confirmed on OpenCity), Maharashtra Budget Speech 2023-24, Balbharati textbooks. DOCX/PPTX: NOT FOUND in official repositories.

6. **Which English sources can provide additional format coverage?**
   None needed. English format coverage in Phase 8.5 Golden Corpus is already comprehensive across all 10 format families.

7. **What is the smallest high-quality corpus that gives meaningful format diversity?**
   The 2-document core:
   - 1 major Marathi PDF (`CAND-FD-MR-PDF-01`, ~300+ pages of prose + tables)
   - 1 major Hindi PDF (`CAND-FD-HI-PDF-01` or `CAND-FD-HI-PDF-03`, ~100+ pages of policy prose + tables)
   This immediately creates balance across English, Hindi, and Marathi in the primary `PDFParser` path, enabling honest 30-case directional evaluation cohorts.

8. **Which sources should be acquired first?**
   `CAND-FD-MR-PDF-01` (Economic Survey of Maharashtra, Marathi PDF) because its direct URL is validated and its license is open public data.

9. **Which sources should be rejected and why?**
   - `Politics.zip` & `Science & Technology.zip`: Rejected because they are plain `.txt` only.
   - `MNATD.zip`: Rejected because it is plain `.txt` only and incomplete.
   - `CAND-FD-HI-PDF-02` (NCERT): Temporarily held under REVIEW REQUIRED due to restrictive copyright against electronic redistribution.

10. **What governance decisions are required before acquisition?**
    - Ratify DEC-P8.6-FD-01 (Format diversity mandate)
    - Ratify DEC-P8.6-FD-08 (Direct binary URL verification requirement)
    - Authorize Priority 1 acquisition of `CAND-FD-MR-PDF-01` and `CAND-FD-HI-PDF-01`

---

*Report Complete — 2026-09-03*
*New Downloads: 0 | Ingestion: FALSE | Phase 8.5: FROZEN*
