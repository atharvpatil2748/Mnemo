"""One fail-closed public error contract for HTTP and MCP tool boundaries."""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from mnemo.cursors import CursorInvalidError
from mnemo.interfaces import (
    ConflictError,
    ContractValidationError,
    DeliveryAuthorizationError,
    DeliveryCursorError,
    DeliveryLimitExceededError,
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
from mnemo.storage.chunk_read_model import CHUNK_READ_FAILURE, CHUNK_SCHEMA_REASONS

_LOGGER = logging.getLogger(__name__)
_SAFE_INTERFACE_CODES = frozenset(
    {
        "interface.error",
        "contract.validation",
        "contract.not_found",
        "contract.conflict",
        "contract.unsupported",
        "contract.integrity",
        "contract.lifecycle",
        "contract.dependency_unavailable",
        "contract.timeout",
        "contract.cancelled",
        "contract.storage",
        "contract.plugin",
        "delivery.size_exceeded",
        "delivery.cursor_invalid",
        "delivery.cursor_expired",
        "delivery.cursor_conflict",
        "delivery.forbidden",
        "cursor.invalid",
        "cursor.expired",
        "cursor.conflict",
        "cursor.key_unavailable",
        "processing.policy",
        "processing.admission",
        "registry.error",
        "registry.frozen",
        "registry.registration_conflict",
        "registry.incompatible_plugin",
        "registry.invalid_plugin",
        "registry.discovery",
        "engine.error",
        "engine.lifecycle",
        "engine.initialization",
    }
)
_SAFE_DETAIL_FIELDS = frozenset({"query"})
_SAFE_DETAIL_REASONS = frozenset({"empty", "bad_value"})


class ErrorCategory(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CONFIGURATION_MISMATCH = "configuration_mismatch"
    SCHEMA_COMPATIBILITY = "schema_compatibility"
    RETRIEVAL_FAILURE = "retrieval_failure"
    TRANSPORT_FAILURE = "transport_failure"
    TIMEOUT = "timeout"
    SERVER_FAILURE = "server_failure"


_PUBLIC_MESSAGES = {
    ErrorCategory.INVALID_INPUT: "Request is invalid",
    ErrorCategory.UNAUTHORIZED: "Authentication is required",
    ErrorCategory.NOT_FOUND: "authorized resource was not found",
    ErrorCategory.CAPABILITY_UNAVAILABLE: "Requested capability is not ready or unavailable",
    ErrorCategory.CONFIGURATION_MISMATCH: "Server configuration is unavailable",
    ErrorCategory.SCHEMA_COMPATIBILITY: "Stored schema is incompatible with this operation",
    ErrorCategory.RETRIEVAL_FAILURE: "Retrieval failed",
    ErrorCategory.TRANSPORT_FAILURE: "Transport failed",
    ErrorCategory.TIMEOUT: "Operation timed out",
    ErrorCategory.SERVER_FAILURE: "An unexpected internal server error occurred.",
}


@dataclass(frozen=True, slots=True)
class TypedPublicError:
    category: ErrorCategory
    code: str
    correlation_id: UUID
    layer: str
    reason: str
    status: int
    retryable: bool = False
    origin_code: str | None = None
    details: dict[str, str] | None = None

    def body(self) -> dict[str, object]:
        return {
            "code": self.code,
            "category": self.category.value,
            "message": (
                "Resource access is forbidden"
                if self.category is ErrorCategory.UNAUTHORIZED and self.status == 403
                else _PUBLIC_MESSAGES[self.category]
            ),
            "details": self.details or {},
            "retryable": self.retryable,
            "origin_code": self.origin_code,
            "layer": self.layer,
            "reason": self.reason,
            "correlation_id": str(self.correlation_id),
        }


def _origin(error: BaseException) -> MnemoInterfaceError | None:
    """Take only a known typed cause, never an arbitrary exception message."""
    if isinstance(error, (NotFoundError, DeliveryAuthorizationError)):
        return error
    current: BaseException | None = error
    selected: MnemoInterfaceError | None = None
    for _ in range(8):
        if current is None:
            break
        if isinstance(current, MnemoInterfaceError):
            selected = current
        current = current.__cause__
    return selected


def _safe_details(error: MnemoInterfaceError | None) -> dict[str, str]:
    if error is None:
        return {}
    details: dict[str, str] = {}
    for key, value in error.details.items():
        if not isinstance(value, str):
            continue
        if (key == "field" and value in _SAFE_DETAIL_FIELDS) or (
            key == "reason" and value in _SAFE_DETAIL_REASONS
        ):
            details[key] = value
        elif key == "execution_id":
            with suppress(ValueError):
                details[key] = str(UUID(value))
    return details


def _trusted_code(error: MnemoInterfaceError) -> str:
    """Use a vetted class declaration, never a mutable instance attribute."""
    for cls in type(error).__mro__:
        if cls is MnemoInterfaceError:
            break
        declared = cls.__dict__.get("code")
        if isinstance(declared, str) and declared in _SAFE_INTERFACE_CODES:
            return declared
    return MnemoInterfaceError.code


def classify_public_error(
    error: BaseException, correlation_id: UUID | None = None
) -> TypedPublicError:
    """Classify from exception *types* and vetted codes, never raw messages."""
    correlation = correlation_id if isinstance(correlation_id, UUID) else uuid4()
    origin = _origin(error)
    code_owner = (
        error
        if isinstance(error, MnemoInterfaceError) and not isinstance(error, PluginError)
        else origin
    )
    code = _trusted_code(code_owner) if code_owner is not None else "internal.error"
    origin_code = _trusted_code(origin) if origin is not None else None
    reason = code if origin is not None else "unexpected_failure"
    layer = "server"
    retryable = bool(code_owner.retryable) if code_owner is not None else False
    if isinstance(error, NotFoundError):
        return TypedPublicError(
            ErrorCategory.NOT_FOUND,
            "contract.not_found",
            correlation,
            "authorization",
            "resource_unavailable",
            404,
        )
    if isinstance(error, DeliveryAuthorizationError):
        return TypedPublicError(
            ErrorCategory.UNAUTHORIZED,
            "delivery.forbidden",
            correlation,
            "authorization",
            "access_denied",
            403,
        )
    if isinstance(error, PermissionError):
        return TypedPublicError(
            ErrorCategory.UNAUTHORIZED,
            "auth.unauthorized",
            correlation,
            "authentication",
            "principal_required",
            401,
        )
    if isinstance(error, (TimeoutError, OperationTimeoutError)) or (
        isinstance(error, PluginError) and isinstance(origin, OperationTimeoutError)
    ):
        return TypedPublicError(
            ErrorCategory.TIMEOUT,
            code if origin else "contract.timeout",
            correlation,
            "execution",
            "deadline_expired",
            504,
            True,
            origin_code,
            _safe_details(error if isinstance(error, MnemoInterfaceError) else origin),
        )
    if isinstance(error, (ConnectionError, BrokenPipeError)):
        return TypedPublicError(
            ErrorCategory.TRANSPORT_FAILURE,
            "transport.failure",
            correlation,
            "transport",
            "connection_failed",
            502,
            True,
        )
    if isinstance(error, OperationCancelledError):
        return TypedPublicError(
            ErrorCategory.TRANSPORT_FAILURE,
            _trusted_code(error),
            correlation,
            "transport",
            "operation_cancelled",
            499,
            False,
            _trusted_code(error),
        )
    if isinstance(
        error,
        (
            ContractValidationError,
            DeliveryCursorError,
            DeliveryLimitExceededError,
            ConflictError,
            ValueError,
            TypeError,
        ),
    ):
        details = _safe_details(origin) if isinstance(error, ContractValidationError) else {}
        status = (
            413
            if isinstance(error, DeliveryLimitExceededError)
            else 409
            if isinstance(error, (DeliveryCursorError, ConflictError))
            else 422
        )
        return TypedPublicError(
            ErrorCategory.INVALID_INPUT,
            code if origin else "contract.validation",
            correlation,
            "request",
            reason if origin else "invalid_request",
            status,
            False,
            origin_code,
            details,
        )
    if isinstance(error, UnsupportedError) or isinstance(origin, UnsupportedError):
        unsupported = error if isinstance(error, UnsupportedError) else origin
        assert isinstance(unsupported, UnsupportedError)
        if unsupported.message in CHUNK_SCHEMA_REASONS:
            return TypedPublicError(
                ErrorCategory.SCHEMA_COMPATIBILITY,
                _trusted_code(unsupported),
                correlation,
                "storage",
                unsupported.message,
                503,
                retryable,
                _trusted_code(unsupported),
            )
        return TypedPublicError(
            ErrorCategory.CAPABILITY_UNAVAILABLE,
            code,
            correlation,
            "capability",
            "unsupported_operation",
            400,
            retryable,
            origin_code,
        )
    if isinstance(error, (DependencyUnavailableError, LifecycleError)):
        return TypedPublicError(
            ErrorCategory.CAPABILITY_UNAVAILABLE,
            code,
            correlation,
            "runtime",
            "dependency_unavailable",
            503,
            retryable,
            origin_code,
            _safe_details(error if isinstance(error, MnemoInterfaceError) else origin),
        )
    if isinstance(error, StorageError) or isinstance(origin, StorageError):
        storage = error if isinstance(error, StorageError) else origin
        assert isinstance(storage, StorageError)
        if storage.message in CHUNK_SCHEMA_REASONS:
            return TypedPublicError(
                ErrorCategory.SCHEMA_COMPATIBILITY,
                _trusted_code(storage),
                correlation,
                "storage",
                storage.message,
                503,
                retryable,
                _trusted_code(storage),
            )
        if storage.message == CHUNK_READ_FAILURE:
            return TypedPublicError(
                ErrorCategory.RETRIEVAL_FAILURE,
                _trusted_code(storage),
                correlation,
                "storage",
                CHUNK_READ_FAILURE,
                503,
                retryable,
                _trusted_code(storage),
            )
        return TypedPublicError(
            ErrorCategory.RETRIEVAL_FAILURE,
            code,
            correlation,
            "storage",
            "storage_failure",
            503,
            retryable,
            origin_code,
        )
    if isinstance(error, PluginError):
        return TypedPublicError(
            ErrorCategory.RETRIEVAL_FAILURE,
            code,
            correlation,
            "retrieval",
            "provider_failure",
            500,
            retryable,
            origin_code,
        )
    if isinstance(error, IntegrityError) and isinstance(origin, CursorInvalidError):
        return TypedPublicError(
            ErrorCategory.INVALID_INPUT,
            "cursor.invalid",
            correlation,
            "request",
            "invalid_cursor",
            422,
            False,
            "cursor.invalid",
        )
    if isinstance(error, IntegrityError):
        return TypedPublicError(
            ErrorCategory.CONFIGURATION_MISMATCH,
            code,
            correlation,
            "runtime",
            "integrity_failure",
            500,
            retryable,
            origin_code,
        )
    if isinstance(error, MnemoInterfaceError):
        _LOGGER.warning("Unclassified interface error at public boundary: %s", type(error).__name__)
        return TypedPublicError(
            ErrorCategory.SERVER_FAILURE,
            code,
            correlation,
            layer,
            reason,
            500,
            retryable,
            origin_code,
        )
    return TypedPublicError(
        ErrorCategory.SERVER_FAILURE,
        "internal.error",
        correlation,
        layer,
        "unexpected_failure",
        500,
    )
