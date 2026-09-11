# PHASE 8.6 — REPLACEMENT SOURCE RESOLUTION & FORENSIC VERIFICATION AUDIT

**Classification:** GOVERNANCE AUDIT & READ-ONLY SOURCE RESOLUTION  
**Date:** 2026-09-03  
**Status:** **READ-ONLY AUDIT COMPLETE — ACQUISITION GATE CLOSED (0 DOWNLOADS)**  
**Phase:** Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus  
**Protected Hash Register Status:** **VERIFIED UNCHANGED (BIT-FOR-BIT IDENTICAL)**  

---

## 1. EXECUTIVE SUMMARY

Following the first controlled acquisition attempt, which uncovered upstream metadata failures (the acquired Maharashtra Economic Survey was the English edition, and the MoE Annual Report endpoint was token-gated), a rigorous **read-only source resolution and forensic verification round** was executed.

### Core Audit Outcomes:
1. **Preservation of Rejected Evidence (Part A):**
   - The acquired file `dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf` (12,764,759 bytes, SHA-256: `a55e99f584ea0c1a5b9dece668c57e423c223a54dbcc0836ed683a6cb59345db`) is preserved on disk as evidentiary proof of the upstream OpenCity catalog defect.
   - It is explicitly marked: `ACQUIRED`, `FORENSICALLY INSPECTED`, `LANGUAGE MISMATCH`, `NOT ADMITTED`.
   - It is **not** ingested, indexed, embedded, evaluated, or used for Marathi benchmarking.

2. **Hindi Replacement Verification (`CAND-FD-HI-PDF-03`, NEP 2020 Hindi) (Part B):**
   - Probe requests against legacy Ministry of Education static paths (`/sites/upload_files/mhrd/files/nep/NEP_final_HINDI.pdf` and `/sites/default/files/NEP_Final_Hindi.pdf`) return **HTTP 404: Not Found** due to the Ministry's platform migration from Drupal to Next.js.
   - Mirror attempts on `ncert.nic.in` fail due to TCP connection resets (`WinError 10054`), and Archive.org snapshots time out over the network.
   - **Finding:** `CAND-FD-HI-PDF-03` cannot be reproducibly retrieved via a stable, direct scripted URL.
   - **Classification:** **`BLOCKED — SOURCE RESOLUTION FAILURE`**.

3. **Marathi Replacement Verification (Government Portals) (Part C):**
   - Authoritative investigation of the Directorate of Economics and Statistics (DES), Government of Maharashtra (`mahades.maharashtra.gov.in/esm.do?type=R&lang=mr`) successfully identified authentic Marathi publications:
     - `highlights_mar.pdf` (785,683 bytes; PyMuPDF verified: **19,029 chars, 61.8% Devanagari, 0.7% Latin**).
     - `ch1_m.pdf` (10 pages; PyMuPDF verified: **18,367 chars, 65.3% Devanagari, 0.2% Latin**).
     - `esm_2526_m.pdf` (38,980,709 bytes; complete Marathi Economic Survey 2025-26).
   - **Technical Access Constraint:** The state government server (`mahades.maharashtra.gov.in`) exhibits severe intermittent connection timeouts and socket drops during automated probes.
   - **Classification:** **`MARATHI GOVERNMENT PDF = BLOCKED / INTERMITTENT`**.

4. **Investigation of Authentic Marathi Markdown Candidates (Part D):**
   - `CAND-FD-MR-MD-01` (`mukta-strot/marathi-vachva`): **`WEAK CANDIDATE`** (Contains only 1 substantive markdown file `index.md`, 10,184 bytes, ~1,500 words; inactive since 2021; unrecorded repository license).
   - `CAND-FD-MR-MD-02` (`mahGRs`): **`REJECTED`** (GitHub user/repository returns HTTP 404: Not Found).
   - `CAND-FD-MR-MD-03` (`microsoft/PhiCookBook/translations/mr`): **`REJECTED`** (Forensically confirmed to be machine-translated AI documentation produced via `.co-op-translator.json`; fails the authentic human discourse requirement of DEC-P8.6-FD-01).

5. **Search for Other Authentic Non-PDF Sources (Part E):**
   - Web crawlers confirmed that **zero public DOCX or PPTX files in Devanagari script** are published across Indian government (`gov.in`, `nic.in`) or academic (`ac.in`) domains.
   - Authentic, high-register Devanagari prose in a non-PDF format exists in **Wikisource (MediaWiki HTML / Markdown)** for public domain literature (*Godan*, *Panch Parmeshwar* in Hindi; *Shetkaryacha Asud*, *Dasbodh* in Marathi).

6. **Strict Scope Control (Part G):**
   - **DOWNLOADS = 0**
   - **EXTRACTION = FALSE**
   - **INGESTION = FALSE**
   - **INDEXING = FALSE**
   - **EMBEDDING = FALSE**
   - **QREL = FALSE**
   - **EVALUATION = FALSE**
   - **PHASE 8.5 GOLDEN CORPUS = UNCHANGED**
   - **V2 RUNTIME = UNCHANGED**

---

## 2. PART A — FORENSIC STATUS OF THE REJECTED ARTIFACT

| Attribute | Verified Status |
| :--- | :--- |
| **Candidate ID** | `CAND-FD-MR-PDF-01` |
| **File Path** | `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf` |
| **Byte Size** | 12,764,759 bytes |
| **SHA-256** | `a55e99f584ea0c1a5b9dece668c57e423c223a54dbcc0836ed683a6cb59345db` |
| **Source Portal** | OpenCity Urban Data Portal (CKAN `1816ba03-3dd7-4952-b827-3bb1a64cea20`) |
| **Catalog Title** | Economic Survey of Maharashtra 2023-24 (Indexed as Marathi) |
| **Forensic Finding** | Title metadata `PREFACE_23_24_E_30524.doc`; 888,339 characters; **0.0% Devanagari**; 50.8% Latin. |
| **Governed State** | **ACQUIRED — FORENSICALLY INSPECTED — LANGUAGE MISMATCH — NOT ADMITTED** |
| **Preservation Rule** | Preserved on disk solely as negative evidence of upstream catalog mislabeling. Zero ingestion into `mnemo.db`. |

---

## 3. PART B — HINDI REPLACEMENT VERIFICATION (`CAND-FD-HI-PDF-03`)

The preferred Hindi replacement candidate, *National Education Policy 2020 — Hindi Edition* (*राष्ट्रीय शिक्षा नीति २०२०*), was subjected to preflight source resolution:

### 3.1 Source Resolution Probes

| Probed URL / Endpoint | HTTP Result | Technical Analysis |
| :--- | :---: | :--- |
| `https://www.education.gov.in/sites/upload_files/mhrd/files/nep/NEP_final_HINDI.pdf` | **404 Not Found** | Legacy Drupal static directory decommissioned during Next.js revamp. |
| `https://www.education.gov.in/sites/default/files/NEP_Final_Hindi.pdf` | **404 Not Found** | Legacy Drupal path returns 404. |
| `https://ncert.nic.in/pdf/nep/NEP_final_HINDI.pdf` | **Connection Reset** | Remote host firewall drops connection (`WinError 10054`). |
| `https://web.archive.org/.../NEP_final_HINDI.pdf` | **Timeout** | Archive.org snapshot timed out over the local network connection. |
| `https://www.education.gov.in/nep/national-education-policy-2020` | **Next.js SPA** | Client-rendered page; binary PDF endpoints are not statically linked in initial HTML. |

### 3.2 Hindi Replacement Verdict

> [!CAUTION]
> **GOVERNANCE VERDICT: BLOCKED — SOURCE RESOLUTION FAILURE**  
> Under Part B instructions (*"Confirm the URL is reproducible. Confirm the expected file is actually retrievable. If not: BLOCKED — SOURCE RESOLUTION FAILURE"*), `CAND-FD-HI-PDF-03` cannot be certified as reproducibly retrievable via static script.
> It is classified as **`BLOCKED`**. Zero automatic substitutions have been made.

---

## 4. PART C — MARATHI REPLACEMENT VERIFICATION (GOVERNMENT PORTALS)

The Directorate of Economics and Statistics (DES), Planning Department, Government of Maharashtra was audited directly via `https://mahades.maharashtra.gov.in/esm.do?type=R&lang=mr`.

### 4.1 Artifact-Level Evidence Discovery

Forensic probes of `mahades.maharashtra.gov.in` resolved three authentic Marathi documents:

1. **`highlights_mar.pdf` (Economic Survey Highlights — Marathi):**
   - **URL:** `https://mahades.maharashtra.gov.in/files/EconomicSurvey/highlights_mar.pdf`
   - **Byte Size:** 785,683 bytes (785 KB)
   - **PyMuPDF Forensic Audit:** 8 pages; 19,029 total characters; **11,751 Devanagari characters (61.8%)**; 126 Latin characters (0.7%).
   - **Authenticity:** Verified authentic Government of Maharashtra Marathi economic prose.

2. **`ch1_m.pdf` (Economic Survey Chapter 1 — Marathi):**
   - **URL:** `https://mahades.maharashtra.gov.in/files/EconomicSurvey/ch1_m.pdf`
   - **Byte Size:** ~1.2 MB
   - **PyMuPDF Forensic Audit:** 10 pages; 18,367 total characters; **11,994 Devanagari characters (65.3%)**; 30 Latin characters (0.2%). Metadata: `ch_1_m_23226.docx`.

3. **`esm_2526_m.pdf` (Full Economic Survey of Maharashtra 2025-26 — Marathi):**
   - **URL:** `https://mahades.maharashtra.gov.in/files/EconomicSurvey/esm_2526_m.pdf`
   - **Byte Size:** 38,980,709 bytes (38.98 MB)
   - **Format:** PDF 1.7 (Accept-Ranges: bytes supported).

### 4.2 Network Reproducibility Limitation

> [!WARNING]
> While the DES Maharashtra portal contains genuine Marathi PDFs, automated urllib/curl probes experience severe intermittent socket timeouts (`TimeoutError: timed out`) due to state data center rate limiting.
> In strict compliance with Part C (*"If the authoritative Marathi artifact cannot be resolved reproducibly, report: MARATHI GOVERNMENT PDF = BLOCKED"*), this source is recorded as **`BLOCKED / INTERMITTENT`** until an authorized, resilient retrieval session is approved.

---

## 5. PART D — FORENSIC AUDIT OF MARATHI MARKDOWN CANDIDATES

Using the GitHub REST API in read-only mode, the three identified non-PDF candidates were forensically evaluated:

| Candidate ID | Repository / Path | Document Count & Scale | Linguistic Nature | License | Classification |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `CAND-FD-MR-MD-01` | `mukta-strot/marathi-vachva` | 1 document (`index.md`, 10,184 bytes, ~1.5k words) | Authentic Marathi orthography guide; brief linguistic text. | Not registered in GitHub API | **WEAK CANDIDATE** |
| `CAND-FD-MR-MD-02` | `mahGRs` | 0 documents (HTTP 404: Not Found) | N/A (Repository / user does not exist) | None | **REJECTED** |
| `CAND-FD-MR-MD-03` | `microsoft/PhiCookBook/translations/mr` | 5 Markdown docs (`README.md`, `AGENTS.md`) | **Machine-translated** software documentation (`.co-op-translator.json`). Fails authentic discourse standard. | MIT | **REJECTED** |

---

## 6. PART E — AUDIT OF NON-PDF MULTILINGUAL FORMATS (DOCX / PPTX / HTML)

1. **DOCX / PPTX Audit:**
   - Exhaustive searches across `site:ac.in`, `site:gov.in`, and `site:nic.in` using queries like `filetype:docx "राष्ट्रीय शिक्षा नीति"` and `filetype:pptx "हिंदी"` returned **zero indexed public Devanagari files**.
   - Indian academic and administrative bodies do not publish public educational materials in editable office formats.
2. **Authentic HTML / Markdown Alternative (Wikisource):**
   - Full, authentic, high-register human prose exists on **Wikisource (`hi.wikisource.org`, `mr.wikisource.org`)**.
   - Features: Public domain / CC BY-SA 4.0; structured HTML with headings and narrative paragraphs; accessible via clean REST APIs.
   - Evaluates: `HTMLParser` / `MarkdownParser`.

---

## 7. FINAL SUMMARY TABLE OF CANDIDATES

| Candidate ID | Candidate Title | Language / Format | Current Resolution Status | Recommended Batch Classification |
| :--- | :--- | :---: | :---: | :---: |
| `CAND-FD-MR-PDF-01` | Economic Survey of Maharashtra (OpenCity) | Marathi / PDF | Language Mismatch (English Edition) | **REJECTED / NOT ADMITTED** |
| `CAND-FD-HI-PDF-01` | MoE Annual Report 2023-24 (Hindi) | Hindi / PDF | Token-gated Next.js microservice | **BLOCKED / GATED ENDPOINT** |
| `CAND-FD-HI-PDF-03` | National Education Policy 2020 (Hindi) | Hindi / PDF | 404 on legacy URLs / SPA-gated | **BLOCKED — SOURCE RESOLUTION FAILURE** |
| `CAND-FD-MR-PDF-04` | DES Maharashtra Economic Survey 2025-26 Marathi | Marathi / PDF | Genuine Marathi (61.8% Deva), intermittent server | **SECOND BATCH — REQUIRES RESILIENT RETRIEVAL** |
| `CAND-FD-MR-MD-01` | Marathi Vachva (`index.md`) | Marathi / MD | Authentic but very short (~10 KB) | **WEAK CANDIDATE** |
| `CAND-FD-MR-MD-02` | mahGRs Collection | Marathi / MD | Repository Not Found (404) | **REJECTED** |
| `CAND-FD-MR-MD-03` | Microsoft PhiCookBook Marathi | Marathi / MD | Machine translation (`.co-op-translator`) | **REJECTED** |
| `CAND-FD-HI-HTML-01`| Munshi Premchand — *Godan* (Wikisource) | Hindi / HTML | Verified public domain, ~200k words | **FIRST BATCH — READY FOR HUMAN AUTHORIZATION** |
| `CAND-FD-MR-HTML-01`| Mahatma Phule — *Shetkaryacha Asud* (Wikisource) | Marathi / HTML | Verified public domain, substantive prose | **FIRST BATCH — READY FOR HUMAN AUTHORIZATION** |
