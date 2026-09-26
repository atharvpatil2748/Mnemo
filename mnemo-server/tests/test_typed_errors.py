"""Adversarial tests for the shared, nonreflecting public error contract."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from mnemo.cursors import CursorInvalidError
from mnemo.interfaces import (
    ContractValidationError,
    DeliveryAuthorizationError,
    DeliveryCursorError,
    DependencyUnavailableError,
    IntegrityError,
    LifecycleError,
    NotFoundError,
    OperationCancelledError,
    OperationTimeoutError,
    PluginError,
    StorageError,
    UnsupportedError,
)
from mnemo.models import FrozenMetadata
from mnemo_server.typed_errors import ErrorCategory, classify_public_error

_SECRET = "C:/private/credential-token.db SELECT * FROM secrets"


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (ValueError(_SECRET), ErrorCategory.INVALID_INPUT),
        (PermissionError(_SECRET), ErrorCategory.UNAUTHORIZED),
        (NotFoundError(_SECRET), ErrorCategory.NOT_FOUND),
        (DeliveryAuthorizationError(_SECRET), ErrorCategory.UNAUTHORIZED),
        (DependencyUnavailableError(_SECRET), ErrorCategory.CAPABILITY_UNAVAILABLE),
        (LifecycleError(_SECRET), ErrorCategory.CAPABILITY_UNAVAILABLE),
        (UnsupportedError(_SECRET), ErrorCategory.CAPABILITY_UNAVAILABLE),
        (IntegrityError(_SECRET), ErrorCategory.CONFIGURATION_MISMATCH),
        (StorageError(_SECRET), ErrorCategory.RETRIEVAL_FAILURE),
        (PluginError(_SECRET), ErrorCategory.RETRIEVAL_FAILURE),
        (ConnectionError(_SECRET), ErrorCategory.TRANSPORT_FAILURE),
        (OperationCancelledError(_SECRET), ErrorCategory.TRANSPORT_FAILURE),
        (DeliveryCursorError(_SECRET), ErrorCategory.INVALID_INPUT),
        (OperationTimeoutError(_SECRET), ErrorCategory.TIMEOUT),
        (RuntimeError(_SECRET), ErrorCategory.SERVER_FAILURE),
    ],
)
def test_category_and_nonreflection(error: Exception, category: ErrorCategory) -> None:
    public = classify_public_error(error)
    assert public.category == category
    assert UUID(str(public.correlation_id))
    assert _SECRET not in json.dumps(public.body())
    assert "SELECT" not in json.dumps(public.body())


def test_known_schema_reason_survives_nested_retrieval_wrapper() -> None:
    try:
        try:
            raise StorageError("PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA")
        except StorageError as error:
            raise PluginError("sq-2:sparse") from error
    except PluginError as error:
        public = classify_public_error(error)
    assert public.category == ErrorCategory.SCHEMA_COMPATIBILITY
    assert public.reason == "PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA"
    assert public.origin_code == "contract.storage"


def test_wrapped_invalid_cursor_is_input_without_leaking_client_text() -> None:
    try:
        try:
            raise CursorInvalidError(_SECRET)
        except CursorInvalidError as error:
            raise IntegrityError("advanced retrieval cursor is invalid") from error
    except IntegrityError as error:
        public = classify_public_error(error)
    assert public.category == ErrorCategory.INVALID_INPUT
    assert public.code == "cursor.invalid"
    assert public.origin_code == "cursor.invalid"
    assert public.reason == "invalid_cursor"
    assert public.status == 422
    assert _SECRET not in json.dumps(public.body())


def test_unknown_storage_reason_is_not_echoed() -> None:
    public = classify_public_error(StorageError(_SECRET))
    assert public.reason == "storage_failure"
    assert _SECRET not in json.dumps(public.body())


def test_unknown_and_inaccessible_resources_have_same_public_shape() -> None:
    unknown = classify_public_error(NotFoundError("unknown " + _SECRET)).body()
    # Governed production delivery maps both cases to NotFoundError before this
    # boundary; legacy direct DeliveryAuthorizationError retains HTTP 403.
    denied = classify_public_error(NotFoundError("denied " + _SECRET)).body()
    unknown.pop("correlation_id")
    denied.pop("correlation_id")
    assert unknown == denied


def test_legacy_direct_delivery_denial_is_generic() -> None:
    denied = classify_public_error(DeliveryAuthorizationError(_SECRET))
    assert denied.status == 403
    assert denied.body()["message"] == "Resource access is forbidden"
    assert _SECRET not in json.dumps(denied.body())


def test_correlation_is_distinct_and_client_message_is_not_reflected() -> None:
    first = classify_public_error(ContractValidationError(_SECRET))
    second = classify_public_error(ContractValidationError(_SECRET))
    assert first.correlation_id != second.correlation_id
    assert _SECRET not in json.dumps(first.body())


def test_only_allowlisted_safe_details_are_published() -> None:
    error = ContractValidationError(
        _SECRET,
        details=FrozenMetadata(
            {"field": "query", "reason": "bad_value", "path": _SECRET, "execution_id": _SECRET}
        ),
    )
    assert classify_public_error(error).body()["details"] == {
        "field": "query",
        "reason": "bad_value",
    }


def test_authorized_execution_id_is_preserved_but_other_details_are_not() -> None:
    execution_id = "065175a3-80b5-4018-871e-d1cdf12d5b30"
    error = OperationTimeoutError(
        _SECRET,
        details=FrozenMetadata({"execution_id": execution_id, "db_path": _SECRET}),
    )
    assert classify_public_error(error).body()["details"] == {"execution_id": execution_id}


def test_dependency_wrapper_keeps_public_contract_and_safe_inner_origin() -> None:
    execution_id = "065175a3-80b5-4018-871e-d1cdf12d5b30"
    try:
        raise StorageError(_SECRET)
    except StorageError as origin:
        error = DependencyUnavailableError(
            "timeout reconciliation unavailable",
            details=FrozenMetadata({"execution_id": execution_id}),
        )
        error.__cause__ = origin
    public = classify_public_error(error)
    assert public.category is ErrorCategory.CAPABILITY_UNAVAILABLE
    assert public.code == "contract.dependency_unavailable"
    assert public.origin_code == "contract.storage"
    assert public.body()["details"] == {"execution_id": execution_id}
    assert _SECRET not in json.dumps(public.body())


def test_only_allowlisted_schema_reason_is_published() -> None:
    allowed = classify_public_error(StorageError("CHUNK_READ_SCHEMA_INCOMPATIBLE"))
    unknown = classify_public_error(StorageError("NOT_A_GOVERNED_SCHEMA_REASON"))
    assert allowed.category is ErrorCategory.SCHEMA_COMPATIBILITY
    assert unknown.category is ErrorCategory.RETRIEVAL_FAILURE
    assert unknown.reason == "storage_failure"


def test_instance_code_cannot_forge_public_origin() -> None:
    error = StorageError("ordinary storage failure")
    error.code = "private_secret_token"
    public = classify_public_error(error)
    assert public.code == "contract.storage"
    assert public.origin_code == "contract.storage"
    assert "private_secret_token" not in json.dumps(public.body())


def test_token_shaped_untrusted_details_are_not_public() -> None:
    error = ContractValidationError(
        "invalid request",
        details=FrozenMetadata({"field": "private_secret_token", "reason": "private_secret_token"}),
    )
    assert classify_public_error(error).body()["details"] == {}


def test_malformed_correlation_is_replaced_with_server_uuid() -> None:
    public = classify_public_error(ValueError("invalid"), "private_secret_token")  # type: ignore[arg-type]
    assert isinstance(public.correlation_id, UUID)
    assert "private_secret_token" not in json.dumps(public.body())


def test_nested_provider_timeout_keeps_timeout_category() -> None:
    try:
        try:
            raise OperationTimeoutError("deadline exceeded")
        except OperationTimeoutError as origin:
            raise PluginError("sq-2:sparse") from origin
    except PluginError as error:
        public = classify_public_error(error)
    assert public.category is ErrorCategory.TIMEOUT
    assert public.origin_code == "contract.timeout"
    assert public.reason == "deadline_expired"


@pytest.mark.parametrize(
    ("error", "category", "reason"),
    [
        (
            StorageError("CHUNK_READ_SCHEMA_UNAVAILABLE"),
            "schema_compatibility",
            "CHUNK_READ_SCHEMA_UNAVAILABLE",
        ),
        (StorageError("CHUNK_READ_FAILURE"), "retrieval_failure", "CHUNK_READ_FAILURE"),
        (
            UnsupportedError("PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA"),
            "schema_compatibility",
            "PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA",
        ),
    ],
)
def test_reader_origin_is_typed_without_message_reflection(
    error: Exception, category: str, reason: str
) -> None:
    public = classify_public_error(error)
    assert public.category.value == category
    assert public.reason == reason
    assert public.layer == "storage"
    assert public.origin_code in {"contract.storage", "contract.unsupported"}


@pytest.mark.parametrize(
    ("origin", "category", "reason"),
    [
        (
            StorageError("CHUNK_READ_SCHEMA_INCOMPATIBLE"),
            "schema_compatibility",
            "CHUNK_READ_SCHEMA_INCOMPATIBLE",
        ),
        (StorageError("CHUNK_READ_FAILURE"), "retrieval_failure", "CHUNK_READ_FAILURE"),
        (
            UnsupportedError("PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA"),
            "schema_compatibility",
            "PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA",
        ),
    ],
)
def test_nested_sparse_reader_origin_survives_wrapping(
    origin: Exception, category: str, reason: str
) -> None:
    try:
        raise PluginError("sq-2:sparse") from origin
    except PluginError as wrapper:
        public = classify_public_error(wrapper)
    assert public.category.value == category
    assert public.reason == reason
    assert public.layer == "storage"
    assert public.origin_code in {"contract.storage", "contract.unsupported"}


def test_untrusted_reader_failure_message_cannot_become_public_reason() -> None:
    error = StorageError("CHUNK_READ_FAILURE:C:/private/token.db SELECT * FROM secrets")
    public = classify_public_error(error)
    assert public.reason == "storage_failure"
    assert "private" not in json.dumps(public.body())
