"""Canonical local token-counting contract."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TokenCounterInterfaceV1(Protocol):  # pragma: no cover
    """Count ordinary document text deterministically without network access."""

    @property
    def tokenizer_id(self) -> str:
        """Return the stable engine, adapter, and asset identity."""
        ...

    def count(self, text: str) -> int:
        """Return the number of canonical tokens in text."""
        ...
