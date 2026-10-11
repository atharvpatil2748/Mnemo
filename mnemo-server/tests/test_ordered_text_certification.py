"""Independent persisted mixed-content truth through real MCP transports."""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import timedelta
from pathlib import Path
from subprocess import PIPE

import anyio
import pytest
from httpx import AsyncClient
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from ordered_text_fixture import EXPECTED_BLOCKS, EXPECTED_TEXT, truth_manifest


async def collect_ordered(client: ClientSession) -> None:
    await client.initialize()
    tool = next(t for t in (await client.list_tools()).tools if t.name == "get_document")
    assert set(tool.inputSchema["properties"]["mode"]["enum"]) == {"original", "text", "blocks"}
    identity = truth_manifest()
    scope = {key: identity[key] for key in ("notebook_id", "document_id", "version_id")}
    snapshots: dict[str, str] = {}
    for mode in ("blocks", "text"):
        for limit in (1, 3):
            args = {
                **scope,
                "mode": mode,
                "selector": {"kind": "full"},
                "max_items": limit,
                "max_bytes": 8192,
            }
            items = []
            while True:
                response = await client.call_tool("get_document", args)
                assert not response.isError, response
                data = response.structuredContent
                assert data and data["total_items"] == 12
                assert data["representation"] == f"parsed_{mode}/v1"
                snapshots.setdefault(mode, data["snapshot_identity"])
                assert snapshots[mode] == data["snapshot_identity"]
                assert 0 < len(data["items"]) <= limit
                for item in data["items"]:
                    assert item["index"] == len(items)
                    for key, value in scope.items():
                        assert item["attribution"][key] == value
                    assert item["attribution"]["source_id"] == identity["source_id"]
                    items.append(item)
                cursor = data["next_cursor"]
                if not cursor:
                    assert data["completeness"] == "complete"
                    break
                assert data["completeness"] == "truncated"
                # Replaying the same page is deterministic and does not consume state.
                repeated = await client.call_tool("get_document", args)
                assert repeated.structuredContent["items"] == data["items"]
                for changed in (
                    {"max_items": limit + 1},
                    {"max_bytes": 8193},
                    {"mode": "text" if mode == "blocks" else "blocks"},
                    {"selector": {"kind": "block_range", "start": 0, "end": 11}},
                ):
                    bad = await client.call_tool(
                        "get_document", {**args, **changed, "cursor": cursor}
                    )
                    assert bad.isError
                    assert bad.structuredContent["error"]["category"] == "invalid_input"
                tampered = await client.call_tool("get_document", {**args, "cursor": cursor + "x"})
                assert tampered.isError
                args["cursor"] = cursor
            assert len(items) == 12
            if mode == "text":
                text = "".join(
                    i["payload"]["text"] + i["payload"]["separator_after"] for i in items
                )
                assert text == EXPECTED_TEXT
                assert hashlib.sha256(text.encode()).hexdigest() == identity["text_sha256_utf8"]
            else:
                for item, expected in zip(items, EXPECTED_BLOCKS, strict=True):
                    assert item["kind"] == "canonical_block"
                    for key, value in expected.items():
                        if key != "kind":
                            assert item["payload"][key] == value
                    assert item["payload"]["ordinal"] == item["index"]
                    assert item["payload"]["page_number"] == item["index"] + 1


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["older", "newer"])
@pytest.mark.parametrize("transport", ["stdio", "sse"])
async def test_persisted_mixed_document_real_transports(
    tmp_path: Path, legacy: bool, transport: str
) -> None:
    child = Path(__file__).with_name(f"mcp_contract_{transport}_child.py")
    env = {k: v for k, v in os.environ.items() if not k.startswith("MNEMO_SERVER_")}
    args = [str(child), str(tmp_path), "older" if legacy else "newer", "ordered"]
    if transport == "stdio":
        async with (
            stdio_client(
                StdioServerParameters(command=sys.executable, args=args, env=env)
            ) as streams,
            ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client,
        ):
            await collect_ordered(client)
        return
    process = await anyio.open_process(
        [sys.executable, *args], stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env
    )
    try:
        assert process.stdout is not None
        with anyio.fail_after(30):
            line = b""
            while b"\n" not in line:
                line += await process.stdout.receive()
        assert line.startswith(b"PORT="), line
        port = int(line.split(b"\n", 1)[0].split(b"=", 1)[1])
        with anyio.fail_after(30):
            async with AsyncClient() as http:
                while True:
                    try:
                        if (await http.get(f"http://127.0.0.1:{port}/health")).status_code == 200:
                            break
                    except OSError:
                        pass
                    await anyio.sleep(0.05)
        async with (
            sse_client(
                f"http://127.0.0.1:{port}/sse",
                headers={"Authorization": "Bearer fixture-only-not-production"},
            ) as streams,
            ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client,
        ):
            await collect_ordered(client)
    finally:
        assert process.stdin is not None
        await process.stdin.send(b"\n")
        await process.stdin.aclose()
        with anyio.fail_after(30):
            assert await process.wait() == 0
