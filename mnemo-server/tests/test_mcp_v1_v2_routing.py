"""Public routing regressions: retained V1 availability never disguises missing V2."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.app import create_app
from mnemo_server.mcp.server import create_mcp_server
from test_mcp_immutable_schema_matrix import _fixture


def test_http_v1_v2_public_routes_remain_distinct() -> None:
    paths = create_app(provision_tokenizer_on_startup=False).openapi()["paths"]
    expected = {
        ("/v1/query", "post"),
        ("/v1/search", "post"),
        ("/v1/query/stream", "post"),
        ("/v1/notebooks/{notebook_id}/final-qa", "post"),
        ("/v2/notebooks/{notebook_id}/final-qa", "post"),
        ("/v2/retrieval/evidence", "post"),
        ("/v2/retrieval/structured", "post"),
        ("/v2/capabilities", "get"),
        (
            "/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}",
            "get",
        ),
        (
            "/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/chunks/{chunk_id}",
            "get",
        ),
        ("/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content", "get"),
        ("/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis", "get"),
    }
    assert all(method in paths[path] for path, method in expected)
    assert (
        paths["/v1/notebooks/{notebook_id}/final-qa"]["post"]["operationId"]
        != (paths["/v2/notebooks/{notebook_id}/final-qa"]["post"]["operationId"])
    )


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["older", "newer"])
async def test_retained_v1_survives_unavailable_v2_without_historical_fallback(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id = identities[0][0]
    # The retained V1 retriever and deterministic synthesizer remain healthy.
    # V2 retrieval/projection/composition are deliberately unavailable.
    engine._advanced_retrieval = None
    engine._structured_retrieval = None
    engine._final_qa_v2 = None
    server = create_mcp_server(
        engine,
        config=config,
        principal_provider=lambda: PrincipalContextV1(uuid4(), True),
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                v1 = await client.call_tool(
                    "query_notebook",
                    {
                        "notebook_id": str(notebook_id),
                        "question": "schema",
                        "top_k": 1,
                        "synthesize": True,
                    },
                )
                assert not v1.isError, v1.content
                assert "Grounded" in json.dumps(json.loads(v1.content[0].text))
                retained = await client.call_tool(
                    "search_all_notebooks",
                    {"notebook_id": str(notebook_id), "query": "schema", "top_k": 1},
                )
                assert not retained.isError
                assert json.loads(retained.content[0].text)["results"]

                for name, arguments in (
                    (
                        "search_evidence",
                        {
                            "query": "schema",
                            "mode": "ranked",
                            "scope": {"notebook_id": str(notebook_id)},
                            "representations": ["canonical_text"],
                            "evidence_budget": 1,
                        },
                    ),
                    (
                        "query_structured",
                        {
                            "operation": "describe",
                            "scope": {
                                "notebook_id": str(notebook_id),
                                "version_ids": [str(identities[0][2])],
                            },
                            "page_size": 1,
                        },
                    ),
                    (
                        "run_final_qa_v2",
                        {
                            "notebook_id": str(notebook_id),
                            "session_id": str(UUID(int=2100)),
                            "user_turn_id": str(UUID(int=2101)),
                            "assistant_turn_id": str(UUID(int=2102)),
                            "question": "schema",
                            "provider_profile": "final_qa_v2:transport",
                            "publication_policy": "allow_partial",
                            "evidence_request_or_snapshot": {
                                "query": "schema",
                                "mode": "ranked",
                                "scope": {"notebook_id": str(notebook_id)},
                                "representations": ["canonical_text"],
                            },
                        },
                    ),
                ):
                    unavailable = await client.call_tool(name, arguments)
                    assert unavailable.isError, name
                    error = json.loads(unavailable.content[0].text)["error"]
                    assert error["category"] == "capability_unavailable", (name, error)
                    assert UUID(error["correlation_id"])
                    assert "Grounded" not in json.dumps(error)
                tasks.cancel_scope.cancel()
    finally:
        await c2s_send.aclose()
        await s2c_send.aclose()
        await reader.close()
