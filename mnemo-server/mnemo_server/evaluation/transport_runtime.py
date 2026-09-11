"""Isolated real-transport runtime for governed evaluation notebook validation.

The reindex orchestrator launches this module in child processes.  The child uses
Mnemo's normal application services and transport implementations, but binds storage
to one server-resolved evaluation notebook.  A caller can choose only a registry
alias; arbitrary database paths never cross a public HTTP or MCP request boundary.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.stdio import stdio_server
from mnemo import KnowledgeEngine, MnemoConfig

from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.evaluation.notebook_registry import (
    ServerOwnedEvaluationNotebookRegistryV1,
    resolve_evaluation_notebook_validation_candidate_v1,
)
from mnemo_server.mcp.server import configure_stderr_logging, create_mcp_server, create_sse_app
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.retrieval_v2 import build_retrieval_cursor_codec

_API_KEY = "mnemo-evaluation-notebook-transport-key"
_CURSOR_SECRET = "mnemo-evaluation-notebook-cursor-secret-v1"
_PRINCIPAL_SUBJECT = "mnemo-evaluation-notebook-validator"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transport", choices=("http", "stdio", "sse"))
    parser.add_argument("--alias", required=True, choices=("phase8_5", "phase8_6"))
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--validation-candidate", action="store_true")
    return parser.parse_args()


def _configuration(
    workspace: Path, alias: str, *, validation_candidate: bool
) -> tuple[MnemoConfig, ServerConfig]:
    root = workspace.resolve(strict=True)
    selection = (
        resolve_evaluation_notebook_validation_candidate_v1(workspace_root=root, alias=alias)
        if validation_candidate
        else ServerOwnedEvaluationNotebookRegistryV1(
            workspace_root=root,
            registry=root / "scratch/evaluation_notebooks/registry.json",
        ).resolve(alias)
    )
    core = MnemoConfig.from_file(root / "mnemo.toml")
    storage = core.storage.model_copy(
        update={
            "sqlite": core.storage.sqlite.model_copy(update={"path": selection.database}),
            "filesystem": core.storage.filesystem.model_copy(update={"root": selection.blob_root}),
        }
    )
    core = core.model_copy(update={"storage": storage})
    server = ServerConfig(
        auth_mode="api-key",
        api_key=_API_KEY,
        delivery_cursor_secret=_CURSOR_SECRET,
        max_advanced_elapsed_milliseconds=60_000,
        production_rerank_candidate_limit=50,
    )
    return core, server


async def _run_stdio(core: MnemoConfig, server_config: ServerConfig) -> None:
    configure_stderr_logging("info")
    engine = KnowledgeEngine(
        core,
        advanced_retrieval_cursor_codec=build_retrieval_cursor_codec(server_config),
    )
    await engine.initialize()
    principal = principal_from_claims({"sub": _PRINCIPAL_SUBJECT})
    server = create_mcp_server(
        engine=engine,
        config=server_config,
        principal_provider=lambda: principal,
    )
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await engine.shutdown()


def main() -> int:
    args = _arguments()
    core, server_config = _configuration(
        args.workspace, args.alias, validation_candidate=args.validation_candidate
    )
    if args.transport == "stdio":
        asyncio.run(_run_stdio(core, server_config))
        return 0
    if args.port < 1:
        raise ValueError("HTTP and SSE validation require --port")
    if args.transport == "http":
        app: Any = create_app(
            server_config,
            core,
            provision_tokenizer_on_startup=False,
        )
    else:
        engine = KnowledgeEngine(
            core,
            advanced_retrieval_cursor_codec=build_retrieval_cursor_codec(server_config),
        )
        principal = principal_from_claims({"sub": _PRINCIPAL_SUBJECT})
        mcp_server = create_mcp_server(
            engine=engine,
            config=server_config,
            principal_provider=lambda: principal,
        )
        app = create_sse_app(
            server=mcp_server,
            config=server_config,
            mnemo_config=core,
            engine=engine,
        )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
