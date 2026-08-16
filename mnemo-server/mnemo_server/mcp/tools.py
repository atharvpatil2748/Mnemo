"""Knowledge tool definitions and dispatcher for the Mnemo MCP Server."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import mcp.types as types
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    DependencyUnavailableError,
    NotFoundError,
    TokenCounterInterfaceV1,
)
from mnemo.models import FrozenMetadata, InsightType
from mnemo.tokenizers import O200KBaseTokenCounter

from mnemo_server.schemas.query import QueryRequest, RetrievalConfig, SynthesisConfig
from mnemo_server.schemas.search import SearchRequest
from mnemo_server.services.query import QueryService
from mnemo_server.services.search import SearchService
from mnemo_server.tokenizer_provisioning import provision_tokenizer

_LOGGER = logging.getLogger("mnemo.mcp.tools")

MCPContent = types.TextContent | types.ImageContent | types.EmbeddedResource


_TOOL_DEFINITIONS: list[types.Tool] = [
    types.Tool(
        name="query_notebook",
        description=(
            "Retrieve evidence from a specific notebook in response to a question. "
            "Returns grounded evidence with source citations. Does not browse the "
            "web, execute code, or perform any external actions."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "notebook_id": {
                    "type": "string",
                    "description": "UUID of the notebook to query",
                },
                "question": {
                    "type": "string",
                    "description": "The question to answer",
                },
                "top_k": {
                    "type": "integer",
                    "description": (
                        "Maximum number of evidence chunks to retrieve (default: 10, range: 1-100)"
                    ),
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "synthesize": {
                    "type": "boolean",
                    "description": "Whether to synthesize an answer (default: true)",
                    "default": True,
                },
            },
            "required": ["notebook_id", "question"],
        },
    ),
    types.Tool(
        name="search_all_notebooks",
        description="Full-text and semantic search across all notebooks.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string",
                },
                "top_k": {
                    "type": "integer",
                    "description": (
                        "Maximum number of search results to return (default: 10, range: 1-100)"
                    ),
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "notebook_id": {
                    "type": "string",
                    "description": "Optional UUID to constrain search to a specific notebook",
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="list_notebooks",
        description="List all available notebooks with their source counts.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of notebooks to return (default: 50, range: 1-100)"
                    ),
                    "default": 50,
                    "minimum": 1,
                    "maximum": 100,
                },
                "cursor": {
                    "type": "string",
                    "description": "Optional pagination cursor for keyset pagination",
                },
            },
        },
    ),
    types.Tool(
        name="get_notebook_summary",
        description="Get a pre-generated or freshly-generated summary of a notebook.",
        inputSchema={
            "type": "object",
            "properties": {
                "notebook_id": {
                    "type": "string",
                    "description": "UUID of the notebook to retrieve summary for",
                },
            },
            "required": ["notebook_id"],
        },
    ),
    types.Tool(
        name="get_source_insights",
        description="Get extracted insights (key facts, entities) from a specific source.",
        inputSchema={
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "UUID of the source to retrieve insights for",
                },
                "insight_type": {
                    "type": "string",
                    "description": "Optional insight type filter",
                    "enum": ["fact", "key_fact", "summary", "entity", "claim"],
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of insights to return (default: 50, range: 1-100)"
                    ),
                    "default": 50,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["source_id"],
        },
    ),
    types.Tool(
        name="get_timeline",
        description="Get chronological events extracted from a notebook.",
        inputSchema={
            "type": "object",
            "properties": {
                "notebook_id": {
                    "type": "string",
                    "description": "UUID of the notebook to get timeline events for",
                },
                "source_id": {
                    "type": "string",
                    "description": "Optional source UUID to constrain timeline extraction",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of timeline events to return (default: 50, range: 1-100)"
                    ),
                    "default": 50,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["notebook_id"],
        },
    ),
]


def get_mcp_tools() -> list[types.Tool]:
    """Return the list of authoritative MCP tool definitions exposed by Mnemo."""
    return list(_TOOL_DEFINITIONS)


def _unpack_metadata(meta: Any) -> dict[str, Any]:
    """Recursively unpack FrozenMetadata into a standard JSON dictionary."""
    if isinstance(meta, (FrozenMetadata, dict)):
        return {k: _unpack_value(v) for k, v in meta.items()}
    return {}


def _unpack_value(v: Any) -> Any:
    """Recursively unpack values into JSON-compatible python primitives."""
    if isinstance(v, (FrozenMetadata, dict)):
        return _unpack_metadata(v)
    if isinstance(v, (tuple, list)):
        return [_unpack_value(item) for item in v]
    if isinstance(v, UUID):
        return str(v)
    return v


def _parse_uuid(value: Any, param_name: str) -> UUID:
    """Parse and validate a string as a UUID."""
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"Parameter '{param_name}' must be a non-empty UUID string")
    try:
        return UUID(value.strip())
    except ValueError as err:
        raise ContractValidationError(
            f"Parameter '{param_name}' has invalid UUID format: '{value}'"
        ) from err


def _get_token_counter() -> TokenCounterInterfaceV1:
    """Lazily provision tokenizer asset and return canonical token counter."""
    asset_path = provision_tokenizer()
    return O200KBaseTokenCounter(asset_path)


async def execute_mcp_tool(
    engine: KnowledgeEngine | None,
    name: str,
    arguments: dict[str, Any] | None,
) -> list[MCPContent]:
    """Execute an authorized Mnemo MCP knowledge tool call."""
    if engine is None or engine.state is not EngineState.READY:
        raise DependencyUnavailableError(
            "KnowledgeEngine is not ready or uninitialized on the MCP server",
            retryable=True,
        )

    args = arguments or {}

    if name == "query_notebook":
        return await _handle_query_notebook(engine, args)
    elif name == "search_all_notebooks":
        return await _handle_search_all_notebooks(engine, args)
    elif name == "list_notebooks":
        return await _handle_list_notebooks(engine, args)
    elif name == "get_notebook_summary":
        return await _handle_get_notebook_summary(engine, args)
    elif name == "get_source_insights":
        return await _handle_get_source_insights(engine, args)
    elif name == "get_timeline":
        return await _handle_get_timeline(engine, args)
    else:
        raise ValueError(f"Unknown MCP tool: '{name}'")


async def _handle_query_notebook(
    engine: KnowledgeEngine,
    args: dict[str, Any],
) -> list[MCPContent]:
    """Handle query_notebook tool invocation."""
    notebook_id_raw = args.get("notebook_id")
    question = args.get("question")
    top_k = args.get("top_k", 10)
    synthesize = args.get("synthesize", True)

    notebook_id = _parse_uuid(notebook_id_raw, "notebook_id")

    if not isinstance(question, str) or not question.strip():
        raise ContractValidationError("Parameter 'question' must be a non-empty string")

    if not isinstance(top_k, int) or top_k < 1 or top_k > 100:
        raise ContractValidationError("Parameter 'top_k' must be an integer between 1 and 100")

    if not isinstance(synthesize, bool):
        raise ContractValidationError("Parameter 'synthesize' must be a boolean")

    token_counter = _get_token_counter()
    service = QueryService(engine=engine, token_counter=token_counter)

    req = QueryRequest(
        question=question.strip(),
        notebook_id=notebook_id,
        retrieval_config=RetrievalConfig(top_k=top_k),
        synthesis=SynthesisConfig(enabled=synthesize),
    )

    resp = await service.execute_query(req)

    data = {
        "answer": resp.answer,
        "citations": [
            {
                "id": str(c.id),
                "chunk_id": str(c.chunk_id),
                "document_title": c.document_title,
                "page": c.page,
                "heading_path": c.heading_path,
                "quote": c.quote,
                "confidence": c.confidence,
            }
            for c in resp.citations
        ],
        "retrieval_metadata": {
            "chunks_retrieved": resp.retrieval_metadata.chunks_retrieved,
            "chunks_used": resp.retrieval_metadata.chunks_used,
            "retrieval_modes_used": resp.retrieval_metadata.retrieval_modes_used,
            "latency_ms": resp.retrieval_metadata.latency_ms,
        },
    }

    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


async def _handle_search_all_notebooks(
    engine: KnowledgeEngine,
    args: dict[str, Any],
) -> list[MCPContent]:
    """Handle search_all_notebooks tool invocation."""
    query = args.get("query")
    top_k = args.get("top_k", 10)
    notebook_id_raw = args.get("notebook_id")

    if not isinstance(query, str) or not query.strip():
        raise ContractValidationError("Parameter 'query' must be a non-empty string")

    if not isinstance(top_k, int) or top_k < 1 or top_k > 100:
        raise ContractValidationError("Parameter 'top_k' must be an integer between 1 and 100")

    notebook_id: UUID | None = None
    if notebook_id_raw is not None:
        notebook_id = _parse_uuid(notebook_id_raw, "notebook_id")

    service = SearchService(engine=engine)
    req = SearchRequest(
        query=query.strip(),
        notebook_id=notebook_id,
        limit=top_k,
    )

    resp = await service.execute_search(req)

    data = {
        "results": [
            {
                "chunk_id": str(r.chunk_id),
                "document_id": str(r.document_id),
                "version_id": str(r.version_id),
                "text": r.text,
                "score": r.score,
                "rank": r.rank,
                "retrieval_mode": r.retrieval_mode,
                "heading_path": r.heading_path,
                "page_number": r.page_number,
                "metadata": r.metadata,
            }
            for r in resp.results
        ],
        "total": resp.total,
        "latency_ms": resp.latency_ms,
    }

    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


async def _handle_list_notebooks(
    engine: KnowledgeEngine,
    args: dict[str, Any],
) -> list[MCPContent]:
    """Handle list_notebooks tool invocation."""
    limit = args.get("limit", 50)
    cursor = args.get("cursor")

    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ContractValidationError("Parameter 'limit' must be an integer between 1 and 100")

    cursor_str = str(cursor) if cursor is not None else None
    page = await engine.storage.list_notebooks(limit=limit, cursor=cursor_str)

    notebooks_list: list[dict[str, Any]] = []
    for nb in page.items:
        # Aggregated source count for each notebook
        sources_page = await engine.storage.list_sources(
            notebook_id=nb.notebook_id, limit=1000, cursor=None
        )
        notebooks_list.append(
            {
                "notebook_id": str(nb.notebook_id),
                "title": nb.title,
                "description": nb.description,
                "source_count": len(sources_page.items),
                "created_at": nb.created_at.isoformat(),
                "updated_at": nb.updated_at.isoformat(),
                "metadata": _unpack_metadata(nb.metadata),
            }
        )

    data = {
        "notebooks": notebooks_list,
        "next_cursor": page.next_cursor,
        "total": len(notebooks_list),
    }

    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


async def _handle_get_notebook_summary(
    engine: KnowledgeEngine,
    args: dict[str, Any],
) -> list[MCPContent]:
    """Handle get_notebook_summary tool invocation."""
    notebook_id_raw = args.get("notebook_id")
    notebook_id = _parse_uuid(notebook_id_raw, "notebook_id")

    existing = await engine.storage.get_notebook(notebook_id)
    if existing is None:
        raise NotFoundError(f"Notebook {notebook_id} was not found")

    insights_page = await engine.storage.list_insights(notebook_id, limit=100, cursor=None)
    sources_page = await engine.storage.list_sources(notebook_id, limit=100, cursor=None)

    summaries = [
        {
            "summary_id": str(ins.insight_id),
            "source_id": str(ins.source_id) if ins.source_id else None,
            "content": ins.content,
            "created_at": ins.created_at.isoformat(),
        }
        for ins in insights_page.items
        if ins.type == InsightType.SUMMARY
    ]

    sources = []
    for s in sources_page.items:
        doc_title = str(s.document_id)
        try:
            doc = await engine.storage.get_document(s.document_id)
            if doc is not None:
                for v in doc.versions:
                    if v.version_id == doc.current_version_id and v.metadata.title:
                        doc_title = v.metadata.title
                        break
        except Exception:
            pass
        sources.append(
            {
                "source_id": str(s.source_id),
                "document_id": str(s.document_id),
                "title": doc_title,
                "created_at": s.created_at.isoformat(),
            }
        )

    combined_summary = "\n\n".join(str(s["content"]) for s in summaries) if summaries else None
    status_str = "ready" if summaries else "empty"

    data = {
        "notebook_id": str(notebook_id),
        "summary": combined_summary,
        "summaries": summaries,
        "sources": sources,
        "status": status_str,
    }

    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


async def _handle_get_source_insights(
    engine: KnowledgeEngine,
    args: dict[str, Any],
) -> list[MCPContent]:
    """Handle get_source_insights tool invocation."""
    source_id_raw = args.get("source_id")
    insight_type_raw = args.get("insight_type")
    limit = args.get("limit", 50)

    source_id = _parse_uuid(source_id_raw, "source_id")

    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ContractValidationError("Parameter 'limit' must be an integer between 1 and 100")

    target_type: InsightType | None = None
    if insight_type_raw is not None:
        normalized = insight_type_raw.lower().strip()
        if normalized == "fact":
            normalized = "key_fact"
        try:
            target_type = InsightType(normalized)
        except ValueError as err:
            raise ContractValidationError(
                f"Invalid insight_type: '{insight_type_raw}'. "
                f"Expected one of: {[t.value for t in InsightType]}"
            ) from err

    source = await engine.storage.get_source(source_id)
    if source is None:
        raise NotFoundError(f"Source with id '{source_id}' not found")

    insights_page = await engine.storage.list_insights(source.notebook_id, limit=1000, cursor=None)

    matching_insights = [
        ins
        for ins in insights_page.items
        if ins.source_id == source_id and (target_type is None or ins.type is target_type)
    ][:limit]

    data = {
        "source_id": str(source_id),
        "notebook_id": str(source.notebook_id),
        "insights": [
            {
                "insight_id": str(ins.insight_id),
                "notebook_id": str(ins.notebook_id),
                "source_id": str(ins.source_id) if ins.source_id else None,
                "type": ins.type.value,
                "content": ins.content,
                "confidence": ins.confidence,
                "created_at": ins.created_at.isoformat(),
                "metadata": _unpack_metadata(ins.metadata),
            }
            for ins in matching_insights
        ],
        "total": len(matching_insights),
    }

    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


async def _handle_get_timeline(
    engine: KnowledgeEngine,
    args: dict[str, Any],
) -> list[MCPContent]:
    """Handle get_timeline tool invocation."""
    notebook_id_raw = args.get("notebook_id")
    limit = args.get("limit", 50)

    notebook_id = _parse_uuid(notebook_id_raw, "notebook_id")

    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ContractValidationError("Parameter 'limit' must be an integer between 1 and 100")

    existing = await engine.storage.get_notebook(notebook_id)
    if existing is None:
        raise NotFoundError(f"Notebook {notebook_id} was not found")

    sources_page = await engine.storage.list_sources(
        notebook_id=notebook_id, limit=1000, cursor=None
    )
    notes_page = await engine.storage.list_notes(notebook_id=notebook_id, limit=1000, cursor=None)
    sessions_page = await engine.storage.list_sessions(
        notebook_id=notebook_id, limit=1000, cursor=None
    )

    events: list[dict[str, Any]] = []
    for s in sources_page.items:
        events.append(
            {
                "event_type": "source_added",
                "event_id": str(s.source_id),
                "timestamp": s.created_at.isoformat(),
                "title": "Source Added",
                "details": {"document_id": str(s.document_id)},
            }
        )
    for n in notes_page.items:
        events.append(
            {
                "event_type": "note_created",
                "event_id": str(n.note_id),
                "timestamp": n.created_at.isoformat(),
                "title": n.title or "Untitled Note",
                "details": {
                    "origin": str(n.origin.value if hasattr(n.origin, "value") else n.origin)
                },
            }
        )
    for sess in sessions_page.items:
        events.append(
            {
                "event_type": "session_started",
                "event_id": str(sess.session_id),
                "timestamp": sess.created_at.isoformat(),
                "title": sess.title or "New Conversation",
                "details": {},
            }
        )

    # Sort descending by timestamp (most recent first)
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    sliced_events = events[:limit]

    data = {
        "notebook_id": str(notebook_id),
        "events": sliced_events,
        "total": len(sliced_events),
    }

    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
