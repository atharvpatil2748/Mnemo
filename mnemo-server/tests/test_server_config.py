"""Unit tests for ServerConfig."""

from __future__ import annotations

import os
from pathlib import Path
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


def test_durable_reranker_activation_configuration_is_atomic() -> None:
    common = {
        "production_mode": True,
        "auth_mode": "api-key",
        "api_key": "test-key",
        "delivery_cursor_secret": "x" * 32,
        "full_multilingual_v2_enabled": True,
        "full_multilingual_v2_model_cache": Path("models"),
        "final_qa_operational_store_path": Path("operational.db"),
        "mcp_stdio_principal_subject": "stdio-server",
    }
    with pytest.raises(ValidationError, match="both a state path and operator subject"):
        ServerConfig(**common, reranker_activation_state_path=Path("reranker.json"))
    config = ServerConfig(
        **common,
        reranker_activation_state_path=Path("reranker.json"),
        reranker_activation_operator_subject="production-operator",
    )
    assert config.reranker_activation_state_path == Path("reranker.json")


def test_durable_reranker_activation_environment_binding() -> None:
    env = {
        "MNEMO_SERVER_PRODUCTION_MODE": "true",
        "MNEMO_SERVER_AUTH_MODE": "api-key",
        "MNEMO_SERVER_API_KEY": "test-key",
        "MNEMO_SERVER_DELIVERY_CURSOR_SECRET": "x" * 32,
        "MNEMO_SERVER_FULL_MULTILINGUAL_V2_ENABLED": "true",
        "MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE": "models",
        "MNEMO_SERVER_FINAL_QA_OPERATIONAL_STORE_PATH": "operational.db",
        "MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT": "stdio-server",
        "MNEMO_SERVER_RERANKER_ACTIVATION_STATE_PATH": "reranker.json",
        "MNEMO_SERVER_RERANKER_ACTIVATION_OPERATOR_SUBJECT": "production-operator",
    }
    with patch.dict(os.environ, env, clear=True):
        config = ServerConfig.from_env()
    assert config.reranker_activation_state_path == Path("reranker.json")
    assert config.reranker_activation_operator_subject == "production-operator"
