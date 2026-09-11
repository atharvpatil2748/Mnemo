"""WP-16 blind-agent manifest, runner, oracle, mutation, and adapter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

import jsonschema
import pytest
from mnemo_server.evaluation.blind_agent import (
    AgentDecision,
    AgentTurnView,
    BehavioralScenario,
    BehavioralTranscript,
    BlindAgentEvaluator,
    MCPClientSessionTransport,
    ToolCallRecord,
    ToolDefinition,
    load_behavioral_manifest,
    redact_transcript,
)
from mnemo_server.mcp.tools import get_mcp_tools

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evaluation/phase8_5_wp16/behavioral_manifest.json"
SCHEMA = ROOT / "evaluation/phase8_5_wp16/behavioral_manifest.schema.json"


class _MemoryTransport:
    transport_name = "memory"

    def __init__(self, results: list[dict[str, object]]) -> None:
        self.results = results
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self) -> tuple[ToolDefinition, ...]:
        return tuple(
            ToolDefinition(
                name=item.name,
                description=item.description or "missing",
                input_schema=item.inputSchema,
            )
            for item in get_mcp_tools()
        )

    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> dict[str, object]:
        self.calls.append((name, dict(arguments)))
        return self.results.pop(0)


class _SequenceClient:
    client_id = "deterministic-harness-fixture"
    model_id = "no-model"

    def __init__(self, decisions: list[AgentDecision]) -> None:
        self.decisions = decisions
        self.views: list[AgentTurnView] = []

    async def decide(self, view: AgentTurnView) -> AgentDecision:
        self.views.append(view)
        return self.decisions.pop(0)


def _scenario(**changes: object) -> BehavioralScenario:
    base: dict[str, object] = {
        "scenario_id": "P85-B-01",
        "category": "exact-document",
        "priority": "P0",
        "prompt": "Give me the complete document.",
        "max_tool_calls": 4,
        "oracle": {
            "required_tool_sequence": [["get_document"]],
            "require_cursor_completion": True,
            "require_terminal_complete": True,
            "required_provenance_fields": ["document_id", "version_id"],
        },
    }
    base.update(changes)
    return BehavioralScenario.model_validate(base)


def test_manifest_schema_and_authoritative_31_case_matrix() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    jsonschema.validate(payload, json.loads(SCHEMA.read_text(encoding="utf-8")))
    manifest = load_behavioral_manifest(MANIFEST)
    assert len(manifest.scenarios) == 31
    assert {item.scenario_id for item in manifest.scenarios} == {
        f"P85-B-{number:02d}" for number in range(1, 32)
    }
    assert {item.priority for item in manifest.scenarios} == {"P0", "P1"}


def test_agent_view_is_blind_and_contains_only_prompt_tools_and_prior_calls() -> None:
    assert set(AgentTurnView.model_fields) == {"prompt", "tools", "calls"}
    manifest = load_behavioral_manifest(MANIFEST)
    for scenario in manifest.scenarios:
        view = AgentTurnView(prompt=scenario.prompt, tools=(), calls=())
        serialized = view.model_dump_json()
        assert "oracle" not in serialized
        assert "required_tool_sequence" not in serialized


@pytest.mark.anyio
async def test_runner_follows_opaque_cursor_and_oracle_accepts_terminal_completion() -> None:
    client = _SequenceClient(
        [
            AgentDecision(kind="tool_call", tool="get_document", arguments={}),
            AgentDecision(kind="tool_call", tool="get_document", arguments={"cursor": "opaque"}),
            AgentDecision(kind="final", answer="done", claimed_completeness="complete"),
        ]
    )
    transport = _MemoryTransport(
        [
            {
                "completeness": "truncated",
                "next_cursor": "opaque",
                "document_id": "opaque-document",
                "version_id": "opaque-version",
            },
            {
                "completeness": "complete",
                "next_cursor": None,
                "document_id": "opaque-document",
                "version_id": "opaque-version",
            },
        ]
    )
    transcript, verdict = await BlindAgentEvaluator().run(
        run_id="run-1", scenario=_scenario(), client=client, transport=transport
    )
    assert verdict.passed
    assert len(transcript.calls) == 2
    assert transport.calls[1][1]["cursor"] == "opaque"
    assert all("oracle" not in view.model_dump() for view in client.views)


def test_oracle_mutations_catch_wrong_tool_false_completeness_and_missing_provenance() -> None:
    transcript = BehavioralTranscript(
        run_id="run",
        scenario_id="P85-B-01",
        client_id="client",
        client_model="model",
        transport="memory",
        tools=(),
        tools_digest="0" * 64,
        calls=(
            ToolCallRecord(
                tool="query_notebook",
                arguments={},
                result={"completeness": "truncated", "next_cursor": "opaque"},
            ),
        ),
        final_answer="complete answer",
        claimed_completeness="complete",
        exhausted_budget=False,
    )
    verdict = BlindAgentEvaluator().evaluate(_scenario(), transcript)
    codes = {item.code.value for item in verdict.failures}
    assert "TOOL_SELECTION_FAILURE" in codes
    assert "CURSOR_CONTINUATION_FAILURE" in codes
    assert "COMPLETENESS_REASONING_FAILURE" in codes
    assert "PROVENANCE_FAILURE" in codes


def test_oracle_detects_safe_denial_absence_and_sensitive_result_leakage() -> None:
    scenario = _scenario(
        oracle={
            "required_tool_sequence": [["get_document"]],
            "expected_error_codes": ["auth.forbidden"],
            "allowed_terminal_states": ["unavailable"],
        }
    )
    transcript = BehavioralTranscript(
        run_id="run",
        scenario_id="P85-B-01",
        client_id="client",
        client_model="model",
        transport="memory",
        tools=(),
        tools_digest="0" * 64,
        calls=(
            ToolCallRecord(
                tool="get_document",
                arguments={},
                result={"filesystem_path": "C:\\private\\document.txt"},
            ),
        ),
        final_answer="denied",
        claimed_completeness="unavailable",
        exhausted_budget=False,
    )
    verdict = BlindAgentEvaluator().evaluate(scenario, transcript)
    assert [item.code.value for item in verdict.failures].count("SECURITY_FAILURE") == 2


@pytest.mark.anyio
async def test_runner_stops_at_budget_and_classifies_resource_loop() -> None:
    scenario = _scenario(max_tool_calls=2, oracle={"required_tool_sequence": [["get_document"]]})
    client = _SequenceClient(
        [
            AgentDecision(kind="tool_call", tool="get_document", arguments={}),
            AgentDecision(kind="tool_call", tool="get_document", arguments={}),
        ]
    )
    transport = _MemoryTransport([{"completeness": "partial"}] * 2)
    transcript, verdict = await BlindAgentEvaluator().run(
        run_id="bounded", scenario=scenario, client=client, transport=transport
    )
    assert transcript.exhausted_budget
    assert any(item.code.value == "RESOURCE_CONTROL_FAILURE" for item in verdict.failures)


def test_redacted_transcript_contains_no_arguments_results_prompt_or_answer() -> None:
    transcript = BehavioralTranscript(
        run_id="run",
        scenario_id="P85-B-01",
        client_id="client",
        client_model="model",
        transport="stdio",
        tools=(),
        tools_digest="0" * 64,
        calls=(
            ToolCallRecord(
                tool="get_document",
                arguments={"document_id": "private-id"},
                result={"text": "private evidence"},
            ),
        ),
        final_answer="private answer",
        claimed_completeness="complete",
        exhausted_budget=False,
    )
    summary = json.dumps(redact_transcript(transcript), sort_keys=True)
    assert "private-id" not in summary
    assert "private evidence" not in summary
    assert "private answer" not in summary
    assert "get_document" in summary


@pytest.mark.anyio
async def test_mcp_client_session_adapter_normalizes_structured_content() -> None:
    class _Result:
        tools: ClassVar = get_mcp_tools()
        structuredContent: ClassVar = {"completeness": "complete"}
        content: tuple[object, ...] = ()

    class _Session:
        async def list_tools(self) -> _Result:
            return _Result()

        async def call_tool(self, name: str, arguments: dict[str, object]) -> _Result:
            assert name == "get_capabilities"
            assert arguments == {}
            return _Result()

    adapter = MCPClientSessionTransport(_Session(), transport_name="stdio")
    tools = await adapter.list_tools()
    result = await adapter.call_tool("get_capabilities", {})
    assert len(tools) == 14
    assert result == {"completeness": "complete"}


def test_mcp_guidance_has_no_semantic_image_or_final_qa_chain_contradiction() -> None:
    tools = {item.name: (item.description or "").casefold() for item in get_mcp_tools()}
    search = tools["search_evidence"]
    final_qa = tools["run_final_qa_v2"]
    assert "semantic image discovery is supported" in search
    assert "one aggregate cursorcodecv2 cursor" in search
    for tool in ("search_evidence", "get_document", "query_structured", "get_asset"):
        assert tool in final_qa
