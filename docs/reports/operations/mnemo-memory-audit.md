# Mnemo Memory and Artifact Audit

Status: **MNEMO_MEMORY_AUDIT_AND_CLEANUP_PASS**.

## Scope and safety boundary

This audit inventories repository artifacts, caches, retained evaluation stores, model locations, runtime dependencies, user caches, and large temporary directories. The entire source and test tree is protected. No source, test, script, configuration, database, model, dataset, governance record, certification evidence, or active runtime dependency is a cleanup target.

The machine-readable inventory is `scratch/mnemo-memory-audit.json`. The exact deletion plan is `scratch/mnemo-memory-deletion-manifest.json`.

## Storage summary before cleanup

| Location | Used | Free |
|---|---:|---:|
| C: | 414,336,888,832 bytes | 33,756,332,032 bytes |
| D: | 148,918,657,024 bytes | 400,836,104,192 bytes |

The repository contains 94,044 files totaling 10,758,477,557 bytes. Its largest top-level area is `scratch/` at 6,603,298,366 bytes.

## Protected and active state

- Production corpus: `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`, SHA-256 `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`, 44 documents, 44 versions, 2,658 chunks, integrity `ok`, zero foreign-key violations.
- Phase 8.5 notebook: SHA-256 `bc048cc15173acbd818b98786a3380a01f2263843a435708f6814c6de21a1d84`, 44 documents, 2,658 chunks, integrity `ok`.
- Phase 8.6 notebook: SHA-256 `9a3521f8cefc74e2673592dbd207a7f5673dcfc05cebfdc18899d93be93307a2`, 24 documents, 5,843 chunks, integrity `ok`.
- Registry: Phase 8.5 identity `6b52d36fb5f3c60e7126a0236dfab52061e831a748b1da49b951f3228725f31a`; Phase 8.6 identity `8f4aeda7be411065f570fd798f3465b5076f78db06469c9f80d16424d325b1ed`.
- Production lifecycle remains `CERTIFIED`; V2 is exposed and `BGE_V2_M3` is active.
- Ollama remains at `D:\Ollama\models`; `OLLAMA_NUM_PARALLEL` remains `4`.
- Live Mnemo MCP processes use `.venv`; the live tunnel uses `C:\Users\athar\AppData\Roaming\tunnel-client\mnemo.yaml`.

## Largest candidate classes

| Class | Approximate size | Decision |
|---|---:|---|
| Shared Hugging Face cache | 24.42 GB | `REVIEW_REQUIRED`; cross-project models and uncertain ownership |
| User Temp | 9.62 GB | `REVIEW_REQUIRED`; large Visual Studio/VS Code updater payloads, external ownership |
| npm cache | 7.09 GB | `REBUILD_COST_HIGH`; shared across projects and active `_npx` consumers |
| GPU preflight environment | 3.43 GB | `REBUILD_COST_HIGH`; retained for governed GPU evaluation/reindex tooling |
| Codex runtime cache | 1.38 GB | `ACTIVE` |
| Puppeteer browser cache | 1.39 GB | `REVIEW_REQUIRED`; may serve other projects/tooling |
| WP-10 remediation artifacts | 780.70 MB | `HISTORICAL_REVIEW_REQUIRED` |
| Evaluation notebooks | 541.00 MB | `ACTIVE` |
| WP-16 artifacts | 400.84 MB | `HISTORICAL_REVIEW_REQUIRED` |
| Phase 8.5.11 artifacts | 377.46 MB | `HISTORICAL_REVIEW_REQUIRED` |

The top 50 repository files include active databases, protected evidence, environment DLLs, Git packs, and exact corpus copies. None is safe for automatic deletion.

## Duplicate analysis

Files of at least 1 MiB under `scratch/` and `docs/` were grouped by byte length and verified with SHA-256. Large exact duplicates exist, including 66.1 MB, 32.3 MB, 26.8 MB, and 21.2 MB source assets replicated across active notebooks and historical evaluation stores. These are not disposable duplicates: their paths and content-addressed placement are part of notebook/evaluation reproducibility. No duplicate data file was approved for deletion.

## Safe cleanup plan

Only generated repository-local caches and coverage outputs are approved:

- root, `mnemo-core`, and `mnemo-server` mypy caches;
- root Ruff and empty Pytest caches;
- `.coverage` and `coverage.xml`.

Estimated recovery is 205,754,947 bytes. `__pycache__` directories are deliberately retained because live Python services are running and the additional recovery is small. Shared user caches and Temp content are not included.

## Safety gate

The planned targets resolve to exact paths within the workspace, are reproducible generated outputs, and do not overlap source, tests, scripts, configuration, databases, models, datasets, notebooks, registry, documentation, Git state, Ollama, or active environments. The safety gate passes only for the listed targets.

## Post-cleanup validation

The six non-empty generated targets were deleted. The empty `.pytest_cache` directory could not be inspected because Windows denied access; it represented zero measured bytes, so its permissions were not changed and it was retained.

| Measure | Result |
|---|---:|
| Deleted bytes by file length | 205,754,947 |
| Observed C: free-space increase | 203,796,480 |
| C: free space after | 33,960,128,512 |
| D: free space after | 400,836,104,192 |

The difference between summed file lengths and filesystem free-space movement is expected from allocation accounting and concurrent system activity.

Independent after-state checks confirmed:

- production DB SHA-256 remained `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`;
- Phase 8.5 and Phase 8.6 notebook DB hashes remained unchanged;
- all three DBs returned SQLite integrity `ok`, zero foreign-key violations, and zero-byte WAL files;
- notebook registry and production configuration hashes remained unchanged;
- Phase 8.5 and Phase 8.6 registry identities still resolve to the same READY stores;
- `OLLAMA_MODELS` remained `D:\Ollama\models` and `OLLAMA_NUM_PARALLEL` remained `4`;
- Ollama still listed all six previously configured models;
- the tunnel health endpoint returned `live` and the tunnel process remained active;
- live Mnemo Python/MCP processes remained active from `.venv`;
- 27 focused production-manifest, registry, HTTP startup, MCP stdio, and MCP SSE tests passed. The run emitted one Starlette deprecation warning and a non-failing pytest Temp cleanup permission message;
- no source, test, script, configuration, model, database, dataset, documentation history, or certification evidence was deleted or changed by cleanup.

## Deferred review items

The largest remaining opportunities require user-level ownership decisions and were not deleted:

- 24.42 GB Hugging Face cache shared by multiple models/projects;
- 9.62 GB user Temp content, including a 3.29 GB Visual Studio installer payload and repeated 131.7 MB installer extraction directories;
- 7.09 GB shared npm cache;
- 3.43 GB GPU preflight environment;
- historical Phase 8.5/WP-10/WP-16 databases and evidence;
- large exact duplicate corpus assets whose independent paths preserve active notebook or evaluation reproducibility.

These remain `REVIEW_REQUIRED` or `REBUILD_COST_HIGH`; none was silently treated as obsolete.
