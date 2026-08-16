"""Mnemo command-line interface for installation, server startup, and configuration verification."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn
from mnemo import __version__

from .config import ServerConfig
from .tokenizer_provisioning import provision_tokenizer


def build_parser() -> argparse.ArgumentParser:
    """Build the canonical argument parser for the mnemo CLI."""
    parser = argparse.ArgumentParser(
        prog="mnemo",
        description="Mnemo: Local-first Knowledge Engine CLI and Server.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"mnemo-server v{__version__}",
        help="Show program version and exit.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. serve command
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the Mnemo HTTP/WebSocket ASGI server.",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host address to bind (default: 127.0.0.1 or MNEMO_SERVER_HOST).",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind (default: 8000 or MNEMO_SERVER_PORT).",
    )
    serve_parser.add_argument(
        "--log-level",
        type=str,
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        default=None,
        help="Server logging verbosity.",
    )
    serve_parser.add_argument(
        "--auth-mode",
        type=str,
        choices=["none", "api-key", "jwt"],
        default=None,
        help="API authentication mode (none, api-key, jwt).",
    )
    serve_parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Static API key for api-key auth mode.",
    )
    serve_parser.add_argument(
        "--jwt-secret",
        type=str,
        default=None,
        help="JWT shared secret for jwt auth mode.",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto-reload for local development.",
    )
    serve_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1).",
    )

    # 2. provision-tokenizer command
    provision_parser = subparsers.add_parser(
        "provision-tokenizer",
        help="Install the canonical tokenizer asset.",
    )
    provision_parser.add_argument(
        "--from-file",
        type=Path,
        help="Import an independently obtained tokenizer asset.",
    )
    provision_parser.add_argument(
        "--data-root",
        type=Path,
        help="Override local data root directory.",
    )

    # 3. check command
    subparsers.add_parser(
        "check",
        help="Validate configuration and verify runtime readiness.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Mnemo CLI with given command-line arguments."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "provision-tokenizer":
        path = provision_tokenizer(source=args.from_file, data_root=args.data_root)
        print(path)
        return 0

    if args.command == "check":
        try:
            config = ServerConfig.from_env()
            print("Mnemo server configuration valid:")
            print(f"  Host: {config.host}")
            print(f"  Port: {config.port}")
            print(f"  Log Level: {config.log_level}")
            print(f"  Auth Mode: {config.auth_mode}")
            if config.auth_mode == "api-key":
                print(f"  API Key: {'[CONFIGURED]' if config.api_key else '[MISSING]'}")
            elif config.auth_mode == "jwt":
                print(f"  JWT Secret: {'[CONFIGURED]' if config.jwt_secret else '[MISSING]'}")
            return 0
        except Exception as err:
            print(f"Configuration error: {err}", file=sys.stderr)
            return 1

    if args.command == "serve":
        env_config = ServerConfig.from_env()
        host = args.host or env_config.host
        port = args.port or env_config.port
        log_level = args.log_level or env_config.log_level

        # Pass CLI overrides to environment for app lifespan
        if args.host:
            os.environ["MNEMO_SERVER_HOST"] = str(args.host)
        if args.port:
            os.environ["MNEMO_SERVER_PORT"] = str(args.port)
        if args.log_level:
            os.environ["MNEMO_SERVER_LOG_LEVEL"] = str(args.log_level)
        if args.auth_mode:
            os.environ["MNEMO_SERVER_AUTH_MODE"] = str(args.auth_mode)
        if args.api_key:
            os.environ["MNEMO_SERVER_API_KEY"] = str(args.api_key)
        if args.jwt_secret:
            os.environ["MNEMO_SERVER_JWT_SECRET"] = str(args.jwt_secret)

        uvicorn.run(
            "mnemo_server.main:app",
            host=host,
            port=port,
            log_level=log_level,
            reload=args.reload,
            workers=args.workers,
        )
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
