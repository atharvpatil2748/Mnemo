"""HTTP exception translation boundary and standardized JSON error responses."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

_LOGGER = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    """Standardized error payload body."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = Field(default=False)


class ErrorEnvelope(BaseModel):
    """Standardized root error response envelope."""

    model_config = ConfigDict(frozen=True)

    error: ErrorBody


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Construct a standardized JSON error response."""
    payload = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or {},
            retryable=retryable,
        )
    ).model_dump()
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers=dict(headers) if headers is not None else None,
    )


def _interface_error_handler(request: Request, exc: MnemoInterfaceError) -> JSONResponse:
    """Handle core MnemoInterfaceError exceptions according to ADR-0049 mapping."""
    details = dict(exc.details) if hasattr(exc, "details") and exc.details else {}
    code = getattr(exc, "code", "interface.error")
    retryable = getattr(exc, "retryable", False)

    match exc:
        case ContractValidationError():
            return error_response(422, code, exc.message, details=details, retryable=retryable)
        case NotFoundError():
            return error_response(404, code, exc.message, details=details, retryable=retryable)
        case ConflictError():
            return error_response(409, code, exc.message, details=details, retryable=retryable)
        case UnsupportedError():
            return error_response(400, code, exc.message, details=details, retryable=retryable)
        case IntegrityError():
            _LOGGER.error("Integrity error encountered: %s", exc.message)
            return error_response(500, code, exc.message, details=details, retryable=retryable)
        case EngineLifecycleError() | LifecycleError():
            return error_response(503, code, exc.message, details=details, retryable=retryable)
        case EngineInitializationError() | DependencyUnavailableError():
            return error_response(503, code, exc.message, details=details, retryable=retryable)
        case OperationTimeoutError():
            return error_response(504, code, exc.message, details=details, retryable=retryable)
        case OperationCancelledError():
            return error_response(499, code, exc.message, details=details, retryable=retryable)
        case StorageError():
            _LOGGER.error("Storage error encountered: %s", exc.message)
            return error_response(503, code, exc.message, details=details, retryable=retryable)
        case PluginError():
            _LOGGER.error("Plugin error encountered: %s", exc.message)
            return error_response(500, code, exc.message, details=details, retryable=retryable)
        case KnowledgeEngineError():
            _LOGGER.error("KnowledgeEngine error encountered: %s", exc.message)
            return error_response(500, code, exc.message, details=details, retryable=retryable)
        case _:
            _LOGGER.error("Unclassified core interface error: %s", exc.message)
            return error_response(500, code, exc.message, details=details, retryable=retryable)


def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI request validation errors."""
    return error_response(
        422,
        "http.validation",
        "Request validation failed",
        details={"validation_errors": exc.errors()},
        retryable=False,
    )


def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle Starlette / FastAPI HTTPExceptions."""
    message = str(exc.detail) if exc.detail else "HTTP request failed"
    retryable = exc.status_code in (502, 503, 504)
    code = f"http.{exc.status_code}"
    return error_response(
        exc.status_code,
        code,
        message,
        details={},
        retryable=retryable,
        headers=exc.headers,
    )


def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other unhandled exceptions with sanitization."""
    _LOGGER.exception("Unhandled server exception: %s", exc)
    return error_response(
        500,
        "internal.error",
        "An unexpected internal server error occurred.",
        details={},
        retryable=False,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all standardized ADR-0049 error handlers on the FastAPI app."""
    app.add_exception_handler(MnemoInterfaceError, _interface_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)
