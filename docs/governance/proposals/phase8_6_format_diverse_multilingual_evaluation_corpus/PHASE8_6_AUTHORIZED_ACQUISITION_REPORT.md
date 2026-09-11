# Mnemo Phase 8.6 — Authorized Corpus Acquisition Report
**Document ID:** `mnemo.phase9-authorized-acquisition-report.v1`  
**Path:** `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/PHASE8_6_AUTHORIZED_ACQUISITION_REPORT.md`  
**Date:** September 2, 2026  
**Auditor:** Mnemo Architecture & Governance Assurance Agent  
**Operational Status:** CRITICAL STOP CONDITION TRIGGERED — GOVERNANCE REVIEW REQUIRED  
**Execution Boundary:** Zero External Files Downloaded • Zero Files Ingested • Golden Corpus Frozen • V2 DB Frozen

---

## 1. Important Governance Notice & Non-Ingestion Declarations

```text
================================================================================
CRITICAL GOVERNANCE INVARIANT ENFORCEMENT:
1. "Zero unapproved substitute URLs or mirror websites were accessed."
2. "Zero format conversions, multi-page HTML assemblies, or synthetic
   re-encodings were performed (Rule 4 strict adherence)."
3. "Phase 8.6 Ingestion: NOT EXECUTED."
4. "Phase 8.6 Indexing: NOT EXECUTED."
5. "Phase 8.6 Evaluation: NOT EXECUTED."
6. "Phase 8.5 Golden Corpus: 100% PERMANENTLY FROZEN (Hash Verified)."
7. "Phase 8.5 V2 Database, Generations & Aliases: 100% UNTOUCHED."
================================================================================
```

---

## A. Executive Determination

### **`ACQUISITION BLOCKED — SOURCE/PROVENANCE FAILURE`**

In accordance with Phase 8.6 Authorized Corpus Acquisition governance:
1. **Rule 3 Prohibition on Substitution:** *"If the preferred source is unavailable, DO NOT automatically choose another source. Instead: STOP THAT CANDIDATE and report it for human decision."*
2. **Rule 4 Prohibition on Format Conversion:** *"Preserve the original bytes; do not edit; do not convert formats; do not assemble scrapes."*
3. **Rule 15 Critical Stop Condition:** *"STOP immediately if the approved source cannot be retrieved or an unapproved source is required. Do NOT solve failures by substitution."*

When acquisition was initiated across the 10 approved sources from their approved URLs, **zero documents could be retrieved as a single byte-exact downloadable artifact without either substituting unapproved third-party mirrors, resolving broken/moved government endpoints, or assembling fragmented multi-page HTML wiki chapters**:
- **4 Candidates Failed Directly (`ACQUISITION_FAILED`):** `CAND-HI-01` (HTTP 404 endpoint moved), `CAND-HI-04` (HTTP 404 URL spelling mismatch), `CAND-MR-03` (HTTP 404 absent on Marathi Wikisource), `CAND-MR-05` (DNS host resolution failure).
- **6 Candidates Require Human Governance Review (`GOVERNANCE_REVIEW_REQUIRED`):** `CAND-HI-02`, `CAND-HI-05`, `CAND-MR-01`, and `CAND-MR-02` point to interactive single-page web portals or form gateways rather than direct static document URLs; `CAND-HI-03` and `CAND-MR-04` point to multi-page wiki transcriptions split across 17 to 36 separate subpages rather than a unified immutable document file.

Rather than compromising repository governance by silently scraping third-party mirrors or converting web fragments into artificial PDFs, the engineering agent **HALTED ACQUISITION IMMEDIATELY** and submits this forensic report to human governance.

---

## B. Candidate Acquisition & Forensic Status Table

| Candidate ID | Approved Title | Acquired | SHA-256 | Size | Pages | Language | Script | Representation | Provenance | License Status | Forensic / Acquisition Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- | :---: |
| **CAND-HI-01** | National Education Policy 2020 | **NO** | `N/A` | `N/A` | `N/A` | `hi` | `Deva` | `NATIVE_UNICODE` | Ministry of Education | `GOVERNMENT_OPEN_DATA` | **`ACQUISITION_FAILED`** (404 Not Found) |
| **CAND-HI-02** | Constitution of India (Hindi) | **NO** | `N/A` | `N/A` | `N/A` | `hi` | `Deva` | `NATIVE_UNICODE` | Legislative Department | `PUBLIC_DOMAIN_INDICATION` | **`GOVERNANCE_REVIEW_REQUIRED`** (Portal Landing Page) |
| **CAND-HI-03** | *Godan* by Premchand | **NO** | `N/A` | `N/A` | `N/A` | `hi` | `Deva` | `NATIVE_UNICODE` | Wikisource / Saraswati | `CLEAR_OPEN_LICENSE` | **`GOVERNANCE_REVIEW_REQUIRED`** (Multi-Page Fragmented) |
| **CAND-HI-04** | *Chintamani* by R. Shukla | **NO** | `N/A` | `N/A` | `N/A` | `hi` | `Deva` | `NATIVE_UNICODE` | Wikisource / Nagari Prach. | `CLEAR_OPEN_LICENSE` | **`ACQUISITION_FAILED`** (404 / Alternate Title) |
| **CAND-HI-05** | NCERT Class 10 World History | **NO** | `N/A` | `N/A` | `N/A` | `hi` | `Deva` | `NATIVE_UNICODE` | NCERT, GoI | `GOVERNMENT_OPEN_DATA` | **`GOVERNANCE_REVIEW_REQUIRED`** (Interactive Form Portal) |
| **CAND-MR-01** | *Kumarbharati* Marathi Class 10 | **NO** | `N/A` | `N/A` | `N/A` | `mr` | `Deva` | `NATIVE_UNICODE` | Balbharati, Pune | `GOVERNMENT_OPEN_DATA` | **`GOVERNANCE_REVIEW_REQUIRED`** (Catalog Form Portal) |
| **CAND-MR-02** | Maharashtra State Gazetteer History | **NO** | `N/A` | `N/A` | `N/A` | `mr` | `Deva` | `NATIVE_UNICODE` | Gazetteers Department | `GOVERNMENT_OPEN_DATA` | **`GOVERNANCE_REVIEW_REQUIRED`** (Department Portal Page) |
| **CAND-MR-03** | *Dasbodh* by Samarth Ramdas | **NO** | `N/A` | `N/A` | `N/A` | `mr` | `Deva` | `NATIVE_UNICODE` | Marathi Wikisource | `CLEAR_OPEN_LICENSE` | **`ACQUISITION_FAILED`** (404 / Content Incomplete) |
| **CAND-MR-04** | *Shetkaryacha Asud* by J. Phule | **NO** | `N/A` | `N/A` | `N/A` | `mr` | `Deva` | `NATIVE_UNICODE` | State Literature Board | `CLEAR_OPEN_LICENSE` | **`ACQUISITION_FAILED`** (404 / 17 Page Scrapes) |
| **CAND-MR-05** | Maharashtra Economic Survey | **NO** | `N/A` | `N/A` | `N/A` | `mr` | `Deva` | `NATIVE_UNICODE` | Directorate of Economics | `GOVERNMENT_OPEN_DATA` | **`ACQUISITION_FAILED`** (DNS Unresolved) |

---

## C. Hindi Forensic Results

1. **`CAND-HI-01` (NEP 2020 Hindi):**
   - *Approved URL:* `https://www.education.gov.in/sites/upload_files/mhrd/files/NEP_Final_Hindi.pdf`
   - *Network Result:* HTTP 404 Not Found.
   - *Forensic Finding:* The Ministry of Education has restructured its upload paths, moving older static links into archived or re-indexed directories. Under Rule 3, no unapproved third-party mirror was accessed.
   - *Status:* `ACQUISITION_FAILED`.

2. **`CAND-HI-02` (Constitution of India - Hindi):**
   - *Approved URL:* `https://legislative.gov.in/constitution-of-india/`
   - *Network Result:* HTTP 200 (Next.js SPA Shell).
   - *Forensic Finding:* The URL points to an interactive single-page application shell rather than a direct downloadable PDF file. Direct PDF links are injected dynamically via JavaScript. Downloading the HTML shell yields zero document text.
   - *Status:* `GOVERNANCE_REVIEW_REQUIRED` (Specific direct PDF URL required).

3. **`CAND-HI-03` (*Godan* by Premchand):**
   - *Approved URL:* `https://hi.wikisource.org/wiki/गोदान`
   - *Network Result:* HTTP 200 (Wikitext Index).
   - *Forensic Finding:* The work is not hosted as a single text file or PDF, but is split across 36 separate wiki subpages (`गो-दान/१` through `गो-दान/३६`) referencing an underlying DjVu file (`गो-दान.djvu`). Ingesting HTML chapter scrapes violates Rule 4 (preserve original bytes without format conversion).
   - *Status:* `GOVERNANCE_REVIEW_REQUIRED` (Human decision required on whether to acquire the official DjVu/PDF image scan or authorize a single-file text compilation).

4. **`CAND-HI-04` (*Chintamani* by Acharya Ramchandra Shukla):**
   - *Approved URL:* `https://hi.wikisource.org/wiki/चिंतामणि`
   - *Network Result:* HTTP 404 Not Found.
   - *Forensic Finding:* On Hindi Wikisource, the title is cataloged under the spelling `चिन्तामणि` and segmented across 15 separate essay subpages. Rule 3 forbids automatic URL substitution.
   - *Status:* `ACQUISITION_FAILED`.

5. **`CAND-HI-05` (NCERT Class 10 World History):**
   - *Approved URL:* `https://ncert.nic.in/textbook.php`
   - *Network Result:* HTTP 200 (Interactive Form Gateway).
   - *Forensic Finding:* The approved URL is an interactive PHP form requiring session variables. Direct textbook chapter downloads require specific zip bundle endpoints (e.g. `jhess1dd.zip`).
   - *Status:* `GOVERNANCE_REVIEW_REQUIRED` (Direct zip bundle URL required).

---

## D. Marathi Forensic Results

1. **`CAND-MR-01` (*Kumarbharati* Marathi Class 10):**
   - *Approved URL:* `https://ebalbharati.in`
   - *Network Result:* HTTP 200 (Portal Gateway).
   - *Forensic Finding:* The URL is the main educational portal. Downloading specific textbook PDFs requires navigating through the ASP.NET cart portal (`cart.ebalbharati.in`).
   - *Status:* `GOVERNANCE_REVIEW_REQUIRED` (Direct textbook PDF URL required).

2. **`CAND-MR-02` (Maharashtra State Gazetteer: History & Culture):**
   - *Approved URL:* `https://gazetteers.maharashtra.gov.in`
   - *Network Result:* HTTP 200 (Department Portal).
   - *Forensic Finding:* The URL points to the departmental index. The Gazetteers series contains dozens of distinct volumes; human governance must specify the exact target volume filename.
   - *Status:* `GOVERNANCE_REVIEW_REQUIRED`.

3. **`CAND-MR-03` (*Dasbodh* by Samarth Ramdas):**
   - *Approved URL:* `https://mr.wikisource.org/wiki/दासबोध`
   - *Network Result:* HTTP 404 Not Found.
   - *Forensic Finding:* A full standalone text of *Dasbodh* does not exist on Marathi Wikisource; only isolated verses appear in prayer collections (`नित्यनेमावली`). Rule 3 forbids unapproved mirror substitution.
   - *Status:* `ACQUISITION_FAILED`.

4. **`CAND-MR-04` (*Shetkaryacha Asud* by Mahatma Jyotirao Phule):**
   - *Approved URL:* `https://mr.wikisource.org/wiki/महात्मा_फुले_समग्र_वाङ्मय`
   - *Network Result:* HTTP 404 Not Found.
   - *Forensic Finding:* On Marathi Wikisource, the work is indexed across 17 individual page transcriptions (`शेतकऱ्याचा असूड/पान १` to `१७`). Rule 3 and Rule 4 prohibit assembling multi-page web scrapes.
   - *Status:* `ACQUISITION_FAILED`.

5. **`CAND-MR-05` (Economic Survey of Maharashtra):**
   - *Approved URL:* `https://des.maharashtra.gov.in`
   - *Network Result:* DNS Resolution Failure (`getaddrinfo` error).
   - *Forensic Finding:* The host domain is unreachable or has migrated to state intranet / updated subdomains (`mahades.maharashtra.gov.in`).
   - *Status:* `ACQUISITION_FAILED`.

---

## E. Evidence Sufficiency Assessment

Because zero files were acquired as immutable documents in this step:
- **Eligible Chunk Yield:** Currently **0 chunks** in `evaluationDataset/`.
- **Governed Benchmark Readiness:** The planned 240-case / 270-case evaluation remains **BLOCKED BY HARD STOP** as established in Phase 8.5.
- **Scientific Integrity Preserved:** The repository successfully avoided admitting broken HTML fragments, unverified mirror copies, or synthesized text into the evaluation namespace.

---

## F. Governed Next Steps for Human Review

To unblock Phase 8.6 acquisition without compromising provenance:

1. **Review and Update Direct Download Endpoints:**
   Human governance must ratify an updated, byte-exact acquisition manifest specifying direct, static PDF/binary URLs rather than portal homepages.
2. **Decide on Wikisource Multi-Page Policy:**
   Human governance must decide whether literary works on Wikisource (e.g. *Godan*, *Chintamani*, *Shetkaryacha Asud*) should be:
   - Acquired via official Wikimedia API compilation into a standardized document record; OR
   - Replaced by curated digital editions from authoritative state or institutional repositories (e.g. National Digital Library of India).
3. **Approve Updated Acquisition Manifest:**
   Upon governance sign-off on direct URLs, acquisition can be re-executed under identical cryptographic controls.

---

## G. Protected Repository State Check

Before and after this task, all repository protected assets were verified bit-for-bit against their authoritative SHA-256 digests:
- **`manuscript.pdf`:** `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` (**MATCH**)
- **`Valmiki Ramayana...pdf`:** `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` (**MATCH**)
- **`mnemo.db`:** `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` (**MATCH**)
- **`Active Alias Digest`:** `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` (**MATCH**)
- **Golden Corpus Files:** Exactly 44 files preserved bit-for-bit.
- **Phase 8.6 Ingestion:** **FALSE** (Zero files ingested).
- **Phase 8.6 Indexing:** **FALSE** (Zero vectors or indexes built).
- **Phase 8.6 Evaluation:** **FALSE** (Zero queries run).
- **QRELs Created:** **FALSE** (Zero judgments recorded).
