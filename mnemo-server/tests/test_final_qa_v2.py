"""Focused contract tests for the Final-QA V2 transport bridge."""

import json
from uuid import uuid4

from mcp import types
from mnemo.models import AdvancedRetrievalMode, EvidenceRepresentation
from mnemo_server.mcp.tools import get_mcp_tools, structured_content_for
from mnemo_server.schemas.final_qa_v2 import FinalQAV2RequestBody
from mnemo_server.schemas.retrieval_v2 import EvidenceScopeRequest, EvidenceSearchRequest


def _body(notebook_id, question: str = "What is stated?") -> FinalQAV2RequestBody:
    retrieval = EvidenceSearchRequest(
        query=question,
        mode=AdvancedRetrievalMode.RANKED,
        scope=EvidenceScopeRequest(notebook_id=notebook_id),
        representations=(EvidenceRepresentation.CANONICAL_TEXT,),
    )
    return FinalQAV2RequestBody(
        notebook_id=notebook_id,
        session_id=uuid4(),
        user_turn_id=uuid4(),
        assistant_turn_id=uuid4(),
        question=question,
        evidence_request_or_snapshot=retrieval,
        provider_profile="final_qa_v2:test-model",
    )


def test_http_and_mcp_compile_to_identical_canonical_request() -> None:
    notebook_id = uuid4()
    http_request = _body(notebook_id)
    mcp_request = FinalQAV2RequestBody.model_validate(http_request.model_dump(mode="json"))
    assert http_request == mcp_request
    assert http_request.evidence_request_or_snapshot.scope.notebook_id == notebook_id


def test_run_final_qa_v2_is_advertised() -> None:
    tools = get_mcp_tools()
    tool = next(item for item in tools if item.name == "run_final_qa_v2")
    assert "immutable" in tool.description.lower()
    assert "provider_profile" in tool.inputSchema["properties"]


def test_final_qa_structured_content_satisfies_common_mcp_envelope() -> None:
    response = {
        "contract_version": "mnemo.final-qa-v2/1",
        "execution_id": str(uuid4()),
        "answer": "Grounded [source:1]",
        "citations": [],
        "completeness": "truncated",
        "coverage": {"items": 1},
        "omissions": ["token_limit"],
        "recommended_next_actions": [],
    }
    structured = structured_content_for(
        "run_final_qa_v2",
        {"evidence_request_or_snapshot": {"evidence_budget": 5}},
        [types.TextContent(type="text", text=json.dumps(response))],
    )
    assert structured["schema_version"] == "mnemo.final-qa-v2/1"
    assert structured["operation"] == "run_final_qa_v2"
    assert structured["request_id"] == response["execution_id"]
    assert structured["limits"] == {"requested_k": 5}
