"""HTTP exception translation boundary and standardized JSON error responses."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mnemo.interfaces import ContractValidationError, MnemoInterfaceError
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from mnemo_server.typed_errors import ErrorCategory, TypedPublicError, classify_public_error

_LOGGER = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    """Standardized error payload body."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = Field(default=False)
    category: str | None = None
    origin_code: str | None = None
    layer: str | None = None
    reason: str | None = None
    correlation_id: str | None = None


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
    typed: TypedPublicError | None = None,
) -> JSONResponse:
    """Construct a standardized JSON error response."""
    payload = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or {},
            retryable=retryable,
            category=None if typed is None else typed.category.value,
            origin_code=None if typed is None else typed.origin_code,
            layer=None if typed is None else typed.layer,
            reason=None if typed is None else typed.reason,
            correlation_id=None if typed is None else str(typed.correlation_id),
        )
    ).model_dump()
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={
            **(dict(headers) if headers is not None else {}),
            **({"X-Mnemo-Correlation-ID": str(typed.correlation_id)} if typed else {}),
        },
    )


def _correlation(request: Request) -> UUID:
    existing = getattr(request.state, "correlation_id", None)
    if isinstance(existing, UUID):
        return existing
    created = uuid4()
    request.state.correlation_id = created
    return created


def _typed_response(typed: TypedPublicError, *, code: str | None = None) -> JSONResponse:
    body = typed.body()
    return error_response(
        typed.status,
        code or typed.code,
        str(body["message"]),
        retryable=typed.retryable,
        details=typed.details,
        typed=typed,
    )


def _interface_error_handler(request: Request, exc: MnemoInterfaceError) -> JSONResponse:
    """Map existing stable codes to sanitized category, reason and correlation."""
    typed = classify_public_error(exc, _correlation(request))
    _LOGGER.warning(
        "Public interface failure: correlation=%s type=%s category=%s origin=%s reason=%s",
        typed.correlation_id,
        type(exc).__name__,
        typed.category.value,
        typed.origin_code,
        typed.reason,
    )
    return _typed_response(typed)


def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Never echo pydantic inputs, locations or exception contexts."""
    del exc
    typed = classify_public_error(
        ContractValidationError("request validation"), _correlation(request)
    )
    return _typed_response(typed, code="http.validation")


def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Preserve the HTTP status without reflecting arbitrary detail or headers."""
    correlation = _correlation(request)
    category = (
        ErrorCategory.NOT_FOUND
        if exc.status_code == 404
        else ErrorCategory.UNAUTHORIZED
        if exc.status_code in {401, 403}
        else ErrorCategory.CAPABILITY_UNAVAILABLE
        if exc.status_code in {501, 503}
        else ErrorCategory.TIMEOUT
        if exc.status_code in {408, 504}
        else ErrorCategory.TRANSPORT_FAILURE
        if exc.status_code == 502
        else ErrorCategory.INVALID_INPUT
        if exc.status_code < 500
        else ErrorCategory.SERVER_FAILURE
    )
    typed = TypedPublicError(
        category,
        f"http.{exc.status_code}",
        correlation,
        "http",
        "http_failure",
        exc.status_code,
        exc.status_code in {502, 503, 504},
    )
    return _typed_response(typed)


def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other unhandled exceptions with sanitization."""
    if isinstance(exc, BaseExceptionGroup):
        for sub_exc in exc.exceptions:
            if isinstance(sub_exc, MnemoInterfaceError):
                return _interface_error_handler(request, sub_exc)
    typed = classify_public_error(exc, _correlation(request))
    _LOGGER.error(
        "Unhandled server failure: correlation=%s type=%s", typed.correlation_id, type(exc).__name__
    )
    return _typed_response(typed)


def register_error_handlers(app: FastAPI) -> None:
    """Register all standardized ADR-0049 error handlers on the FastAPI app."""
    app.add_exception_handler(MnemoInterfaceError, _interface_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)
