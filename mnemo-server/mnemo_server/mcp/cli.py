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
    parser.add_argument(
        "--stdio-principal-subject",
        type=str,
        default=os.getenv("MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT"),
        help="Server-owned authenticated subject for the trusted local stdio transport.",
    )

    subparsers = parser.add_subparsers(dest="command", help="MCP transport subcommands")

    # stdio subcommand
    subparsers.add_parser(
        "stdio",
        help="Run MCP server over standard input/output (for local desktop/IDE clients).",
    )
    subparsers.add_parser(
        "certified-tunnel-stdio",
        help="Run the external tunnel through the server-owned certified stdio startup.",
    )
    subparsers.add_parser(
        "certified-stdio",
        help="Run local MCP stdio through the server-owned certified startup.",
    )
    subparsers.add_parser(
        "certified-sse",
        help="Run local MCP SSE through the server-owned certified startup.",
    )
    subparsers.add_parser(
        "certified-evidence",
        help="Verify four signed transport observations against current production authority.",
    )
    subparsers.add_parser(
        "observe-stdio",
        help="Authenticated, read-only pre-certification MCP observation only.",
    )
    subparsers.add_parser(
        "observe-tunnel-stdio",
        help="External tunnel transport for the staged observation-only runtime.",
    )
    subparsers.add_parser(
        "observe-sse",
        help="Authenticated, read-only pre-certification MCP SSE observation only.",
    )

    # sse subcommand
    sse_parser = subparsers.add_parser(
        "sse",
        help="Run MCP server over HTTP Server-Sent Events (SSE).",
    )
    sse_parser.add_argument(
        "--host",
        dest="sse_host",
        type=str,
        default=None,
        help="Host address to bind (default: 127.0.0.1).",
    )
    sse_parser.add_argument(
        "--port",
        dest="sse_port",
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
    supplied = argv if argv is not None else sys.argv[1:]
    identity_options = {
        "--auth-mode",
        "--api-key",
        "--jwt-secret",
        "--stdio-principal-subject",
    }
    observation_mode = command in {"observe-stdio", "observe-tunnel-stdio", "observe-sse"}
    governed_command = command in {
        "certified-tunnel-stdio",
        "certified-stdio",
        "certified-sse",
        "certified-evidence",
    } or (observation_mode)
    if governed_command:
        forbidden = {
            "--transport",
            *identity_options,
        }
        if any(item.split("=", 1)[0] in forbidden for item in supplied):
            print("CERTIFIED_PRODUCTION_BINDING_REJECTED", file=sys.stderr)
            return 1

    selected_transport = "stdio"
    if command in {"sse", "certified-sse", "observe-sse"} or transport == "sse":
        selected_transport = "sse"
    elif command == "stdio" or transport == "stdio":
        selected_transport = "stdio"

    raw_host = getattr(args, "sse_host", None) or getattr(args, "host", None)
    host: str = str(raw_host if raw_host is not None else os.getenv("MNEMO_MCP_HOST", "127.0.0.1"))
    raw_port = getattr(args, "sse_port", None) or getattr(args, "port", None)
    port: int = int(raw_port if raw_port is not None else os.getenv("MNEMO_MCP_PORT", "8001"))

    try:
        base_config = ServerConfig.from_env(
            certified_production=governed_command,
            pre_certification_observation=observation_mode,
        )
    except Exception:
        if governed_command:
            print("CERTIFIED_PRODUCTION_BINDING_REJECTED", file=sys.stderr)
            return 1
        raise
    if base_config.production_mode and not base_config.full_multilingual_v2_enabled:
        print("CERTIFIED_PRODUCTION_BINDING_REJECTED", file=sys.stderr)
        return 1
    if base_config.production_mode and any(
        item.split("=", 1)[0] in identity_options for item in supplied
    ):
        print("CERTIFIED_PRODUCTION_BINDING_REJECTED", file=sys.stderr)
        return 1
    transport_overrides = {"host": host, "port": port, "log_level": args.log_level}
    identity_overrides = (
        {}
        if base_config.production_mode
        else {
            "auth_mode": args.auth_mode,
            "api_key": args.api_key,
            "jwt_secret": args.jwt_secret,
            "mcp_stdio_principal_subject": args.stdio_principal_subject,
        }
    )
    config = ServerConfig.model_validate(
        {
            **base_config.model_dump(),
            **transport_overrides,
            **identity_overrides,
        }
    )
    if governed_command and not (config.production_mode and config.full_multilingual_v2_enabled):
        print("CERTIFIED_PRODUCTION_BINDING_REJECTED", file=sys.stderr)
        return 1

    if command == "certified-evidence":
        from mnemo_server.services.production_runtime_binding import (
            write_certified_convergence,
        )

        try:
            artifact = write_certified_convergence(server_config=config)
        except Exception:
            print("CERTIFIED_CONVERGENCE_EVIDENCE_REJECTED", file=sys.stderr)
            return 1
        print(artifact)
        return 0

    if selected_transport == "stdio":
        try:
            asyncio.run(
                run_stdio_server(
                    config=config,
                    transport_label=(
                        "external_tunnel"
                        if command in {"certified-tunnel-stdio", "observe-tunnel-stdio"}
                        else "mcp_stdio"
                    ),
                    pre_certification_observation=observation_mode,
                )
            )
            return 0
        except KeyboardInterrupt:
            return 0
        except Exception:
            if governed_command:
                print("CERTIFIED_PRODUCTION_STARTUP_FAILED", file=sys.stderr)
            else:
                print("Error in stdio MCP server: startup failed", file=sys.stderr)
            return 1

    if selected_transport == "sse":
        try:
            run_sse_server(
                host=host,
                port=port,
                config=config,
                pre_certification_observation=observation_mode,
            )
            return 0
        except KeyboardInterrupt:
            return 0
        except Exception:
            if governed_command:
                print("CERTIFIED_PRODUCTION_STARTUP_FAILED", file=sys.stderr)
            else:
                print("Error in SSE MCP server: startup failed", file=sys.stderr)
            return 1

    parser.print_help(file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
