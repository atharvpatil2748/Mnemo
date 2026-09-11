# Mnemo Historical Index and Embedding Cleanup

Status: `MNEMO_HISTORICAL_INDEX_CLEANUP_PASS`.

## Current protected state

The Phase 8.5 notebook, Phase 8.6 notebook, 44-document production store, active blob root, current evaluation embeddings, configured BGE/CLIP models, Ollama, runtime configuration, registry, source, tests, scripts, and certification evidence are excluded from cleanup.

| Store | SHA-256 | Documents | Chunks | Status |
|---|---|---:|---:|---|
| Production | `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c` | 44 | 2,658 | protected |
| Phase 8.5 notebook | `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84` | 44 | 2,658 | protected/READY |
| Phase 8.6 notebook | `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2` | 24 | 5,843 | protected/READY |

## Historical candidates approved for deletion

Four incomplete/superseded canonical build generations from September 3 and one empty scratch test store passed the dependency audit. No generation ID is referenced by source, tests, scripts, configuration, manifests outside its own directory, registry, or active process. None contains tracked files.

Only their databases, SQLite sidecars, blob/index payloads, and one historical 3,906×1,024 embedding matrix are targeted. Historical integrity manifests and evaluation-result JSON files remain in place.

Expected recovery: 780,531,821 bytes across 16 exact targets.

## Historical state retained

- Phase 8.5.11: referenced by governed build/activation protection logic and tests.
- WP-10 stage 2: referenced by governed build logic, tests, and governance.
- WP-16: current V2 build operator source database and reproducibility evidence.
- WP-10 remediation: governance explicitly requires forensic retention; the DB also reports 1,498 FK violations.
- Oversized atomic-structure stores: linked deterministic fix evidence.
- Evaluation recovery/query vectors: identity-bound evaluation inputs.
- Reindex run directories: diagnostic and transport evidence; only 4.2 MB of abandoned smoke-store data.
- Manual Gita QA: directly referenced by a script and MCP Golden Corpus tests.

## Before cleanup

- C: free space: 46,435,971,072 bytes.
- Known historical index/store data: 2,590,942,068 bytes.
- Explicit historical embedding artifacts: 65,900,984 bytes.
- Approved deletion targets: 16.

## Safety gate

PASS. All 16 exact targets existed, matched their recorded size and digest, had no protected-path overlap, and had no active-process reference. The three protected DB hashes, registry/configuration/tunnel digests, model paths, and Ollama settings matched the recorded state.

## Post-cleanup verification

All 16 manifest targets were deleted and are absent. The cleanup removed only the payloads listed in the deletion manifest:

- Blob/index payloads and SQLite stores/sidecars from `build_20260903_170620_f55487`.
- Blob/index payloads and SQLite stores/sidecars from `build_20260903_171400_4f259a`.
- Blob/index payloads and SQLite stores/sidecars from `build_20260903_171913_956e22`.
- Blob/index payload, SQLite store, and the historical 3,906×1,024 embedding matrix from `build_20260903_173745_cfa854`.
- The empty, unregistered `scratch/data/canonical_production` test store.

Historical integrity manifests and evaluation results in the four build directories were retained. No documentation, governance evidence, source, configuration, test, script, model, current index, or current embedding was deleted.

### Storage result

- Manifest-attributed reclaimed space: 780,531,821 bytes.
- C: free space before: 46,435,971,072 bytes.
- C: free space after: 48,224,477,184 bytes.
- Observed C: free-space increase: 1,788,506,112 bytes. Concurrent external filesystem activity occurred, so only 780,531,821 bytes is attributed to this cleanup.
- Known historical storage remaining: approximately 1,810,410,247 bytes, retained because it is shared, referenced, forensic evidence, or review-required.

### Current store sizes after cleanup

| Store | Directory size | Files |
|---|---:|---:|
| Phase 8.5 notebook | 409,998,851 bytes | 990 |
| Phase 8.6 notebook | 130,998,617 bytes | 284 |
| Production build | 189,849,600 bytes | 4 |
| Shared canonical-production root | 483,968,850 bytes | 1,330 |

### Protected-state validation

- Production DB SHA remains `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`.
- Phase 8.5 DB SHA remains `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`.
- Phase 8.6 DB SHA remains `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`.
- All three databases report SQLite integrity `ok`, zero foreign-key violations, and zero-byte WAL state.
- Phase 8.5 remains READY with 44 documents, 44 versions, 44 memberships, 2,658 chunks/FTS rows/embeddings, and its multimodal records intact.
- Phase 8.6 remains READY with 24 documents, 24 versions, 24 memberships, 5,843 chunks/FTS rows/embeddings, and 161 OCR/Vision/CLIP records intact.
- The notebook registry still resolves both READY notebooks and matches both manifest identities.
- Production configuration, current canonical evaluation DB/embedding matrix, BGE-M3, BGE reranker, CLIP, Ollama configuration/models, tunnel configuration, and active runtime remained unchanged.
- Certified lifecycle and active `BGE_V2_M3` state remained unchanged.

### Runtime verification

Focused registry, HTTP, MCP stdio, MCP SSE, and post-certification single-path tests passed: 27 passed, 0 failed. The existing tunnel health endpoint remained live and the active Mnemo/Ollama processes remained running.

No ingestion, reindexing, embedding generation, OCR, Vision, or CLIP command was executed during this cleanup.
