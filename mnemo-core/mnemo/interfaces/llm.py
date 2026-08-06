"""Language-model provider contract."""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from mnemo.models import JSONValue

from .types import CompletionResult, HealthStatus, LLMCapabilities, Message


@runtime_checkable
class LLMInterface(Protocol):  # pragma: no cover
    """Provide knowledge-engine language-model operations without tool use."""

    @property
    def provider(self) -> str:
        """Return the stable provider identifier."""
        ...

    @property
    def model(self) -> str:
        """Return the configured model identifier."""
        ...

    @property
    def max_context_tokens(self) -> int:
        """Return the positive context-window limit."""
        ...

    def capabilities(self) -> LLMCapabilities:
        """Return immutable descriptive model capabilities."""
        ...

    async def complete(
        self,
        system: str,
        messages: tuple[Message, ...],
        structured_output: JSONValue = None,
        max_tokens: int = 1000,
    ) -> CompletionResult:
        """Produce one text or schema-conforming structured completion."""
        ...

    def stream(
        self,
        system: str,
        messages: tuple[Message, ...],
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        """Stream ordered non-empty text fragments asynchronously."""
        ...

    async def health_check(self) -> HealthStatus:
        """Return a transport-independent provider health observation."""
        ...
