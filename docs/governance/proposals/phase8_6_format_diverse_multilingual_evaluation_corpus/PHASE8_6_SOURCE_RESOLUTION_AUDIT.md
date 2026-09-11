# Mnemo Phase 8.6 — Source Resolution / Acquisition-Path Governance Audit
**Document ID:** `mnemo.phase9-source-resolution-audit.v1`  
**Path:** `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/PHASE8_6_SOURCE_RESOLUTION_AUDIT.md`  
**Date:** September 2, 2026  
**Auditor:** Mnemo Architecture & Governance Assurance Agent  
**Operational Scope:** Fail-Closed Source Resolution Audit (Zero Downloads • Zero Ingestion • Zero Corpus Creation • Zero Evaluation)

---

## 1. Important Governance Notice & Immutability Affirmation

```text
================================================================================
CRITICAL GOVERNANCE INVARIANT ENFORCEMENT:
1. "Zero corpus documents were downloaded, scraped, or acquired."
2. "Zero third-party mirrors, unauthorized re-uploads, or ad-hoc aggregators
   were consulted or accepted as substitutes (Rule 3 strictly enforced)."
3. "Zero multi-page HTML assemblies, format conversions, or synthetic documents
   were constructed (Rule 4 and Rule 5 strictly enforced)."
4. "Phase 8.6 Corpus Ingestion: NOT EXECUTED."
5. "Phase 8.6 Indexing / Vectorization: NOT EXECUTED."
6. "Phase 8.6 Evaluation / QREL Creation: NOT EXECUTED."
7. "Phase 8.5 Golden Corpus: 100% PERMANENTLY FROZEN (Hash Verified)."
8. "Phase 8.5 V2 Database, Generations & Aliases: 100% UNTOUCHED."
================================================================================
```

---

## 2. Executive Determination

### **`PHASE 8.6 SOURCE RESOLUTION = AUDIT COMPLETE — GOVERNANCE ACTION REQUIRED`**

Following the halt of the authorized acquisition attempt, an exhaustive, fail-closed governance audit was conducted to determine whether each of the 10 approved Phase 8.6 works possesses a legitimate, policy-compliant acquisition artifact path.

### Summary Findings:
- **`RESOLVED_FOR_HUMAN_ACQUISITION_APPROVAL`:** **0 Candidates**  
  No candidate currently has a verified, static, single-file direct download URL that functions out-of-the-box without requiring human specification of underlying endpoints, authorization of multi-file archives, or policy amendments.
- **`GOVERNANCE_REVIEW_REQUIRED`:** **4 Candidates** (`CAND-HI-02`, `CAND-HI-05`, `CAND-MR-01`, `CAND-MR-02`)  
  These candidates belong to confirmed authoritative government bodies (Legislative Department, NCERT, Balbharati, Gazetteers Department), but the approved source URLs are interactive front-end portals (Next.js SPAs, session forms, or ASP.NET catalogs). Concrete direct document artifacts exist within these institutions, but their exact binary endpoints or archive extraction policies require explicit human governance approval.
- **`SOURCE_RESOLUTION_FAILED`:** **6 Candidates** (`CAND-HI-01`, `CAND-HI-03`, `CAND-HI-04`, `CAND-MR-03`, `CAND-MR-04`, `CAND-MR-05`)  
  - **Wikisource Works (`CAND-HI-03`, `CAND-HI-04`, `CAND-MR-04`):** MediaWiki hosts these works as collections of 15 to 36 separate wiki subpages. Official RESTBase PDF endpoints only export the root index page (280 KB) rather than transcluding the work. Toolforge WS-Export is an interactive community tool protected by bot challenges. Manual scraping, concatenation, and HTML-to-PDF conversion are strictly forbidden by Phase 8.6 rules.
  - **Missing / Moved Official Endpoints (`CAND-HI-01`, `CAND-MR-03`, `CAND-MR-05`):** `CAND-HI-01` (NEP 2020) returns HTTP 404 following Ministry CMS migration; `CAND-MR-03` (*Dasbodh*) does not exist as a complete standalone work on Marathi Wikisource; and `CAND-MR-05` (Economic Survey) fails DNS resolution. Under Rule 3, third-party mirrors cannot be substituted.

---

## 3. Candidate-by-Candidate Resolution Matrix

| Candidate ID | Approved Title | Approved Authority | Approved Source URL | Acquisition Path Status | Proposed Artifact Type | Requires Assembly | Policy Compliant | Primary Governance Issue |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **CAND-HI-01** | National Education Policy 2020 | Ministry of Education, GoI | `education.gov.in/sites/upload_files/...` | **`SOURCE_RESOLUTION_FAILED`** | `PDF` | No | No | Approved official URL returns HTTP 404. Third-party mirrors forbidden. |
| **CAND-HI-02** | Constitution of India (Hindi) | Legislative Dept, Ministry of Law, GoI | `legislative.gov.in/constitution-of-india/` | **`GOVERNANCE_REVIEW_REQUIRED`** | `PDF` | No | Yes | Dynamic Next.js portal shell. Requires human specification of direct PDF endpoint. |
| **CAND-HI-03** | *Godan* by Munshi Premchand | Wikisource / Saraswati Press | `hi.wikisource.org/wiki/गोदान` | **`SOURCE_RESOLUTION_FAILED`** | `WIKITEXT_SUBPAGES` | **Yes** | **No** | Split across 36 subpages. RESTBase only exports 280 KB index. Scraping/assembly forbidden. |
| **CAND-HI-04** | *Chintamani* by Acharya R. Shukla | Wikisource / Nagari Pracharini Sabha | `hi.wikisource.org/wiki/चिंतामणि` | **`SOURCE_RESOLUTION_FAILED`** | `WIKITEXT_SUBPAGES` | **Yes** | **No** | Approved URL 404 (spelled 'चिन्तामणि'). Split across 15 subpages. Manual assembly forbidden. |
| **CAND-HI-05** | NCERT Class 10 World History | NCERT, Ministry of Education, GoI | `ncert.nic.in/textbook.php` | **`GOVERNANCE_REVIEW_REQUIRED`** | `ZIP_PDF_BUNDLE` | No | Yes | Interactive PHP form. Downloads packaged as official chapter zip archives (`jhss1dd.zip`). |
| **CAND-MR-01** | *Kumarbharati* Class 10 | Balbharati, Pune (Textbook Bureau) | `ebalbharati.in` | **`GOVERNANCE_REVIEW_REQUIRED`** | `PDF` | No | Yes | Portal gateway. Textbooks reside in BalBooks ASP.NET catalog. Requires exact PDF link. |
| **CAND-MR-02** | Maharashtra State Gazetteer History | Gazetteers Department, GoM | `gazetteers.maharashtra.gov.in` | **`GOVERNANCE_REVIEW_REQUIRED`** | `PDF` | No | Yes | Departmental portal. Contains dozens of volumes; human selection of target volume required. |
| **CAND-MR-03** | *Dasbodh* by Samarth Ramdas | Marathi Wikisource | `mr.wikisource.org/wiki/दासबोध` | **`SOURCE_RESOLUTION_FAILED`** | `N/A` | **Yes** | **No** | Approved URL 404. Complete text absent on Marathi Wikisource. Mirrors forbidden. |
| **CAND-MR-04** | *Shetkaryacha Asud* by J. Phule | State Literature Board / Wikisource | `mr.wikisource.org/wiki/महात्मा_फुले...` | **`SOURCE_RESOLUTION_FAILED`** | `WIKITEXT_SUBPAGES` | **Yes** | **No** | Approved URL 404. Split across 17 wiki pages. Manual scraping/assembly forbidden. |
| **CAND-MR-05** | Economic Survey of Maharashtra | Directorate of Economics & Statistics | `des.maharashtra.gov.in` | **`SOURCE_RESOLUTION_FAILED`** | `PDF` | No | No | Domain fails DNS resolution. Host migrated to state network. Unapproved switch forbidden. |

---

## 4. Forensic Analysis by Source Category

### A. Wikisource Works (`CAND-HI-03`, `CAND-HI-04`, `CAND-MR-04`)
1. **The Structural Architecture of Wikisource:**
   - Works on Wikisource are structured using the MediaWiki *ProofreadPage* extension, which stores pages as individual subpages referencing underlying DjVu/PDF scans.
   - For example, *Godan* (`CAND-HI-03`) is transcluded across 36 discrete URLs (`गो-दान/१` through `गो-दान/३६`). *Chintamani* (`CAND-HI-04`) is indexed under `चिन्तामणि` and segmented across 15 essay subpages. *Shetkaryacha Asud* (`CAND-MR-04`) is divided across 17 individual page transcriptions (`शेतकऱ्याचा असूड/पान १` to `१७`).
2. **Platform Export Investigation:**
   - **Wikimedia RESTBase PDF API (`/api/rest_v1/page/pdf/{title}`):** Evaluated directly. When requested for `गो-दान`, the endpoint returns HTTP 200 with an `application/pdf` of exactly **280,536 bytes (~280 KB)**. Forensic header inspection confirmed this generates a PDF of **only the single root wiki page**, containing the table of contents and template transclusion tags, **NOT the 36 substantive chapters**.
   - **Toolforge WS-Export (`ws-export.wmcloud.org`):** Evaluated directly. The tool returned HTTP 200 but rendered an interactive Proof-of-Work / bot challenge page (*"Making sure you're not a bot!"*). WS-Export is an external community utility that executes client-side page traversing and HTML stitching.
3. **Policy Determination under Sections 3 and 5:**
   - Section 3 strictly forbids: *"HTML scraping, OCR scraping, manually concatenating Wikisource pages, converting HTML into PDF/text, or synthetic reconstruction."*
   - Section 5 mandates: *"Explicitly distinguish a legitimate platform-provided export of the complete work from manually fetching individual page/chapter HTML and constructing a new document. If the platform's available export still does not provide a provenance-preserving single artifact under current policy, mark the candidate blocked."*
   - **Conclusion:** Wikisource does not provide an immutable, single-file official artifact download for these multi-chapter works under current policy.

### B. Government Portal Endpoints (`CAND-HI-02`, `CAND-HI-05`, `CAND-MR-01`, `CAND-MR-02`)
1. **Interactive Portal vs. Static File URL:**
   - The approved URLs for these candidates point to web portal entry points:
     - `CAND-HI-02` (`https://legislative.gov.in/constitution-of-india/`) renders a client-side Next.js shell where documents are viewed via an interactive viewer.
     - `CAND-HI-05` (`https://ncert.nic.in/textbook.php`) is a PHP session-based selection form.
     - `CAND-MR-01` (`https://ebalbharati.in`) is the textbook bureau portal gateway.
     - `CAND-MR-02` (`https://gazetteers.maharashtra.gov.in`) is the departmental index.
2. **Technical Feasibility:**
   - In all four cases, the publisher/authority is verified and authentic.
   - For NCERT (`CAND-HI-05`), textbooks are officially packaged into chapter zip bundles (e.g. `jhss1dd.zip` containing the complete 5 chapters in Hindi).
   - For Legislative Department (`CAND-HI-02`), Balbharati (`CAND-MR-01`), and Gazetteers (`CAND-MR-02`), specific direct static PDF files exist on the infrastructure, but their exact binary paths are dynamic or require navigating catalog parameters.
3. **Governance Resolution:**
   - These 4 candidates do NOT suffer from source failure or missing works. They merely require human governance to ratify the direct binary link or archive extraction protocol rather than relying on portal root URLs.

### C. Failed Official Endpoints (`CAND-HI-01`, `CAND-MR-03`, `CAND-MR-05`)
1. **`CAND-HI-01` (NEP 2020 Hindi):** The Ministry of Education reorganized its site structure. The old path returns 404, and the new portal renders content dynamically. While third-party university mirrors exist, Rule 3 strictly forbids using unapproved mirrors.
2. **`CAND-MR-03` (*Dasbodh*):** Forensic search of Marathi Wikisource confirmed that *Dasbodh* does not exist as a complete work on the platform (only selected prayer verses exist in `नित्यनेमावली`). Rule 3 forbids substituting random blog or religious website PDFs.
3. **`CAND-MR-05` (Economic Survey):** `des.maharashtra.gov.in` fails DNS resolution. While the Government of Maharashtra has migrated departments to updated subdomains (e.g. `mahades.maharashtra.gov.in`), Rule 3 forbids automated domain switching without human approval.

---

## 5. Explicit List of Unacceptable Acquisition Paths

The following paths were evaluated and rejected as **strictly forbidden** under repository governance:

1. **Third-Party PDF Mirror Downloads:** Downloading government documents (NEP 2020, Constitution, Economic Survey) from educational aggregators, state university portals, Scribd, or SlideShare is **FORBIDDEN**.
2. **Internet Archive Scans as Official Substitutes:** Using arbitrary historical scans uploaded by anonymous users on `archive.org` as substitutes for official government publications is **FORBIDDEN**.
3. **MediaWiki Subpage HTML Scraping:** Writing custom scripts to download 36 individual HTML pages from Wikisource and concatenating them into a `.txt` or `.html` file is **FORBIDDEN**.
4. **Synthetic PDF Generation:** Rendering web pages through headless Chromium / Weasyprint / wkhtmltopdf to create artificial PDF files is **FORBIDDEN**.
5. **Silent Edition / Title Substitution:** Substituting partial excerpts or alternate editions without explicit human governance authorization is **FORBIDDEN**.

---

## 6. Recommended Human Decisions Required Before Acquisition

To establish a legitimate, policy-compliant Phase 8.6 corpus, human governance must review and decide upon the following four governance items:

1. **Ratify Direct Government Binary Endpoints (`DEC-P8.6-17`):**  
   Authorize specific direct static URLs for `CAND-HI-02` (Constitution), `CAND-MR-01` (Balbharati Class 10), and `CAND-MR-02` (Gazetteer target volume).
2. **Authorize Multi-Chapter Archive Policy (`DEC-P8.6-18`):**  
   Authorize the ingestion of official multi-chapter zip bundles for NCERT (`CAND-HI-05`), establishing a governed extraction rule where chapter PDFs (`jhss101.pdf` to `jhss105.pdf`) are ingested as an atomic composite work.
3. **Adopt Governed Wikisource Acquisition Policy OR Authorize Institutional Editions (`DEC-P8.6-19`):**  
   For literary works (*Godan*, *Chintamani*, *Shetkaryacha Asud*), decide between:
   - **Option A (Institutional Repository Pivot):** Replace Wikisource with official digital editions from the **National Digital Library of India (NDLI)** or the **Maharashtra Rajya Sahitya ani Sanskruti Mandal**; OR
   - **Option B (Governed Platform Compilation Protocol):** Establish a formal, governed MediaWiki API assembly protocol that extracts all official subpages, verifies revision IDs and cryptographic digests, and records full chapter-by-chapter provenance without manual heuristic alteration.
4. **Resolve Defunct URLs (`DEC-P8.6-20`):**  
   Formally approve updated official URLs for `CAND-HI-01` (Ministry of Education / NIC portal) and `CAND-MR-05` (`mahades.maharashtra.gov.in`), and select a vetted authoritative repository for *Dasbodh* (`CAND-MR-03`).

---

## 7. Protected Repository State Affirmation

Cryptographic verification performed before and after this audit confirms that all repository protected assets remain 100% bit-for-bit identical:
- **`manuscript.pdf`:** `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` (**MATCH**)
- **`Valmiki Ramayana...pdf`:** `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` (**MATCH**)
- **`mnemo.db`:** `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` (**MATCH**)
- **`Active Alias Digest`:** `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` (**MATCH**)
- **Golden Corpus Files:** Exactly 44 files preserved bit-for-bit.
- **Evaluation Dataset:** Zero external document files added.
- **Corpus Ingestion:** **FALSE** (Zero files ingested).
- **Corpus Indexing:** **FALSE** (Zero vectors created).
- **Evaluation Execution:** **FALSE** (Zero retrieval queries executed).
- **QRELs Created:** **FALSE** (Zero judgments created).

---

## 8. Final Governance Status Declaration

```text
================================================================================
FINAL GOVERNANCE REPOSITORY STATUS:
PHASE 8.6 SOURCE RESOLUTION = AUDIT COMPLETE — GOVERNANCE ACTION REQUIRED

PHASE 8.6 DOCUMENT ACQUISITION = NOT EXECUTED
PHASE 8.6 INGESTION = NOT EXECUTED
PHASE 8.6 INDEXING = NOT EXECUTED
PHASE 8.6 EVALUATION = NOT EXECUTED
PHASE 8.6 QREL = NOT EXECUTED

PHASE 8.5 GOLDEN CORPUS = FROZEN (Hash Verified)
PHASE 8.5 V2 DATABASE = FROZEN (Hash Verified)
================================================================================
```
