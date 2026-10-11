"""Explicit, sanitized certified-stdio acceptance probe (never a CI default).

Read-only except --final-qa, which publishes one bounded answer to the governed
operational store, not the immutable corpus. It does not certify the tunnel.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mnemo_server.config import ServerConfig

NOTEBOOK = "df9c20cf-85fe-529c-902e-2e9e68193fbe"
CODE_DOCUMENT = "8abc6c73-7d1c-5248-8c28-4157de5ca51a"
ASSET_DOCUMENT = "135b4fd5-15cd-5a22-89db-096dcc9b55bc"
ASSET_VERSION = "d49eb763-3bf3-54d1-aec4-bfd66ca43fe8"
STRUCTURED_DOCUMENT = "092b9610-05e6-54f4-bb3f-ea8b4544a25f"
STRUCTURED_VERSION = "2190addb-b826-586f-b2be-65962e520068"


async def probe(model_cache: str, final_qa: bool, sse_url: str | None = None) -> None:
    env = dict(os.environ)
    env["MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE"] = model_cache
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mnemo_server.mcp.cli", "certified-stdio"],
        env=env,
    )
    if sse_url:
        if not sse_url.startswith("http://127.0.0.1:"):
            raise ValueError("This operator probe supports isolated loopback SSE only")
        os.environ["MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE"] = model_cache
        config = ServerConfig.from_env(certified_production=True)
        if config.auth_mode != "api-key" or not config.api_key:
            raise RuntimeError("Existing authorized API-key configuration required")
        transport = sse_client(sse_url, headers={"X-API-Key": config.api_key})
    else:
        transport = stdio_client(params)
    label = "real_loopback_certified_sse" if sse_url else "local_certified_stdio"
    async with transport as (reader, writer), ClientSession(reader, writer) as client:
        await client.initialize()
        print(
            json.dumps(
                {
                    "transport": label,
                    "tools": [tool.name for tool in (await client.list_tools()).tools],
                }
            ),
            flush=True,
        )

        async def call(
            name: str, args: dict[str, Any], *, expected_error: bool = False
        ) -> dict[str, Any]:
            start = datetime.now(UTC).isoformat()
            result = await client.call_tool(name, args)
            payload: dict[str, Any] = {}
            resources: list[dict[str, Any]] = []
            for block in result.content:
                if block.type == "text":
                    value = json.loads(block.text)
                    if isinstance(value, dict):
                        payload = value
                elif block.type == "resource" and hasattr(block.resource, "blob"):
                    resources.append(
                        {
                            "type": "binary_resource",
                            "mime_type": block.resource.mimeType,
                            "returned_bytes": len(base64.b64decode(block.resource.blob)),
                            "metadata_keys": sorted((block.resource.meta or {}).keys()),
                        }
                    )
                else:
                    resources.append({"type": block.type})
            print(
                json.dumps(
                    {
                        "tool": name,
                        "transport": label,
                        "arguments": {
                            key: "<opaque cursor omitted>" if key == "cursor" else value
                            for key, value in args.items()
                        },
                        "start_utc": start,
                        "end_utc": datetime.now(UTC).isoformat(),
                        "is_error": result.isError,
                        "request_id": payload.get("request_id"),
                        "error": payload.get("error"),
                        "completeness": payload.get("completeness"),
                        "item_count": len(payload.get("items", [])),
                        "status": payload.get("status"),
                        "answer_present": bool(payload.get("answer")),
                        "citation_count": len(payload.get("citations", [])),
                        "retrieval_metadata": payload.get("retrieval_metadata"),
                        "citation_chunk_ids": [
                            item.get("chunk_id") for item in payload.get("citations", [])
                        ],
                        "answer_termination": payload.get("coverage", {}).get("answer_termination"),
                        "resources": resources,
                        "top_level_keys": sorted(payload),
                        "capability_states": [
                            {
                                "id": capability["capability_id"],
                                "lifecycle": capability["lifecycle"],
                                "reason": capability.get("unavailable_reason"),
                                "modalities": capability.get("supported_modalities"),
                            }
                            for capability in payload.get("capabilities", [])
                            if capability["capability_id"]
                            in {
                                "document_delivery",
                                "asset_delivery",
                                "exact_retrieval",
                                "final_qa_v2",
                                "multimodal_retrieval",
                                "ocr",
                            }
                        ],
                    }
                ),
                flush=True,
            )
            assert bool(result.isError) == expected_error, (name, payload.get("error"))
            return payload

        await call("get_capabilities", {})
        await call("list_notebooks", {"limit": 1})
        await call("get_capabilities", {"notebook_id": NOTEBOOK})
        await call("get_notebook_summary", {"notebook_id": NOTEBOOK})
        await call("get_timeline", {"notebook_id": NOTEBOOK, "limit": 1})
        await call("search_all_notebooks", {"query": "buildCodePrompt", "top_k": 1})
        request: dict[str, Any] = {
            "query": "buildCodePrompt",
            "mode": "exhaustive",
            "scope": {"notebook_id": NOTEBOOK, "document_ids": [CODE_DOCUMENT]},
            "representations": ["canonical_text"],
            "candidate_budget": 3,
            "evidence_budget": 1,
            "max_content_characters": 2000,
        }
        first = await call("search_evidence", request)
        if first.get("next_cursor"):
            await call("search_evidence", {**request, "cursor": first["next_cursor"]})
            conflict = await call(
                "search_evidence",
                {**request, "cursor": first["next_cursor"], "candidate_budget": 4},
                expected_error=True,
            )
            assert conflict["error"]["code"] == "cursor.conflict"
            token = first["next_cursor"]
            await call(
                "search_evidence",
                {**request, "cursor": ("a" if token[0] != "a" else "b") + token[1:]},
                expected_error=True,
            )
        for count in (1, 5):
            await call(
                "query_notebook",
                {
                    "notebook_id": NOTEBOOK,
                    "question": "buildCodePrompt",
                    "top_k": count,
                    "synthesize": False,
                },
            )
        if first.get("items"):
            item = first["items"][0]
            await call("get_source_insights", {"source_id": item["source_id"], "limit": 1})
            await call(
                "get_document_chunk",
                {
                    "notebook_id": NOTEBOOK,
                    "document_id": item["document_id"],
                    "version_id": item["version_id"],
                    "chunk_id": item["chunk_id"],
                },
            )
        else:
            print(
                json.dumps(
                    {
                        "uninvoked": ["get_source_insights", "get_document_chunk"],
                        "reason": "authorized evidence fixture absent",
                    }
                ),
                flush=True,
            )
        await call(
            "query_notebook",
            {
                "notebook_id": NOTEBOOK,
                "question": "buildCodePrompt",
                "top_k": 1,
                "synthesize": True,
            },
        )
        description = await call(
            "query_structured",
            {
                "operation": "describe",
                "scope": {
                    "notebook_id": NOTEBOOK,
                    "document_ids": [STRUCTURED_DOCUMENT],
                    "version_ids": [STRUCTURED_VERSION],
                },
                "page_size": 1,
            },
        )
        if description.get("items"):
            dataset = description["items"][0]
            structured_query = {
                "operation": "query",
                "scope": description["scope"],
                "dataset_ids": [dataset["dataset_id"]],
                "page_size": 1,
            }
            # The response scope contains the same public canonical scope fields.
            structured_query["scope"] = {
                "notebook_id": NOTEBOOK,
                "document_ids": [STRUCTURED_DOCUMENT],
                "version_ids": [STRUCTURED_VERSION],
            }
            page = await call("query_structured", structured_query)
            if page.get("next_cursor"):
                await call("query_structured", {**structured_query, "cursor": page["next_cursor"]})
            string_field = next(
                (field for field in dataset["fields"] if field["field_type"] == "string"), None
            )
            if string_field:
                await call(
                    "query_structured",
                    {
                        **structured_query,
                        "filters": [
                            {
                                "field": string_field["name"],
                                "operator": "eq",
                                "value": "mnemo-probe-no-match-" + str(uuid4()),
                            }
                        ],
                    },
                )
        assets = await call(
            "get_asset",
            {
                "notebook_id": NOTEBOOK,
                "document_id": ASSET_DOCUMENT,
                "version_id": ASSET_VERSION,
                "limit": 1,
            },
        )
        if assets.get("items"):
            item = assets["items"][0]
            occurrence = item["attribution"]["occurrence_id"]
            await call(
                "get_asset",
                {"notebook_id": NOTEBOOK, "occurrence_id": occurrence, "max_bytes": 1024},
            )
            await call(
                "get_image_analysis",
                {"notebook_id": NOTEBOOK, "occurrence_id": occurrence, "selection": "latest_ready"},
            )
        await call(
            "get_document",
            {
                "notebook_id": NOTEBOOK,
                "document_id": ASSET_DOCUMENT,
                "version_id": ASSET_VERSION,
                "mode": "original",
                "max_bytes": 1024,
            },
        )
        if final_qa:
            qa_args = {
                "notebook_id": NOTEBOOK,
                "session_id": str(uuid4()),
                "user_turn_id": str(uuid4()),
                "assistant_turn_id": str(uuid4()),
                "question": "buildCodePrompt",
                "evidence_request_or_snapshot": {
                    **request,
                    "evidence_budget": 3,
                    "max_content_characters": 4000,
                },
                "provider_profile": "final_qa_v2:gemma4:e4b",
                "max_output_tokens": 1024,
            }
            result = await call("run_final_qa_v2", qa_args)
            assert result["coverage"]["answer_termination"]["complete"] is True
            replay = await call("run_final_qa_v2", qa_args)
            assert replay["replayed"] and replay["execution_id"] == result["execution_id"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-cache", required=True)
    parser.add_argument("--final-qa", action="store_true")
    parser.add_argument("--sse-url")
    arguments = parser.parse_args()
    asyncio.run(probe(arguments.model_cache, arguments.final_qa, arguments.sse_url))
