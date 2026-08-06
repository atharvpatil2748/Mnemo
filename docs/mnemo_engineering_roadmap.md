# Mnemo — Engineering Roadmap v1.0

**Document Type:** Engineering Execution Plan  
**Architectural Input:** Mnemo Architecture Specification v2.0 (FROZEN)  
**Status:** Living Implementation Tracker  
**Scope:** Complete implementation of all four layers — mnemo-core, mnemo-server, mnemo-ui, plugins  

**Current baseline:** Phase 0 and Phase 1 are complete at version 0.5.1.
Phase 2 is the next phase and has not started. Completed checklist items are
marked below; later-phase trees and tasks describe planned work.

> *This document does not redesign the architecture. It translates the v2.0 specification into a concrete, phase-by-phase engineering execution plan.*

---

## Table of Contents

1. [Master Roadmap](#1-master-roadmap)
2. [Task Breakdown](#2-task-breakdown)
3. [Module Dependency Graph](#3-module-dependency-graph)
4. [Implementation Order Rationale](#4-implementation-order-rationale)
5. [Milestones](#5-milestones)
6. [Test Plan](#6-test-plan)
7. [Reference Mapping](#7-reference-mapping)
8. [Project Structure](#8-project-structure)
9. [GitHub Project Plan](#9-github-project-plan)
10. [Engineering Rules](#10-engineering-rules)
11. [Estimation and Risk](#11-estimation-and-risk)
12. [Master Implementation Checklist](#12-master-implementation-checklist)

---

## 1. Master Roadmap

### Phase Ordering Rationale

The phase ordering follows a single guiding principle: **every phase produces a runnable, testable artifact**. No phase exits in a broken state. The ordering is dictated by the dependency graph — storage must exist before indexing, interfaces must exist before implementations, core must exist before server.

```
Phase 0  →  Phase 1  →  Phase 2  →  Phase 3  →  Phase 4
   Dev         Core         Storage       Parser        Chunker
   Env         Scaff.       Layer         System        Engine

     ↓             ↓             ↓             ↓
Phase 5  →  Phase 6  →  Phase 7  →  Phase 8  →  Phase 9
  Embed.       Retrieval     REST API      MCP          Web UI
  Pipeline     Pipeline      + Streaming   Server

     ↓             ↓             ↓
Phase 10 →  Phase 11 →  Phase 12 →  Phase 13
  Notebook      Cross-doc      Plugin         Production
  Features      Reasoning      Ecosystem      Hardening
```

---

### Phase 0 — Development Environment
**Duration:** Week 1  
**Status:** Complete
**Goal:** Every developer can clone, install, and run the test suite in under 10 minutes.

Sets up the repository, tooling, linting, formatting, pre-commit hooks, CI pipeline, and Docker stack. Nothing works yet — but the development rails are laid.

---

### Phase 1 — mnemo-core Scaffolding: Types, Interfaces, Registry
**Duration:** Weeks 2–3  
**Status:** Complete
**Goal:** All seven typed provider `Protocol` interfaces are defined. The plugin registry, configuration authority, and composition root are operational. No concrete storage, parser, retrieval, embedding, reranking, or LLM providers are included.

This phase is the most critical architectural phase. Every subsequent phase implements something that conforms to an interface defined here. Getting the interface contracts wrong here costs exponentially more to fix later.

---

### Phase 2 — Storage Layer
**Duration:** Weeks 4–6  
**Goal:** All four storage backends (Qdrant, SQLite FTS5, SurrealDB, Filesystem) are implemented behind `StorageInterface`. CRUD operations, schema initialization, and health checks pass.

Storage must precede everything else in mnemo-core because every other module writes to or reads from it. Building parsers without a place to store results is a dead-end.

---

### Phase 3 — Parser System
**Duration:** Weeks 7–10  
**Goal:** Five built-in parsers (PDF, DOCX, Markdown, HTML, plain text) are implemented behind `ParserInterface`. Output is `ParsedDocument` with typed `Block[]`.

This is the front door of all data. Quality here directly determines quality everywhere downstream.

---

### Phase 4 — Chunking Engine
**Duration:** Weeks 11–15  
**Goal:** All nine document-type-aware chunking strategies are implemented behind `ChunkerInterface`. Parent-child chunk relationships are correctly established. Every `Chunk` carries a full `heading_path`.

Chunking quality is the single biggest lever on retrieval quality. More implementation time is allocated here than anywhere else in mnemo-core.

---

### Phase 5 — Embedding Pipeline
**Duration:** Weeks 16–17  
**Goal:** Ollama embedding provider is implemented behind `EmbeddingProvider`. Content-addressable embedding cache is operational. Batch embedding works. Dimension mismatch detection works.

---

### Phase 6 — Retrieval Pipeline
**Duration:** Weeks 18–23  
**Goal:** Complete retrieval pipeline operational — dense retrieval (Qdrant), sparse retrieval (SQLite FTS5), HyDE query expansion, parent retrieval, cross-encoder reranking, RRF fusion, context assembly, citation engine. A full end-to-end query against a locally ingested document returns cited results.

This is the most complex phase. It has six interdependent modules and integration-level complexity.

---

### Phase 7 — REST API and WebSocket Streaming
**Duration:** Weeks 24–27  
**Goal:** All REST endpoints defined in the architecture are implemented in mnemo-server. WebSocket streaming is operational. No business logic in the server layer — pure adapter code.

---

### Phase 8 — MCP Server
**Duration:** Weeks 28–30  
**Goal:** MCP server is operational in both stdio and SSE modes. All six defined tools (`query_notebook`, `search_all_notebooks`, `list_notebooks`, `get_notebook_summary`, `get_source_insights`, `get_timeline`) pass the MCP specification test suite. Claude Desktop can query notebooks.

---

### Phase 9 — Web UI
**Duration:** Weeks 31–37  
**Goal:** React frontend is operational. Users can perform the complete NotebookLM MVP workflow: create notebook → upload document → chat → see citations — entirely through the browser.

---

### Phase 10 — Notebook Features
**Duration:** Weeks 38–42  
**Goal:** Full NotebookLM feature parity — notebook summaries, notes, session memory (3 tiers), insight extraction, incremental indexing, background job management UI.

---

### Phase 11 — Cross-Document Reasoning
**Duration:** Weeks 43–46  
**Goal:** Multi-hop retrieval operational. Cross-document synthesis with per-source attribution. Entity graph (lazy construction). Knowledge Graph Explorer UI connected.

---

### Phase 12 — Plugin Ecosystem
**Duration:** Weeks 47–52  
**Goal:** Plugin SDK documented and tested. First-party plugins shipped: `deepdoc-parser`, `podcast-gen`, `timeline-gen`, `watchfolder`. Plugin installation/uninstallation lifecycle verified.

---

### Phase 13 — Production Hardening
**Duration:** Weeks 53–58  
**Goal:** Performance benchmarks pass (20M chunks, <30s end-to-end). Authentication middleware (API key, JWT). Rate limiting. Structured logging. Qdrant memmap mode. Docker images published. OpenAPI spec published. README and quickstart complete.

---

## 2. Task Breakdown

---

### Phase 0 — Development Environment

**Status:** Complete

**Module 0.1 — Repository Setup**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Initialize git repository | `git init`, `.gitignore`, `LICENSE (Apache 2.0)` | Use standard Python + Node gitignore | Low | None |
| Create monorepo structure | Create `mnemo-core/`, `mnemo-server/`, `mnemo-ui/`, `plugins/`, `docker/`, `docs/` | Match architecture §3 exactly | Low | None |
| Write root `pyproject.toml` | Configure workspace with `uv` workspaces | Use `uv` as the Python package manager | Low | None |

**Module 0.2 — Python Tooling**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Configure `uv` as package manager | `uv init`, `uv.lock` | Faster than pip, deterministic locks | Low | 0.1 |
| Set up `ruff` for linting + formatting | `ruff.toml` at root | Replaces flake8 + black + isort | Low | 0.1 |
| Set up `mypy` for type checking | Strict mode: `disallow_untyped_defs = true` | Enforces 100% type hints rule | Low | 0.1 |
| Set up `pytest` | `pytest.ini`, fixtures, coverage config | Target: 90% coverage minimum | Low | 0.1 |
| Configure `pre-commit` | hooks: ruff, mypy, trailing whitespace, no-debug | All hooks run on every commit | Low | 0.2 |

**Module 0.3 — Frontend Tooling**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Initialize React project | `pnpm create vite mnemo-ui --template react-ts` | TypeScript, Vite for fast HMR | Low | 0.1 |
| Configure `biome` | Formatting + linting for TypeScript | Single tool, replaces eslint + prettier | Low | 0.3 |
| Set up `vitest` | Unit testing for React components | Fast, Vite-native | Low | 0.3 |

**Module 0.4 — CI Pipeline**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Create GitHub Actions workflow | On push: lint → typecheck → test → build | Runs in <5 minutes | Medium | 0.2, 0.3 |
| Add Docker build check | Build all Docker images, verify no errors | Catches Dockerfile regressions | Medium | 0.5 |

**Module 0.5 — Docker Dev Stack**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Write `docker-compose.dev.yml` | qdrant + surrealdb + hot-reload server | For local development | Medium | 0.1 |
| Write `docker-compose.yml` | Full production stack | Without hot reload | Medium | 0.1 |
| Write `docker-compose.minimal.yml` | Single container, SQLite vector fallback | For low-resource users | Medium | 0.1 |

---

### Phase 1 — mnemo-core Scaffolding

**Status:** Complete

**Module 1.1 — Domain Models**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Define `Block` types | `TextBlock`, `HeadingBlock`, `TableBlock`, `ImageBlock`, `CodeBlock`, `EquationBlock`, `CaptionBlock` | Use dataclasses with frozen=True | — | Low | Phase 0 |
| Define `ParsedDocument` | `blocks: list[Block]`, `metadata: DocumentMetadata`, `language: str`, `doc_type: DocType` | — | RAGFlow deepdoc | Low | 1.1a |
| Define `DocumentMetadata` | Canonical schema from ADR-0001, including `content_hash` | Use `dataclasses.field` with defaults | — | Low | 1.1a |
| Define `DocType` enum | BOOK, PAPER, CODE, EMAIL, RESUME, SLIDES, MARKDOWN, DOCUMENTATION, GENERIC | — | — | Low | 1.1a |
| Define `Chunk` dataclass | Canonical immutable schema from ADR-0001 | Identity uses version, block-ordinal span, and text; headings/offsets excluded | RAGFlow | Low | 1.1a |
| Define `ChunkType` enum | PASSAGE, SUMMARY, VERBATIM, QUESTION, CODE, CAPTION, EQUATION | — | — | Low | 1.1a |
| Define `ChunkPosition` | page, section_index, chunk_index_in_section | — | — | Low | 1.1a |
| Define `ScoredChunk` | `chunk: Chunk`, `score: float`, `retrieval_mode: str` | — | — | Low | 1.1e |
| Define `MetadataFilter` | notebook_id, doc_type[], date_after, date_before, source_id[] | Pydantic model for validation | — | Low | 1.1a |
| Define `Entity`, `GraphEdge` | Exact entity and relationship schemas from ADR-0001 | — | RAG-Anything | Low | 1.1a |
| Define `Session`, `Turn`, `Citation` | Full structures from architecture §12 | — | Open Notebook | Low | 1.1a |
| Define `Document` registry model | `document_id`, versions, current version/hash, status | Notebook membership belongs to `Source` | — | Low | 1.1a |
| Define `Notebook`, `Source`, `Note`, `Insight` | As described in architecture §4.3 | — | Open Notebook | Low | 1.1a |

**Module 1.2 — Interface Contracts**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Define `ParserInterface` | Protocol with `supported_formats` + `parse()` | From architecture §8.1 | Low | 1.1 |
| Define `ChunkerInterface` | Protocol with `supported_doc_types` + `chunk()` | From architecture §8.2 | Low | 1.1 |
| Define `EmbeddingProvider` | Protocol with `model_name`, `dimensions`, `embed()`, `embed_batch()` | Provider abstraction from ADR-0002 | Low | 1.1 |
| Define `RetrieverInterface` | Protocol with `retrieval_mode` + `retrieve()` | From architecture §8.4 | Low | 1.1 |
| Define `RerankerInterface` | Protocol with `rerank()` | From architecture §8.5 | Low | 1.1 |
| Define `LLMInterface` | Protocol with `complete()` + `stream()` + structured output | From architecture §8.6 | Low | 1.1 |
| Define `StorageInterface` | Full Protocol from architecture §8.7 | Largest interface — 12 methods | Low | 1.1 |
| Write interface version markers | `PARSER_INTERFACE_VERSION = "v1"` constants | Supports future versioning | Low | 1.2a–g |

**Module 1.3 — Plugin Registry**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `PluginRegistry` class | Dict of slots → implementations with priorities | Architecture §4.4 | Medium | 1.2 |
| Implement slot registration | `register_parser()`, `register_chunker()`, etc. — one per interface | Conflict resolution by priority | Medium | 1.3a |
| Implement plugin discovery | Python entry points plus explicit module/package paths | `MNEMO_PLUGINS` retained only as deprecated Module 1.x compatibility | Medium | 1.3a |
| Implement `load_plugins()` | Call each plugin's `register()` function | Catch per-plugin failures gracefully | Medium | 1.3b |
| Write registry unit tests | Verify priority conflict resolution, missing slot fallback | — | Medium | 1.3c |

**Module 1.4 — Configuration System**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Define `MnemoConfig` | Frozen Pydantic v2 model with explicit TOML/environment loading | Exact five-section schema from ADR-0003 | Medium | 1.1 |
| Define `LLMRoleConfig` | Per-role: provider, model, max_context_tokens | Validates on startup | Low | 1.4a |
| Define `StorageConfig` | Explicit filesystem, SQLite, Qdrant, and SurrealDB sections | No backend selector | Low | 1.4a |
| Implement config loading | `MnemoConfig.from_file(path)` + `from_env()` | Prefer env over file | Low | 1.4a |

**Module 1.5 — KnowledgeEngine Entrypoint**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `KnowledgeEngine` class | Top-level class from architecture §17.5 | Wraps all core modules | Medium | 1.2, 1.3, 1.4 |
| Implement `initialize()` | Discover plugins → freeze registry → structurally validate required providers | Async, atomic, no external I/O in Phase 1 | Medium | 1.5a |
| Implement lifecycle and inspection | `shutdown()`, state, provider access, immutable capabilities | Health is lifecycle state only in Phase 1 | Low | 1.5a |

---

### Phase 2 — Storage Layer

**Module 2.1 — Filesystem Blob Store**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Implement content-addressed blob store | SHA-256 based path: `ab/cdef.../raw.pdf` | Architecture §13 | — | Low | Phase 1 |
| Implement `put_asset()` | Write bytes → return immutable `Asset` | Atomic write via temp file | — | Low | 2.1a |
| Implement `get_asset()` | Read bytes by asset UUID | Content hash remains the integrity key | — | Low | 2.1a |
| Implement `put_parsed_document()` | Write `ParsedDocument` as JSON by `version_id` | Enables re-chunking without re-parsing | — | Low | 2.1a |
| Implement `get_parsed_document()` | Deserialize `ParsedDocument` by `version_id` | — | — | Low | 2.1d |

**Module 2.2 — SQLite FTS5 Store**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Design schema | chunks table, fts5 virtual table, documents table | Single `.db` file | — | Low | Phase 1 |
| Implement `SQLiteStore` | Implements `StorageInterface` (keyword-relevant methods) | `aiosqlite` for async | — | Medium | 2.2a |
| Implement `upsert_chunks()` | Write to both chunks table and FTS5 index | Atomic transaction | — | Medium | 2.2b |
| Implement `search_sparse()` | `SELECT ... MATCH ? ORDER BY rank` BM25 | FTS5 native ranking | — | Medium | 2.2b |
| Implement `delete_chunks_for_document()` | Delete from chunks + FTS5 indexes | Document cascade is owned by the composite façade | — | Medium | 2.2b |
| Implement session/citation tables | `sessions`, `turns`, `citations` schema | — | Open Notebook | Medium | 2.2b |
| Implement embedding cache table | `sha256_text_model → vector BLOB` | Content-addressable | — | Low | 2.2b |
| Write migration system | Simple versioned migration runner | No Alembic dependency for simplicity | — | Medium | 2.2a |

**Module 2.3 — Qdrant Vector Store**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Implement `QdrantStore` | `qdrant-client` async, implements vector search methods | Architecture §13 | RAGFlow | Medium | Phase 1 |
| Implement collection initialization | Create collection on first run, detect existing | Named vectors: body, title, question | — | Medium | 2.3a |
| Implement `upsert_chunks()` | Write points with payload filters | Payload: notebook_id, document_id, version_id, doc_type, chunk_type | — | Medium | 2.3a |
| Implement `search_dense()` | `qdrant_client.search()` with filter | Architecture §13 | — | Medium | 2.3b |
| Implement memmap mode config | `on_disk: true` in collection params | For low-RAM deployments | — | Low | 2.3a |
| Implement `delete_chunks_for_document()` | Delete points by `document_id` and optional `version_id` filter | — | — | Low | 2.3a |

**Module 2.4 — SurrealDB Store**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Implement `SurrealDBStore` | `surrealdb` Python client, async | Architecture §13 | Open Notebook | High | Phase 1 |
| Design SurrealDB schema | Tables: documents, notebooks, sources, notes, sessions, turns, citations, entities, graph_edges, jobs | — | — | High | 2.4a |
| Implement document CRUD | `upsert_document()`, `get_document()`, `list_documents()` | — | — | Medium | 2.4b |
| Implement notebook/source CRUD | Full CRUD matching Notebook Manager models | — | — | Medium | 2.4b |
| Implement session/turn storage | Append-only turn records | — | — | Medium | 2.4b |
| Implement citation storage | `upsert_citation()`, `get_citations_for_turn()` | — | — | Medium | 2.4b |
| Implement entity/graph storage | `upsert_entity()`, `upsert_edge()`, `get_related_entities()` | Graph traversal query | RAG-Anything | High | 2.4b |
| Implement job queue | Background job records with status enum | Fast-path / slow-path coordination | — | Medium | 2.4b |

**Module 2.5 — Composite Storage Router**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `CompositeStorage` | Routes method calls to correct backend | Single `StorageInterface` over all 4 backends | High | 2.1–2.4 |
| Implement atomic upsert | Write to Qdrant + SQLite + SurrealDB + Filesystem as one logical operation | Rollback on partial failure | High | 2.5a |
| Implement rollback logic | On any write failure, undo all partial writes | — | High | 2.5a |

---

### Phase 3 — Parser System

**Module 3.1 — Parser Router**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Implement `ParserRouter` | Maps file extension + MIME to `ParserInterface` impl | Checks registry first, built-ins second | — | Medium | Phase 2 |
| Implement MIME detection | `python-magic` for reliable MIME | Extension fallback if magic fails | — | Low | 3.1a |
| Implement deduplication gate | SHA-256 check before parsing | Return existing `document_id` if already known | — | Low | 3.1a |

**Module 3.2 — PDF Parser**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Implement `BasicPDFParser` | `pymupdf` (fitz) for digital PDFs | Text + table + image extraction | RAGFlow deepdoc | High | 3.1 |
| Extract text with layout awareness | Respect reading order from PDF layout | Handle multi-column layouts | RAGFlow | High | 3.2a |
| Extract table structures | Convert tables to markdown or structured dict | — | RAGFlow deepdoc | High | 3.2a |
| Extract images | Save as blob, attach caption if present | — | — | Medium | 3.2a |
| Extract headings from formatting | Bold, larger font-size → HeadingBlock | Font size heuristic | RAGFlow | Medium | 3.2a |
| Detect running headers/footers | Frequency analysis across pages | Architecture §4.1 Cleaner note | RAGFlow | High | 3.2a |

**Module 3.3 — DOCX Parser**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Implement `DOCXParser` | `python-docx` | Preserve heading levels (H1–H6) | RAGFlow | Medium | 3.1 |
| Extract paragraph structure | Map Word styles → HeadingBlock / TextBlock | — | — | Medium | 3.3a |
| Extract tables | Convert to structured TableBlock | — | — | Medium | 3.3a |

**Module 3.4 — Markdown Parser**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Implement `MarkdownParser` | `mistune` or `markdown-it-py` AST parser | Full AST, not regex-based | — | Low | 3.1 |
| Map AST nodes to Block types | H1-H6 → HeadingBlock, fenced code → CodeBlock, table → TableBlock | — | — | Low | 3.4a |
| Extract internal links | Store as graph edge metadata | — | — | Low | 3.4a |

**Module 3.5 — HTML Parser**

| Task | Subtask | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|---|
| Implement `HTMLParser` | `beautifulsoup4` + `html5lib` | — | — | Low | 3.1 |
| Respect semantic heading hierarchy | `<h1>`–`<h6>` → HeadingBlock | — | — | Low | 3.5a |
| Strip boilerplate | Nav, footer, ads heuristic removal | `readability-lxml` for main content extraction | — | Medium | 3.5a |

**Module 3.6 — Text and Other Parsers**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `PlainTextParser` | Line-based splitting, paragraph detection | — | Low | 3.1 |
| Implement `JSONParser` | Flatten JSON to text with key context | — | Low | 3.1 |
| Implement `CSVParser` | Treat each row as a TextBlock with header context | — | Low | 3.1 |

**Module 3.7 — Cleaner**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `DocumentCleaner` | Operates on `ParsedDocument` | All cleaning in one pass | — | Medium | 3.1 |
| Unicode normalization | NFC normalization for all text | — | Low | 3.7a |
| Duplicate whitespace removal | Collapse multiple spaces/newlines | — | Low | 3.7a |
| Hyphenated line break fix | `end-\nof-line` → `end-of-line` | Common in PDF extraction | Medium | 3.7a |
| Language detection | `langdetect` per block | Tag `Block.language` | Low | 3.7a |
| Header/footer detection | Frequency analysis: text appearing on >50% of pages | Filter or tag | High | 3.7a |

**Module 3.8 — Document Classifier**

| Task | Subtask | Notes | Difficulty | Dependency |
|---|---|---|---|---|
| Implement rule-based classification | DocType from extension + heading patterns + structure | Fast path, no LLM | Medium | 3.7 |
| Implement LLM-assisted classification | For ambiguous cases: send first-page text to Extractor LLM | Fallback only | High | 3.8a |

---

### Phase 4 — Chunking Engine

**Module 4.1 — Chunker Dispatcher**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `ChunkerDispatcher` | Selects `ChunkerInterface` by `doc_type` from registry | Medium | Phase 3 |
| Implement parent-child ID linking | After chunking, link chunk IDs to parent IDs | Must happen post-chunk, pre-index | High | 4.1a |
| Implement sibling ID linking | Group chunks by section, set `sibling_ids` | Required for parent retrieval | High | 4.1a |
| Enforce chunking invariants | Min 15 tokens, max 2× target. Drop short. Split long. | Architecture §10.9 | Medium | 4.1a |
| Implement chunk ID computation | SHA-256 of version, canonical block-ordinal span, and text | Heading path and offsets excluded | Low | 4.1a |

**Module 4.2 — Generic Recursive Chunker**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `GenericChunker` | Paragraph-first split, then sentence, then word | Fallback for GENERIC DocType | Medium | 4.1 |
| Respect block boundaries | Never split mid-HeadingBlock, mid-TableBlock | — | Medium | 4.2a |

**Module 4.3 — Book Chunker**

| Task | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `BookChunker` | Architecture §10.1 three-level hierarchy | RAGFlow | High | 4.1 |
| ToC extraction | Parse Table of Contents → section hierarchy | RAGFlow deepdoc | High | 4.3a |
| ToC inference | If no ToC: infer hierarchy from heading patterns | — | High | 4.3b |
| Three chunk types per section | SUMMARY stub (filled later), PASSAGE, VERBATIM for key claims | — | High | 4.3a |
| Never cross chapter boundaries | Chapter boundary = hard split | — | Medium | 4.3a |
| Skip ToC itself | Detect and skip ToC pages | — | Low | 4.3a |

**Module 4.4 — Paper Chunker**

| Task | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `PaperChunker` | Architecture §10.2 | RAGFlow | High | 4.1 |
| Section heading detection | Font + numbering patterns: "3.1 Methodology" | RAGFlow | High | 4.4a |
| Canonical section mapping | Assign `section_type` enum: Abstract, Introduction, etc. | — | Medium | 4.4a |
| Abstract → atomic chunk | Single chunk, never split | — | Low | 4.4a |
| References → metadata only | Extract DOIs, not embedded | — | Medium | 4.4a |
| Equation handling | Preserve LaTeX + generate plain-language description (slow path) | — | High | 4.4a |

**Module 4.5 — Code Chunker**

| Task | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `CodeChunker` | AST-structural chunking via `tree-sitter` | RAG-Anything | High | 4.1 |
| `tree-sitter` grammar install | Install grammars for Python, JS/TS, Go, Rust, Java, C/C++ | — | Medium | 4.5a |
| Extract top-level declarations | Class, function, method, constant per file | — | High | 4.5b |
| Never split mid-function | Function body is atomic | — | Medium | 4.5b |
| Build `call_context` metadata | What calls what (from AST) | — | High | 4.5b |
| File-level summary chunk | README or module docstring → SUMMARY chunk | — | Low | 4.5b |

**Module 4.6 — Markdown Chunker**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `MarkdownChunker` | Header-hierarchy chunking from architecture §10.5 | Medium | 4.1 |
| Split boundaries: H1, H2, H3 | Content between H3s = one chunk | Low | 4.6a |
| Code blocks → CODE chunks | With language tag | Low | 4.6a |
| Tables → structured chunk | Markdown table preserved as text | Low | 4.6a |

**Module 4.7 — Resume Chunker**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `ResumeChunker` | Architecture §10.3 semantic section isolation | High | 4.1 |
| Section detection | Contact, Summary, Experience, Education, Skills, Projects | Medium | 4.7a |
| Role isolation | Each Experience role = distinct chunk | High | 4.7a |
| Profile summary chunk | LLM-generated holistic summary (slow path) | High | 4.7a |

**Module 4.8 — Slides Chunker**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `SlidesChunker` | Architecture §10.7 slide-level atomic | Medium | 4.1 |
| One chunk per slide | Title + body + speaker notes | Low | 4.8a |
| Detect section dividers | Title slides mark section boundaries | Medium | 4.8a |

**Module 4.9 — Documentation Chunker**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `DocumentationChunker` | Architecture §10.8 task-and-topic | Medium | 4.1 |
| Detect task blocks | Numbered procedures stay atomic | Medium | 4.9a |
| API reference format | One chunk per function/endpoint | High | 4.9a |
| Preserve callout type tags | Note, Warning, Tip in chunk metadata | Low | 4.9a |

---

### Phase 5 — Embedding Pipeline

**Module 5.1 — Ollama Embedding Provider**

| Task | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `OllamaEmbedder` | `httpx` async calls to Ollama `/api/embeddings` | Open Notebook | Medium | Phase 4 |
| Implement batch embedding | Chunk text list → vector list | — | Medium | 5.1a |
| Implement dimension detection | Query model on init, cache `dimensions` property | — | Low | 5.1a |
| Implement connection retry | Exponential backoff if Ollama unavailable | — | Medium | 5.1a |

**Module 5.2 — Embedding Cache**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement content-addressable cache | `sha256(text) + "::" + model_name → vector BLOB` in SQLite | Architecture §15 | Medium | 5.1 |
| Implement cache lookup | Check before calling Ollama | Low | 5.2a |
| Implement cache write | After Ollama call, persist to SQLite | Low | 5.2a |
| Implement dimension mismatch detection | Compare stored `dimensions` to current model's | Medium | 5.2a |

**Module 5.3 — Embedder Module**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `EmbedderModule` | Coordinates cache + provider | Medium | 5.1, 5.2 |
| Implement parallel batch embedding | Async batch with concurrency limit | Medium | 5.3a |
| Implement question embedding | Generate question embeddings separately for storage | Low | 5.3a |

---

### Phase 6 — Retrieval Pipeline

**Module 6.1 — Query Planner**

| Task | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `QueryPlanner` | LLM call → structured `RetrievalPlan` | Open Notebook `ask.py` | High | Phase 5 |
| Define `RetrievalPlan` schema | `intent`, `sub_queries[]`, `requires_multi_hop`, `requires_multi_doc` | JSON Schema for structured output | Medium | 6.1a |
| Implement intent detection | Factual / comparative / exploratory | — | Medium | 6.1b |
| Implement query decomposition | Multi-question queries → multiple SubQueries | — | High | 6.1b |
| Implement HyDE | Generate hypothetical answer paragraph with Planner LLM | Architecture §11 | High | 6.1b |
| Embed the HyDE paragraph | Send to Embedder, not the original question | — | Low | 6.1c |

**Module 6.2 — Dense Retriever**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `DenseRetriever` | Qdrant ANN search implementing `RetrieverInterface` | Medium | 6.1 |
| Apply metadata filters at HNSW level | Pass `MetadataFilter` as Qdrant filter payload | High | 6.2a |
| Return `ScoredChunk[]` | Normalized scores (0–1) | Low | 6.2a |

**Module 6.3 — Sparse Retriever**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `SparseRetriever` | SQLite FTS5 BM25 implementing `RetrieverInterface` | Medium | 6.1 |
| Query synonym expansion | Add alternate phrasings from Planner output | Medium | 6.3a |
| Return `ScoredChunk[]` | Normalize BM25 score to 0–1 | Medium | 6.3a |

**Module 6.4 — Parent Retriever**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `ParentRetriever` | Architecture §11 hierarchical upgrade | High | 6.2, 6.3 |
| Sibling co-occurrence check | ≥50% of a section's siblings in result set → upgrade to parent | High | 6.4a |
| Fetch parent chunk from storage | Parent ID lookup | Low | 6.4a |

**Module 6.5 — Result Fusion**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement parallel retrieval runner | Dispatch all SubQueries across all Retrievers concurrently | High | 6.2, 6.3, 6.4 |
| Implement deduplication | Deduplicate by `chunk_id` across retriever results | Medium | 6.5a |
| Implement Reciprocal Rank Fusion | RRF as default fusion when no reranker | Medium | 6.5a |

**Module 6.6 — Cross-Encoder Reranker**

| Task | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|
| Implement `CrossEncoderReranker` | `sentence-transformers` ms-marco model | RAGFlow | High | 6.5 |
| Implement `(query, chunk)` pair scoring | Batch inference | — | Medium | 6.6a |
| Implement confidence threshold flagging | < 0.4 → flagged in `ScoredChunk.metadata` | — | Low | 6.6a |
| Implement RRF fallback | When reranker not configured | — | Medium | 6.6a |

**Module 6.7 — Context Builder**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `ContextBuilder` | Architecture §4.2 | High | 6.6 |
| Implement token budget computation | `budget = context_budget - system_prompt - question - session_history` | Medium | 6.7a |
| Implement greedy chunk selection | Select by score until budget consumed | Medium | 6.7a |
| Implement context compression | Summarize low-priority chunks beyond budget via Extractor LLM | High | 6.7a |
| Implement attribution marker formatting | `=== Source [N]: Title Ch.X p.Y ===` | Low | 6.7a |
| Implement context assembly | Ordered, formatted context string | Low | 6.7a |

**Module 6.8 — Citation Engine**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `CitationEngine` | Parse `[source:N]` markers from synthesized text | Medium | 6.7 |
| Resolve markers to Citation records | chunk_id → doc title, page, heading_path, quote | Medium | 6.8a |
| Persist citations in SurrealDB | Every turn's citations permanently stored | Medium | 6.8a |
| Return `Citation[]` with response | Attach to every query response | Low | 6.8a |

**Module 6.9 — Synthesizer**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `Synthesizer` | Calls Synthesizer LLM with context + citation instructions | High | 6.7, 6.8 |
| Implement streaming synthesis | `LLMInterface.stream()` → async token iterator | High | 6.9a |
| Write grounding system prompt | Instruct LLM to cite only from provided context, use [N] format | High | 6.9a |
| Handle `synthesis.enabled: false` | Return raw context + citations without LLM call | Low | 6.9a |

**Module 6.10 — Multi-Hop Retrieval**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement multi-hop orchestration | Architecture §11 — max 3 hops | High | 6.1–6.9 |
| Extract entities from hop-1 results | Use spaCy NER on top-5 chunks | High | 6.10a |
| Run hop-2 with extracted entities | New SubQuery per entity | High | 6.10a |
| Fuse hop-1 and hop-2 with RRF | — | Medium | 6.10a |

---

### Phase 7 — REST API and WebSocket

**Module 7.1 — FastAPI Application Setup**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Initialize `mnemo-server` FastAPI app | `lifespan` context manager for startup/shutdown | Low | Phase 6 |
| Wire `KnowledgeEngine` to app state | Singleton instance, initialized on startup | Medium | 7.1a |
| Configure CORS | Allow UI origin in dev, configurable for prod | Low | 7.1a |
| Configure error handling | Global exception handler → structured JSON errors | Medium | 7.1a |

**Module 7.2 — Notebook Endpoints**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| `GET/POST /v1/notebooks` | List + create | Low | 7.1 |
| `GET/PATCH/DELETE /v1/notebooks/{id}` | CRUD | Low | 7.1 |
| `GET /v1/notebooks/{id}/summary` | Trigger summary generation if stale | Medium | 7.1 |
| `GET /v1/notebooks/{id}/timeline` | Return timeline events | Low | 7.1 |
| `GET /v1/notebooks/{id}/graph` | Return entity graph nodes + edges | Medium | 7.1 |

**Module 7.3 — Sources and Ingestion Endpoints**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| `POST /v1/notebooks/{id}/sources` | Multipart file upload, return job_id | High | 7.1 |
| `GET /v1/notebooks/{id}/sources/{sid}/status` | Polling endpoint, return ingestion status | Medium | 7.1 |
| `GET/DELETE /v1/notebooks/{id}/sources/{sid}` | CRUD | Low | 7.1 |

**Module 7.4 — Query and Search Endpoints**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| `POST /v1/query` | Full query endpoint per architecture §5.1 | High | 7.1 |
| `POST /v1/search` | Global full-text + vector search | Medium | 7.1 |
| Request validation | Pydantic models for all request bodies | Low | 7.4a |
| Response serialization | Pydantic models for all responses | Low | 7.4a |

**Module 7.5 — Sessions, Notes, Insights Endpoints**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Session CRUD endpoints | 5 endpoints from architecture §5.1 | Medium | 7.1 |
| Notes CRUD endpoints | 4 endpoints | Low | 7.1 |
| Insights endpoints | List + generate | Medium | 7.1 |

**Module 7.6 — System Endpoints**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| `GET /v1/health` | Returns backend connectivity | Low | 7.1 |
| `GET/PATCH /v1/config` | Config read + hot reload | High | 7.1 |
| `GET /v1/jobs`, `GET /v1/jobs/{id}` | Background job status | Medium | 7.1 |

**Module 7.7 — WebSocket Streaming**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `/ws/query` WebSocket endpoint | Architecture §5.3 5-event protocol | High | 7.4 |
| Implement event serialization | JSON events per architecture schema | Low | 7.7a |
| Implement streaming token forwarding | `LLMInterface.stream()` → WebSocket send | High | 7.7a |
| Implement connection lifecycle | Auth check, heartbeat, cleanup on disconnect | Medium | 7.7a |

**Module 7.8 — Authentication Middleware**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `AuthMiddleware` | Three modes: none, api-key, JWT | Medium | 7.1 |
| Implement none mode | Pass-through, single-user default | Low | 7.8a |
| Implement API key mode | `Authorization: Bearer {key}` header check | Low | 7.8a |
| Implement JWT mode | `python-jose` JWT validation | High | 7.8a |

---

### Phase 8 — MCP Server

**Module 8.1 — MCP Server Core**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement MCP server using `mcp` Python SDK | `pip install mcp` | High | Phase 7 |
| Implement stdio mode | Subprocess communication, newline-delimited JSON | High | 8.1a |
| Implement SSE mode | HTTP-based MCP for remote clients | High | 8.1a |
| Create `mnemo-mcp` CLI entrypoint | `mnemo-mcp --host --port` | Low | 8.1a |

**Module 8.2 — MCP Tool Implementations**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `query_notebook` tool | Calls `KnowledgeEngine.retrieve()` | Medium | 8.1 |
| Implement `search_all_notebooks` tool | Global search, no synthesis | Medium | 8.1 |
| Implement `list_notebooks` tool | Read-only listing | Low | 8.1 |
| Implement `get_notebook_summary` tool | Calls summary generator | Medium | 8.1 |
| Implement `get_source_insights` tool | Returns stored insights | Low | 8.1 |
| Implement `get_timeline` tool | Returns timeline events | Low | 8.1 |

**Module 8.3 — MCP Testing**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Write MCP spec conformance tests | Use MCP test harness / inspector | High | 8.2 |
| Test Claude Desktop integration | Manual: add to `config.json`, verify tool calls | High | 8.2 |

---

### Phase 9 — Web UI

**Module 9.1 — Design System and Routing**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Define design tokens | Colors, typography (Inter/Geist), spacing, radii | Medium | Phase 8 |
| Set up React Router v7 | Routes per architecture §6 | Low | 9.1a |
| Implement API client layer | All HTTP calls in `src/api/`, using `@tanstack/query` | High | 9.1a |
| Implement WebSocket client | Reconnection, event parsing, streaming state | High | 9.1a |

**Module 9.2 — Dashboard Page**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Recent notebooks list | Fetch + render `GET /v1/notebooks` | Low | 9.1 |
| Quick search bar | Global search `POST /v1/search` | Medium | 9.1 |

**Module 9.3 — Notebook Page**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Notebook detail header | Title, source count, last updated | Low | 9.1 |
| Sources tab | File list, upload via multipart, ingestion progress polling | High | 9.1 |
| Chat tab | WebSocket streaming chat with citation rendering | High | 9.1 |
| Notes tab | Note CRUD | Medium | 9.1 |
| Implement citation rendering | Inline footnotes, click → source location | High | 9.3d |

**Module 9.4 — Chat Interface**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Message history | Session turns rendered chronologically | Medium | 9.3 |
| Token streaming | Render tokens as they arrive from WebSocket | High | 9.3 |
| Citation footnotes | `[1]`, `[2]` → interactive source cards | High | 9.3 |
| Retrieval metadata display | Show which chunks were retrieved, scores | Medium | 9.3 |

**Module 9.5 — Settings Page**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Model config panel | LLM role configuration per architecture §14 | Medium | 9.1 |
| Plugin status panel | List installed plugins | Medium | 9.1 |
| Storage health panel | Backend connectivity status | Low | 9.1 |

---

### Phase 10 — Notebook Features

**Module 10.1 — Background Job Worker**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement background worker process | Polls job queue in SurrealDB | High | Phase 9 |
| Implement slow path stages 9A–9D | NER, question gen, summaries, graph edges | High | 10.1a |
| Implement job priority queue | High-priority docs processed first | Medium | 10.1a |
| Implement interruptible jobs | Jobs can be paused/resumed | High | 10.1a |

**Module 10.2 — Notebook Summaries**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement per-source summarization | Synthesizer LLM over top chunks | High | 10.1 |
| Implement notebook-level summary | Multi-source synthesis | High | 10.2a |
| Implement summary staleness detection | Re-generate when new sources added | Medium | 10.2a |
| Implement `GET /v1/notebooks/{id}/summary` | Return cached or trigger fresh | Medium | 10.2a |

**Module 10.3 — Insight Extraction**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement insight extraction pipeline | Extractor LLM → key facts, claims, entities | High | 10.1 |
| Store insights in SurrealDB | Attached to source | Medium | 10.3a |
| Implement `POST .../insights/generate` | Trigger extraction job | Low | 10.3a |

**Module 10.4 — Session Memory (3-Tier)**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement Tier 1 — immediate context | Last N turns injected into each call | Low | 10.1 |
| Implement Tier 2 — within-session retrieval | BM25 search over current session turns | Medium | 10.4a |
| Implement Tier 3 — session notes | AI-generated session summaries → embedded as documents | High | 10.4a |

**Module 10.5 — Incremental Indexing**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement hash-based change detection | Compare new chunk IDs to stored IDs | High | 10.1 |
| Implement differential update | Delete removed chunks, insert new chunks only | High | 10.5a |
| Re-embed only new chunks | Skip cache hits | Low | 10.5a |

---

### Phase 11 — Cross-Document Reasoning

**Module 11.1 — Knowledge Graph (Lazy)**

| Task | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|
| Implement spaCy NER in slow path | Stage 9A per ingestion pipeline | RAG-Anything | High | Phase 10 |
| Implement entity normalization | Fuzzy match surface forms to canonical entities | High | 11.1a |
| Implement relationship extraction | Small LLM in slow path, rate-limited | RAG-Anything | High | 11.1a |
| Store entity graph in SurrealDB | Architecture §13 | — | Medium | 11.1a |

**Module 11.2 — Graph Retrieval**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement multi-hop entity traversal | SurrealDB graph query, 1–3 hops | High | 11.1 |
| Integrate graph retrieval into pipeline | `GraphRetriever` as optional retriever | High | 11.2a |

**Module 11.3 — Cross-Document Synthesis**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement cross-doc context segmentation | Context partitioned by source | Medium | 11.1 |
| Implement cross-doc Synthesizer prompt | Compare/contrast instructions per source | High | 11.3a |
| Per-source citation attribution | Track which source contributed which claim | High | 11.3a |

**Module 11.4 — Knowledge Graph UI**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement graph explorer view | `react-force-graph` or `cytoscape.js` | High | 11.2 |
| Node click → related chunks | Link entity node to source chunks | High | 11.4a |
| Timeline view | Chronological events extracted from graph | High | 11.4a |

---

### Phase 12 — Plugin Ecosystem

**Module 12.1 — Plugin SDK**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Define plugin development guide | `docs/plugin-development.md` | Medium | Phase 11 |
| Create plugin template | Cookiecutter template for new plugins | Medium | 12.1a |
| Write plugin compatibility testing | CI test against all interface versions | High | 12.1a |

**Module 12.2 — deepdoc-parser Plugin**

| Task | Notes | Ref. Repo | Difficulty | Dependency |
|---|---|---|---|---|
| Port RAGFlow's deepdoc parsing logic | Advanced layout analysis, multi-column, complex tables | RAGFlow | High | 12.1 |
| Implement `DeepDocPDFParser` | Replaces `BasicPDFParser` for complex PDFs | — | High | 12.2a |
| Register as priority-10 PDF parser | Overrides built-in | — | Low | 12.2a |

**Module 12.3 — podcast-gen Plugin**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `PodcastGenerator` | Synthesizes a two-voice script from notebook | High | 12.1 |
| Implement TTS with Kokoro | `kokoro` TTS for local audio generation | High | 12.3a |
| Implement audio concatenation | `ffmpeg` for segment assembly | Medium | 12.3b |
| `POST /v1/notebooks/{id}/podcast` endpoint | Async job, returns job_id | Medium | 12.3c |

**Module 12.4 — timeline-gen Plugin**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `TimelineGenerator` | Extractor LLM → date:event pairs | High | 12.1 |
| Store timeline events in SurrealDB | Attach to notebook | Medium | 12.4a |
| Return via `GET /v1/notebooks/{id}/timeline` | — | Low | 12.4a |

**Module 12.5 — watchfolder Plugin**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement `WatchFolderService` | `watchdog` library, zero CPU when idle | Medium | 12.1 |
| Detect new/modified files | SHA-256 check before queuing ingest | Medium | 12.5a |
| Configure watched paths | Via `MnemoConfig` or config endpoint | Low | 12.5a |

---

### Phase 13 — Production Hardening

**Module 13.1 — Performance**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Run 20M chunk benchmark | Ingest benchmark corpus, measure query latency | High | Phase 12 |
| Optimize Qdrant indexing | Tune HNSW `ef_construction`, `m` params | High | 13.1a |
| Implement Qdrant memmap mode | For deployments with <64 GB RAM | Medium | 13.1a |
| Profile slow ingestion paths | `py-spy` profiling | Medium | 13.1a |

**Module 13.2 — Observability**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Implement structured logging | `structlog`, JSON output | Medium | Phase 12 |
| Add request tracing | Trace IDs across all log lines | Medium | 13.2a |
| Add performance metrics | Ingestion latency, retrieval latency, embedding latency | Medium | 13.2a |
| Add background job metrics | Queue depth, job success/failure rate | Low | 13.2a |

**Module 13.3 — Docker Production Images**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Write multi-stage Dockerfiles | Build stage + slim runtime | High | Phase 12 |
| Publish images to Docker Hub | CI-automated on tags | Medium | 13.3a |
| Write healthcheck scripts | `/v1/health` in Docker HEALTHCHECK | Low | 13.3a |

**Module 13.4 — Documentation**

| Task | Notes | Difficulty | Dependency |
|---|---|---|---|
| Write `quickstart.md` | `docker compose up` → first query in 5 minutes | High | Phase 12 |
| Write `api-reference.md` | Generated from OpenAPI spec | Medium | 13.4a |
| Write `mcp-integration.md` | Claude Desktop, VS Code integration guide | Medium | 13.4a |
| Write `plugin-development.md` | SDK guide with example plugin | High | 13.4a |
| Publish OpenAPI spec | Export from FastAPI, publish to `docs/` | Low | 13.4a |

---

## 3. Module Dependency Graph

```
══════════════════════════════════════════════════════════
                  MNEMO DEPENDENCY GRAPH
══════════════════════════════════════════════════════════

Phase 0: Development Environment
         │
         ▼
Phase 1: Domain Models + Interfaces + Plugin Registry + Config
         │
         ├──────────────────────────────────────────┐
         ▼                                          ▼
Phase 2: Storage Layer                    (interfaces defined)
  ┌────────────────────────┐
  │ Filesystem             │
  │ SQLite FTS5            │
  │ Qdrant                 │
  │ SurrealDB              │
  │ CompositeStorage       │ ← CRITICAL: all phases below block on this
  └───────────┬────────────┘
              │
              ▼
Phase 3: Parser System
  ┌────────────────────────┐
  │ PDF Parser             │
  │ DOCX Parser            │
  │ Markdown Parser        │
  │ HTML Parser            │
  │ Text Parser            │
  │ Cleaner                │
  │ Classifier             │ ← CRITICAL: quality propagates everywhere
  └───────────┬────────────┘
              │
              ▼
Phase 4: Chunking Engine
  ┌────────────────────────┐
  │ Generic Chunker        │
  │ Book Chunker           │
  │ Paper Chunker          │
  │ Code Chunker           │
  │ Markdown Chunker       │ ← CRITICAL: determines retrieval quality ceiling
  │ Resume Chunker         │
  │ Slides Chunker         │
  │ Documentation Chunker  │
  │ Invariant Enforcement  │
  └───────────┬────────────┘
              │
              ▼
Phase 5: Embedding Pipeline
  ┌────────────────────────┐
  │ Ollama Embedder        │
  │ Embedding Cache        │
  │ Batch Embedder         │
  └───────────┬────────────┘
              │
              ▼
Phase 6: Retrieval Pipeline ← MOST COMPLEX PHASE
  ┌────────────────────────────────────────────────┐
  │ Query Planner (HyDE) ──► Dense Retriever       │
  │                      └──► Sparse Retriever     │
  │                      └──► Parent Retriever     │
  │                      └──► (Graph Retriever)    │
  │                               │                │
  │                         Result Fusion          │
  │                               │                │
  │                         Reranker               │
  │                               │                │
  │                         Context Builder        │
  │                               │                │
  │                         Synthesizer ───────► Citation Engine
  └───────────────────────────────┬────────────────┘
                                  │
              ┌───────────────────┤
              ▼                   ▼
Phase 7: REST API          Phase 8: MCP Server
  FastAPI                    stdio + SSE modes
  WebSocket                  6 MCP tools
  Auth Middleware
              │
              ▼
Phase 9: Web UI
  Dashboard, Notebook, Chat, Sources, Notes, Settings

              │
              ▼
Phase 10: Notebook Features
  Background Worker, Summaries, Insights, Session Memory, Incremental Indexing

              │
              ▼
Phase 11: Cross-Document Reasoning
  Entity Graph, Multi-Hop, Cross-Doc Synthesis, Graph UI

              │
              ▼
Phase 12: Plugin Ecosystem
  Plugin SDK, deepdoc-parser, podcast-gen, timeline-gen, watchfolder

              │
              ▼
Phase 13: Production Hardening
  Benchmarks, Observability, Docker Images, Documentation
```

### Critical Path

The critical path through the project is:

```
Phase 0 → Phase 1 → Phase 2 (CompositeStorage) → Phase 3 (Parsers) →
Phase 4 (Chunkers) → Phase 5 (Embedder) → Phase 6 (Retrieval) →
Phase 7 (REST API) → End-to-End MVP
```

Any delay on the critical path delays every subsequent phase. Phase 2 (CompositeStorage) and Phase 4 (Chunking Engine) are the two highest-risk modules on the critical path.

---

## 4. Implementation Order Rationale

| Phase | Why This Position |
|---|---|
| **Phase 0** | Nothing can be built without tooling. Pre-commit hooks prevent regressions from day one. |
| **Phase 1** | Interfaces must be defined before any implementation, because every subsequent implementation is *against* an interface. Getting an interface wrong at Phase 6 causes cascading rework through Phases 3–5. |
| **Phase 2** | Storage is the bottom layer. Every module above it writes to or reads from storage. Building parsers without storage means tests have nowhere to store results. |
| **Phase 3** | Parsers are the input to chunkers. Without parsers, chunker tests require synthetic data. With parsers, chunkers can be tested against real documents. |
| **Phase 4** | Chunkers are the input to the embedder. Chunking quality directly determines retrieval quality. It must be correct before the embedding pipeline is built, because changing chunking after embeddings are stored requires full re-indexing. |
| **Phase 5** | Embedder is blocked on chunkers (needs chunks to embed). |
| **Phase 6** | All retrieval modules depend on having embedded chunks in storage. Must come after Phase 5. |
| **Phase 7** | REST API is an adapter over a working core. Building the API before the core works leads to an untestable API. |
| **Phase 8** | MCP server is an adapter over the same core as the REST API. Can be built in parallel with Phase 7 if resources allow, but sequentially to reduce context switching. |
| **Phase 9** | UI requires a working API to be useful and testable. |
| **Phase 10** | Notebook features (background jobs, summaries, session memory) extend a working retrieval system. |
| **Phase 11** | Cross-document reasoning extends the retrieval pipeline with graph-based enrichment. Placed after notebook features so the base pipeline is stable. |
| **Phase 12** | Plugin ecosystem requires stable interfaces (Phase 1) and working implementations to test against. |
| **Phase 13** | Production hardening requires a complete system to harden. |

**Modules blocked by Phase 2 (CompositeStorage):** Every module that reads or writes data. All of Phases 3–13.

**Modules blocked by Phase 6 (Retrieval Pipeline):** REST API, MCP Server, UI, all notebook features.

---

## 5. Milestones

| Milestone | Description | Exit Criteria | Phase End |
|---|---|---|---|
| **M0 — Dev Rails** | All tooling, CI, and Docker scaffolds operational | Python/frontend quality gates pass; distributions and Dockerfiles build; Compose files validate. | Phase 0 |
| **M1 — Core Skeleton** | Interfaces and domain models compile | `from mnemo import KnowledgeEngine; engine = KnowledgeEngine(config)` works | Phase 1 |
| **M2 — Storage Live** | All four backends operational | Write a chunk to all backends. Read it back. Delete it. All pass. | Phase 2 |
| **M3 — First Parse** | PDF parser returns typed blocks | Parse a 100-page PDF → `ParsedDocument` with correct block count, headings preserved | Phase 3 |
| **M4 — First Chunks** | PDF → structured chunks with hierarchy | Parse + chunk "The Intelligent Investor" → chapters produce distinct chunks with correct `heading_path` | Phase 4 |
| **M5 — First Embeddings** | Chunks embedded and stored in Qdrant | 1000 chunks embedded via Ollama `nomic-embed-text`. All stored in Qdrant. | Phase 5 |
| **M6 — First Retrieval** | End-to-end query against one document returns cited answer | Ingest one PDF. Query it. Receive answer with at least one citation pointing to correct page. | Phase 6 |
| **M7 — API Live** | REST API operational, all endpoints return correct responses | Full Postman/HTTPie test suite passes. WebSocket streaming delivers token-by-token. | Phase 7 |
| **M8 — MCP Live** | Claude Desktop can query notebooks | Configure Claude Desktop. Ask "what do my documents say about X?". Claude receives grounded answer with citations. | Phase 8 |
| **M9 — UI MVP** | Full NotebookLM-equivalent workflow in browser | Create notebook → upload PDF → chat → see citations, all in browser. | Phase 9 |
| **M10 — Notebook Complete** | Background enrichment, summaries, session memory | Upload 10 documents. Wait for background enrichment. Query using 3-turn session. Receive session-aware answer. | Phase 10 |
| **M11 — Multi-Doc Reasoning** | Cross-document synthesis with entity graph | Query a 10-source notebook. Receive answer comparing claims across sources with per-source citations. | Phase 11 |
| **M12 — Plugin Ecosystem** | Podcast generated, deepdoc parser working | Install `mnemo-plugin-podcast-gen`. Generate 10-minute podcast from a 5-source notebook. | Phase 12 |
| **M13 — Production** | 100K docs, <30s latency, Docker images published | Benchmark: 100K documents, 20M chunks. End-to-end query latency ≤30s. Docker image published. | Phase 13 |

---

## 6. Test Plan

### Testing Philosophy

- Every module has unit tests before implementation (TDD is optional but encouraged).
- Integration tests run against real Docker-based storage (not mocks).
- Regression tests protect every milestone from regressions in subsequent phases.
- Performance tests gate each phase that touches storage or retrieval.

---

### Phase 0 Tests

| Type | Tests |
|---|---|
| **Unit** | Python and frontend formatting, linting, typing, and tests pass |
| **Integration** | All Compose configurations validate and all scaffold Dockerfiles build |
| **Manual** | Developer can clone, `uv sync`, `pytest` in < 5 min |

---

### Phase 1 Tests

| Type | Tests |
|---|---|
| **Unit** | Every dataclass instantiates with all required fields |
| **Unit** | Every Protocol interface is implementable (create a trivial mock, verify type checker accepts it) |
| **Unit** | Plugin registry: priority conflict resolution, missing implementation returns None |
| **Unit** | Configuration defaults, TOML loading, environment precedence, validation, paths, immutability, and serialization |
| **Unit** | KnowledgeEngine lifecycle, plugin discovery, provider resolution, rollback, and no-I/O boundary |

---

### Phase 2 Tests

| Type | Tests |
|---|---|
| **Unit** | `CompositeStorage.upsert_chunks()` → rollback when one backend fails |
| **Integration** | Write chunk to all 4 backends, read back, assert equality |
| **Integration** | Delete chunk, assert absence in all backends |
| **Integration** | `search_dense()` returns chunks by cosine similarity |
| **Integration** | `search_sparse()` returns chunks by BM25 |
| **Performance** | Upsert 10,000 chunks in < 60 seconds |

---

### Phase 3 Tests

| Type | Tests |
|---|---|
| **Unit** | PDF parser: heading detection accuracy on sample academic paper |
| **Unit** | Cleaner: hyphenated line breaks fixed, headers/footers removed |
| **Unit** | Classifier: 20 sample documents classified correctly without LLM |
| **Integration** | Parse → Clean → Classify pipeline on 5 document types |
| **Regression** | Parse the same PDF twice → identical `ParsedDocument` (deterministic) |
| **Manual** | Inspect `ParsedDocument` for a 300-page book. Verify chapters are HeadingBlocks. |

---

### Phase 4 Tests

| Type | Tests |
|---|---|
| **Unit** | Every chunker: min/max invariants enforced on synthetic input |
| **Unit** | `BookChunker`: chunks never cross chapter boundaries |
| **Unit** | `CodeChunker`: functions never split mid-body |
| **Unit** | Chunk IDs are stable on re-chunking identical content |
| **Unit** | `heading_path` is correct on all chunker types |
| **Integration** | Parse + chunk a real 500-page book → verify chapter/section hierarchy |
| **Performance** | Chunk 1000 pages in < 10 seconds |
| **Regression** | Re-chunk after minor edit → only changed chunks get new IDs |

---

### Phase 5 Tests

| Type | Tests |
|---|---|
| **Unit** | Embedding cache: second call for same text returns cached vector |
| **Unit** | Dimension mismatch detection raises error |
| **Integration** | Embed 100 chunks via Ollama `nomic-embed-text` → all stored in Qdrant |
| **Performance** | Embed 10,000 chunks in < 5 minutes (batch mode) |

---

### Phase 6 Tests

| Type | Tests |
|---|---|
| **Unit** | `QueryPlanner` returns valid `RetrievalPlan` JSON for 10 sample queries |
| **Unit** | `DenseRetriever` returns top-k with scores in [0,1] |
| **Unit** | `SparseRetriever` returns exact-match chunks for identifier queries |
| **Unit** | `ParentRetriever`: sibling co-occurrence upgrade triggers correctly |
| **Unit** | `CitationEngine`: `[source:2]` → correct chunk resolved |
| **Unit** | `ContextBuilder`: never exceeds token budget |
| **Integration** | Ingest 1 PDF. Query. Assert answer references correct page. |
| **Integration** | Multi-hop: query about entity relationship returns cross-chunk evidence |
| **Regression** | Reranker failure → RRF fallback succeeds |
| **Performance** | Full retrieval pipeline (no synthesis) < 500ms on 100K chunk corpus |
| **Acceptance** | 10 manually verified question-answer pairs from a known document return correct citations |

---

### Phase 7 Tests

| Type | Tests |
|---|---|
| **Unit** | Every endpoint returns 422 on invalid request body |
| **Integration** | Full CRUD cycle for notebooks, sources, sessions via HTTP |
| **Integration** | `POST /v1/query` returns citations |
| **Integration** | WebSocket streaming: all 5 events received in correct order |
| **Integration** | Auth: API key mode rejects missing/wrong keys with 401 |
| **Performance** | 100 concurrent REST queries → no timeout |

---

### Phase 8 Tests

| Type | Tests |
|---|---|
| **Integration** | `query_notebook` tool returns cited answer |
| **Integration** | MCP protocol conformance: all 6 tools pass spec test suite |
| **Manual** | Claude Desktop: configure `mnemo-mcp`, run 5 queries, verify citations |

---

### Phase 9 Tests

| Type | Tests |
|---|---|
| **Unit** | React components render without errors (`vitest`) |
| **Integration** | Upload PDF via UI → see ingestion progress → query → see citation |
| **Manual** | Full NotebookLM MVP workflow walkthrough |

---

### Phase 10 Tests

| Type | Tests |
|---|---|
| **Integration** | Upload document → background job completes → session questions enabled |
| **Integration** | 3-turn session: third question correctly references prior turns |
| **Integration** | Re-upload modified document → only changed chunks re-indexed |

---

### Phase 11 Tests

| Type | Tests |
|---|---|
| **Integration** | 5-source notebook → cross-doc query → answer cites 3+ sources |
| **Integration** | Knowledge graph: entity from document A linked to entity from document B |

---

### Phase 12 Tests

| Type | Tests |
|---|---|
| **Integration** | Install `mnemo-plugin-deepdoc-parser` → complex PDF parsed with higher accuracy |
| **Integration** | Generate podcast from 3-source notebook → valid MP3 produced |
| **Unit** | Plugin install/uninstall lifecycle: registry correctly updated |

---

### Phase 13 Tests

| Type | Tests |
|---|---|
| **Performance** | 100K documents, 20M chunks: query latency ≤30s |
| **Performance** | Ingestion throughput: ≥10 documents/minute (100-page PDFs) |
| **Performance** | `docker compose up` → first query in < 60 seconds (fresh install) |
| **Stress** | 24-hour continuous operation: no memory leaks, no crash |

---

## 7. Reference Mapping

| Module | Study Reference | Specific Files | What to Learn (NOT Copy) |
|---|---|---|---|
| PDF Parser (advanced) | RAGFlow `deepdoc` | `rag/app/paper.py`, `rag/nlp/` | Layout analysis algorithm, heading detection, table extraction strategy |
| Resume Parser | RAGFlow `deepdoc` | `rag/app/resume.py` | Structured section detection approach |
| Document Cleaning | RAGFlow | `rag/nlp/text.py` | Header/footer frequency analysis algorithm |
| Chunking (Book) | RAGFlow | `rag/app/book.py` | Three-level hierarchy design |
| Chunking (Code) | RAG-Anything | Any code parsing module | AST-based chunking concept |
| Entity Graph | RAG-Anything | Graph construction modules | Lazy graph construction approach — NOT the LLM-per-chunk ingestion pattern |
| Knowledge Graph query | RAG-Anything | Query graph modules | Multi-hop entity traversal pattern |
| MCP Protocol | Open Notebook | `open_notebook/mcp/` | MCP tool registration pattern |
| Session management | Open Notebook | `open_notebook/graphs/` | Session memory injection |
| SurrealDB queries | Open Notebook | All SurrealDB call sites | Query patterns, connection lifecycle |
| Notebook UX flow | Open Notebook | UI components | Feature scope, user workflow |
| Podcast generation | Open Notebook | `open_notebook/podcast/` | Script generation approach, TTS integration |
| Streaming API | Open Notebook, RAGFlow | WebSocket handlers | Streaming event protocol |

**IMPORTANT:** The reference repositories are **read-only inspiration**. We study *patterns* and *algorithms*, not syntax. We do not copy implementations.

---

## 8. Project Structure

This is the planned end-state tree. Phase 1 currently contains the domain,
interface, registry, configuration, and engine files documented by changelogs
0001–0005; later directories appear only in their designated phases.

```
mnemo/
│
├── mnemo-core/                  ← Layer 1: Pure Python library
│   ├── mnemo/
│   │   ├── __init__.py          ← Exports KnowledgeEngine
│   │   ├── engine.py            ← KnowledgeEngine class
│   │   ├── config.py            ← MnemoConfig, LLMRoleConfig, StorageConfig
│   │   ├── registry.py          ← PluginRegistry
│   │   │
│   │   ├── interfaces/          ← All typed Protocol contracts (no implementations)
│   │   │   ├── __init__.py
│   │   │   ├── parser.py
│   │   │   ├── chunker.py
│   │   │   ├── embedding.py
│   │   │   ├── retriever.py
│   │   │   ├── reranker.py
│   │   │   ├── llm.py
│   │   │   └── storage.py
│   │   │
│   │   ├── models/              ← All domain dataclasses/Pydantic models
│   │   │   ├── __init__.py
│   │   │   ├── blocks.py        ← Block types
│   │   │   ├── chunks.py        ← Chunk, ChunkType, ChunkPosition
│   │   │   ├── documents.py     ← ParsedDocument, DocumentMetadata, DocType
│   │   │   ├── retrieval.py     ← ScoredChunk, MetadataFilter, RetrievalPlan
│   │   │   ├── graph.py         ← Entity, GraphEdge
│   │   │   └── notebook.py      ← Notebook, Source, Session, Turn, Citation, Note, Insight
│   │   │
│   │   ├── ingestion/           ← The fast path pipeline
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py      ← Orchestrates stages 0–8
│   │   │   ├── router.py        ← ParserRouter (format detection + routing)
│   │   │   ├── cleaner.py       ← DocumentCleaner
│   │   │   ├── classifier.py    ← DocType classification
│   │   │   ├── embedder.py      ← EmbedderModule (cache + batch + provider)
│   │   │   └── indexer.py       ← Atomic multi-backend indexer
│   │   │
│   │   ├── parsers/             ← Built-in ParserInterface implementations
│   │   │   ├── __init__.py
│   │   │   ├── pdf.py
│   │   │   ├── docx.py
│   │   │   ├── markdown.py
│   │   │   ├── html.py
│   │   │   ├── text.py
│   │   │   ├── json.py
│   │   │   └── csv.py
│   │   │
│   │   ├── chunkers/            ← Built-in ChunkerInterface implementations
│   │   │   ├── __init__.py
│   │   │   ├── dispatcher.py    ← ChunkerDispatcher (doctype → chunker)
│   │   │   ├── generic.py
│   │   │   ├── book.py
│   │   │   ├── paper.py
│   │   │   ├── code.py
│   │   │   ├── markdown.py
│   │   │   ├── resume.py
│   │   │   ├── slides.py
│   │   │   └── documentation.py
│   │   │
│   │   ├── retrieval/           ← The retrieval pipeline
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py      ← Orchestrates retrieval steps 1–10
│   │   │   ├── planner.py       ← QueryPlanner (HyDE, query decomposition)
│   │   │   ├── dense.py         ← DenseRetriever
│   │   │   ├── sparse.py        ← SparseRetriever
│   │   │   ├── parent.py        ← ParentRetriever
│   │   │   ├── fusion.py        ← RRF + deduplication
│   │   │   ├── reranker.py      ← CrossEncoderReranker
│   │   │   ├── context.py       ← ContextBuilder
│   │   │   ├── synthesizer.py   ← Synthesizer (LLM grounded answer)
│   │   │   ├── citation.py      ← CitationEngine
│   │   │   └── multihop.py      ← Multi-hop orchestration
│   │   │
│   │   ├── storage/             ← StorageInterface implementations
│   │   │   ├── __init__.py
│   │   │   ├── composite.py     ← CompositeStorage (routes to all backends)
│   │   │   ├── qdrant.py        ← QdrantStore
│   │   │   ├── sqlite.py        ← SQLiteStore (FTS5 + embedding cache)
│   │   │   ├── surrealdb.py     ← SurrealDBStore
│   │   │   └── filesystem.py    ← Blob store
│   │   │
│   │   ├── notebook/            ← Notebook management (no LLM calls)
│   │   │   ├── __init__.py
│   │   │   ├── manager.py       ← NotebookManager
│   │   │   ├── source.py        ← SourceManager
│   │   │   ├── session.py       ← SessionManager
│   │   │   └── insight.py       ← InsightManager
│   │   │
│   │   ├── llm/                 ← LLMInterface implementations
│   │   │   ├── __init__.py
│   │   │   └── ollama.py        ← OllamaLLM
│   │   │
│   │   └── background/          ← Slow path worker
│   │       ├── __init__.py
│   │       ├── worker.py        ← Background job runner
│   │       └── tasks/
│   │           ├── ner.py       ← Stage 9A: NER
│   │           ├── questions.py ← Stage 9B: Question generation
│   │           ├── summaries.py ← Stage 9C: Summaries
│   │           └── graph.py     ← Stage 9D: Graph edges
│   │
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   └── pyproject.toml
│
├── mnemo-server/                ← Layer 2: HTTP adapter (no business logic)
│   ├── mnemo_server/
│   │   ├── __init__.py
│   │   ├── app.py               ← FastAPI app + lifespan
│   │   ├── deps.py              ← KnowledgeEngine dependency injection
│   │   │
│   │   ├── api/                 ← REST API route handlers
│   │   │   ├── __init__.py
│   │   │   ├── notebooks.py
│   │   │   ├── sources.py
│   │   │   ├── query.py
│   │   │   ├── sessions.py
│   │   │   ├── notes.py
│   │   │   ├── insights.py
│   │   │   └── system.py
│   │   │
│   │   ├── schemas/             ← Request/response Pydantic models
│   │   │   ├── requests.py
│   │   │   └── responses.py
│   │   │
│   │   ├── ws/
│   │   │   └── streaming.py     ← WebSocket /ws/query handler
│   │   │
│   │   ├── mcp/
│   │   │   ├── server.py        ← MCP server (stdio + SSE)
│   │   │   └── tools.py         ← 6 MCP tool implementations
│   │   │
│   │   └── auth/
│   │       └── middleware.py    ← None / API key / JWT middleware
│   │
│   ├── tests/
│   └── pyproject.toml
│
├── mnemo-ui/                    ← Layer 3: React frontend
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx              ← Router setup
│   │   │
│   │   ├── api/                 ← API client (never import mnemo-core)
│   │   │   ├── client.ts        ← Base httpx client + interceptors
│   │   │   ├── notebooks.ts
│   │   │   ├── sources.ts
│   │   │   ├── query.ts
│   │   │   ├── sessions.ts
│   │   │   └── ws.ts            ← WebSocket client
│   │   │
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Notebooks.tsx
│   │   │   ├── Notebook.tsx
│   │   │   ├── Search.tsx
│   │   │   └── Settings.tsx
│   │   │
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   ├── citation/
│   │   │   ├── sources/
│   │   │   ├── graph/
│   │   │   └── common/
│   │   │
│   │   └── store/               ← State management (Zustand)
│   │
│   ├── tests/
│   └── package.json
│
├── plugins/                     ← Layer 4: Optional extensions
│   ├── deepdoc-parser/
│   │   ├── deepdoc_parser/
│   │   └── pyproject.toml
│   ├── podcast-gen/
│   ├── timeline-gen/
│   ├── watchfolder/
│   ├── git-ingestion/
│   └── email-ingestion/
│
├── docker/
│   ├── docker-compose.yml
│   ├── docker-compose.minimal.yml
│   ├── docker-compose.dev.yml
│   ├── core.Dockerfile
│   ├── server.Dockerfile
│   └── ui.Dockerfile
│
├── docs/
│   ├── quickstart.md
│   ├── api-reference.md
│   ├── mcp-integration.md
│   ├── plugin-development.md
│   └── adr/                     ← Architecture Decision Records
│       └── 001-four-storage-backends.md
│
├── scripts/
│   ├── setup.sh                 ← Dev environment bootstrap
│   ├── benchmark.py             ← Performance benchmarks
│   └── seed_data.py             ← Seed sample notebook for testing
│
├── examples/
│   ├── python-library-usage/    ← Direct mnemo-core usage example
│   ├── rest-api-client/         ← HTTP client example
│   └── mcp-claude-desktop/      ← Claude Desktop config example
│
├── config/
│   ├── mnemo.example.yaml       ← Annotated example config
│   └── mnemo.minimal.yaml       ← Minimal config
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
│
├── .pre-commit-config.yaml
├── ruff.toml
├── pyproject.toml               ← Root workspace
└── README.md
```

---

## 9. GitHub Project Plan

### Epic Structure

```
EPIC 1: mnemo-core — Foundation
  FEATURE 1.1: Domain Models and Types
    ISSUE: Define all Block types (TextBlock, HeadingBlock, etc.)
    ISSUE: Define ParsedDocument, DocumentMetadata, DocType
    ISSUE: Define Chunk, ChunkType, ChunkPosition, ScoredChunk
    ISSUE: Define Session, Turn, Citation, Entity, GraphEdge
    ISSUE: Define Notebook, Source, Note, Insight

  FEATURE 1.2: Interface Contracts
    ISSUE: ParserInterface Protocol + acceptance test
    ISSUE: ChunkerInterface Protocol + acceptance test
    ISSUE: EmbeddingProvider Protocol + acceptance test
    ISSUE: RetrieverInterface Protocol + acceptance test
    ISSUE: RerankerInterface Protocol + acceptance test
    ISSUE: LLMInterface Protocol + acceptance test
    ISSUE: StorageInterface Protocol + acceptance test

  FEATURE 1.3: Plugin Registry
    ISSUE: PluginRegistry class + slot registration
    ISSUE: Entry-point based plugin discovery
    ISSUE: Priority conflict resolution
    ISSUE: PluginRegistry unit tests

  FEATURE 1.4: Configuration System
    ISSUE: MnemoConfig Pydantic model
    ISSUE: LLMRoleConfig per-role configuration
    ISSUE: Config loading from file and env

  FEATURE 1.5: KnowledgeEngine
    ISSUE: KnowledgeEngine class + initialize() + shutdown() + lifecycle inspection

EPIC 2: mnemo-core — Storage Layer
  FEATURE 2.1: Filesystem Blob Store
    ISSUE: Content-addressed blob store implementation
    ISSUE: ParsedDocument IR serialization/deserialization

  FEATURE 2.2: SQLite FTS5 Store
    ISSUE: Schema design + migration runner
    ISSUE: Chunk CRUD + FTS5 indexing
    ISSUE: BM25 search implementation
    ISSUE: Session/turn/citation tables
    ISSUE: Embedding cache table

  FEATURE 2.3: Qdrant Vector Store
    ISSUE: QdrantStore + collection initialization
    ISSUE: Named vector upsert + payload filters
    ISSUE: ANN dense search with metadata filtering
    ISSUE: Qdrant memmap mode configuration

  FEATURE 2.4: SurrealDB Store
    ISSUE: Schema design (all tables)
    ISSUE: Document, Notebook, Source CRUD
    ISSUE: Session/turn/citation storage
    ISSUE: Entity graph storage + traversal query
    ISSUE: Job queue implementation

  FEATURE 2.5: Composite Storage Router
    ISSUE: CompositeStorage multi-backend routing
    ISSUE: Atomic upsert with rollback

EPIC 3: mnemo-core — Parser System
  FEATURE 3.1: Parser Infrastructure
    ISSUE: ParserRouter (format detection, routing, dedup gate)

  FEATURE 3.2: Document Parsers
    ISSUE: BasicPDFParser (pymupdf, layout-aware)
    ISSUE: DOCXParser
    ISSUE: MarkdownParser (AST-based)
    ISSUE: HTMLParser (semantic + boilerplate removal)
    ISSUE: PlainTextParser, JSONParser, CSVParser

  FEATURE 3.3: Document Cleaner
    ISSUE: DocumentCleaner (normalization, header/footer removal, language detection)

  FEATURE 3.4: Document Classifier
    ISSUE: Rule-based DocType classifier
    ISSUE: LLM-assisted classifier (fallback)

EPIC 4: mnemo-core — Chunking Engine
  FEATURE 4.1: Chunker Infrastructure
    ISSUE: ChunkerDispatcher (doctype → strategy)
    ISSUE: Parent-child and sibling ID linking
    ISSUE: Chunking invariants enforcement

  FEATURE 4.2: Chunker Implementations
    ISSUE: GenericChunker
    ISSUE: BookChunker (ToC extraction + 3-level hierarchy)
    ISSUE: PaperChunker (canonical sections + equation handling)
    ISSUE: CodeChunker (tree-sitter AST + call context)
    ISSUE: MarkdownChunker
    ISSUE: ResumeChunker (section isolation + role chunks)
    ISSUE: SlidesChunker
    ISSUE: DocumentationChunker

EPIC 5: mnemo-core — Embedding Pipeline
  FEATURE 5.1: OllamaEmbedder + Embedding Cache + EmbedderModule
    ISSUE: OllamaEmbedder implementation
    ISSUE: Content-addressable embedding cache
    ISSUE: Batch embedding + parallel concurrency

EPIC 6: mnemo-core — Retrieval Pipeline
  FEATURE 6.1: Query Planning
    ISSUE: QueryPlanner + RetrievalPlan schema
    ISSUE: HyDE query expansion

  FEATURE 6.2: Retrievers
    ISSUE: DenseRetriever (Qdrant HNSW)
    ISSUE: SparseRetriever (SQLite FTS5 BM25)
    ISSUE: ParentRetriever (sibling co-occurrence upgrade)

  FEATURE 6.3: Fusion + Reranking
    ISSUE: Parallel retrieval runner
    ISSUE: Deduplication + RRF fusion
    ISSUE: CrossEncoderReranker + RRF fallback

  FEATURE 6.4: Context and Synthesis
    ISSUE: ContextBuilder (token budget + compression)
    ISSUE: Synthesizer (grounded LLM + streaming)
    ISSUE: CitationEngine (marker parsing + persistence)

  FEATURE 6.5: Multi-Hop
    ISSUE: Multi-hop retrieval orchestration (≤3 hops)

EPIC 7: mnemo-server — REST API
  FEATURE 7.1: FastAPI Setup
    ISSUE: App initialization, CORS, error handling, engine injection

  FEATURE 7.2: API Endpoints
    ISSUE: Notebook endpoints (CRUD + summary + timeline + graph)
    ISSUE: Source/ingestion endpoints + job status polling
    ISSUE: Query endpoint + search endpoint
    ISSUE: Session/memory endpoints
    ISSUE: Notes and insights endpoints
    ISSUE: System endpoints (health, config, jobs)

  FEATURE 7.3: WebSocket Streaming
    ISSUE: /ws/query WebSocket handler + 5-event protocol

  FEATURE 7.4: Authentication
    ISSUE: None / API key / JWT middleware

EPIC 8: mnemo-server — MCP Server
  FEATURE 8.1: MCP Server
    ISSUE: MCP server (stdio + SSE modes)
    ISSUE: mnemo-mcp CLI entrypoint

  FEATURE 8.2: MCP Tools
    ISSUE: query_notebook tool
    ISSUE: search_all_notebooks tool
    ISSUE: list_notebooks, get_notebook_summary, get_source_insights, get_timeline tools
    ISSUE: MCP spec conformance testing

EPIC 9: mnemo-ui — Web Interface
  FEATURE 9.1: Foundation
    ISSUE: Design tokens, routing, API client, WebSocket client

  FEATURE 9.2: Pages
    ISSUE: Dashboard page
    ISSUE: Notebooks list page
    ISSUE: Notebook detail + tabs (Chat, Sources, Notes)
    ISSUE: Settings page
    ISSUE: Global search page

  FEATURE 9.3: Chat Interface
    ISSUE: Message history + token streaming
    ISSUE: Citation footnotes (interactive, link to source)
    ISSUE: Retrieval metadata display

EPIC 10: Notebook Features
  FEATURE 10.1: Background Worker
    ISSUE: Worker process + job queue polling
    ISSUE: Slow path stages (NER, questions, summaries, graph edges)

  FEATURE 10.2: Notebook Summaries + Insights + Session Memory
    ISSUE: Per-source summarization
    ISSUE: Notebook-level summary
    ISSUE: Insight extraction pipeline
    ISSUE: 3-tier session memory
    ISSUE: Incremental indexing (hash-based differential update)

EPIC 11: Cross-Document Reasoning
  FEATURE 11.1: Knowledge Graph
    ISSUE: spaCy NER in slow path
    ISSUE: Entity normalization + relationship extraction
    ISSUE: Multi-hop graph traversal

  FEATURE 11.2: Cross-Doc Synthesis + UI
    ISSUE: Cross-doc context segmentation + synthesis prompt
    ISSUE: Knowledge Graph Explorer UI
    ISSUE: Timeline UI

EPIC 12: Plugin Ecosystem
  FEATURE 12.1: Plugin SDK
    ISSUE: Plugin development guide + template + compatibility testing

  FEATURE 12.2: First-Party Plugins
    ISSUE: deepdoc-parser plugin
    ISSUE: podcast-gen plugin
    ISSUE: timeline-gen plugin
    ISSUE: watchfolder plugin

EPIC 13: Production
  FEATURE 13.1: Performance + Observability
    ISSUE: 20M chunk benchmark + optimization
    ISSUE: Structured logging + tracing
    ISSUE: Qdrant memmap mode

  FEATURE 13.2: Docker + Documentation
    ISSUE: Multi-stage Dockerfiles + Docker Hub publishing
    ISSUE: quickstart.md
    ISSUE: api-reference.md, mcp-integration.md, plugin-development.md
    ISSUE: OpenAPI spec publication
```

---

## 10. Engineering Rules

These rules are non-negotiable. Any violation is a bug, not a style preference.

### Layering Rules
1. **No upward calls.** Core cannot import from server. Server cannot import from UI. Core is the bottom.
2. **No layer skipping.** UI calls only server. Server calls only core. UI never calls core directly.
3. **No HTTP in core.** `httpx`, `requests`, `fastapi`, `starlette` — none of these may appear in `mnemo-core` except in `llm/ollama.py`.
4. **No business logic in server.** If a route handler contains conditional logic beyond input validation and error handling, that logic belongs in core.

### Interface Rules
5. **Every implementation behind an interface.** No direct instantiation of storage classes, parser classes, or LLM classes outside of the registry.
6. **Interfaces use `Protocol`.** Not `ABC`. `typing.Protocol` allows structural subtyping without forcing inheritance.
7. **Interface methods are async.** All I/O-touching interface methods are `async def`. Pure computation methods may be synchronous.
8. **Interfaces are versioned.** Breaking changes to an interface require a new version (`ParserInterfaceV2`). Old version supported for ≥2 minor releases.

### Code Quality Rules
9. **100% type hints.** Every function and method has complete type annotations. `mypy --strict` must pass.
10. **No `Any` types.** `Any` is forbidden in production code. Use `Unknown` or `object` where necessary.
11. **Unit tests required.** Every public function must have at least one unit test.
12. **No commented-out code.** Dead code is deleted. If it might be needed later, it lives in git history.
13. **Docstrings on all public interfaces.** Every public class, method, and function in `interfaces/` and public API surfaces has a docstring.

### Architecture Decision Rules
14. **Architecture Decision Records for major changes.** Any change that affects the four-layer model, interface contracts, or storage choices requires a written ADR in `docs/adr/`.
15. **No redesign without ADR.** The architecture is frozen. Proposals to change it go through the ADR process.

### Plugin Rules
16. **Plugins fail gracefully.** A crashing plugin disables its capability, not the system. All plugin loading is wrapped in try/except.
17. **Plugins declare version compatibility.** `pyproject.toml` must declare `mnemo-core>=X.Y,<X.Z` compatibility.
18. **No circular plugin dependencies.** Plugins may not import other plugins.

### Privacy Rules
19. **No telemetry.** No analytics, no crash reporting, no `ping home` of any kind. Ever.
20. **No external network calls in core.** The only external call in core is to Ollama (local). Storage backends are local. No cloud calls.

### Git Rules
21. **Conventional commits.** `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`. Required for changelog generation.
22. **No force-push to main.** Feature branches only. PRs required for main.
23. **All PRs require passing CI.** Lint, typecheck, unit tests, integration tests must pass.

---

## 11. Estimation and Risk

### Phase Complexity and Risk

| Phase | Duration | Complexity | Risk | Risk Driver |
|---|---|---|---|---|
| **P0 — Dev Env** | 1 week | Low | Low | Tooling setup is well-understood |
| **P1 — Interfaces** | 2 weeks | Medium | **HIGH** | Wrong interface design propagates to all subsequent phases |
| **P2 — Storage** | 3 weeks | High | **HIGH** | CompositeStorage atomic rollback is complex; SurrealDB API instability |
| **P3 — Parsers** | 4 weeks | High | Medium | PDF layout analysis is heuristic-heavy; correctness is hard to verify |
| **P4 — Chunkers** | 5 weeks | **Very High** | **HIGH** | Nine strategies, each with domain-specific complexity; errors invisible until retrieval |
| **P5 — Embedder** | 2 weeks | Low | Low | Ollama API is stable; cache logic is straightforward |
| **P6 — Retrieval** | 6 weeks | **Very High** | **HIGH** | Most complex phase; 10 interdependent modules; integration bugs hard to trace |
| **P7 — REST API** | 4 weeks | Medium | Low | FastAPI is mature; adapter-only code is low risk |
| **P8 — MCP Server** | 3 weeks | Medium | Medium | MCP spec is evolving; SDK maturity uncertain |
| **P9 — Web UI** | 7 weeks | High | Medium | Frontend state complexity; streaming rendering |
| **P10 — Notebook** | 5 weeks | High | Medium | Background workers, incremental indexing correctness |
| **P11 — Cross-doc** | 4 weeks | High | **HIGH** | Entity normalization is hard; graph quality depends on LLM quality |
| **P12 — Plugins** | 6 weeks | Medium | Low | Plugin SDK is additive, doesn't touch core |
| **P13 — Production** | 6 weeks | High | Medium | Performance at 20M chunks may require significant Qdrant tuning |

---

### Highest-Risk Modules (Detailed)

#### Risk 1: Interface Contract Design (Phase 1)
**Risk:** If `StorageInterface` or `ChunkerInterface` is underspecified, every implementation breaks when the interface is corrected later.  
**Mitigation:** Spend extra time here. Write acceptance tests for each interface *before* any implementation. Use the ADR process to record any interface evolution decisions.

#### Risk 2: CompositeStorage Atomic Rollback (Phase 2)
**Risk:** Partial write (e.g., Qdrant succeeds, SurrealDB fails) leaves the system in an inconsistent state.  
**Mitigation:** Design the rollback protocol as the first thing in Phase 2, before any individual backend. Write chaos tests that intentionally fail individual backends.

#### Risk 3: Chunking Quality (Phase 4)
**Risk:** Chunking errors are silent — tests pass but retrieval quality is poor. A `BookChunker` that doesn't correctly detect chapter boundaries produces chunks that span chapters, making retrieval nonsensical for specific chapter queries.  
**Mitigation:** Build a manual evaluation framework. For every chunker, create 5 ground-truth documents where the "correct" chunks are manually labeled. Run these as acceptance tests.

#### Risk 4: Retrieval Pipeline Integration (Phase 6)
**Risk:** Dense + sparse + parent + reranker produce different result sets; fusion bugs only manifest at integration level.  
**Mitigation:** Build the pipeline incrementally: dense-only first → add sparse → add fusion → add reranker → add parent. Merge nothing until the previous level passes its integration tests.

#### Risk 5: SurrealDB API Instability (Phase 2, Phase 10–11)
**Risk:** SurrealDB is a younger database. Its Python client has had breaking changes between minor versions. Graph traversal query syntax may change.  
**Mitigation:** Pin exact SurrealDB version. Write an adapter that isolates all SurrealDB-specific queries in `surrealdb.py`. If SurrealDB becomes unviable, the fallback is PostgreSQL + SQLite (no graph retrieval).

#### Risk 6: MCP Spec Evolution (Phase 8)
**Risk:** The MCP spec is actively evolving. Breaking changes to the protocol would require rework.  
**Mitigation:** Track the `mcp` Python SDK version. Write an integration test that runs against the MCP inspector tool. Accept that MCP may need to be updated in Phase 13.

---

## 12. Master Implementation Checklist

### Phase 0 — Development Environment

- ☑ `git init`, `.gitignore`, `LICENSE`
- ☑ Monorepo directory structure created
- ☑ Root `pyproject.toml` with `uv` workspace
- ☑ `ruff.toml` configured
- ☑ `mypy` strict mode configured
- ☑ `pytest` + coverage configured
- ☑ `pre-commit` hooks: ruff, mypy, trailing whitespace
- ☑ React project initialized with Vite + TypeScript
- ☑ `biome` configured
- ☑ `vitest` configured
- ☑ GitHub Actions CI workflow
- ☑ `docker-compose.dev.yml` validated
- ☑ `docker-compose.yml` validated
- ☑ `docker-compose.minimal.yml` validated
- ☑ **[MILESTONE M0] Development rails validated; service implementations remain assigned to later phases**

### Phase 1 — mnemo-core Scaffolding

- ☑ `Block` types (all 7 subtypes)
- ☑ `ParsedDocument`, `DocumentMetadata`, `DocType`
- ☑ `Chunk`, `ChunkType`, `ChunkPosition`
- ☑ `ScoredChunk`, `MetadataFilter`
- ☑ `Entity`, `GraphEdge`
- ☑ `Session`, `Turn`, `Citation`
- ☑ `Document` (registry model)
- ☑ `Notebook`, `Source`, `Note`, `Insight`
- ☑ `ParserInterface` Protocol
- ☑ `ChunkerInterface` Protocol
- ☑ `EmbeddingProvider` Protocol
- ☑ `RetrieverInterface` Protocol
- ☑ `RerankerInterface` Protocol
- ☑ `LLMInterface` Protocol
- ☑ `StorageInterface` Protocol
- ☑ Interface version markers
- ☑ `PluginRegistry` class
- ☑ Slot registration methods
- ☑ Entry-point and configured-path plugin discovery
- ☑ Plugin conflict resolution
- ☑ `MnemoConfig` Pydantic model
- ☑ `LLMRoleConfig`
- ☑ `StorageConfig`
- ☑ Config loading (TOML + environment)
- ☑ `KnowledgeEngine` class
- ☑ `initialize()` and `shutdown()` methods
- ☑ Lifecycle-state capability inspection
- ☑ **[MILESTONE M1] `from mnemo import KnowledgeEngine` works**

`RetrievalPlan` and `SubQuery` remain assigned to Phase 6 query planning; they
were intentionally excluded from Module 1.1 by ADR-0001.

### Phase 2 — Storage Layer

- □ Content-addressed filesystem blob store
- □ `put_asset()` + `get_asset()`
- □ `put_parsed_document()` + `get_parsed_document()`
- □ SQLite schema + migration runner
- □ `SQLiteStore.upsert_chunks()` + FTS5 indexing
- □ `SQLiteStore.search_sparse()` BM25
- □ `SQLiteStore.delete_chunks_for_document()`
- □ Session/turn/citation tables
- □ Embedding cache table
- □ `QdrantStore` + collection initialization
- □ `QdrantStore.upsert_chunks()` (named vectors)
- □ `QdrantStore.search_dense()` with payload filter
- □ `QdrantStore` memmap mode config
- □ `SurrealDBStore` + schema init
- □ Document/Notebook/Source CRUD
- □ Session/turn/citation storage
- □ Entity/graph storage + traversal
- □ Job queue
- □ `CompositeStorage` routing
- □ Atomic upsert with rollback
- □ **[MILESTONE M2] Write/read/delete chunk across all backends**

### Phase 3 — Parser System

- □ `ParserRouter` + MIME detection + dedup gate
- □ `BasicPDFParser` (layout-aware, tables, images, headings)
- □ Running header/footer detection
- □ `DOCXParser`
- □ `MarkdownParser` (AST-based)
- □ `HTMLParser` + boilerplate removal
- □ `PlainTextParser`, `JSONParser`, `CSVParser`
- □ `DocumentCleaner` (unicode, whitespace, hyphenation, language detection)
- □ Rule-based `DocType` classifier
- □ LLM-assisted classifier (fallback)
- □ **[MILESTONE M3] Parse 100-page PDF → correct ParsedDocument**

### Phase 4 — Chunking Engine

- □ `ChunkerDispatcher`
- □ Parent-child ID linking
- □ Sibling ID linking
- □ Chunking invariants enforcement
- □ Chunk ID computation (`sha256`)
- □ `GenericChunker`
- □ `BookChunker` (ToC extraction + inference + 3 levels)
- □ `PaperChunker` (section detection + canonical mapping)
- □ `CodeChunker` (tree-sitter + 6 language grammars + call context)
- □ `MarkdownChunker`
- □ `ResumeChunker` (section isolation + role chunks)
- □ `SlidesChunker`
- □ `DocumentationChunker`
- □ **[MILESTONE M4] 500-page book → chunks with correct heading_path hierarchy**

### Phase 5 — Embedding Pipeline

- □ `OllamaEmbedder` (batch + retry + dimension detection)
- □ Embedding cache (lookup + write)
- □ Dimension mismatch detection
- □ `EmbedderModule` (cache + provider + batch orchestration)
- □ **[MILESTONE M5] 1000 chunks embedded and stored in Qdrant**

### Phase 6 — Retrieval Pipeline

- □ `QueryPlanner` + `RetrievalPlan` schema
- □ Intent detection
- □ Query decomposition
- □ HyDE query expansion
- □ HyDE paragraph embedding
- □ `DenseRetriever` (Qdrant with metadata filters)
- □ `SparseRetriever` (SQLite FTS5 BM25 + synonym expansion)
- □ `ParentRetriever` (sibling co-occurrence upgrade)
- □ Parallel retrieval runner
- □ Deduplication by chunk_id
- □ RRF fusion
- □ `CrossEncoderReranker` (ms-marco)
- □ Confidence threshold flagging
- □ RRF fallback
- □ `ContextBuilder` (token budget + compression + formatting)
- □ `Synthesizer` (grounded prompt + streaming)
- □ `CitationEngine` (marker parsing + SurrealDB persistence)
- □ Multi-hop orchestration (≤3 hops)
- □ **[MILESTONE M6] Ingest PDF → query → cited answer on correct page**

### Phase 7 — REST API

- □ FastAPI app + lifespan + CORS + error handling
- □ KnowledgeEngine dependency injection
- □ Notebook CRUD endpoints (7 endpoints)
- □ Sources/ingestion endpoints (5 endpoints)
- □ Query endpoint + search endpoint
- □ Session/memory endpoints (5 endpoints)
- □ Notes CRUD endpoints (4 endpoints)
- □ Insights endpoints (2 endpoints)
- □ System endpoints (health, config, jobs)
- □ All request Pydantic models
- □ All response Pydantic models
- □ WebSocket `/ws/query` + 5-event protocol
- □ Auth middleware (none / api-key / JWT)
- □ **[MILESTONE M7] All REST endpoints pass, WebSocket streaming works**

### Phase 8 — MCP Server

- □ MCP server (stdio mode)
- □ MCP server (SSE mode)
- □ `mnemo-mcp` CLI entrypoint
- □ `query_notebook` tool
- □ `search_all_notebooks` tool
- □ `list_notebooks` tool
- □ `get_notebook_summary` tool
- □ `get_source_insights` tool
- □ `get_timeline` tool
- □ MCP spec conformance tests
- □ **[MILESTONE M8] Claude Desktop successfully queries notebooks via MCP**

### Phase 9 — Web UI

- □ Design tokens + typography
- □ React Router v7 routes
- □ API client layer (`@tanstack/query`)
- □ WebSocket client (reconnection + streaming state)
- □ Dashboard page
- □ Notebooks list page
- □ Notebook detail page (tabs)
- □ Sources tab (upload + progress polling)
- □ Chat tab (streaming + citations)
- □ Notes tab (CRUD)
- □ Settings page (model config + plugins + health)
- □ Global search page
- □ Citation footnote rendering (interactive)
- □ **[MILESTONE M9] Full NotebookLM MVP workflow in browser**

### Phase 10 — Notebook Features

- □ Background worker process
- □ Job queue polling
- □ Stage 9A: NER extraction
- □ Stage 9B: Question generation
- □ Stage 9C: Section summaries
- □ Stage 9D: Graph edge extraction (rate-limited)
- □ Per-source summarization
- □ Notebook-level summary
- □ Summary staleness detection
- □ Insight extraction pipeline
- □ Insights storage + retrieval
- □ Tier 1 session memory (last N turns)
- □ Tier 2 session memory (within-session BM25)
- □ Tier 3 session memory (session notes as documents)
- □ Incremental indexing (hash-based diff)
- □ Differential chunk update
- □ **[MILESTONE M10] 10-doc notebook with background enrichment + 3-tier session memory**

### Phase 11 — Cross-Document Reasoning

- □ spaCy NER in slow path
- □ Entity normalization
- □ LLM relationship extraction (rate-limited)
- □ Multi-hop graph traversal (SurrealDB)
- □ Cross-doc context segmentation
- □ Cross-doc synthesis prompt
- □ Per-source citation attribution
- □ Knowledge Graph Explorer UI (`react-force-graph`)
- □ Node click → related chunks
- □ Timeline view
- □ **[MILESTONE M11] 10-source notebook → cross-source answer with graph**

### Phase 12 — Plugin Ecosystem

- □ Plugin development guide
- □ Cookiecutter plugin template
- □ Plugin compatibility CI test
- □ `deepdoc-parser` plugin (advanced PDF layout)
- □ `podcast-gen` plugin (script generation + Kokoro TTS)
- □ `timeline-gen` plugin
- □ `watchfolder` plugin
- □ Plugin install/uninstall lifecycle test
- □ **[MILESTONE M12] Podcast generated from 5-source notebook**

### Phase 13 — Production Hardening

- □ 20M chunk benchmark
- □ Qdrant HNSW parameter tuning
- □ Qdrant memmap mode implementation
- □ py-spy profiling + bottleneck resolution
- □ Structured logging (structlog + JSON output)
- □ Request trace IDs
- □ Performance metrics (ingestion, retrieval, embedding latency)
- □ Background job metrics
- □ Multi-stage core.Dockerfile
- □ Multi-stage server.Dockerfile
- □ UI production build + Dockerfile
- □ Docker Hub CI publishing
- □ `quickstart.md`
- □ `api-reference.md` (from OpenAPI)
- □ `mcp-integration.md`
- □ `plugin-development.md`
- □ OpenAPI spec published
- □ **[MILESTONE M13] 100K docs, 20M chunks, ≤30s latency, Docker images live**

---

*End of Mnemo Engineering Roadmap v1.0*  
*Architecture input: Mnemo Architecture Specification v2.0 (FROZEN)*  
*This document is the authoritative implementation tracker. All phase completion is gated on milestone criteria.*
