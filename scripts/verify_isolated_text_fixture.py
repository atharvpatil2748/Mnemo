"""Authenticated network MCP reconstruction against independent fixture truth.

Never logs authentication material. Raw page receipts remain in ignored scratch.
This is an external-style HTTP client, not an external ChatGPT certification.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mnemo_server.config import ServerConfig


async def verify(url: str, manifest_path: Path, receipts: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = ServerConfig.from_env(certified_production=True)
    if not config.api_key or config.auth_mode != "api-key":
        raise ValueError("existing owner authentication required")
    if not (
        url.startswith("http://127.0.0.1:")
        or url.startswith("https://")
        or url == "stdio://fixture"
    ):
        raise ValueError("loopback or HTTPS endpoint required")
    receipts.mkdir(parents=True, exist_ok=False)
    evidence = {
        "start_utc": datetime.now(UTC).isoformat(),
        "endpoint": url,
        "transport": ("external_https" if url.startswith("https:") else "loopback")
        + ("_streamable_http" if "/mcp" in url else "_sse"),
        "traversals": [],
        "negative_calls": 0,
    }
    if url != "stdio://fixture":
        async with httpx.AsyncClient(timeout=20) as http:
            assert (await http.get(url)).status_code == 401
            assert (
                await http.get(url, headers={"Authorization": "Bearer incorrect-test-key"})
            ).status_code == 401
    scope = {key: manifest[key] for key in ("notebook_id", "document_id", "version_id")}
    headers = {"Authorization": f"Bearer {config.api_key}"}
    authenticated_http = httpx.AsyncClient(headers=headers, timeout=30)
    transport = (
        streamable_http_client(url, http_client=authenticated_http)
        if "/mcp" in url
        else sse_client(url, headers=headers)
    )
    if url == "stdio://fixture":
        evidence["transport"] = "real_isolated_stdio"
        transport = stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=[
                    str(Path(__file__).with_name("serve_ordered_text_fixture.py")),
                    "stdio",
                    "--root",
                    str(manifest_path.parent.resolve()),
                ],
                env=dict(os.environ),
            )
        )
    async with (
        authenticated_http,
        transport as streams,
        ClientSession(*streams[:2], read_timeout_seconds=timedelta(seconds=30)) as client,
    ):
        await client.initialize()
        tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == {"get_capabilities", "get_document", "list_notebooks"}
        schema = next(t.inputSchema for t in tools if t.name == "get_document")
        assert set(schema["properties"]["mode"]["enum"]) == {"text", "blocks", "original"}
        evidence["mode_enum"] = schema["properties"]["mode"]["enum"]
        global_caps = await client.call_tool("get_capabilities", {})
        assert not global_caps.isError, global_caps
        evidence["global_capabilities"] = global_caps.structuredContent
        caps = await client.call_tool("get_capabilities", {"notebook_id": scope["notebook_id"]})
        assert not caps.isError, caps
        evidence["capabilities"] = caps.structuredContent
        inventory = await client.call_tool("list_notebooks", {"limit": 1})
        assert not inventory.isError, inventory
        assert inventory.structuredContent["notebooks"][0]["document_id"] == scope["document_id"]
        for mode in ("blocks", "text"):
            for limit in (1, 3):
                args = {
                    **scope,
                    "mode": mode,
                    "selector": {"kind": "full"},
                    "max_items": limit,
                    "max_bytes": 8192,
                }
                collected = []
                snapshots = set()
                pages = 0
                request_ids = []
                while True:
                    result = await client.call_tool("get_document", args)
                    assert not result.isError, result
                    data = result.structuredContent
                    assert data["total_items"] == manifest["total_items"]
                    assert data["representation"] == f"parsed_{mode}/v1"
                    snapshots.add(data["snapshot_identity"])
                    assert len(snapshots) == 1
                    request_ids.append(data["request_id"])
                    pages += 1
                    (receipts / f"{mode}-{limit}-{pages:02}.json").write_text(
                        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    for item in data["items"]:
                        assert item["index"] == len(collected)
                        for key, value in scope.items():
                            assert item["attribution"][key] == value
                        assert item["attribution"]["source_id"] == manifest["source_id"]
                        collected.append(item)
                    replay = await client.call_tool("get_document", args)
                    assert replay.structuredContent["items"] == data["items"]
                    cursor = data["next_cursor"]
                    if not cursor:
                        assert data["completeness"] == "complete"
                        break
                    assert data["completeness"] == "truncated"
                    if pages == 1:
                        for changed in (
                            {"max_items": limit + 1},
                            {"max_bytes": 8193},
                            {"mode": "text" if mode == "blocks" else "blocks"},
                            {"selector": {"kind": "block_range", "start": 0, "end": 11}},
                            {"document_id": "00000000-0000-0000-0000-000000000099"},
                            {"version_id": "00000000-0000-0000-0000-000000000099"},
                        ):
                            bad = await client.call_tool(
                                "get_document", {**args, **changed, "cursor": cursor}
                            )
                            assert bad.isError, changed
                            evidence["negative_calls"] += 1
                        bad = await client.call_tool(
                            "get_document", {**args, "cursor": cursor + "x"}
                        )
                        assert bad.isError
                        evidence["negative_calls"] += 1
                    args["cursor"] = cursor
                assert len(collected) == 12
                if mode == "text":
                    actual = "".join(
                        i["payload"]["text"] + i["payload"]["separator_after"] for i in collected
                    )
                    assert actual.encode() == manifest["expected_text"].encode()
                    digest = hashlib.sha256(actual.encode()).hexdigest()
                    assert digest == manifest["text_sha256_utf8"]
                else:
                    fields = []
                    for item, expected in zip(collected, manifest["expected_blocks"], strict=True):
                        assert item["kind"] == "canonical_block"
                        assert item["payload"]["ordinal"] == item["index"]
                        assert item["payload"]["page_number"] == item["index"] + 1
                        for key, value in expected.items():
                            if key != "kind":
                                assert item["payload"][key] == value
                        fields.append(expected)
                    digest = hashlib.sha256(
                        json.dumps(
                            fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest()
                    assert digest == manifest["block_fields_sha256"]
                evidence["traversals"].append(
                    {
                        "mode": mode,
                        "max_items": limit,
                        "pages": pages,
                        "total_items": len(collected),
                        "sha256": digest,
                        "snapshot": next(iter(snapshots)),
                        "request_ids": request_ids,
                    }
                )
    evidence["end_utc"] = datetime.now(UTC).isoformat()
    (receipts / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence))
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.manifest, args.receipts))
