"""Read-only certified MCP reconstruction probe; stores actual received ranges.

Not external ChatGPT evidence. Credentials stay in the approved environment.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mnemo_server.config import ServerConfig
from PIL import Image

NOTEBOOK = "df9c20cf-85fe-529c-902e-2e9e68193fbe"
DOCUMENT = "135b4fd5-15cd-5a22-89db-096dcc9b55bc"
VERSION = "d49eb763-3bf3-54d1-aec4-bfd66ca43fe8"
OCCURRENCE = "7c31fd63-a975-51f3-bc27-0a6505649ffe"
IMAGE_HASH = "cab6378eeb056237af3b785d9421e8fb0c6c889b730b37e719dcea8247acb19a"


async def probe(cache: str, sse_url: str | None, adjacent_only: bool = False) -> None:
    env = dict(os.environ)
    env["MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE"] = cache
    if sse_url:
        if not sse_url.startswith("http://127.0.0.1:"):
            raise ValueError("Only authorized loopback SSE is supported by this probe")
        os.environ["MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE"] = cache
        config = ServerConfig.from_env(certified_production=True)
        transport = sse_client(sse_url, headers={"X-API-Key": config.api_key or ""})
    else:
        transport = stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "mnemo_server.mcp.cli", "certified-stdio"],
                env=env,
            )
        )
    output = Path(tempfile.mkdtemp(prefix="mnemo-reconstruction-"))
    manifest: dict[str, Any] = {
        "transport": "real_loopback_sse" if sse_url else "real_certified_stdio",
        "start_utc": datetime.now(UTC).isoformat(),
        "resources": {},
    }
    async with transport as (reader, writer), ClientSession(reader, writer) as client:
        await client.initialize()
        tools = (await client.list_tools()).tools
        manifest["tools"] = [tool.name for tool in tools]
        document_tool = next(tool for tool in tools if tool.name == "get_document")
        manifest["get_document_input_schema"] = document_tool.inputSchema
        assert set(document_tool.inputSchema["properties"]["mode"]["enum"]) == {
            "original",
            "blocks",
            "text",
        }
        if adjacent_only:
            observed = []
            for name, request in (
                (
                    "get_document",
                    {
                        "notebook_id": NOTEBOOK,
                        "document_id": DOCUMENT,
                        "version_id": VERSION,
                        "mode": "original",
                        "max_bytes": 524288,
                    },
                ),
                (
                    "get_asset",
                    {
                        "notebook_id": NOTEBOOK,
                        "occurrence_id": OCCURRENCE,
                        "max_bytes": 65536,
                        "binary_format": "resource",
                    },
                ),
            ):
                position = 0
                for page in range(2):
                    result = await client.call_tool(name, request)
                    assert not result.isError
                    resource = result.content[0].resource
                    received = base64.b64decode(resource.blob, validate=True)
                    meta = resource.meta
                    public = result.structuredContent["resource"]
                    for key in (
                        "rangeStart",
                        "rangeEnd",
                        "rangeEndExclusive",
                        "returnedBytes",
                        "totalBytes",
                        "contentHash",
                        "snapshotIdentity",
                        "originalMediaType",
                        "notebookId",
                        "sourceId",
                        "documentId",
                        "versionId",
                        "completeness",
                        "nextCursor",
                    ):
                        assert public[key] == meta[key]
                    assert type(public["rangeStart"]) is int
                    assert type(public["rangeEnd"]) is int
                    assert public["rangeEndExclusive"] is True
                    assert public["rangeStart"] == position
                    position += len(received)
                    assert public["rangeEnd"] == position
                    assert public["returnedBytes"] == len(received)
                    assert public["notebookId"] == NOTEBOOK
                    assert public["documentId"] == DOCUMENT and public["versionId"] == VERSION
                    assert public["contentHash"] == (
                        "eb4fe330163f7d89535ca48f792204a16da042bb2e4895a6030102df20a63984"
                        if name == "get_document"
                        else IMAGE_HASH
                    )
                    observed.append(
                        {
                            "tool": name,
                            "page": page + 1,
                            "metadata": {k: v for k, v in public.items() if k != "nextCursor"},
                        }
                    )
                    request["cursor"] = public["nextCursor"]
                    assert request["cursor"]
                bad = await client.call_tool(
                    name, {**request, "max_bytes": request["max_bytes"] + 1}
                )
                assert bad.isError
            unavailable = []
            for document, version in (
                (DOCUMENT, VERSION),
                ("8abc6c73-7d1c-5248-8c28-4157de5ca51a", "7882f1db-a197-5c84-9b10-66b1fe2d3689"),
            ):
                for mode in ("blocks", "text"):
                    result = await client.call_tool(
                        "get_document",
                        {
                            "notebook_id": NOTEBOOK,
                            "document_id": document,
                            "version_id": version,
                            "mode": mode,
                            "selector": {"kind": "full"},
                            "max_items": 3,
                            "max_bytes": 8192,
                        },
                    )
                    assert result.isError
                    data = json.loads(result.content[0].text)
                    assert data["error"]["code"] == "delivery.representation_unavailable"
                    unavailable.append(
                        {"document_id": document, "mode": mode, "error": data["error"]}
                    )
            print(
                json.dumps(
                    {
                        "result": "PASS",
                        "transport": manifest["transport"],
                        "ranges": observed,
                        "production_representations": unavailable,
                    }
                ),
                flush=True,
            )
            return

        async def transfer(name: str, args: dict[str, Any], label: str) -> bytes:
            ranges: list[dict[str, Any]] = []
            pieces: list[bytes] = []
            cursor = None
            position = 0
            digest = None
            snapshot = None
            for index in range(100):
                request = {**args, **({"cursor": cursor} if cursor else {})}
                started = datetime.now(UTC).isoformat()
                result = await client.call_tool(name, request)
                ended = datetime.now(UTC).isoformat()
                assert not result.isError, result.content
                assert len(result.content) == 1
                block = result.content[0]
                if block.type == "resource":
                    assert hasattr(block.resource, "blob")
                    raw = base64.b64decode(block.resource.blob, validate=True)
                    meta = block.resource.meta or {}
                else:
                    assert block.type == "image"
                    raw = base64.b64decode(block.data, validate=True)
                    meta = block.meta or {}
                assert meta["rangeStart"] == position
                assert meta["rangeEnd"] == position + len(raw)
                assert meta["rangeEndExclusive"] is True
                assert meta["returnedBytes"] == len(raw)
                structured = (result.structuredContent or {}).get("resource", {})
                for key in (
                    "rangeStart",
                    "rangeEnd",
                    "rangeEndExclusive",
                    "returnedBytes",
                    "totalBytes",
                    "contentHash",
                    "snapshotIdentity",
                    "originalMediaType",
                    "notebookId",
                    "sourceId",
                    "documentId",
                    "versionId",
                    "completeness",
                    "nextCursor",
                ):
                    assert structured[key] == meta[key], key
                assert meta["originalMediaType"] == (
                    "application/pdf" if label.startswith("pdf") else "image/jpeg"
                )
                assert meta["notebookId"] == NOTEBOOK
                assert meta["documentId"] == DOCUMENT and meta["versionId"] == VERSION
                digest = digest or meta["contentHash"]
                snapshot = snapshot or meta["snapshotIdentity"]
                assert digest == meta["contentHash"] and snapshot == meta["snapshotIdentity"]
                path = output / f"{label}-{index:03}.bin"
                path.write_bytes(raw)
                pieces.append(path.read_bytes())
                ranges.append(
                    {
                        "start": position,
                        "end_exclusive": position + len(raw),
                        "received_bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "file": str(path),
                        "completeness": meta["completeness"],
                        "start_utc": started,
                        "end_utc": ended,
                        "request_id": (result.structuredContent or {}).get("request_id"),
                        "original_media_type": meta["originalMediaType"],
                    }
                )
                position += len(raw)
                cursor = meta["nextCursor"]
                if cursor is None:
                    assert meta["completeness"] == "complete"
                    assert position == meta["totalBytes"]
                    break
                assert meta["completeness"] == "truncated" and raw
            else:
                raise AssertionError("Traversal did not terminate")
            reconstructed = b"".join(pieces)
            assert hashlib.sha256(reconstructed).hexdigest() == digest
            (output / f"{label}-complete.bin").write_bytes(reconstructed)
            manifest["resources"][label] = {
                "bytes": position,
                "sha256": digest,
                "snapshot": snapshot,
                "notebook_id": NOTEBOOK,
                "document_id": DOCUMENT,
                "version_id": VERSION,
                "occurrence_id": args.get("occurrence_id"),
                "ranges": ranges,
            }
            return reconstructed

        doc_args = {
            "notebook_id": NOTEBOOK,
            "document_id": DOCUMENT,
            "version_id": VERSION,
            "mode": "original",
        }
        pdf = await transfer("get_document", {**doc_args, "max_bytes": 4_000_000}, "pdf-one")
        multipart = await transfer("get_document", {**doc_args, "max_bytes": 524288}, "pdf-parts")
        assert pdf == multipart and len(pdf) == 3821824 and pdf.startswith(b"%PDF-")
        assert len(manifest["resources"]["pdf-parts"]["ranges"]) >= 5
        parsed = pymupdf.open(stream=pdf, filetype="pdf")
        assert len(parsed) == 6
        asset_args = {"notebook_id": NOTEBOOK, "occurrence_id": OCCURRENCE}
        jpeg = await transfer("get_asset", {**asset_args, "max_bytes": 1000000}, "jpeg-one")
        resource = await transfer(
            "get_asset",
            {**asset_args, "max_bytes": 1000000, "binary_format": "resource"},
            "jpeg-resource",
        )
        parts = await transfer("get_asset", {**asset_args, "max_bytes": 65536}, "jpeg-parts")
        assert jpeg == parts == resource and len(jpeg) == 704901
        assert hashlib.sha256(jpeg).hexdigest() == IMAGE_HASH
        with Image.open(io.BytesIO(jpeg)) as image:
            assert image.format == "JPEG" and image.size == (3576, 2512)
            image.load()
        extracted = [
            parsed.extract_image(entry[0])["image"] for entry in parsed[0].get_images(full=True)
        ]
        assert jpeg in extracted
        parsed.close()
        manifest["pdf_pages"] = 6
        manifest["jpeg_dimensions"] = [3576, 2512]
        manifest["pdf_extracted_jpeg_identical"] = True
        analysis_result = await client.call_tool(
            "get_image_analysis",
            {
                **asset_args,
                "selection": "latest_ready",
                "modalities": ["ocr", "vision"],
            },
        )
        assert not analysis_result.isError
        analysis_block = analysis_result.content[0]
        assert analysis_block.type == "text"
        analysis = json.loads(analysis_block.text)
        assert analysis["completeness"] == "complete" and len(analysis["items"]) == 2
        for item in analysis["items"]:
            attribution = item["attribution"]
            assert attribution["occurrence_id"] == OCCURRENCE
            assert attribution["document_id"] == DOCUMENT and attribution["version_id"] == VERSION
            assert attribution["derivation_id"] and attribution["generation_id"]
            assert item["payload"]
        (output / "persisted-analysis.json").write_text(analysis_block.text, encoding="utf-8")
        manifest["analysis"] = {
            "completeness": analysis["completeness"],
            "request_id": analysis.get("request_id"),
            "records": [
                {
                    "kind": item["kind"],
                    "attribution": item["attribution"],
                    "bytes": item["byte_size"],
                    "regions": len(item["payload"].get("regions", [])),
                    "observations": len(item["payload"].get("observations", [])),
                }
                for item in analysis["items"]
            ],
        }
        for document_id, version_id in (
            (DOCUMENT, VERSION),
            ("8abc6c73-7d1c-5248-8c28-4157de5ca51a", "7882f1db-a197-5c84-9b10-66b1fe2d3689"),
        ):
            for mode in ("blocks", "text"):
                result = await client.call_tool(
                    "get_document",
                    {
                        "notebook_id": NOTEBOOK,
                        "document_id": document_id,
                        "version_id": version_id,
                        "mode": mode,
                        "selector": {"kind": "full"},
                        "max_items": 20,
                        "max_bytes": 50000,
                    },
                )
                assert result.isError
                block = result.content[0]
                assert block.type == "text"
                payload = json.loads(block.text)
                manifest.setdefault("representation_errors", []).append(
                    {
                        "document_id": document_id,
                        "mode": mode,
                        "error": payload.get("error"),
                        "request_id": payload.get("request_id"),
                    }
                )
    manifest["end_utc"] = datetime.now(UTC).isoformat()
    destination = output / "transfer-manifest.json"
    destination.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": str(destination),
                "result": "PASS",
                "pdf_sha256": manifest["resources"]["pdf-one"]["sha256"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-cache", required=True)
    parser.add_argument("--sse-url")
    parser.add_argument("--adjacent-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(probe(args.model_cache, args.sse_url, args.adjacent_only))
