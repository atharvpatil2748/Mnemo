"""Unit and integration tests for mnemo-mcp CLI (Module 8.1)."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import AsyncMock, patch

import pytest
from mnemo import __version__
from mnemo_server.mcp.cli import create_parser, main


def test_cli_parser_defaults() -> None:
    """Parser defaults to stdio transport and default host/port."""
    parser = create_parser()
    args = parser.parse_args([])
    assert args.command is None
    assert args.transport is None
    assert args.host == "127.0.0.1"
    assert args.port == 8001
    assert args.auth_mode == "none"


def test_cli_parser_subcommands() -> None:
    """Parser parses stdio and sse subcommands."""
    parser = create_parser()
    args_stdio = parser.parse_args(["stdio"])
    assert args_stdio.command == "stdio"

    args_sse = parser.parse_args(["sse", "--host", "0.0.0.0", "--port", "9090"])
    assert args_sse.command == "sse"
    assert args_sse.host == "0.0.0.0"
    assert args_sse.port == 9090


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """mnemo-mcp --version prints version and exits."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert f"mnemo-mcp v{__version__}" in captured.out


def test_cli_main_runs_stdio() -> None:
    """main() with stdio invokes run_stdio_server."""
    with patch("mnemo_server.mcp.cli.run_stdio_server", new_callable=AsyncMock) as mock_stdio:
        exit_code = main(["stdio"])
        assert exit_code == 0
        assert mock_stdio.called


def test_cli_main_runs_sse() -> None:
    """main() with sse invokes run_sse_server."""
    with patch("mnemo_server.mcp.cli.run_sse_server") as mock_sse:
        exit_code = main(["sse", "--host", "127.0.0.1", "--port", "8002"])
        assert exit_code == 0
        assert mock_sse.called
        call_kwargs = mock_sse.call_args.kwargs
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 8002


def test_cli_main_runs_transport_sse_flag() -> None:
    """main() with --transport sse invokes run_sse_server."""
    with patch("mnemo_server.mcp.cli.run_sse_server") as mock_sse:
        exit_code = main(["--transport", "sse"])
        assert exit_code == 0
        assert mock_sse.called


def test_cli_main_handles_keyboard_interrupt_stdio() -> None:
    """main() catches KeyboardInterrupt gracefully in stdio mode."""
    with patch("mnemo_server.mcp.cli.run_stdio_server", side_effect=KeyboardInterrupt):
        exit_code = main(["stdio"])
        assert exit_code == 0


def test_cli_main_handles_keyboard_interrupt_sse() -> None:
    """main() catches KeyboardInterrupt gracefully in sse mode."""
    with patch("mnemo_server.mcp.cli.run_sse_server", side_effect=KeyboardInterrupt):
        exit_code = main(["sse"])
        assert exit_code == 0


def test_cli_main_handles_exception(capsys: pytest.CaptureFixture[str]) -> None:
    """main() catches runner exceptions and writes to stderr."""
    with patch("mnemo_server.mcp.cli.run_stdio_server", side_effect=RuntimeError("Stream failure")):
        exit_code = main(["stdio"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error in stdio MCP server: Stream failure" in captured.err


def test_cli_main_handles_exception_sse(capsys: pytest.CaptureFixture[str]) -> None:
    """main() catches runner exceptions in sse mode and writes to stderr."""
    with patch("mnemo_server.mcp.cli.run_sse_server", side_effect=RuntimeError("SSE failure")):
        exit_code = main(["sse"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error in SSE MCP server: SSE failure" in captured.err


def test_cli_subprocess_execution() -> None:
    """Executing mnemo-mcp via subprocess emits valid version on stdout."""
    res = subprocess.run(
        [sys.executable, "-m", "mnemo_server.mcp.cli", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"mnemo-mcp v{__version__}" in res.stdout
