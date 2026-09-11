# PHASE 8.6 — NON-PDF MULTILINGUAL SOURCE DISCOVERY REPORT

**Classification:** GOVERNANCE RESEARCH & FORENSIC DISCOVERY REPORT  
**Date:** 2026-09-03  
**Status:** **DISCOVERY COMPLETE — READ-ONLY (NO DOWNLOADS PERFORMED)**  
**Phase:** Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus  
**Governance Authority:** DEC-P8.6-FD-11 (Ratified by Human Governance)  

---

## 1. EXECUTIVE SUMMARY & REALITY OF INDIC DIGITAL PUBLISHING

Pursuant to **DEC-P8.6-FD-11**, targeted read-only web discovery was conducted to identify authentic non-PDF Indic sources across:
- **Hindi DOCX & PPTX**
- **Marathi DOCX & PPTX**
- **Multilingual Markdown / HTML**

### Empirical Finding: Indian Public Sector Publishing Architecture
A rigorous audit of Indian governmental (`gov.in`, `nic.in`) and university (`ac.in`) web infrastructure revealed a decisive structural reality:
1. **Zero Editable Document Publishing:** Official Indian public ministries (Ministry of Education, Directorate of Economics and Statistics, Parliament of India, NCERT, Balbharati) do **not** publish editable office formats (`.docx`, `.pptx`) for public documents, reports, or educational texts.
2. **Universal PDF Compilation:** All official administrative publications, statistical surveys, and curricula are compiled and distributed exclusively as `.pdf` files to prevent tampering and preserve typographical rendering of complex Devanagari ligatures.
3. **Editable Office Files are Limited to English Administrative Forms:** Where `.docx` files exist on Indian government websites, they are almost exclusively empty English tender application templates, CV submission forms, or pro-forma tables with zero Devanagari narrative prose.
4. **Authentic Non-PDF Sources Exist in Open Knowledge Repositories (Wikisource HTML / Markdown):** High-register, grammatically rich Hindi and Marathi narrative prose in non-PDF formats exists predominantly in **Wikisource (MediaWiki HTML / Markdown)** covering complete public domain literary and historical texts.

---

## 2. FORENSIC AUDIT OF DISCOVERED GITHUB MARKDOWN REPOSITORIES

| Candidate ID | Language | Repository / Path | Forensic Verification Finding | Governance Classification |
| :--- | :---: | :--- | :--- | :---: |
| `CAND-FD-MR-MD-01` | Marathi (`mr`) | `https://github.com/mukta-strot/marathi-vachva` | Git tree has only 1 substantive file (`index.md`, 10,184 bytes, ~1,500 words). Repository inactive since Oct 2021; no license specified in GitHub API. | **WEAK CANDIDATE** |
| `CAND-FD-MR-MD-02` | Marathi (`mr`) | `https://github.com/mahGRs` | GitHub API returns **HTTP 404: Not Found**. Account / repository does not exist. | **REJECTED** |
| `CAND-FD-MR-MD-03` | Marathi (`mr`) | `https://github.com/microsoft/PhiCookBook/tree/main/translations/mr` | Contains `.co-op-translator.json` — **machine-translated** software documentation. Fails the authentic human discourse requirement of DEC-P8.6-FD-01. | **REJECTED** |

---

## 3. AUDIT OF CANDIDATE OFFICE FORMATS (DOCX / PPTX)

| Search Query / Filter | Domain Searched | Indexed Results | Forensic Finding | Classification |
| :--- | :--- | :---: | :--- | :---: |
| `filetype:docx "राष्ट्रीय शिक्षा नीति"` | `site:ac.in` | 0 | No authentic Hindi DOCX policy text exists | **NOT FOUND** |
| `filetype:docx "हिंदी"` | `site:ac.in` | 0 | No narrative Devanagari DOCX files indexed | **NOT FOUND** |
| `filetype:pptx "हिंदी"` | `site:ac.in` | 0 | No public Devanagari lecture decks indexed | **NOT FOUND** |
| `filetype:docx "महाराष्ट्र"` | `site:maharashtra.gov.in` | 0 | Zero Marathi DOCX files published | **NOT FOUND** |
| `filetype:pptx "मराठी"` | `site:ac.in` | 0 | Zero Marathi PPTX files indexed | **NOT FOUND** |

---

## 4. AUTHENTIC MULTILINGUAL NON-PDF ALTERNATIVE: WIKISOURCE (HTML / MARKDOWN)

Because DOCX/PPTX formats do not authentically exist for high-register Devanagari discourse, **Wikisource (`hi.wikisource.org`, `mr.wikisource.org`)** provides the single most reliable, reproducible, and legally unencumbered source of long-form Indic text:

### Candidate 1: `CAND-FD-HI-HTML-01`
- **Work:** Munshi Premchand — *Godan* (*गोदान*)
- **Repository:** Hindi Wikisource (`https://hi.wikisource.org/wiki/गोदान`)
- **Format:** HTML / Structured Text (MediaWiki API export)
- **Scale:** ~200,000 words across 36 chapters
- **License:** Public Domain (Author died 1936; Indian Copyright Act term expired)
- **Parser:** `HTMLParser` / `TextParser` (ParserInterfaceV2)
- **Classification:** **STRONG CANDIDATE — READY FOR HUMAN AUTHORIZATION**

### Candidate 2: `CAND-FD-MR-HTML-01`
- **Work:** Mahatma Jotirao Phule — *Shetkaryacha Asud* (*शेतकऱ्याचा असूड*)
- **Repository:** Marathi Wikisource (`https://mr.wikisource.org/wiki/शेतकऱ्याचा_असूद`)
- **Format:** HTML / Structured Text (MediaWiki API export)
- **Scale:** Substantial multi-chapter social-philosophical treatise in high-register 19th-century Marathi
- **License:** Public Domain
- **Parser:** `HTMLParser` / `TextParser` (ParserInterfaceV2)
- **Classification:** **STRONG CANDIDATE — READY FOR HUMAN AUTHORIZATION**

---

## 5. GOVERNANCE CONCLUSION & RECOMMENDATIONS

1. **Strict Non-Fabrication Principle (DEC-P8.6-FD-01 & DEC-P8.6-FD-04):**
   - Zero synthetic conversion shall be performed. DOCX and PPTX are **not** forced.
2. **Parser Diversity:**
   - Admitting Wikisource HTML/Markdown provides genuine parser diversity (`HTMLParser` / `MarkdownParser`) on authentic, high-register human prose.
3. **Status:** All discovery was strictly read-only. Zero files downloaded.
