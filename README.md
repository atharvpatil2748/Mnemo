# Mnemo

> One knowledge layer. Thousands of documents. Your hardware, your data.

![Version](https://img.shields.io/badge/version-0.25.0-blue) ![Python](https://img.shields.io/badge/python-3.12-blue) ![License](https://img.shields.io/badge/license-Apache_2.0-blue) [![CI](https://github.com/atharvpatil2748/Mnemo/actions/workflows/ci.yml/badge.svg)](https://github.com/atharvpatil2748/Mnemo/actions/workflows/ci.yml)

## Why Mnemo Exists

Modern AI systems can reason extremely well, but a user's own documents are often fragmented across PDFs, books, papers, notes, notebooks, source code, emails, and documentation.

Mnemo exists to create a persistent knowledge layer over those materials.

**Mnemo is not an agent. Mnemo is not an assistant.**
It is the epistemic knowledge and evidence layer beneath them. The central question Mnemo answers is:

> *"What do my documents say about X?"*

Not: *"What should I do about X?"*

Mnemo ingests documents, understands them deeply, retrieves evidence in response to questions, persists knowledge permanently, and cites every claim it surfaces—all while maintaining deterministic architectural boundaries.

## The NotebookLM Difference

Mnemo provides a local-first, self-hosted, open-architecture alternative to cloud notebook and knowledge systems like NotebookLM.

* **Local-First Operation:** All storage and retrieval happens on your own hardware. Nothing is sent to the cloud unless you explicitly configure a remote LLM provider.
* **User-Controlled Storage:** You own your knowledge graph. No mandatory cloud dependencies.
* **Open Architecture & Plugins:** Replaceable parsers, chunkers, embedders, and LLM providers.
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

Mnemo's **architectural target** is to support **100,000 documents and 20 million chunks**. The current certified V2 topology uses a content-addressed filesystem, an immutable SQLite corpus (FTS5 plus governed BGE-M3 vectors), and a separate mutable operational SQLite store. Qdrant is an optional future vector-scale path, and SurrealDB is a partial future graph path; neither is a current production prerequisite.

*(Note: These scale benchmarks are an architectural target, not a currently benchmarked capability. Formal benchmarking will occur during Phase 13 production hardening.)*

## Architecture Overview

Mnemo strictly enforces a layered, provider-independent architecture where no layer may call upward.

### Certified production runtime

Mnemo V2 is certified and active for the 44-document production store. HTTP,
MCP stdio, and MCP SSE are transport adapters over one production application:
server-derived authorization → BGE-M3 and SQLite FTS5 retrieval → RRF → the
top 50 fused candidates → BGE-reranker-v2-m3 → governed ContextBuilder →
FinalQA. The caller's `requested_k` remains dynamic and is distinct from the
internal 50-candidate reranking pool. Mutable FinalQA records live in a separate
operational database. Ollama supplies local FinalQA and vision roles; its model
storage is external to Mnemo's reranker lifecycle.

The canonical declarative configuration is
[`config/production/full_multilingual_v2.production.json`](config/production/full_multilingual_v2.production.json),
with runtime settings in [`mnemo.toml`](mnemo.toml), pinned model identities in
[`config/model_profiles/full_multilingual_v2_profiles.toml`](config/model_profiles/full_multilingual_v2_profiles.toml),
and signed mutable activation/lifecycle records referenced by that manifest.
See the [single-production-path audit](docs/reports/architecture/mnemo-v2-single-production-path-audit.md)
and [final certification report](docs/reports/certification/current/mnemo-v2-final-certification.md).

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
       Certified Storage (content-addressed FS + immutable SQLite corpus
                          + separate mutable operational SQLite)
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
| Local Storage Layer | ✅ Implemented | Certified V2: content-addressed filesystem + immutable SQLite corpus + separate operational SQLite. Qdrant is optional V1/future scale; SurrealDB is a partial future graph adapter. |
| Document Parsing | ✅ Implemented | PDF, DOCX, PPTX, XLSX, Markdown, HTML, plain text/source code, JSON, CSV (Phase 3) |
| Ingestion Canonicalization | ✅ Complete | Canonical `ParsedDocument` bridge (Phase 3.9) |
| Chunking Engine | ✅ Complete | Modules 4.1–4.10: dispatcher plus all nine document-aware V2 strategies (Phase 4) |
| Embedding Pipeline | ✅ Released | Content-addressed embedding cache and batch vector generation (Phase 5) |
| Hybrid Retrieval & Grounded QA | ✅ Implemented and validated | Title-aware sparse retrieval, optional dense retrieval, fusion/reranking, strict persisted Final QA, citation correction, immutable replay (ADRs 0052–0057). |
| REST API & Streaming | ✅ Released; Phase 8.8 hardening planned | Milestone M7 REST and legacy V1 WebSocket/SSE exist. Phase 9 chat requires authenticated FinalQA V2 or a separately certified authenticated V2 streaming contract. |
| Native MCP Integration | ✅ 14 tools registered; Phase 8.8 hardening planned | Six retained knowledge tools, four bounded delivery tools, and four V2 evidence/capability/FinalQA tools over stdio/SSE. Runtime convergence, authorization, compatible readers, metadata, capability truth, errors, and tunnel parity remain Phase 8.8 work. |
| Advanced Retrieval & Multimodal Foundation | ✅ Implemented & evaluated | Phase 8.5 is certified for its exact 44-document production identity. OCR, Vision, CLIP, and BGE-M3 foundations are validated; dedicated semantic image discovery through MCP is not currently exposed and is planned as `search_images` in Phase 8.8. |
| Phase 8.6 evaluation notebook | ✅ Validated; evaluation-only | Format-diverse multilingual corpus with structure-aware chunking, OCR, Vision, CLIP, BGE-M3, provenance, canonical manifests, isolation, and transport validation; not production-exposed. |
| Phase 8.8 | 📋 Designed, not implemented | Final MCP/runtime convergence and Phase 9 readiness gates, including planned `search_images`. |
| Web UI | 📋 Planned after Phase 8.8 verification | Phase 9 is the next implementation phase, but has not started. |
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

```console
# Start the HTTP/REST and WebSocket server (port 8000)
mnemo serve

# Check health probe
curl -s http://127.0.0.1:8000/health
```

### 3. Run the Native MCP Server

Mnemo currently registers 14 Model Context Protocol tools: six retained
knowledge tools, four bounded delivery tools, and four V2 tools. Registration
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

Phase 8.8 plans one additional tool, `search_images`, for OCR, caption/Vision,
CLIP text-to-image, and governed hybrid discovery. It becomes a 15-tool surface
only after implementation and verification. `search_images` will return stable
notebook/source/document/version/occurrence/asset identities and human-readable
metadata where available; `get_asset` remains exact binary delivery.

### 4. Setup and Validation
Clone the repository and run the validation script to ensure your environment is clean:

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
* [Contributing Guide](CONTRIBUTING.md) - How to contribute to the project.
* [Engineering Changelog](docs/changelog/README.md) - Current index and detailed historical module releases.

## Roadmap

Mnemo's roadmap is structured to ensure every phase produces a runnable, testable artifact.

* **COMPLETED (Phases 0–8):** Core scaffolding, storage, canonical ingestion, deterministic V2 chunking, embedding pipeline, hybrid retrieval & grounded QA (Milestone M6), REST/WebSocket APIs & Auth (Milestone M7), and Native MCP Server (Milestone M8) are complete and certified.
* **COMPLETED/CERTIFIED (Phase 8.5):** Exact 44-document V2 production composition, production-parity evaluation, durable BGE activation/rollback, authenticated FinalQA, and transport parity. Historical Golden evaluation and later production-parity evaluation remain distinct evidence identities.
* **COMPLETED/VALIDATED (Phase 8.6):** Isolated 24-document format-diverse multilingual evaluation notebook; not production-exposed.
* **COMPLETED CAPABILITY MILESTONE (Phase 8.7):** 14 registered MCP tools and real client exercises. Defects discovered by the later audits are Phase 8.8 inputs, not retroactive Phase 8.7 claims.
* **NEXT HARDENING (Phase 8.8):** Designed, not implemented. Converges certified MCP runtime/contracts and establishes the mutable-workspace and authenticated-V2-chat gates.
* **NEXT IMPLEMENTATION AFTER VERIFICATION (Phase 9):** Web UI React frontend. Phase 9 starts only after `Phase 8.8 VERIFIED → Phase 9 GO`.
* **FUTURE (Phases 10–13):** Notebook features, cross-document reasoning, plugin ecosystem, and production hardening.

See the complete execution plan in the [Engineering Roadmap](docs/architecture/current/mnemo_engineering_roadmap.md).

## Contributing

Interested in working on Mnemo?

Whether you're interested in building a new parser, optimizing vector storage, or shaping the retrieval algorithms, we welcome your help!

Please read our [Contributing Guide](CONTRIBUTING.md) to understand our architectural rules, local setup, and PR expectations before opening a pull request.
