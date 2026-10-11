"""Opt-in real loopback HTTP probe of the certified immutable composition.

No corpus mutations and no credential output. This is not public-tunnel evidence.
The complete OpenAPI inventory is emitted as a machine-readable test manifest;
mutation operations require a separate disposable authorized server.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from mnemo_server.config import ServerConfig
from verify_completed_stage_mcp import (
    ASSET_DOCUMENT,
    ASSET_VERSION,
    CODE_DOCUMENT,
    NOTEBOOK,
    STRUCTURED_DOCUMENT,
    STRUCTURED_VERSION,
)


def probe(model_cache: str, final_qa: bool = False) -> None:
    os.environ["MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE"] = model_cache
    config = ServerConfig.from_env(certified_production=True)
    if config.auth_mode != "api-key" or not config.api_key:
        raise RuntimeError("This probe requires existing authorized API-key configuration")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    worker = subprocess.Popen(
        [sys.executable, __file__, "--model-cache", model_cache, "--worker-port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            headers={"X-API-Key": config.api_key},
            timeout=180,
            trust_env=False,
        ) as client:
            for _ in range(120):
                if worker.poll() is not None:
                    raise RuntimeError("Certified HTTP worker failed startup")
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Certified HTTP worker startup deadline exceeded")

            def call(
                method: str,
                path: str,
                *,
                expected: tuple[int, ...] = (200,),
                **kwargs: Any,
            ) -> dict[str, Any]:
                start = datetime.now(UTC).isoformat()
                response = client.request(method, path, **kwargs)
                payload = (
                    response.json()
                    if "application/json" in response.headers.get("content-type", "")
                    else {}
                )
                print(
                    json.dumps(
                        {
                            "transport": "real_loopback_certified_http",
                            "method": method,
                            "path": path,
                            "start_utc": start,
                            "end_utc": datetime.now(UTC).isoformat(),
                            "status": response.status_code,
                            "request_id": response.headers.get("x-request-id"),
                            "error": payload.get("error"),
                            "completeness": payload.get("completeness"),
                            "result_status": payload.get("status"),
                            "citation_count": len(payload.get("citations", [])),
                            "replayed": payload.get("replayed"),
                            "answer_termination": payload.get("coverage", {}).get(
                                "answer_termination"
                            ),
                            "retrieval_metadata": payload.get("retrieval_metadata"),
                            "citation_chunk_ids": [
                                item.get("chunk_id") for item in payload.get("citations", [])
                            ],
                            "item_count": len(payload.get("items", [])),
                            "content_type": response.headers.get("content-type"),
                            "returned_bytes": len(response.content),
                        }
                    ),
                    flush=True,
                )
                assert response.status_code in expected, (method, path, response.status_code)
                return payload

            spec = client.get("/openapi.json").json()
            print(
                json.dumps(
                    {
                        "openapi_manifest": [
                            {
                                "method": method.upper(),
                                "path": path,
                                "operation_id": operation.get("operationId"),
                                "responses": sorted(operation.get("responses", {})),
                                "request_schema": operation.get("requestBody"),
                                "parameters": operation.get("parameters", []),
                                "production_probe": "read_only_only",
                            }
                            for path, methods in spec["paths"].items()
                            for method, operation in methods.items()
                            if method in {"get", "post", "patch", "delete", "put"}
                        ]
                    }
                ),
                flush=True,
            )
            call("GET", "/v2/capabilities")
            call("GET", "/v2/capabilities", params={"notebook_id": NOTEBOOK})
            call("GET", "/v1/notebooks")
            for suffix in ("", "/sources", "/summary", "/timeline", "/insights", "/graph"):
                call("GET", f"/v1/notebooks/{NOTEBOOK}{suffix}")
            request = {
                "query": "buildCodePrompt",
                "mode": "exhaustive",
                "scope": {"notebook_id": NOTEBOOK, "document_ids": [CODE_DOCUMENT]},
                "representations": ["canonical_text"],
                "candidate_budget": 3,
                "evidence_budget": 1,
                "max_content_characters": 2000,
            }
            first = call("POST", "/v2/retrieval/evidence", json=request)
            assert first["items"] and first["next_cursor"]
            second = call(
                "POST", "/v2/retrieval/evidence", json={**request, "cursor": first["next_cursor"]}
            )
            assert second["items"] and second["next_cursor"] is None
            conflict = call(
                "POST",
                "/v2/retrieval/evidence",
                expected=(409,),
                json={**request, "cursor": first["next_cursor"], "candidate_budget": 4},
            )
            assert conflict["error"]["code"] == "cursor.conflict"
            item = first["items"][0]
            for count in (1, 5):
                call(
                    "POST",
                    "/v1/query",
                    json={
                        "notebook_id": NOTEBOOK,
                        "question": "buildCodePrompt",
                        "retrieval_config": {"top_k": count},
                        "synthesis": {"enabled": False},
                    },
                )
            call(
                "POST",
                "/v1/query",
                json={
                    "notebook_id": NOTEBOOK,
                    "question": "buildCodePrompt",
                    "retrieval_config": {
                        "top_k": 5,
                        "filters": {"source_ids": [item["source_id"]]},
                    },
                    "synthesis": {"enabled": False},
                },
            )
            base = (
                f"/v2/notebooks/{NOTEBOOK}/documents/{item['document_id']}"
                f"/versions/{item['version_id']}"
            )
            call("GET", f"{base}/chunks/{item['chunk_id']}")
            small = {**request, "max_content_characters": 80}
            small_first = call("POST", "/v2/retrieval/evidence", json=small)
            call(
                "POST",
                "/v2/retrieval/evidence",
                expected=(422,),
                json={**small, "cursor": small_first["next_cursor"]},
            )
            call(
                "POST",
                "/v2/retrieval/evidence",
                expected=(422,),
                json={**request, "candidate_budget": True},
            )
            call(
                "POST",
                "/v2/retrieval/structured",
                json={
                    "operation": "describe",
                    "scope": {
                        "notebook_id": NOTEBOOK,
                        "document_ids": [STRUCTURED_DOCUMENT],
                        "version_ids": [STRUCTURED_VERSION],
                    },
                    "page_size": 1,
                },
            )
            assets_base = (
                f"/v2/notebooks/{NOTEBOOK}/documents/{ASSET_DOCUMENT}/versions/{ASSET_VERSION}"
            )
            assets = call("GET", f"{assets_base}/assets", params={"limit": 1})
            occurrence = assets["items"][0]["attribution"]["occurrence_id"]
            call("GET", f"{assets_base}/original", expected=(206,), params={"max_bytes": 1024})
            call(
                "GET",
                f"/v2/notebooks/{NOTEBOOK}/asset-occurrences/{occurrence}/content",
                expected=(206,),
                params={"max_bytes": 1024},
            )
            call(
                "GET",
                f"/v2/notebooks/{NOTEBOOK}/asset-occurrences/{occurrence}/analysis",
                params={"selection": "latest_ready"},
            )
            if final_qa:
                assistant_turn = str(uuid4())
                qa_request = {
                    "notebook_id": NOTEBOOK,
                    "session_id": str(uuid4()),
                    "user_turn_id": str(uuid4()),
                    "assistant_turn_id": assistant_turn,
                    "question": "buildCodePrompt",
                    "evidence_request_or_snapshot": {
                        **request,
                        "evidence_budget": 3,
                        "max_content_characters": 4000,
                    },
                    "provider_profile": "final_qa_v2:gemma4:e4b",
                    "max_output_tokens": 1024,
                }
                qa = call("POST", f"/v2/notebooks/{NOTEBOOK}/final-qa", json=qa_request)
                assert qa["status"] == "citation_resolved" and qa["citations"]
                replay = call("POST", f"/v2/notebooks/{NOTEBOOK}/final-qa", json=qa_request)
                assert replay["replayed"] and replay["execution_id"] == qa["execution_id"]
                call("GET", f"/v2/notebooks/{NOTEBOOK}/final-qa/{assistant_turn}/evidence")
            unauthenticated = httpx.get(f"http://127.0.0.1:{port}/v2/capabilities", trust_env=False)
            print(
                json.dumps(
                    {
                        "transport": "real_loopback_http",
                        "negative": "missing_authentication",
                        "status": unauthenticated.status_code,
                    }
                ),
                flush=True,
            )
            assert unauthenticated.status_code == 401
    finally:
        worker.terminate()
        worker.wait(timeout=30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-cache", required=True)
    parser.add_argument("--worker-port", type=int)
    parser.add_argument("--sse-worker", action="store_true")
    parser.add_argument("--final-qa", action="store_true")
    args = parser.parse_args()
    if args.worker_port:
        import uvicorn
        from mnemo_server.app import create_app
        from mnemo_server.mcp.server import create_sse_app

        os.environ["MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE"] = args.model_cache
        worker_config = ServerConfig.from_env(certified_production=True)
        application = (
            create_sse_app(config=worker_config) if args.sse_worker else create_app(worker_config)
        )
        uvicorn.run(
            application,
            host="127.0.0.1",
            port=args.worker_port,
            log_level="error",
            access_log=False,
        )
    else:
        probe(args.model_cache, args.final_qa)
