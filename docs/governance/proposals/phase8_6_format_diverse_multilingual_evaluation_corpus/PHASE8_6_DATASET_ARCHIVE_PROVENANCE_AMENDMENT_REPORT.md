# Mnemo Phase 8.6 — Dataset Archive Provenance Amendment Report
**Document ID:** `mnemo.phase8_6.dataset-archive-provenance-amendment-report.v1`  
**Path:** `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/PHASE8_6_DATASET_ARCHIVE_PROVENANCE_AMENDMENT_REPORT.md`  
**Date:** September 2, 2026  
**Auditor:** Mnemo Architecture & Governance Assurance Agent  
**Status:** Read-Only Governance Amendment Complete — Zero Corpus Bytes Downloaded

---

## 1. Important Governance Notice & Invariant Affirmation

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

## 2. Existing Schema Gap Analysis

During the Phase 8.6 Pre-Acquisition Forensic Audit, a structural limitation was identified in `PHASE8_6_EVALUATION_CORPUS_SCHEMA.proposed.json`:

1. **Document-Centric Monolithic Assumption:**
   The schema required that every admitted entity be an `EvaluationDocumentAdmissionRecord`, which explicitly mandates:
   - `relative_path` pointing to a single file on disk;
   - `file_sha256` capturing the hash of that single file;
   - `document_id` representing the single document;
   - An expectation that chunk projections derive directly from that single file.

2. **The Impedance Mismatch with Modern Linguistic Repositories:**
   High-quality multilingual corpora published on platforms like CERN Zenodo (e.g. *Hindi News Article Dataset*, DOI `10.5281/zenodo.10020768`) are distributed as container archives (`.zip` or `.tar.gz`) packaging hundreds or thousands of complete, individual articles.
   
3. **The Two Flawed Alternatives Under the Unamended Schema:**
   - **Alternative A (Treat Archive as One Document):** If `Politics.zip` is admitted as a single document, the **20% document concentration cap (`DEC-P8.6-09`)** restricts the entire 1,000-article archive to a maximum of **6 evaluation targets** in an $n=30$ cohort. This would prevent diverse sampling across articles.
   - **Alternative B (Unpack into Files Without Lineage):** If the archive is unpacked into raw text files and each file is admitted independently, the cryptographic link to the parent archive hash (`archive_sha256`), download URL, and DOI is severed. Each file would look like an ad-hoc local creation rather than an authoritative download.

---

## 3. The Two-Tier Provenance Model

This amendment introduces a formal **Two-Tier Provenance Hierarchy**:

```text
================================================================================
TIER 1: IMMUTABLE DATASET ARCHIVE
   Artifact: Downloaded container bitstream (e.g. Politics.zip, 59.97 MB)
   Identity: archive_id (UUID)
   Integrity: archive_sha256 (Bit-exact match to remote server)
   Attribution: DOI (10.5281/zenodo.10020768), hosting_platform, original_creator
   Governance: Immutable, preserved permanently in acquisition cache.

          │
          ▼  [Governed Deterministic Unpacking]

TIER 2: CONSTITUENT SOURCE RECORD
   Artifact: Extracted discrete article/document
   Identity: source_record_id (UUID), document_id (UUID)
   Integrity: source_content_hash (SHA-256 of extracted content)
   Lineage: parent_archive_id (Foreign Key -> archive_id)
   Locator: source_locator (e.g. "Politics/article_0042.txt")
   Governance: Ingested into Mnemo evaluation storage; generates canonical chunks.
================================================================================
```

---

## 4. Cryptographic Lineage & Verifiability

To ensure end-to-end cryptographic integrity:

1. **Independent Cryptographic Identities:**  
   The archive hash (`archive_sha256`) and constituent content hash (`source_content_hash`) are distinct. Under no circumstances is `archive_sha256` equated to `source_content_hash`.
2. **Determinism:**  
   Unpacking the archive with standard tools must deterministically reproduce the identical `source_content_hash` for every constituent record.
3. **Audit Trail:**  
   Any evaluation query target in QREL can be audited from the evidence row all the way back to the remote Zenodo deposit:
   $$\text{QREL Target} \longrightarrow \text{Chunk ID} \longrightarrow \text{Document ID} \longrightarrow \text{Constituent Record} \longrightarrow \text{Parent Archive ID} \longrightarrow \text{Zenodo DOI}$$

---

## 5. Source Locator Semantics

The `source_locator` field in `ConstituentSourceRecord` provides the precise, unambiguous address of the constituent content within the parent container:
- **For ZIP Archives (Zenodo):** The normalized relative internal file path (e.g. `Politics/article_0128.txt`).
- **For TAR Archives (Leipzig):** The relative internal path and, if sentence-clustered, line number range (e.g. `hin_news_2020_30K-sentences.txt:L1024-1050`).
- **Standardization:** All locators use forward slashes (`/`), lowercase extensions, and UTF-8 encoding.

---

## 6. Independence Grouping & Concentration-Control Interpretation (`DEC-P8.6-09` Clarification)

### A. Resolution & Two-Level Concentration Evaluation:
To prevent benchmark concentration within any single document or dataset ecosystem, the concentration-control rule is evaluated at **BOTH**:

1. **Constituent Source Document / Record Level:**
   - In an evaluation cohort of size $n=30$, no single constituent source document or article may contribute more than 6 evaluation targets ($\le 20\%$).
2. **Parent Dataset / Independence-Group Level:**
   - Concentration is tracked at the parent dataset archive and `independence_group_id` level to ensure that evaluation targets are not excessively concentrated within one dataset ecosystem, narrow topical event, or publishing author.
   - If a specific numerical cap at the dataset archive level is required beyond the governed document-level cap, it is designated as a future human decision (`DEC-P8.6-26`) rather than arbitrarily invented here.

### B. Independence Grouping (`independence_group_id`):
To prevent artificial concentration (e.g., selecting 10 articles written about the exact same press conference or by the same author in a single newspaper edition), every constituent record must be tagged with an `independence_group_id`.
- Concentration caps must be enforced across independence groups as well as individual constituent records.

### C. Critical Statistical & Independence Disclaimers:
- **Provenance Distinctness:** Constituent records are *provenance-distinct* records; they are **NOT** automatically statistically independent observations.
- **Clustering Metadata:** The `independence_group_id` is permanently retained for every constituent record to capture thematic, temporal, or authorial clustering.
- **Limits Do Not Create Independence:** Enforcing concentration caps limits sampling bias, but does **NOT** manufacture statistical independence.
- **Downstream Analysis:** Later statistical analyses and reporting must explicitly account for clustering where appropriate (e.g. cluster-robust variance estimation or hierarchical grouping).

---

## 7. QREL Compatibility Verification

Future QREL evidence rows require five standard fields:
- `query_id`
- `corpus_id`
- `document_id`
- `chunk_id`
- `relevance_grade`

Because `ConstituentSourceRecord` maps directly to `document_id`, the existing QREL architecture remains 100% compatible:
- The QREL engine queries `document_id` and `chunk_id` exactly as before.
- The evaluation report can join `document_id` back to `ConstituentSourceRecord.parent_archive_id` to report metrics grouped by parent archive, dataset author, or domain.

---

## 8. Backward Compatibility (Model A vs. Model B)

The amendment is strictly additive and supports both paradigms simultaneously:

| Feature | Model A: Standalone Document | Model B: Dataset Archive |
| :--- | :--- | :--- |
| **Typical Target** | `Constitution of India (Hindi).pdf` | `Politics.zip` (Zenodo HNAD) |
| **Container File** | Monolithic PDF / TXT document | Compressed ZIP / TAR container |
| **Admission Record** | `EvaluationDocumentAdmissionRecord` | `DatasetArchiveAdmissionRecord` |
| **Constituent Records** | None (Self-contained) | `ConstituentSourceRecord` array |
| **Evaluation Unit** | The PDF file itself | Each extracted article |
| **Concentration Cap** | $\le 6$ targets for the entire PDF | $\le 6$ targets per constituent article |

Existing Phase 8.6 single-document candidates require zero schema modifications.

---

## 9. Exact Schema Changes Introduced

The companion schema file [`PHASE8_6_DATASET_ARCHIVE_PROVENANCE_SCHEMA.proposed.json`](PHASE8_6_DATASET_ARCHIVE_PROVENANCE_SCHEMA.proposed.json) defines:

1. **`$defs/DatasetArchiveAdmissionRecord`:**
   - `archive_id` (UUID format)
   - `candidate_id` (string regex `^CAND-(REP|CONT)-(HI|MR|EN|FR|DE)-[0-9]{2}$`)
   - `dataset_title`, `hosting_platform`, `original_creator`, `authoritative_source`
   - `source_url`, `artifact_url`, `doi`
   - `archive_sha256` (64-char hex pattern)
   - `archive_size_bytes` (integer minimum 1)
   - `artifact_type` (enum: `ZIP`, `TAR_GZ`, `TAR_BZ2`, `TAR_XZ`, `7Z`)
   - `license` (object: `license_type`, `copyright_holder`, `evaluation_use_verified`)
   - `citation`, `admission_status`
2. **`$defs/ConstituentSourceRecord`:**
   - `source_record_id` (UUID format)
   - `parent_archive_id` (UUID foreign key)
   - `constituent_record_identifier` (string)
   - `document_id` (UUID format)
   - `source_content_hash` (64-char hex pattern)
   - `source_format`, `language`, `script`, `representation`
   - `source_locator`, `source_record_type`, `independence_group_id`
   - `extraction_metadata` (`extracted_at`, `extracted_by_tool`, `extraction_integrity_verified`)

---

## 10. Governance Risks & Mitigation

| Governance Risk | Severity | Mitigation Strategy |
| :--- | :---: | :--- |
| **Corpus Bloat from Oversized Archives** | High | `MNATD.zip` is 1.08 GB. A controlled subset selection protocol must be governed before unpacking. |
| **Accidental Over-Concentration** | Medium | Enforce concentration caps across `independence_group_id` clusters in addition to article IDs. |
| **Transformation Drift During Extraction** | High | Extraction must be bit-exact, deterministic, and verify `source_content_hash` against admission records. |

---

## 11. Human Decisions Required

The amendment is submitted as `PROPOSED` and awaits formal human governance ratification of:
- **`DEC-P8.6-21`:** Approve the `DatasetArchiveAdmissionRecord` model.
- **`DEC-P8.6-22`:** Approve the `ConstituentSourceRecord` model.
- **`DEC-P8.6-23`:** Approve archive-to-constituent cryptographic lineage.
- **`DEC-P8.6-24`:** Approve the constituent-record interpretation of the 20% concentration cap.
- **`DEC-P8.6-25`:** Approve the controlled acquisition of the three Zenodo candidate datasets under this model.

---

## 12. Protected Repository State Affirmation

Cryptographic assertions performed before and after this audit confirm that all repository protected assets remain 100% bit-for-bit identical:
- **`manuscript.pdf`:** `31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085` (**MATCH**)
- **`Valmiki Ramayana...pdf`:** `759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75` (**MATCH**)
- **`mnemo.db`:** `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` (**MATCH**)
- **`Active Alias Digest`:** `b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0` (**MATCH**)
- **Golden Corpus Files:** Exactly 44 files preserved bit-for-bit.
- **Evaluation Dataset:** Only `PHASE8_6_ACQUISITION_MANIFEST.proposed.json` present; zero external documents stored.
- **CORPUS DOWNLOADS:** **0**
- **CORPUS FILES ADDED:** **0**
- **CORPUS EXTRACTION:** **0**
- **CORPUS TRANSFORMATION:** **0**
- **INGESTION:** **NOT EXECUTED**
- **INDEXING:** **NOT EXECUTED**
- **EVALUATION:** **NOT EXECUTED**
- **QREL:** **NOT EXECUTED**

---

## 13. Final Governance Status Declaration

```text
================================================================================
FINAL EXPLICIT GOVERNANCE STATUS:
PHASE 8.6 DATASET ARCHIVE PROVENANCE AMENDMENT =
PROPOSED — REQUIRES HUMAN GOVERNANCE APPROVAL

DECISIONS PENDING HUMAN RATIFICATION:
DEC-P8.6-21 (DatasetArchiveAdmissionRecord)
DEC-P8.6-22 (ConstituentSourceRecord)
DEC-P8.6-23 (Cryptographic Lineage)
DEC-P8.6-24 (Concentration Cap Interpretation)
DEC-P8.6-25 (Zenodo Datasets Acquisition Authorization)

PHASE 8.6 DOCUMENT ACQUISITION = NOT EXECUTED
PHASE 8.6 INGESTION = NOT EXECUTED
PHASE 8.6 INDEXING = NOT EXECUTED
PHASE 8.6 EVALUATION = NOT EXECUTED
PHASE 8.6 QREL = NOT EXECUTED

PHASE 8.5 GOLDEN CORPUS = FROZEN (Hash Verified)
PHASE 8.5 V2 DATABASE = FROZEN (Hash Verified)
================================================================================
```
