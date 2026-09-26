"""Unit tests for ADR-0049 HTTP error mapping and error responses."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mnemo.engine import (
    EngineInitializationError,
    EngineLifecycleError,
    KnowledgeEngineError,
)
from mnemo.interfaces import (
    ConflictError,
    ContractValidationError,
    DependencyUnavailableError,
    IntegrityError,
    LifecycleError,
    MnemoInterfaceError,
    NotFoundError,
    OperationCancelledError,
    OperationTimeoutError,
    PluginError,
    StorageError,
    UnsupportedError,
)
from mnemo.models import FrozenMetadata
from mnemo_server.errors import register_error_handlers
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class DummyBody(BaseModel):
    name: str = Field(..., min_length=2)


@pytest.fixture
def error_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise/contract-validation")
    async def raise_contract_validation() -> None:
        raise ContractValidationError("Contract violation occurred")

    @app.get("/raise/contract-validation-with-details")
    async def raise_contract_validation_with_details() -> None:
        raise ContractValidationError(
            "Contract violation with details",
            details=FrozenMetadata({"field": "query", "reason": "empty"}),
        )

    @app.get("/raise/not-found")
    async def raise_not_found() -> None:
        raise NotFoundError("Resource was not found")

    @app.get("/raise/conflict")
    async def raise_conflict() -> None:
        raise ConflictError("Version conflict occurred")

    @app.get("/raise/unsupported")
    async def raise_unsupported() -> None:
        raise UnsupportedError("Format is unsupported")

    @app.get("/raise/integrity")
    async def raise_integrity() -> None:
        raise IntegrityError("Data integrity check failed")

    @app.get("/raise/lifecycle")
    async def raise_lifecycle() -> None:
        raise LifecycleError("Component not in ready state")

    @app.get("/raise/engine-lifecycle")
    async def raise_engine_lifecycle() -> None:
        raise EngineLifecycleError("Engine is not ready")

    @app.get("/raise/dependency-unavailable")
    async def raise_dependency_unavailable() -> None:
        raise DependencyUnavailableError("Provider is offline")

    @app.get("/raise/engine-initialization")
    async def raise_engine_initialization() -> None:
        raise EngineInitializationError("Initialization failed")

    @app.get("/raise/timeout")
    async def raise_timeout() -> None:
        raise OperationTimeoutError("Deadline exceeded")

    @app.get("/raise/cancelled")
    async def raise_cancelled() -> None:
        raise OperationCancelledError("Operation cancelled")

    @app.get("/raise/storage")
    async def raise_storage() -> None:
        raise StorageError("Database connection refused")

    @app.get("/raise/nested-schema")
    async def raise_nested_schema() -> None:
        try:
            raise StorageError("PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA")
        except StorageError as error:
            raise PluginError("sq-2:sparse /private/credential.sql") from error

    @app.get("/raise/forged-code")
    async def raise_forged_code() -> None:
        error = StorageError("C:/private/token.db")
        error.code = "private_secret_token"
        raise error

    @app.get("/raise/plugin")
    async def raise_plugin() -> None:
        raise PluginError("Plugin crashed")

    @app.get("/raise/knowledge-engine")
    async def raise_knowledge_engine() -> None:
        raise KnowledgeEngineError("Engine error")

    @app.get("/raise/interface-error")
    async def raise_interface_error() -> None:
        raise MnemoInterfaceError("Base interface error")

    @app.post("/validate-body")
    async def validate_body(body: DummyBody) -> dict[str, str]:
        return {"name": body.name}

    @app.get("/raise/http-exception")
    async def raise_http_exception() -> None:
        raise StarletteHTTPException(status_code=403, detail="Forbidden access")

    @app.get("/raise/http-503")
    async def raise_http_503() -> None:
        raise StarletteHTTPException(status_code=503, detail="Service unavailable")

    @app.get("/raise/http-status/{status}")
    async def raise_http_status(status: int) -> None:
        raise StarletteHTTPException(status_code=status, detail="C:/private/token.sql")

    @app.get("/raise/unexpected")
    async def raise_unexpected() -> None:
        raise RuntimeError("Secret internal failure with /path/to/secret.key")

    return app


@pytest.mark.anyio
async def test_http_error_does_not_publish_forged_instance_code(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        response = await client.get("/raise/forged-code")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "contract.storage"
    assert "private_secret_token" not in response.text
    assert "C:/private" not in response.text


@pytest.mark.anyio
async def test_contract_validation_error(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/raise/contract-validation")
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "contract.validation"
        assert data["error"]["message"] == "Request is invalid"
        assert data["error"]["category"] == "invalid_input"
        assert resp.headers["X-Mnemo-Correlation-ID"] == data["error"]["correlation_id"]
        assert data["error"]["details"] == {}
        assert data["error"]["retryable"] is False


@pytest.mark.anyio
async def test_contract_validation_error_with_details(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/raise/contract-validation-with-details")
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "contract.validation"
        assert data["error"]["details"] == {"field": "query", "reason": "empty"}


@pytest.mark.anyio
async def test_not_found_error(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/raise/not-found")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "contract.not_found"
        assert data["error"]["retryable"] is False


@pytest.mark.anyio
async def test_conflict_error(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/raise/conflict")
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"]["code"] == "contract.conflict"
        assert data["error"]["retryable"] is False


@pytest.mark.anyio
async def test_unsupported_error(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/raise/unsupported")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "contract.unsupported"
        assert data["error"]["retryable"] is False


@pytest.mark.anyio
async def test_integrity_error(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/raise/integrity")
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "contract.integrity"
        assert data["error"]["retryable"] is False


@pytest.mark.anyio
async def test_lifecycle_errors(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp1 = await client.get("/raise/lifecycle")
        assert resp1.status_code == 503
        assert resp1.json()["error"]["code"] == "contract.lifecycle"

        resp2 = await client.get("/raise/engine-lifecycle")
        assert resp2.status_code == 503
        assert resp2.json()["error"]["code"] == "engine.lifecycle"


@pytest.mark.anyio
async def test_dependency_unavailable_errors(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp1 = await client.get("/raise/dependency-unavailable")
        assert resp1.status_code == 503
        data1 = resp1.json()
        assert data1["error"]["code"] == "contract.dependency_unavailable"
        assert data1["error"]["retryable"] is True

        resp2 = await client.get("/raise/engine-initialization")
        assert resp2.status_code == 503
        data2 = resp2.json()
        assert data2["error"]["code"] == "engine.initialization"
        assert data2["error"]["retryable"] is True


@pytest.mark.anyio
async def test_timeout_and_cancelled_errors(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp1 = await client.get("/raise/timeout")
        assert resp1.status_code == 504
        assert resp1.json()["error"]["code"] == "contract.timeout"
        assert resp1.json()["error"]["retryable"] is True

        resp2 = await client.get("/raise/cancelled")
        assert resp2.status_code == 499
        assert resp2.json()["error"]["code"] == "contract.cancelled"
        assert resp2.json()["error"]["retryable"] is False


@pytest.mark.anyio
async def test_storage_error(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/raise/storage")
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "contract.storage"


@pytest.mark.anyio
async def test_nested_schema_error_preserves_safe_origin(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.get("/raise/nested-schema")
    assert resp.status_code == 503
    data = resp.json()["error"]
    assert data["category"] == "schema_compatibility"
    assert data["origin_code"] == "contract.storage"
    assert data["reason"] == "PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA"
    assert "credential.sql" not in resp.text
    assert "sq-2:sparse" not in resp.text
    assert resp.headers["X-Mnemo-Correlation-ID"] == data["correlation_id"]


@pytest.mark.anyio
async def test_plugin_and_knowledge_engine_errors(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp1 = await client.get("/raise/plugin")
        assert resp1.status_code == 500
        assert resp1.json()["error"]["code"] == "contract.plugin"

        resp2 = await client.get("/raise/knowledge-engine")
        assert resp2.status_code == 500
        assert resp2.json()["error"]["code"] == "engine.error"

        resp3 = await client.get("/raise/interface-error")
        assert resp3.status_code == 500
        assert resp3.json()["error"]["code"] == "interface.error"


@pytest.mark.anyio
async def test_request_validation_error(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp = await client.post("/validate-body", json={"name": "a"})
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "http.validation"
        assert data["error"]["message"] == "Request is invalid"
        assert data["error"]["details"] == {}


@pytest.mark.anyio
async def test_http_exceptions(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        resp1 = await client.get("/raise/http-exception")
        assert resp1.status_code == 403
        data1 = resp1.json()
        assert data1["error"]["code"] == "http.403"
        assert data1["error"]["message"] == "Resource access is forbidden"
        assert data1["error"]["retryable"] is False

        resp2 = await client.get("/raise/http-503")
        assert resp2.status_code == 503
        data2 = resp2.json()
        assert data2["error"]["code"] == "http.503"
        assert data2["error"]["retryable"] is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "category"),
    [
        (400, "invalid_input"),
        (401, "unauthorized"),
        (404, "not_found"),
        (408, "timeout"),
        (501, "capability_unavailable"),
        (502, "transport_failure"),
        (504, "timeout"),
        (500, "server_failure"),
    ],
)
async def test_http_status_mapping_is_sanitized(
    error_app: FastAPI, status: int, category: str
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app), base_url="http://test"
    ) as client:
        response = await client.get(f"/raise/http-status/{status}")
    assert response.status_code == status
    error = response.json()["error"]
    assert error["category"] == category
    assert error["code"] == f"http.{status}"
    assert "private" not in response.text
    assert response.headers["X-Mnemo-Correlation-ID"] == error["correlation_id"]


@pytest.mark.anyio
async def test_unexpected_exception_sanitization(error_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=error_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.get("/raise/unexpected")
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "internal.error"
        assert data["error"]["message"] == "An unexpected internal server error occurred."
        assert data["error"]["details"] == {}
        # Verify no leakage of internal path or details
        assert "secret.key" not in json.dumps(data)
