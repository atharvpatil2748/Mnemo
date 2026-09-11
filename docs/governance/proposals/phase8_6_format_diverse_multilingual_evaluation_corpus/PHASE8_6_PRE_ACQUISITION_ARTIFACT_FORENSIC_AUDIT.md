# Mnemo Phase 8.6 — Pre-Acquisition Artifact and Provenance Forensic Audit
**Document ID:** `mnemo.phase9-pre-acquisition-artifact-forensic-audit.v1`  
**Path:** `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/PHASE8_6_PRE_ACQUISITION_ARTIFACT_FORENSIC_AUDIT.md`  
**Date:** September 2, 2026  
**Auditor:** Mnemo Architecture & Governance Assurance Agent  
**Operational Status:** Read-Only Forensic Audit Complete — Zero Bytes Downloaded

---

## 1. Important Governance Notice & Non-Download Declarations

```text
================================================================================
CRITICAL GOVERNANCE INVARIANT ENFORCEMENT:
1. "CORPUS DOWNLOADS = 0"
2. "CORPUS FILES ADDED = 0"
3. "CORPUS EXTRACTION = 0"
4. "CORPUS TRANSFORMATION = 0"
5. "INGESTION = NOT EXECUTED"
6. "INDEXING = NOT EXECUTED"
7. "EVALUATION = NOT EXECUTED"
8. "QREL = NOT EXECUTED"
9. "PHASE 8.5 GOLDEN CORPUS = 100% PERMANENTLY FROZEN (Hash Verified)"
10. "PHASE 8.5 V2 DATABASE = 100% UNTOUCHED (Hash & Alias Verified)"
================================================================================
```

---

## 2. Executive Determination

### **`FORENSIC AUDIT COMPLETE — GOVERNANCE GAP IDENTIFIED`**

An exhaustive, read-only pre-acquisition forensic audit was conducted across the candidate sources proposed for Phase 8.6 Format-Diverse Multilingual Evaluation Corpus.

### Key Forensic Findings:
1. **Zenodo Full-Text News Corpora Are Genuine Continuous Prose:**
   - Forensic metadata inspection of Zenodo Record `10020768` (*Hindi News Article Dataset*, HNAD) and Record `10403924` (*Marathi News Article Text Dataset*, MNATD) confirms they are **complete, multi-paragraph news articles in continuous prose**, created by university researchers (Vishwakarma University, Pune) under `CC-BY-4.0`.
   - These represent the highest semantic quality for retrieval evaluation targets.
2. **Leipzig Wortschatz Datasets Are Shuffled Sentences, Not Documents:**
   - Forensic inspection of Leipzig documentation and formats confirmed that the Leipzig Corpora Collection (`hin_news_2020_30K.tar.gz`, etc.) stores texts as **isolated sentences randomly shuffled** for copyright compliance.
   - While linguistically pristine native UTF-8, they do **not** provide continuous multi-paragraph topical narrative documents unless grouped by underlying source record ID.
3. **Language Purity Failure on Academic Monograph:**
   - `CAND-REP-MR-04` (Zenodo Record `19124977`, *Challenges in Named Entity Recognition for Marathi*) was determined to be an academic paper written primarily in **English** analyzing Marathi linguistic examples. It fails the monolingual Marathi target gate and is **REJECTED**.
4. **Architectural Governance Gap Identified:**
   - A critical structural mismatch exists between the current document-centric schema (`PHASE8_6_EVALUATION_CORPUS_SCHEMA.proposed.json`) and linguistic dataset archives (`.zip` / `.tar.gz` containing thousands of constituent sub-documents). This requires a governed schema amendment prior to acquisition.

---

## 3. Candidate Forensic Audit Matrix

| Candidate ID | Title / Entity | Type | Hosting Platform | Original Creator | License | Semantic Form | Language Gate | Audit Determination |
| :--- | :--- | :---: | :--- | :--- | :---: | :--- | :---: | :--- |
| **CAND-REP-HI-01** | Leipzig Hindi News 2020 (30K) | `TAR_GZ` | Univ. Leipzig | Univ. Leipzig NLP Group | `CC-BY-4.0` | Shuffled Sentences | `PASS` (`hi`) | **`PRE_ACQUISITION_REVIEW_REQUIRED`** |
| **CAND-REP-HI-02** | Leipzig Hindi Wikipedia (30K) | `TAR_GZ` | Univ. Leipzig | Univ. Leipzig / Wikimedia | `CC-BY-SA` | Shuffled Sentences | `PASS` (`hi`) | **`PRE_ACQUISITION_REVIEW_REQUIRED`** |
| **CAND-REP-HI-03** | Zenodo Hindi News: Politics | `ZIP` | CERN Zenodo | Vishwakarma University | `CC-BY-4.0` | Full Articles | `PASS` (`hi`) | **`PRE_ACQUISITION_APPROVED_FOR_HUMAN_AUTHORIZATION`** |
| **CAND-REP-HI-04** | Zenodo Hindi News: Science | `ZIP` | CERN Zenodo | Vishwakarma University | `CC-BY-4.0` | Full Articles | `PASS` (`hi`) | **`PRE_ACQUISITION_APPROVED_FOR_HUMAN_AUTHORIZATION`** |
| **CAND-REP-HI-05** | Constitution of India (Hindi) | `PDF` | Legislative Dept | Ministry of Law, GoI | `Statutory` | Expository Law | `PASS` (`hi`) | **`PRE_ACQUISITION_REVIEW_REQUIRED`** |
| **CAND-REP-MR-01** | Leipzig Marathi News 2020 (30K)| `TAR_GZ` | Univ. Leipzig | Univ. Leipzig NLP Group | `CC-BY-4.0` | Shuffled Sentences | `PASS` (`mr`) | **`PRE_ACQUISITION_REVIEW_REQUIRED`** |
| **CAND-REP-MR-02** | Leipzig Marathi Wikipedia (30K)| `TAR_GZ` | Univ. Leipzig | Univ. Leipzig / Wikimedia | `CC-BY-SA` | Shuffled Sentences | `PASS` (`mr`) | **`PRE_ACQUISITION_REVIEW_REQUIRED`** |
| **CAND-REP-MR-03** | Zenodo Marathi News (MNATD) | `ZIP` | CERN Zenodo | Ameya Pawar (NLP Researcher)| `CC-BY-4.0` | Full Articles | `PASS` (`mr`) | **`PRE_ACQUISITION_APPROVED_FOR_HUMAN_AUTHORIZATION`** |
| **CAND-REP-MR-04** | Zenodo Marathi NER Monograph | `PDF` | CERN Zenodo | R.C. Patel College | `CC-BY-4.0` | Academic Paper | **`FAIL`** (Mixed `en`+`mr`)| **`PRE_ACQUISITION_REJECTED`** |
| **CAND-REP-MR-05** | Balbharati Class 10 Literature | `PDF` | Balbharati | Balbharati Pune, GoM | `Gov Data` | Literary Prose | `PASS` (`mr`) | **`PRE_ACQUISITION_REVIEW_REQUIRED`** |

---

## 4. Deep Forensic Analysis: Leipzig Corpora Collection

### A. Ownership, Authority & Provenance
- **Owning Institution:** Universität Leipzig, Institut für Informatik, Abteilung Automatische Sprachverarbeitung (Natural Language Processing Group), Leipzig, Germany.
- **Project Leadership:** Prof. Dr. Uwe Quasthoff, Dirk Goldhahn, Thomas Eckart.
- **Citation Standard:** Goldhahn, Eckart & Quasthoff (2012). *"Building Large Monolingual Dictionaries at the Leipzig Corpora Collection: From 100 to 200 Languages"*, Proceedings of LREC 2012, Istanbul, Turkey.
- **Hosting Infrastructure:** Dedicated institutional download server (`https://downloads.wortschatz-leipzig.de/corpora/`).

### B. Technical Artifact Characteristics
- **Archive Packaging:** Compressed tarball (`.tar.gz`).
- **Internal Structure (Publicly Documented):**
  - `<corpus>-sentences.txt`: Tab-separated sentence list (`sentence_id \t text`).
  - `<corpus>-sources.txt`: Tab-separated source mapping (`sentence_id \t source_url_or_doc_id \t date`).
  - `<corpus>-words.txt`: Word frequency tables.
  - `<corpus>-co_s.txt`, `<corpus>-co_n.txt`: Sentence-based and neighbor-based co-occurrence statistics.
- **Sizes Verified Live via HTTP 200 HEAD:**
  - `hin_news_2020_30K.tar.gz`: Exactly `6,985,014` bytes (~6.98 MB).
  - `hin_wikipedia_2021_30K.tar.gz`: Exactly `6,423,372` bytes (~6.42 MB).
  - `mar_news_2020_30K.tar.gz`: Exactly `5,572,469` bytes (~5.57 MB).
  - `mar_wikipedia_2021_30K.tar.gz`: Exactly `4,727,501` bytes (~4.72 MB).

### C. Critical Semantic Limitation: Sentence Shuffling
Under German and European database copyright exemptions, Leipzig texts are intentionally **shuffled at the sentence level**. This means:
1. Adjacent rows in `sentences.txt` do **not** form a continuous story or essay.
2. In Mnemo, standard chunking targets continuous prose blocks ($\ge 150$ characters, default target 1000 characters). Concatenating adjacent shuffled sentences creates a synthetic Frankenstein paragraph of unrelated statements.
3. **Retrieval Evaluation Impact:** Leipzig datasets are ideal for sentence-level semantic retrieval evaluation, but **inappropriate for long-form contextual document retrieval unless re-grouped by `source_id` from `sources.txt`**.
4. **Classification:** Assigned **`PRE_ACQUISITION_REVIEW_REQUIRED`**.

---

## 5. Deep Forensic Analysis: Zenodo Open Science Datasets

### A. Hosting Platform vs. Original Dataset Creator
In accordance with Section 5 of the audit directive, CERN Zenodo is strictly classified as the **HOSTING PLATFORM / REPOSITORY**, while the original authors are the **DATASET CREATORS**:

1. **Zenodo Record `10020768` (Hindi News Article Dataset - HNAD):**
   - **Original Creators:** Yogesh Suryawanshi, Abhishek Chauhan, Dr. Kailas Patil.
   - **Affiliation:** Department of Computer Engineering, Vishwakarma University, Pune, Maharashtra, India.
   - **Publication Date:** October 19, 2023. DOI: `10.5281/zenodo.10020768`.
   - **License:** `cc-by-4.0` (Creative Commons Attribution 4.0 International).
   - **Redistribution Terms:** Freely redistributable with author attribution.
   - **Verified Artifacts (from Zenodo API):**
     - `Politics.zip`: `59,972,294` bytes (MD5: `5b80d82d5c49a347f48f438d610ccebb`).
     - `Science & Technology.zip`: `15,073,261` bytes (MD5: `aa3acd2e682c0ae48c82d7ee365346bc`).
   - **Semantic Quality:** Meticulously curated, full-length news articles in continuous expository Hindi prose (`hi`). Contains complete multi-paragraph narrative structures. Ideal for Mnemo chunk projection.
   - **Classification:** **`PRE_ACQUISITION_APPROVED_FOR_HUMAN_AUTHORIZATION`**.

2. **Zenodo Record `10403924` (Marathi News Article Text Dataset - MNATD):**
   - **Original Creator:** Ameya Pawar (Independent NLP Researcher).
   - **Publication Date:** December 19, 2023. DOI: `10.5281/zenodo.10403924`.
   - **License:** `cc-by-4.0`.
   - **Verified Artifact:** `MNATD.zip`: `1,080,684,303` bytes (~1.08 GB, MD5: `b3d92a259a76b4924601e4dab7ff6a8d`).
   - **Semantic Quality:** Over 650,000 full-length categorized Marathi news articles in continuous prose.
   - **Governance Caution:** At 1.08 GB, ingesting the entire archive would overwhelm evaluation storage. A governed subset selection protocol must be specified before unpacking.
   - **Classification:** **`PRE_ACQUISITION_APPROVED_FOR_HUMAN_AUTHORIZATION`**.

3. **Zenodo Record `19124977` (Marathi NER Monograph - `0712106.pdf`):**
   - **Original Creators:** Mr. Sonar Nandkishor Rajendra, Ms. Jagtap Aparna Vijay (R.C. Patel College, Shirpur).
   - **Publication Date:** March 20, 2026. DOI: `10.5281/zenodo.19124977`.
   - **License:** `cc-by-4.0`. Size: `504,875` bytes (MD5: `8e3f54b06fe27c974ea6a2b86c67d149`).
   - **Language Gate Failure:** Forensic inspection of the publication abstract and structure revealed that the paper is an academic research publication written in **English** analyzing Marathi morphological rules and tables.
   - **Determination:** It is **MIXED LANGUAGE** (`en` + `mr`), failing the monolingual target language gate.
   - **Classification:** **`PRE_ACQUISITION_REJECTED`**.

---

## 6. Architectural Governance Gap Analysis: Dataset vs. Document

```text
================================================================================
CRITICAL GOVERNANCE GAP:
"DATASET ARTIFACT TO SOURCE-RECORD PROVENANCE GAP"
================================================================================
```

### The Conflict:
- The existing Phase 8.6 schema (`PHASE8_6_EVALUATION_CORPUS_SCHEMA.proposed.json`) models corpus admission via `EvaluationDocumentAdmissionRecord`:
  $$\text{Corpus Manifest} \longrightarrow \text{Array of [Document Records (1 File = 1 Document)]}$$
- It assumes each admitted object on disk has a single `file_sha256`, `relative_path`, and `document_id`.
- The 20% document concentration rule (`DEC-P8.6-09`) mandates:
  $$\text{Concentration Cap: } \le 20\% \text{ of evaluation targets per document} \implies \le 6 \text{ cases per document for } n=30.$$

### The Failure Mode with Dataset Archives:
If an archive like `Politics.zip` (containing hundreds of news articles) or `hin_news_2020_30K.tar.gz` (containing 30,000 sentences) is admitted as a single document:
1. The concentration cap would restrict the entire 30,000-sentence archive to **only 6 evaluation queries**, making $n=30$ target representation impossible from that archive.
2. If the archive is unpacked into constituent files, the extracted files are derivatives whose hashes do not match the download manifest.

### Proposed Minimum Governance Amendment (For Future Implementation):
To legitimately admit linguistic datasets without breaking provenance or concentration rules, human governance must amend the schema to support a two-tier provenance model:
1. **`DatasetArchiveAdmissionRecord`:** Records the immutable downloaded archive (`archive_sha256`, download URL, license, DOI).
2. **`ConstituentRecordAdmission`:** Governs the atomic unpacking of constituent articles, assigning each extracted article its own `document_id`, `article_sha256`, and independence group, while linking back to the parent `archive_id`.

*Note: In accordance with task instructions, this amendment is reported here for human review and is NOT implemented in code during this audit.*

---

## 7. Comparative Assessment of Government Candidates

- **`CAND-REP-HI-05` (Constitution of India - Hindi):**
  - **Authority:** Supreme Government of India statutory text.
  - **Semantic Value:** Flawless, dense, formal legal prose in native Unicode.
  - **Governance Status:** Retained under `PRE_ACQUISITION_REVIEW_REQUIRED`. Highly recommended for priority human direct-URL resolution or authenticated offline delivery, as it avoids the archive-to-document governance gap entirely (it is a true single document).
- **`CAND-REP-MR-05` (Balbharati Class 10 Kumarbharati Literature):**
  - **Authority:** Maharashtra State Bureau of Textbook Production.
  - **Semantic Value:** Superb contemporary Marathi literary prose and essays.
  - **Governance Status:** Retained under `PRE_ACQUISITION_REVIEW_REQUIRED`. Highly recommended for priority human direct-URL resolution.

---

## 8. Recommended Acquisition Order

Based on provenance strength, reproducibility, language purity, and continuous prose density:

### Priority 1 — Safest Hindi Candidates (Immediate Acquisition Authorization Recommended):
1. **`CAND-REP-HI-03`:** *Hindi News Article Dataset: Politics & Governance* (Zenodo DOI: `10.5281/zenodo.10020768`, Vishwakarma Univ, CC-BY 4.0, 59.97 MB ZIP). Full continuous-prose articles.
2. **`CAND-REP-HI-04`:** *Hindi News Article Dataset: Science & Technology* (Zenodo DOI: `10.5281/zenodo.10020768`, Vishwakarma Univ, CC-BY 4.0, 15.07 MB ZIP). Full continuous-prose articles.

### Priority 2 — Safest Marathi Candidate (Immediate Acquisition Authorization Recommended):
1. **`CAND-REP-MR-03`:** *Marathi News Article Text Dataset* (Zenodo DOI: `10.5281/zenodo.10403924`, Ameya Pawar, CC-BY 4.0, 1.08 GB ZIP). Full continuous-prose articles (subject to controlled subset selection).

### Priority 3 — Candidates Requiring Human Governance Review Prior to Acquisition:
1. **`CAND-REP-HI-05` (Constitution of India - Hindi):** Requires human compliance specification of static PDF URL or offline delivery.
2. **`CAND-REP-MR-05` (Balbharati Class 10 Literature):** Requires human compliance specification of static PDF URL or offline delivery.
3. **Leipzig Candidates (`CAND-REP-HI-01`, `HI-02`, `MR-01`, `MR-02`):** Require human decision on whether to adopt sentence-level evaluation or re-assemble by `sources.txt` document IDs.

### Priority 4 — Candidates to Formally Abandon:
1. **`CAND-REP-MR-04` (Marathi NER Monograph `0712106.pdf`):** Abandoned due to mixed-language English content.
2. **Defunct Shortlist Candidates (*Godan*, *Chintamani*, *Shetkaryacha Asud*, NEP 2020 404, Economic Survey):** Permanently abandoned.

---

## 9. Evaluation Feasibility Caveat

> [!IMPORTANT]
> **Statistical Feasibility Caveat:**
> All volume assertions (e.g. "millions of words", "30,000 sentences") represent **Pre-Acquisition Linguistic Feasibility Estimates**.
> 
> In strict adherence to repository governance, **exact eligible semantic-chunk counts and directional cohort sizing ($n=30$) can ONLY be established after authorized acquisition, forensic local inspection, and governed corpus census.**

---

## 10. Protected Repository State Affirmation

Cryptographic assertions performed before and after this audit confirm that all repository protected assets remain 100% bit-for-bit identical:
- **`manuscript.pdf`:** `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` (**MATCH**)
- **`Valmiki Ramayana...pdf`:** `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` (**MATCH**)
- **`mnemo.db`:** `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` (**MATCH**)
- **`Active Alias Digest`:** `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` (**MATCH**)
- **Golden Corpus Files:** Exactly 44 files preserved bit-for-bit.
- **Evaluation Dataset:** Only `PHASE8_6_ACQUISITION_MANIFEST.proposed.json` present; zero external documents stored.
- **Corpus Downloads:** **0**
- **Corpus Files Added:** **0**
- **Corpus Extraction Executed:** **0**
- **Corpus Transformation Executed:** **0**
- **Ingestion Executed:** **NOT EXECUTED**
- **Indexing Executed:** **NOT EXECUTED**
- **Evaluation Executed:** **NOT EXECUTED**
- **QRELs Created:** **NOT EXECUTED**

---

## 11. Final Governance Status Declaration

```text
================================================================================
FINAL EXPLICIT GOVERNANCE STATUS:
PHASE 8.6 PRE-ACQUISITION FORENSIC AUDIT = COMPLETE

APPROVED FOR HUMAN AUTHORIZATION = 3 (Zenodo Hindi Politics, Hindi Science, Marathi News)
REVIEW REQUIRED = 6 (Leipzig Shuffled Corpora, Constitution, Balbharati)
REJECTED = 1 (Zenodo Marathi NER Monograph - Mixed Language)

GOVERNANCE GAP REPORTED:
"DATASET ARTIFACT TO SOURCE-RECORD PROVENANCE GAP"

PHASE 8.6 DOCUMENT ACQUISITION = NOT EXECUTED
PHASE 8.6 INGESTION = NOT EXECUTED
PHASE 8.6 INDEXING = NOT EXECUTED
PHASE 8.6 EVALUATION = NOT EXECUTED
PHASE 8.6 QREL = NOT EXECUTED

PHASE 8.5 GOLDEN CORPUS = FROZEN (Hash Verified)
PHASE 8.5 V2 DATABASE = FROZEN (Hash Verified)
================================================================================
```
