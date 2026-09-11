"""Parser contract for raw document bytes."""

from typing import Protocol, runtime_checkable

from mnemo.interfaces.parser_models import ParseResult, ParseResultV2

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


@runtime_checkable
class ParserInterfaceV2(ParserInterfaceV1, Protocol):  # pragma: no cover
    """Additive pure parser contract for typed asset occurrences and omissions."""

    def parse_with_assets(
        self,
        data: bytes,
        filename: str,
        metadata: FileMetadata,
    ) -> ParseResultV2:
        """Return frozen V1 text plus bounded asset-discovery evidence."""
        ...
