"""Unit and integration tests for Mnemo CLI commands and argument parser."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from mnemo import __version__
from mnemo_server.cli import build_parser, main


def test_cli_parser_build() -> None:
    parser = build_parser()
    assert parser.prog == "mnemo"


def test_cli_no_args_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "usage: mnemo" in captured.out


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert f"mnemo-server v{__version__}" in captured.out


def test_cli_check_valid(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MNEMO_SERVER_PORT", "9000")
    monkeypatch.setenv("MNEMO_SERVER_LOG_LEVEL", "debug")
    monkeypatch.setenv("MNEMO_SERVER_AUTH_MODE", "none")

    exit_code = main(["check"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Mnemo server configuration valid:" in captured.out
    assert "Port: 9000" in captured.out


def test_cli_check_invalid(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MNEMO_SERVER_PORT", "invalid-port")

    exit_code = main(["check"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Configuration error:" in captured.err


def test_cli_provision_tokenizer(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("mnemo_server.cli.provision_tokenizer", return_value="/mock/path/asset.tiktoken"):
        exit_code = main(["provision-tokenizer"])
        assert exit_code == 0


def test_cli_serve_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate environment mutations
    orig_env = dict(os.environ)
    try:
        with patch("uvicorn.run") as mock_run:
            exit_code = main(
                [
                    "serve",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8080",
                    "--log-level",
                    "warning",
                    "--auth-mode",
                    "api-key",
                    "--api-key",
                    "secret-key",
                ]
            )
            assert exit_code == 0
            mock_run.assert_called_once_with(
                "mnemo_server.main:app",
                host="0.0.0.0",
                port=8080,
                log_level="warning",
                reload=False,
                workers=1,
            )
    finally:
        os.environ.clear()
        os.environ.update(orig_env)
