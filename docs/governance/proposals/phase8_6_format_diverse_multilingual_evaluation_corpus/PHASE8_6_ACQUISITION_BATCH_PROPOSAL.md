# PHASE 8.6 — FORMAT-DIVERSE ACQUISITION BATCH PROPOSAL

**Classification:** GOVERNANCE ACQUISITION PROPOSAL — REQUIRES HUMAN AUTHORIZATION  
**Date:** 2026-09-03  
**Status:** **PROPOSED — ACQUISITION GATE CLOSED (0 DOWNLOADS)**  
**Phase:** Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus  

---

> [!IMPORTANT]
> **Zero downloads shall occur automatically.**
> This proposal groups all discovered and audited candidates into three strict governance categories:
> 1. **FIRST BATCH — READY FOR HUMAN AUTHORIZATION**
> 2. **SECOND BATCH — REQUIRES FURTHER VERIFICATION**
> 3. **REJECTED / BLOCKED**
>
> Execution will occur **only** upon explicit, written human ratification of specific candidate IDs.

---

## 1. CATEGORY 1: FIRST BATCH — READY FOR HUMAN AUTHORIZATION

Candidates in this tier have passed all preflight checks:
- Exact source organization and provenance certified;
- Authentic, human-authored, high-register prose verified (Devanagari script);
- Licensing verified (Public Domain / CC BY-SA 4.0);
- URL endpoints proven stable and reproducibly accessible via standard HTTP API;
- Meaningful format and language diversity established without synthetic conversion.

---

### Candidate 1: `CAND-FD-HI-HTML-01`
**Title:** *गोदान (Godan)* by Munshi Premchand  
**Language:** Hindi (`hi`, Devanagari script)  
**Format:** HTML / Structured MediaWiki Text (`text/html`)  
**Parser Exercised:** `HTMLParser` / `TextParser` (ParserInterfaceV2)  
**Publisher / Repository:** Hindi Wikisource (`https://hi.wikisource.org/wiki/गोदान`)  

| Evaluation Dimension | Verified Finding |
| :--- | :--- |
| **Reproducibility** | **HIGHEST**. Permanent REST API endpoint: `https://hi.wikisource.org/w/api.php?action=parse&page=गोदान&format=json`. Zero tokens, zero dynamic gating. |
| **Authenticity** | Masterpiece of modern Hindi literature. Written by Munshi Premchand (1936). |
| **Licensing Evidence** | Public Domain (Author passed away in 1936; Indian Copyright Act 60-year posthumous term expired). Content dual-licensed CC BY-SA 4.0. |
| **Scale & Density** | ~200,000 words across 36 structured chapters. Continuous, high-register narrative prose covering agrarian economy, social structures, and legal conflicts. |
| **Parser Exercise** | Exercises HTML DOM traversal, paragraph extraction, heading hierarchy, and Unicode Devanagari character handling. |
| **Evaluation Value** | Provides an ideal, noise-free benchmark for Hindi semantic retrieval and multi-hop question answering. |

---

### Candidate 2: `CAND-FD-MR-HTML-01`
**Title:** *शेतकऱ्याचा असूड (Shetkaryacha Asud — The Cultivator's Whipcord)* by Mahatma Jotirao Phule  
**Language:** Marathi (`mr`, Devanagari script)  
**Format:** HTML / Structured MediaWiki Text (`text/html`)  
**Parser Exercised:** `HTMLParser` / `TextParser` (ParserInterfaceV2)  
**Publisher / Repository:** Marathi Wikisource (`https://mr.wikisource.org/wiki/शेतकऱ्याचा_असूद`)  

| Evaluation Dimension | Verified Finding |
| :--- | :--- |
| **Reproducibility** | **HIGHEST**. Permanent REST API endpoint: `https://mr.wikisource.org/w/api.php?action=parse&page=शेतकऱ्याचा_असूद&format=json`. |
| **Authenticity** | Foundational 19th-century Marathi socio-economic treatise on agriculture, rural governance, and education (1883). |
| **Licensing Evidence** | Public Domain (19th-century work). Dual-licensed CC BY-SA 4.0. |
| **Scale & Density** | Substantial multi-part prose treatise (~25,000 words). High-register formal Marathi with rich socio-economic vocabulary. |
| **Parser Exercise** | Exercises HTML tag parsing, section demarcation, and Marathi Unicode font handling. |
| **Evaluation Value** | Eliminates the single greatest defect in the evaluation suite (current Marathi coverage is only 10 short chunks in `manuscript.pdf`). |

---

## 2. CATEGORY 2: SECOND BATCH — REQUIRES FURTHER VERIFICATION

Candidates in this tier represent authentic, valuable documents whose automated retrieval is currently constrained by server-side rate limits, session management, or network instability:

---

### Candidate 3: `CAND-FD-MR-PDF-04`
**Title:** *महाराष्ट्राची आर्थिक पाहणी २०२५-२६ (Economic Survey of Maharashtra 2025-26 — Marathi Edition)*  
**Language:** Marathi (`mr`, Devanagari script)  
**Format:** PDF (`application/pdf`, PDF 1.7)  
**Parser Exercised:** `PDFParser` (ParserInterfaceV2)  
**Publisher:** Directorate of Economics and Statistics (DES), Planning Department, Government of Maharashtra  
**Source Portal:** `https://mahades.maharashtra.gov.in/esm.do?type=R&lang=mr`  
**Endpoints Discovered:**
- `highlights_mar.pdf` (785 KB, 8 pages, **61.8% Devanagari text verified via PyMuPDF**)
- `ch1_m.pdf` (~1.2 MB, 10 pages, **65.3% Devanagari text verified via PyMuPDF**)
- `esm_2526_m.pdf` (38.98 MB, complete compiled state report)  

| Evaluation Dimension | Verified Finding |
| :--- | :--- |
| **Authenticity** | Verified authentic official Government of Maharashtra economic prose. |
| **Why In Second Batch** | Server `mahades.maharashtra.gov.in` experiences intermittent TCP socket timeouts during automated script probes. Requires an authorized resilient retrieval harness with exponential backoff before batch acquisition can proceed cleanly. |

---

### Candidate 4: `CAND-FD-MR-MD-01`
**Title:** *मराठी वाचवा (Marathi Vachva) — Language Preservation Guide*  
**Language:** Marathi (`mr`, Devanagari script)  
**Format:** Markdown (`text/markdown`, `.md`)  
**Parser Exercised:** `MarkdownParser` (ParserInterfaceV2)  
**Repository:** `https://github.com/mukta-strot/marathi-vachva`  

| Evaluation Dimension | Verified Finding |
| :--- | :--- |
| **Authenticity** | Authentic community linguistic guide on Marathi grammar and orthography. |
| **Why In Second Batch** | The repository contains only a single substantive file (`index.md`, 10,184 bytes, ~1,500 words). Volume is very small for an evaluation benchmark; requires human decision on whether ~1,500 words is acceptable as a parser-test probe. |

---

## 3. CATEGORY 3: REJECTED / BLOCKED

Candidates in this tier have failed forensic verification, violated governing principles (DEC-P8.6-FD-01), or cannot be reproducibly retrieved:

---

### Candidate 5: `CAND-FD-MR-PDF-01`
**Title:** *Economic Survey of Maharashtra 2023-24 (OpenCity Mislabeled Resource)*  
**Status:** **REJECTED — NOT ADMITTED (LANGUAGE MISMATCH)**  
- **Forensic Reason:** Downloaded file `dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf` is `Microsoft Word - PREFACE_23_24_E_30524.doc` (the **English Edition**), containing 888,339 characters and **0.0% Devanagari**.
- **Action:** Preserved on disk solely as negative forensic evidence. Gated from evaluation corpus.

---

### Candidate 6: `CAND-FD-HI-PDF-01`
**Title:** *Ministry of Education Annual Report 2023-24 (Hindi Edition)*  
**Status:** **BLOCKED — TOKEN-GATED ENDPOINT**  
- **Forensic Reason:** Portal `dohe-education.gov.in` serves document links via a client-side Next.js React SPA with an authenticated WordPress REST API (`wp-json/document/documents`) requiring dynamic browser token headers. Direct scripted HTTP requests time out. Halted under DEC-P8.6-FD-10.

---

### Candidate 7: `CAND-FD-HI-PDF-03`
**Title:** *National Education Policy 2020 — Hindi Edition (राष्ट्रीय शिक्षा नीति २०२०)*  
**Status:** **BLOCKED — SOURCE RESOLUTION FAILURE**  
- **Forensic Reason:** Legacy Drupal static endpoints (`/sites/upload_files/mhrd/files/nep/NEP_final_HINDI.pdf` and `/sites/default/files/NEP_Final_Hindi.pdf`) return **HTTP 404: Not Found** following the Ministry's platform migration. Mirror probes on NCERT drop connections (`WinError 10054`), and Archive.org snapshots time out. Cannot be reproducibly retrieved via static script.

---

### Candidate 8: `CAND-FD-MR-MD-02`
**Title:** *mahGRs Collection*  
**Status:** **REJECTED — REPOSITORY NOT FOUND**  
- **Forensic Reason:** Probes to `https://api.github.com/users/mahGRs` return **HTTP 404: Not Found**. The purported repository does not exist.

---

### Candidate 9: `CAND-FD-MR-MD-03`
**Title:** *Microsoft PhiCookBook Marathi Localization*  
**Status:** **REJECTED — SYNTHETIC / MACHINE TRANSLATION**  
- **Forensic Reason:** Forensically confirmed to contain `.co-op-translator.json` — machine-translated AI documentation. Fails the authentic human discourse requirement of DEC-P8.6-FD-01 (*"No synthetic format conversion is permitted solely to satisfy format coverage"*).

---

## 4. FORMAT DIVERSITY MATRIX UNDER PROPOSED BATCHES

| Format Family | Intended Native Parser | First Batch Representation | Status |
| :--- | :--- | :--- | :---: |
| **PDF** | `PDFParser` (ParserInterfaceV2) | Phase 8.5 Golden Baseline (`manuscript.pdf`, `Ramayana.pdf`, `PHYSICS_JEE_ADVANCED.pdf`) | **CERTIFIED** |
| **DOCX** | `DocxParser` (ParserInterfaceV2) | Phase 8.5 Golden Baseline (`ME333_Linear_Systems_Analysis.docx`) | **CERTIFIED** |
| **PPTX** | `PptxParser` (ParserInterfaceV2) | Phase 8.5 Golden Baseline (`Quantum_Spin_Hall_Effect.pptx`) | **CERTIFIED** |
| **HTML / Markdown** | `HTMLParser` / `TextParser` (ParserInterfaceV2) | **`CAND-FD-HI-HTML-01` (Godan)** & **`CAND-FD-MR-HTML-01` (Shetkaryacha Asud)** | **READY FOR AUTHORIZATION** |

> [!NOTE]
> Admitting Category 1 (*Godan* and *Shetkaryacha Asud*) achieves:
> 1. Full 4-format parser diversity (PDF, DOCX, PPTX, HTML/Markdown).
> 2. Complete, noise-free, high-volume coverage for both Hindi (~200,000 words) and Marathi (~25,000 words).
> 3. Zero copyright ambiguity (100% public domain).
> 4. Zero synthetic conversion.
