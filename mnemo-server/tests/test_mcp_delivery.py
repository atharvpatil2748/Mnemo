"""Additive MCP document and asset delivery tests."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import mcp.types as types
import pytest
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import ContractValidationError, DeliveryAuthorizationError
from mnemo.models import (
    BinaryDelivery,
    DeliveryAttribution,
    DeliveryCompleteness,
    DeliveryItem,
    DeliveryResourceKind,
    DeliveryResponse,
    DeliveryUsage,
)
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.tools import execute_mcp_tool, get_mcp_tools


def _engine() -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    return engine


def _values():  # type: ignore[no-untyped-def]
    notebook_id, document_id, version_id, source_id, occurrence_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    attribution = DeliveryAttribution(
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        asset_id=uuid4(),
        occurrence_id=occurrence_id,
        modality="image",
    )
    response = DeliveryResponse(
        resource_kind=DeliveryResourceKind.DOCUMENT,
        snapshot_identity="a" * 64,
        completeness=DeliveryCompleteness.COMPLETE,
        items=(
            DeliveryItem(
                index=0,
                kind="evidence",
                attribution=attribution,
                payload={"safe": True},
                byte_size=4,
            ),
        ),
        usage=DeliveryUsage(items=1, bytes=4),
    )
    binary = BinaryDelivery(
        resource_kind=DeliveryResourceKind.ASSET,
        attribution=attribution,
        snapshot_identity="b" * 64,
        content=b"\x89PNG\r\n\x1a\n",
        media_type="image/png",
        content_hash="c" * 64,
        total_byte_size=8,
        range_start=0,
        completeness=DeliveryCompleteness.COMPLETE,
    )
    return notebook_id, document_id, version_id, occurrence_id, response, binary


@pytest.mark.anyio
async def test_four_additive_tools_preserve_six_frozen_tools() -> None:
    names = [item.name for item in get_mcp_tools()]
    assert names[:6] == [
        "query_notebook",
        "search_all_notebooks",
        "list_notebooks",
        "get_notebook_summary",
        "get_source_insights",
        "get_timeline",
    ]
    assert names[6:] == [
        "get_document",
        "get_document_chunk",
        "get_asset",
        "get_image_analysis",
        "search_evidence",
        "query_structured",
        "run_final_qa_v2",
        "get_capabilities",
    ]


@pytest.mark.anyio
async def test_mcp_document_chunk_inventory_and_analysis_delivery() -> None:
    notebook_id, document_id, version_id, occurrence_id, response, _ = _values()
    service = MagicMock()
    service.expand_document = AsyncMock(return_value=response)
    service.get_document_chunk = AsyncMock(return_value=response)
    service.list_assets = AsyncMock(return_value=response)
    service.get_image_analysis = AsyncMock(return_value=response)
    common = {
        "notebook_id": str(notebook_id),
        "document_id": str(document_id),
        "version_id": str(version_id),
    }
    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service):
        document = await execute_mcp_tool(_engine(), "get_document", common)
        assert isinstance(document[0], types.TextContent)
        assert json.loads(document[0].text)["completeness"] == "complete"
        chunk = await execute_mcp_tool(
            _engine(), "get_document_chunk", {**common, "chunk_id": "d" * 64}
        )
        assert isinstance(chunk[0], types.TextContent)
        inventory = await execute_mcp_tool(_engine(), "get_asset", common)
        assert isinstance(inventory[0], types.TextContent)
        analysis = await execute_mcp_tool(
            _engine(),
            "get_image_analysis",
            {
                "notebook_id": str(notebook_id),
                "occurrence_id": str(occurrence_id),
                "ocr_derivation_id": str(uuid4()),
            },
        )
        assert isinstance(analysis[0], types.TextContent)


@pytest.mark.anyio
async def test_mcp_document_selector_uses_exact_v2_service() -> None:
    notebook_id, document_id, version_id, _, response, _ = _values()
    service = MagicMock()
    service.expand_document_v2 = AsyncMock(return_value=response)
    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service):
        content = await execute_mcp_tool(
            _engine(),
            "get_document",
            {
                "notebook_id": str(notebook_id),
                "document_id": str(document_id),
                "version_id": str(version_id),
                "selector": {"kind": "from_end", "unit": "page"},
            },
        )
    assert isinstance(content[0], types.TextContent)
    request = service.expand_document_v2.await_args.args[0]
    assert request.selector.kind.value == "from_end"
    payload = json.loads(content[0].text)
    assert payload["coverage"]["selection_semantics"] == "exact_physical_order"


@pytest.mark.anyio
async def test_mcp_native_binary_and_image_delivery() -> None:
    notebook_id, document_id, version_id, occurrence_id, _, binary = _values()
    service = MagicMock()
    service.get_original_document = AsyncMock(return_value=binary)
    service.get_asset = AsyncMock(return_value=binary)
    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service):
        document = await execute_mcp_tool(
            _engine(),
            "get_document",
            {
                "notebook_id": str(notebook_id),
                "document_id": str(document_id),
                "version_id": str(version_id),
                "mode": "original",
            },
        )
        assert isinstance(document[0], types.EmbeddedResource)
        assert document[0].resource.mimeType == "image/png"
        image = await execute_mcp_tool(
            _engine(),
            "get_asset",
            {
                "notebook_id": str(notebook_id),
                "occurrence_id": str(occurrence_id),
                "max_bytes": 1024,
            },
        )
        assert isinstance(image[0], types.ImageContent)
        assert image[0].mimeType == "image/png"
        assert image[0].meta["occurrenceId"] == str(occurrence_id)
        assert image[0].meta["completeness"] == "complete"
        assert service.get_asset.await_args.kwargs["max_bytes"] == 1024


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("media_type", "prefix"),
    (("image/png", b"\x89PNG"), ("image/jpeg", b"\xff\xd8\xff\xe0")),
)
async def test_mcp_partial_image_is_a_bounded_range_resource(
    media_type: str, prefix: bytes
) -> None:
    notebook_id, _, _, occurrence_id, _, binary = _values()
    partial = replace(
        binary,
        content=prefix,
        media_type=media_type,
        completeness=DeliveryCompleteness.TRUNCATED,
        next_cursor="opaque-next",
    )
    service = MagicMock()
    service.get_asset = AsyncMock(return_value=partial)
    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service):
        content = await execute_mcp_tool(
            _engine(),
            "get_asset",
            {"notebook_id": str(notebook_id), "occurrence_id": str(occurrence_id)},
        )
    assert isinstance(content[0], types.EmbeddedResource)
    assert content[0].resource.mimeType == "application/octet-stream"
    assert content[0].resource.meta["originalMediaType"] == media_type
    assert content[0].resource.meta["completeness"] == "truncated"
    assert content[0].resource.meta["nextCursor"] == "opaque-next"


@pytest.mark.anyio
async def test_mcp_malformed_or_unsupported_image_mime_is_not_image_content() -> None:
    notebook_id, _, _, occurrence_id, _, binary = _values()
    service = MagicMock()
    service.get_asset = AsyncMock(
        return_value=replace(binary, content=b"not-a-png", total_byte_size=9)
    )
    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service):
        content = await execute_mcp_tool(
            _engine(),
            "get_asset",
            {"notebook_id": str(notebook_id), "occurrence_id": str(occurrence_id)},
        )
    assert isinstance(content[0], types.EmbeddedResource)
    assert content[0].resource.mimeType == "application/octet-stream"
    assert content[0].resource.meta["originalMediaType"] == "image/png"


@pytest.mark.anyio
async def test_mcp_latest_ready_analysis_does_not_require_hidden_ids() -> None:
    notebook_id, _, _, occurrence_id, response, _ = _values()
    service = MagicMock()
    service.get_image_analysis_v2 = AsyncMock(return_value=response)
    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service):
        content = await execute_mcp_tool(
            _engine(),
            "get_image_analysis",
            {
                "notebook_id": str(notebook_id),
                "occurrence_id": str(occurrence_id),
                "selection": "latest_ready",
                "modalities": ["ocr", "vision"],
            },
        )
    assert isinstance(content[0], types.TextContent)
    selector = service.get_image_analysis_v2.await_args.kwargs["selector"]
    assert selector.selection.value == "latest_ready"
    assert selector.derivation_ids == ()


@pytest.mark.anyio
async def test_mcp_delivery_validation_fails_closed() -> None:
    with pytest.raises(ContractValidationError):
        await execute_mcp_tool(
            _engine(),
            "get_document",
            {
                "notebook_id": str(uuid4()),
                "document_id": str(uuid4()),
                "version_id": str(uuid4()),
                "mode": "filesystem_path",
            },
        )
    with pytest.raises(ContractValidationError):
        await execute_mcp_tool(
            _engine(),
            "get_document_chunk",
            {
                "notebook_id": str(uuid4()),
                "document_id": str(uuid4()),
                "version_id": str(uuid4()),
                "chunk_id": "../secret",
            },
        )


@pytest.mark.anyio
async def test_mcp_delivery_uses_server_configured_bounds() -> None:
    notebook_id, document_id, version_id, _, response, _ = _values()
    service = MagicMock()
    service.expand_document = AsyncMock(return_value=response)
    config = ServerConfig(max_delivery_document_bytes=1234)
    engine = _engine()
    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service) as service_factory:
        await execute_mcp_tool(
            engine,
            "get_document",
            {
                "notebook_id": str(notebook_id),
                "document_id": str(document_id),
                "version_id": str(version_id),
            },
            config,
        )
    service_factory.assert_called_once_with(engine, config)


@pytest.mark.anyio
async def test_mcp_delivery_sanitizes_authorization_failures() -> None:
    _, _, _, occurrence_id, _, _ = _values()
    service = MagicMock()
    service.get_asset = AsyncMock(side_effect=DeliveryAuthorizationError("C:\\private\\asset.bin"))
    with (
        patch("mnemo_server.mcp.tools._delivery_service", return_value=service),
        pytest.raises(DeliveryAuthorizationError, match="Resource access is forbidden") as err,
    ):
        await execute_mcp_tool(
            _engine(),
            "get_asset",
            {"notebook_id": str(uuid4()), "occurrence_id": str(occurrence_id)},
        )
    assert "private" not in str(err.value)


@pytest.mark.anyio
async def test_mcp_get_document_auto_resolves_notebook_id() -> None:
    notebook_id, document_id, version_id, _, response, _ = _values()
    service = MagicMock()
    service.expand_document = AsyncMock(return_value=response)

    engine = _engine()
    from datetime import UTC, datetime

    from mnemo.models import Source

    now = datetime.now(UTC)
    source_obj = Source(
        source_id=uuid4(),
        notebook_id=notebook_id,
        document_id=document_id,
        created_at=now,
    )
    engine.storage = MagicMock()
    engine.storage.list_sources_for_document = AsyncMock(return_value=(source_obj,))

    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service):
        document = await execute_mcp_tool(
            engine,
            "get_document",
            {
                "document_id": str(document_id),
                "version_id": str(version_id),
            },
        )
        assert isinstance(document[0], types.TextContent)
        assert json.loads(document[0].text)["completeness"] == "complete"
        # Verify expand_document was called with resolved notebook_id
        service.expand_document.assert_called_once()
        req = service.expand_document.call_args[0][0]
        assert req.notebook_id == notebook_id
        assert req.document_id == document_id


@pytest.mark.anyio
async def test_mcp_get_document_auto_resolve_fails_when_ambiguous() -> None:
    notebook_id_1 = uuid4()
    notebook_id_2 = uuid4()
    document_id = uuid4()
    version_id = uuid4()

    engine = _engine()
    from datetime import UTC, datetime

    from mnemo.models import Source

    now = datetime.now(UTC)
    source_1 = Source(
        source_id=uuid4(), notebook_id=notebook_id_1, document_id=document_id, created_at=now
    )
    source_2 = Source(
        source_id=uuid4(), notebook_id=notebook_id_2, document_id=document_id, created_at=now
    )
    engine.storage = MagicMock()
    engine.storage.list_sources_for_document = AsyncMock(return_value=(source_1, source_2))

    with pytest.raises(ContractValidationError, match="multiple notebooks"):
        await execute_mcp_tool(
            engine,
            "get_document",
            {
                "document_id": str(document_id),
                "version_id": str(version_id),
            },
        )


@pytest.mark.anyio
async def test_mcp_get_document_auto_resolve_fails_when_not_found() -> None:
    from mnemo.interfaces import NotFoundError

    document_id = uuid4()
    version_id = uuid4()

    engine = _engine()
    engine.storage = MagicMock()
    engine.storage.list_sources_for_document = AsyncMock(return_value=())

    with pytest.raises(NotFoundError, match="authorized resource was not found"):
        await execute_mcp_tool(
            engine,
            "get_document",
            {
                "document_id": str(document_id),
                "version_id": str(version_id),
            },
        )


@pytest.mark.anyio
async def test_mcp_get_document_chunk_auto_resolves_notebook_id() -> None:
    notebook_id, document_id, version_id, _, response, _ = _values()
    service = MagicMock()
    service.get_document_chunk = AsyncMock(return_value=response)

    engine = _engine()
    from datetime import UTC, datetime

    from mnemo.models import Source

    now = datetime.now(UTC)
    source_obj = Source(
        source_id=uuid4(),
        notebook_id=notebook_id,
        document_id=document_id,
        created_at=now,
    )
    engine.storage = MagicMock()
    engine.storage.list_sources_for_document = AsyncMock(return_value=(source_obj,))

    with patch("mnemo_server.mcp.tools._delivery_service", return_value=service):
        chunk = await execute_mcp_tool(
            engine,
            "get_document_chunk",
            {
                "document_id": str(document_id),
                "version_id": str(version_id),
                "chunk_id": "d" * 64,
            },
        )
        assert isinstance(chunk[0], types.TextContent)
        service.get_document_chunk.assert_called_once_with(
            notebook_id=notebook_id,
            document_id=document_id,
            version_id=version_id,
            chunk_id="d" * 64,
        )
