import hashlib
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mnemo.interfaces.errors import UnsupportedError
from mnemo.interfaces.parser_models import ParseResult
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.models import Document
from mnemo.parsers.router import ParserRouter
from mnemo.registry import PluginRegistry


@pytest.fixture
def mock_registry() -> Mock:
    registry = Mock(spec=PluginRegistry)
    registry.resolve_parser.return_value = None
    return registry


@pytest.fixture
def mock_storage() -> AsyncMock:
    storage = AsyncMock(spec=StorageInterfaceV1)
    storage.get_document_by_content_hash.return_value = None
    return storage


@pytest.fixture
def router(mock_registry: Mock, mock_storage: AsyncMock) -> ParserRouter:
    return ParserRouter(mock_registry, mock_storage)


@pytest.fixture
def mock_parser() -> Mock:
    parser = Mock()
    parsed_result = Mock(spec=ParseResult)
    parser.parse.return_value = parsed_result
    return parser


def test_register_builtins(router: ParserRouter) -> None:
    # Ensure it doesn't crash (currently a NO-OP)
    router.register_builtins()


def test_detect_mime_magic_success(router: ParserRouter) -> None:
    # A generic text file content
    data = b"Hello, world!"
    with patch("magic.from_buffer", return_value="text/plain") as mock_magic:
        mime = router._detect_mime(data, "file.txt")
        assert mime == "text/plain"
        mock_magic.assert_called_once_with(data, mime=True)


def test_detect_mime_magic_octet_stream_fallback(router: ParserRouter) -> None:
    data = b"dummy data"
    with patch("magic.from_buffer", return_value="application/octet-stream"):
        mime = router._detect_mime(data, "file.json")
        assert mime == "application/json"


def test_detect_mime_magic_exception_fallback(router: ParserRouter) -> None:
    data = b"dummy data"
    with patch("magic.from_buffer", side_effect=Exception("Magic failed")):
        mime = router._detect_mime(data, "file.pdf")
        assert mime == "application/pdf"


def test_detect_mime_total_fallback(router: ParserRouter) -> None:
    data = b"dummy data"
    with patch("magic.from_buffer", side_effect=Exception("Magic failed")):
        mime = router._detect_mime(data, "file.unknown")
        assert mime == "application/octet-stream"


@pytest.mark.anyio
async def test_route_deduplication(
    router: ParserRouter, mock_storage: AsyncMock, mock_registry: Mock
) -> None:
    data = b"duplicate data"
    filename = "doc.txt"
    sha256_hash = hashlib.sha256(data).hexdigest()

    mock_doc = Mock(spec=Document)
    mock_storage.get_document_by_content_hash.return_value = mock_doc

    result = await router.route(data, filename)

    assert result is mock_doc
    mock_storage.get_document_by_content_hash.assert_awaited_once_with(sha256_hash)
    mock_registry.resolve_parser.assert_not_called()


@pytest.mark.anyio
async def test_route_successful_parse_by_mime(
    router: ParserRouter, mock_storage: AsyncMock, mock_registry: Mock, mock_parser: Mock
) -> None:
    data = b"content"
    filename = "test.txt"

    mock_registry.resolve_parser.return_value = mock_parser

    with patch.object(router, "_detect_mime", return_value="text/plain"):
        result = await router.route(data, filename)

    assert result is mock_parser.parse.return_value
    mock_registry.resolve_parser.assert_called_once_with("text/plain")
    mock_parser.parse.assert_called_once()

    # Check metadata passed to parse
    args, _kwargs = mock_parser.parse.call_args

    assert args[0] == data
    assert args[1] == filename
    metadata = args[2]
    assert metadata.mime_type == "text/plain"
    assert metadata.content_hash == hashlib.sha256(data).hexdigest()
    assert metadata.size_bytes == len(data)


@pytest.mark.anyio
async def test_route_successful_parse_by_extension(
    router: ParserRouter, mock_storage: AsyncMock, mock_registry: Mock, mock_parser: Mock
) -> None:
    data = b"content"
    filename = "test.custom"

    # MIME lookup fails, extension lookup succeeds
    def mock_resolve_parser(key: str) -> Mock | None:
        if key == "application/octet-stream":
            return None
        if key == ".custom":
            return mock_parser
        return None

    mock_registry.resolve_parser.side_effect = mock_resolve_parser

    with patch.object(router, "_detect_mime", return_value="application/octet-stream"):
        result = await router.route(data, filename)

    assert result is mock_parser.parse.return_value
    assert mock_registry.resolve_parser.call_count == 2
    mock_parser.parse.assert_called_once()


@pytest.mark.anyio
async def test_route_unsupported_format(
    router: ParserRouter, mock_storage: AsyncMock, mock_registry: Mock
) -> None:
    data = b"content"
    filename = "test.unknown"

    mock_registry.resolve_parser.return_value = None

    with (
        patch.object(router, "_detect_mime", return_value="application/octet-stream"),
        pytest.raises(
            UnsupportedError,
            match=(
                r"No parser found for MIME type 'application/octet-stream' "
                r"or extension '\.unknown'"
            ),
        ),
    ):
        await router.route(data, filename)


@pytest.mark.anyio
async def test_route_parser_exception_propagation(
    router: ParserRouter, mock_storage: AsyncMock, mock_registry: Mock, mock_parser: Mock
) -> None:
    data = b"content"
    filename = "test.txt"

    mock_registry.resolve_parser.return_value = mock_parser
    mock_parser.parse.side_effect = ValueError("Parser failed")

    with pytest.raises(ValueError, match="Parser failed"):
        await router.route(data, filename)


@pytest.mark.anyio
async def test_route_registry_exception_propagation(
    router: ParserRouter, mock_storage: AsyncMock, mock_registry: Mock
) -> None:
    data = b"content"
    filename = "test.txt"

    mock_registry.resolve_parser.side_effect = RuntimeError("Registry error")

    with pytest.raises(RuntimeError, match="Registry error"):
        await router.route(data, filename)
