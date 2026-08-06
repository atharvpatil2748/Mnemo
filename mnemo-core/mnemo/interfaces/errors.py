"""Shared contract-only exception taxonomy for public core interfaces."""

from typing import ClassVar

from mnemo.models import FrozenMetadata
from mnemo.models._shared import require_non_empty

_EMPTY_DETAILS = FrozenMetadata()


class MnemoInterfaceError(Exception):
    """Base exception carrying stable, transport-independent error metadata."""

    code: ClassVar[str] = "interface.error"
    default_retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        *,
        retryable: bool | None = None,
        details: FrozenMetadata = _EMPTY_DETAILS,
    ) -> None:
        """Initialize descriptive fields for an interface failure."""
        require_non_empty(message, "message")
        if retryable is not None and not isinstance(retryable, bool):
            raise TypeError("retryable must be a boolean")
        if not isinstance(details, FrozenMetadata):
            raise TypeError("details must be FrozenMetadata")
        super().__init__(message)
        self.message = message
        self.retryable = self.default_retryable if retryable is None else retryable
        self.details = details


class ContractValidationError(MnemoInterfaceError):
    """Input violates a public contract invariant."""

    code = "contract.validation"


class NotFoundError(MnemoInterfaceError):
    """A requested stable identity does not exist."""

    code = "contract.not_found"


class ConflictError(MnemoInterfaceError):
    """An identity, version, priority, or optimistic-state conflict occurred."""

    code = "contract.conflict"


class UnsupportedError(MnemoInterfaceError):
    """Valid input requests an unsupported format or capability."""

    code = "contract.unsupported"


class IntegrityError(MnemoInterfaceError):
    """A content, dimension, relationship, or record integrity check failed."""

    code = "contract.integrity"


class LifecycleError(MnemoInterfaceError):
    """A component is in an invalid lifecycle state."""

    code = "contract.lifecycle"


class DependencyUnavailableError(MnemoInterfaceError):
    """A required local provider or infrastructure dependency is unavailable."""

    code = "contract.dependency_unavailable"
    default_retryable = True


class OperationTimeoutError(MnemoInterfaceError):
    """A public contract deadline expired."""

    code = "contract.timeout"
    default_retryable = True


class OperationCancelledError(MnemoInterfaceError):
    """A caller or cooperative cancellation completed."""

    code = "contract.cancelled"


class StorageError(MnemoInterfaceError):
    """A storage operation failed without leaking a vendor exception."""

    code = "contract.storage"


class PluginError(MnemoInterfaceError):
    """Plugin registration or invocation failed at an isolation boundary."""

    code = "contract.plugin"
