# PHASE 8.6 — CONTROLLED ACQUISITION & FORENSIC REPORT (BATCH 1)

**Classification:** GOVERNANCE AUDIT & FORENSIC VERIFICATION REPORT  
**Date:** 2026-09-03  
**Status:** **CONTROLLED ACQUISITION COMPLETE — ADMISSION GATED**  
**Phase:** Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus  
**Protected Hash Register Status:** **VERIFIED UNCHANGED (BIT-FOR-BIT IDENTICAL)**  

---

## 1. EXECUTIVE SUMMARY & GOVERNANCE COMPLIANCE

Under explicit human authorization, the First Batch of authentic multilingual HTML sources was acquired:
1. **`CAND-FD-HI-HTML-01`**: Munshi Premchand — *Godan (Chapter 1)* (*गोदान/ भाग 1*)
2. **`CAND-FD-MR-HTML-01`**: Mahatma Jotirao Phule — *Shetkaryacha Asud (Pan 1)* (*शेतकऱ्याचा असूड/पान १*)

Both artifacts were retrieved directly as raw, unmodified W3C-compliant Parsoid HTML5 documents via the official Wikimedia Core REST API v1.

### Governance Status Lifecycle Progression:
- **`CAND-FD-HI-HTML-01`**: `AUTHORIZED` → `ACQUIRED` → `FORENSICALLY VERIFIED` → **`ADMITTED = FALSE`**
- **`CAND-FD-MR-HTML-01`**: `AUTHORIZED` → `ACQUIRED` → `FORENSICALLY VERIFIED` → **`ADMITTED = FALSE`**
- **`CAND-FD-MR-PDF-01`**: `ACQUIRED` → `FORENSICALLY INSPECTED` → `LANGUAGE MISMATCH` → **`ADMITTED = FALSE`**
- **`CAND-FD-HI-PDF-01`**: `AUTHORIZED` → `TOKEN-GATED ENDPOINT` → **`NOT ACQUIRED`**

### System Protection Affirmation:
- **EXTRACTION = FALSE**
- **INGESTION = FALSE**
- **CHUNKING = FALSE**
- **INDEXING = FALSE**
- **EMBEDDING = FALSE**
- **QREL CREATION = FALSE**
- **EVALUATION = FALSE**
- **PHASE 8.5 GOLDEN CORPUS = UNCHANGED / FROZEN**
- **V2 RUNTIME (mnemo.db) = UNCHANGED / FROZEN**

---

## 2. PROTECTED ARTIFACT VERIFICATION (BEFORE & AFTER ACQUISITION)

Authoritative verification was performed immediately before and after acquisition using `scratch/verify_phase8_5_protected.py`:

| Protected Asset | Canonical Authority / Path | Pre-Acquisition SHA-256 | Post-Acquisition SHA-256 | Forensic Verdict |
| :--- | :--- | :--- | :--- | :---: |
| `manuscript.pdf` | `tests/fixtures/multilingual/manuscript.pdf` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` | **IDENTICAL (PASS)** |
| `Ramayana PDF` | `evaluationDataset/Valmiki-Ramayana-Gita-Press/Ramayana.pdf` | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` | **IDENTICAL (PASS)** |
| `mnemo.db` | `data/mnemo.db` (V2 Production DB) | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | **IDENTICAL (PASS)** |
| V2 Alias-Set Digest | Active Multilingual Model Alias-Set | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` | **IDENTICAL (PASS)** |
| Database Schema | V2 Production Table Registry (19 tables) | 19 Verified Tables | 19 Verified Tables | **UNMODIFIED (PASS)** |

---

## 3. ACQUISITION RECORD 1: `CAND-FD-HI-HTML-01` (Godan)

### 3.1 Provenance and Acquisition Metadata

| Attribute | Verified Value |
| :--- | :--- |
| **Candidate ID** | `CAND-FD-HI-HTML-01` |
| **Source Title** | *गोदान (अध्याय १)* (Godan Chapter 1) by Munshi Premchand |
| **Publisher / Repository**| Hindi Wikisource / Wikimedia Foundation |
| **Target Language / Script**| Hindi (`hi`) / Devanagari (`Deva`) |
| **Target Format** | HTML (`text/html`) |
| **Source Endpoint** | `https://hi.wikisource.org/w/rest.php/v1/page/%E0%A4%97%E0%A5%8B%E0%A4%A6%E0%A4%BE%E0%A4%A8%2F_%E0%A4%AD%E0%A4%BE%E0%A4%97_1/html` |
| **Final URL** | `https://hi.wikisource.org/w/rest.php/v1/page/%E0%A4%97%E0%A5%8B%E0%A4%A6%E0%A4%BE%E0%A4%A8%2F_%E0%A4%AD%E0%A4%BE%E0%A4%97_1/html` |
| **HTTP Status Code** | `200 OK` |
| **Response Content-Type** | `text/html; charset=utf-8; profile="https://www.mediawiki.org/wiki/Specs/HTML/2.8.0"` |
| **Retrieval Method** | HTTP GET / Wikimedia Core REST API v1 |
| **Acquisition Timestamp** | `2026-09-02T20:49:15Z` |
| **Local File Path** | `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/CAND-FD-HI-HTML-01-godan.html` |
| **Byte Size** | `57,029 bytes` |
| **SHA-256** | `9ec8a82b8795c1c09261a0f862e76f7319b1adde64ac5d02079bf9b3fa397a0f` |
| **MD5** | `08d496d7970608ea99537eaca3744f57` |
| **Licensing Evidence** | Public Domain under Section 22 of the Indian Copyright Act 1957; dual-licensed Creative Commons CC BY-SA 4.0. |

### 3.2 Content-Identity Forensics & Linguistic Verification

Read-only forensic inspection of the file on disk confirmed:
- **Title Tag:** `<title>गो-दान/१</title>`
- **Total Extracted Characters:** 15,473
- **Devanagari Characters:** **11,817 (76.37%)**
- **Latin Characters:** **0 (0.00%)**
- **Word Count:** 3,210 words
- **Paragraphs (`<p>` tags):** 56
- **Linguistic Markers:**
  - Character names: `होरी` (31 occurrences), `धनिया` (8 occurrences), `गोबर` (6 occurrences).
  - Auxiliary verbs: `है` (102), `था` (52), `थी` (35), `थे` (10).
  - Hindi postpositions: `ने` (113), `से` (122), `को` (59), `का/के/की` (267).
- **Parser Compatibility:** Successfully verified against `HTMLParser` (`ParserInterfaceV2`), generating 55 native `RawTextBlock` entries with zero errors.
- **Anomalies:** None. Zero synthetic conversions, zero translation artifacts.

---

## 4. ACQUISITION RECORD 2: `CAND-FD-MR-HTML-01` (Shetkaryacha Asud)

### 4.1 Provenance and Acquisition Metadata

| Attribute | Verified Value |
| :--- | :--- |
| **Candidate ID** | `CAND-FD-MR-HTML-01` |
| **Source Title** | *शेतकऱ्याचा असूड (पान १)* (Shetkaryacha Asud Pan 1) by Mahatma Jotirao Phule |
| **Publisher / Repository**| Marathi Wikisource / Wikimedia Foundation |
| **Target Language / Script**| Marathi (`mr`) / Devanagari (`Deva`) |
| **Target Format** | HTML (`text/html`) |
| **Source Endpoint** | `https://mr.wikisource.org/w/rest.php/v1/page/%E0%A4%B6%E0%A5%87%E0%A4%A4%E0%A4%95%E0%A4%B1%E0%A5%8D%E0%A4%AF%E0%A4%BE%E0%A4%9A%E0%A4%BE_%E0%A4%85%E0%A4%B8%E0%A5%82%E0%A4%A1%2F%E0%A4%AA%E0%A4%BE%E0%A4%A8_%E0%A5%A7/html` |
| **Final URL** | `https://mr.wikisource.org/w/rest.php/v1/page/%E0%A4%B6%E0%A5%87%E0%A4%A4%E0%A4%95%E0%A4%B1%E0%A5%8D%E0%A4%AF%E0%A4%BE%E0%A4%9A%E0%A4%BE_%E0%A4%85%E0%A4%B8%E0%A5%82%E0%A4%A1%2F%E0%A4%AA%E0%A4%BE%E0%A4%A8_%E0%A5%A7/html` |
| **HTTP Status Code** | `200 OK` |
| **Response Content-Type** | `text/html; charset=utf-8; profile="https://www.mediawiki.org/wiki/Specs/HTML/2.8.0"` |
| **Retrieval Method** | HTTP GET / Wikimedia Core REST API v1 |
| **Acquisition Timestamp** | `2026-09-02T20:49:22Z` |
| **Local File Path** | `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/CAND-FD-MR-HTML-01-shetkaryacha-asud.html` |
| **Byte Size** | `57,087 bytes` |
| **SHA-256** | `e0212854739433ca78b0fb12a855fb809476db2589af49f0509b3a56f9eff01d` |
| **MD5** | `1e06ff2c840a1d55934d22a6adcbecc2` |
| **Licensing Evidence** | Public Domain (historical 1883 publication); dual-licensed Creative Commons CC BY-SA 4.0. |

### 4.2 Content-Identity Forensics & Linguistic Verification

Read-only forensic inspection of the file on disk confirmed:
- **Title Tag:** `<title>शेतकऱ्याचा असूड/पान १</title>`
- **Total Extracted Characters:** 18,227
- **Devanagari Characters:** **15,524 (85.17%)**
- **Latin Characters:** **0 (0.00%)**
- **Word Count:** 2,369 words
- **Paragraphs (`<p>` tags):** 10
- **Linguistic Markers:**
  - Key vocabulary: `शेतकरी` (6), `शेतकर्‍यांस` (10), `ब्राह्यण` (14), `कामगारांचें` (2), `प्राबल्य` (2).
  - Marathi grammatical markers: `करून` (30), `नाहीं` (12), `म्हणून` (6), `त्यांनी` (4), `आहे/होता` (7).
- **Parser Compatibility:** Successfully verified against `HTMLParser` (`ParserInterfaceV2`), generating 11 native `RawTextBlock` entries with zero errors.
- **Anomalies:** None. Zero synthetic conversions, zero translation artifacts.

---

## 5. SUMMARY OF ACQUIRED ARTIFACTS ON DISK

```
Directory: evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/

1. CAND-FD-HI-HTML-01-godan.html
   Size:    57,029 bytes
   SHA-256: 9ec8a82b8795c1c09261a0f862e76f7319b1adde64ac5d02079bf9b3fa397a0f
   Status:  ACQUIRED — FORENSICALLY VERIFIED — ADMITTED = FALSE

2. CAND-FD-MR-HTML-01-shetkaryacha-asud.html
   Size:    57,087 bytes
   SHA-256: e0212854739433ca78b0fb12a855fb809476db2589af49f0509b3a56f9eff01d
   Status:  ACQUIRED — FORENSICALLY VERIFIED — ADMITTED = FALSE

3. dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf
   Size:    12,764,759 bytes
   SHA-256: a55e99f584ea0c1a5b9dece668c57e423c223a54dbcc0836ed683a6cb59345db
   Status:  PRESERVED FAILURE EVIDENCE — LANGUAGE MISMATCH — ADMITTED = FALSE

4. PHASE8_6_ACQUISITION_MANIFEST.proposed.json
   Size:    ~6.5 KB
   Status:  AUTHORITATIVE PROPOSED MANIFEST
```
