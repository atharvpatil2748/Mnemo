"""Integration and contract tests for Authentication Middleware (none, api-key, jwt)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.config import MnemoConfig
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import HealthStatus, StorageCapabilities
from mnemo_server.app import create_app
from mnemo_server.auth import AuthError, validate_jwt
from mnemo_server.config import ServerConfig


def create_test_jwt(
    payload: dict[str, Any],
    secret: str,
    alg: str = "HS256",
) -> str:
    """Generate a valid JWT token for testing."""
    header = {"alg": alg, "typ": "JWT"}
    h_bytes = json.dumps(header).encode("utf-8")
    p_bytes = json.dumps(payload).encode("utf-8")
    h_b64 = base64.urlsafe_b64encode(h_bytes).decode("utf-8").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(p_bytes).decode("utf-8").rstrip("=")
    signing_input = f"{h_b64}.{p_b64}".encode()
    hash_map = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}
    sig = hmac.new(secret.encode("utf-8"), signing_input, hash_map[alg]).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"{h_b64}.{p_b64}.{sig_b64}"


def _make_ready_engine() -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.version = "0.23.0"
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
    now = datetime.now(UTC)

    engine.config = MnemoConfig.model_validate(
        {
            "llm": {
                "planner": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                "synthesizer": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                "extractor": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
                "classifier": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            },
            "embedding": {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "dimensions": 768,
            },
            "reranker": {
                "provider": "cross-encoder",
                "model": "ms-marco-MiniLM-L-6-v2",
            },
        }
    )

    storage_mock = MagicMock()
    storage_mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=True,
        supports_dense_search=True,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=False,
        supports_transactions=True,
        supports_health_checks=True,
    )
    storage_mock.health_check = AsyncMock(
        return_value=(
            HealthStatus(component="sqlite", healthy=True, checked_at=now),
            HealthStatus(component="filesystem", healthy=True, checked_at=now),
        )
    )
    storage_mock.list_notebooks = AsyncMock(
        return_value=MagicMock(items=(), next_cursor=None, has_more=False)
    )
    engine.storage = storage_mock

    emb_mock = MagicMock()
    emb_mock.health_check = AsyncMock(
        return_value=HealthStatus(component="ollama", healthy=True, checked_at=now)
    )
    engine.embedding_provider = emb_mock

    llm_mock = MagicMock()
    llm_mock.health_check = AsyncMock(
        return_value=HealthStatus(component="ollama_llm", healthy=True, checked_at=now)
    )
    engine.llm = MagicMock(return_value=llm_mock)

    return engine


def _make_test_app(config: ServerConfig) -> Any:
    engine = _make_ready_engine()
    app = create_app(engine=engine, server_config=config, provision_tokenizer_on_startup=False)
    tc_mock = MagicMock()
    tc_mock.count.return_value = 0
    tc_mock.tokenizer_id = "o200k_base"
    app.state.token_counter = tc_mock
    app.state.engine = engine
    return app


@pytest.mark.anyio
async def test_auth_mode_none_allows_all_requests() -> None:
    app = _make_test_app(ServerConfig(auth_mode="none"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Public health endpoint
        resp_health = await client.get("/v1/health")
        assert resp_health.status_code == 200

        # Protected notebooks endpoint
        resp_nb = await client.get("/v1/notebooks")
        assert resp_nb.status_code == 200


@pytest.mark.anyio
async def test_auth_mode_api_key_enforcement() -> None:
    valid_key = "test-secret-api-key-12345"
    app = _make_test_app(ServerConfig(auth_mode="api-key", api_key=valid_key))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Health check is always exempt
        resp_health = await client.get("/v1/health")
        assert resp_health.status_code == 200

        # 2. Missing key returns 401
        resp_no_key = await client.get("/v1/notebooks")
        assert resp_no_key.status_code == 401
        data = resp_no_key.json()
        assert data["error"]["code"] == "auth.unauthorized"

        # 3. Invalid key returns 401
        resp_bad_key = await client.get(
            "/v1/notebooks",
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp_bad_key.status_code == 401

        # 4. Valid key in Authorization Bearer returns 200
        resp_valid_bearer = await client.get(
            "/v1/notebooks",
            headers={"Authorization": f"Bearer {valid_key}"},
        )
        assert resp_valid_bearer.status_code == 200

        # 5. Valid key in X-API-Key header returns 200
        resp_valid_x_key = await client.get(
            "/v1/notebooks",
            headers={"X-API-Key": valid_key},
        )
        assert resp_valid_x_key.status_code == 200


@pytest.mark.anyio
async def test_auth_mode_api_key_misconfigured() -> None:
    app = _make_test_app(ServerConfig(auth_mode="api-key", api_key=None))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/notebooks")
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "internal.configuration"


@pytest.mark.anyio
async def test_auth_mode_jwt_enforcement() -> None:
    jwt_secret = "my-super-secret-key-32-bytes-long"
    app = _make_test_app(ServerConfig(auth_mode="jwt", jwt_secret=jwt_secret))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Exempt health endpoint
        resp_health = await client.get("/v1/health")
        assert resp_health.status_code == 200

        # 2. Missing token returns 401
        resp_no_tok = await client.get("/v1/notebooks")
        assert resp_no_tok.status_code == 401

        # 3. Invalid signature returns 401
        bad_token = create_test_jwt({"sub": "user1"}, secret="wrong-secret")
        resp_bad_sig = await client.get(
            "/v1/notebooks",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert resp_bad_sig.status_code == 401

        # 4. Expired token returns 401
        past_exp = int(time.time()) - 100
        expired_token = create_test_jwt({"sub": "user1", "exp": past_exp}, secret=jwt_secret)
        resp_expired = await client.get(
            "/v1/notebooks",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp_expired.status_code == 401

        # 5. Future nbf token returns 401
        future_nbf = int(time.time()) + 500
        nbf_token = create_test_jwt({"sub": "user1", "nbf": future_nbf}, secret=jwt_secret)
        resp_nbf = await client.get(
            "/v1/notebooks",
            headers={"Authorization": f"Bearer {nbf_token}"},
        )
        assert resp_nbf.status_code == 401

        # 6. Valid token returns 200
        valid_token = create_test_jwt(
            {"sub": "user1", "exp": int(time.time()) + 3600}, secret=jwt_secret
        )
        resp_valid = await client.get(
            "/v1/notebooks",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp_valid.status_code == 200

        # 7. Valid token via query param (?token=...) returns 200
        resp_query = await client.get(f"/v1/notebooks?token={valid_token}")
        assert resp_query.status_code == 200


def test_jwt_validation_unit_edge_cases() -> None:
    secret = "unit-test-jwt-secret-xyz"

    # Malformed tokens
    with pytest.raises(AuthError, match="Invalid JWT token format"):
        validate_jwt("bad.token", secret)

    with pytest.raises(AuthError, match="Malformed JWT header"):
        validate_jwt("!!!.payload.sig", secret)

    with pytest.raises(AuthError, match="Unsupported or disallowed JWT algorithm"):
        validate_jwt(
            create_test_jwt({}, secret, alg="HS256"), secret, allowed_algorithms=("HS512",)
        )

    # HS384 and HS512 support
    tok384 = create_test_jwt({"sub": "test"}, secret, alg="HS384")
    res384 = validate_jwt(tok384, secret, allowed_algorithms=("HS384",))
    assert res384["sub"] == "test"

    tok512 = create_test_jwt({"sub": "test"}, secret, alg="HS512")
    res512 = validate_jwt(tok512, secret, allowed_algorithms=("HS512",))
    assert res512["sub"] == "test"
