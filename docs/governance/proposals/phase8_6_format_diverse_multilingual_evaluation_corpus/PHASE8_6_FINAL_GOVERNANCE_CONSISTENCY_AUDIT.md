# PHASE 8.6 — FINAL FORMAT-DIVERSITY GOVERNANCE CONSISTENCY AUDIT
**Classification:** GOVERNANCE AUDIT & CONSISTENCY RECONCILIATION
**Date:** 2026-09-03
**Status:** COMPLETE / VERIFIED
**Phase:** Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus

---

## 1. EXECUTIVE SUMMARY

This audit establishes the final, authoritative governance consistency baseline for **Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus**.

Following the controlled deletion of the three obsolete plain-text archives (`Politics.zip`, `Science & Technology.zip`, and partial `MNATD.zip`) and the semantic renaming from Phase 9 to Phase 8.6, an exhaustive review was conducted across all Phase 8.6 governance documents.

### The Governing Principle
The governing principle of Phase 8.6 is officially codified as:

> **"Phase 8.6 must contain authentic documents spanning multiple natively supported formats, with multilingual coverage prioritized. A format does NOT need to exist for every language. No synthetic format conversion is permitted solely to satisfy format coverage."**

This principle establishes that **authenticity, semantic density, and retrieval-evaluation value strictly supersede superficial format counts or rigid matrix-filling**.

---

## 2. PART A — AUDIT OF GOVERNANCE PROPOSALS & CONTRADICTION ELIMINATION

Every proposal document under `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/` was audited to eliminate any wording implying that:
- Every language must be represented in every format;
- A rigid 3×N matrix must be completed before any document can be ingested;
- DOCX and PPTX are mandatory prerequisites for Hindi and Marathi regardless of whether authentic public documents exist;
- Numeric-only XLSX/CSV files are acceptable merely to increment format count.

### 2.1 Reconciled Assertions

| Previous Rigid / Ambiguous Phrasing | Reconciled Governed Wording | Rationale |
| :--- | :--- | :--- |
| "The format-diverse baseline requires at minimum: at least one DOCX in Hindi or Marathi, and at least one PPTX in Hindi or Marathi" | **"The format-diverse baseline requires authentic documents across multiple native format families. Non-PDF formats (DOCX/PPTX) are prioritized where authentic public documents exist, but are NOT artificially mandated if official publishers release only PDF."** | Government publishers in Maharashtra and India publish gazettes and official reports exclusively in PDF. Blocking Marathi PDF acquisition because a Marathi PPTX does not exist would paralyze evaluation. |
| "Must exercise at least 3 distinct production parser classes on non-English Unicode text before ingestion" | **"The evaluation corpus as a whole must exercise multiple distinct production parser classes, with newly acquired material providing substantial Hindi and Marathi language coverage."** | Avoids deadlock. Combined with Phase 8.5's existing DOCX/PPTX/XLSX parser coverage, acquiring authentic Marathi and Hindi PDFs immediately exercises multi-column layout and tabular extraction on Devanagari. |
| "All formats must be represented for all languages" | **"A format does NOT need to exist for every language. Formats reflect real publishing practices."** | Authentic publishing realities take precedence over artificial matrix completion. |

---

## 3. PART B — PROPOSED MINIMUM FORMAT-DIVERSITY BASELINE

### Proposed Governance Baseline (Requires Human Approval)

To provide an objective, defensible standard for corpus admission without creating impossible preconditions, the following **Minimum Format-Diversity Baseline** is proposed:

```
================================================================================
PROPOSED MINIMUM FORMAT-DIVERSITY BASELINE
================================================================================
1. Distinct Format Families (System-Level):
   The evaluation corpus suite (Phase 8.5 Golden + Phase 8.6 Expansion) must span
   at least FOUR (4) distinct natively supported format families:
   - PDF (PDFParser)
   - DOCX (DOCXParser)
   - PPTX (PPTXParser)
   - XLSX / Tabular (XLSXParser / CSVParser)

2. Multilingual Representation:
   Newly acquired Phase 8.6 material must add substantial authentic coverage in
   at least TWO (2) non-English language families:
   - Hindi (hi, Devanagari script)
   - Marathi (mr, Devanagari script)

3. Substantive Document Threshold:
   - At least ONE (1) major authentic Marathi document (≥ 50 pages / ≥ 100 paragraphs of continuous prose).
   - At least ONE (1) major authentic Hindi document (≥ 50 pages / ≥ 100 paragraphs of continuous prose).

4. Non-PDF Multilingual Expansion:
   Targeted discovery for authentic Hindi and/or Marathi DOCX, PPTX, or Markdown
   documents shall continue, but acquisition of verified PDF candidates shall NOT
   be blocked pending non-PDF discovery.

5. Strict Anti-Fabrication Constraints:
   - Zero synthetic conversion (e.g. PDF-to-DOCX conversion is strictly prohibited).
   - Zero low-value numeric padding (spreadsheets with only numbers and headers are excluded).
   - Zero plain-text-only dominance (no standalone TXT archives admitted without multi-format anchor).
================================================================================
```

### Baseline Rationale:
- **Why PDF is highest priority:** PDF is the universal medium for authoritative government, legal, and academic publications in India. It simultaneously exercises PyMuPDF text stream extraction, font encoding, Devanagari ligature handling, page boundary mapping, and table detection.
- **Why DOCX/PPTX are optional/secondary:** While Mnemo natively supports DOCX and PPTX, public government bodies in Maharashtra and India do not publish editable word processor or presentation files for official reports. Forcing DOCX/PPTX before acquiring verified PDFs would stall progress or force artificial file creation.
- **What is explicitly forbidden:** Synthetically converting PDFs into DOCX/PPTX or generating mock slides. Every admitted document must be an authentic artifact from an original publisher.

---

## 4. PART C — AUDIT OF EXISTING PHASE 8.5 FORMAT COVERAGE

Inspection of `goldenDataset/Phase 8.5 Evaluation Corpus/` (44 files, frozen) confirms existing system-level parser coverage:

| Format Family | Count | Primary Language | Parser Exercised | Existing Multilingual Status | Phase 8.6 Role |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **PDF** | 12 | English (11), Hindi/Bilingual (1) | `PDFParser` | Critically deficient in Marathi (10 chunks in `manuscript.pdf`). | **Primary Expansion Target:** Add major Marathi and Hindi PDFs. |
| **DOCX** | 1 | English | `DOCXParser` | Zero Hindi, zero Marathi. | **Secondary Target:** Seek authentic academic notes where available. |
| **PPTX** | 2 | English | `PPTXParser` | Zero Hindi, zero Marathi. | **Secondary Target:** Seek authentic training slide decks where available. |
| **XLSX** | 5 | English | `XLSXParser` | Zero Hindi, zero Marathi. | **Optional:** Tabular data admitted only if narrative text is present. |
| **CSV** | 1 | English | `CSVParser` | Zero Hindi, zero Marathi. | **Optional.** |
| **HTML** | 1 | English | `HTMLParser` | Zero Hindi, zero Marathi. | **Optional.** |
| **Markdown** | 1 | English | `MarkdownParser` | Zero Hindi, zero Marathi. | **Optional.** |
| **Plain Text** | 1 | English | `PlainTextParser` | Zero Hindi, zero Marathi. | **Supplementary Only.** |
| **Code** | 12 | English | `PlainTextParser` | N/A (Programming code). | No expansion required. |
| **Image** | 8 | N/A | `StandaloneImageParser` | Images only, no text. | No expansion required (OCR is not native). |

**Conclusion:** Phase 8.5 already proves that Mnemo's parser stack functions on English DOCX, PPTX, XLSX, HTML, and Markdown. Phase 8.6's true engineering value is to prove that the system retrieves **authentic Devanagari text (Marathi and Hindi) across real document layouts**.

---

## 5. PART G — SEPARATION OF CRITICAL EVALUATION CONCEPTS

To avoid confusion during benchmark authoring, governance explicitly decouples the following four concepts:

```
+-------------------------------------------------------------------------------+
|                       EVALUATION CONCEPT DECOUPLING                           |
+-------------------------------------------------------------------------------+
| 1. FORMAT DIVERSITY                                                           |
|    Definition: Exercising distinct parser classes and physical file structures |
|    (e.g. PDF multi-column layout vs DOCX styles vs XLSX tables).              |
|    Invariant: Does NOT require every language to exist in every format.       |
+-------------------------------------------------------------------------------+
| 2. LANGUAGE COVERAGE                                                          |
|    Definition: Linguistic representation of target scripts, vocabularies, and |
|    semantic domains (English, Hindi, Marathi).                                |
|    Invariant: Does NOT depend on having 10,000 documents; depends on authentic|
|    linguistic depth and terminology.                                          |
+-------------------------------------------------------------------------------+
| 3. QUERY SAMPLE SIZE                                                          |
|    Definition: The statistical power of the evaluation cohort (e.g. n=30 per  |
|    direction = 270 queries; n=75 per direction = 675 queries).                |
|    Invariant: A large query count over a single document causes query         |
|    saturation and tests memorization rather than generalization.              |
+-------------------------------------------------------------------------------+
| 4. STATISTICAL INDEPENDENCE                                                   |
|    Definition: Independence of underlying evidence sources (governed by the   |
|    20% concentration ceiling at both constituent and parent-dataset levels).  |
|    Invariant: Multiple articles from one news dataset are NOT statistically   |
|    independent; independent government/academic publishers are required.      |
+-------------------------------------------------------------------------------+
```

---

## 6. PART H & L — FINAL GOVERNANCE DECLARATIONS

```
================================================================================
PHASE 8.6 GOVERNANCE LIFECYCLE ASSERTION
================================================================================
PHASE:
Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus

FORMAT-DIVERSITY POLICY:
PROPOSED — REQUIRES HUMAN GOVERNANCE APPROVAL

MINIMUM FORMAT BASELINE:
PROPOSED — REQUIRES HUMAN GOVERNANCE APPROVAL

TXT-ONLY DATASETS:
DELETED (Politics.zip, Science & Technology.zip, MNATD.zip)

NEW DOWNLOADS:
0

EXTRACTION:
FALSE

INGESTION:
FALSE

INDEXING:
FALSE

QREL:
FALSE

EVALUATION:
FALSE

PHASE 8.5 GOLDEN CORPUS:
UNCHANGED (Verified via authoritative hash register)

V2 RUNTIME:
UNCHANGED

ACQUISITION GATE:
CLOSED (Awaiting explicit human ratification of proposed decisions)
================================================================================
```
