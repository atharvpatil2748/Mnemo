"""Focused static conformance tests for the Phase 8.5 WP-00 contract freeze."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_ACTIVE_DIR = ADR_DIR / "active"
ADR_SUPERSEDED_DIR = ADR_DIR / "superseded"
CONTRACT_DIR = ROOT / "docs" / "governance" / "contracts"
CAPABILITY_PATH = CONTRACT_DIR / "phase8_5_capability_matrix.json"
CAPABILITY_SCHEMA_PATH = CONTRACT_DIR / "phase8_5_capability_matrix.schema.json"
MCP_PATH = CONTRACT_DIR / "phase8_5_mcp_contracts.json"
STORAGE_PATH = ROOT / "mnemo-core" / "mnemo" / "interfaces" / "storage.py"
ADR_0072_PATH = ADR_SUPERSEDED_DIR / (
    "ADR-0072-propagate-notebook-identity-and-safely-resolve-"
    "notebook-context-for-mcp-document-retrieval.md"
)

REQUIRED_CAPABILITIES = {
    "canonical_ingestion",
    "v1_retrieval",
    "exact_retrieval",
    "positional_retrieval",
    "exhaustive_retrieval",
    "structured_retrieval",
    "asset_discovery",
    "asset_delivery",
    "ocr",
    "vision",
    "visual_vector_retrieval",
    "multilingual_retrieval",
    "multimodal_retrieval",
    "multi_document_retrieval",
    "final_qa_v2",
    "document_delivery",
    "capability_discovery",
    "cursor_continuation",
    "provenance",
    "authorization",
    "completeness",
    "processing_jobs",
    "multilingual_ocr",
    "multilingual_vision",
    "behavioral_verification",
    "security_verification",
    "phase_11_deterministic_primitives",
    "runtime_profile_activation",
}

REQUIRED_STATES = {
    "code_present",
    "configured",
    "provider_ready",
    "generation_present",
    "generation_active",
    "exposed_http",
    "exposed_mcp",
    "discoverable",
    "behaviorally_verified",
    "security_verified",
    "certified",
}

RETAINED_TOOLS = {
    "list_notebooks",
    "get_notebook_summary",
    "search_all_notebooks",
    "query_notebook",
    "get_source_insights",
    "get_timeline",
    "get_document",
    "get_document_chunk",
    "get_asset",
    "get_image_analysis",
}

ADDITIVE_TOOLS = {
    "search_evidence",
    "query_structured",
    "run_final_qa_v2",
    "get_capabilities",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _storage_methods() -> set[str]:
    tree = ast.parse(STORAGE_PATH.read_text(encoding="utf-8"))
    protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "StorageInterfaceV1"
    )
    return {
        node.name
        for node in protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_adr_numbers_links_and_successor_relationships_are_frozen() -> None:
    adr_paths = sorted(ADR_ACTIVE_DIR.glob("ADR-*.md")) + sorted(
        ADR_SUPERSEDED_DIR.glob("ADR-*.md")
    )
    numbers = [int(path.name[4:8]) for path in adr_paths]
    assert len(numbers) == len(set(numbers))
    assert {73, 74, 75}.issubset(numbers)

    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    for number in (73, 74, 75):
        matches = [path for path in adr_paths if path.name.startswith(f"ADR-{number:04d}-")]
        assert len(matches) == 1
        relative = matches[0].relative_to(ADR_DIR).as_posix()
        assert f"({relative})" in index
        assert "**Status:** Accepted" in matches[0].read_text(encoding="utf-8")

    historical = ADR_0072_PATH.read_text(encoding="utf-8")
    successor = (ADR_ACTIVE_DIR / "ADR-0075-additive-document-scope-resolution.md").read_text(
        encoding="utf-8"
    )
    assert "**Supersedes:** Nothing" in historical
    assert "Supersedes:** ADR-0072 mechanism only" in successor
    assert "ADR-0072 is\npreserved unchanged" in successor


def test_capability_matrix_has_required_shape_and_no_unsupported_certification() -> None:
    schema = _load(CAPABILITY_SCHEMA_PATH)
    matrix = _load(CAPABILITY_PATH)
    assert matrix["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert len(matrix["work_packages"]) == 18
    assert {wp["id"] for wp in matrix["work_packages"]} == {
        f"WP-{number:02d}" for number in range(18)
    }

    capabilities = matrix["capabilities"]
    ids = [item["id"] for item in capabilities]
    assert len(ids) == len(set(ids))
    assert REQUIRED_CAPABILITIES.issubset(ids)
    for capability in capabilities:
        assert set(capability["states"]) == REQUIRED_STATES
        assert capability["readiness_conditions"]
        assert capability["security"]
        assert capability["certification_requirements"]
        states = capability["states"]
        if states["generation_active"] is True:
            assert states["generation_present"] is True
        if states["behaviorally_verified"] is True:
            assert states["code_present"] is True
        if states["certified"] is True:
            for name, value in states.items():
                if name != "certified" and value is not None:
                    assert value is True, (capability["id"], name)


def test_frozen_storage_signature_is_restored_after_adr_0075_migration() -> None:
    matrix = _load(CAPABILITY_PATH)
    frozen = set(matrix["frozen_v1"]["storage_interface_v1_pre_0072_methods"])
    current = _storage_methods()
    assert current == frozen
    assert frozen - current == set()
    assert "ADR-0075" in matrix["frozen_v1"]["known_drift"]


def test_document_scope_resolver_contract_is_explicit_and_fail_closed() -> None:
    adr = (ADR_ACTIVE_DIR / "ADR-0075-additive-document-scope-resolution.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "DocumentScopeResolverV1",
        "actor_scope",
        "document_id",
        "version_id",
        "requested_notebook_id",
        "UNIQUE_ASSOCIATION",
        "Multiple possible associations fail closed",
        "No new method is added to `StorageInterfaceV1`",
    ):
        assert phrase in adr


def test_mcp_contract_freezes_retained_and_additive_tool_sets() -> None:
    contract = _load(MCP_PATH)
    tools = contract["tools"]
    retained = {tool["name"] for tool in tools if tool["kind"] == "retained"}
    additive = {tool["name"] for tool in tools if tool["kind"] == "additive"}
    assert retained == RETAINED_TOOLS
    assert additive == ADDITIVE_TOOLS
    assert all(tool["registered_now"] for tool in tools if tool["kind"] == "retained")
    assert {
        tool["name"] for tool in tools if tool["kind"] == "additive" and tool["registered_now"]
    } == {"search_evidence", "query_structured", "run_final_qa_v2", "get_capabilities"}

    output_required = set(contract["common_output_schema"]["required"])
    assert {
        "schema_version",
        "operation",
        "request_id",
        "completeness",
        "coverage",
        "limits",
        "recommended_next_actions",
    }.issubset(output_required)


def test_mcp_metadata_distinguishes_the_critical_semantic_boundaries() -> None:
    tools = {tool["name"]: tool for tool in _load(MCP_PATH)["tools"]}

    search_negative = " ".join(tools["search_all_notebooks"]["do_not_use_when"]).lower()
    assert all(
        term in search_negative for term in ("all/every", "exact page", "structured", "image")
    )
    assert "ranked" in tools["search_all_notebooks"]["responsibility"].lower()

    document_text = " ".join(
        tools["get_document"][key] for key in ("responsibility", "completeness")
    ).lower()
    assert all(term in document_text for term in ("exact-version", "continue", "cursor"))

    asset_negative = " ".join(tools["get_asset"]["do_not_use_when"]).lower()
    analysis_negative = " ".join(tools["get_image_analysis"]["do_not_use_when"]).lower()
    assert "natural-language" in asset_negative
    assert "original bytes" in analysis_negative
    assert "search_evidence" in {tool["name"] for tool in tools.values()}
    assert "query_structured" in {tool["name"] for tool in tools.values()}


def test_dependency_graph_and_phase_11_non_goals_are_frozen() -> None:
    matrix = _load(CAPABILITY_PATH)
    by_id = {wp["id"]: wp for wp in matrix["work_packages"]}
    assert by_id["WP-00"]["depends_on"] == []
    assert "WP-00" in by_id["WP-01"]["depends_on"]
    assert set(by_id["WP-17"]["depends_on"]) == {f"WP-{number:02d}" for number in range(17)}
    non_goals = " ".join(matrix["phase_11_non_goals"]).lower()
    for term in ("query decomposition", "replanning", "adaptive", "multi-hop", "open-ended joins"):
        assert term in non_goals


def test_new_adr_index_links_resolve() -> None:
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\[[^]]+\]\(([^)]+)\)", index)
    for link in links:
        assert (ADR_DIR / link).resolve().exists(), link
