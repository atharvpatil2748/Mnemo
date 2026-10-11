# Mnemo

> One knowledge layer. Thousands of documents. Your hardware, your data.

Copyright © 2026 Atharv Patil.
All rights reserved.

Mnemo is proprietary software. Its source code and
project-owned documentation are not offered under an
open-source license. No license to use, copy, modify,
distribute, sublicense, or commercially exploit the
proprietary material is granted without prior written
permission from Atharv Patil, except where applicable
law or pre-existing rights provide otherwise.

Unauthorized use or redistribution is prohibited
to the extent permitted by applicable law.

This notice applies to Mnemo-owned material in the current tree. Third-party
materials retain their own terms and notices; earlier licensed versions retain
rights already granted. See the [distribution policy](docs/governance/active/proprietary_distribution_policy.md).

![Version](https://img.shields.io/badge/version-0.25.0-blue) ![Python](https://img.shields.io/badge/python-3.12-blue)

## Why Mnemo Exists

Modern AI systems can reason extremely well, but a user's own documents are often fragmented across PDFs, books, papers, notes, notebooks, source code, emails, and documentation.

Mnemo exists to create a persistent knowledge layer over those materials.

**Mnemo is not an agent. Mnemo is not an assistant.**
It is the epistemic knowledge and evidence layer beneath them. The central question Mnemo answers is:

> *"What do my documents say about X?"*

Not: *"What should I do about X?"*

Mnemo ingests documents, understands them deeply, retrieves evidence in response to questions, persists knowledge permanently, and cites every claim it surfaces—all while maintaining deterministic architectural boundaries.

## The NotebookLM Difference

Mnemo provides a local-first, self-hosted alternative to cloud notebook and knowledge systems like NotebookLM.

* **Local-First Operation:** All storage and retrieval happens on your own hardware. Nothing is sent to the cloud unless you explicitly configure a remote LLM provider.
* **User-Controlled Storage:** You own your knowledge graph. No mandatory cloud dependencies.
* **Modular Architecture & Plugins:** Replaceable parsers, chunkers, embedders, and LLM providers.
* **No SaaS Rate Limits:** Because Mnemo runs locally, there is no hosted SaaS query quota. Practical limits are determined entirely by your local compute, storage, models, and workload.

## Cross-Document & Cross-Notebook Retrieval

Mnemo is architected to perform deep synthesis across disparate sources and organizational boundaries.

### Cross-Document Example
Suppose you have a research paper, a textbook, lecture notes, a project report, and a technical specification in the same notebook. Mnemo is designed to answer conceptual queries like:

> *"Compare the explanation of gradient descent in my ML textbook with the approach used in these three research papers. Where do they agree, and where do they differ?"*

> *"Across all my documents, what evidence supports or contradicts the claim that X?"*

### Cross-Notebook Example
Knowledge doesn't live in silos. If you maintain multiple notebooks—like *Machine Learning Research*, *Course Notes*, *Research Papers*, and *Project Experiments*—Mnemo's global architecture is designed to synthesize insights across them:

> *"Across all my notebooks, what have I learned about transformer-based models, and which conclusions are supported by experimental evidence?"*

## Designed to Scale

Users shouldn't be forced into a "10 documents per notebook" mental model.

Mnemo's **architectural target** is to support **100,000 documents and 20 million chunks**. The formerly certified V2 topology used a content-addressed filesystem, an immutable SQLite corpus (FTS5 plus governed BGE-M3 vectors), and a separate mutable FinalQA operational SQLite store. That exact historical index was retired on 2026-10-10; its certification is retained as historical evidence, not current serving authority. ADR-0077's separately governed mutable filesystem + SQLite user workspace and mandatory read-only fallback are implemented and certified. Qdrant is an optional future vector-scale path, and SurrealDB is a partial future graph path; neither is a current production prerequisite.

*(Note: These scale benchmarks are an architectural target, not a currently benchmarked capability. Formal benchmarking will occur during Phase 13 production hardening.)*

## Architecture Overview

Mnemo strictly enforces a layered, provider-independent architecture where no layer may call upward.

### Production baseline: offline and unindexed

Production selection is explicitly `UNINDEXED` in
[`config/production/runtime-selection.json`](config/production/runtime-selection.json).
HTTP and MCP reject retrieval before loading a historical binding, including
when HTTP lifespan startup is bypassed. No production notebook or index is
currently available. The former 44-document V2 certification describes a
retired, exact-identity deployment; it does **not** authorize this unindexed
baseline or a future index. That historical composition used HTTP,
MCP stdio, and MCP SSE as transport adapters over one application:
server-derived authorization → BGE-M3 and SQLite FTS5 retrieval → RRF → the
top 50 fused candidates → BGE-reranker-v2-m3 → governed ContextBuilder →
FinalQA. The caller's `requested_k` remains dynamic and is distinct from the
internal 50-candidate reranking pool. Mutable FinalQA records live in a separate
purpose-specific operational database; it is not the future user workspace.
Without a valid, separately governed ADR-0077 workspace configuration,
production workspace mutations remain server-enforced read-only. Ollama supplies local FinalQA and vision roles; its
model storage is external to Mnemo's reranker lifecycle.

The retained **historical** declarative configuration is
[`config/production/full_multilingual_v2.production.json`](config/production/full_multilingual_v2.production.json),
which is not a fallback or a setup instruction. Current relative, unindexed
runtime settings are in [`mnemo.toml`](mnemo.toml); historical pinned model identities are in
[`config/model_profiles/full_multilingual_v2_profiles.toml`](config/model_profiles/full_multilingual_v2_profiles.toml),
and signed mutable activation/lifecycle records referenced by that manifest.
See the [single-production-path audit](docs/reports/architecture/mnemo-v2-single-production-path-audit.md)
and [final certification report](docs/reports/certification/current/mnemo-v2-final-certification.md).
The [pre-Phase-8.9 reset record](docs/reports/architecture/phase-8-9-runtime-cutover-execution.md)
describes the five decommissioned stores. Future production and user notebooks
need explicit, server-controlled ownership/grants and a separately governed
index-publication lifecycle; the current `UNINDEXED` guard does not certify
indexed multi-user serving. Existing V1 and V2 contracts remain historical
code capabilities and can be exercised in disposable fixtures, not against a
live production index.

```text
User / AI Assistant / Antigravity / Client
       │
       ├── REST API (Layer 2 — Complete)
       ├── Legacy V1 WebSocket / SSE (implemented;
       │                              not Phase 9 V2 chat authority)
       ├── Native Model Context Protocol (MCP) (Layer 2 — Complete)
       ├── Asset provenance + parser extraction (Phase 8.5.1–8.5.2 — Implemented/Tested)
       ├── Durable processing + cost governance (Phase 8.5.3 — Implemented/Tested)
       ├── Governed OCR derivations (Phase 8.5.4 — Implemented/Tested)
       ├── Vision + visual-vector derivations (Phase 8.5.5 — Implemented/Tested)
       ├── Advanced ranked/exhaustive retrieval (Phase 8.5.6 core + WP-07 HTTP/MCP exposure — Implemented/Tested)
       ├── Structured retrieval + safe aggregation (Phase 8.5.7 — Implemented/Tested)
       ├── Multimodal context/citations/Final-QA V2 (Phase 8.5.8 — Implemented/Tested)
       ├── Multilingual processing/retrieval (Phase 8.5.9 — Implemented/Tested)
       ├── Bounded HTTP/MCP V2 delivery (Phase 8.5.10 — Implemented/Tested)
       └── Web UI (Layer 3 — Planned Phase 9)
            │
            ▼
       Mnemo Server (Layer 2 — FastAPI, Uvicorn & MCP)
            │
            ▼
       Mnemo Core (Layer 1 — Domain Engine)
            │
     ┌──────┼────────┐
     ▼      ▼        ▼
 Ingestion Retrieval Notebook
     │      │        │
     └──────┼────────┘
            ▼
       Certified Storage (content-addressed FS + immutable SQLite corpus)
       Governed Operational (separate mutable FinalQA/activation/certification)
       Planned ADR-0077 Workspace (separate mutable FS + SQLite;
                                  read-only fallback until valid/certified)
       Optional/Future (Qdrant vector scale + SurrealDB graph)
```

### Core Architectural Principles
* **Local-first:** The system operates entirely offline by default.
* **Citation-grounded:** Persisted Final QA (`POST
  /v1/notebooks/{notebook_id}/final-qa`) validates exact `[source:N]` markers,
  stores immutable execution provenance, and replays idempotently without a
  second model call. `/v1/query` remains a non-persistent evidence/search
  preview.
* **Provider-independent:** Parsers, chunkers, and embedders are replaceable plugins behind typed contracts.
* **Interface-driven:** Core logic relies on `Protocol` interfaces, not concrete implementations.
* **Knowledge engine, not agent:** It retrieves evidence; it does not plan actions.
* **Retrieval before reasoning:** Facts are gathered deterministically before any synthesis occurs.
* **Explicit backend capability:** Historical V1 profiles may degrade to sparse retrieval when optional Qdrant is disabled. Certified V2 does not depend on Qdrant; it uses SQLite-resident BGE-M3 vectors plus FTS5 and reports unavailable capabilities truthfully.

## Built For

Mnemo's component-based design allows it to serve multiple roles:
* **A standalone local knowledge engine** (via REST, CLI, and the planned Web UI)
* **A grounding/retrieval layer for AI assistants** (via native Model Context Protocol)
* **An MCP knowledge backend** (Validated natively with Antigravity and MCP clients)
* **A retrieval backend for custom applications** (via the REST API and WebSocket streaming)
* **A persistent research/document memory system**

## Current Capabilities

Mnemo is in active engineering development. Every module is rigorously tested before being marked complete.

| Capability | Status | Notes |
|---|---|---|
| Typed Domain Model | 🧊 Frozen | Core schemas and contracts (Phases 0–1) |
| Configuration System | ✅ Implemented | Immutable configuration authority (Phase 1) |
| Plugin Registry | ✅ Implemented | Discovers and injects providers (Phase 1) |
| Local Storage Layer | ✅ Certified reads/operational state and governed workspace boundary | Certified V2 uses content-addressed filesystem + immutable SQLite corpus + separate purpose-specific operational state. ADR-0077's mutable user workspace and mandatory read-only fallback are implemented and certified. Qdrant is optional V1/future scale; SurrealDB is a partial future graph adapter. |
| Document Parsing | ✅ Implemented | PDF, DOCX, PPTX, XLSX, Markdown, HTML, plain text/source code, JSON, CSV (Phase 3) |
| Ingestion Canonicalization | ✅ Complete | Canonical `ParsedDocument` bridge (Phase 3.9) |
| Chunking Engine | ✅ Complete | Modules 4.1–4.10: dispatcher plus all nine document-aware V2 strategies (Phase 4) |
| Embedding Pipeline | ✅ Released | Content-addressed embedding cache and batch vector generation (Phase 5) |
| Hybrid Retrieval & Grounded QA | ✅ Implemented and validated | Title-aware sparse retrieval, optional dense retrieval, fusion/reranking, strict persisted Final QA, citation correction, immutable replay (ADRs 0052–0057). |
| REST API & Streaming | ✅ Released; Phase 8.8 hardening in progress | Milestone M7 REST and legacy V1 WebSocket/SSE exist. Authenticated HTTP FinalQA V2 is the accepted production chat path; V1 streaming is non-production and V2 streaming is optional future work. |
| Native MCP Integration | ✅ 15 registered in the working tree; 8.8.1 runtime convergence certified | Historical 14-tool inventory plus additive `query_notebook_v2`. Stage 5 and the 8.8.5/8.8.7/8.8.2f/8.8.4/8.8.8 batch have local acceptance, not phase-wide or external certification. Four-transport behavioral parity moves to Phase 8.9. |
| Advanced Retrieval & Multimodal Foundation | ✅ Scoped historical implementation; no current production index | Phase 8.5 certification applied to its exact, now-retired identity. V2 automatic query can consider ready OCR/Vision and compatible visual/multilingual evidence within one notebook in suitable isolated data; multi-notebook, selected-document and automatic structured search remain Phase 8.9 plans. No mandatory `search_images` is planned. |
| Phase 8.6 evaluation corpus | ✅ Historically validated; index retired | The 24 original sources and rebuild manifest remain; the previously validated evaluation index was decommissioned and is not production-exposed. |
| Phase 8.8 | 🚧 Scoped checkpoint, not phase-verified | Active roadmap stops at 8.8.8. 8.8.1 is certified; 8.8.2–8.8.8 have local acceptance evidence, not phase-wide external certification. 8.8.14a–c and locally accepted 8.8.10/11 remain historical evidence. |
| Phase 8.9 | 📋 Planned, not implemented/certified | Governed shared search, membership-backed scope, automatic hybrid/structured retrieval, provenance and real transport parity; exact-identity GO/NO-GO gates Phase 9. |
| Web UI | 📋 Planned after Phase 8.9 GO | Phase 9 has not started. |
| Cross-Doc Reasoning | 📋 Planned | Phase 11 |

## Quick Start

### 1. Requirements
* **Python 3.12**
* **`uv` 0.12.2** or compatible
* **Node.js 22** and **pnpm 11.16** (for UI scaffold)
* **Docker** with Compose (for integration checks)

Token counting requires an explicit user-initiated provisioning step:

```console
mnemo provision-tokenizer
```

The command downloads the frozen `o200k_base` asset directly from upstream,
verifies its SHA-256, and installs it in user-local content-addressed storage.
Mnemo does not bundle the asset, and chunking never accesses the network.

### 2. Start the REST & Streaming Server

**Current operational boundary:** Production is offline and explicitly
`UNINDEXED`. The commands below describe entry points, not an available indexed
retrieval deployment. Notebook-scoped production serving fails closed until a
separately authorized, verified publication exists; do not point these commands
at a historical evaluation database or retired signed binding.

```console
# Start the HTTP/REST and WebSocket server (port 8000)
mnemo serve

# Check health probe
curl -s http://127.0.0.1:8000/health
```

### 3. Run the Native MCP Server

Mnemo currently registers 15 Model Context Protocol tools: six retained
knowledge tools, four bounded delivery tools, four earlier V2 tools, and the
additive `query_notebook_v2` working-tree tool. Registration
does not by itself prove configured/ready/active/exposed/scope-available state;
Phase 8.8 owns that production-contract convergence.

```console
# Run MCP server over stdio (for Antigravity, Claude Desktop, Cursor)
mnemo-mcp --transport stdio

# Run MCP server over SSE (port 8001)
mnemo-mcp --transport sse --host 127.0.0.1 --port 8001
```

**Registered MCP Tools:**
- `list_notebooks`: Discover accessible notebooks and source counts.
- `query_notebook`: Execute grounded question answering with citations or evidence-only retrieval (`synthesize=false`).
- `search_all_notebooks`: Hybrid semantic/keyword search across all notebooks.
- `get_notebook_summary`: Retrieve notebook-level overview and source inventory.
- `get_source_insights`: Retrieve extracted source-level insights.
- `get_timeline`: Retrieve chronologically ordered notebook activity events.
- `get_document`: Retrieve bounded typed blocks or authorized original bytes.
- `get_document_chunk`: Retrieve an exact authorized chunk and ancestry.
- `get_asset`: List derivation-enriched occurrences or retrieve one authorized original asset/range.
- `get_image_analysis`: Retrieve explicit, latest-ready, or all bounded authorized OCR/vision derivations.
- `search_evidence`: Search authorized typed evidence in governed ranked or exhaustive modes.
- `query_structured`: Execute allowlisted typed structured retrieval when its projection is available.
- `run_final_qa_v2`: Execute or replay authenticated, persisted FinalQA V2.
- `get_capabilities`: Report truthful lifecycle and scope-qualified capability state.
- `query_notebook_v2` (working tree, not yet deployed/certified): Server-planned
  canonical plus active derived evidence over one unambiguous authorized notebook;
  returns evidence and coverage, not a synthesized answer.

PaddleOCR is an opt-in `OCRProviderV1` implementation in
`mnemo-core/mnemo/ocr_paddle.py`. Its optional `mnemo-core[ocr-paddle]` dependency
does not install or activate an OCR generation by itself. An operator must
provision approved local detection/recognition model trees, bind their hashes and
the package/model revision in a new OCR profile, run the governed worker on a
new isolated notebook, and build complete projections before V2 can search the
results. The former Phase 8.5 production and Phase 8.6 evaluation indexes are
retired; their original source corpora remain. Any future isolated rebuild must
verify its selected OCR provider, model/runtime, and derived search coverage.
Cross-language quality
and grounded V2 answer generation are not certified by this adapter.

The Phase 8.9 target is one shared authorized search application service for
MCP, HTTP and future UI. It should consider canonical, OCR, Vision, compatible
CLIP/multilingual and applicable structured evidence without modality hints.
The currently registered `query_notebook_v2` is evidence-first and limited to
one unambiguous notebook; it is not yet cross-notebook or automatic structured
search. Frozen V1 `query_notebook`/`search_all_notebooks` remain canonical-only.
`get_asset` and `get_image_analysis` remain exact recovery operations. The
former dedicated `search_images` plan is retired as a mandatory tool; proposed
`search`/`POST /v2/search` are not yet registered. See [ADR-0080](docs/adr/active/ADR-0080-phase-8-9-unified-authorized-retrieval-plan.md).

Tool registration is not proof that a service is configured, callable for an
authorized scope, or certified. In particular, exact persisted
`get_document_chunk` reads can succeed while broader `get_document` delivery
is unavailable for a production document lacking a registered parsed-document
representation. Use `get_capabilities` for the effective service state. The
older/newer SQLite schema MCP matrix passed locally with disposable fixtures;
its in-memory parsed blocks do not establish production document delivery or
external ChatGPT verification of the complete Stage 5 code set.

### 4. Setup and Validation
In an owner-authorized checkout, run the validation script to ensure your environment is clean:

```shell
# Windows
validate.bat
```
*(On other platforms, follow the development commands below).*

### 5. Test the Python Baseline
Mnemo relies on strict linting, type checking, and testing:

```shell
uv sync --locked --all-packages
uv run ruff format --check .
uv run ruff check .
uv run mypy mnemo-core/mnemo mnemo-server/mnemo_server
uv run pytest
```

On the existing Windows checkout, run tests through the selected interpreter:
`.\.venv\Scripts\python.exe -m pytest`. This ensures its `pytest-cov` plugin
handles the coverage options in `pytest.ini`; a bare `pytest` may resolve to a
different installation and reject `--cov`. The former
`scratch/.venv-gpu-preflight` was manually removed. The optional CUDA preflight
now selects `.venv/Scripts/python.exe` and fails closed when it is missing;
see the [pre-Phase-8.9 readiness report](docs/reports/architecture/pre-phase-8-9-final-readiness-report.md).

### 6. Build the Packages
```shell
uv build --all
```

### 7. Python API Usage
The core knowledge engine can be initialized programmatically:

```python
from mnemo import KnowledgeEngine, MnemoConfig

config = MnemoConfig.from_file("mnemo.toml")
engine = KnowledgeEngine(config)
await engine.initialize()
# Ready for interactions...
await engine.shutdown()
```

## Development

Mnemo enforces a strict development standard:
* **Environment:** Managed by `uv`.
* **Testing:** `pytest` with a 90%+ coverage expectation.
* **Linting & Formatting:** `ruff`.
* **Type Checking:** `mypy` running in strict mode (`disallow_untyped_defs = true`).
* **Validation:** All commits must pass the pre-commit hooks (`uv run pre-commit run --all-files`).

## Documentation Map

To understand the system in depth, consult the authoritative documentation in the `docs/` directory:

* [Documentation authority and navigation](docs/README.md) - Current documents, historical records, and report categories.
* [Architecture Specification v2.0](docs/architecture/current/mnemo_architecture_v2.md) - Full design and philosophy.
* [Engineering Roadmap](docs/architecture/current/mnemo_engineering_roadmap.md) - The master execution plan.
* [Phase 8.5 Architecture](docs/architecture/historical/phase8.5_architecture.md) - Accepted additive architecture retained with the completed phase history.
* [Phase 8.5 Engineering Roadmap](docs/architecture/historical/mnemo_phase8_5_engineering_roadmap.md) - Dedicated implementation and certification plan.
* [Architecture Decision Records (ADRs)](docs/adr/README.md) - Historical records and the Phase 8.5 successor package.
* [Proprietary distribution policy](docs/governance/active/proprietary_distribution_policy.md) - Current-tree rights and historical-license limits.
* [Engineering Changelog](docs/changelog/README.md) - Current index and detailed historical module releases.

## Roadmap

Mnemo's roadmap is structured to ensure every phase produces a runnable, testable artifact.

* **COMPLETED (Phases 0–8):** Core scaffolding, storage, canonical ingestion, deterministic V2 chunking, embedding pipeline, hybrid retrieval & grounded QA (Milestone M6), REST/WebSocket APIs & Auth (Milestone M7), and Native MCP Server (Milestone M8) are complete and certified.
* **COMPLETED/CERTIFIED (Phase 8.5):** Exact 44-document V2 production composition, production-parity evaluation, durable BGE activation/rollback, authenticated FinalQA, and transport parity. Historical Golden evaluation and later production-parity evaluation remain distinct evidence identities.
* **HISTORICALLY VALIDATED (Phase 8.6):** The isolated 24-document format-diverse multilingual evaluation index was validated for its exact identity and later decommissioned; its original sources remain. It is not production-exposed.
* **COMPLETED CAPABILITY MILESTONE (Phase 8.7):** 14 registered MCP tools and real client exercises. Defects discovered by the later audits are Phase 8.8 inputs, not retroactive Phase 8.7 claims.
* **PHASE 8.8 CHECKPOINT:** Active scope ends at 8.8.8; 8.8.1 runtime is certified, 8.8.2–8.8.8 have scoped local acceptance. 8.8.14a–c and 8.8.10/11 accepted work remains historical evidence, not a phase-wide verification.
* **NEXT PLANNED PHASE (8.9):** Shared authorized retrieval and external-client certification. Transport parity, provenance and Phase 9 readiness formerly assigned to 8.8.9/13/14d belong here. The [Engineering Roadmap](docs/architecture/current/mnemo_engineering_roadmap.md) is authoritative.
* **PHASE 9:** Web UI begins only after the exact-identity Phase 8.9 GO gate; it has not started.
* **FUTURE (Phases 10–13):** Notebook features, cross-document reasoning, plugin ecosystem, and production hardening.

See the complete execution plan in the [Engineering Roadmap](docs/architecture/current/mnemo_engineering_roadmap.md).
