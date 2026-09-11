# Retrieval evaluation preflight

Status: **READY_FOR_GPU_BENCHMARK**. Benchmark execution in this task: **NOT AUTHORIZED; NOT RUN**.

## 1. GPU and Python state

OS detects RTX 4060 Laptop GPU, 8188 MiB, driver 591.44; nvidia-smi reports driver CUDA compatibility 13.1. Bare `python` resolves first to LibreOffice Python 3.12.12, not the repository. Original repository `.venv` is Python 3.12.10, torch 2.13.0+cpu, CUDA unavailable. Do not use bare python for this experiment.

Isolated CUDA environment verification:

```json
{
  "python": "3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]",
  "executable": "C:\\Users\\athar\\Desktop\\Mnemo\\scratch\\.venv-gpu-preflight\\Scripts\\python.exe",
  "torch": "2.13.0+cu130",
  "cuda_runtime": "13.0",
  "cuda_available": true,
  "device_count": 1,
  "device_name": "NVIDIA GeForce RTX 4060 Laptop GPU",
  "tensor_test": {
    "shape": [
      1024,
      1024
    ],
    "device": "cuda:0",
    "finite": true
  },
  "packages": {
    "sentence-transformers": "5.7.0",
    "transformers": "5.15.0",
    "mnemo-core": "0.25.0",
    "mnemo-server": "0.25.0"
  }
}
```

Only a 1024x1024 random tensor multiplication was executed on CUDA. No model loading, query embeddings, corpus inference, reranking or benchmark was performed.

## 2. Repository environment mechanism and exact commands

Root pyproject.toml defines a uv workspace; README documents `uv sync --locked --all-packages`. Python requirement is >=3.12. mnemo-core reranking extra requires sentence-transformers>=5.1,<6. Installed sentence-transformers metadata accepts torch>=1.11 and transformers>=4.41,<6; transformers torch extra requires >=2.5. The matching official Windows CPython312 wheel torch2.13.0+cu130 exists. No version downgrade or driver/CUDA-toolkit installation is necessary for this test.

Executed in a separate environment because live Mnemo processes use `.venv`:

```powershell
$env:UV_PROJECT_ENVIRONMENT='scratch/.venv-gpu-preflight'
uv sync --locked --all-packages --all-extras --no-dev --python .venv/Scripts/python.exe
uv pip install --python scratch/.venv-gpu-preflight/Scripts/python.exe --no-deps 'torch==2.13.0+cu130' --index-url https://download.pytorch.org/whl/cu130
```

This installs the repository workspace's declared dependencies in isolation, then changes only torch's compute build at the same base version. Original `.venv`, application source, model settings, pyproject.toml and uv.lock were not edited. CUDA selection is an explicit environment override, not a lockfile change; future `uv sync` can restore CPU torch, so verify/reapply the exact override after syncing.

Locked transformers is5.15.0 whereas the original recovery environment has5.15.1. This difference is recorded, not hidden: any future paired run must use this same frozen environment for both rerankers; historical comparisons are not isolated solely to candidate depth. Do not silently use `uv run` against the original environment.

Sources: [official PyTorch wheel index](https://download.pytorch.org/whl/cu130/torch/), [PyTorch installation guidance](https://pytorch.org/get-started/locally/).

## 3. Exact relevance matching, end to end

### Comprehensive path

`scratch/execute_comprehensive_evaluation.py`, main/evaluate_cohort: Phase8.5 literal queries carry `target_doc`; Phase8.6 JSON carries `target_file`. Line246 selects either filename label. Lines169–197 read `document_versions.metadata.title` into `chunks_meta.doc_title`. Lines259/284/304/333 compare exact `doc_title == target`, including final relevance. No manifest lookup or document/version comparison controls relevance. The candidate dictionary contains chunk/document/version IDs, metadata title, notebook memberships, text and headings; it does not carry a source_id or filename. IDs are available but ignored by matching.

### Canonical pipeline

`scratch/run_canonical_production_pipeline.py`, ingest_dataset: line323 sets `doc_titles[c.id] = f.name`. This is **a source filename despite the variable name**, not parsed metadata title. evaluate_cohort line491 selects target_file or expected_document; line534 gets that candidate filename; line552 applies case-insensitive bidirectional substring matching between target label and candidate filename. Candidate tuple is `(cid, chunk, title)`; the chunk carries document/version IDs, but matching ignores them. A Source with source_id is created at ingestion lines306–312 but is not carried in the reranking tuple. Final saved query records contain ranks, not candidate document/version IDs.

### Forensic path

`scratch/run_forensic_analysis.py:103` defines a hardcoded filename->document-ID map for Phase8.6. get_target_cids lines137–148 selects those document chunks; Phase8.5 falls back to exact metadata title then first substring match. It imports historical canonical `found_rank` as `bge_rerank_rank` at lines163/178 rather than reranking the newly reconstructed candidate pools. These traces are not a single controlled stage-by-stage run.

## 4. Authoritative identity and validation

For new evaluation, use exact target label to locate one existing ingestion-manifest record, verify its file SHA256, then resolve document_versions.content_hash within the manifest notebook to exactly one document/version. The authoritative relevance comparison is that **document/version pair**, not title or filename substring. The label is only a lookup key; content hash and notebook membership establish identity.

All68 manifest source files match hashes; all70 Phase8.6 targets resolve uniquely; every Phase8.6 forensic hardcoded mapping agrees with the independently hash-derived identity. Mapping ambiguities: 0. No duplicate document-version titles or multiple versions of a document exist in the current67-version inventory. No false-positive filename-substring pairs were found among the current Phase8.6 query-target/candidate-filename combinations. The rule remains unsafe generically: empty titles, overlapping names, duplicate titles or multiple versions can cause false matches/ambiguity. No fallback is permitted if uniqueness fails.

## 5. Exact 34.3% versus 11.4% discrepancy

Canonical BGE-only artifact contains24/70 rank-one hits (34.2857%). Comprehensive contains8/70 per reranker (11.4286%). They use different candidate-label values and ranking setups. Applying the actual canonical filename rule to the **same saved comprehensive top candidates**, using manifest-bound filenames, gives19/70 for each reranker—the same as document/version identity. Thus11 additional top candidates are genuine targets missed by metadata-title equality.

Arithmetic: **24-8 = (19-8)+(24-19) = 11 recognition misses +5 residual cross-experiment difference**. The remaining5 cannot be causally decomposed from saved evidence. Canonical uses Top-40, filename-based contextual provider text, batch32 and explicit max_length512; comprehensive uses Top-25, metadata-title contextual text and batch16. Canonical top-candidate identities/full rankings were not persisted. We cannot assert every historical canonical hit is identity-verified, nor that matching alone explains the whole gap. No inference was rerun to fill the missing history.

The older claim 'canonical uses document IDs, comprehensive uses substring' is false. Our earlier review also omitted the canonical filename origin; this audit corrects that omission. The prior report's use of 'exact title' was accurate for comprehensive but insufficient to describe canonical label provenance.

## 6. Concrete saved-candidate examples

All70 comparisons and query texts are in the JSON and printed for the first10 by audit_relevance_mapping.py. Below, canonical-rule result is the filename rule applied to this **same saved comprehensive BGE top candidate**, not an invented historical canonical result. Historical canonical top identity is explicitly unavailable.

| QID | Target label | Target document / version | Saved BGE top document / version | Exact metadata title | Canonical filename rule | Manifest identity |
|---|---|---|---|---|---|---|
| DQ01 | mahades_economic_survey_highlights_marathi.pdf | be66dc63-1370-4932-ac33-39da3b554718 / 56aecdd5-421e-4b0d-9f6e-5068d7b6186e | e63dbca3-f16b-4e56-a018-730df2bade07 / 2ae42bf8-7df3-49f0-a633-0bd1fd4b64be | False | False | False |
| DQ02 | mahades_economic_survey_highlights_marathi.pdf | be66dc63-1370-4932-ac33-39da3b554718 / 56aecdd5-421e-4b0d-9f6e-5068d7b6186e | ba83cdf3-dcab-40c3-9fdc-6fa3d9759a2c / 01732d59-e11b-404d-a9b6-95116f1f7f45 | False | False | False |
| DQ03 | mahades_economic_survey_ch1_marathi.pdf | b7772f9c-4b1f-4c25-8e30-1d1b85b0b9e1 / 4339c4cc-10c9-4c63-a1a6-adddc5a20cfd | ba83cdf3-dcab-40c3-9fdc-6fa3d9759a2c / 01732d59-e11b-404d-a9b6-95116f1f7f45 | False | False | False |
| DQ04 | mahades_economic_survey_ch1_marathi.pdf | b7772f9c-4b1f-4c25-8e30-1d1b85b0b9e1 / 4339c4cc-10c9-4c63-a1a6-adddc5a20cfd | ba83cdf3-dcab-40c3-9fdc-6fa3d9759a2c / 01732d59-e11b-404d-a9b6-95116f1f7f45 | False | False | False |
| DQ05 | mahades_economic_survey_ch2_marathi.pdf | 5083333e-4741-49db-b6f1-62338e635efa / c189a32c-359c-448b-99e0-74da3c2f7888 | ba83cdf3-dcab-40c3-9fdc-6fa3d9759a2c / 01732d59-e11b-404d-a9b6-95116f1f7f45 | False | False | False |
| DQ06 | mahades_economic_survey_ch2_marathi.pdf | 5083333e-4741-49db-b6f1-62338e635efa / c189a32c-359c-448b-99e0-74da3c2f7888 | ba83cdf3-dcab-40c3-9fdc-6fa3d9759a2c / 01732d59-e11b-404d-a9b6-95116f1f7f45 | False | False | False |
| DQ07 | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | c4cccf07-6c9a-4c25-8b50-88faaf4db783 / 76301e1d-a4d4-48d7-a054-dc648ff88320 | e63dbca3-f16b-4e56-a018-730df2bade07 / 2ae42bf8-7df3-49f0-a633-0bd1fd4b64be | False | False | False |
| DQ08 | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | c4cccf07-6c9a-4c25-8b50-88faaf4db783 / 76301e1d-a4d4-48d7-a054-dc648ff88320 | fe0b67bf-1365-4fb8-a1cd-905a3d00f365 / e94f8421-1253-4ce7-88b7-222508099c39 | False | False | False |
| DQ09 | shetkaryacha_asud_pan_2_marathi.html | bb9b60d2-24f6-4111-b523-f601ac27dea6 / d68b0b67-f882-4812-bcd5-d111f237bb34 | e63dbca3-f16b-4e56-a018-730df2bade07 / 2ae42bf8-7df3-49f0-a633-0bd1fd4b64be | False | False | False |
| DQ10 | shetkaryacha_asud_pan_2_marathi.html | bb9b60d2-24f6-4111-b523-f601ac27dea6 / d68b0b67-f882-4812-bcd5-d111f237bb34 | ba83cdf3-dcab-40c3-9fdc-6fa3d9759a2c / 01732d59-e11b-404d-a9b6-95116f1f7f45 | False | False | False |

## 7. Database owners and stability

Windows Restart Manager identified these resource owners (no process was terminated):

```json
[
  {
    "ProcessId": 3656,
    "ParentProcessId": 20916,
    "Name": "python.exe",
    "CommandLine": "\"C:\\Users\\athar\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" scratch/test_e2e_answer.py"
  },
  {
    "ProcessId": 28960,
    "ParentProcessId": 33568,
    "Name": "python.exe",
    "CommandLine": "\"C:\\Users\\athar\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" scratch/test_e2e_answer.py"
  },
  {
    "ProcessId": 25632,
    "ParentProcessId": 30568,
    "Name": "python.exe",
    "CommandLine": "\"C:\\Users\\athar\\AppData\\Local\\Programs\\Python\\Python312\\python.exe\" scratch/test_comprehensive_context.py"
  }
]
```

These are existing Mnemo scratch E2E/context tests, not the three mnemo-mcp server chains. Their scripts initialize KnowledgeEngine and open default writable sqlite3 connections; they cannot be certified read-only from process names. Nevertheless, no writes were observed: persistent read-only connection data_version stayed unchanged, DB/WAL/SHM bytes matched across the audit, WAL was empty, and hashes were checked again after environment setup. Read-only evaluation is technically possible with `mode=ro`, `query_only=ON`, an explicit consistent read transaction and identity/stability checks. An observed future write must invalidate/stop a run. Do not rely on another process remaining idle indefinitely.

The previous PowerShell Get-FileHash failure was not proof of an exclusive SQLite lock. Python read access and SQLite read-only access succeeded without a lock bypass or database copy.

## 8. Integrity and counts

integrity_check: ['ok']; foreign_key_check: [].

```json
{
  "documents": 67,
  "document_versions": 67,
  "sources": 68,
  "chunks": 4026,
  "fts_chunks": 4026,
  "asset_catalog": 589,
  "asset_occurrences": 620,
  "visual_embeddings": 619,
  "ocr_results": 619,
  "vision_results": 619
}
```

Text NPZ embeddings:4026x1024,4026 unique chunk IDs, zero orphan IDs. FTS logical row count is4026; this is not a claim that FTS postings or retrieval quality were tested. Visual/OCR/Vision each619; this is not multimodal retrieval evaluation.

DB SHA256: `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`. Final watched DB/WAL/SHM/NPZ/pyproject/lock bytes unchanged: True. Full hashes and68 source-file comparisons are in JSON. No index rebuild, corpus write, model-artifact write, ContextBuilder/FTS change, Top-50 change or alias change occurred.

## 9. Authorization and next task

**This task does not authorize benchmark execution.** Status READY_FOR_GPU_BENCHMARK describes hardware/mapping/database preflight only; it does not assert the defective harness has been repaired or production runtime parity established. Stop here.

Next task: authorize a narrowly scoped corrected production-path harness implementation using the validated manifest document/version mapping, then separately execute the shared-candidate Top-50 GPU A/B using `scratch/.venv-gpu-preflight/Scripts/python.exe`. Do not run the old comprehensive or canonical scripts: the former retains defective matching and the latter includes ingestion/embedding generation. Exact safe preflight rerun command: `.\.venv\Scripts\python.exe scratch/audit_relevance_mapping.py`, then `.\.venv\Scripts\python.exe scratch/audit_relevance_mapping.py --finalize` for the tiny CUDA check/report, not retrieval.
