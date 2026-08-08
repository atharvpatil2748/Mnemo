"""Parser contract for raw document bytes."""

from typing import Protocol, runtime_checkable

from mnemo.interfaces.parser_models import ParseResult

from .types import FileMetadata, ParserCapabilities


@runtime_checkable
class ParserInterfaceV1(Protocol):  # pragma: no cover
    """Convert raw bytes into a ParseResult without I/O side effects."""

    @property
    def supported_formats(self) -> tuple[str, ...]:
        """Return the case-normalized formats accepted by this parser."""
        ...

    def capabilities(self) -> ParserCapabilities:
        """Return immutable descriptive parser capabilities."""
        ...

    def parse(
        self,
        data: bytes,
        filename: str,
        metadata: FileMetadata,
    ) -> ParseResult:
        """Parse bytes synchronously without network or persistent writes."""
        ...


ParserInterface = ParserInterfaceV1
