"""Unit and integration tests for mnemo-mcp CLI (Module 8.1)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mnemo import __version__
from mnemo_server.config import ServerConfig
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
    assert args_sse.sse_host == "0.0.0.0"
    assert args_sse.sse_port == 9090


def test_cli_main_preserves_top_level_sse_host_and_port() -> None:
    """Top-level transport options are not overwritten by subparser defaults."""
    with patch("mnemo_server.mcp.cli.run_sse_server") as mock_sse:
        assert main(["--host", "127.0.0.2", "--port", "8032", "sse"]) == 0
    assert mock_sse.call_args.kwargs["host"] == "127.0.0.2"
    assert mock_sse.call_args.kwargs["port"] == 8032


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


def test_certified_tunnel_refuses_unconfigured_production(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MNEMO_SERVER_PRODUCTION_MODE", raising=False)
    with (
        patch(
            "mnemo_server.mcp.cli.ServerConfig.from_env",
            side_effect=RuntimeError("CERTIFIED_CONFIGURATION_UNAVAILABLE"),
        ),
        patch("mnemo_server.mcp.cli.run_stdio_server", new_callable=AsyncMock) as runner,
    ):
        assert main(["certified-tunnel-stdio"]) == 1
    runner.assert_not_called()
    assert "CERTIFIED_PRODUCTION_BINDING_REJECTED" in capsys.readouterr().err


def test_certified_tunnel_forbids_transport_identity_overrides(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MNEMO_SERVER_PRODUCTION_MODE", raising=False)
    assert main(["--auth-mode", "none", "certified-tunnel-stdio"]) == 1
    assert "CERTIFIED_PRODUCTION_BINDING_REJECTED" in capsys.readouterr().err


def test_production_cli_preserves_server_owned_authentication(tmp_path: Path) -> None:
    base = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        auth_mode="api-key",
        api_key="synthetic-test-credential",
        delivery_cursor_secret="synthetic-test-signing-secret-material-123456",
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "final-qa.db",
        mcp_stdio_principal_subject="local-test-operator",
    )
    with (
        patch("mnemo_server.mcp.cli.ServerConfig.from_env", return_value=base),
        patch("mnemo_server.mcp.cli.run_stdio_server", new_callable=AsyncMock) as runner,
    ):
        assert main(["certified-tunnel-stdio"]) == 0
        effective = runner.call_args.kwargs["config"]
        assert effective.auth_mode == base.auth_mode
        assert effective.api_key == base.api_key
        assert effective.mcp_stdio_principal_subject == base.mcp_stdio_principal_subject
        assert runner.call_args.kwargs["transport_label"] == "external_tunnel"
        runner.reset_mock()
        assert main(["certified-stdio"]) == 0
        assert runner.call_args.kwargs["transport_label"] == "mcp_stdio"
        runner.reset_mock()
        assert main(["--api-key", "client-selected", "stdio"]) == 1
        runner.assert_not_called()


def test_certified_sse_uses_governed_configuration(tmp_path: Path) -> None:
    base = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        auth_mode="api-key",
        api_key="synthetic-test-authentication-key",
        delivery_cursor_secret="synthetic-test-signing-secret-material-123456",
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "final-qa.db",
        mcp_stdio_principal_subject="local-test-operator",
    )
    with (
        patch("mnemo_server.mcp.cli.ServerConfig.from_env", return_value=base),
        patch("mnemo_server.mcp.cli.run_sse_server") as runner,
    ):
        assert main(["certified-sse"]) == 0
        effective = runner.call_args.kwargs["config"]
        assert effective.auth_mode == base.auth_mode
        assert effective.api_key == base.api_key
        assert effective.credential_generation_id == base.credential_generation_id
        assert runner.call_args.kwargs["pre_certification_observation"] is False
        runner.reset_mock()
        assert main(["--api-key", "client-selected", "certified-sse"]) == 1
        runner.assert_not_called()


def test_observation_cli_rejects_missing_staged_configuration(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MNEMO_SERVER_PRODUCTION_MODE", raising=False)
    with (
        patch(
            "mnemo_server.mcp.cli.ServerConfig.from_env",
            side_effect=RuntimeError("STAGED_CONFIGURATION_UNAVAILABLE"),
        ),
        patch("mnemo_server.mcp.cli.run_stdio_server", new_callable=AsyncMock) as runner,
    ):
        assert main(["observe-tunnel-stdio"]) == 1
    runner.assert_not_called()
    assert "CERTIFIED_PRODUCTION_BINDING_REJECTED" in capsys.readouterr().err


def test_observation_cli_selects_transport_only(tmp_path: Path) -> None:
    base = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        auth_mode="api-key",
        api_key="synthetic-observer-credential",
        delivery_cursor_secret="synthetic-observer-signing-material-123456",
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "final-qa.db",
        mcp_stdio_principal_subject="local-test-operator",
    )
    with (
        patch("mnemo_server.mcp.cli.ServerConfig.from_env", return_value=base) as config_reader,
        patch("mnemo_server.mcp.cli.run_stdio_server", new_callable=AsyncMock) as runner,
    ):
        assert main(["observe-tunnel-stdio"]) == 0
        assert config_reader.call_args.kwargs["pre_certification_observation"] is True
        assert runner.call_args.kwargs["pre_certification_observation"] is True
        assert runner.call_args.kwargs["transport_label"] == "external_tunnel"
        runner.reset_mock()
        assert main(["--api-key", "client-selected", "observe-stdio"]) == 1
        runner.assert_not_called()


def test_observation_sse_startup_error_is_safe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ServerConfig(
        production_mode=True,
        full_multilingual_v2_enabled=True,
        auth_mode="api-key",
        api_key="synthetic-observer-credential",
        delivery_cursor_secret="synthetic-observer-signing-material-123456",
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "final-qa.db",
        mcp_stdio_principal_subject="local-test-operator",
    )
    with (
        patch("mnemo_server.mcp.cli.ServerConfig.from_env", return_value=base),
        patch("mnemo_server.mcp.cli.run_sse_server", side_effect=RuntimeError("private path")),
    ):
        assert main(["observe-sse"]) == 1
    error = capsys.readouterr().err
    assert "CERTIFIED_PRODUCTION_STARTUP_FAILED" in error
    assert "private path" not in error


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
