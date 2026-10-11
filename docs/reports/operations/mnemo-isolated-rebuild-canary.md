# Isolated rebuild canary — engineering evidence

Date: 2026-10-07 UTC. This is a partial engineering warm-up, **not** the full evaluation re-index or certification.

## Implemented

- `mnemo_server.tools.isolated_rebuild` verifies each immutable selected file against the existing evaluation index by SHA-256 and prior document/version identity, allocates a fresh notebook/runtime identity, invokes the actual ingestion runner, verifies stored original bytes and ordered version IR, checks chunk ordinal spans, and records a non-serving coverage report. It never promotes a generation.
- The existing derived worker now accepts explicit modality selection. Its read-only observations include the live SQLite WAL; the earlier `immutable=1` observation incorrectly reported zero persisted Vision rows after a successful job.
- The governed projection coordinator supports `activate=False`. The existing preparation runner's `--build-only` mode persists READY Vision/visual projections without activation and skips structured-table projection, whose helper otherwise promoted generations independently.
- A bounded local V2 query utility targets only a runtime under `scratch/isolated_rebuilds` and uses a disposable cursor key.

## Warm-up dataset and storage

Final canary runtime: `scratch/isolated_rebuilds/8059e573fac94560a9747c9bb7eda990`; notebook `d909e143-675d-5835-a91e-f3d5792b53f8`. The earlier two disposable runs exposed and then verified fixes to the WAL observation and build-only activation defects; they were not promoted.

| Immutable source | SHA-256 | Prior and canary document/version | Reason |
|---|---|---|---|
| `codePrompt.js` | `53020012146826d1580727632b696cc884d5396dd0f1ae21c26ae4fe05fd5003` | `8abc6c73-7d1c-5248-8c28-4157de5ca51a` / `7882f1db-a197-5c84-9b10-66b1fe2d3689` | Canonical code and chunk retrieval |
| `IMG_20260824_121815328_HDR_AE.jpg` | `5ed7f5ecb32e3abcdede8c11363d55dbcbcbf0363fc0efcd808c52057b0f0580` | `f662b4e1-7e34-5e45-9075-d667a24e8f82` / `41913ab4-08fa-5f00-a78d-1e456494d707` | A diagram with real Vision/visual derivations; OCR is applicable |

The isolated SQLite store contains two documents, two versions, two notebook sources, two canonical code chunks, and one image occurrence. Both persisted IR files have one contiguous ordinal-0 block. The code version has two chunks whose source ordinal spans resolve to that block; the image-only version has no canonical text chunks. Original blob bytes and their database references match the immutable source hashes. The production parser and ingestion service generated all records.

## Actual modality execution

- **PaddleOCR:** not executed. Neither `paddleocr` nor `paddle` is installed in the current virtual environment; no approved detection/recognition model trees were supplied. No OCR results or OCR projection rows were fabricated.
- **Vision:** local `qwen2.5vl:latest` revision `5ced39dfa4bac325dc183dd1e4febaa1c46b3ea28bce48896c8e69c1e79611cc` completed one job and persisted one complete result with four observations. Occurrence `5b4254ee-5594-5c4e-9426-587064bdd660`; derivation `0b0f5120-7ac0-5a02-a14c-62842e1a3ef9`; derivation generation `9aadaf0f-dc07-5828-a6ec-f5c1d9abfc2d`.
- **Visual embedding:** local CLIP revision `32bd64288804d66eefd0ccbe215aa642df71cc41` completed one 768-dimensional, unit-normalized cosine-space result for the same occurrence. Derivation `05b5c68b-469d-5c6c-856b-b72ee1bd1e0e`; generation `94c1c210-76d8-5b6c-a801-d181540ec9ca`.
- **Projections:** one Vision-text row, generation `5153e130-28ca-561c-b15a-2d79219b01e1`, and one visual-vector row, generation `c61d2d88-b48d-5e7b-a21f-956edae6b7b5`. Both have complete 1/1 source-local coverage and are READY but **inactive**. There are zero active index generations in the final canary.
- **Multilingual:** no canonical/OCR/Vision multilingual embedding rows were generated. The existing historical rebuild path still does not construct a complete new-notebook BGE-M3 derived embedding generation. Cross-language retrieval is untested.

## Activation and retrieval

The canary coverage report expects one raster occurrence. Vision and visual derivation/projection coverage is 1/1; OCR and OCR projection coverage is 0/1. Canonical chunks are 2, multilingual embeddings are 0, and no generation is active. The combined activation gate is **NO**. The diagnostic cannot authorize activation even if its counts eventually match: full ancestry, model-space compatibility and atomic promotion are not yet integrated into this orchestrator. Do not use the individual READY projection results as proof of complete retrieval.

Actual `query_notebook_v2` against this isolated notebook returned two canonical `buildCodePrompt` chunks. It reported canonical `searched` and OCR, Vision, multilingual, and visual `unavailable`, with `answer_status=not_generated`. A normal query for `cutting tool diagram` returned no canonical evidence while still reporting those unavailable representations; it did not constitute a derived-evidence retrieval success.

## Integrity and next gate

The two original source file hashes remained unchanged. After final testing, all four protected database byte sizes and SHA-256 hashes matched the pre-run checkpoint: `3157ff27…ab458c`, `18835883…2bf55d`, `bc048cc1…1d84`, and `9a3521f8…d7a2`. Their WAL/SHM presence, sizes and hashes were also unchanged. No Phase 8.5/8.6 corpus re-index or production promotion occurred.

Final-source checks: 2,817 passed, 18 skipped, 9 warnings; 90.13% coverage. Ruff, strict mypy (292 source files), compileall, lock verification, all three Python package builds, and `git diff --check` passed. The protected-storage policy regression passed after live WAL observations were routed through the existing worker connection.

**Not ready for the two permanent evaluation notebooks.** Required before that phase: provision an approved PaddleOCR 3.4.1 runtime and exact model trees; execute real OCR on this canary; build governed canonical/OCR/Vision multilingual embeddings in the new notebook; prove complete projection/embedding coverage and compatibility; then exercise a controlled activation and positive OCR/Vision V2 retrieval. The current module is a guarded canary-ingest/coverage entry point, not yet a complete one-command rebuild orchestrator.
