# Mnemo Phase 8.6 — Dataset Archive / Constituent Source-Record Provenance Governance Amendment
**Document ID:** `mnemo.phase8_6.dataset-archive-provenance-amendment.proposed.v1`  
**Path:** `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/PHASE8_6_DATASET_ARCHIVE_PROVENANCE_AMENDMENT.proposed.md`  
**Date:** September 2, 2026  
**Status:** `PROPOSED — REQUIRES HUMAN GOVERNANCE APPROVAL`  
**Applicability:** Phase 8.6 Multilingual Evaluation Corpus Expansion

---

## 1. Executive Summary & Purpose

This governance amendment establishes the formal data model, cryptographic lineage rules, and admission criteria required to admit **linguistic dataset archives** containing multiple constituent articles or documents into the Phase 8.6 Evaluation Corpus.

### Background: The 1-File = 1-Document Limitation
The initial Phase 8.6 corpus schema (`PHASE8_6_EVALUATION_CORPUS_SCHEMA.proposed.json`) assumed a strictly 1-to-1 relationship between an acquired file on disk and an admitted evaluation document (`EvaluationDocumentAdmissionRecord`). 

When acquiring modern, open-science linguistic corpora (e.g., CERN Zenodo datasets such as *Hindi News Article Dataset* or *Marathi News Article Text Dataset*), the acquired artifact is an immutable compressed container (`.zip` or `.tar.gz`) packaging hundreds or thousands of complete, independent, continuous-prose articles. 

Under the original schema:
1. Treating a 60 MB `.zip` archive containing 1,000 articles as a single "document" would subject the entire archive to the **20% document concentration cap (`DEC-P8.6-09`)**, restricting the entire collection to only **6 evaluation queries**, thereby preventing diverse evaluation sampling.
2. Unpacking the archive without a formal two-tier governance model would sever the cryptographic provenance linking each extracted article back to the authoritative repository DOI and parent archive hash.

This amendment resolves both issues by establishing a governed **Two-Tier Provenance Hierarchy**.

---

## 2. Two-Tier Provenance Architecture

```text
================================================================================
IMMUTABLE DATASET ARCHIVE
  │
  ├── archive_id (UUID)
  ├── candidate_id (e.g. CAND-REP-HI-03)
  ├── archive_sha256 (Hash of the container bitstream)
  ├── source_url / artifact_url (Authoritative download endpoints)
  ├── doi (Permanent DOI if applicable)
  └── license / copyright_holder
        │
        ▼  [Governed Deterministic Unpacking]
CONSTITUENT SOURCE RECORD
  │
  ├── source_record_id (UUID)
  ├── parent_archive_id (FK -> archive_id)
  ├── source_locator (Internal archive path, e.g. "Politics/article_0042.txt")
  ├── source_content_hash (SHA-256 of the extracted content bytes)
  ├── document_id (UUID assigned for corpus indexing)
  ├── language / script / representation
  └── independence_group_id (Cluster grouping for concentration governance)
        │
        ▼  [Ingestion & Projection]
CANONICAL EVALUATION DOCUMENT VERSION
        │
        ▼  [Segmentation]
CHUNKS (doc_id:p:offset)
        │
        ▼  [Annotation]
EVALUATION EVIDENCE & QREL
================================================================================
```

---

## 3. Cryptographic Lineage Invariants

To guarantee bit-for-bit auditability across the lifecycle:

1. **Archive Invariant:** The downloaded archive container file is stored unmodified in an immutable acquisition cache. Its hash (`archive_sha256`) serves as the permanent identifier of the remote bitstream.
2. **Constituent Record Invariant:** Each extracted constituent document receives its own cryptographic content digest (`source_content_hash`). Under no circumstances is `archive_sha256` equated to `source_content_hash`.
3. **Traceability Chain:** Every evaluation target, chunk, and QREL row can be deterministically traced backward:
   $$\text{QREL Row} \longrightarrow \text{Chunk} \longrightarrow \text{Document ID} \longrightarrow \text{Constituent Record} \longrightarrow \text{Parent Archive ID} \longrightarrow \text{Source DOI / URL}$$

---

## 4. Governed Extraction Specification

Extraction is a governed, deterministic lifecycle step that executes **after** human authorization of the parent archive:

1. **Integrity Pre-Condition:** The downloaded archive file must be verified against its declared `archive_sha256` prior to extraction.
2. **Container Preservation:** Extraction does not overwrite, delete, or replace the parent archive container. The container remains permanently preserved.
3. **Deterministic Identity:** The `constituent_record_identifier` is computed deterministically from the internal archive file path (e.g. normalized POSIX path inside the ZIP).
4. **Content Validation:** The extracted text must be verified as valid native UTF-8 Unicode, free from binary corruption or legacy encodings, before admission.

---

## 5. Resolution of Concentration-Control Rule (`DEC-P8.6-09` Clarification)

### Policy Interpretation & Two-Level Concentration Evaluation:
To prevent benchmark concentration within any single document or dataset ecosystem, the concentration-control rule is evaluated at **BOTH**:

1. **Constituent Source Document / Record Level:**
   - In an evaluation cohort of size $n=30$, no single constituent source document or article may contribute more than 6 evaluation targets ($\le 20\%$).
2. **Parent Dataset / Independence-Group Level:**
   - Concentration is tracked at the parent dataset archive and `independence_group_id` level to ensure that evaluation targets are not excessively concentrated within one dataset ecosystem, narrow topical event, or publishing author.
   - If a specific numerical cap at the dataset archive level is required beyond the governed document-level cap, it is designated as a future human decision (`DEC-P8.6-26`) rather than arbitrarily invented here.

### Critical Statistical & Independence Disclaimers:
- **Provenance Distinctness:** Constituent records are *provenance-distinct* records; they are **NOT** automatically statistically independent observations.
- **Clustering Metadata:** The `independence_group_id` is permanently retained for every constituent record to capture thematic, temporal, or authorial clustering.
- **Limits Do Not Create Independence:** Enforcing concentration caps limits sampling bias, but does **NOT** manufacture statistical independence.
- **Downstream Analysis:** Later statistical analyses and reporting must explicitly account for clustering where appropriate (e.g. cluster-robust variance estimation or hierarchical grouping).

---

## 6. Backward Compatibility with Standalone Documents

This amendment fully preserves backward compatibility. The Phase 8.6 evaluation architecture natively supports two coexisting admission models:

- **Model A (Standalone Document):** Single monolithic files (e.g. `Constitution of India (Hindi).pdf`, `Balbharati Kumarbharati Class 10.pdf`). Admitted directly via `EvaluationDocumentAdmissionRecord` where 1 file = 1 document.
- **Model B (Dataset Archive):** Container archives (e.g. `Politics.zip`, `Science & Technology.zip`, `MNATD.zip`). Admitted via `DatasetArchiveAdmissionRecord` and decomposed into `ConstituentSourceRecord` instances.

Existing documents and future standalone documents require zero modifications.

---

## 7. Human Governance Decisions Required

This amendment is submitted for explicit human governance review and requires ratification of the following decisions:

- **`DEC-P8.6-21`:** Approve the `DatasetArchiveAdmissionRecord` schema definition for container-level provenance.
- **`DEC-P8.6-22`:** Approve the `ConstituentSourceRecord` schema definition for article-level extraction.
- **`DEC-P8.6-23`:** Approve the cryptographic lineage chain linking constituent records to parent archive hashes.
- **`DEC-P8.6-24`:** Approve the application of the 20% concentration cap at the constituent document level rather than the archive container level.
- **`DEC-P8.6-25`:** Approve the controlled acquisition of the three verified Zenodo candidates (`CAND-REP-HI-03`, `CAND-REP-HI-04`, `CAND-REP-MR-03`) under this two-tier model.

*Operational Status: PROPOSED — REQUIRES HUMAN GOVERNANCE APPROVAL.*
