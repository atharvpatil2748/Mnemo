"""Tests for the Module 1.2 shared exception contract."""

import pytest
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


@pytest.mark.parametrize(
    ("error_type", "code", "retryable"),
    [
        (ContractValidationError, "contract.validation", False),
        (NotFoundError, "contract.not_found", False),
        (ConflictError, "contract.conflict", False),
        (UnsupportedError, "contract.unsupported", False),
        (IntegrityError, "contract.integrity", False),
        (LifecycleError, "contract.lifecycle", False),
        (DependencyUnavailableError, "contract.dependency_unavailable", True),
        (OperationTimeoutError, "contract.timeout", True),
        (OperationCancelledError, "contract.cancelled", False),
        (StorageError, "contract.storage", False),
        (PluginError, "contract.plugin", False),
    ],
)
def test_exception_taxonomy_has_stable_metadata(
    error_type: type[MnemoInterfaceError],
    code: str,
    retryable: bool,
) -> None:
    """Every public exception carries its stable code and retry default."""
    details = FrozenMetadata({"error.operation": "test"})
    error = error_type("failed", details=details)

    assert str(error) == "failed"
    assert error.message == "failed"
    assert error.code == code
    assert error.retryable is retryable
    assert error.details == details
    assert isinstance(error, MnemoInterfaceError)


def test_exception_retryability_can_be_set_by_the_failure_boundary() -> None:
    """A concrete failure may refine the taxonomy's retryability default."""
    assert StorageError("busy", retryable=True).retryable


@pytest.mark.parametrize(
    "factory",
    [
        lambda: StorageError(" "),
        lambda: StorageError("failed", retryable=1),  # type: ignore[arg-type]
        lambda: StorageError("failed", details={}),  # type: ignore[arg-type]
    ],
)
def test_exception_metadata_validation(factory: object) -> None:
    """Contract exceptions reject malformed descriptive fields."""
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]
