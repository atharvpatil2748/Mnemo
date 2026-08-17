# Mnemo

> One knowledge layer. Thousands of documents. Your hardware, your data.

![Version](https://img.shields.io/badge/version-0.23.0-blue) ![Python](https://img.shields.io/badge/python-3.12-blue) ![License](https://img.shields.io/badge/license-Apache_2.0-blue) [![CI](https://github.com/atharvpatil2748/Mnemo/actions/workflows/ci.yml/badge.svg)](https://github.com/atharvpatil2748/Mnemo/actions/workflows/ci.yml)

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

Mnemo's **architectural target** is to support **100,000 documents and 20 million chunks**. To support a massive corpus of PDFs, notebooks, books, papers, notes, source code, emails, and presentations, the repository leverages:
* Qdrant (HNSW vector indexing)
* SQLite FTS5 (Sparse keyword retrieval)
* SurrealDB (Graph, metadata, and relations)
* Content-addressable local filesystem storage

*(Note: These scale benchmarks are an architectural target, not a currently benchmarked capability. Formal benchmarking will occur during Phase 13 production hardening.)*

## Architecture Overview

Mnemo strictly enforces a layered, provider-independent architecture where no layer may call upward.

```text
User / AI Assistant / Antigravity / Client
       │
       ├── REST API (Layer 2 — Complete)
       ├── WebSocket / SSE (Layer 2 — Complete)
       ├── Native Model Context Protocol (MCP) (Layer 2 — Complete)
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
       Local Storage (Qdrant, SQLite, SurrealDB, FS)
```

### Core Architectural Principles
* **Local-first:** The system operates entirely offline by default.
* **Citation-grounded:** Every retrieved statement is traceable to a source, page, and chunk.
* **Provider-independent:** Parsers, chunkers, and embedders are replaceable plugins behind typed contracts.
* **Interface-driven:** Core logic relies on `Protocol` interfaces, not concrete implementations.
* **Knowledge engine, not agent:** It retrieves evidence; it does not plan actions.
* **Retrieval before reasoning:** Facts are gathered deterministically before any synthesis occurs.
* **Graceful degradation:** If a non-essential backend (e.g. Qdrant) is disabled, retrieval continues gracefully over available sparse streams.

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
| Local Storage Layer | ✅ Implemented | Qdrant, SQLite FTS5, SurrealDB, FS with atomic composite transactions (Phase 2) |
| Document Parsing | ✅ Implemented | PDF, DOCX, Markdown, HTML, TXT, JSON, CSV (Phase 3) |
| Ingestion Canonicalization | ✅ Complete | Canonical `ParsedDocument` bridge (Phase 3.9) |
| Chunking Engine | ✅ Complete | Modules 4.1–4.10: dispatcher plus all nine document-aware V2 strategies (Phase 4) |
| Embedding Pipeline | ✅ Released | Content-addressed embedding cache and batch vector generation (Phase 5) |
| Hybrid Retrieval & Grounded QA | ✅ Released | Milestone M6: dense/sparse fusion, cross-encoder diversity reranking, dynamic prompt routing, citations (Phase 6) |
| REST API & WebSocket Streaming | ✅ Released | Milestone M7: REST endpoints, WebSocket/SSE streaming, Auth middleware (Phase 7) |
| Native MCP Integration | ✅ Released | Milestone M8: 6 native knowledge retrieval tools, stdio/SSE transports, Antigravity verified (Phase 8) |
| Web UI | 📋 Planned | Phase 9 |
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

Mnemo provides a full Model Context Protocol (MCP) server exposing 6 native knowledge retrieval tools:

```console
# Run MCP server over stdio (for Antigravity, Claude Desktop, Cursor)
mnemo-mcp --transport stdio

# Run MCP server over SSE (port 8001)
mnemo-mcp --transport sse --host 127.0.0.1 --port 8001
```

**Exposed MCP Tools:**
- `mnemo/list_notebooks`: Discover accessible notebooks and source counts.
- `mnemo/query_notebook`: Execute grounded question answering with citations or evidence-only retrieval (`synthesize=false`).
- `mnemo/search_all_notebooks`: Hybrid semantic/keyword search across all notebooks.
- `mnemo/get_notebook_summary`: Retrieve notebook-level overview and source inventory.
- `mnemo/get_source_insights`: Retrieve extracted source-level insights.
- `mnemo/get_timeline`: Retrieve chronologically ordered notebook activity events.

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

* [Architecture Specification v2.0](docs/mnemo_architecture_v2.md) - Full design and philosophy.
* [Engineering Roadmap](docs/mnemo_engineering_roadmap.md) - The master execution plan.
* [Architecture Decision Records (ADRs)](docs/adr/) - Historical records of all major design decisions.
* [Contributing Guide](CONTRIBUTING.md) - How to contribute to the project.
* [Engineering Changelog](docs/changelog/) - Detailed historical module releases.

## Roadmap

Mnemo's roadmap is structured to ensure every phase produces a runnable, testable artifact.

* **COMPLETED (Phases 0–8):** Core scaffolding, storage, canonical ingestion, deterministic V2 chunking, embedding pipeline, hybrid retrieval & grounded QA (Milestone M6), REST/WebSocket APIs & Auth (Milestone M7), and Native MCP Server (Milestone M8) are complete and certified.
* **NEXT (Phase 9):** Web UI React frontend (Milestone M9).
* **FUTURE (Phases 10–13):** Notebook features, cross-document reasoning, plugin ecosystem, and production hardening.

See the complete execution plan in the [Engineering Roadmap](docs/mnemo_engineering_roadmap.md).

## Contributing

Interested in working on Mnemo?

Whether you're interested in building a new parser, optimizing vector storage, or shaping the retrieval algorithms, we welcome your help!

Please read our [Contributing Guide](CONTRIBUTING.md) to understand our architectural rules, local setup, and PR expectations before opening a pull request.

