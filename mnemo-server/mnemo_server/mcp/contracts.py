"""Machine-facing MCP contracts frozen by ADR-0073.

This module contains transport metadata only.  A definition in the reserved
catalog is not evidence that its backing application service is callable.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import mcp.types as types

from mnemo_server.schemas.capabilities_v2 import CapabilityDiscoveryRequest, CapabilityDocument
from mnemo_server.schemas.final_qa_v2 import FinalQAV2RequestBody
from mnemo_server.schemas.structured_v2 import StructuredRetrievalRequest

CONTRACT_VERSION = "phase8.5-mcp-v1"


def _description(*sections: tuple[str, str]) -> str:
    return "\n\n".join(f"{heading}: {body}" for heading, body in sections)


TOOL_DESCRIPTIONS: dict[str, str] = {
    "list_notebooks": _description(
        ("Purpose", "List a bounded page of authorized notebooks and their IDs."),
        ("Use when", "You need to discover notebook scope before another call."),
        ("Do not use when", "You need to search document content or read a document."),
        ("Continuation", "If next_cursor is present, pass it unchanged to this tool."),
        ("Next", "Use a returned notebook_id with notebook-scoped tools."),
    ),
    "get_notebook_summary": _description(
        ("Purpose", "Return a coarse, bounded summary for one known notebook."),
        ("Use when", "A notebook overview is sufficient."),
        (
            "Do not use when",
            "Exact evidence, complete traversal, exhaustive results, or arithmetic is required.",
        ),
        ("Completeness", "A summary is not proof of complete document or corpus coverage."),
        ("Next", "Use search for relevant evidence or get_document for exact content."),
    ),
    "search_all_notebooks": _description(
        (
            "Purpose",
            "Run bounded ranked discovery over canonical text and return relevant chunks plus "
            "notebook_id, document_id, version_id, and chunk_id for follow-up calls.",
        ),
        ("Use when", "You need to find relevant text, a document, or its exact identifiers."),
        (
            "Do not use when",
            "The request asks for all/every matches, a count, exact page/range/first/last/final "
            "content, full sequential reading, structured arithmetic, or semantic image search. "
            "Top-k results are never exhaustive.",
        ),
        (
            "Next",
            "For an exact passage, first/last page, or complete document, pass returned IDs to "
            "get_document; use get_document_chunk only when its exact chunk_id is sufficient.",
        ),
        ("Completeness", "Always bounded ranked discovery, not complete enumeration."),
    ),
    "query_notebook": _description(
        (
            "Purpose",
            "Run frozen V1 bounded text retrieval and optional synthesis in one known notebook.",
        ),
        ("Use when", "A relevant top-k canonical-text answer in one notebook is sufficient."),
        (
            "Do not use when",
            "Exact traversal, exhaustive enumeration, structured arithmetic, multimodal evidence, "
            "or persisted Final-QA V2 is required.",
        ),
        ("Completeness", "Bounded ranked V1 evidence; it has no exhaustive guarantee."),
        ("Next", "Use get_document with cited document/version IDs for exact source traversal."),
    ),
    "get_source_insights": _description(
        ("Purpose", "Return bounded persisted insights for one already-known source_id."),
        ("Use when", "Persisted facts, summaries, entities, or claims are requested."),
        ("Do not use when", "Searching source text or claiming complete source coverage."),
        ("Completeness", "Applies only to the bounded persisted-insight inventory."),
        ("Next", "Use exact document delivery for original supporting content."),
    ),
    "get_timeline": _description(
        ("Purpose", "Return bounded persisted chronological events in a known notebook."),
        ("Use when", "The persisted notebook timeline is requested."),
        ("Do not use when", "Complete document traversal or exhaustive fact extraction is needed."),
        ("Completeness", "Covers persisted timeline records, not every event in source text."),
        ("Next", "Retrieve exact cited document content when needed."),
    ),
    "get_document": _description(
        (
            "Purpose",
            "Retrieve or traverse one exact authorized document version in source order, "
            "or deliver its bounded original resource.",
        ),
        (
            "Use when",
            "The document/version IDs are known and the request needs exact content, "
            "ordered reading, the complete document, an exact page/slide/sheet/block/chunk/"
            "section range, adjacent material, or the first/last/final passage. Select exactly "
            "one selector; positional selectors never use semantic ranking.",
        ),
        (
            "Do not use when",
            "The relevant document is not known yet, or semantic/exhaustive matching "
            "across documents is required. Discover IDs with search first.",
        ),
        (
            "Continuation",
            "cursor is opaque continuation state, not a page number. If completeness is "
            "truncated and next_cursor is non-null, call get_document again with the same "
            "IDs/mode/bounds and pass next_cursor unchanged. For complete/end requests, do "
            "not answer until next_cursor is null or the requested selector is complete. Keep "
            "the selector and bounds unchanged while continuing.",
        ),
        (
            "Authorization",
            "Omitted notebook_id is resolved only when unambiguous; ambiguity fails closed.",
        ),
    ),
    "get_document_chunk": _description(
        ("Purpose", "Return one exact authorized canonical chunk and its provenance/ancestry."),
        ("Use when", "A 64-character chunk_id and its document/version IDs are already known."),
        ("Do not use when", "Searching for content or retrieving the whole document."),
        ("Completeness", "Complete only for the single requested chunk resource."),
        ("Next", "Use search to discover IDs; use get_document for ordered surrounding content."),
    ),
    "get_asset": _description(
        (
            "Purpose",
            "List bounded authorized asset occurrences in a known document/version, or deliver the "
            "original bytes for one known occurrence_id.",
        ),
        ("Use when", "Document/version or occurrence identity is already known."),
        (
            "Do not use when",
            "Finding an image from a natural-language description or requesting OCR/Vision "
            "meaning. This is direct asset inventory/delivery, not semantic image search.",
        ),
        (
            "Continuation",
            "For inventory, pass next_cursor unchanged to this tool until null when complete "
            "inventory is required. For a truncated binary range, pass next_cursor unchanged "
            "until null. Only a complete image is emitted as ImageContent; partial media is an "
            "opaque range resource with original MIME, hash, length, and provenance metadata.",
        ),
        (
            "Next",
            "Inventory items include authorized derivation descriptors. Pass a returned "
            "occurrence_id to get_image_analysis and use explicit IDs, latest_ready, or all as "
            "appropriate.",
        ),
    ),
    "get_image_analysis": _description(
        (
            "Purpose",
            "Return existing bounded OCR and/or Vision derivations for one authorized "
            "image occurrence.",
        ),
        (
            "Use when",
            "A concrete occurrence_id is known and existing derived interpretation is required; "
            "use selection=latest_ready when inventory IDs should be resolved deterministically.",
        ),
        (
            "Do not use when",
            "Retrieving original bytes, discovering an image by description, or requesting a new "
            "provider inference. Derived analysis is not original source truth.",
        ),
        (
            "Next",
            "Use get_asset for the original image; preserve occurrence and derivation provenance.",
        ),
        (
            "Completeness",
            "Missing analysis means unavailable, not that the image contains nothing.",
        ),
    ),
    "search_evidence": _description(
        ("Purpose", "Search authorized typed evidence using explicit ranked or exhaustive mode."),
        (
            "Use when",
            "Use ranked for bounded relevance discovery. Use exhaustive for all/every lexical "
            "match across the declared scope and follow next_cursor until null. For deterministic "
            "multi-document comparison, provide explicit partition_document_ids; each partition "
            "retains its own provenance/completeness while one aggregate CursorCodecV2 cursor "
            "continues the stable partition traversal.",
        ),
        (
            "Do not use when",
            "Exact document traversal, structured arithmetic, direct original binary delivery, "
            "or autonomous planning is required. Semantic image discovery is supported only via "
            "an advertised ready OCR, Vision, asset-metadata, or visual-vector representation.",
        ),
        (
            "Continuation",
            "Only exhaustive mode accepts a cursor. If completeness=truncated and next_cursor is "
            "present, call search_evidence again with the identical request and cursor unchanged.",
        ),
        (
            "Completeness",
            "Ranked results are bounded/unknown, never exhaustive. Exhaustive is complete only "
            "after every requested available representation terminates; unavailable requested "
            "representations make the result partial.",
        ),
        (
            "Current representations",
            "canonical_text, asset_metadata, ocr_text, vision_analysis, and visual_vector are "
            "typed representations. Each is searched only when its active generation/provider "
            "is ready; unavailable coverage is reported explicitly. Use asset_metadata/OCR/"
            "vision for image evidence and then get_asset or get_image_analysis for delivery. "
            "visual_vector is used only in a compatible shared vector space.",
        ),
        ("Next", "Use returned document/chunk IDs for exact delivery; preserve provenance."),
    ),
    "query_structured": _description(
        (
            "Purpose",
            "Discover exact-version table datasets or execute allowlisted typed filters, "
            "ranges, sorting, grouping, COUNT/AVG/SUM/MIN/MAX, compatible union, and "
            "explicit equality join with row/cell provenance.",
        ),
        (
            "Use when",
            "The user asks for CPI > 8.9, every row in a numeric range, counts, averages, "
            "sorting, grouping, or an exact table/dataset comparison. For comparing already "
            "typed values across records, use the deterministic comparison primitive exposed "
            "by this structured service; never ask an LLM to calculate it. Call operation=describe "
            "first when dataset IDs or field types are unknown.",
        ),
        (
            "Do not use when",
            "Do not use for semantic document relevance, arbitrary SQL, approximate or fuzzy "
            "joins, image discovery/delivery, or OCR/Vision analysis. Use search_evidence for "
            "ranked/exhaustive text evidence and get_asset/get_image_analysis for known images.",
        ),
        (
            "Completeness and continuation",
            "Results are bound to exact versions and active generations. If completeness is "
            "truncated and next_cursor is non-null, repeat this same request with the cursor "
            "unchanged until next_cursor is null. unavailable/partial is not an empty dataset.",
        ),
        (
            "Security",
            "Only declared schema fields/operators are accepted; no SQL string or expression "
            "input exists. Unknown or unauthorized datasets fail closed.",
        ),
    ),
    "run_final_qa_v2": _description(
        ("Purpose", "Execute or replay a persisted citation-compliant Final-QA V2 answer."),
        ("Use when", "A grounded immutable answer over authorized typed V2 evidence is required."),
        ("Do not use when", "Evidence is not authorized or V1 query semantics are required."),
        (
            "Workflow",
            "First retrieve authorized typed evidence with search_evidence, get_document, "
            "query_structured, get_asset, or get_image_analysis as the question requires; "
            "then pass the exact governed evidence request here.",
        ),
        (
            "Replay",
            "Repeat the identical request to replay the immutable snapshot without generation.",
        ),
    ),
    "get_capabilities": _description(
        (
            "Purpose",
            "Return the deterministic machine-readable Phase 8.5 runtime capability snapshot.",
        ),
        (
            "Use when",
            "Before selecting advanced, exact, exhaustive, structured, multimodal, "
            "multilingual, asset, or Final-QA paths; or when explaining why one is unavailable.",
        ),
        (
            "Truth",
            "States come from Phase85RuntimeV1. Declared, configured, buildable, ready, "
            "active, exposed, verified, and certified are distinct; code presence never "
            "implies support.",
        ),
        (
            "Workflow",
            "Read task_guidance and each capability's transports, dependencies, generation, "
            "profiles, limits, unavailable_reason, and next_actions. Then invoke only a "
            "callable tool.",
        ),
        (
            "Do not use when",
            "Authorizing data access, enumerating documents, or inferring verification or "
            "certification from exposure.",
        ),
    ),
}


_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tool", "reason"],
    "properties": {
        "tool": {"type": "string"},
        "reason": {"type": "string"},
        "arguments_from_result": {"type": "array", "items": {"type": "string"}},
        "pass_cursor_unchanged": {"type": "boolean"},
        "stop_condition": {"type": "string"},
    },
    "additionalProperties": False,
}


def output_schema(*required_payload: str) -> dict[str, Any]:
    """Build the additive structured-output schema shared by retained tools."""
    return {
        "type": "object",
        "required": [
            *required_payload,
            "schema_version",
            "operation",
            "request_id",
            "completeness",
            "coverage",
            "limits",
            "recommended_next_actions",
        ],
        "properties": {
            **{name: {} for name in required_payload},
            "schema_version": {"type": "string"},
            "operation": {"type": "string"},
            "request_id": {"type": "string"},
            "completeness": {
                "enum": [
                    "complete",
                    "partial",
                    "bounded",
                    "truncated",
                    "no_match",
                    "empty",
                    "unavailable",
                    "failed",
                    "unknown",
                ]
            },
            "coverage": {"type": "object"},
            "omissions": {"type": "array", "items": {"type": "string"}},
            "limits": {"type": "object"},
            "next_cursor": {"type": ["string", "null"]},
            "partitions": {"type": "array"},
            "recommended_next_actions": {"type": "array", "items": _ACTION_SCHEMA},
        },
        "additionalProperties": True,
    }


OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "query_notebook": output_schema("answer", "citations", "retrieval_metadata"),
    "search_all_notebooks": output_schema("results", "total", "latency_ms"),
    "list_notebooks": output_schema("notebooks", "total", "next_cursor"),
    "get_notebook_summary": output_schema("notebook_id", "summary", "sources"),
    "get_source_insights": output_schema("source_id", "notebook_id", "insights"),
    "get_timeline": output_schema("notebook_id", "events"),
    "get_document": output_schema(),
    "get_document_chunk": output_schema("resource_kind", "items"),
    "get_asset": output_schema(),
    "get_image_analysis": output_schema("resource_kind", "items"),
    "query_structured": output_schema("items", "structured", "snapshot_identity"),
}


def apply_retained_contracts(tools: Iterable[types.Tool]) -> list[types.Tool]:
    """Return definitions enriched without changing names or input wire semantics."""
    enriched: list[types.Tool] = []
    for tool in tools:
        enriched.append(
            tool.model_copy(
                update={
                    "description": TOOL_DESCRIPTIONS[tool.name],
                    "outputSchema": OUTPUT_SCHEMAS[tool.name],
                    "annotations": types.ToolAnnotations(readOnlyHint=True),
                }
            )
        )
    return enriched


def reserved_tool_names() -> tuple[str, ...]:
    """Return frozen additive names that are intentionally not advertised yet."""
    return ()


SEARCH_EVIDENCE_TOOL = types.Tool(
    name="search_evidence",
    description=TOOL_DESCRIPTIONS["search_evidence"],
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "mode": {"enum": ["ranked", "exhaustive"]},
            "scope": {
                "type": "object",
                "properties": {
                    "notebook_id": {"type": "string", "format": "uuid"},
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "uniqueItems": True,
                        "maxItems": 200,
                    },
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "uniqueItems": True,
                        "maxItems": 200,
                    },
                    "version_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "uniqueItems": True,
                        "maxItems": 200,
                    },
                },
                "required": ["notebook_id"],
                "additionalProperties": False,
            },
            "representations": {
                "type": "array",
                "items": {
                    "enum": [
                        "canonical_text",
                        "title_metadata",
                        "ocr_text",
                        "vision_analysis",
                        "visual_vector",
                        "asset_metadata",
                        "multilingual_text",
                        "positional_metadata",
                    ]
                },
                "minItems": 1,
                "uniqueItems": True,
            },
            "cursor": {"type": "string"},
            "candidate_budget": {"type": "integer", "minimum": 1, "maximum": 1000},
            "evidence_budget": {"type": "integer", "minimum": 1, "maximum": 200},
            "max_serialized_bytes": {"type": "integer", "minimum": 256, "maximum": 10000000},
            "max_content_characters": {"type": "integer", "minimum": 1, "maximum": 2000000},
            "positional_scope": {
                "type": "object",
                "properties": {
                    "page_start": {"type": "integer", "minimum": 1},
                    "page_end": {"type": "integer", "minimum": 1},
                    "section_indexes": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0},
                        "uniqueItems": True,
                    },
                    "heading_prefix": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "additionalProperties": False,
            },
            "expansion_policy": {"enum": ["none", "adjacent", "parent_and_adjacent"]},
            "deduplication_policy": {"enum": ["authoritative_identity"]},
            "partition_document_ids": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
                "uniqueItems": True,
                "maxItems": 100,
                "description": (
                    "Explicit authorized document partitions for deterministic comparison."
                ),
            },
            "partition_cursors": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": "Opaque CursorCodecV2 continuation cursor per document partition.",
            },
            "all_authorized_documents": {
                "type": "boolean",
                "description": "Enumerate every document authorized in the notebook scope.",
            },
        },
        "required": ["query", "mode", "scope", "representations"],
        "additionalProperties": False,
    },
    outputSchema=output_schema("items"),
    annotations=types.ToolAnnotations(readOnlyHint=True),
)


QUERY_STRUCTURED_TOOL = types.Tool(
    name="query_structured",
    description=TOOL_DESCRIPTIONS["query_structured"],
    inputSchema=StructuredRetrievalRequest.model_json_schema(),
    outputSchema=OUTPUT_SCHEMAS["query_structured"],
    annotations=types.ToolAnnotations(readOnlyHint=True),
)


FINAL_QA_V2_TOOL = types.Tool(
    name="run_final_qa_v2",
    description=TOOL_DESCRIPTIONS["run_final_qa_v2"],
    inputSchema=FinalQAV2RequestBody.model_json_schema(),
    outputSchema=output_schema("answer", "citations"),
    annotations=types.ToolAnnotations(readOnlyHint=False),
)

CAPABILITIES_TOOL = types.Tool(
    name="get_capabilities",
    description=TOOL_DESCRIPTIONS["get_capabilities"],
    inputSchema=CapabilityDiscoveryRequest.model_json_schema(),
    outputSchema=CapabilityDocument.model_json_schema(),
    annotations=types.ToolAnnotations(readOnlyHint=True),
)

RESERVED_TOOL_DEFINITIONS: tuple[types.Tool, ...] = ()
