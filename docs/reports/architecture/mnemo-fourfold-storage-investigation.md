# Mnemo Four-Fold Storage Architecture Investigation

**Status:** Complete — read-only forensic investigation  
**Date:** 2026-09-08  
**Repository HEAD inspected:** `31cdfb179a15fd96153071373641d24af0b815ed`

## Executive verdict

No: Mnemo is **not currently indexing every file into all four storage systems**.

The repository contains a four-adapter architectural framework—filesystem, SQLite, Qdrant, and SurrealDB—but it does not define a four-copy persistence invariant. The current certified V2 production topology intentionally uses:

1. a content-addressed filesystem for original/blob content; and
2. SQLite for authoritative document/version/source metadata, chunks, FTS5, BGE-M3 vector projections, multimodal results, and provenance.

Qdrant is classified **INTENTIONALLY_OPTIONAL**. It is a real, functional V1 vector adapter and was exercised against a live service historically, but it is explicitly disabled in the current profile and is not wired into certified V2 retrieval.

SurrealDB is classified **PARTIALLY_IMPLEMENTED**. A graph-specific entity/edge adapter exists, but the general storage surface is largely unsupported, the tests found are mock-based, and end-to-end entity extraction plus graph retrieval remains Phase 11 roadmap work.

The wording “four storage backends” accurately describes the adapter/composition design and an earlier standard-stack aspiration. It is misleading if read as a description of the current certified deployment or as a requirement that every indexed file be replicated four times.

## What is actually running

The current `mnemo.toml` explicitly enables filesystem and SQLite while setting both `storage.qdrant.enabled` and `storage.surrealdb.enabled` to `false`. Read-only process and listener inspection found no Qdrant or SurrealDB process and no listener on the configured service ports. No service was started during this investigation.

The certified production manifest binds the corpus to:

- database: `scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db`
- governed identity: `0c6c73f9b847d204d073ddec8c2a5d2265c2a8bf2bf19bfec552e264f839af8d`
- physical SHA-256: `3157ff278a16c9978784211a5a8e77ccd1d2c648cde8496d50c7fd83d3ab458c`

The production assembler `ProductionFullMultilingualV2ServerDependencyAssemblerV1` validates that exact path, opens it through `SQLiteV2ReadOnlyRuntimeStore` using SQLite URI flags `mode=ro&immutable=1`, and binds retrieval, authorization, evidence resolution, and candidate projection to that same store. `MultilingualDenseRetrieverV2` reads BGE-M3 vectors from SQLite and cosine-scores them in process. `MultilingualSparseRetrieverV2` uses the SQLite language-text FTS/projection. Neither class calls Qdrant or SurrealDB.

## Current indexed-file data flow

```text
input file
  ├─> content-addressed filesystem blob
  └─> SQLite document + version + source membership
        ├─> extracted/derived chunks
        ├─> SQLite FTS5 projections
        ├─> SQLite BGE-M3 vector generations/projections
        ├─> asset identities and provenance
        ├─> OCR / Vision / structured projections
        └─> visual-vector projections
              ↓
       V2 dense + sparse retrieval
              ↓
       RRF → candidate builder → reranker → context → FinalQA

FinalQA execution/snapshot/transition/citation state
  └─> separate mutable operational SQLite store

Qdrant:   not contacted by current V2
SurrealDB: not contacted by current V2
```

Physical responsibilities are therefore not equivalent replicas:

| Data | Current physical home |
|---|---|
| Original file bytes | Content-addressed filesystem |
| Document/version/source identity | Authoritative SQLite corpus DB |
| Extracted and derived text | SQLite chunk/projection tables |
| Lexical index | SQLite FTS5 |
| Text embeddings | SQLite V2 vector generation/projection tables |
| Image bytes | Filesystem |
| Asset metadata and provenance | SQLite |
| OCR and Vision results | SQLite |
| CLIP/visual embeddings | SQLite visual-vector tables |
| Graph/entity data | No active certified graph store/path |
| FinalQA mutable execution state | Separate operational SQLite DB |

An inspected representative, `Act 2. panch-parmeshwar-by-munshi-premchand.pdf`, has content-addressed raw bytes under `data/canonical_production/blobs`, a document/version and original-asset reference in SQLite, and retrieval representations in SQLite. There is no current Qdrant point or SurrealDB entity representation required for that file.

## Production SQLite observation

Read-only inspection of the governed production DB found:

| Representation | Rows |
|---|---:|
| Documents | 44 |
| Versions | 44 |
| Source memberships | 44 |
| Chunks | 2,658 |
| Chunk FTS entries | 2,658 |
| Multilingual V2 embeddings | 3,019 |
| Language-text projection rows | 3,019 |
| Language-text FTS rows | 3,019 |
| Visual embeddings | 463 |
| Visual-vector projection rows | 477 |
| Asset catalog rows | 469 |
| Asset occurrences | 464 |
| OCR results | 463 |
| Vision results | 463 |
| Structured-table projections | 105 |

The 3,019 multilingual rows are not a contradiction with 2,658 chunks: the V2 projection contains independently governed representations/generations beyond the base chunk count.

## Implementation status matrix

| Storage | Designed | Interface/adapter | Persistent implementation | Configured | Tested | Current ingestion | Current V2 retrieval | Current production | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Filesystem | Yes | Yes | Yes | Enabled | Yes | Yes | Original-asset delivery | Yes | Current and required |
| SQLite | Yes | Yes | Yes, extensive | Enabled | Yes | Yes | Dense vectors + FTS5 | Yes | Current and required |
| Qdrant | Yes | Yes | Yes, V1 dense vector store | Present but disabled | In-memory unit tests and historical live acceptance | No | No | No | **INTENTIONALLY_OPTIONAL** |
| SurrealDB | Yes | Yes | Graph methods only; general surface unsupported | Present but disabled | Mock-based graph tests | No | No | No | **PARTIALLY_IMPLEMENTED** |

### Qdrant

`QdrantStore` is not a placeholder. It creates collections, writes vectors with retrieval projection payloads, searches, filters, and deletes. `CompositeStorage` historically routed V1 dense search to it. ADR-0038 explicitly says the Qdrant payload is **derived search-index state**, may be rebuilt from filesystem and SQLite, and is never authoritative.

Historical Phase 4/5 evidence and commit `94e348765` show a real Ollama/Qdrant run rather than only a mock. Commit `a96059d9` subsequently repaired disabled-backend lifecycle behavior and established the local profile with Qdrant disabled. ADR-0071 says optional backends are not enabled by migration, and ADR-0074 both preserves Qdrant optionality and rejects requiring every backend at startup.

For current V2, the missing pieces are a V2 generation-to-Qdrant synchronization path, a V2 Qdrant read adapter in the certified assembler, and matching lifecycle/coverage/certification evidence. Those are implementation gaps **only if a future deployment elects to enable Qdrant**; they are not missed requirements for the current certified profile.

### SurrealDB

`SurrealDBStore` is real but deliberately narrow. It connects to the Surreal client and implements graph-specific entity and edge operations. Most document, notebook, source, session, citation, chunk, and search methods are unsupported. `CompositeStorage` routes graph calls to it, but current ingestion does not produce an end-to-end Surreal graph and current retrieval does not query one.

ADR-0005 is only **Proposed**, not Accepted. The graph tests found use a `MockSurreal` test double; no current live SurrealDB integration test was found. The engineering roadmap assigns entity extraction, graph persistence integration, and graph retrieval to Phase 11. This makes SurrealDB partially implemented with operational use deferred—not a completed production backend and not merely a nonexistent idea.

## ADR findings

| ADR | Date/status | Storage decision | Effect on four-fold claim |
|---|---|---|---|
| ADR-0003, Configuration System | 2026-08-07, Accepted | Defines separately enabled configuration for all four adapters | Supports selectable capabilities, not mandatory four-way replication |
| ADR-0004, KnowledgeEngine Composition | 2026-08-07, Accepted | Defines the composition root; concrete service connection was then out of scope | Does not require all backends to be active |
| ADR-0005, Graph Identity Resolution | 2026-08-08, Proposed | Resolves identities for Surreal graph persistence | Shows intent, not an accepted current-production mandate |
| ADR-0038, Version-Aware Retrieval Filter Projection | 2026-08-13, Accepted | Makes Qdrant a derived, rebuildable vector projection | Explicitly keeps filesystem and SQLite authoritative |
| ADR-0039, Version-Aware Sparse Retrieval | 2026-08-13, Accepted | Puts sparse retrieval projection in SQLite FTS5 | Establishes SQLite retrieval responsibility |
| ADR-0071, Phase 8.5 Additive Migration and Index-Generation Lifecycle | 2026-08-24, Accepted | Adds SQLite generations and says migrations do not enable optional backends | Explicitly preserves Qdrant/SurrealDB optionality |
| ADR-0074, Phase 8.5 Runtime and Profile Activation | 2026-08-26, Accepted | Treats Qdrant as optional and rejects require-every-backend startup | Directly permits the certified two-store deployment |

No inspected ADR says that every indexed file **must** exist in filesystem + SQLite + Qdrant + SurrealDB simultaneously.

## Storage architecture timeline

| Date/phase | Event | Filesystem | SQLite | Qdrant | SurrealDB | Evidence |
|---|---|---|---|---|---|---|
| 2026-08-07 / early Phase 2 | Filesystem and SQLite completed; all four config surfaces defined | Implemented | Implemented | Planned/configured | Planned/configured | ADR-0003; changelog 0007/0008 |
| 2026-08-08 / Phase 2 | Qdrant adapter, Surreal graph adapter, and composite added | Composed | Composed | Implemented | Graph subset implemented | commits `3f01684a334b`, `2055b38f`, `b51d1d179`; changelog 0009–0011 |
| 2026-08-13 / Phase 4–6 | Live Qdrant dense milestone; version-aware projection governance | Canonical | Canonical + sparse | Live derived index | Outside retrieval | commit `94e348765`; ADR-0038/0039 |
| 2026-08-15 / Phase 6 | Historical hybrid retrieval release | Canonical | Sparse | Dense | Not used | commit `e2041cd0` |
| 2026-08-17 / local profile | Disabled-backend lifecycle repaired; Qdrant and Surreal disabled | Enabled | Enabled | Disabled | Disabled | commit `a96059d9`; `mnemo.toml` |
| 2026-08-24–26 / Phase 8.5 | SQLite generation lifecycle and optional backend policy accepted | Required | Required | Optional | Optional | ADR-0071/0074 |
| Current certified V2 | Immutable SQLite supplies V2 dense/sparse retrieval | Current | Current | Not used | Not used | production assembler and manifest |
| Phase 11 roadmap | Entity extraction and graph retrieval planned | Unchanged | Unchanged | Optional | Integration planned | engineering roadmap |

This is not a staged plan of “two stores now, Qdrant next, SurrealDB next.” Qdrant was implemented early and used historically, then made optional in the current profile. SurrealDB received an early graph adapter, while actual graph production behavior was left for Phase 11.

## Configuration, dependencies, tests, and deployment evidence

- `qdrant-client` and `surrealdb` are direct runtime dependencies in `mnemo-core/pyproject.toml`, not optional or dev-only packages. Dependency presence proves adapter availability, not current use.
- Full/development Compose files declare Qdrant and SurrealDB services; the minimal Compose profile disables both. Compose availability is a deployable option, not proof that the certified local runtime uses them.
- Qdrant unit tests use the real client in in-memory mode, and historical opt-in tests exercise a live service.
- Surreal graph tests use a test double. This validates adapter logic but does not prove a live production deployment.
- Current process/port inspection found neither backend running.

## Documentation contradictions

`docs/architecture/current/mnemo_architecture_v2.md` contains a “Four-Store Design” and ingestion diagrams that can be read as current all-store writes. The same document also says SurrealDB is intended/future, records that the local certified profile disables Qdrant, and elsewhere mentions SQLite vector brute force. It mixes original architecture, aspirational standard deployment, and current behavior.

`docs/architecture/current/mnemo_engineering_roadmap.md` marks the Phase 2 four-backend milestone complete and describes SurrealDB CRUD more broadly than the implementation supports. Later in that same roadmap, Phase 11 still schedules entity extraction, graph persistence, and graph retrieval.

Accordingly, the documentation is not wholly false, but its unqualified “four-store” language is outdated or misleading for the current certified V2 topology.

## Direct answers

1. **Are we currently indexing into all four storage types?** No. Current certified V2 writes/reads filesystem and SQLite representations; it does not contact Qdrant or SurrealDB.
2. **If not, was that intentional?** Yes. Current configuration disables both optional services, ADR-0071 preserves their optionality, and ADR-0074 rejects require-every-backend startup.
3. **Was there an ADR/architectural decision?** Yes. ADR-0003 established independently enabled backend configuration; ADR-0038 made Qdrant derived/non-authoritative; ADR-0071/0074 explicitly preserve optional backends.
4. **Was it planned for a later engineering phase?** SurrealDB's useful end-to-end graph path was; Phase 11 owns entity extraction and graph retrieval. Qdrant itself was already implemented and historically deployed, though current V2 integration is optional/unimplemented.
5. **Did we simply fail to implement it?** Not as a single four-fold requirement—no such mandatory current requirement was found. Qdrant is implemented but not integrated into current V2. SurrealDB is only partially implemented, consistent with later Phase 11 work.
6. **What does current certified V2 require?** A content-addressed filesystem, the governed immutable SQLite corpus DB, and a separate mutable FinalQA operational SQLite DB. Qdrant and SurrealDB are outside the certified serving path.

## Final classifications

- **Qdrant — INTENTIONALLY_OPTIONAL.** Functional and historically live-tested, derived rather than authoritative, explicitly disabled in the current profile, and not required by certified V2.
- **SurrealDB — PARTIALLY_IMPLEMENTED.** Graph adapter exists, but live integration, entity extraction, graph synchronization, and graph retrieval are absent from current production and deferred in the roadmap.

## Evidence index

### Current implementation

- `mnemo.toml` — enabled/disabled storage profile
- `mnemo-core/mnemo/storage/filesystem.py` — `FilesystemBlobStore`
- `mnemo-core/mnemo/storage/sqlite.py` — `SQLiteStore`
- `mnemo-core/mnemo/storage/qdrant.py` — `QdrantStore`
- `mnemo-core/mnemo/storage/surrealdb.py` — `SurrealDBStore`
- `mnemo-core/mnemo/storage/composite.py` — routing and compensation boundaries
- `mnemo-core/mnemo/storage/engine.py` — four-adapter construction
- `mnemo-core/mnemo/storage/v2_runtime.py` — immutable SQLite V2 runtime
- `mnemo-server/mnemo_server/services/full_multilingual_v2_production.py` — certified production assembler
- `mnemo-core/mnemo/retrieval/multilingual_dense_v2.py` — SQLite vector read and in-process cosine scoring
- `mnemo-core/mnemo/retrieval/multilingual_sparse_v2.py` — SQLite FTS/projection retrieval
- `config/production/full_multilingual_v2.production.json` — certified production topology

### Governance and history

- `docs/adr/active/ADR-0003-configuration-system.md`
- `docs/adr/active/ADR-0004-knowledge-engine-composition.md`
- `docs/adr/active/ADR-0005-graph-identity-resolution.md`
- `docs/adr/active/ADR-0038-version-aware-retrieval-filter-projection.md`
- `docs/adr/active/ADR-0039-version-aware-sparse-retrieval.md`
- `docs/adr/active/ADR-0071-phase-8-5-additive-migration-and-index-generation-lifecycle.md`
- `docs/adr/active/ADR-0074-phase-8-5-runtime-and-profile-activation.md`
- `docs/architecture/current/mnemo_architecture_v2.md`
- `docs/architecture/current/mnemo_engineering_roadmap.md`
- commits `3f01684a334baf6ac55d629045dd5c372c241e7e`, `2055b38f1dc5e078fe67a8d9fd2563fd58f45f98`, `b51d1d1791bec99ff443a3247090f52216c26cb8`, `94e3487656599fbea30b7465d76586556a3b7138`, `e2041cd0b392805a0a6f6e52e5ba2aae5856e91e`, and `a96059d9f9e61271dec96e0fc066d094dc4a6554`

No source, configuration, database, registry, model, process, or service was modified by this investigation.
