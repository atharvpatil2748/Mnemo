"""Knowledge tool definitions and dispatcher for the Mnemo MCP Server."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any
from uuid import UUID, uuid4

import mcp.types as types
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import (
    ContractValidationError,
    DeliveryAuthorizationError,
    DeliveryCursorConflictError,
    DeliveryCursorError,
    DeliveryCursorExpiredError,
    DeliveryLimitExceededError,
    DependencyUnavailableError,
    IntegrityError,
    NotFoundError,
    TokenCounterInterfaceV1,
)
from mnemo.models import (
    AssetAnalysisModality,
    AssetAnalysisSelection,
    AssetAnalysisSelector,
    DeliveryCompleteness,
    DeliveryRequest,
    DeliveryView,
    FrozenMetadata,
    InsightType,
)
from mnemo.retrieval import StorageDocumentScopeResolverV1, StorageSourceAssociationReaderV1
from mnemo.tokenizers import O200KBaseTokenCounter
from pydantic import AnyUrl

from mnemo_server.config import ServerConfig
from mnemo_server.schemas.capabilities_v2 import CapabilityDiscoveryRequest
from mnemo_server.schemas.delivery import DocumentExpansionRequestBody
from mnemo_server.schemas.final_qa_v2 import FinalQAV2RequestBody
from mnemo_server.schemas.query import QueryRequest, RetrievalConfig, SynthesisConfig
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest
from mnemo_server.schemas.search import SearchRequest
from mnemo_server.schemas.structured_v2 import StructuredRetrievalRequest
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
    ServerPrincipalV1,
    principal_from_claims,
)
from mnemo_server.services.capabilities_v2 import CapabilityDiscoveryService
from mnemo_server.services.delivery import build_delivery_service, delivery_response_body
from mnemo_server.services.final_qa_v2 import (
    FinalQAV2ApplicationService,
)
from mnemo_server.services.query import QueryService
from mnemo_server.services.retrieval_v2 import EvidenceRetrievalApplicationService
from mnemo_server.services.search import SearchService
from mnemo_server.services.structured_v2 import StructuredRetrievalApplicationService
from mnemo_server.tokenizer_provisioning import provision_tokenizer

from .contracts import (
    CAPABILITIES_TOOL,
    CONTRACT_VERSION,
    FINAL_QA_V2_TOOL,
    QUERY_STRUCTURED_TOOL,
    SEARCH_EVIDENCE_TOOL,
    apply_retained_contracts,
)

_LOGGER = logging.getLogger("mnemo.mcp.tools")

MCPContent = types.TextContent | types.ImageContent | types.EmbeddedResource


_LEGACY_TOOL_DEFINITIONS: list[types.Tool] = [
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
    types.Tool(
        name="get_document",
        description=(
            "Retrieve an authorized exact document version using bounded blocks or original bytes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "UUID of the document"},
                "version_id": {"type": "string", "description": "UUID of the document version"},
                "notebook_id": {
                    "type": "string",
                    "description": (
                        "Optional UUID of the parent notebook. Auto-resolved if unambiguous."
                    ),
                },
                "mode": {"type": "string", "enum": ["blocks", "original"], "default": "blocks"},
                "selector": {
                    "description": (
                        "Exactly one deterministic positional selector for blocks mode. Use full, "
                        "page_range, slide_range, sheet_range, block_range, chunk_range, section, "
                        "from_end, or adjacent. Omit only for the legacy full-block traversal."
                    ),
                    "oneOf": [
                        {
                            "type": "object",
                            "properties": {"kind": {"const": "full"}},
                            "required": ["kind"],
                            "additionalProperties": False,
                        },
                        *[
                            {
                                "type": "object",
                                "properties": {
                                    "kind": {"const": kind},
                                    "start": {"type": "integer", "minimum": minimum},
                                    "end": {"type": "integer", "minimum": minimum},
                                },
                                "required": ["kind", "start", "end"],
                                "additionalProperties": False,
                            }
                            for kind, minimum in (
                                ("page_range", 1),
                                ("slide_range", 1),
                                ("sheet_range", 1),
                                ("block_range", 0),
                                ("chunk_range", 0),
                            )
                        ],
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"const": "section"},
                                "heading_path": {
                                    "type": "array",
                                    "items": {"type": "string", "minLength": 1},
                                    "minItems": 1,
                                },
                            },
                            "required": ["kind", "heading_path"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"const": "from_end"},
                                "unit": {
                                    "type": "string",
                                    "enum": [
                                        "page",
                                        "slide",
                                        "sheet",
                                        "block",
                                        "chunk",
                                        "section",
                                        "paragraph",
                                    ],
                                },
                                "count": {"type": "integer", "minimum": 1, "default": 1},
                            },
                            "required": ["kind", "unit"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {
                                "kind": {"const": "adjacent"},
                                "anchor_kind": {"type": "string", "enum": ["block", "chunk"]},
                                "block_ordinal": {"type": "integer", "minimum": 0},
                                "chunk_id": {"type": "string", "minLength": 64, "maxLength": 64},
                                "before": {"type": "integer", "minimum": 0, "default": 0},
                                "after": {"type": "integer", "minimum": 0, "default": 0},
                                "include_anchor": {"type": "boolean", "default": True},
                            },
                            "required": ["kind", "anchor_kind"],
                            "additionalProperties": False,
                        },
                    ],
                },
                "cursor": {
                    "type": "string",
                    "description": (
                        "Opaque next_cursor returned by the prior get_document call. Pass it "
                        "unchanged; it is not a page number."
                    ),
                },
                "max_bytes": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Requested byte ceiling, capped by server policy.",
                },
                "max_items": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Requested block ceiling, capped by server policy.",
                },
            },
            "required": ["document_id", "version_id"],
        },
    ),
    types.Tool(
        name="get_document_chunk",
        description="Retrieve one exact authorized canonical chunk and its ancestry.",
        inputSchema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "UUID of the document"},
                "version_id": {"type": "string", "description": "UUID of the document version"},
                "chunk_id": {
                    "type": "string",
                    "minLength": 64,
                    "maxLength": 64,
                    "description": "SHA-256 chunk identity",
                },
                "notebook_id": {
                    "type": "string",
                    "description": (
                        "Optional UUID of the parent notebook. Auto-resolved if unambiguous."
                    ),
                },
            },
            "required": ["document_id", "version_id", "chunk_id"],
        },
    ),
    types.Tool(
        name="get_asset",
        description="List bounded asset occurrences or retrieve one authorized original asset.",
        inputSchema={
            "type": "object",
            "properties": {
                "notebook_id": {"type": "string", "description": "Authorizing notebook UUID."},
                "document_id": {
                    "type": "string",
                    "description": "Document UUID for occurrence inventory mode.",
                },
                "version_id": {
                    "type": "string",
                    "description": "Exact version UUID for occurrence inventory mode.",
                },
                "occurrence_id": {
                    "type": "string",
                    "description": "Known occurrence UUID for original binary delivery mode.",
                },
                "cursor": {
                    "type": "string",
                    "description": (
                        "Opaque next_cursor from the same inventory or binary call; pass unchanged."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Requested occurrence count ceiling, capped by server policy.",
                },
                "max_bytes": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Requested binary range ceiling, capped by server policy.",
                },
            },
            "required": ["notebook_id"],
            "anyOf": [
                {"required": ["occurrence_id"]},
                {"required": ["document_id", "version_id"]},
            ],
        },
    ),
    types.Tool(
        name="get_image_analysis",
        description=(
            "Retrieve bounded authorized OCR and/or vision derivations for an image occurrence."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "notebook_id": {"type": "string", "description": "Authorizing notebook UUID."},
                "occurrence_id": {
                    "type": "string",
                    "description": "Known image occurrence UUID, normally returned by get_asset.",
                },
                "ocr_derivation_id": {
                    "type": "string",
                    "description": "Optional exact existing OCR derivation UUID.",
                },
                "vision_derivation_id": {
                    "type": "string",
                    "description": "Optional exact existing Vision derivation UUID.",
                },
                "selection": {
                    "type": "string",
                    "enum": ["explicit", "latest_ready", "all"],
                    "default": "explicit",
                    "description": (
                        "Use explicit with existing IDs, latest_ready to deterministically select "
                        "one ready derivation per modality, or all for every ready derivation."
                    ),
                },
                "modalities": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["ocr", "vision"]},
                    "uniqueItems": True,
                    "minItems": 1,
                    "description": "Derived analysis kinds; original bytes come from get_asset.",
                },
                "profile": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional exact generation profile filter.",
                },
            },
            "required": ["notebook_id", "occurrence_id"],
        },
    ),
]

_TOOL_DEFINITIONS = [
    *apply_retained_contracts(_LEGACY_TOOL_DEFINITIONS),
    SEARCH_EVIDENCE_TOOL,
    QUERY_STRUCTURED_TOOL,
    FINAL_QA_V2_TOOL,
    CAPABILITIES_TOOL,
]


def get_mcp_tools() -> list[types.Tool]:
    """Return the list of authoritative MCP tool definitions exposed by Mnemo."""
    return list(_TOOL_DEFINITIONS)


def _next_action(
    tool: str,
    reason: str,
    *arguments: str,
    pass_cursor_unchanged: bool = False,
    stop_condition: str | None = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "tool": tool,
        "reason": reason,
        "arguments_from_result": list(arguments),
    }
    if pass_cursor_unchanged:
        action["pass_cursor_unchanged"] = True
    if stop_condition is not None:
        action["stop_condition"] = stop_condition
    return action


def _contract_fields(
    operation: str,
    *,
    completeness: str,
    coverage: dict[str, Any],
    limits: dict[str, Any],
    next_cursor: str | None = None,
    omissions: list[str] | None = None,
    recommended_next_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_VERSION,
        "operation": operation,
        "request_id": str(uuid4()),
        "completeness": completeness,
        "coverage": coverage,
        "omissions": omissions or [],
        "limits": limits,
        "next_cursor": next_cursor,
        "recommended_next_actions": recommended_next_actions or [],
    }


def structured_content_for(
    name: str, arguments: dict[str, Any], content: list[MCPContent]
) -> dict[str, Any]:
    """Build structured MCP content while retaining legacy content blocks."""
    if len(content) == 1 and isinstance(content[0], types.TextContent):
        value = json.loads(content[0].text)
        if isinstance(value, dict):
            if name == "run_final_qa_v2":
                evidence = arguments.get("evidence_request_or_snapshot")
                requested_k = (
                    evidence.get("evidence_budget") if isinstance(evidence, dict) else None
                )
                return {
                    **value,
                    "schema_version": str(value.get("contract_version", "")),
                    "operation": name,
                    "request_id": str(value.get("execution_id", "")),
                    "limits": {"requested_k": requested_k},
                }
            return value
    # Binary delivery keeps native MCP content and adds a non-secret companion envelope.
    resource = content[0]
    mime_type: str | None = None
    next_cursor: str | None = None
    completeness = "complete"
    if isinstance(resource, types.ImageContent):
        mime_type = resource.mimeType
        metadata = resource.meta or {}
        completeness = str(metadata.get("completeness", "complete"))
        next_cursor_value = metadata.get("nextCursor")
        next_cursor = str(next_cursor_value) if next_cursor_value is not None else None
    elif isinstance(resource, types.EmbeddedResource):
        mime_type = resource.resource.mimeType
        metadata = resource.resource.meta or {}
        completeness = str(metadata.get("completeness", "complete"))
        next_cursor_value = metadata.get("nextCursor")
        next_cursor = str(next_cursor_value) if next_cursor_value is not None else None
    return {
        "resource": {
            "content_type": resource.type,
            "mime_type": mime_type,
            "notebook_id": arguments.get("notebook_id"),
            "document_id": arguments.get("document_id"),
            "version_id": arguments.get("version_id"),
            "occurrence_id": arguments.get("occurrence_id"),
        },
        **_contract_fields(
            name,
            completeness=completeness,
            coverage={"resource": "delivered"},
            limits={"bounded_by_server": True},
            next_cursor=next_cursor,
            recommended_next_actions=(
                [
                    _next_action(
                        name,
                        "Continue this exact resource delivery.",
                        "next_cursor",
                        pass_cursor_unchanged=True,
                        stop_condition="next_cursor is null",
                    )
                ]
                if next_cursor is not None
                else []
            ),
        ),
    }


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
    server_config: ServerConfig | None = None,
    principal: ServerPrincipalV1 | None = None,
) -> list[MCPContent]:
    """Execute an authorized Mnemo MCP knowledge tool call."""
    if engine is None or engine.state is not EngineState.READY:
        raise DependencyUnavailableError(
            "KnowledgeEngine is not ready or uninitialized on the MCP server",
            retryable=True,
        )

    args = arguments or {}
    config = server_config or ServerConfig()
    server_principal = _principal_for_call(principal, config)

    if name == "query_notebook":
        return await _handle_query_notebook(engine, args)
    elif name == "search_all_notebooks":
        return await _handle_search_all_notebooks(engine, args)
    elif name == "search_evidence":
        return await _handle_search_evidence(
            engine,
            args,
            config,
            server_principal,
        )
    elif name == "query_structured":
        return await _handle_query_structured(
            engine,
            args,
            config,
            server_principal,
        )
    elif name == "run_final_qa_v2":
        return await _handle_final_qa_v2(
            engine,
            args,
            config,
            server_principal,
        )
    elif name == "get_capabilities":
        return await _handle_get_capabilities(engine, args, config)
    elif name == "list_notebooks":
        return await _handle_list_notebooks(engine, args)
    elif name == "get_notebook_summary":
        return await _handle_get_notebook_summary(engine, args)
    elif name == "get_source_insights":
        return await _handle_get_source_insights(engine, args)
    elif name == "get_timeline":
        return await _handle_get_timeline(engine, args)
    elif name in {"get_document", "get_document_chunk", "get_asset", "get_image_analysis"}:
        return await _execute_delivery_tool(
            engine,
            name,
            args,
            config,
            server_principal,
        )
    else:
        raise ValueError(f"Unknown MCP tool: '{name}'")


def _principal_for_call(
    principal: ServerPrincipalV1 | None, config: ServerConfig
) -> ServerPrincipalV1:
    if principal is not None and principal.authenticated:
        return principal
    if config.full_multilingual_v2_enabled:
        raise PermissionError("authenticated MCP server principal is required")
    # Preserve the historical non-production/V1 seam. Production V2 can never use it.
    return principal_from_claims(None)


async def _handle_search_evidence(
    engine: KnowledgeEngine,
    args: dict[str, Any],
    config: ServerConfig,
    principal: ServerPrincipalV1,
) -> list[MCPContent]:
    """Execute the shared strict ranked/exhaustive evidence contract."""
    request = EvidenceSearchRequest.model_validate(args)
    response = await EvidenceRetrievalApplicationService(engine, config).execute(request, principal)
    return [
        types.TextContent(
            type="text",
            text=response.model_dump_json(indent=2),
        )
    ]


async def _handle_query_structured(
    engine: KnowledgeEngine,
    args: dict[str, Any],
    config: ServerConfig,
    principal: ServerPrincipalV1,
) -> list[MCPContent]:
    """Execute the same strict structured application contract used by HTTP."""
    request = StructuredRetrievalRequest.model_validate(args)
    response = await StructuredRetrievalApplicationService(engine, config).execute(
        request, principal
    )
    return [types.TextContent(type="text", text=response.model_dump_json(indent=2))]


async def _handle_final_qa_v2(
    engine: KnowledgeEngine,
    args: dict[str, Any],
    config: ServerConfig,
    principal: ServerPrincipalV1,
) -> list[MCPContent]:
    request = FinalQAV2RequestBody.model_validate(args)
    response = await FinalQAV2ApplicationService(engine, config).execute(
        request.notebook_id, request, principal
    )
    return [types.TextContent(type="text", text=response.model_dump_json(indent=2))]


async def _handle_get_capabilities(
    engine: KnowledgeEngine, args: dict[str, Any], config: ServerConfig
) -> list[MCPContent]:
    request = CapabilityDiscoveryRequest.model_validate(args)
    response = CapabilityDiscoveryService(engine, config).document(request)
    return [types.TextContent(type="text", text=response.model_dump_json(indent=2))]


def _delivery_service(engine: KnowledgeEngine, config: ServerConfig):  # type: ignore[no-untyped-def]
    return build_delivery_service(engine, config)


async def _execute_delivery_tool(
    engine: KnowledgeEngine,
    name: str,
    args: dict[str, Any],
    config: ServerConfig,
    principal: ServerPrincipalV1,
) -> list[MCPContent]:
    try:
        if name == "get_document":
            return await _handle_get_document(engine, args, config, principal)
        if name == "get_document_chunk":
            return await _handle_get_document_chunk(engine, args, config, principal)
        if type(engine) is KnowledgeEngine:
            notebook_id = _parse_uuid(args.get("notebook_id"), "notebook_id")
            await CentralAuthorizationServiceV1(engine).authorize_notebook(
                principal, notebook_id, AuthorizationOperationV1.DELIVER
            )
        if name == "get_asset":
            return await _handle_get_asset(engine, args, config)
        return await _handle_get_image_analysis(engine, args, config)
    except DeliveryAuthorizationError as error:
        raise DeliveryAuthorizationError("Resource access is forbidden") from error
    except DeliveryCursorExpiredError as error:
        raise DeliveryCursorExpiredError(
            "Continuation cursor expired; restart the traversal"
        ) from error
    except DeliveryCursorConflictError as error:
        raise DeliveryCursorConflictError(
            "Continuation cursor conflicts with this traversal; restart it"
        ) from error
    except DeliveryCursorError as error:
        raise DeliveryCursorError("Continuation cursor is invalid or stale") from error
    except DeliveryLimitExceededError as error:
        raise DeliveryLimitExceededError("Delivery limit exceeded") from error
    except IntegrityError as error:
        raise IntegrityError("Delivered resource failed integrity validation") from error


def _optional_positive_int(args: dict[str, Any], name: str) -> int | None:
    value = args.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractValidationError(f"Parameter '{name}' must be a positive integer")
    return int(value)


def _optional_uuid(args: dict[str, Any], name: str) -> UUID | None:
    value = args.get(name)
    return None if value is None else _parse_uuid(value, name)


async def _handle_get_document(
    engine: KnowledgeEngine,
    args: dict[str, Any],
    config: ServerConfig,
    principal: ServerPrincipalV1,
) -> list[MCPContent]:
    document_id = _parse_uuid(args.get("document_id"), "document_id")
    version_id = _parse_uuid(args.get("version_id"), "version_id")
    notebook_id_raw = args.get("notebook_id")
    requested_notebook_id = (
        None if notebook_id_raw is None else _parse_uuid(notebook_id_raw, "notebook_id")
    )
    if requested_notebook_id is not None and type(engine) is not KnowledgeEngine:
        notebook_id = requested_notebook_id
    else:
        resolver = StorageDocumentScopeResolverV1(
            engine.storage, StorageSourceAssociationReaderV1(engine.storage)
        )
        resolved_scope = await resolver.resolve_document_scope(
            principal, document_id, version_id, requested_notebook_id
        )
        notebook_id = resolved_scope.notebook_id

    mode = args.get("mode", "blocks")
    if mode not in {"blocks", "original"}:
        raise ContractValidationError("Parameter 'mode' must be 'blocks' or 'original'")
    cursor = args.get("cursor")
    if cursor is not None and not isinstance(cursor, str):
        raise ContractValidationError("Parameter 'cursor' must be a string")
    request = DeliveryRequest(
        notebook_id=notebook_id,
        document_id=document_id,
        version_id=version_id,
        view=DeliveryView(mode),
        cursor=cursor,
        max_bytes=_optional_positive_int(args, "max_bytes"),
        max_items=_optional_positive_int(args, "max_items"),
    )
    service = _delivery_service(engine, config)
    if mode == "original":
        result = await service.get_original_document(request)
        return [
            types.EmbeddedResource(
                type="resource",
                resource=types.BlobResourceContents(
                    uri=AnyUrl(f"mnemo://documents/{document_id}/versions/{version_id}"),
                    mimeType=result.media_type,
                    blob=base64.b64encode(result.content).decode("ascii"),
                    _meta={
                        "completeness": result.completeness.value,
                        "contentHash": result.content_hash,
                        "nextCursor": result.next_cursor,
                        "totalBytes": result.total_byte_size,
                    },
                ),
            )
        ]
    selector_raw = args.get("selector")
    selector_body: DocumentExpansionRequestBody | None = None
    if selector_raw is not None:
        if mode != "blocks":
            raise ContractValidationError("selector is supported only in blocks mode")
        try:
            selector_body = DocumentExpansionRequestBody.model_validate(
                {
                    "selector": selector_raw,
                    "cursor": cursor,
                    "max_bytes": request.max_bytes,
                    "max_items": request.max_items,
                }
            )
        except ValueError as error:
            raise ContractValidationError("Parameter 'selector' is invalid") from error
    result = (
        await service.expand_document_v2(
            selector_body.to_core(
                notebook_id=notebook_id,
                document_id=document_id,
                version_id=version_id,
            )
        )
        if selector_body is not None
        else await service.expand_document(request)
    )
    data = delivery_response_body(result).model_dump(mode="json")
    data.update(
        _contract_fields(
            "get_document",
            completeness=result.completeness.value,
            coverage={
                "document_version": "ordered_blocks",
                "selector": selector_raw,
                "selection_semantics": "exact_physical_order",
            },
            limits={
                "max_bytes": request.max_bytes,
                "max_items": request.max_items,
                "usage": data["usage"],
            },
            next_cursor=result.next_cursor,
            omissions=list(result.omissions),
            recommended_next_actions=(
                [
                    _next_action(
                        "get_document",
                        "Continue ordered traversal; do not answer a complete/end request yet.",
                        "notebook_id",
                        "document_id",
                        "version_id",
                        *(["selector"] if selector_body is not None else []),
                        "next_cursor",
                        pass_cursor_unchanged=True,
                        stop_condition="next_cursor is null or requested selector is complete",
                    )
                ]
                if result.next_cursor is not None
                else []
            ),
        )
    )
    return [types.TextContent(type="text", text=json.dumps(data, sort_keys=True))]


async def _handle_get_document_chunk(
    engine: KnowledgeEngine,
    args: dict[str, Any],
    config: ServerConfig,
    principal: ServerPrincipalV1,
) -> list[MCPContent]:
    chunk_id = args.get("chunk_id")
    if not isinstance(chunk_id, str) or len(chunk_id) != 64:
        raise ContractValidationError("Parameter 'chunk_id' must be a SHA-256 identity")
    document_id = _parse_uuid(args.get("document_id"), "document_id")
    version_id = _parse_uuid(args.get("version_id"), "version_id")
    notebook_id_raw = args.get("notebook_id")
    requested_notebook_id = (
        None if notebook_id_raw is None else _parse_uuid(notebook_id_raw, "notebook_id")
    )
    if requested_notebook_id is not None and type(engine) is not KnowledgeEngine:
        notebook_id = requested_notebook_id
    else:
        resolver = StorageDocumentScopeResolverV1(
            engine.storage, StorageSourceAssociationReaderV1(engine.storage)
        )
        resolved_scope = await resolver.resolve_document_scope(
            principal, document_id, version_id, requested_notebook_id
        )
        notebook_id = resolved_scope.notebook_id

    result = await _delivery_service(engine, config).get_document_chunk(
        notebook_id=notebook_id,
        document_id=document_id,
        version_id=version_id,
        chunk_id=chunk_id,
    )
    data = delivery_response_body(result).model_dump(mode="json")
    data.update(
        _contract_fields(
            "get_document_chunk",
            completeness=result.completeness.value,
            coverage={"exact_chunk": chunk_id},
            limits={"usage": data["usage"]},
            omissions=list(result.omissions),
            recommended_next_actions=[
                _next_action(
                    "get_document",
                    "Retrieve ordered surrounding or complete document content.",
                    "notebook_id",
                    "document_id",
                    "version_id",
                )
            ],
        )
    )
    return [types.TextContent(type="text", text=json.dumps(data, sort_keys=True))]


def _is_safe_complete_image_content(media_type: str, content: bytes) -> bool:
    """Allow MCP ImageContent only for recognizable complete raster envelopes."""
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP",
    }
    return signatures.get(media_type.lower(), False)


async def _handle_get_asset(
    engine: KnowledgeEngine, args: dict[str, Any], config: ServerConfig
) -> list[MCPContent]:
    notebook_id = _parse_uuid(args.get("notebook_id"), "notebook_id")
    occurrence_id = _optional_uuid(args, "occurrence_id")
    cursor = args.get("cursor")
    if cursor is not None and not isinstance(cursor, str):
        raise ContractValidationError("Parameter 'cursor' must be a string")
    service = _delivery_service(engine, config)
    if occurrence_id is not None:
        result = await service.get_asset(
            notebook_id=notebook_id,
            occurrence_id=occurrence_id,
            cursor=cursor,
            max_bytes=_optional_positive_int(args, "max_bytes"),
        )
        encoded = base64.b64encode(result.content).decode("ascii")
        resource_metadata = {
            "completeness": result.completeness.value,
            "nextCursor": result.next_cursor,
            "contentHash": result.content_hash,
            "totalBytes": result.total_byte_size,
            "rangeStart": result.range_start,
            "rangeEnd": result.range_start + len(result.content),
            "notebookId": str(result.attribution.notebook_id),
            "sourceId": str(result.attribution.source_id),
            "documentId": str(result.attribution.document_id),
            "versionId": str(result.attribution.version_id),
            "assetId": str(result.attribution.asset_id),
            "occurrenceId": str(result.attribution.occurrence_id),
        }
        if (
            _is_safe_complete_image_content(result.media_type, result.content)
            and result.completeness is DeliveryCompleteness.COMPLETE
        ):
            return [
                types.ImageContent(
                    type="image",
                    data=encoded,
                    mimeType=result.media_type,
                    _meta=resource_metadata,
                )
            ]
        return [
            types.EmbeddedResource(
                type="resource",
                resource=types.BlobResourceContents(
                    uri=AnyUrl(f"mnemo://asset-occurrences/{occurrence_id}"),
                    mimeType=(
                        "application/octet-stream"
                        if result.media_type.startswith("image/")
                        else result.media_type
                    ),
                    blob=encoded,
                    _meta={**resource_metadata, "originalMediaType": result.media_type},
                ),
            )
        ]
    document_id = _parse_uuid(args.get("document_id"), "document_id")
    version_id = _parse_uuid(args.get("version_id"), "version_id")
    result = await service.list_assets(
        notebook_id=notebook_id,
        document_id=document_id,
        version_id=version_id,
        cursor=cursor,
        limit=_optional_positive_int(args, "limit"),
    )
    data = delivery_response_body(result).model_dump(mode="json")
    data.update(
        _contract_fields(
            "get_asset",
            completeness=result.completeness.value,
            coverage={"asset_occurrences": "known_document_version"},
            limits={"limit": args.get("limit"), "usage": data["usage"]},
            next_cursor=result.next_cursor,
            omissions=list(result.omissions),
            recommended_next_actions=(
                [
                    _next_action(
                        "get_asset",
                        "Continue the bounded occurrence inventory.",
                        "notebook_id",
                        "document_id",
                        "version_id",
                        "next_cursor",
                        pass_cursor_unchanged=True,
                        stop_condition="next_cursor is null",
                    )
                ]
                if result.next_cursor is not None
                else [
                    _next_action(
                        "get_image_analysis",
                        "Retrieve existing OCR/Vision derivations for a selected occurrence.",
                        "notebook_id",
                        "occurrence_id",
                    )
                ]
            ),
        )
    )
    return [types.TextContent(type="text", text=json.dumps(data, sort_keys=True))]


async def _handle_get_image_analysis(
    engine: KnowledgeEngine, args: dict[str, Any], config: ServerConfig
) -> list[MCPContent]:
    notebook_id = _parse_uuid(args.get("notebook_id"), "notebook_id")
    occurrence_id = _parse_uuid(args.get("occurrence_id"), "occurrence_id")
    ocr_id = _optional_uuid(args, "ocr_derivation_id")
    vision_id = _optional_uuid(args, "vision_derivation_id")
    if "selection" not in args and "modalities" not in args and "profile" not in args:
        result = await _delivery_service(engine, config).get_image_analysis(
            notebook_id=notebook_id,
            occurrence_id=occurrence_id,
            ocr_derivation_id=ocr_id,
            vision_derivation_id=vision_id,
        )
    else:
        try:
            selection = AssetAnalysisSelection(args.get("selection", "explicit"))
            raw_modalities = args.get("modalities", ["ocr", "vision"])
            if not isinstance(raw_modalities, list):
                raise ValueError("modalities")
            selector = AssetAnalysisSelector(
                selection=selection,
                modalities=tuple(AssetAnalysisModality(item) for item in raw_modalities),
                derivation_ids=tuple(item for item in (ocr_id, vision_id) if item is not None),
                profile=args.get("profile"),
            )
        except (TypeError, ValueError) as error:
            raise ContractValidationError("analysis selection is invalid") from error
        result = await _delivery_service(engine, config).get_image_analysis_v2(
            notebook_id=notebook_id, occurrence_id=occurrence_id, selector=selector
        )
    data = delivery_response_body(result).model_dump(mode="json")
    data.update(
        _contract_fields(
            "get_image_analysis",
            completeness=result.completeness.value,
            coverage={"derived_analysis": "requested_occurrence"},
            limits={"usage": data["usage"]},
            omissions=list(result.omissions),
            recommended_next_actions=[
                _next_action(
                    "get_asset",
                    "Retrieve the original image; derived analysis is not source truth.",
                    "notebook_id",
                    "occurrence_id",
                )
            ],
        )
    )
    return [types.TextContent(type="text", text=json.dumps(data, sort_keys=True))]


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
        **_contract_fields(
            "query_notebook",
            completeness="bounded",
            coverage={"representations": ["canonical_text"], "exhaustive": False},
            limits={"top_k": top_k},
            omissions=["exhaustive coverage is not evaluated by V1 query"],
            recommended_next_actions=[
                _next_action(
                    "search_all_notebooks",
                    "Discover document/version IDs before exact traversal when they are "
                    "not present.",
                    "notebook_id",
                )
            ],
        ),
    }

    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


async def _handle_search_all_notebooks(
    engine: KnowledgeEngine,
    args: dict[str, Any],
) -> list[MCPContent]:
    """Handle search_all_notebooks tool invocation."""
    query = args.get("query")
    top_k_raw = args.get("top_k") if "top_k" in args else args.get("limit", 10)
    top_k = top_k_raw
    notebook_id_raw = args.get("notebook_id")

    if not isinstance(query, str) or not query.strip():
        raise ContractValidationError("Parameter 'query' must be a non-empty string")

    if not isinstance(top_k, int) or top_k < 1 or top_k > 100:
        raise ContractValidationError(
            "Parameter 'top_k' (or 'limit') must be an integer between 1 and 100"
        )

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
                "notebook_id": str(r.notebook_id) if r.notebook_id is not None else None,
                "document_id": str(r.document_id),
                "version_id": str(r.version_id),
                "text": r.text,
                "score": r.score,
                "rank": r.rank,
                "retrieval_mode": r.retrieval_mode,
                "heading_path": r.heading_path,
                "page_number": r.page_number,
                "page_start": r.page_start,
                "page_end": r.page_end,
                "metadata": r.metadata,
            }
            for r in resp.results
        ],
        "total": resp.total,
        "latency_ms": resp.latency_ms,
        **_contract_fields(
            "search_all_notebooks",
            completeness="bounded",
            coverage={"representations": ["canonical_text"], "exhaustive": False},
            limits={"top_k": top_k, "returned": len(resp.results)},
            omissions=["ranked top-k does not enumerate every matching result"],
            recommended_next_actions=[
                _next_action(
                    "get_document",
                    "Retrieve exact, ordered, first/last/final, or complete document content.",
                    "notebook_id",
                    "document_id",
                    "version_id",
                ),
                _next_action(
                    "get_document_chunk",
                    "Retrieve one exact returned canonical chunk.",
                    "notebook_id",
                    "document_id",
                    "version_id",
                    "chunk_id",
                ),
            ],
        ),
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
        **_contract_fields(
            "list_notebooks",
            completeness="truncated" if page.next_cursor is not None else "complete",
            coverage={"authorized_notebooks": "inventory_page"},
            limits={"limit": limit, "returned": len(notebooks_list)},
            next_cursor=page.next_cursor,
            recommended_next_actions=(
                [
                    _next_action(
                        "list_notebooks",
                        "Continue the notebook inventory.",
                        "next_cursor",
                        pass_cursor_unchanged=True,
                        stop_condition="next_cursor is null",
                    )
                ]
                if page.next_cursor is not None
                else []
            ),
        ),
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
        **_contract_fields(
            "get_notebook_summary",
            completeness="unknown",
            coverage={"summary": status_str, "source_count_returned": len(sources)},
            limits={"insight_scan": 100, "source_scan": 100},
            omissions=["summary coverage is not exact document coverage"],
            recommended_next_actions=[
                _next_action(
                    "search_all_notebooks",
                    "Find supporting canonical evidence or document identifiers.",
                    "notebook_id",
                )
            ],
        ),
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
        **_contract_fields(
            "get_source_insights",
            completeness="bounded",
            coverage={"persisted_insights": "bounded_inventory"},
            limits={"limit": limit, "returned": len(matching_insights)},
            omissions=["source text is not exhaustively searched"],
        ),
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
        **_contract_fields(
            "get_timeline",
            completeness="bounded",
            coverage={"persisted_timeline_events": "bounded_inventory"},
            limits={"limit": limit, "returned": len(sliced_events)},
            omissions=["source text is not exhaustively interpreted"],
        ),
    }

    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]
