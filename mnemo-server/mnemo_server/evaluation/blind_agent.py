"""Blind external-agent runner and deterministic Phase 8.5 behavioral oracle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FailureCode(StrEnum):
    """Stable WP-16 failure taxonomy."""

    TOOL_DISCOVERY_FAILURE = "TOOL_DISCOVERY_FAILURE"
    TOOL_SELECTION_FAILURE = "TOOL_SELECTION_FAILURE"
    CONTRACT_DISCOVERABILITY_FAILURE = "CONTRACT_DISCOVERABILITY_FAILURE"
    CURSOR_CONTINUATION_FAILURE = "CURSOR_CONTINUATION_FAILURE"
    COMPLETENESS_REASONING_FAILURE = "COMPLETENESS_REASONING_FAILURE"
    RETRIEVAL_SEMANTICS_FAILURE = "RETRIEVAL_SEMANTICS_FAILURE"
    MULTIMODAL_DISCOVERY_FAILURE = "MULTIMODAL_DISCOVERY_FAILURE"
    MULTILINGUAL_FAILURE = "MULTILINGUAL_FAILURE"
    STRUCTURED_QUERY_FAILURE = "STRUCTURED_QUERY_FAILURE"
    MULTI_DOCUMENT_FAILURE = "MULTI_DOCUMENT_FAILURE"
    PROVENANCE_FAILURE = "PROVENANCE_FAILURE"
    SECURITY_FAILURE = "SECURITY_FAILURE"
    RESOURCE_CONTROL_FAILURE = "RESOURCE_CONTROL_FAILURE"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    RUNTIME_FAILURE = "RUNTIME_FAILURE"


class ToolDefinition(BaseModel):
    """Public MCP metadata visible to the evaluated client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict[str, object]


class ScenarioOracle(BaseModel):
    """Deterministic oracle retained by the evaluator and hidden from the client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_tool_sequence: tuple[tuple[str, ...], ...]
    forbidden_tools: tuple[str, ...] = ()
    require_cursor_completion: bool = False
    require_terminal_complete: bool = False
    required_provenance_fields: tuple[str, ...] = ()
    allowed_terminal_states: tuple[str, ...] = ("complete",)
    expected_error_codes: tuple[str, ...] = ()
    answer_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class BehavioralScenario(BaseModel):
    """One natural-language blind case and its private oracle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(pattern=r"^P85-B-[0-9]{2}$")
    category: str = Field(min_length=1)
    priority: Literal["P0", "P1"]
    prompt: str = Field(min_length=1)
    max_tool_calls: int = Field(ge=1, le=32)
    oracle: ScenarioOracle


class BehavioralManifest(BaseModel):
    """Versioned set of blind cases for one governed evaluation pack."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_uri: str = Field(alias="$schema")
    schema_version: Literal["mnemo.behavioral-manifest/1"]
    corpus_id: str = Field(min_length=1)
    scenarios: tuple[BehavioralScenario, ...]

    @model_validator(mode="after")
    def _unique_complete_matrix(self) -> BehavioralManifest:
        identifiers = tuple(item.scenario_id for item in self.scenarios)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("behavioral scenario IDs must be unique")
        return self


class ToolCallRecord(BaseModel):
    """One actual public tool invocation and returned structured result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    arguments: dict[str, object]
    result: dict[str, object]


class AgentDecision(BaseModel):
    """One client decision in the tool loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["tool_call", "final"]
    tool: str | None = None
    arguments: dict[str, object] = Field(default_factory=dict)
    answer: str | None = None
    claimed_completeness: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_microusd: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _decision_shape(self) -> AgentDecision:
        if self.kind == "tool_call" and not self.tool:
            raise ValueError("tool_call decision requires a tool")
        if self.kind == "final" and self.answer is None:
            raise ValueError("final decision requires an answer")
        return self


class AgentTurnView(BaseModel):
    """The complete blind input. It intentionally has no oracle field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str
    tools: tuple[ToolDefinition, ...]
    calls: tuple[ToolCallRecord, ...]


class BehavioralTranscript(BaseModel):
    """Local protected transcript produced by one evaluated client run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["mnemo.behavioral-transcript/1"] = "mnemo.behavioral-transcript/1"
    run_id: str = Field(min_length=1)
    scenario_id: str
    client_id: str = Field(min_length=1)
    client_model: str = Field(min_length=1)
    transport: Literal["stdio", "sse", "memory"]
    tools: tuple[ToolDefinition, ...]
    tools_digest: str = Field(min_length=64, max_length=64)
    calls: tuple[ToolCallRecord, ...]
    final_answer: str | None
    claimed_completeness: str | None
    exhausted_budget: bool
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_microusd: int = Field(default=0, ge=0)


class BehavioralFailure(BaseModel):
    """One deterministic oracle failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FailureCode
    detail: str


class ScenarioVerdict(BaseModel):
    """Oracle result kept separate from the client transcript."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    passed: bool
    failures: tuple[BehavioralFailure, ...]
    tool_calls: int


class BlindAgentClientV1(Protocol):
    """An external client/model that sees only ``AgentTurnView``."""

    client_id: str
    model_id: str

    async def decide(self, view: AgentTurnView) -> AgentDecision: ...


class ToolTransportV1(Protocol):
    """Public MCP-only transport consumed by the evaluator."""

    transport_name: Literal["stdio", "sse", "memory"]

    async def list_tools(self) -> tuple[ToolDefinition, ...]: ...

    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> dict[str, object]: ...


class MCPClientSessionTransport:
    """Adapter over an initialized MCP ``ClientSession`` for stdio or SSE."""

    def __init__(self, session: object, *, transport_name: Literal["stdio", "sse"]) -> None:
        self._session = session
        self.transport_name = transport_name

    async def list_tools(self) -> tuple[ToolDefinition, ...]:
        result = await cast(Any, self._session).list_tools()
        tools: list[ToolDefinition] = []
        for item in result.tools:
            schema = getattr(item, "inputSchema", getattr(item, "input_schema", {}))
            tools.append(
                ToolDefinition(
                    name=item.name,
                    description=item.description or "No description supplied.",
                    input_schema=cast(dict[str, object], schema),
                )
            )
        return tuple(sorted(tools, key=lambda value: value.name))

    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> dict[str, object]:
        result = await cast(Any, self._session).call_tool(name, dict(arguments))
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return cast(dict[str, object], structured)
        content = getattr(result, "content", ())
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return cast(dict[str, object], parsed)
        return {"error": {"code": "transport.unstructured_result"}}


class BlindAgentEvaluator:
    """Run the bounded public MCP loop and evaluate its transcript independently."""

    async def run(
        self,
        *,
        run_id: str,
        scenario: BehavioralScenario,
        client: BlindAgentClientV1,
        transport: ToolTransportV1,
    ) -> tuple[BehavioralTranscript, ScenarioVerdict]:
        tools = await transport.list_tools()
        digest = hashlib.sha256(
            json.dumps(
                [item.model_dump(mode="json") for item in tools],
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        calls: list[ToolCallRecord] = []
        final: AgentDecision | None = None
        input_tokens = 0
        output_tokens = 0
        cost_microusd = 0
        names = {item.name for item in tools}
        for _ in range(scenario.max_tool_calls):
            decision = await client.decide(
                AgentTurnView(prompt=scenario.prompt, tools=tools, calls=tuple(calls))
            )
            input_tokens += decision.input_tokens
            output_tokens += decision.output_tokens
            cost_microusd += decision.cost_microusd
            if decision.kind == "final":
                final = decision
                break
            assert decision.tool is not None
            if decision.tool not in names:
                calls.append(
                    ToolCallRecord(
                        tool=decision.tool,
                        arguments=decision.arguments,
                        result={"error": {"code": "mcp.unknown_tool"}},
                    )
                )
                break
            result = await transport.call_tool(decision.tool, decision.arguments)
            calls.append(
                ToolCallRecord(
                    tool=decision.tool,
                    arguments=decision.arguments,
                    result=result,
                )
            )
        transcript = BehavioralTranscript(
            run_id=run_id,
            scenario_id=scenario.scenario_id,
            client_id=client.client_id,
            client_model=client.model_id,
            transport=transport.transport_name,
            tools=tools,
            tools_digest=digest,
            calls=tuple(calls),
            final_answer=None if final is None else final.answer,
            claimed_completeness=None if final is None else final.claimed_completeness,
            exhausted_budget=final is None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microusd=cost_microusd,
        )
        return transcript, self.evaluate(scenario, transcript)

    def evaluate(
        self, scenario: BehavioralScenario, transcript: BehavioralTranscript
    ) -> ScenarioVerdict:
        failures: list[BehavioralFailure] = []
        tools = tuple(item.tool for item in transcript.calls)
        if not _ordered_tool_match(tools, scenario.oracle.required_tool_sequence):
            failures.append(
                BehavioralFailure(
                    code=_selection_failure(scenario.category),
                    detail="required public tool sequence was not observed",
                )
            )
        forbidden = sorted(set(tools).intersection(scenario.oracle.forbidden_tools))
        if forbidden:
            failures.append(
                BehavioralFailure(
                    code=FailureCode.RETRIEVAL_SEMANTICS_FAILURE,
                    detail=f"forbidden tool selected: {', '.join(forbidden)}",
                )
            )
        if transcript.exhausted_budget:
            failures.append(
                BehavioralFailure(
                    code=FailureCode.RESOURCE_CONTROL_FAILURE,
                    detail="client exhausted the bounded tool-call budget",
                )
            )
        terminal_states = _terminal_states(transcript.calls)
        if scenario.oracle.require_terminal_complete and "complete" not in terminal_states:
            failures.append(
                BehavioralFailure(
                    code=FailureCode.COMPLETENESS_REASONING_FAILURE,
                    detail="terminal complete result was not observed",
                )
            )
        if terminal_states and not terminal_states.intersection(
            state.casefold() for state in scenario.oracle.allowed_terminal_states
        ):
            failures.append(
                BehavioralFailure(
                    code=FailureCode.COMPLETENESS_REASONING_FAILURE,
                    detail="observed completeness state is outside the scenario contract",
                )
            )
        if scenario.oracle.require_cursor_completion and not _cursor_chain_complete(
            transcript.calls
        ):
            failures.append(
                BehavioralFailure(
                    code=FailureCode.CURSOR_CONTINUATION_FAILURE,
                    detail="a returned continuation cursor was not followed unchanged",
                )
            )
        if (
            transcript.claimed_completeness == "complete"
            and terminal_states
            and "complete" not in terminal_states
        ):
            failures.append(
                BehavioralFailure(
                    code=FailureCode.COMPLETENESS_REASONING_FAILURE,
                    detail="client claimed complete without terminal complete evidence",
                )
            )
        flattened = _flatten_keys(tuple(item.result for item in transcript.calls))
        missing = tuple(
            field for field in scenario.oracle.required_provenance_fields if field not in flattened
        )
        if missing:
            failures.append(
                BehavioralFailure(
                    code=FailureCode.PROVENANCE_FAILURE,
                    detail=f"missing provenance fields: {', '.join(missing)}",
                )
            )
        if scenario.oracle.expected_error_codes:
            observed_errors = _error_codes(transcript.calls)
            if not set(scenario.oracle.expected_error_codes).intersection(observed_errors):
                failures.append(
                    BehavioralFailure(
                        code=FailureCode.SECURITY_FAILURE,
                        detail="expected safe denial/error code was not observed",
                    )
                )
        if scenario.oracle.answer_sha256 is not None:
            actual = hashlib.sha256((transcript.final_answer or "").encode("utf-8")).hexdigest()
            if actual != scenario.oracle.answer_sha256:
                failures.append(
                    BehavioralFailure(
                        code=FailureCode.RETRIEVAL_SEMANTICS_FAILURE,
                        detail="final answer digest did not match the governed oracle",
                    )
                )
        if _contains_sensitive_data(tuple(item.result for item in transcript.calls)):
            failures.append(
                BehavioralFailure(
                    code=FailureCode.SECURITY_FAILURE,
                    detail="public result contains a forbidden path or secret-shaped field",
                )
            )
        return ScenarioVerdict(
            scenario_id=scenario.scenario_id,
            passed=not failures,
            failures=tuple(failures),
            tool_calls=len(transcript.calls),
        )


def load_behavioral_manifest(path: str | Path) -> BehavioralManifest:
    """Load one strict behavioral manifest without altering its fixture corpus."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return BehavioralManifest.model_validate(payload)


def redact_transcript(transcript: BehavioralTranscript) -> dict[str, object]:
    """Produce a publishable summary without prompts, arguments, results, or answers."""
    return {
        "schema_version": transcript.schema_version,
        "run_id": transcript.run_id,
        "scenario_id": transcript.scenario_id,
        "client_id": transcript.client_id,
        "client_model": transcript.client_model,
        "transport": transcript.transport,
        "tools_digest": transcript.tools_digest,
        "available_tool_names": [item.name for item in transcript.tools],
        "invoked_tool_names": [item.tool for item in transcript.calls],
        "tool_calls": len(transcript.calls),
        "answer_sha256": hashlib.sha256(
            (transcript.final_answer or "").encode("utf-8")
        ).hexdigest(),
        "claimed_completeness": transcript.claimed_completeness,
        "exhausted_budget": transcript.exhausted_budget,
        "input_tokens": transcript.input_tokens,
        "output_tokens": transcript.output_tokens,
        "cost_microusd": transcript.cost_microusd,
    }


def _ordered_tool_match(actual: Sequence[str], required: Sequence[Sequence[str]]) -> bool:
    position = 0
    for alternatives in required:
        while position < len(actual) and actual[position] not in alternatives:
            position += 1
        if position == len(actual):
            return False
        position += 1
    return True


def _walk(value: object) -> Sequence[object]:
    if isinstance(value, Mapping):
        children: list[object] = [value]
        for child in value.values():
            children.extend(_walk(child))
        return children
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        children = [value]
        for child in value:
            children.extend(_walk(child))
        return children
    return (value,)


def _terminal_states(calls: Sequence[ToolCallRecord]) -> set[str]:
    states: set[str] = set()
    for call in calls:
        for value in _walk(call.result):
            if isinstance(value, Mapping):
                completeness = value.get("completeness")
                if isinstance(completeness, str):
                    states.add(completeness.casefold())
                elif isinstance(completeness, Mapping):
                    state = completeness.get("state")
                    if isinstance(state, str):
                        states.add(state.casefold())
    return states


def _cursor_chain_complete(calls: Sequence[ToolCallRecord]) -> bool:
    for index, call in enumerate(calls):
        cursor = _first_string(call.result, "next_cursor")
        state = _first_string(call.result, "completeness") or _first_string(call.result, "state")
        if cursor and state and state.casefold() == "truncated":
            if index + 1 >= len(calls):
                return False
            following = calls[index + 1]
            if following.tool != call.tool or following.arguments.get("cursor") != cursor:
                return False
    return not calls or _first_string(calls[-1].result, "next_cursor") in {None, ""}


def _first_string(value: object, key: str) -> str | None:
    for item in _walk(value):
        if isinstance(item, Mapping):
            found = item.get(key)
            if isinstance(found, str):
                return found
    return None


def _flatten_keys(values: Sequence[object]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        for item in _walk(value):
            if isinstance(item, Mapping):
                keys.update(str(key) for key in item)
    return keys


def _error_codes(calls: Sequence[ToolCallRecord]) -> set[str]:
    codes: set[str] = set()
    for call in calls:
        for item in _walk(call.result):
            if isinstance(item, Mapping):
                error = item.get("error")
                if isinstance(error, Mapping) and isinstance(error.get("code"), str):
                    codes.add(cast(str, error["code"]))
    return codes


def _selection_failure(category: str) -> FailureCode:
    normalized = category.casefold()
    if "structured" in normalized or "comparison" in normalized:
        return FailureCode.STRUCTURED_QUERY_FAILURE
    if "image" in normalized or "multimodal" in normalized or "ocr" in normalized:
        return FailureCode.MULTIMODAL_DISCOVERY_FAILURE
    if "language" in normalized:
        return FailureCode.MULTILINGUAL_FAILURE
    if "multi-document" in normalized:
        return FailureCode.MULTI_DOCUMENT_FAILURE
    return FailureCode.TOOL_SELECTION_FAILURE


def _contains_sensitive_data(values: Sequence[object]) -> bool:
    forbidden_keys = {
        "api_key",
        "authorization",
        "credential",
        "filesystem_path",
        "model_root",
        "password",
        "secret",
        "signing_key",
        "storage_uri",
    }
    for value in values:
        for item in _walk(value):
            if isinstance(item, Mapping):
                if forbidden_keys.intersection(str(key).casefold() for key in item):
                    return True
            elif isinstance(item, str) and ("file://" in item.casefold() or ":\\" in item):
                return True
    return False
