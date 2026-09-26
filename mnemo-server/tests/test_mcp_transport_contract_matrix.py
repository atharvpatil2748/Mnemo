"""Same logical disposable corpus across real local MCP transport codecs."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from subprocess import PIPE
from uuid import UUID

import anyio
import pytest
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.app import create_app
from mnemo_server.mcp.server import create_mcp_server
from mnemo_server.services.production_storage_composition import preflight_production_storage
from test_mcp_immutable_schema_matrix import _fixture

_NOTEBOOK = str(UUID(int=1))
_DOCUMENT = str(UUID(int=2))
_VERSION = str(UUID(int=3))
_SOURCE = str(UUID(int=4))


def _cases(occurrence_id: UUID, ocr_id: UUID) -> dict[str, tuple[str, dict[str, object]]]:
    return {
        "inventory": ("list_notebooks", {"limit": 2}),
        "summary": ("get_notebook_summary", {"notebook_id": _NOTEBOOK}),
        "timeline": ("get_timeline", {"notebook_id": _NOTEBOOK, "limit": 1}),
        "insights": ("get_source_insights", {"source_id": _SOURCE, "limit": 1}),
        "global_search": ("search_all_notebooks", {"query": "schema", "top_k": 2}),
        "query": (
            "query_notebook",
            {"notebook_id": _NOTEBOOK, "question": "schema", "top_k": 1, "synthesize": False},
        ),
        "query_synth": (
            "query_notebook",
            {"notebook_id": _NOTEBOOK, "question": "schema", "top_k": 1, "synthesize": True},
        ),
        "evidence": (
            "search_evidence",
            {
                "query": "schema",
                "mode": "ranked",
                "scope": {"notebook_id": _NOTEBOOK, "document_ids": [_DOCUMENT]},
                "representations": ["canonical_text"],
                "evidence_budget": 1,
            },
        ),
        "evidence_partition": (
            "search_evidence",
            {
                "query": "schema",
                "mode": "ranked",
                "scope": {"notebook_id": _NOTEBOOK},
                "representations": ["canonical_text"],
                "evidence_budget": 1,
                "partition_document_ids": [_DOCUMENT],
            },
        ),
        "governed_evidence": (
            "search_evidence",
            {
                "query": "schema",
                "mode": "ranked",
                "scope": {"notebook_id": _NOTEBOOK},
                "representations": ["multilingual_text"],
                "evidence_budget": 1,
            },
        ),
        "governed_partition": (
            "search_evidence",
            {
                "query": "schema",
                "mode": "ranked",
                "scope": {"notebook_id": _NOTEBOOK},
                "representations": ["multilingual_text"],
                "evidence_budget": 1,
                "partition_document_ids": [_DOCUMENT],
            },
        ),
        "document": (
            "get_document",
            {
                "notebook_id": _NOTEBOOK,
                "document_id": _DOCUMENT,
                "version_id": _VERSION,
                "mode": "blocks",
                "max_items": 1,
            },
        ),
        "document_original": (
            "get_document",
            {
                "notebook_id": _NOTEBOOK,
                "document_id": _DOCUMENT,
                "version_id": _VERSION,
                "mode": "original",
            },
        ),
        "chunk": (
            "get_document_chunk",
            {
                "notebook_id": _NOTEBOOK,
                "document_id": _DOCUMENT,
                "version_id": _VERSION,
                "chunk_id": f"{1:064x}",
            },
        ),
        "asset_inventory": (
            "get_asset",
            {
                "notebook_id": _NOTEBOOK,
                "document_id": _DOCUMENT,
                "version_id": _VERSION,
                "limit": 1,
            },
        ),
        "asset_original": (
            "get_asset",
            {"notebook_id": _NOTEBOOK, "occurrence_id": str(occurrence_id)},
        ),
        "analysis": (
            "get_image_analysis",
            {
                "notebook_id": _NOTEBOOK,
                "occurrence_id": str(occurrence_id),
                "ocr_derivation_id": str(ocr_id),
            },
        ),
        "capabilities": ("get_capabilities", {}),
        "structured": (
            "query_structured",
            {
                "operation": "describe",
                "scope": {"notebook_id": _NOTEBOOK, "version_ids": [_VERSION]},
            },
        ),
        "final_qa": (
            "run_final_qa_v2",
            {
                "notebook_id": _NOTEBOOK,
                "session_id": str(UUID(int=2100)),
                "user_turn_id": str(UUID(int=2101)),
                "assistant_turn_id": str(UUID(int=2102)),
                "question": "schema",
                "provider_profile": "final_qa_v2:transport",
                "publication_policy": "allow_partial",
                "evidence_request_or_snapshot": {
                    "query": "schema",
                    "mode": "ranked",
                    "scope": {"notebook_id": _NOTEBOOK},
                    "representations": ["canonical_text"],
                },
            },
        ),
        "final_qa_invalid": ("run_final_qa_v2", {"notebook_id": _NOTEBOOK}),
        "unknown_resource": (
            "get_document_chunk",
            {
                "notebook_id": str(UUID(int=999)),
                "document_id": _DOCUMENT,
                "version_id": _VERSION,
                "chunk_id": "1" * 64,
            },
        ),
        "inventory_invalid": ("list_notebooks", {"limit": True}),
        "summary_unknown": ("get_notebook_summary", {"notebook_id": str(UUID(int=999))}),
        "timeline_unknown": ("get_timeline", {"notebook_id": str(UUID(int=999))}),
        "insights_unknown": ("get_source_insights", {"source_id": str(UUID(int=999))}),
        "global_search_unknown": (
            "search_all_notebooks",
            {"query": "schema", "notebook_id": str(UUID(int=999))},
        ),
        "query_unknown": (
            "query_notebook",
            {"notebook_id": str(UUID(int=999)), "question": "schema"},
        ),
        "evidence_invalid": ("search_evidence", {"query": "schema", "mode": "invalid"}),
        "capability_invalid": ("get_capabilities", {"capability_ids": ["INVALID_CAPABILITY"]}),
        "structured_invalid": (
            "query_structured",
            {"operation": "invalid", "scope": {"notebook_id": _NOTEBOOK}},
        ),
        "document_unknown": (
            "get_document",
            {
                "notebook_id": str(UUID(int=999)),
                "document_id": _DOCUMENT,
                "version_id": _VERSION,
                "mode": "blocks",
            },
        ),
        "asset_unknown": (
            "get_asset",
            {"notebook_id": str(UUID(int=999)), "occurrence_id": str(occurrence_id)},
        ),
        "analysis_unknown": (
            "get_image_analysis",
            {"notebook_id": str(UUID(int=999)), "occurrence_id": str(occurrence_id)},
        ),
    }


def _normalize(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: bool(item) if key == "next_cursor" else _normalize(item)
            for key, item in value.items()
            if key not in {"request_id", "correlation_id", "latency_ms", "elapsed_milliseconds"}
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _first_difference(left: object, right: object, path: str = "root") -> str | None:
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys():
            return f"{path}: keys differ"
        for key in left:
            difference = _first_difference(left[key], right[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            return f"{path}: lengths differ"
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            difference = _first_difference(a, b, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


async def _collect(
    client: ClientSession, cases: dict[str, tuple[str, dict[str, object]]]
) -> dict[str, tuple[bool, object]]:
    await client.initialize()
    assert {tool.name for tool in (await client.list_tools()).tools} == {
        "query_notebook",
        "search_all_notebooks",
        "list_notebooks",
        "get_notebook_summary",
        "get_source_insights",
        "get_timeline",
        "get_document",
        "get_document_chunk",
        "get_asset",
        "get_image_analysis",
        "search_evidence",
        "query_structured",
        "run_final_qa_v2",
        "get_capabilities",
    }
    observed: dict[str, tuple[bool, object]] = {}
    expected_errors = {
        "final_qa_invalid",
        "unknown_resource",
        "inventory_invalid",
        "summary_unknown",
        "timeline_unknown",
        "insights_unknown",
        "global_search_unknown",
        "query_unknown",
        "evidence_invalid",
        "capability_invalid",
        "structured_invalid",
        "document_unknown",
        "asset_unknown",
        "analysis_unknown",
    }
    for label, (tool, arguments) in cases.items():
        response = await client.call_tool(tool, arguments)
        assert response.content, label
        assert bool(response.isError) == (label in expected_errors), label
        if response.isError:
            assert response.content[0].type == "text", label
            body = json.loads(response.content[0].text)
            assert UUID(body["error"]["correlation_id"])
        elif response.content[0].type == "text":
            body = json.loads(response.content[0].text)
            if label == "final_qa":
                assert len(body["snapshot_identity"]) == 64
                body["snapshot_identity"] = "<valid-persisted-snapshot-hash>"
        else:
            body = [block.model_dump(mode="json") for block in response.content]
        observed[label] = (bool(response.isError), _normalize(body))
    assert observed["query_synth"][1]["answer"] == "Grounded [source:1]"
    assert observed["structured"][1]["items"]
    assert observed["chunk"][1]["items"]
    assert observed["governed_evidence"][1]["items"][0]["document_id"] == _DOCUMENT
    assert observed["governed_partition"][1]["items"][0]["document_id"] == _DOCUMENT
    assert (
        observed["governed_partition"][1]["partitions"][0]["items"][0]["source_metadata"]
        == observed["governed_partition"][1]["items"][0]["source_metadata"]
    )
    partition = observed["evidence_partition"][1]
    assert (
        partition["partitions"][0]["items"][0]["source_metadata"]
        == (partition["items"][0]["source_metadata"])
    )
    assert observed["final_qa"][1]["citations"]
    return observed


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_same_fixture_direct_and_real_stdio_contracts(tmp_path: Path, legacy: bool) -> None:
    direct_root = tmp_path / "direct"
    direct_root.mkdir()
    engine, reader, config, _ = await _fixture(
        direct_root,
        legacy=legacy,
        analysis=True,
        capability_ready=True,
        structured_ready=True,
        final_qa_ready=True,
        governed_multilingual=True,
    )
    ids = reader.analysis_ids
    cases = _cases(ids["occurrence"], ids["ocr_0"])
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(UUID(int=99), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                direct = await _collect(client, cases)
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()

    child_root = tmp_path / "stdio"
    child_root.mkdir()
    child = Path(__file__).with_name("mcp_contract_stdio_child.py")
    env = {key: value for key, value in os.environ.items() if not key.startswith("MNEMO_SERVER_")}
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(child), str(child_root), "older" if legacy else "newer"],
        env=env,
    )
    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as client,
    ):
        stdio = await _collect(client, cases)
    assert not (difference := _first_difference(stdio, direct)), difference
    assert not direct["analysis"][0]
    assert direct["analysis"][1]["items"][0]["attribution"]["derivation_id"] == str(ids["ocr_0"])
    assert not direct["capabilities"][0]
    assert direct["unknown_resource"][0]


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_same_fixture_direct_and_real_loopback_sse_contracts(
    tmp_path: Path, legacy: bool
) -> None:
    direct_root = tmp_path / "direct"
    direct_root.mkdir()
    engine, reader, config, _ = await _fixture(
        direct_root,
        legacy=legacy,
        analysis=True,
        capability_ready=True,
        structured_ready=True,
        final_qa_ready=True,
        governed_multilingual=True,
    )
    ids = reader.analysis_ids
    cases = _cases(ids["occurrence"], ids["ocr_0"])
    workspace_decision = (
        preflight_production_storage(
            application_root=direct_root, mnemo_config=engine.config, server_config=config
        )
        .materialize()
        .decision
    )
    direct_server = create_mcp_server(
        engine,
        config=config,
        principal_provider=lambda: PrincipalContextV1(UUID(int=99), True),
        workspace_decision=workspace_decision,
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(
                direct_server.run,
                c2s_recv,
                s2c_send,
                direct_server.create_initialization_options(),
            )
            async with ClientSession(s2c_recv, c2s_send) as client:
                direct = await _collect(client, cases)
                tasks.cancel_scope.cancel()

        sse_root = tmp_path / "sse"
        sse_root.mkdir()
        child = Path(__file__).with_name("mcp_contract_sse_child.py")
        env = {
            key: value for key, value in os.environ.items() if not key.startswith("MNEMO_SERVER_")
        }
        process = await anyio.open_process(
            [sys.executable, str(child), str(sse_root), "older" if legacy else "newer"],
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            env=env,
        )
        try:
            assert process.stdout is not None
            with anyio.fail_after(20):
                line = b""
                while b"\n" not in line:
                    line += await process.stdout.receive()
            assert line.startswith(b"PORT="), line
            port = int(line.split(b"\n", 1)[0].split(b"=", 1)[1])
            with anyio.fail_after(20):
                async with AsyncClient(base_url=f"http://127.0.0.1:{port}") as readiness:
                    while True:
                        try:
                            health = await readiness.get("/health")
                            if health.status_code == 200:
                                break
                        except OSError:
                            pass
                        await anyio.sleep(0.05)
            async with (
                sse_client(
                    f"http://127.0.0.1:{port}/sse",
                    headers={"Authorization": "Bearer fixture-only-not-production"},
                ) as (read_stream, write_stream),
                ClientSession(read_stream, write_stream) as client,
            ):
                sse = await _collect(client, cases)
        finally:
            assert process.stdin is not None
            await process.stdin.send(b"\n")
            await process.stdin.aclose()
            with anyio.fail_after(20):
                assert await process.wait() == 0
        assert not (difference := _first_difference(sse, direct)), (
            difference,
            sse.get("capabilities"),
        )
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_same_fixture_http_and_public_mcp_v2_contracts(tmp_path: Path, legacy: bool) -> None:
    direct_root = tmp_path / "mcp"
    direct_root.mkdir()
    engine, reader, config, _ = await _fixture(
        direct_root,
        legacy=legacy,
        analysis=True,
        capability_ready=True,
        structured_ready=True,
        final_qa_ready=True,
        governed_multilingual=True,
    )
    ids = reader.analysis_ids
    cases = _cases(ids["occurrence"], ids["ocr_0"])
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(UUID(int=99), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                direct = await _collect(client, cases)
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()

    http_root = tmp_path / "http"
    http_root.mkdir()
    http_engine, http_reader, http_config, _ = await _fixture(
        http_root,
        legacy=legacy,
        analysis=True,
        capability_ready=True,
        structured_ready=True,
        final_qa_ready=True,
        governed_multilingual=True,
    )
    app = create_app(
        server_config=http_config, engine=http_engine, provision_tokenizer_on_startup=False
    )
    app.state.engine = http_engine
    app.state.server_config = http_config
    prefix = f"/v2/notebooks/{_NOTEBOOK}/documents/{_DOCUMENT}/versions/{_VERSION}"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fixture",
            headers={"X-API-Key": "fixture-only-not-production"},
        ) as http:
            notebooks = await http.get("/v1/notebooks", params={"limit": 2})
            assert notebooks.status_code == 200, notebooks.text
            assert {item["notebook_id"] for item in notebooks.json()["items"]} == {
                item["notebook_id"] for item in direct["inventory"][1]["notebooks"]
            }
            summary = await http.get(f"/v1/notebooks/{_NOTEBOOK}/summary")
            assert summary.status_code == 200, summary.text
            assert summary.json()["status"] == direct["summary"][1]["status"]
            timeline = await http.get(f"/v1/notebooks/{_NOTEBOOK}/timeline", params={"limit": 1})
            assert timeline.status_code == 200, timeline.text
            assert timeline.json()["events"]
            insights = await http.get(f"/v1/notebooks/{_NOTEBOOK}/insights", params={"limit": 1})
            assert insights.status_code == 200, insights.text
            assert insights.json()["items"][0]["source_id"] == _SOURCE
            search = await http.post(
                "/v1/search",
                json={"query": "schema", "top_k": 2, "modes": ["sparse"]},
            )
            assert search.status_code == 200, search.text
            assert {item["chunk_id"] for item in search.json()["results"]} == {
                item["chunk_id"] for item in direct["global_search"][1]["results"]
            }
            query = await http.post(
                "/v1/query",
                json={
                    "question": "schema",
                    "notebook_id": _NOTEBOOK,
                    "retrieval_config": {"top_k": 1},
                    "synthesis": {"enabled": True},
                },
            )
            assert query.status_code == 200, query.text
            assert query.json()["answer"] == direct["query_synth"][1]["answer"]
            assert [item["chunk_id"] for item in query.json()["citations"]] == [
                item["chunk_id"] for item in direct["query_synth"][1]["citations"]
            ]
            retained_negatives = {
                "inventory_invalid": await http.get("/v1/notebooks", params={"limit": 0}),
                "summary_unknown": await http.get(f"/v1/notebooks/{UUID(int=999)}/summary"),
                "timeline_unknown": await http.get(f"/v1/notebooks/{UUID(int=999)}/timeline"),
                "insights_unknown": await http.get(f"/v1/notebooks/{UUID(int=999)}/insights"),
                "global_search_unknown": await http.post(
                    "/v1/search", json={"query": "schema", "notebook_id": str(UUID(int=999))}
                ),
                "query_unknown": await http.post(
                    "/v1/query", json={"question": "schema", "notebook_id": str(UUID(int=999))}
                ),
            }
            for label, response in retained_negatives.items():
                assert response.status_code >= 400, (label, response.text)
                assert response.json()["error"]["category"] == direct[label][1]["error"]["category"]
                assert "schema evidence" not in response.text
            capabilities = await http.get("/v2/capabilities")
            assert capabilities.status_code == 200
            assert (
                capabilities.json()["snapshot_identity"]
                == direct["capabilities"][1]["snapshot_identity"]
            )
            structured = await http.post("/v2/retrieval/structured", json=cases["structured"][1])
            assert structured.status_code == 200, structured.text
            assert structured.json()["items"] == direct["structured"][1]["items"]
            evidence = await http.post("/v2/retrieval/evidence", json=cases["evidence"][1])
            assert evidence.status_code == 200, evidence.text
            assert (
                evidence.json()["items"][0]["chunk_id"]
                == direct["evidence"][1]["items"][0]["chunk_id"]
            )
            partitioned = await http.post(
                "/v2/retrieval/evidence", json=cases["evidence_partition"][1]
            )
            assert partitioned.status_code == 200, partitioned.text
            assert (
                _normalize(partitioned.json()["partitions"])
                == (direct["evidence_partition"][1]["partitions"])
            )
            governed = await http.post(
                "/v2/retrieval/evidence", json=cases["governed_partition"][1]
            )
            assert governed.status_code == 200, governed.text
            assert (
                _normalize(governed.json()["partitions"])
                == (direct["governed_partition"][1]["partitions"])
            )
            document = await http.get(prefix, params={"max_items": 1})
            assert document.status_code == 200, document.text
            assert document.json()["items"] == direct["document"][1]["items"]
            chunk = await http.get(f"{prefix}/chunks/{1:064x}")
            assert chunk.status_code == 200, chunk.text
            assert chunk.json()["items"] == direct["chunk"][1]["items"]
            assets = await http.get(f"{prefix}/assets", params={"limit": 1})
            assert assets.status_code == 200, assets.text
            assert assets.json()["items"] == direct["asset_inventory"][1]["items"]
            original = await http.get(f"{prefix}/original")
            assert original.status_code == 200
            assert original.headers["content-type"].startswith("image/png")
            assert (
                hashlib.sha256(original.content).hexdigest()
                == direct["document_original"][1][0]["resource"]["meta"]["contentHash"]
            )
            occurrence = ids["occurrence"]
            asset = await http.get(
                f"/v2/notebooks/{_NOTEBOOK}/asset-occurrences/{occurrence}/content"
            )
            assert asset.status_code == 200
            assert (
                hashlib.sha256(asset.content).hexdigest()
                == direct["asset_original"][1][0]["meta"]["contentHash"]
            )
            analysis = await http.get(
                f"/v2/notebooks/{_NOTEBOOK}/asset-occurrences/{occurrence}/analysis",
                params={"ocr_derivation_id": str(ids["ocr_0"])},
            )
            assert analysis.status_code == 200, analysis.text
            assert analysis.json()["items"] == direct["analysis"][1]["items"]
            qa = await http.post(f"/v2/notebooks/{_NOTEBOOK}/final-qa", json=cases["final_qa"][1])
            assert qa.status_code == 200, qa.text
            assert qa.json()["answer"] == direct["final_qa"][1]["answer"]
            assert qa.json()["citations"] == direct["final_qa"][1]["citations"]
            negatives = {
                "unknown_resource": await http.get(
                    f"/v2/notebooks/{UUID(int=999)}/documents/{_DOCUMENT}/"
                    f"versions/{_VERSION}/chunks/{1:064x}"
                ),
                "document_unknown": await http.get(
                    f"/v2/notebooks/{UUID(int=999)}/documents/{_DOCUMENT}/versions/{_VERSION}"
                ),
                "asset_unknown": await http.get(
                    f"/v2/notebooks/{UUID(int=999)}/asset-occurrences/{occurrence}/content"
                ),
                "analysis_unknown": await http.get(
                    f"/v2/notebooks/{UUID(int=999)}/asset-occurrences/{occurrence}/analysis"
                ),
                "evidence_invalid": await http.post(
                    "/v2/retrieval/evidence", json=cases["evidence_invalid"][1]
                ),
                "structured_invalid": await http.post(
                    "/v2/retrieval/structured", json=cases["structured_invalid"][1]
                ),
                "capability_invalid": await http.get(
                    "/v2/capabilities", params={"capability_ids": "INVALID_CAPABILITY"}
                ),
                "final_qa_invalid": await http.post(
                    f"/v2/notebooks/{_NOTEBOOK}/final-qa",
                    json=cases["final_qa_invalid"][1],
                ),
            }
            for label, response in negatives.items():
                assert response.status_code >= 400, (label, response.text)
                error = response.json()["error"]
                assert error["category"] == direct[label][1]["error"]["category"], label
                assert UUID(error["correlation_id"])
                assert "schema evidence" not in response.text
                assert "same-name.csv" not in response.text
    finally:
        await http_reader.close()
