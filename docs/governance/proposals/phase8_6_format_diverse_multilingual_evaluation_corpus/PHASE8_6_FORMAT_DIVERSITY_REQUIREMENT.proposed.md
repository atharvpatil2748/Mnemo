# PHASE 8.6 — FORMAT DIVERSITY REQUIREMENT
**Classification:** GOVERNANCE PROPOSAL — REQUIRES HUMAN RATIFICATION
**Proposal Date:** 2026-09-03
**Status:** PROPOSED — AWAITING HUMAN GOVERNANCE APPROVAL
**Phase:** Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus

---

## 1. BACKGROUND & PROBLEM STATEMENT

What was previously initiated as a multilingual expansion effort targeting raw chunk volume resulted in the acquisition of three plain-text (`.txt`) archives:
- `Politics.zip` (20,939 `.txt` news articles)
- `Science & Technology.zip` (6,017 `.txt` news articles)
- `MNATD.zip` (partially downloaded plain `.txt` archive)

A forensic inspection confirmed that these archives **exercise only a single parser path** (`PlainTextParser`). They provide **zero verification** of Mnemo's:
- `PDFParser` (page boundaries, bounding boxes, table extraction, multi-column reading);
- `DOCXParser` (heading hierarchies, paragraph styles, embedded relationships);
- `PPTXParser` (slide shapes, slide titles, slide-level table and image locators);
- `XLSXParser` (worksheet partitions, tabular grids, row limits);
- Multimodal / transient asset pipelines across non-English text.

---

## 2. THE GOVERNING PRINCIPLE

The central policy of Phase 8.6 is officially codified as:

> **"Phase 8.6 must contain authentic documents spanning multiple natively supported formats, with multilingual coverage prioritized. A format does NOT need to exist for every language. No synthetic format conversion is permitted solely to satisfy format coverage."**

### Core Invariants:
1. **Authenticity Over Matrix Filling:** An authentic, high-quality document collection that reflects real-world publishing practices strictly supersedes an artificial 3×N matrix.
2. **Zero Synthetic Conversion:** Converting a PDF into DOCX or PPTX is strictly forbidden. Documents must be ingested in the authentic format released by their original publisher.
3. **No Low-Value Padding:** Tabular datasets (XLSX/CSV) containing predominantly numbers with short column headers provide negligible semantic retrieval evaluation value and shall not be admitted merely to check a format box.
4. **OCR Gating Decoupled:** OCR is an optional, provider-backed pipeline. Phase 8.6 candidates must contain native, selectable Unicode text.

---

## 3. DISPOSITION OF OBSOLETE TXT-ONLY DATASETS

In accordance with Phase 8.6 Part A directives, the obsolete TXT-only archives have been **permanently deleted from disk**:

| Archive Name | Status | Disposition | Reason |
| :--- | :--- | :--- | :--- |
| `Politics.zip` | 59,972,294 bytes | **DELETED** | TXT-only format does not satisfy format-diversity requirement |
| `Science & Technology.zip` | 15,073,261 bytes | **DELETED** | TXT-only format does not satisfy format-diversity requirement |
| `MNATD.zip` | 759,169,024 bytes (partial) | **DELETED** | Download terminated, incomplete, TXT-only |

Zero files were extracted. Zero database tables were modified.

---

## 4. PHASE 8.6 MINIMUM FORMAT-DIVERSITY BASELINE

### 4.1 Proposed Baseline (Requires Human Ratification)

Before any candidate corpus may be admitted or ingested for Phase 8.6, the combined evaluation suite must satisfy:

1. **System-Level Multi-Format Representation:** The complete evaluation corpus (Phase 8.5 Golden + Phase 8.6 Expansion) must span at least **four (4) distinct native format families** (`PDFParser`, `DOCXParser`, `PPTXParser`, `XLSXParser`/`CSVParser`).
2. **Substantial Multilingual Expansion:** Newly acquired Phase 8.6 material must introduce substantial authentic text across at least **two (2) non-English language families** (Hindi and Marathi).
3. **Document Scale & Continuity:**
   - At least one (1) major authentic Marathi document (≥ 50 pages / ≥ 100 paragraphs of cohesive prose).
   - At least one (1) major authentic Hindi document (≥ 50 pages / ≥ 100 paragraphs of cohesive prose).
4. **Authentic Publishing Realities:** Government bodies in India publish authoritative reports and gazettes overwhelmingly as **PDF**. Therefore, acquisition of verified, high-value Marathi and Hindi PDFs shall proceed without waiting for non-existent public DOCX/PPTX variants.
5. **Targeted Non-PDF Discovery:** A second round of discovery shall actively seek authentic, public-domain or open-licensed non-PDF documents (such as university lecture decks or academic syllabi) without resorting to synthetic conversion.
6. **Supplementary Plain Text:** Plain text (`.txt`) is restricted to a supplementary role *after* the multi-format baseline is established.

---

## 5. SEPARATION OF EVALUATION CONCEPTS

Governance strictly enforces the analytical distinction between:
- **Format Diversity:** Exercising distinct parser implementations and document object models.
- **Language Coverage:** Linguistic representation of vocabulary, syntax, and morphology in Devanagari.
- **Query Sample Size:** Statistical cohort size ($n=30$ provisional, $n=75$ certification) to achieve statistical power.
- **Statistical Independence:** Diversity of underlying sources to satisfy the 20% concentration ceiling across independent publishers.

A large number of formats does not guarantee linguistic diversity; a large token count in plain text does not guarantee parser diversity. Both dimensions must be satisfied with genuine artifacts.

---

## 6. CURRENT GOVERNED STATUS

```
================================================================================
PHASE 8.6 FORMAT-DIVERSITY REQUIREMENT: LIFECYCLE SUMMARY
================================================================================
FORMAT-DIVERSITY REQUIREMENT   = PROPOSED — REQUIRES HUMAN GOVERNANCE APPROVAL
TXT DATASETS                   = DELETED
  Politics.zip                 = DELETED
  Science & Technology.zip     = DELETED
  MNATD.zip                    = DELETED / WAS PARTIAL
NEW DATASET DOWNLOADS          = 0
NEW DATASET EXTRACTIONS        = FALSE
INGESTION                      = FALSE
INDEXING                       = FALSE
EVALUATION                     = FALSE
QREL CREATION                  = FALSE

PHASE 8.5 GOLDEN CORPUS        = FROZEN / UNCHANGED
V2 RUNTIME                     = UNCHANGED
ACQUISITION GATE               = CLOSED
================================================================================
```
