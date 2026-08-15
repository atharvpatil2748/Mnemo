"""Unit tests for ServerConfig."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from mnemo_server.config import ServerConfig
from pydantic import ValidationError


def test_server_config_defaults() -> None:
    config = ServerConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 8000
    assert config.cors_origins == ("http://localhost:3000", "http://127.0.0.1:3000")
    assert config.log_level == "info"


def test_server_config_custom_values() -> None:
    config = ServerConfig(
        host="0.0.0.0",
        port=9000,
        cors_origins=("https://app.mnemo.local",),
        log_level="debug",
    )
    assert config.host == "0.0.0.0"
    assert config.port == 9000
    assert config.cors_origins == ("https://app.mnemo.local",)
    assert config.log_level == "debug"


def test_server_config_frozen() -> None:
    config = ServerConfig()
    with pytest.raises(ValidationError):
        config.host = "0.0.0.0"  # type: ignore[misc]


def test_server_config_from_env_defaults() -> None:
    with patch.dict(os.environ, {}, clear=True):
        config = ServerConfig.from_env()
        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.cors_origins == ("http://localhost:3000", "http://127.0.0.1:3000")
        assert config.log_level == "info"


def test_server_config_from_env_custom() -> None:
    env = {
        "MNEMO_SERVER_HOST": "10.0.0.1",
        "MNEMO_SERVER_PORT": "8080",
        "MNEMO_SERVER_CORS_ORIGINS": "https://example.com, https://test.com",
        "MNEMO_SERVER_LOG_LEVEL": "WARNING",
    }
    with patch.dict(os.environ, env, clear=True):
        config = ServerConfig.from_env()
        assert config.host == "10.0.0.1"
        assert config.port == 8080
        assert config.cors_origins == ("https://example.com", "https://test.com")
        assert config.log_level == "warning"


def test_server_config_from_env_json_cors() -> None:
    env = {
        "MNEMO_SERVER_CORS_ORIGINS": '["http://localhost:8080", "http://127.0.0.1:8080"]',
    }
    with patch.dict(os.environ, env, clear=True):
        config = ServerConfig.from_env()
        assert config.cors_origins == ("http://localhost:8080", "http://127.0.0.1:8080")


def test_server_config_from_env_invalid_port() -> None:
    with (
        patch.dict(os.environ, {"MNEMO_SERVER_PORT": "invalid"}, clear=True),
        pytest.raises(ValueError, match="must be an integer"),
    ):
        ServerConfig.from_env()


def test_server_config_from_env_invalid_log_level() -> None:
    with (
        patch.dict(os.environ, {"MNEMO_SERVER_LOG_LEVEL": "invalid"}, clear=True),
        pytest.raises(ValueError, match="must be one of"),
    ):
        ServerConfig.from_env()
