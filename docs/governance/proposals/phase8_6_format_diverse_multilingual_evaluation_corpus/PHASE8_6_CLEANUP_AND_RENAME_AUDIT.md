# PHASE 8.6 — CONTROLLED CLEANUP AND RENAME AUDIT REPORT
**Classification:** GOVERNANCE AUDIT REPORT — PHASE REBRAND & DATASET CLEANUP
**Date:** 2026-09-03
**Status:** COMPLETE / VERIFIED
**Author:** Automated Governance Audit

---

## 1. EXECUTIVE SUMMARY

In accordance with explicit human governance directives, the evaluation-corpus-expansion effort previously designated "Phase 9 Evaluation Corpus Expansion" has been officially renamed to:

**PHASE 8.6 — FORMAT-DIVERSE MULTILINGUAL EVALUATION CORPUS**

This renaming eliminates ambiguity with a separate, pre-existing Phase 9 in the Mnemo engineering roadmap (Web UI React frontend, Layer 3).

Simultaneously:
1. The three obsolete TXT-only archives acquired solely for chunk-count language coverage (`Politics.zip`, `Science & Technology.zip`, and partial `MNATD.zip`) have been **permanently deleted**.
2. All directory paths, governance proposal documents, schemas, and registries have undergone **semantic renaming**.
3. All Phase 8.5 protected physical and cryptographic assets were **verified unchanged** both pre- and post-operation.
4. **Zero new downloads, zero extractions, zero ingestions, and zero database mutations** occurred during this operation.

---

## 2. PART A — CONTROLLED CLEANUP AUDIT: OBSOLETE TXT-ONLY DATASETS

The format-diversity audit confirmed that `Politics.zip` (20,939 `.txt` files), `Science & Technology.zip` (6,017 `.txt` files), and `MNATD.zip` (partial download of plain `.txt` files) exercise exclusively the `PlainTextParser`. Because the objective of Phase 8.6 is to exercise Mnemo's multi-format parser stack across languages, these TXT-only archives were rejected and ordered deleted.

### 2.1 Pre-Deletion Forensic Record

| Artifact Name | Former Local Path | Pre-Deletion Byte Size | Published / Computed Checksum | Acquisition Status | Governance Disposition |
| :--- | :--- | ---: | :--- | :--- | :--- |
| `Politics.zip` | `evaluationDataset/Phase 9 Evaluation Expansion Corpus/Politics.zip` | 59,972,294 bytes | MD5: `5b80d82d5c49a347f48f438d610ccebb`<br>SHA-256: `479a25a9b2a6ec690a77a83078857a01cec98fcb8719699d842cd1f1ba861ca4` | ACQUIRED-BUT-NOT-ADMITTED | **REJECTED & DELETED** (TXT-only, fails format diversity) |
| `Science & Technology.zip` | `evaluationDataset/Phase 9 Evaluation Expansion Corpus/Science & Technology.zip` | 15,073,261 bytes | MD5: `aa3acd2e682c0ae48c82d7ee365346bc`<br>SHA-256: `e7df60f6e2eaf7b0a23d73dd53d707dbc42078275fc1a3e4bc61679f3caa778b` | ACQUIRED-BUT-NOT-ADMITTED | **REJECTED & DELETED** (TXT-only, fails format diversity) |
| `MNATD.zip` | `evaluationDataset/Phase 9 Evaluation Expansion Corpus/MNATD.zip` | 759,169,024 bytes | Partial stream (70.3% of 1,080,684,303 bytes). Download was cleanly terminated via `manage_task(kill)`. | STOPPED-PARTIAL | **REJECTED & DELETED** (TXT-only, incomplete archive) |

### 2.2 Pre-Deletion Safety Verification
Before deletion, the following invariants were verified:
- **No extraction occurred:** Zero `.txt` files were extracted to disk from any of the three archives.
- **No database reference:** Neither `mnemo.db` nor any SQLite table referenced any of these files or candidate IDs.
- **Not part of Phase 8.5:** None of these three files existed in `goldenDataset/` or any Phase 8.5 corpus directory.
- **Targeted deletion only:** Only the three specific file paths were targeted; no recursive deletion was invoked.

### 2.3 Post-Deletion Verification

```
Politics.zip             = ABSENT (verified on disk)
Science & Technology.zip = ABSENT (verified on disk)
MNATD.zip                = ABSENT (verified on disk)
```

Disk space freed: ~834.2 MB.

---

## 3. PART B — PHASE RENAME: PHASE 9 → PHASE 8.6

### 3.1 Directory Renaming

| Old Directory Path | New Directory Path | Status |
| :--- | :--- | :---: |
| `evaluationDataset/Phase 9 Evaluation Expansion Corpus/` | `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/` | **RENAMED** |
| `docs/governance/proposals/phase9_evaluation_corpus_expansion/` | `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/` | **RENAMED** |

All legitimate non-archive files were preserved during directory rename (e.g. `PHASE8_6_ACQUISITION_MANIFEST.proposed.json`).

### 3.2 File Renaming in Governance Directory

All 25 proposal files in `docs/governance/proposals/phase8_6_format_diverse_multilingual_evaluation_corpus/` were renamed from `PHASE9_*` to `PHASE8_6_*`:

1. `PHASE9_ARTIFACT_PROVENANCE_REGISTER.proposed.json` → `PHASE8_6_ARTIFACT_PROVENANCE_REGISTER.proposed.json`
2. `PHASE9_AUTHORIZED_ACQUISITION_REPORT.md` → `PHASE8_6_AUTHORIZED_ACQUISITION_REPORT.md`
3. `PHASE9_CANDIDATE_REPLACEMENT_AND_ACQUISITION_PATH_AUDIT.md` → `PHASE8_6_CANDIDATE_REPLACEMENT_AND_ACQUISITION_PATH_AUDIT.md`
4. `PHASE9_CANDIDATE_SOURCE_DISCOVERY_REPORT.md` → `PHASE8_6_CANDIDATE_SOURCE_DISCOVERY_REPORT.md`
5. `PHASE9_CANDIDATE_SOURCE_REGISTER.proposed.json` → `PHASE8_6_CANDIDATE_SOURCE_REGISTER.proposed.json`
6. `PHASE9_CANDIDATE_SOURCE_VERIFICATION_AUDIT.md` → `PHASE8_6_CANDIDATE_SOURCE_VERIFICATION_AUDIT.md`
7. `PHASE9_CORPUS_ADMISSION_POLICY.proposed.md` → `PHASE8_6_CORPUS_ADMISSION_POLICY.proposed.md`
8. `PHASE9_DATASET_ARCHIVE_PROVENANCE_AMENDMENT.proposed.md` → `PHASE8_6_DATASET_ARCHIVE_PROVENANCE_AMENDMENT.proposed.md`
9. `PHASE9_DATASET_ARCHIVE_PROVENANCE_AMENDMENT_REPORT.md` → `PHASE8_6_DATASET_ARCHIVE_PROVENANCE_AMENDMENT_REPORT.md`
10. `PHASE9_DATASET_ARCHIVE_PROVENANCE_SCHEMA.proposed.json` → `PHASE8_6_DATASET_ARCHIVE_PROVENANCE_SCHEMA.proposed.json`
11. `PHASE9_EVALUATION_CORPUS_EXPANSION_DECISION_REGISTER.md` → `PHASE8_6_EVALUATION_CORPUS_EXPANSION_DECISION_REGISTER.md`
12. `PHASE9_EVALUATION_CORPUS_EXPANSION_GOVERNANCE_PROPOSAL.md` → `PHASE8_6_EVALUATION_CORPUS_EXPANSION_GOVERNANCE_PROPOSAL.md`
13. `PHASE9_EVALUATION_CORPUS_SCHEMA.proposed.json` → `PHASE8_6_EVALUATION_CORPUS_SCHEMA.proposed.json`
14. `PHASE9_EXPANSION_FORENSIC_AUDIT_REPORT.md` → `PHASE8_6_EXPANSION_FORENSIC_AUDIT_REPORT.md`
15. `PHASE9_FORMAT_DIVERSE_SOURCE_DISCOVERY_REPORT.md` → `PHASE8_6_FORMAT_DIVERSE_SOURCE_DISCOVERY_REPORT.md`
16. `PHASE9_FORMAT_DIVERSE_SOURCE_REGISTER.proposed.json` → `PHASE8_6_FORMAT_DIVERSE_SOURCE_REGISTER.proposed.json`
17. `PHASE9_FORMAT_DIVERSITY_GOVERNANCE_DECISION_REGISTER.md` → `PHASE8_6_FORMAT_DIVERSITY_GOVERNANCE_DECISION_REGISTER.md`
18. `PHASE9_FORMAT_DIVERSITY_REQUIREMENT.proposed.md` → `PHASE8_6_FORMAT_DIVERSITY_REQUIREMENT.proposed.md`
19. `PHASE9_GOVERNANCE_PRE_APPROVAL_CONSISTENCY_AUDIT.md` → `PHASE8_6_GOVERNANCE_PRE_APPROVAL_CONSISTENCY_AUDIT.md`
20. `PHASE9_MULTILINGUAL_FORMAT_COVERAGE_MATRIX.proposed.json` → `PHASE8_6_MULTILINGUAL_FORMAT_COVERAGE_MATRIX.proposed.json`
21. `PHASE9_NATIVE_FORMAT_AUDIT.md` → `PHASE8_6_NATIVE_FORMAT_AUDIT.md`
22. `PHASE9_PRE_ACQUISITION_ARTIFACT_FORENSIC_AUDIT.md` → `PHASE8_6_PRE_ACQUISITION_ARTIFACT_FORENSIC_AUDIT.md`
23. `PHASE9_REPLACEMENT_CANDIDATE_REGISTER.proposed.json` → `PHASE8_6_REPLACEMENT_CANDIDATE_REGISTER.proposed.json`
24. `PHASE9_RESOLVED_ACQUISITION_PATHS.proposed.json` → `PHASE8_6_RESOLVED_ACQUISITION_PATHS.proposed.json`
25. `PHASE9_SOURCE_RESOLUTION_AUDIT.md` → `PHASE8_6_SOURCE_RESOLUTION_AUDIT.md`

### 3.3 File Renaming in Evaluation Dataset Directory

- `evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus/PHASE9_ACQUISITION_MANIFEST.proposed.json` → `PHASE8_6_ACQUISITION_MANIFEST.proposed.json`

---

## 4. PART B.2 — CROSS-REFERENCE AUDIT & MIGRATION TABLE

The entire workspace was scanned with ripgrep to identify and classify all occurrences of `Phase 9`, `phase9_evaluation_corpus_expansion`, `PHASE9_`, and `DEC-P9-`.

### 4.1 Migration Classification Table

| Occurrence Pattern | Context / Location | Migration Action | Reason |
| :--- | :--- | :---: | :--- |
| `Phase 9 Evaluation Expansion Corpus` | Governance proposals & manifests | **CHANGED → `Phase 8.6 Format-Diverse Multilingual Evaluation Corpus`** | Belongs directly to this corpus-expansion effort. |
| `Phase 9 Evaluation Corpus Expansion` | Governance proposals & audits | **CHANGED → `Phase 8.6 Format-Diverse Multilingual Evaluation Corpus`** | Formal project title updated to reflect Phase 8.6. |
| `phase9_evaluation_corpus_expansion` | Directory paths & schema references | **CHANGED → `phase8_6_format_diverse_multilingual_evaluation_corpus`** | Proposal directory moved and paths updated. |
| `PHASE9_` | File names, schema IDs, document titles | **CHANGED → `PHASE8_6_`** | Standardized file naming for Phase 8.6. |
| `DEC-P9-*` | Governance decision identifiers | **CHANGED → `DEC-P8.6-*`** | Decision IDs updated to prevent collision. |
| `mnemo.phase9.*` | Manifest and schema URI identifiers | **CHANGED → `mnemo.phase8_6.*`** | Canonical JSON schema/manifest identifier alignment. |
| `Web UI (Layer 3 — Planned Phase 9)` | `README.md` (lines 78, 135, 256) | **PRESERVED (UNCHANGED)** | Genuinely refers to engineering Phase 9 (React Web UI frontend). |
| `Phase 9 UI implementation` | `PHASE_8_5_COMPLETE_IMPLEMENTATION_PLAN.md` | **PRESERVED (UNCHANGED)** | Refers to future UI engineering roadmap. |
| `Phase 9 may consume capability discovery` | `PHASE_8_5_PRE_8_5_11_RECONCILIATION.md` | **PRESERVED (UNCHANGED)** | Architectural demarcation between core engine and UI phase. |
| `Phase 9 Web UI responsibility` | `PHASE_8_5_ARCHITECTURAL_CONTRADICTION_AUDIT.md` | **PRESERVED (UNCHANGED)** | Architectural audit record referencing UI milestone M9. |

---

## 5. PART B.3 — CANONICAL GOVERNANCE STATUS

```
================================================================================
PHASE 8.6 FORMAT-DIVERSE MULTILINGUAL EVALUATION CORPUS
CURRENT GOVERNED LIFECYCLE STATUS
================================================================================

PHASE NAME                     = Phase 8.6 — Format-Diverse Multilingual Evaluation Corpus
FORMAT-DIVERSITY REQUIREMENT   = PROPOSED — REQUIRES HUMAN GOVERNANCE APPROVAL
NEW DATASET ACQUISITION        = NOT STARTED
NEW DATASET EXTRACTION         = FALSE
INGESTION                      = FALSE
INDEXING                       = FALSE
EVALUATION                     = FALSE
QREL CREATION                  = FALSE

OBSOLETE TXT DATASETS:
  Politics.zip                 = DELETED
  Science & Technology.zip     = DELETED
  MNATD.zip                    = DELETED / WAS PARTIAL

PROTECTED ASSET INTEGRITY:
  Phase 8.5 Golden Corpus      = FROZEN / UNCHANGED
  Phase 8.5 V2 Database        = FROZEN / UNCHANGED
  V2 Active Alias Set          = FROZEN / UNCHANGED
  V2 Runtime                   = UNCHANGED
================================================================================
```

---

## 6. PROTECTED ASSET VERIFICATION AUDIT

All Phase 8.5 protected physical assets were verified against the authoritative governance register before and after the cleanup and renaming operations:

```
[PASS] manuscript.pdf:
       Path: goldenDataset/Phase 8.5 Evaluation Corpus/manuscript.pdf
       Hash: 31addf387d13de26e3b155e1fc6ee65d5f554cfdfb4281951c56e9482b6f8085 (EXACT MATCH)

[PASS] Valmiki Ramayana Comparison PDF:
       Path: goldenDataset/Phase 8.5 Evaluation Corpus/Valmiki Ramayana aur Ramakien Ek Tulnamatmak Adhyayan.pdf
       Hash: 759f2adbfd2fc1191ff8576401d1cbc34bbfefaf79a573e8747c53d4c858af75 (EXACT MATCH)

[PASS] V2 SQLite Production Database:
       Path: scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db
       Hash: 3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c (EXACT MATCH)

[PASS] Active Multilingual V2 Alias Set Digest:
       Digest: b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0 (EXACT MATCH)
```

**Result:** Zero bit-level changes to any Phase 8.5 protected artifact.
