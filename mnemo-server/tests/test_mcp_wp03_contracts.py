"""Focused WP-03 MCP discoverability and structured-contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import mcp.types as types
import pytest
from mnemo_server.mcp.contracts import (
    CONTRACT_VERSION,
    RESERVED_TOOL_DEFINITIONS,
    SEARCH_EVIDENCE_TOOL,
    reserved_tool_names,
)
from mnemo_server.mcp.tools import get_mcp_tools, structured_content_for
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest

_RETAINED_REQUIRED_INPUTS = {
    "query_notebook": ["notebook_id", "question"],
    "search_all_notebooks": ["query"],
    "list_notebooks": [],
    "get_notebook_summary": ["notebook_id"],
    "get_source_insights": ["source_id"],
    "get_timeline": ["notebook_id"],
    "get_document": ["document_id", "version_id"],
    "get_document_chunk": ["document_id", "version_id", "chunk_id"],
    "get_asset": ["notebook_id"],
    "get_image_analysis": ["notebook_id", "occurrence_id"],
}


def _tools_by_name() -> dict[str, types.Tool]:
    return {tool.name: tool for tool in get_mcp_tools()}


def _governance_contract() -> dict[str, object]:
    path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "governance"
        / "contracts"
        / "phase8_5_mcp_contracts.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_retained_tools_keep_names_and_required_inputs() -> None:
    tools = _tools_by_name()
    assert list(tools)[: len(_RETAINED_REQUIRED_INPUTS)] == list(_RETAINED_REQUIRED_INPUTS)
    assert list(tools)[len(_RETAINED_REQUIRED_INPUTS) :] == [
        "search_evidence",
        "query_structured",
        "run_final_qa_v2",
        "get_capabilities",
    ]
    assert {
        name: tools[name].inputSchema.get("required", []) for name in _RETAINED_REQUIRED_INPUTS
    } == _RETAINED_REQUIRED_INPUTS


def test_reserved_contracts_are_frozen_but_not_falsely_advertised() -> None:
    retained_names = set(_tools_by_name())
    assert tuple(tool.name for tool in RESERVED_TOOL_DEFINITIONS) == reserved_tool_names()
    assert retained_names.isdisjoint(reserved_tool_names())
    for tool in RESERVED_TOOL_DEFINITIONS:
        assert "Advertise only after" in (tool.description or "")
        assert tool.outputSchema is not None


def test_runtime_catalog_matches_governance_advertisement() -> None:
    contract = _governance_contract()
    governed_tools = contract["tools"]
    assert isinstance(governed_tools, list)
    advertised = [item["name"] for item in governed_tools if item["registered_now"]]
    gated = [item["name"] for item in governed_tools if not item["registered_now"]]
    assert set(advertised) == set(_tools_by_name())
    assert tuple(gated) == reserved_tool_names()
    assert contract["status"] == "WP-13_CAPABILITY_DISCOVERY_EXPOSED_RUNTIME_DERIVED"


def test_all_advertised_tools_have_structured_output_contracts() -> None:
    for tool in get_mcp_tools():
        assert tool.outputSchema is not None
        if tool.name == "get_capabilities":
            assert "snapshot_identity" in tool.outputSchema["required"]
            assert "capabilities" in tool.outputSchema["required"]
            continue
        required = set(tool.outputSchema["required"])
        assert {
            "schema_version",
            "operation",
            "request_id",
            "completeness",
            "coverage",
            "limits",
            "recommended_next_actions",
        } <= required


def test_search_representation_vocabulary_matches_http_and_mcp() -> None:
    http_schema = EvidenceSearchRequest.model_json_schema()
    http_values = set(http_schema["$defs"]["EvidenceRepresentation"]["enum"])
    mcp_values = set(
        SEARCH_EVIDENCE_TOOL.inputSchema["properties"]["representations"]["items"]["enum"]
    )
    assert http_values == mcp_values
    assert "multilingual_text" in mcp_values
    assert "asset_metadata" in mcp_values


def test_blind_agent_contract_distinguishes_search_from_traversal() -> None:
    tools = _tools_by_name()
    search = (tools["search_all_notebooks"].description or "").lower()
    document = (tools["get_document"].description or "").lower()
    assert "bounded ranked discovery" in search
    assert "top-k results are never exhaustive" in search
    assert "first/last/final" in search
    assert "pass returned ids to get_document" in search
    assert "complete document" in document
    assert "cursor is opaque continuation state, not a page number" in document
    assert "pass next_cursor unchanged" in document
    assert "do not answer" in document
    assert "positional selectors never use semantic ranking" in document


def test_document_selector_schema_is_exactly_one_tagged_selector() -> None:
    schema = _tools_by_name()["get_document"].inputSchema
    selector = schema["properties"]["selector"]
    kinds = {item["properties"]["kind"]["const"] for item in selector["oneOf"]}
    assert kinds == {
        "full",
        "page_range",
        "slide_range",
        "sheet_range",
        "block_range",
        "chunk_range",
        "section",
        "from_end",
        "adjacent",
    }
    jsonschema.validate(
        {
            "document_id": "d",
            "version_id": "v",
            "selector": {"kind": "from_end", "unit": "page", "count": 1},
        },
        schema,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {
                "document_id": "d",
                "version_id": "v",
                "selector": {"kind": "page_range", "start": 1, "end": 2, "count": 1},
            },
            schema,
        )


def test_blind_agent_contract_distinguishes_asset_workflows() -> None:
    tools = _tools_by_name()
    asset = (tools["get_asset"].description or "").lower()
    analysis = (tools["get_image_analysis"].description or "").lower()
    assert "not semantic image search" in asset
    assert "original bytes" in asset
    assert "pass a returned occurrence_id to get_image_analysis" in asset
    assert "existing bounded ocr and/or vision derivations" in analysis
    assert "retrieving original bytes" in analysis
    assert "derived analysis is not original source truth" in analysis


def test_structured_text_fallback_is_identical_json() -> None:
    payload = {
        "notebooks": [],
        "total": 0,
        "schema_version": CONTRACT_VERSION,
        "operation": "list_notebooks",
        "request_id": "request-1",
        "completeness": "complete",
        "coverage": {},
        "omissions": [],
        "limits": {},
        "next_cursor": None,
        "recommended_next_actions": [],
    }
    content = [types.TextContent(type="text", text=json.dumps(payload))]
    structured = structured_content_for("list_notebooks", {}, content)
    assert structured == payload
    schema = _tools_by_name()["list_notebooks"].outputSchema
    assert schema is not None
    jsonschema.validate(structured, schema)


def test_binary_content_has_structured_companion_without_bytes() -> None:
    content = [types.ImageContent(type="image", data="cG5n", mimeType="image/png")]
    structured = structured_content_for(
        "get_asset",
        {"notebook_id": "n", "occurrence_id": "o"},
        content,
    )
    assert structured["resource"] == {
        "content_type": "image",
        "mime_type": "image/png",
        "notebook_id": "n",
        "document_id": None,
        "version_id": None,
        "occurrence_id": "o",
    }
    assert "cG5n" not in json.dumps(structured)
    schema = _tools_by_name()["get_asset"].outputSchema
    assert schema is not None
    jsonschema.validate(structured, schema)


def test_asset_input_schema_requires_inventory_or_occurrence_mode() -> None:
    schema = _tools_by_name()["get_asset"].inputSchema
    jsonschema.validate(
        {"notebook_id": "n", "occurrence_id": "o"},
        schema,
    )
    jsonschema.validate(
        {"notebook_id": "n", "document_id": "d", "version_id": "v"},
        schema,
    )
    try:
        jsonschema.validate({"notebook_id": "n"}, schema)
    except jsonschema.ValidationError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("get_asset must require a selected occurrence or document/version")
