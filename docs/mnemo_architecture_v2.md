# Mnemo — Local Knowledge Engine
## Architecture Specification v2.0

**Document Type:** Design Specification  
**Status:** Living Design Document  
**Project Type:** Standalone Open-Source Software  
**License Target:** Apache 2.0  

**Implementation baseline:** Phase 0, Phase 1, Phase 2, and Phase 3 through
Module 3.9 are complete. The parser boundary returns transient
`ParseResult` values as specified by ADR-0011. Accepted ADRs refine public
schemas and contracts where this document previously used shorthand.

> *"A knowledge engine. Not an agent. The difference is everything."*

---

## A Note on Project Name

Throughout this document, the project is referred to as **Mnemo** (from *Mnemosyne*, the Greek goddess of memory and mother of the Muses). This is a working name. The final name is a project decision. What matters is that the name must convey: *local, personal, permanent, private* — not "AI assistant."

---

## Table of Contents

1. [Vision and Philosophy](#1-vision-and-philosophy)
2. [High-Level Architecture Diagram](#2-high-level-architecture-diagram)
3. [The Four-Layer Model](#3-the-four-layer-model)
4. [Layer 1 — mnemo-core](#4-layer-1--mnemo-core)
5. [Layer 2 — mnemo-server](#5-layer-2--mnemo-server)
6. [Layer 3 — mnemo-ui](#6-layer-3--mnemo-ui)
7. [Layer 4 — plugins/](#7-layer-4--plugins)
8. [Plugin Registry and Interface Contracts](#8-plugin-registry-and-interface-contracts)
9. [Document Ingestion Pipeline](#9-document-ingestion-pipeline)
10. [Adaptive Chunking Engine](#10-adaptive-chunking-engine)
11. [Retrieval Pipeline](#11-retrieval-pipeline)
12. [Conversation Memory](#12-conversation-memory)
13. [Storage Architecture](#13-storage-architecture)
14. [LLM Orchestration](#14-llm-orchestration)
15. [Performance Architecture](#15-performance-architecture)
16. [Scalability](#16-scalability)
17. [Integration Patterns](#17-integration-patterns)
18. [Deployment Model](#18-deployment-model)
19. [Implementation Roadmap](#19-implementation-roadmap)
20. [Critical Review](#20-critical-review)
21. [Final Architecture Snapshot](#21-final-architecture-snapshot)

---

## 1. Vision and Philosophy

### 1.1 What Mnemo Is

Mnemo is a **local-first Knowledge Engine**. It ingests documents, understands them deeply, and retrieves evidence in response to questions. It persists knowledge permanently. It cites every claim it surfaces. It runs entirely on a personal machine with no cloud dependency.

It is **not** an AI assistant.  
It is **not** an agent.  
It is **not** a task executor.

It is the epistemic layer beneath those things — the component that knows what you know, surfaces what is relevant, and hands the evidence upward to whatever reasoning system needs it.

The single most important design constraint is this:

> **Mnemo answers the question: "What do my documents say about X?"  
> It never answers: "What should I do about X?"**

### 1.2 Two Equally Important Use Cases

#### Use Case 1: Standalone NotebookLM Alternative

A user clones the repository, runs `docker compose up`, and opens a browser. From that moment:

- They upload documents.
- They create notebooks.
- They chat with their documents.
- The system cites sources, generates notes, produces podcasts, builds timelines.
- Everything runs locally. Nothing is sent to the cloud.

The user does not know or care about ARVSAL. They do not know what MCP is. They simply have a powerful, private, local alternative to Google NotebookLM.

#### Use Case 2: Reusable Knowledge Backend

A developer integrates Mnemo into their application. They call:

```
REST POST /v1/query
{
  "notebook_id": "my-research",
  "question": "What are the key arguments against X?",
  "context_budget": 8000
}
→ { "answer": "...", "citations": [...], "confidence": 0.87 }
```

Or they configure Claude Desktop with Mnemo as an MCP server, and Claude gains access to all of the user's knowledge bases as grounded retrieval tools.

Or ARVSAL routes a knowledge query to Mnemo via MCP without Mnemo knowing or caring that ARVSAL exists.

Both use cases are fully supported. Neither is secondary.

### 1.3 The Knowledge Engine Boundary

The following is the formal boundary of what Mnemo does and does not do. This boundary is architectural, not aspirational. Violating it would destroy the project's identity.

**Inside the boundary (Mnemo's responsibility):**

| Responsibility | Rationale |
|---|---|
| Document ingestion | Core function |
| Parsing (all formats) | Core function |
| OCR and layout analysis | Required for parsing |
| Metadata extraction | Required for retrieval |
| Adaptive chunking | Core function |
| Embedding generation | Core function |
| Vector indexing | Core function |
| Keyword indexing | Core function |
| Retrieval (dense, sparse, graph) | Core function |
| Reranking | Core function |
| Cross-document reasoning | Knowledge synthesis |
| Citation tracking | Epistemic integrity |
| Notebook management | Organizational layer |
| Podcast generation | Knowledge export |
| Timeline generation | Knowledge organization |
| Notebook summaries | Knowledge synthesis |
| Evidence collection | Core function |
| Context building | Core function |
| Confidence estimation | Core function |

**Outside the boundary (host application's responsibility):**

| Responsibility | Why it belongs elsewhere |
|---|---|
| Web browsing | Requires internet access, not a knowledge function |
| Email sending/reading | Requires external I/O, not a knowledge function |
| Filesystem management | Requires OS access, not a knowledge function |
| Code execution | Requires a sandbox, not a knowledge function |
| Calendar operations | Requires external service access |
| Task planning | Requires reasoning over goals, not evidence |
| Tool orchestration | Requires agent-level decision making |
| Multi-step autonomous action | Requires agency, which Mnemo explicitly does not have |

This boundary is enforced at the API level. Mnemo's REST API and MCP tool definitions never expose an action that crosses it.

### 1.4 Design Principles

1. **Privacy is axiomatic.** No telemetry, no external calls, no "calling home."
2. **Every interface is replaceable.** Parser, chunker, embedder, storage, LLM — all behind typed contracts.
3. **Ingest fast, enrich lazily.** The pipeline is split: documents become searchable in seconds, enrichment happens in the background.
4. **Cite everything.** Every retrieved statement is traceable to a source, page, and chunk.
5. **Core has no HTTP.** The core library is pure Python. It can be embedded in any application directly.
6. **Plugins are opt-in.** A minimal installation is functional without any plugin. Complex capabilities are additive.
7. **Fail gracefully, degrade predictably.** If a plugin fails, its capability is absent — not the system.

---

## 2. High-Level Architecture Diagram

```
═══════════════════════════════════════════════════════════════════════
                     EXTERNAL CONSUMERS
═══════════════════════════════════════════════════════════════════════

  Browser User          MCP Client              REST Client
  (standalone UI)   (Claude Desktop,        (ARVSAL, LibreChat,
                   VS Code, ARVSAL)         Open WebUI, custom)
       │                   │                       │
       │ HTTP/WS           │ MCP Protocol          │ HTTP REST
       │                   │                       │
       └───────────────────┴───────────────────────┘
                           │
═══════════════════════════╪═══════════════════════════════════════════
                    LAYER 2: mnemo-server
═══════════════════════════╪═══════════════════════════════════════════
                           │
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼──────┐
   │  REST API   │  │ MCP Server  │  │  WebSocket │
   │ (FastAPI)   │  │ (stdio/sse) │  │ (streaming)│
   └──────┬──────┘  └──────┬──────┘  └─────┬──────┘
          │                │                │
          └────────────────┼────────────────┘
                           │ Python function calls
═══════════════════════════╪═══════════════════════════════════════════
                    LAYER 1: mnemo-core
═══════════════════════════╪═══════════════════════════════════════════
                           │
    ┌──────────────────────┼──────────────────────────┐
    │                      │                           │
    ▼                      ▼                           ▼
┌──────────┐       ┌───────────────┐         ┌─────────────────┐
│INGESTION │       │   RETRIEVAL   │         │   NOTEBOOK      │
│PIPELINE  │       │   PIPELINE    │         │   MANAGER       │
│          │       │               │         │                 │
│ Parser   │       │ QueryPlanner  │         │ Notebook CRUD   │
│ Cleaner  │       │ Retriever[]   │         │ Source Manager  │
│ Chunker  │       │ Reranker      │         │ Note Manager    │
│ Embedder │       │ ContextBuilder│         │ Session Manager │
│ Indexer  │       │ CitationEngine│         │ Insight Manager │
└──────┬───┘       └───────┬───────┘         └────────┬────────┘
       │                   │                           │
       └───────────────────┼───────────────────────────┘
                           │
═══════════════════════════╪═══════════════════════════════════════════
                    STORAGE LAYER
═══════════════════════════╪═══════════════════════════════════════════
                           │
    ┌──────────────────────┼──────────────────────────┐
    │                      │                           │
    ▼                      ▼                           ▼
┌──────────┐       ┌────────────┐            ┌──────────────────┐
│  Qdrant  │       │ SQLite FTS5│            │   SurrealDB      │
│ (Vectors)│       │ (Keywords) │            │ (Meta/Graph/     │
│          │       │            │            │  Relations/      │
│          │       │            │            │  Sessions)       │
└──────────┘       └────────────┘            └──────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Filesystem │
                    │ (Blobs/IR)  │
                    └─────────────┘
═══════════════════════════════════════════════════════════════════════
                    LAYER 4: plugins/    (optional, loaded at runtime)
═══════════════════════════════════════════════════════════════════════

   [deepdoc-parser]  [mineru-parser]  [graph-retrieval]  [raptor]
   [ocr-paddle]      [podcast-gen]    [timeline-gen]     [watchfolder]
   [git-ingestion]   [email-ingestion][browser-history]  [epub-parser]
```

---

## 3. The Four-Layer Model

The entire project is organized into four layers. The rule is absolute: **each layer may only call the layer directly beneath it**. No layer may call upward. No layer may skip a layer.

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: mnemo-ui          (browser, calls Layer 2 only)    │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: mnemo-server      (HTTP/MCP, calls Layer 1 only)   │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: mnemo-core        (pure Python library, no HTTP)   │
├──────────────────────────────────────────────────────────────┤
│  Layer 4: plugins/          (registered into Layer 1)        │
└──────────────────────────────────────────────────────────────┘
```

Layer 4 (plugins) is not "above" or "below" — it is injected *into* Layer 1 at startup time via the plugin registry. A plugin implements a Layer 1 interface and is registered as the provider for a given capability.

### Target Repository Structure

The tree below is the end-state layout. Directories assigned to later roadmap
phases are intentionally absent from the Phase 1 baseline.

```
mnemo/
├── mnemo-core/              # Layer 1 — pure Python library
│   ├── mnemo/
│   │   ├── ingestion/
│   │   │   ├── parser.py
│   │   │   ├── cleaner.py
│   │   │   ├── chunker.py
│   │   │   ├── embedder.py
│   │   │   └── indexer.py
│   │   ├── retrieval/
│   │   │   ├── planner.py
│   │   │   ├── retriever.py
│   │   │   ├── reranker.py
│   │   │   ├── context_builder.py
│   │   │   └── citation_engine.py
│   │   ├── notebook/
│   │   │   ├── notebook_manager.py
│   │   │   ├── source_manager.py
│   │   │   ├── session_manager.py
│   │   │   └── insight_manager.py
│   │   ├── storage/
│   │   │   ├── storage_interface.py
│   │   │   ├── qdrant_store.py
│   │   │   ├── sqlite_store.py
│   │   │   └── surrealdb_store.py
│   │   ├── interfaces/          # All typed contracts
│   │   │   ├── parser_interface.py
│   │   │   ├── chunker_interface.py
│   │   │   ├── embedding.py
│   │   │   ├── retriever_interface.py
│   │   │   ├── reranker_interface.py
│   │   │   ├── llm_interface.py
│   │   │   └── storage_interface.py
│   │   └── registry.py          # Plugin registry
│   └── pyproject.toml
│
├── mnemo-server/            # Layer 2 — API adapter
│   ├── mnemo_server/
│   │   ├── api/
│   │   │   ├── notebooks.py
│   │   │   ├── sources.py
│   │   │   ├── query.py
│   │   │   ├── ingest.py
│   │   │   └── insights.py
│   │   ├── mcp/
│   │   │   ├── server.py
│   │   │   └── tools.py
│   │   ├── ws/
│   │   │   └── streaming.py
│   │   └── auth/
│   │       └── middleware.py
│   └── pyproject.toml
│
├── mnemo-ui/                # Layer 3 — React frontend
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── api/             # All API calls (never talks to core directly)
│   └── package.json
│
├── plugins/                 # Layer 4 — optional extensions
│   ├── deepdoc-parser/
│   ├── mineru-parser/
│   ├── graph-retrieval/
│   ├── raptor/
│   ├── podcast-gen/
│   ├── timeline-gen/
│   ├── watchfolder/
│   ├── git-ingestion/
│   └── email-ingestion/
│
├── docker/
│   ├── docker-compose.yml           # Full stack
│   ├── docker-compose.minimal.yml   # Core + SQLite only
│   └── docker-compose.dev.yml       # Dev with hot reload
│
└── docs/
    ├── quickstart.md
    ├── api-reference.md
    ├── mcp-integration.md
    └── plugin-development.md
```

---

## 4. Layer 1 — mnemo-core

### Purpose and Constraints

`mnemo-core` is a **pure Python library**. It has:

- No HTTP server.
- No authentication.
- No WebSocket.
- No MCP protocol.
- No UI.

It can be installed via `pip install mnemo-core` and used programmatically in any Python application. This makes it the correct primitive for embedding in ARVSAL, for testing, and for any application that wants to bypass the HTTP layer.

### Core Module Responsibilities

#### 4.1 Ingestion Pipeline

**Parser**  
Routes files to format-appropriate parsing implementations. Returns a `ParseResult` (a transient transport object) containing extracted transient blocks and unpersisted binary assets. All implementations are behind `ParserInterface`. The implemented built-in parsers handle digital PDF, DOCX, HTML, Markdown, plain text, JSON, and CSV/TSV. Additional formats, including scanned PDFs and EPUB, remain plugin or later-roadmap work.

**IngestionPipeline**

Owns the implemented Phase 3.9 sequence: router deduplication, cleaning,
classification, transient-asset persistence through `StorageInterfaceV1`,
immutable asset correlation, canonicalization, and publication of the resulting
`ParsedDocument`. On a deduplication hit it loads the existing current-version
canonical document instead of reparsing. It never generates permanent asset
identities and never deletes content-addressed assets as compensation.

**DocumentCanonicalizer**

Purely and synchronously converts a classified `ParseResult` with an
already-resolved immutable asset map into the canonical `ParsedDocument`. It
preserves ordering, ordinals, source geometry, language, metadata, and
classification; resolves raw image references; and performs no storage,
network, LLM, UUID, routing, cleaning, or classification work. ADR-0014 defines
the implemented ownership split.

**Cleaner**  
Normalizes a `ParseResult` before classification and canonicalization. Removes duplicate whitespace and running headers/footers (detected via frequency analysis across pages), fixes hyphenated line breaks, normalizes Unicode to NFC, and detects and tags block language.

**Chunker**  
Phase 4 consumes the canonical `ParsedDocument` from Module 3.9 together with a
`ChunkingContext` that binds a `DocumentVersion` and `ChunkingOptions`. A
version-isolated `ChunkerInterfaceV2` strategy selected by `doc_type` emits
ordered immutable `ChunkDraft` values. The dispatcher validates provenance,
size, and hierarchy, then deterministically materializes final `Chunk` IDs and
relationships. Strategies own semantic splitting; the dispatcher performs no
storage, network, embedding, indexing, retrieval, or semantic text generation.
This accepted contract is defined by ADR-0015. Module 4.1 implements only the
contract infrastructure and dispatcher; semantic strategies remain later work.

**Embedder**  
Transforms text into float vectors. Manages a content-addressable embedding cache. Sends batches to the configured `EmbeddingProvider`. `EmbedderInterface` is the later orchestration boundary for batching, caching, and provider selection. It handles dimension mismatch detection when the model is changed.

**Indexer**  
Writes chunks to configured storage backends as one logical operation. Returned
failures restore exact affected-key snapshots, preserving replacements and
removing only newly introduced identities. Because Qdrant has no distributed
transaction with SQLite, catastrophic interruption during compensation may
require reconciliation. The indexer maintains document ingestion status and
version history. Under ADR-0015, SQLite columns, Qdrant payloads, and
CompositeStorage snapshots must preserve required `Chunk.source_span` exactly.
Legacy chunks are re-created from canonical documents rather than assigned
fabricated provenance. Atomic replacement of an entire prior chunk set during
incremental re-chunking requires a separate later storage/indexing contract;
ADR-0015 does not change ADR-0002 affected-ID upsert semantics.

#### 4.2 Retrieval Pipeline

**QueryPlanner**  
Receives a natural language question and produces a `RetrievalPlan`. This is a lightweight planning step using the configured Planner LLM. It identifies the retrieval intent (factual, comparative, exploratory) and decomposes the query into one or more `SubQuery` objects.

**Important:** The `QueryPlanner` plans *retrieval strategy* only. It does not plan user actions, does not invoke external tools, and does not produce action sequences. It answers: "how should I search my documents to answer this question?" — nothing more.

**Retriever**  
Executes individual `SubQuery` objects. Multiple retrievers run in parallel:
- `DenseRetriever`: ANN search via Qdrant.
- `SparseRetriever`: BM25 via SQLite FTS5.
- `ParentRetriever`: Fetches parent chunks for context promotion.
- `GraphRetriever`: Traverses entity graph in SurrealDB (requires Graph plugin).
- `SummaryRetriever`: Returns pre-computed section summaries.

**Reranker**  
Cross-encoder scoring of (query, chunk) pairs. Deduplicates by chunk ID. Falls back to Reciprocal Rank Fusion if no cross-encoder model is configured.

**ContextBuilder**  
Assembles the final context from ranked chunks, respecting the token budget provided by the caller. Applies context compression (summarizes low-priority chunks) when the budget is tight. Formats the context with explicit source attribution markers.

**CitationEngine**  
Parses `[source:N]` markers from synthesized text. Resolves each marker to a `Citation` record: `(chunk_id, document_title, page_number, heading_path, verbatim_quote)`. Persists all citations in SurrealDB. Enables provenance queries.

#### 4.3 Notebook Manager

Manages the organizational layer: notebooks, sources, notes, sessions, insights.

A notebook is a named collection of sources. A source is an ingested document. Notes are first-class objects (user-created or AI-generated). Sessions are conversation threads attached to a notebook. Insights are extracted claims (entities, summaries, key facts) derived from sources.

The Notebook Manager does not make LLM calls. It is a data management module. Features that require LLM calls (summary generation, insight extraction) are coordinated by later core services. The server remains a transport adapter that calls those core functions.

#### 4.4 Plugin Registry

The registry is the dependency injection container for mnemo-core. During
`KnowledgeEngine.initialize()`, the engine:

1. loads built-in plugin candidates;
2. discovers the `mnemo.plugins` Python entry-point group;
3. scans the immediate Python children of `config.plugins.directory`; and
4. calls each candidate's `register(registry)` entry point before freezing the
   registry.

The registry enforces that each slot has at most one active implementation. If two plugins try to register for the same slot with conflicting priorities, the one with higher priority wins and a warning is logged.

```
Registry slots:
  parsers:      { "pdf": PDFParser, "docx": DocxParser, ... }
  chunkers:     { "book": BookChunker, "paper": PaperChunker, ... }
  embedding_providers: { "primary": OllamaEmbeddingProvider }
  retrievers:   { "dense": QdrantRetriever, "sparse": SQLiteRetriever, ... }
  reranker:     { "primary": CrossEncoderReranker }
  llm:          { "planner": OllamaLLM, "synthesizer": OllamaLLM, ... }
  storage:      { "primary": CompositeStorage }
```

---

## 5. Layer 2 — mnemo-server

### Purpose and Constraints

`mnemo-server` is a **thin adapter**. It has no business logic. Every endpoint is a translation from HTTP/MCP to a `mnemo-core` function call. This is not an opinion — it is a constraint. Any business logic discovered in `mnemo-server` is a bug that must be moved to `mnemo-core`.

The server is built on **FastAPI** (Python). It uses **Uvicorn** as the ASGI server. It handles authentication, rate limiting, websocket connections, and streaming.

### 5.1 REST API Surface

The API is versioned at `/v1`. All requests and responses are JSON unless otherwise specified.

---

#### Notebooks

```
GET    /v1/notebooks                    → list all notebooks
POST   /v1/notebooks                    → create notebook
GET    /v1/notebooks/{id}               → get notebook
PATCH  /v1/notebooks/{id}               → update notebook metadata
DELETE /v1/notebooks/{id}               → delete notebook + all sources
GET    /v1/notebooks/{id}/summary       → get or generate notebook summary
GET    /v1/notebooks/{id}/timeline      → get timeline events
GET    /v1/notebooks/{id}/graph         → get entity graph (nodes + edges)
```

---

#### Sources

```
GET    /v1/notebooks/{id}/sources            → list sources
POST   /v1/notebooks/{id}/sources            → ingest new source (multipart)
GET    /v1/notebooks/{id}/sources/{sid}      → get source metadata
DELETE /v1/notebooks/{id}/sources/{sid}      → delete source + its chunks
GET    /v1/notebooks/{id}/sources/{sid}/status → ingestion status (polling)
```

---

#### Query and Retrieval

```
POST   /v1/query                        → retrieve evidence for a question
POST   /v1/query/stream                 → streaming retrieve + synthesize
POST   /v1/search                       → global full-text + vector search
```

**POST /v1/query** — the primary endpoint.

Request:
```json
{
  "notebook_id": "uuid | null (null = search all notebooks)",
  "question": "What are the key arguments against quantitative easing?",
  "context_budget": 8000,
  "retrieval_config": {
    "modes": ["dense", "sparse"],
    "top_k": 20,
    "filters": {
      "doc_type": ["paper", "book"],
      "date_after": "2020-01-01"
    },
    "enable_reranking": true,
    "enable_parent_retrieval": true
  },
  "synthesis": {
    "enabled": true,
    "llm_role": "synthesizer",
    "max_response_tokens": 1000
  }
}
```

Response:
```json
{
  "answer": "The main arguments against quantitative easing are...",
  "citations": [
    {
      "id": "cit-uuid",
      "chunk_id": "chunk-uuid",
      "document_title": "Keynes Reconsidered",
      "page": 47,
      "heading_path": ["Part II", "Chapter 5", "Monetary Policy"],
      "quote": "The inflationary pressure of asset purchasing...",
      "confidence": 0.91
    }
  ],
  "retrieval_metadata": {
    "chunks_retrieved": 24,
    "chunks_used": 8,
    "retrieval_modes_used": ["dense", "sparse"],
    "latency_ms": 340
  }
}
```

Note that `synthesis.enabled` is optional. A caller can retrieve evidence only (`synthesis.enabled: false`) and perform the synthesis themselves — this is the expected usage for ARVSAL and other agentic systems.

---

#### Sessions and Memory

```
GET    /v1/notebooks/{id}/sessions           → list sessions
POST   /v1/notebooks/{id}/sessions           → create session
GET    /v1/notebooks/{id}/sessions/{sid}     → get session history
POST   /v1/notebooks/{id}/sessions/{sid}/turns → append a turn
DELETE /v1/notebooks/{id}/sessions/{sid}     → delete session
```

---

#### Notes and Insights

```
GET    /v1/notebooks/{id}/notes              → list notes
POST   /v1/notebooks/{id}/notes              → create note
PATCH  /v1/notebooks/{id}/notes/{nid}        → update note
DELETE /v1/notebooks/{id}/notes/{nid}        → delete note
GET    /v1/notebooks/{id}/insights           → list extracted insights
POST   /v1/notebooks/{id}/insights/generate  → trigger insight generation
```

---

#### Plugins and Features (optional, loaded by plugins)

```
POST   /v1/notebooks/{id}/podcast            → generate podcast (plugin)
GET    /v1/notebooks/{id}/podcast            → get podcast status/file (plugin)
```

---

#### System

```
GET    /v1/health                       → liveness check
GET    /v1/config                       → get current plugin/model config
GET    /v1/config/models                → list available LLM/embedding models
PATCH  /v1/config                       → update config (hot reload)
GET    /v1/jobs                         → list background jobs
GET    /v1/jobs/{id}                    → get job status
```

---

### 5.2 MCP Server

Mnemo exposes an **MCP (Model Context Protocol) server** that can run in two modes:

- **stdio mode**: For local MCP clients (Claude Desktop, VS Code extensions, ARVSAL local). Mnemo starts as a subprocess that communicates over stdin/stdout.
- **SSE mode**: For remote MCP clients or applications that need HTTP-based MCP.

The MCP server exposes **knowledge-retrieval tools only**. It does not expose ingestion triggers (those require authentication and are management operations). It does not expose notebook creation or deletion.

#### MCP Tool Definitions

```
Tool: query_notebook
Description: Retrieve evidence from a specific notebook in response to a question.
             Returns grounded evidence with source citations. Does not browse the
             web, execute code, or perform any external actions.
Parameters:
  notebook_id: string   (UUID of the notebook to query)
  question:    string   (the question to answer)
  top_k:       integer  (max evidence chunks, default 10)
  synthesize:  boolean  (whether to synthesize an answer, default true)
Returns:
  answer:      string   (synthesized answer, if synthesis requested)
  citations:   Citation[]

Tool: search_all_notebooks
Description: Full-text and semantic search across all notebooks.
Parameters:
  query:    string   (search query)
  top_k:    integer  (max results, default 10)
Returns:
  results:  SearchResult[]   (chunk, source, notebook, score)

Tool: list_notebooks
Description: List all available notebooks with their source counts.
Returns:
  notebooks: Notebook[]

Tool: get_notebook_summary
Description: Get a pre-generated or freshly-generated summary of a notebook.
Parameters:
  notebook_id: string
Returns:
  summary:    string
  sources:    SourceSummary[]

Tool: get_source_insights
Description: Get extracted insights (key facts, entities) from a specific source.
Parameters:
  source_id:  string
Returns:
  insights:   Insight[]

Tool: get_timeline
Description: Get chronological events extracted from a notebook.
Parameters:
  notebook_id: string
Returns:
  events:     TimelineEvent[]
```

The set of exposed MCP tools is narrow and purposeful. The MCP server does not expose a tool called `run_command`, `browse_web`, `send_email`, or any action that crosses the knowledge engine boundary.

---

### 5.3 WebSocket (Streaming)

For the UI's chat experience, Mnemo-server exposes a WebSocket endpoint at `/ws/query`. It streams:

1. `{ event: "retrieval_start" }` — retrieval beginning.
2. `{ event: "chunk_retrieved", data: { chunk_id, score } }` — as each chunk is retrieved.
3. `{ event: "synthesis_token", data: { token } }` — streamed LLM tokens.
4. `{ event: "citations_ready", data: { citations[] } }` — final citation list.
5. `{ event: "done" }` — stream complete.

### 5.4 Authentication

Mnemo-server supports three authentication modes, configured at startup:

- **None** (default for local single-user): No authentication required.
- **API Key**: Static API key in the `Authorization: Bearer` header.
- **JWT**: For multi-user deployments.

Authentication is handled by a middleware layer and is completely transparent to `mnemo-core`, which never sees credentials.

---

## 6. Layer 3 — mnemo-ui

### Purpose and Constraints

`mnemo-ui` is a React frontend. It communicates with `mnemo-server` **only** via the REST API and WebSocket. It never imports or calls `mnemo-core` directly. It has no knowledge of how retrieval works.

This constraint is important: the UI must remain functional even if the entire backend is replaced with a different implementation that exposes the same API contract.

### Key Pages

```
/                          → Dashboard (recent notebooks, quick search)
/notebooks                 → All notebooks list
/notebooks/[id]            → Notebook view
  /notebooks/[id]/chat     → Chat with documents
  /notebooks/[id]/sources  → Source management, upload
  /notebooks/[id]/notes    → Notes view
  /notebooks/[id]/timeline → Timeline view
  /notebooks/[id]/graph    → Knowledge graph explorer
  /notebooks/[id]/podcast  → Podcast player + generation
/search                    → Global search across all notebooks
/settings                  → Model config, plugin config, storage config
```

### Design Constraints

- The UI handles no LLM logic. It is a view over data returned by the API.
- Streaming responses are consumed via WebSocket and rendered token-by-token.
- Citations are rendered as interactive footnotes that link to the source location.
- The UI must be functional without JavaScript-heavy dependencies — it must work in low-resource environments.

---

## 7. Layer 4 — plugins/

Plugins are the mechanism by which Mnemo's capabilities can be extended without modifying any of the three core layers.

### Plugin Contract

Every plugin is a Python package with the following structure:

```
plugins/deepdoc-parser/
├── pyproject.toml          # declares: mnemo.plugins entry point
├── deepdoc_parser/
│   ├── __init__.py
│   └── parser.py           # implements ParserInterface
└── README.md               # documents what it provides
```

The `pyproject.toml` entry point:
```toml
[project.entry-points."mnemo.plugins"]
deepdoc_parser = "deepdoc_parser:register"
```

The `register` function:
```python
def register(registry: PluginRegistry) -> None:
    registry.register_parser("pdf", DeepDocPDFParser, priority=10)
    registry.register_parser("docx", DeepDocDocxParser, priority=10)
```

Installing a plugin is `pip install mnemo-plugin-deepdoc-parser`. Uninstalling removes it from the registry automatically on next restart. No configuration files need to be edited.

### Built-In vs Plugin Capabilities

| Capability | Built-in | Plugin |
|---|---|---|
| Digital PDF parsing | ✓ (basic) | deepdoc-parser (advanced) |
| Scanned PDF / OCR | | ocr-paddle |
| DOCX/PPTX parsing | ✓ | deepdoc-parser (advanced) |
| HTML parsing | ✓ | |
| Markdown parsing | ✓ | |
| Code (AST-based) chunking | ✓ (built-in) | |
| Book hierarchical chunking | ✓ (built-in) | |
| Paper section chunking | ✓ (built-in) | |
| Email parsing | | email-ingestion |
| Git repository ingestion | | git-ingestion |
| EPUB parsing | | epub-parser |
| Cross-encoder reranking | ✓ (built-in) | |
| Graph retrieval | | graph-retrieval |
| RAPTOR hierarchical | | raptor |
| Knowledge graph extraction | | graph-retrieval |
| Podcast generation | | podcast-gen |
| Timeline generation | | timeline-gen |
| Watch folders | | watchfolder |
| Browser history ingestion | | browser-history |

The completed minimal core currently handles digital PDFs, HTML, Markdown,
DOCX, plain text, JSON, and CSV/TSV through canonicalization. Dense/sparse
retrieval and cross-encoder reranking remain later roadmap phases.

---

## 8. Plugin Registry and Interface Contracts

Phase 1 freezes seven structural, versioned provider contracts. Their exact V1
signatures, records, lifecycle rules, and exceptions are defined by
[ADR-0002](adr/ADR-0002-core-interface-contracts.md) and exported by
`mnemo.interfaces`. Unversioned names are current-version aliases for the V1
contracts.

### 8.1 ParserInterface

`ParserInterfaceV1` synchronously converts immutable bytes and `FileMetadata`
into a `ParseResult`. It exposes immutable `ParserCapabilities` and performs
no network or persistent-storage I/O.

### 8.2 ChunkerInterface

`ChunkerInterfaceV1` is the released contract from ADR-0002 and remains
unchanged. ADR-0015 defines `ChunkerInterfaceV2` as the Phase 4 contract. V2
synchronously accepts `ParsedDocument`, `ChunkingContext`, and one canonical
local `TokenCounterInterfaceV1`, then returns an ordered tuple of immutable,
non-persisted `ChunkDraft` values. `ChunkingContext` contains the authoritative
`DocumentVersion` and `ChunkingOptions`; it does not add identity to
`ParsedDocument`. The existing `register_chunker()`/`resolve_chunker()` methods
and `ChunkerInterface` alias remain V1 during the compatibility window. V2 uses
explicit `register_chunker_v2()`/`resolve_chunker_v2()` methods, and registry
identity, priority, conflicts, active selection, and deterministic listing are
isolated by interface version.

Each draft carries an inclusive, contiguous canonical `BlockSpan` and an
explicit earlier-draft `parent_index` or is a root. The dispatcher finalizes
the canonical `Chunk` values. Chunk identity uses `version_id`, the persisted
source span, and text; `heading_path`, text offsets, tokenizer identity,
metadata, and relationships remain outside identity. The canonical tokenizer
is the explicitly provisioned, hash-verified, offline-only
`tiktoken==0.13.0`/`o200k_base` adapter defined by ADR-0015.

The released `ChunkingOptions` model retains its V1 validation. The accepted
`ChunkingContext` owns the additional V2 minimum of 15 target tokens and
defensively validates all option relationships. The dispatcher computes the
effective maximum as `min(max_tokens, 2 * target_tokens)` and applies it to
draft text; it does not change V1 construction semantics.

### 8.3 EmbeddingProvider

`EmbeddingProviderV1` is the model-provider abstraction for single and batch
vector generation. It exposes model name, dimensions, token limit,
`EmbeddingCapabilities`, and a transport-independent health observation.
`EmbedderInterface` is a separate orchestration contract assigned to a later
roadmap module.

### 8.4 RetrieverInterface

`RetrieverInterfaceV1` performs one bounded retrieval strategy and returns an
ordered tuple of raw-scored `ScoredChunk` values. It exposes a stable retrieval
mode and immutable `RetrieverCapabilities`.

### 8.5 RerankerInterface

`RerankerInterfaceV1` reorders a bounded tuple of candidates while preserving
chunk provenance and exposes immutable `RerankerCapabilities`.

### 8.6 LLMInterface

`LLMInterfaceV1` exposes provider, model, context limit, immutable
`LLMCapabilities`, typed completion and streaming operations, and a local
health observation. Its purpose is knowledge retrieval and synthesis only; it
does not expose tools or autonomous actions.

### 8.7 StorageInterface

`StorageInterfaceV1` is the single atomic façade over blob, vector, keyword,
metadata, notebook, conversation, and graph persistence. It exposes no backend
repositories or vendor types. Phase 2 supplies its concrete `primary`
implementation; Phase 1 defines the contract only.

---

## 9. Document Ingestion Pipeline

The ingestion pipeline is split into a **Fast Path** (blocking, completes before the API returns a job ID with status "indexed") and a **Slow Path** (async background, non-blocking).

```
INPUT: file bytes (from API upload, watch folder, or programmatic call)
           │
           ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           FAST PATH  (target: <30s per 100-page PDF)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           │
    ┌──────▼──────┐
    │  STAGE 0    │  Deduplication: SHA-256 → content-addressable store.
    │  Dedup Gate │  If known, load current ParsedDocument and return it.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 1    │  Format detection: MIME type + extension.
    │  Detection  │  Route to appropriate ParserInterface implementation.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 2    │  Parsing: convert bytes → ParseResult{blocks[], metadata, extracted_assets[]}.
    │  Parsing    │  For digital PDF: text extraction + layout analysis.
    │             │  For scanned: OCR plugin (if installed) → layout.
    │             │  For DOCX: heading hierarchy preserved.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 3    │  Cleaning: remove headers/footers, fix hyphenation,
    │  Cleaning   │  normalize unicode, tag languages per block.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 4    │  Classification: assign doc_type (book, paper, code, etc.)
    │  Classify   │  Rule-based ONLY (fast). Returns Classified ParseResult.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 4B   │  Future Orchestration: LLM-assisted classification
    │  (Deferred) │  for ambiguous cases (Fallback).
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 5    │  Preserve parser-produced DocumentMetadata.
    │  Metadata   │  Optional enrichment remains future roadmap work.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 6    │  IngestionPipeline persists TransientAssets through storage.
    │  Blob Store │  StorageInterfaceV1 returns permanent Asset identities.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 7    │  Pure DocumentCanonicalizer converts resolved ParseResult
    │  Canonical  │  to ParsedDocument without generating identity or doing I/O.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 8    │  ParsedDocument + ChunkingContext -> ChunkerInterfaceV2.
    │  Chunking   │  Drafts -> validated IDs/relationships -> immutable Chunk[].
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 9    │  Embedding: check cache per chunk (sha256 → vector).
    │  Embedding  │  Batch new chunks. Store embeddings with chunks.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 10   │  Indexing: write to Qdrant + SQLite FTS5 + SurrealDB.
    │  Indexing   │  Atomic: if any write fails, roll back all writes.
    └──────┬──────┘
           │
           ▼
   Status: INDEXED  ←── user can query document from this point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           SLOW PATH  (background worker, interruptible)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           │
    ┌──────▼──────┐
    │  STAGE 9A   │  Entity extraction: spaCy NER → entities in SurrealDB graph.
    │  NER        │  Runs at background priority. One batch per 5 minutes.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 9B   │  Question generation: small LLM generates 3–5 questions
    │  Questions  │  per section. Stored as QUESTION-type chunks, embedded,
    │             │  indexed. Dramatically improves retrieval on "what does
    │             │  this document say about X" queries.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 9C   │  Summary generation: per-section summaries (small LLM).
    │  Summaries  │  Stored as SUMMARY-type chunks, embedded, indexed.
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  STAGE 9D   │  Graph edge extraction: lazy, rate-limited LLM calls
    │  Graph      │  to extract entity relationships from high-priority chunks
    │             │  (those with high retrieval frequency are prioritized).
    └──────┬──────┘
           │
           ▼
   Status: ENRICHED  ←── full retrieval quality achieved
```

---

## 10. Adaptive Chunking Engine

The Adaptive Chunker is the most consequential module in the entire system. Retrieval quality cannot exceed chunking quality. A perfect embedding model cannot retrieve a meaningful answer from a semantically broken chunk.

The fundamental principle: **chunking is semantic compression, not text splitting**.

The canonical boundary is:

```text
Parser -> ParseResult -> DocumentCleaner -> DocumentClassifier
       -> IngestionPipeline (asset persistence and resolution)
       -> DocumentCanonicalizer -> ParsedDocument
       -> ChunkingContext + ChunkerInterfaceV2 + TokenCounterInterfaceV1
       -> ordered ChunkDraft values -> dispatcher finalization
       -> immutable Chunk values -> later embedding and indexing
```

`ParsedDocument` remains content-only. `DocumentVersion` in `ChunkingContext`
provides the authoritative document/version binding, and the dispatcher rejects
a mismatch between their content hashes.

### 10.1 Book

Books have narrative hierarchy: Part → Chapter → Section → Subsection → Paragraph.

**Strategy: Three-Level Hierarchical Chunking**

1. Parse the Table of Contents to establish the hierarchy. If no ToC exists, infer it from heading patterns.
2. For each section, produce deterministic local chunk types:
   - `SUMMARY`: only when a source-authored summary is present. Used for high-level routing.
   - `PASSAGE`: 200–500 tokens, bounded by paragraph breaks (never character count). This is the primary retrieval unit.
   - `VERBATIM`: For key definitions, quotes, claims. 30–150 tokens.
3. Each chunk carries `heading_path`: `["Thinking Fast and Slow", "Part II", "Chapter 11", "The Illusion of Understanding"]`.
4. Chapters are never crossed. A 400-token window that spans a chapter boundary is two separate passages.
5. Skip the ToC itself (generates pure duplicate noise).

### 10.2 Research Paper

Papers have canonical structure: Abstract, Introduction, Background, Methods, Results, Discussion, Conclusion, References.

**Strategy: Canonical Section Chunking**

1. Detect section headings via layout analysis (font size, bold, numbering patterns: "3.1 Methodology").
2. Assign each detected section to a canonical `section_type` enum.
3. Never chunk across section boundaries.
4. Abstract → always one atomic chunk. It is the highest-priority retrieval anchor and should be complete and unmodified.
5. References → parsed for structured citation metadata but excluded from embedding.
6. Figures and tables: source captions become `CAPTION` chunks. Figure content
   remains represented by the frozen canonical models; later enrichment may
   add a description using namespaced metadata and an existing `ChunkType`.
7. Equations: source LaTeX is preserved with `ChunkType.EQUATION`. Any generated
   plain-language description belongs to later enrichment.

### 10.3 Resume

**Strategy: Semantic Section Isolation**

1. Identify canonical sections: Contact, Summary, Experience, Education, Skills, Projects, Publications.
2. Each section becomes one chunk.
3. Within Experience: each role is a distinct chunk with preserved structure (company, title, dates, description).
4. Never overlap sections. A query for "Python experience" must not retrieve an education section.
5. Preserve a source-authored profile summary when present. Generated holistic
   summaries belong to later enrichment and are not created by Phase 4.

### 10.4 Code

**Strategy: AST-Structural Chunking (tree-sitter)**

1. Parse each file's AST using tree-sitter (supports 100+ languages).
2. Extract top-level declarations: classes, functions, methods, constants, module-level docstrings.
3. Each declaration is a chunk. Functions are atomic — never split mid-function.
4. Each chunk carries: function signature, docstring, body, and a `call_context` metadata field listing what it calls and what calls it (extracted from AST).
5. Module-level docstrings → `SUMMARY` chunk for the file.
6. Repository-level `README.md` → parsed as Markdown, used as the `SUMMARY` chunk for the entire codebase.
7. Imports are extracted as structured metadata (not embedded separately).

### 10.5 Markdown

**Strategy: Header-Hierarchy Chunking**

The Phase 3 Markdown parser interprets the Markdown AST while it still owns the
source. It records only the bounded immutable semantics required downstream in
`parser.markdown.*` block metadata: block kind, one exact source slice per
source-bearing block, resolved internal links, and structured list type and
nesting. The cleaner carries this metadata unchanged and the pure canonicalizer
copies it to the corresponding canonical block. AST/token objects and a full
AST never cross the parser boundary.

The implemented information flow is:

```text
Markdown bytes
  -> MarkdownParser AST interpretation
  -> RawBlock + immutable parser.markdown.* metadata
  -> DocumentCleaner (typed content normalization; metadata unchanged)
  -> DocumentCanonicalizer (metadata copied, not interpreted)
  -> ParsedDocument
  -> MarkdownChunker (Module 4.6)
```

1. Consume canonical blocks and the approved parser-produced Markdown metadata;
   do not reparse the original file.
2. Split boundaries: H1, H2, H3 headings.
3. The content between each H3 and the next H3 is a passage chunk.
4. Code blocks within Markdown: separate `CODE` chunk with language tag.
5. Tables: derive a text description from canonical `TableBlock.rows` and retain
   the exact Markdown table string from `parser.markdown.source`.
6. Internal links: retained as namespaced metadata for a later graph/indexing
   owner using the parser-resolved `parser.markdown.links` records; the chunker
   does not write SurrealDB.
7. Lists, blockquotes, thematic breaks, and inline source fidelity use their
   approved parser metadata. The chunker does not reconstruct lost syntax or
   consume parser implementation objects.

### 10.6 Email

**Strategy: Thread-Aware Chunking**

1. Parse the entire email thread as an ordered sequence of messages.
2. Each message is a distinct draft with namespaced metadata: `sender`,
   `recipient`, `date`, `subject`, and stable source-thread correlation.
3. Reply hierarchy is expressed by `parent_index`; final parent IDs are created
   by dispatcher finalization and may be indexed as a chain later.
4. Long message bodies: split only at legal message-internal semantic boundaries
   using the canonical token counter; never by blind character count.
5. Newsletters/announcements: treated as flat HTML and chunked via Markdown strategy post-extraction.
6. Attachment extraction and ingestion as separate documents belongs to the
   ingestion/indexing workflow. The Email strategy only preserves available
   attachment correlation metadata.

### 10.7 Slides / Presentations

**Strategy: Slide-Level Atomic Chunking**

1. One chunk per slide: title + body text + speaker notes (if present).
2. Images remain linked through canonical `Asset` references; generated vision
   descriptions belong to later enrichment.
3. If slides have a section structure (revealed by slide titles or section dividers), group slides by section. A section-level `SUMMARY` exists only when supported by source text.
4. The title slide → `SUMMARY` chunk for the deck.

### 10.8 Documentation

**Strategy: Task-and-Topic Chunking**

1. Respect the documentation navigation structure (sidebar, ToC) as the primary hierarchy.
2. Identify **task blocks** — numbered procedures, command sequences — and keep them atomic.
3. API reference sections: one chunk per function/endpoint, with preserved structure: name, signature, description, parameters, return value, examples.
4. Callouts (Note, Warning, Tip, Caution) are preserved with their type tag in chunk metadata.

### 10.9 The Universal Chunking Invariants

Regardless of strategy, all chunkers must satisfy:

1. **Canonical counting:** One deterministic, offline token counter instance is
   supplied to both strategy and dispatcher. No strategy selects its own
   tokenizer. The frozen engine is `tiktoken==0.13.0` with a hash-verified
   `o200k_base` asset and adapter V1. Mnemo never redistributes that asset.
   A user explicitly provisions it from the frozen upstream URL (or imports an
   independently obtained copy for an air-gapped deployment) into local,
   content-addressed storage. Provisioning is the only network-capable step;
   runtime loading and chunking are strictly offline and have no fallback.
2. **Minimum size:** A draft below 15 tokens is removed only when it is a leaf.
   A short parent with children is an invalid strategy result.
3. **Maximum size:** The effective hard maximum is
   `min(max_tokens, 2 * target_tokens)`. Strategies perform legal semantic
   splitting before return. The dispatcher rejects oversized output; it never
   blindly splits or truncates atomic content, and failure is all-or-nothing.
4. **Provenance:** Every draft and final chunk has a valid inclusive,
   contiguous canonical `BlockSpan`. Multiple chunks may share a span,
   including secondary splits within one block. Text boundaries are represented
   by chunk text; `ChunkPosition` offsets are navigation metadata.
5. **Heading path:** Hierarchical sources retain sufficient canonical heading
   context. A hierarchy-free source may use an empty path.
6. **Hierarchy:** Strategies declare a single-parent forest using
   `parent_index` references to earlier drafts. Multiple roots and multiple
   levels are allowed. Parentage is never inferred from `section_index` or
   `heading_path`. Siblings share one non-null parent, exclude self, are
   symmetric, and have deterministic order; roots are not siblings by default.
7. **Semantic atomicity:** A chunk never crosses a major semantic boundary.
8. **Identity stability:** The chunk ID is the SHA-256 of `version_id`, the
   canonical source block-ordinal span, and chunk text. `heading_path`, text
   offsets, tokenizer identity, metadata, and relationships do not participate.

The frozen `ChunkType` enum remains authoritative. Architecture labels such as
`IMAGE`, `EQUATION_DESCRIPTION`, and `PROFILE_SUMMARY` are not new enum values;
the corresponding source or later-enrichment role uses an existing
`ChunkType` plus namespaced metadata. Phase 4 performs no LLM or network calls
and creates no placeholder summaries or descriptions. Optional generated
content belongs to a future post-chunk enrichment pipeline that requires its
own ADR and roadmap assignment before implementation.

---

## 11. Retrieval Pipeline

```
USER QUESTION: "What did Graham say about market volatility?"
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: QUERY ANALYSIS                                          │
│  – Detect intent: factual | comparative | exploratory           │
│  – Extract entities: ["Benjamin Graham", "market volatility"]   │
│  – Detect temporal markers: none                                │
│  – Determine scope: single notebook specified? all?             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: QUERY EXPANSION (HyDE)                                  │
│  Generate a hypothetical answer paragraph using Planner LLM:    │
│  "Graham believed market volatility was not risk itself but     │
│   rather an opportunity for disciplined investors..."           │
│  Embed the hypothetical answer (not the original question).     │
│  This dramatically improves dense retrieval recall.             │
│  Also: extract synonyms/alternate phrasings for sparse search.  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: RETRIEVAL PLANNING                                      │
│  Planner LLM constructs a RetrievalPlan:                        │
│    SubQuery 1: dense, query=HyDE paragraph, k=15               │
│    SubQuery 2: sparse, query="Graham market volatility", k=10   │
│    SubQuery 3: sparse, query="Mr. Market Benjamin Graham", k=8  │
│    SubQuery 4: graph, entity="Benjamin Graham", hops=1          │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼ (all SubQueries in parallel)
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: PARALLEL RETRIEVAL                                      │
│                                                                 │
│  DenseRetriever      SparseRetriever      GraphRetriever        │
│  (Qdrant HNSW)       (SQLite FTS5)        (SurrealDB graph)     │
│       │                    │                    │               │
│       └────────────────────┴────────────────────┘               │
│                            │                                    │
│                    Merge + Deduplicate by chunk_id              │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: METADATA FILTERING                                      │
│  Apply hard filters from the request:                           │
│  – doc_type filter (e.g., papers only)                          │
│  – date_after / date_before                                     │
│  – source_id filter (specific documents only)                   │
│  – notebook_id filter                                           │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: PARENT RETRIEVAL (Hierarchical Upgrade)                 │
│  For each retrieved chunk: inspect its stored sibling family.   │
│  If ≥50% of chunks sharing its non-null parent are present,     │
│  replace them with that explicitly linked parent chunk.         │
│  This upgrades snippet-level hits to section-level context.     │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 7: RERANKING                                               │
│  CrossEncoderReranker scores each (question, chunk) pair.       │
│  Sorts by cross-encoder score (not embedding cosine).           │
│  Attaches confidence score to each chunk.                       │
│  Flags chunks with confidence < 0.4 (used for UI display).      │
│  Falls back to RRF score fusion if no reranker configured.      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 8: CONTEXT COMPRESSION                                     │
│  Calculate available token budget:                              │
│  budget = context_budget - system_prompt - question - history   │
│  Greedily select chunks by score until budget is consumed.      │
│  For remaining high-score chunks beyond budget:                 │
│  compress to ~100 tokens using Extractor LLM.                   │
│  Preserve verbatim the top-3 highest-scored chunks.             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 9: CONTEXT ASSEMBLY                                        │
│  Format with attribution markers:                               │
│                                                                 │
│  === Source [1]: "The Intelligent Investor" Ch.8 p.204 ===     │
│  Graham described Mr. Market as a business partner who...       │
│  === Source [2]: "Graham Interview, Forbes 1974" p.3 ===       │
│  When asked about volatility, Graham stated...                  │
│                                                                 │
│  This formatted string is returned to the caller.              │
│  If synthesis is requested, it goes to STEP 10.                 │
│  If synthesis is disabled, the context is returned as-is.       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 10: SYNTHESIS (optional)                                   │
│  Synthesizer LLM receives context + question.                   │
│  Instructed to cite sources as [1], [2] etc.                    │
│  CitationEngine parses markers → Citation records.              │
│  Citations persisted in SurrealDB.                              │
│  Response + citations returned to caller.                       │
└─────────────────────────────────────────────────────────────────┘
```

### Multi-Hop Retrieval

For complex analytical queries (`requires_multi_hop: true` in the plan):

1. **Hop 1:** Standard retrieval pass.
2. **Entity extraction:** Extract entities from top-5 retrieved chunks.
3. **Hop 2:** New SubQuery using extracted entities as search terms.
4. **Fusion:** Merge hop-1 and hop-2 results with RRF.
5. Maximum 3 hops. Hard limit — prevents infinite traversal.
6. Multi-hop is only triggered when the Planner identifies it as necessary.

### Cross-Document Retrieval

When `requires_multi_doc: true`:

1. Retrieval is not filtered by source. Results may come from any document.
2. The ContextBuilder segments the assembled context by source document.
3. The Synthesizer receives explicit instructions to compare/contrast/synthesize across sources.
4. Each source's contribution is tracked in the citation record.

---

## 12. Conversation Memory

Mnemo implements a **three-tier memory model**. Note that global long-term memory (Tier 4 from the ARVSAL design) is removed from this specification — it is the responsibility of the host application (e.g., ARVSAL), not the knowledge engine.

### Tier 1: Immediate Context
- Current prompt + the last N turns (configurable, default 10).
- Held in the LLM's context window.
- The server maintains session history and injects it into each completion call.

### Tier 2: Working Memory (Within-Session Retrieval)
- All turns from the current session are stored in SurrealDB.
- When processing a new turn, the QueryPlanner receives the last 3 turns as context.
- Relevant past turns are retrieved from the session via BM25 keyword search (SQLite FTS5 over session history).
- This enables follow-up questions ("what about the next chapter?") to be correctly resolved.

### Tier 3: Notebook Memory (Persistent Session Knowledge)
- All Session Notes (AI-generated summaries of past conversations) are stored as first-class documents in SurrealDB.
- Session Notes are embedded and indexed in Qdrant like any other document.
- They are retrievable via the standard retrieval pipeline.
- All citations from past sessions persist — every AI statement is permanently traceable to its source.
- This enables the system to reference past conversations ("As we discussed last month...") when asked.

### Memory API

The host application controls memory access via session parameters:

```json
POST /v1/query
{
  "session_id": "sess-uuid",       // enables working memory injection
  "include_session_notes": true,   // enables Tier 3 retrieval
  ...
}
```

A stateless caller (no `session_id`) receives pure retrieval results with no memory context. This is the correct mode for API integrations that manage their own memory.

---

## 13. Storage Architecture

### The Four-Store Design

Mnemo uses four complementary storage systems. This is not over-engineering — it is selecting the right tool for each query pattern. All four are accessed exclusively through `StorageInterface`.

#### Qdrant — Vector Store

The primary retrieval engine for semantic similarity search.

**Why Qdrant over embedded alternatives:**
- HNSW index delivers <15ms ANN search at 20M+ vectors with >99% recall.
- Named vectors: store multiple embeddings per chunk (body embedding + title embedding + question embedding) without duplicating chunk data.
- Payload filters: apply metadata filters at the HNSW index level, not post-retrieval. This is critical for notebook-scoped queries.
- Runs as a single binary with no dependencies. Zero-configuration local setup.
- Persists data as a directory — backup is `cp -r`.

**Can SurrealDB replace Qdrant?** Not at scale. SurrealDB supports vector search but not HNSW — it uses brute-force or flat index. At 1M+ chunks, query latency diverges by 10–100×.

---

#### SQLite FTS5 — Full-Text / Keyword Store

The gold standard for exact-phrase and BM25 retrieval.

**Why it cannot be removed:**
Vector search is fundamentally unable to reliably retrieve exact terms, identifiers, names, and codes. `ISBN 978-0-06-055566-5`, `CVSS-2025-3841`, `function authenticate()` — these must be found by exact text match, not semantic similarity.

SQLite FTS5 ships as part of SQLite (no extra dependency), supports BM25 ranking natively, handles billions of rows efficiently, and is the most stable local text search solution available.

**Deployment:** A single `.db` file. No server, no daemon.

---

#### SurrealDB — Relational + Graph + Metadata

The source of truth for all structured data.

Used for:
- Document registry (every ingested document, its metadata, ingestion status, version history).
- Notebook and source relationships.
- Chunk-to-document relationships (enables parent retrieval and provenance).
- Session history and turn storage.
- Citation records (permanent, every AI statement).
- Entity graph (nodes = entities, edges = relationships).
- User notes and insights.
- Job queue for background tasks.

**Why SurrealDB over PostgreSQL:** SurrealDB handles relational, document, and graph queries in one engine. For a personal-scale local deployment, the alternative (PostgreSQL + Neo4j) is operationally heavier.

**Why SurrealDB over SQLite alone:** SQLite does not have native graph traversal. The entity graph requires true graph query support (multi-hop entity relationship queries).

---

#### Filesystem — Content-Addressable Blob Store

Raw files, parsed IR JSON, extracted images, generated audio.

```
~/.mnemo/blobs/
    ab/cdef1234.../
        raw.pdf                ← original file
        parsed.ir.json         ← ParsedDocument as JSON
        chunks.json            ← chunk list (pre-embedding)
    cd/ef5678.../
        raw.png                ← extracted figure
```

All paths are content-addressed (`sha256(bytes)[:2]/sha256(bytes)`). Duplicate files share one blob. This directory is the authoritative source for re-ingestion if any index is corrupted.

---

### Storage Decision Summary

| Question | Answer |
|---|---|
| Should SurrealDB replace Qdrant? | No. HNSW performance is non-negotiable at scale. |
| Should SurrealDB replace SQLite? | No. FTS5 BM25 is a distinct query pattern. |
| Should PostgreSQL replace SurrealDB? | Only for multi-user enterprise deployments. |
| Should GraphRAG-style communities be built? | No. The cost (LLM calls per chunk at ingest) is prohibitive locally. Lazy graph construction instead. |

---

## 14. LLM Orchestration

### Specialist Role-Based Architecture

Mnemo uses four LLM roles. Each role has different model requirements. The configuration maps roles to models, and every role's model is independently configurable. Embedding and reranking are separate provider families rather than LLM roles.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LLM ROLE REGISTRY                                 │
├────────────────┬─────────────────────────────────────────────────────┤
│ ROLE           │ JOB                              │ MODEL PROFILE    │
├────────────────┼──────────────────────────────────┼──────────────────┤
│ planner        │ Decompose queries into sub-      │ Fast, small.     │
│                │ queries. Generate retrieval plan. │ 7B–14B param.   │
├────────────────┼──────────────────────────────────┼──────────────────┤
│ synthesizer    │ Write grounded answers from      │ High quality.    │
│                │ retrieved context.               │ 32B–70B param.  │
├────────────────┼──────────────────────────────────┼──────────────────┤
│ extractor      │ NER, entity relationship         │ Small, batch.   │
│                │ extraction. Question generation.  │ 3B–7B param.   │
├────────────────┼──────────────────────────────────┼──────────────────┤
│ classifier     │ Document-type classification.    │ Fast, small.     │
│                │                                  │ Structured.      │
├────────────────┼──────────────────────────────────┼──────────────────┤
│ embedding      │ Separate provider family:        │ nomic-embed or  │
│                │ Called at ingest and query time. │ mxbai-embed     │
├────────────────┼──────────────────────────────────┼──────────────────┤
│ reranker       │ Separate provider family:        │ ms-marco family │
│                │ Not generative.                  │ deterministic   │
└────────────────┴──────────────────────────────────┴──────────────────┘
```

**Configuration shape (TOML; provider and model values are required):**

```toml
[llm.planner]
provider = "ollama"
model = "planner-model"

[llm.synthesizer]
provider = "ollama"
model = "synthesizer-model"

[llm.extractor]
provider = "ollama"
model = "extractor-model"

[llm.classifier]
provider = "ollama"
model = "classifier-model"

[embedding]
provider = "ollama"
model = "embedding-model"
dimensions = 768

[reranker]
provider = "local"
model = "reranker-model"
```

Every generative role implements `LLMInterface`; embedding implements
`EmbeddingProvider`, and reranking implements `RerankerInterface`. Provider
identifiers are registry-resolved free-form strings.

### What Mnemo's LLMs Are NOT Allowed to Do

The LLMs inside Mnemo are constrained by their prompts and by what the modules around them do with their outputs:

- The **Planner LLM** outputs a `RetrievalPlan` JSON structure. It cannot output arbitrary tool calls. Its output schema is a typed Pydantic model.
- The **Synthesizer LLM** outputs a string with optional `[source:N]` citation markers. It cannot output `<tool_call>` or action directives. The system prompt explicitly instructs it to answer only from the provided context.
- The **Extractor LLM** outputs structured entity and relationship JSON. No free-form generation.

These constraints are architectural, not just prompt engineering. The modules that call these LLMs parse their outputs into typed structures and discard anything that doesn't parse.

---

## 15. Performance Architecture

### Incremental Indexing

When a document is updated (detected by hash mismatch on re-ingest):
1. Chunk all blocks again.
2. Compare new chunk IDs against stored chunk IDs.
3. Delete chunks whose IDs are absent (removed content).
4. Insert chunks whose IDs are new (added content).
5. Re-embed only new chunks (changed chunks have new IDs by design).
6. Update graph entities for changed sections only.

Result: re-indexing a minor edit to a 500-page document is O(changed sections), not O(entire document).

### Fast Path / Slow Path Split

| Stage | Path | Target Latency |
|---|---|---|
| Parse + Clean + Classify | Fast | <10s per 100 pages |
| Chunk + Embed + Index | Fast | <20s per 100 pages |
| NER + Question Gen | Slow | background, ≤5 min |
| Graph edge extraction | Slow | background, lazy |
| Section summaries | Slow | background, ≤5 min |

The fast path is synchronous and blocks the API response (returns when indexing is complete). The slow path enqueues jobs in SurrealDB and executes them via a background worker process.

### Embedding Cache

```
Key:   sha256(text) + "::" + model_name
Value: float[] (stored as binary in SQLite)
```

When the same text appears in multiple documents (e.g., a commonly quoted passage), it is embedded once. Cache hit rates on personal document collections typically exceed 60%.

### Parallel Ingestion

The background worker maintains a thread pool (configurable, default 4 threads for CPU-bound parsing, 8 async tasks for I/O-bound embedding). Multiple documents are ingested concurrently.

### Watch Folders (plugin)

The `watchfolder` plugin monitors configured directories using `watchdog`. New or modified files are automatically enqueued for ingestion. The plugin is designed to be idle (zero CPU) when no changes are detected.

### Document Versioning

```
Document:
  document_id:  "stable-uuid"
  versions:
    - hash: "abc123", created_at: "2024-01-01", status: SUPERSEDED
    - hash: "def456", created_at: "2025-06-01", status: CURRENT
  current_hash: "def456"
```

Old chunks remain queryable (by default). A configurable `archive_superseded` flag moves old version chunks to lower-priority retrieval pools.

---

## 16. Scalability

### At 100,000 Documents and 20 Million Chunks

#### Storage Projections

| Resource | Estimate |
|---|---|
| Raw documents (avg 5 MB) | 500 GB |
| Qdrant HNSW index (768d vectors) | ~58 GB in-memory, ~30 GB on-disk |
| SQLite FTS5 index | ~10 GB |
| SurrealDB metadata + graph | ~5 GB |
| Filesystem blobs (IR JSON) | ~20 GB |
| **Total** | ~600 GB |

Fits on a 2 TB NVMe drive. The Qdrant in-memory requirement (58 GB) may require 64–128 GB RAM for optimal performance, or Qdrant's `memmap` mode which sacrifices ~3× speed for ~10× memory reduction.

#### Query Latency

| Stage | Latency |
|---|---|
| HyDE query expansion | 500–1500ms (small LLM) |
| Dense retrieval (Qdrant HNSW) | 5–20ms |
| Sparse retrieval (SQLite FTS5) | 10–50ms |
| Metadata filtering | <5ms |
| Parent retrieval | <10ms |
| Cross-encoder reranking (50 candidates) | 200–500ms |
| Context assembly | <10ms |
| Synthesis (70B LLM @ 40 tok/s) | 15–60s (streaming starts in <5s) |

#### Graceful Degradation

- If Qdrant is in `memmap` mode (low RAM): dense retrieval degrades to ~50ms. Acceptable.
- If no GPU: synthesis with a 70B model runs at ~10 tok/s on CPU. Slow but functional.
- If `graph-retrieval` plugin not installed: graph retrieval is silently skipped. Dense + sparse still work.

---

## 17. Integration Patterns

### 17.1 Standalone User (Docker)

```bash
git clone https://github.com/[org]/mnemo
docker compose up
open http://localhost:3000
```

Nothing else required. The user interacts entirely via the browser UI.

---

### 17.2 REST API Client (Custom Application)

```python
import httpx

client = httpx.AsyncClient(base_url="http://localhost:8000")

# Ingest a document
with open("paper.pdf", "rb") as f:
    response = await client.post(
        "/v1/notebooks/my-research/sources",
        files={"file": ("paper.pdf", f, "application/pdf")}
    )
job_id = response.json()["job_id"]

# Query without synthesis (ARVSAL does its own synthesis)
result = await client.post("/v1/query", json={
    "notebook_id": "my-research",
    "question": "What are the key findings?",
    "synthesis": {"enabled": False},
    "retrieval_config": {"modes": ["dense", "sparse"], "top_k": 10}
})
# → { "context": "...", "citations": [...] }

# ARVSAL then takes this context and synthesizes with its own LLM
```

---

### 17.3 MCP Integration (Claude Desktop)

**`~/.config/claude/config.json`:**
```json
{
  "mcpServers": {
    "mnemo": {
      "command": "mnemo-mcp",
      "args": ["--host", "localhost", "--port", "8000"]
    }
  }
}
```

Claude Desktop now has access to:
- `query_notebook` — ask questions grounded in the user's documents.
- `search_all_notebooks` — full-text search across all knowledge.
- `list_notebooks` — enumerate available notebooks.
- `get_notebook_summary` — get an overview of a notebook.
- `get_timeline` — get chronological events.

Claude does not ingest documents. Claude does not manage notebooks. Claude only retrieves knowledge. The user manages documents via the Mnemo UI or REST API.

---

### 17.4 MCP Integration (ARVSAL)

ARVSAL treats Mnemo as one of many registered MCP tools:

```
User → ARVSAL Orchestrator
         │
         ├── [decides knowledge query is needed]
         │
         ▼
   MCP Tool Call: query_notebook(
       notebook_id = "research",
       question = "What does the literature say about X?",
       synthesize = false    ← ARVSAL synthesizes its own answer
   )
         │
         ▼
   Mnemo returns: { context: "...", citations: [...] }
         │
         ▼
   ARVSAL synthesizes its final answer using its own LLM,
   incorporating the Mnemo evidence as grounded context.
         │
         ▼
   Response to user with citations from Mnemo embedded.
```

ARVSAL never calls Mnemo's ingestion endpoints during a conversation. Document management is a separate, deliberate operation.

---

### 17.5 Python Library (Direct Embedding)

For maximum performance and zero HTTP overhead, `mnemo-core` can be used as a Python library:

```python
from mnemo import KnowledgeEngine, MnemoConfig

engine = KnowledgeEngine(config=MnemoConfig.from_file("mnemo.toml"))
await engine.initialize()
try:
    # Ingestion and retrieval APIs are added in their designated later phases.
    ...
finally:
    await engine.shutdown()
```

This is the deployment model for ARVSAL running Mnemo as an embedded library rather than an external service.

---

## 18. Deployment Model

### Minimal Stack (Single Container)

For users with minimal resources or simple needs:

```yaml
# docker-compose.minimal.yml
services:
  mnemo:
    image: mnemo/mnemo:latest
    ports:
      - "3000:3000"   # UI
      - "8000:8000"   # API + MCP
    volumes:
      - ./data:/data
    environment:
      MNEMO_STORAGE_FILESYSTEM_ROOT: /data/files
      MNEMO_STORAGE_SQLITE_PATH: /data/mnemo.db
      MNEMO_STORAGE_QDRANT_ENABLED: "false"
      MNEMO_STORAGE_SURREALDB_ENABLED: "false"
      # Required LLM, embedding, and reranker provider/model values are
      # supplied through mnemo.toml or their canonical MNEMO_ variables.
```

Tradeoffs: brute-force vector search instead of HNSW. Acceptable for <100K chunks.

---

### Standard Stack (Recommended)

```yaml
# docker-compose.yml
services:
  mnemo-core:
    image: mnemo/mnemo:latest
    ports:
      - "3000:3000"
      - "8000:8000"
      - "8001:8001"  # MCP SSE
    volumes:
      - ./data:/data
    depends_on:
      - qdrant
      - surrealdb
    environment:
      MNEMO_STORAGE_QDRANT_URL: http://qdrant:6333
      MNEMO_STORAGE_SURREALDB_URL: http://surrealdb:8000
      # Required LLM, embedding, and reranker provider/model values are
      # supplied through mnemo.toml or their canonical MNEMO_ variables.

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - ./qdrant_storage:/qdrant/storage
    ports:
      - "6333:6333"

  surrealdb:
    image: surrealdb/surrealdb:latest
    command: start --log info file:/data/surrealdb
    volumes:
      - ./surrealdb_data:/data
    ports:
      - "8000:8000"
```

---

### Dev Stack

```yaml
# docker-compose.dev.yml
# Adds hot reload for core and server.
# Mounts source directories as volumes.
# Enables debug logging.
```

---

## 19. Product Delivery Roadmap

This section preserves the architecture's original product-delivery stages.
They are not the numbered engineering phases. The authoritative implementation
sequence and completion state are defined by `mnemo_engineering_roadmap.md`.

### Product Stage 1 — Minimum Working Notebook (Weeks 1–8)
**Goal:** `docker compose up` → working UI → ingest PDF → chat.

- `mnemo-core`: Parser (digital PDF + Markdown), basic chunker, Ollama embedder, Qdrant + SQLite stores, SurrealDB metadata, dense retriever, basic synthesizer.
- `mnemo-server`: REST API for notebooks, sources, query. No auth.
- `mnemo-ui`: Notebook list, source upload, chat view, basic citation rendering.
- `docker-compose.yml`: Standard stack.

**Exit criterion:** User can ingest a 300-page PDF and receive a cited answer within 60 seconds.

---

### Product Stage 2 — Adaptive Chunking + Full Parser Suite (Weeks 9–16)
**Goal:** All document types handled correctly.

- Implement all built-in `ChunkerInterfaceV2` strategies (generic, book, paper,
  code, Markdown, email, resume, slides, documentation).
- Plugin: `deepdoc-parser` (advanced PDF layout understanding).
- Plugin: `ocr-paddle` (scanned document support).
- Plugin: `git-ingestion` (codebase ingestion via AST chunking).
- Plugin: `email-ingestion`.

**Exit criterion:** A 1,000-page textbook chunked with correct chapter/section hierarchy, retrievable at section granularity.

---

### Product Stage 3 — Hybrid Retrieval + Reranking (Weeks 17–22)
**Goal:** Retrieval quality that matches or exceeds NotebookLM.

- Sparse retriever (SQLite FTS5 BM25).
- Reciprocal Rank Fusion.
- CrossEncoder Reranker.
- Parent Retrieval.
- HyDE query expansion.
- MCP server (stdio mode).

**Exit criterion:** >85% answer accuracy on a personal multi-source benchmark. Claude Desktop can query notebooks via MCP.

---

### Product Stage 4 — NotebookLM Feature Parity (Weeks 23–30)
**Goal:** Every NotebookLM feature implemented locally.

- Multi-hop retrieval.
- Cross-document reasoning mode.
- Notebook summaries.
- Automatic Session Notes.
- Citation Engine (persistent, UI-clickable).
- MCP SSE mode for remote clients.
- Plugin: `podcast-gen` (Kokoro TTS).
- Plugin: `timeline-gen`.

**Exit criterion:** A 20-minute podcast generated from a 10-source notebook. All citations rendered as clickable links in the UI.

---

### Product Stage 5 — Knowledge Graph + Source Insights (Weeks 31–38)
**Goal:** The system understands relationships, not just content.

- Plugin: `graph-retrieval` (spaCy NER + lazy relationship extraction + SurrealDB graph retrieval).
- Insight extraction and management.
- Knowledge Graph Explorer UI.
- Watch folder support (`watchfolder` plugin).
- Document versioning.

**Exit criterion:** User can explore the entity graph of a 50-source notebook with relationship edges.

---

### Product Stage 6 — Scale + Production Polish (Weeks 39–46)
**Goal:** Production-grade stability at 100K document scale.

- Qdrant `memmap` mode configuration for low-RAM environments.
- Embedding cache with cross-session persistence.
- Background job management UI.
- API key authentication.
- Plugin: `raptor` (hierarchical summary indexing for very long documents).
- Benchmark: 100K PDF collection, 20M chunks, query latency <30s end-to-end.

**Exit criterion:** Mnemo handles a 100K document corpus on a machine with 32 GB RAM.

---

### Product Stage 7 — Ecosystem and Extensibility (Month 12+)
**Goal:** Become the reference implementation for local knowledge retrieval.

- Plugin SDK documentation.
- Official plugins: EPUB parser, browser history ingestion.
- OpenAPI specification published.
- MCP server certified against the MCP specification test suite.
- Embed in Open WebUI as a knowledge retrieval backend.

---

## 20. Critical Review

### Weakness 1: Four Storage Systems = Operational Complexity

Qdrant + SQLite + SurrealDB + Filesystem is four systems to maintain, monitor, and back up. A configuration error in any one breaks the system.

**Mitigation:** All four are accessed through `StorageInterface`. A single `mnemo backup` command backs up all four atomically. The Filesystem is the ground truth — if any index is corrupted, re-ingestion from blobs reconstructs everything. The minimal docker-compose uses SQLite for vector search (brute force, one fewer container) for users who prioritize simplicity over scale.

---

### Weakness 2: Local LLM Quality Ceiling

The quality of synthesis, planning, and extraction is bounded by the best model the user can run locally. For users with <16 GB RAM, this means 7B models, which produce noticeably lower quality than GPT-4o.

**Mitigation:** The `LLMInterface` accepts any provider. Users who want higher quality for synthesis can configure an OpenAI-compatible cloud endpoint for just that role while keeping all data locally. Document data never leaves the machine — only the synthesized query does, if the user chooses.

---

### Weakness 3: Knowledge Graph Quality Degrades at Scale

The entity graph is built by a small LLM running in batch. At 100K documents, the graph will have:
- Duplicate entities (different surface forms for the same entity).
- Low-confidence relationships hallucinated by the extractor.

**Mitigation:** Entity normalization before insertion (fuzzy match + canonical form). Low-confidence edges are flagged and not used for primary retrieval. The graph is an additive enrichment layer — its failure degrades graph retrieval only, not dense or sparse retrieval.

---

### Weakness 4: HyDE Adds Latency

Generating a hypothetical answer paragraph using the Planner LLM adds 500–1500ms before any retrieval begins.

**Mitigation:** HyDE is configurable. It can be disabled globally or per-request. For latency-sensitive integrations (MCP tool calls inside an interactive conversation), callers can disable HyDE and accept slightly lower recall. For background batch analysis, HyDE should always be enabled.

---

### Weakness 5: Plugin Fragmentation Risk

As the plugin ecosystem grows, users will face incompatibility between plugin versions and core versions. A breaking change in `ParserInterface` breaks every parser plugin.

**Mitigation:** Interface contracts are versioned (`ParserInterfaceV1`, `ParserInterfaceV2`). Core supports multiple interface versions simultaneously with a deprecation window. Plugin manifests declare compatible core version ranges. The registry warns on startup if a plugin declares an incompatible range.

---

### Weakness 6: No Multi-User Access Control at Core Level

`mnemo-core` has no concept of users, permissions, or access control. This is intentional for single-user deployments but is a gap for shared deployments.

**Mitigation:** Multi-user access control belongs in `mnemo-server`, not `mnemo-core`. The server layer enforces user-scoped notebook access. At the core level, all notebooks are accessible to all callers — the server is the trust boundary. Enterprise deployments requiring row-level security must implement it in `mnemo-server`.

---

## 21. Final Architecture Snapshot

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              MNEMO                                        │
│                    Local Knowledge Engine                                 │
│                       Open Source · Local-First · Privacy-Absolute       │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  IDENTITY                                                                 │
│  ────────                                                                 │
│  Not an agent. Not an assistant. Not a tool executor.                     │
│  A knowledge retrieval engine. The epistemic layer.                       │
│  "What do my documents say about X?" — that is its only question.        │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  LAYER MODEL                                                              │
│  ───────────                                                              │
│  mnemo-core    │ Pure Python library. No HTTP. Embeddable.               │
│  mnemo-server  │ FastAPI adapter. REST + MCP + WebSocket.                │
│  mnemo-ui      │ React frontend. Calls server only.                      │
│  plugins/      │ Opt-in extensions. Implement typed interfaces.          │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  STORAGE STACK                                                            │
│  ─────────────                                                            │
│  Qdrant        │ HNSW vector index. Dense retrieval.                     │
│  SQLite FTS5   │ BM25 keyword index. Exact-match retrieval.              │
│  SurrealDB     │ Relations, graph, sessions, citations.                  │
│  Filesystem    │ Content-addressable blobs. Ground truth.                │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  LLM ROLES                                                               │
│  ─────────                                                               │
│  planner       │ Retrieval planning only. Structured output.             │
│  synthesizer   │ Grounded answer generation. Citation-aware.             │
│  extractor     │ NER, relationships, questions. Batch mode.              │
│  classifier    │ Document-type classification.                           │
│  All roles:    │ Independently configurable providers and models.        │
│  embedding     │ Separate text-to-vector provider family.                │
│  reranker      │ Separate candidate-scoring provider family.             │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  INGESTION                                                               │
│  ─────────                                                               │
│  Fast Path     │ Parse → Clean → Classify → Chunk → Embed → Index        │
│  Target        │ <30s per 100-page PDF                                   │
│  Slow Path     │ NER → Questions → Summaries → Graph Edges               │
│  Target        │ <5 min background, interruptible                        │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  RETRIEVAL                                                               │
│  ─────────                                                               │
│  HyDE          │ Embed hypothetical answer for better dense recall       │
│  Parallel      │ Dense + Sparse + Graph run simultaneously               │
│  Parent        │ Chunk → Section promotion when siblings co-occur        │
│  Reranking     │ CrossEncoder (query, chunk) pairs                       │
│  Compression   │ Adaptive context budget management                      │
│  Citations     │ Every statement → chunk → page → document               │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  INTEGRATION                                                             │
│  ───────────                                                             │
│  Standalone    │ docker compose up → browser → done                      │
│  REST API      │ Any HTTP client. Full management + retrieval.           │
│  MCP stdio     │ Claude Desktop, VS Code, ARVSAL (local).               │
│  MCP SSE       │ Remote MCP clients over HTTP.                           │
│  Python lib    │ pip install mnemo-core. Zero HTTP overhead.             │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  DESIGN PRINCIPLES                                                        │
│  ─────────────────                                                        │
│  1. Privacy is axiomatic. No telemetry. No external calls.               │
│  2. Every interface is a typed contract. Every impl is replaceable.      │
│  3. Ingest fast. Enrich lazily.                                          │
│  4. Chunking is semantic compression, not text splitting.                │
│  5. Retrieval is always dense + sparse + (graph if available).           │
│  6. Every statement is cited. Every fact is traceable.                   │
│  7. Core has no HTTP. Server has no business logic.                      │
│  8. Plugins are opt-in. Minimal install is fully functional.             │
│                                                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

---

*End of Mnemo Architecture Specification v2.0*  
*This document supersedes the ARVSAL Notebook Architecture Specification v1.0.*  
*All implementation must conform to the layer boundaries and interface contracts defined herein.*  
*No business logic may exist in mnemo-server.*  
*No HTTP may exist in mnemo-core.*  
*These two constraints are inviolable.*
