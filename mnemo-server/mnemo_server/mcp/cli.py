"""Command-line interface for the Mnemo MCP Server (mnemo-mcp)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from mnemo import __version__

from mnemo_server.config import ServerConfig

from .server import run_sse_server, run_stdio_server


def create_parser() -> argparse.ArgumentParser:
    """Build the argument parser for mnemo-mcp."""
    parser = argparse.ArgumentParser(
        prog="mnemo-mcp",
        description="Mnemo Model Context Protocol (MCP) server for local knowledge retrieval.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"mnemo-mcp v{__version__}",
        help="Show program version and exit.",
    )

    # Top-level transport flag
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=None,
        help="Transport mode (stdio or sse). Defaults to stdio if omitted.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("MNEMO_MCP_HOST", "127.0.0.1"),
        help="Host to bind for SSE transport (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MNEMO_MCP_PORT", "8001")),
        help="Port to listen on for SSE transport (default: 8001).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        default=os.getenv("MNEMO_SERVER_LOG_LEVEL", "info"),
        help="Log level (default: info).",
    )
    parser.add_argument(
        "--auth-mode",
        type=str,
        choices=["none", "api-key", "jwt"],
        default=os.getenv("MNEMO_SERVER_AUTH_MODE", "none"),
        help="Authentication mode for SSE transport (default: none).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("MNEMO_SERVER_API_KEY"),
        help="API key for api-key auth mode on SSE transport.",
    )
    parser.add_argument(
        "--jwt-secret",
        type=str,
        default=os.getenv("MNEMO_SERVER_JWT_SECRET"),
        help="JWT shared secret for jwt auth mode on SSE transport.",
    )

    subparsers = parser.add_subparsers(dest="command", help="MCP transport subcommands")

    # stdio subcommand
    subparsers.add_parser(
        "stdio",
        help="Run MCP server over standard input/output (for local desktop/IDE clients).",
    )

    # sse subcommand
    sse_parser = subparsers.add_parser(
        "sse",
        help="Run MCP server over HTTP Server-Sent Events (SSE).",
    )
    sse_parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host address to bind (default: 127.0.0.1).",
    )
    sse_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on (default: 8001).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the mnemo-mcp console script."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Determine transport
    command = args.command
    transport = args.transport

    selected_transport = "stdio"
    if command == "sse" or transport == "sse":
        selected_transport = "sse"
    elif command == "stdio" or transport == "stdio":
        selected_transport = "stdio"

    raw_host = getattr(args, "host", None)
    host: str = str(raw_host if raw_host is not None else os.getenv("MNEMO_MCP_HOST", "127.0.0.1"))
    raw_port = getattr(args, "port", None)
    port: int = int(raw_port if raw_port is not None else os.getenv("MNEMO_MCP_PORT", "8001"))

    config = ServerConfig(
        host=host,
        port=port,
        log_level=args.log_level,
        auth_mode=args.auth_mode,
        api_key=args.api_key,
        jwt_secret=args.jwt_secret,
    )

    if selected_transport == "stdio":
        try:
            asyncio.run(run_stdio_server(config=config))
            return 0
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            print(f"Error in stdio MCP server: {exc}", file=sys.stderr)
            return 1

    if selected_transport == "sse":
        try:
            run_sse_server(host=host, port=port, config=config)
            return 0
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            print(f"Error in SSE MCP server: {exc}", file=sys.stderr)
            return 1

    parser.print_help(file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
