# Mnemo

> One knowledge layer. Thousands of documents. Your hardware, your data.

![Version](https://img.shields.io/badge/version-0.18.0-blue) ![Python](https://img.shields.io/badge/python-3.12-blue) ![License](https://img.shields.io/badge/license-Apache_2.0-blue) [![CI](https://github.com/atharvpatil2748/Mnemo/actions/workflows/ci.yml/badge.svg)](https://github.com/atharvpatil2748/Mnemo/actions/workflows/ci.yml)

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

*(Note: These examples represent the query experience Mnemo's architecture is designed to enable. The complete embedding, retrieval, reranking, and cross-document reasoning pipeline is being implemented incrementally according to the roadmap.)*

### Cross-Document Example
Suppose you have a research paper, a textbook, lecture notes, a project report, and a technical specification in the same notebook. Mnemo is designed to answer conceptual queries like:

> *"Compare the explanation of gradient descent in my ML textbook with the approach used in these three research papers. Where do they agree, and where do they differ?"*

> *"Across all my documents, what evidence supports or contradicts the claim that X?"*

### Cross-Notebook Example (Planned Capability)
Knowledge doesn't live in silos. If you maintain multiple notebooks—like *Machine Learning Research*, *Course Notes*, *Research Papers*, and *Project Experiments*—Mnemo's global architecture is designed to synthesize insights across them:

> *"Across all my notebooks, what have I learned about transformer-based models, and which conclusions are supported by experimental evidence?"*

*(Note: While the core storage layers supporting this are built, the cross-notebook reasoning and query orchestration belong to a future roadmap phase.)*

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
User / Application
       │
       ├── REST API (Planned)
       ├── MCP (Planned)
       └── UI (Planned)
            │
            ▼
       Mnemo Server (Layer 2)
            │
            ▼
       Mnemo Core (Layer 1)
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
* **Graceful degradation:** If a non-essential plugin fails, only that capability is disabled.

## Built For

Mnemo's component-based design allows it to eventually serve multiple roles:
* **A standalone local knowledge engine** (via the planned Web UI)
* **A grounding/retrieval layer for AI assistants** (via the core Python library)
* **An MCP knowledge backend** (Planned Phase 8)
* **A retrieval backend for custom applications** (via the planned REST API)
* **A persistent research/document memory system**

## Current Capabilities

Mnemo is in active engineering development. Every module is rigorously tested before being marked complete.

Here is the current implementation status (Module 4.7 complete; release
candidate version 0.18.0):

| Capability | Status | Notes |
|---|---|---|
| Typed Domain Model | 🧊 Frozen | Core schemas and contracts |
| Configuration System | ✅ Implemented | Immutable configuration authority |
| Plugin Registry | ✅ Implemented | Discovers and injects providers |
| Local Storage Layer | ✅ Implemented | Qdrant, SQLite FTS5, SurrealDB, FS |
| Document Parsing | ✅ Implemented | PDF, DOCX, Markdown, HTML, TXT, JSON, CSV |
| Ingestion Canonicalization | ✅ Complete | Phase 3.9 bridge produces canonical `ParsedDocument` values |
| Chunking Engine | 🚧 In progress | Modules 4.1–4.7 complete: dispatcher plus Generic, Book, Paper, Code, Markdown, and Email strategies |
| Embedding Pipeline | 📋 Planned | Phase 5 |
| Hybrid Retrieval | 📋 Planned | Phase 6 |
| REST API | 📋 Planned | Phase 7 |
| MCP Integration | 📋 Planned | Phase 8 |
| Web UI | 📋 Planned | Phase 9 |
| Cross-Doc Reasoning | 📋 Planned | Phase 11 |

## Quick Start

### 1. Requirements
* **Python 3.12**
* **`uv` 0.12.2** or compatible
* **Node.js 22** and **pnpm 11.16** (for UI scaffold)
* **Docker** with Compose (for integration checks)

Phase 4 token counting requires an explicit user-initiated provisioning step:

```console
mnemo provision-tokenizer
```

The command downloads the frozen `o200k_base` asset directly from upstream,
verifies its SHA-256, and installs it in user-local content-addressed storage.
Mnemo does not bundle the asset, and chunking never accesses the network.

### 2. Setup and Validation
Clone the repository and run the validation script to ensure your environment is clean:

```shell
# Windows
validate.bat
```
*(On other platforms, follow the development commands below).*

### 3. Test the Python Baseline
Mnemo relies on strict linting, type checking, and testing:

```shell
uv sync --locked --all-packages
uv run ruff format --check .
uv run ruff check .
uv run mypy mnemo-core/mnemo mnemo-server/mnemo_server
uv run pytest
```

### 4. Build the Packages
```shell
uv build --package mnemo-core
uv build --package mnemo-server
```

### 5. Current Python API Usage
While end-user UI and APIs are planned for later phases, the core engine can be initialized programmatically:

```python
from mnemo import KnowledgeEngine, MnemoConfig

config = MnemoConfig.from_file("mnemo.toml")
engine = KnowledgeEngine(config)
await engine.initialize()
# Ready for interactions...
await engine.shutdown()
```
*(Note: Full initialization requires plugins that provide embedding and LLM roles, which are scheduled for later phases).*

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

## Why This Is an Interesting Engineering Project

Mnemo represents a serious systems and AI infrastructure challenge. It is not a wrapper around a single API. Building a robust local-first knowledge engine requires solving deep architectural problems:

* **Heterogeneous Ingestion:** Parsing wildly different file formats into a unified `RawBlock` schema.
* **Semantic Chunking:** Context-aware, adaptive chunking that preserves heading hierarchies and semantic boundaries.
* **Hybrid Retrieval:** Orchestrating dense vector search (Qdrant), sparse keyword search (SQLite), and relational metadata filtering (SurrealDB).
* **Provenance & Citations:** Guaranteeing that every generated claim maps exactly to a file, page, and chunk.
* **Deterministic Boundaries:** Enforcing a strict separation between core knowledge retrieval (Layer 1) and external HTTP/MCP transports (Layer 2).

## Roadmap

Mnemo's roadmap is structured to ensure every phase produces a runnable, testable artifact.

* **CURRENT (Phases 0–3):** Core scaffolding, storage layer, and parser systems are fully implemented.
* **NEXT:** Begin Phase 4 only after review of the completed Module 3.9 canonicalization bridge.
* **FUTURE (Phases 5–13):** Embedding, hybrid retrieval, REST/WebSocket APIs, MCP Server, Web UI, cross-document reasoning, and production hardening.

See the complete execution plan in the [Engineering Roadmap](docs/mnemo_engineering_roadmap.md).

## Contributing

Interested in working on Mnemo?

Whether you're interested in building a new parser, optimizing vector storage, or shaping the retrieval algorithms, we welcome your help!

Please read our [Contributing Guide](CONTRIBUTING.md) to understand our architectural rules, local setup, and PR expectations before opening a pull request.
