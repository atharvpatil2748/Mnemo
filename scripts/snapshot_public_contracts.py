"""Capture registered contracts without entering lifespan or opening storage.

This is a review artifact, not an external-transport or readiness attestation.
Run with the repository interpreter; replacement requires an explicit flag.
"""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute, iter_route_contexts
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import get_mcp_route_contracts, get_mcp_tools
from mnemo_server.schemas.query import QueryRequest
from mnemo_server.schemas.scope_contract_review import ScopeRequestReview, ScopeResponseReview
from mnemo_server.schemas.search import SearchRequest


def capture_contracts() -> dict[str, Any]:
    # Ephemeral configuration only; never load operator credentials or enter lifespan.
    app = create_app(
        server_config=ServerConfig(
            production_mode=True, delivery_cursor_secret=secrets.token_hex(32)
        )
    )
    routes = get_mcp_route_contracts()
    return {
        "schema": "mnemo.public-contract-inventory/1",
        "evidence": "registration-only; no lifespan, database, or external request",
        "mcp": [
            {
                "tool": tool.model_dump(mode="json", exclude_none=True),
                "backend": routes[tool.name].backend.value,
                "scope": routes[tool.name].auth_scope,
                "handler": (
                    f"{routes[tool.name].handler.__module__}.{routes[tool.name].handler.__name__}"
                ),
            }
            for tool in sorted(get_mcp_tools(), key=lambda item: item.name)
        ],
        "http": [
            {
                "path": route.path,
                "methods": sorted(route.methods or ()),
                "endpoint": f"{route.endpoint.__module__}.{route.endpoint.__name__}",
                "dependencies": [
                    f"{dep.call.__module__}.{dep.call.__name__}"
                    for dep in route.dependant.dependencies
                    if dep.call is not None
                ],
            }
            for route in iter_route_contexts(app.routes)
            if isinstance(route.original_route, APIRoute) and route.endpoint is not None
        ],
        "middleware": [
            str(getattr(item.cls, "__name__", type(item.cls).__name__))
            for item in app.user_middleware
        ],
        "openapi": app.openapi(),
        "v1_defaults": {
            "query": QueryRequest(question="contract probe").model_dump(mode="json"),
            "search": SearchRequest(query="contract probe").model_dump(mode="json"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review-output", type=Path)
    parser.add_argument(
        "--review-only", action="store_true", help="Regenerate only the unregistered review schema"
    )
    parser.add_argument(
        "--replace", action="store_true", help="Explicitly refresh a reviewed snapshot"
    )
    args = parser.parse_args()
    if args.review_only and (args.output is not None or args.review_output is None):
        parser.error("--review-only requires --review-output and forbids --output")
    if not args.review_only and args.output is None:
        parser.error("--output is required unless --review-only is set")
    if args.output is not None:
        content = json.dumps(capture_contracts(), indent=2, sort_keys=True) + "\n"
        with args.output.open("w" if args.replace else "x", encoding="utf-8") as stream:
            stream.write(content)
    if args.review_output is not None:
        with args.review_output.open("w" if args.replace else "x", encoding="utf-8") as stream:
            json.dump(
                {
                    "request": ScopeRequestReview.model_json_schema(),
                    "response": ScopeResponseReview.model_json_schema(),
                },
                stream,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")


if __name__ == "__main__":
    main()
