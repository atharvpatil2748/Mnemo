"""HTTP Phase 8.5.10 bounded delivery contract tests."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import DeliveryAuthorizationError, DeliveryLimitExceededError
from mnemo.models import (
    BinaryDelivery,
    DeliveryAttribution,
    DeliveryCapability,
    DeliveryCapabilityState,
    DeliveryCompleteness,
    DeliveryItem,
    DeliveryResourceKind,
    DeliveryResponse,
    DeliveryUsage,
)
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig


def _engine() -> MagicMock:
    engine = MagicMock(spec=KnowledgeEngine)
    engine.state = EngineState.READY
    engine.initialize = AsyncMock()
    engine.shutdown = AsyncMock()
    return engine


def _response(notebook_id, document_id, version_id):  # type: ignore[no-untyped-def]
    return DeliveryResponse(
        resource_kind=DeliveryResourceKind.DOCUMENT,
        snapshot_identity="a" * 64,
        completeness=DeliveryCompleteness.COMPLETE,
        items=(
            DeliveryItem(
                index=0,
                kind="TextBlock",
                attribution=DeliveryAttribution(
                    notebook_id=notebook_id,
                    source_id=uuid4(),
                    document_id=document_id,
                    version_id=version_id,
                ),
                payload={"text": "bounded"},
                byte_size=7,
            ),
        ),
        usage=DeliveryUsage(items=1, bytes=7),
    )


@pytest.mark.anyio
async def test_http_v2_document_binary_capability_and_openapi() -> None:
    engine = _engine()
    config = ServerConfig(
        auth_mode="api-key", api_key="secret-key", delivery_cursor_secret="c" * 32
    )
    app = create_app(
        server_config=config,
        engine=engine,
        provision_tokenizer_on_startup=False,
    )
    app.state.engine = engine
    app.state.server_config = config
    notebook_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    attribution = DeliveryAttribution(
        notebook_id=notebook_id,
        source_id=uuid4(),
        document_id=document_id,
        version_id=version_id,
        asset_id=uuid4(),
    )
    binary = BinaryDelivery(
        resource_kind=DeliveryResourceKind.DOCUMENT,
        attribution=attribution,
        snapshot_identity="b" * 64,
        content=b"PDF",
        media_type="application/pdf",
        content_hash="c" * 64,
        total_byte_size=3,
        range_start=0,
        completeness=DeliveryCompleteness.COMPLETE,
    )
    service = MagicMock()
    service.capabilities.return_value = (
        DeliveryCapability(name="binary_resources", state=DeliveryCapabilityState.SUPPORTED),
    )
    service.expand_document = AsyncMock(
        return_value=_response(notebook_id, document_id, version_id)
    )
    service.expand_document_v2 = AsyncMock(
        return_value=_response(notebook_id, document_id, version_id)
    )
    service.get_original_document = AsyncMock(return_value=binary)
    occurrence_id = uuid4()
    service.get_asset = AsyncMock(
        return_value=replace(
            binary,
            resource_kind=DeliveryResourceKind.ASSET,
            attribution=replace(attribution, occurrence_id=occurrence_id, modality="image"),
            content=b"PD",
            completeness=DeliveryCompleteness.TRUNCATED,
            next_cursor="opaque-next",
        )
    )
    headers = {"X-API-Key": "secret-key"}
    with patch("mnemo_server.routers.delivery.build_delivery_service", return_value=service):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            url = f"/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}"
            document = await client.get(url, headers=headers)
            assert document.status_code == 200
            assert document.json()["items"][0]["payload"]["text"] == "bounded"
            expanded = await client.post(
                f"{url}/expand",
                headers=headers,
                json={"selector": {"kind": "from_end", "unit": "page", "count": 1}},
            )
            assert expanded.status_code == 200
            core_request = service.expand_document_v2.await_args.args[0]
            assert core_request.selector.kind.value == "from_end"
            invalid = await client.post(
                f"{url}/expand",
                headers=headers,
                json={
                    "selector": {
                        "kind": "page_range",
                        "start": 1,
                        "end": 2,
                        "count": 1,
                    }
                },
            )
            assert invalid.status_code == 422
            original = await client.get(f"{url}/original", headers=headers)
            assert original.status_code == 200
            assert original.content == b"PDF"
            assert original.headers["x-content-type-options"] == "nosniff"
            assert original.headers["x-mnemo-content-sha256"] == "c" * 64
            assert original.headers["x-mnemo-notebook-id"] == str(notebook_id)
            assert original.headers["x-mnemo-document-id"] == str(document_id)
            partial_asset = await client.get(
                f"/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content",
                headers=headers,
                params={"max_bytes": 2},
            )
            assert partial_asset.status_code == 206
            assert partial_asset.headers["x-mnemo-completeness"] == "truncated"
            assert partial_asset.headers["x-mnemo-next-cursor"] == "opaque-next"
            assert partial_asset.headers["x-mnemo-occurrence-id"] == str(occurrence_id)
            assert service.get_asset.await_args.kwargs["max_bytes"] == 2
            assert (
                await client.get("/v2/notebooks/not-a-uuid/documents/x/versions/y", headers=headers)
            ).status_code == 422
    openapi = app.openapi()
    assert (
        url.replace(str(notebook_id), "{notebook_id}")
        .replace(str(document_id), "{document_id}")
        .replace(str(version_id), "{version_id}")
        in openapi["paths"]
    )


@pytest.mark.anyio
async def test_http_v2_assets_analysis_and_sanitized_forbidden() -> None:
    engine = _engine()
    app = create_app(engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = ServerConfig()
    notebook_id, document_id, version_id, occurrence_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    service = MagicMock()
    response = _response(notebook_id, document_id, version_id)
    service.list_assets = AsyncMock(return_value=response)
    service.get_image_analysis = AsyncMock(return_value=response)
    service.get_image_analysis_v2 = AsyncMock(return_value=response)
    service.get_final_qa_evidence = AsyncMock(return_value=response)
    service.get_asset = AsyncMock(side_effect=DeliveryAuthorizationError("C:\\private\\secret.png"))
    with patch("mnemo_server.routers.delivery.build_delivery_service", return_value=service):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            inventory = await client.get(
                f"/v2/notebooks/{notebook_id}/documents/{document_id}/versions/{version_id}/assets"
            )
            assert inventory.status_code == 200
            analysis = await client.get(
                f"/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis",
                params={"ocr_derivation_id": str(uuid4())},
            )
            assert analysis.status_code == 200
            latest = await client.get(
                f"/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis",
                params={"selection": "latest_ready", "modalities": ["ocr", "vision"]},
            )
            assert latest.status_code == 200
            selector = service.get_image_analysis_v2.await_args.kwargs["selector"]
            assert selector.selection.value == "latest_ready"
            invalid_selector = await client.get(
                f"/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/analysis",
                params={"selection": "explicit"},
            )
            assert invalid_selector.status_code == 422
            final_qa = await client.get(f"/v2/notebooks/{notebook_id}/final-qa/{uuid4()}/evidence")
            assert final_qa.status_code == 200
            forbidden = await client.get(
                f"/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content"
            )
            assert forbidden.status_code == 403
            assert forbidden.json()["error"]["message"] == "Resource access is forbidden"
            assert "private" not in forbidden.text

    service.get_asset = AsyncMock(side_effect=DeliveryLimitExceededError("private size detail"))
    with patch("mnemo_server.routers.delivery.build_delivery_service", return_value=service):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            exceeded = await client.get(
                f"/v2/notebooks/{notebook_id}/asset-occurrences/{occurrence_id}/content"
            )
            assert exceeded.status_code == 413
            assert exceeded.json()["error"]["code"] == "delivery.size_exceeded"
            assert "private size detail" not in exceeded.text


def test_delivery_configuration_is_environment_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MNEMO_SERVER_MAX_DELIVERY_DOCUMENT_BYTES", "101")
    monkeypatch.setenv("MNEMO_SERVER_MAX_DELIVERY_ASSET_BYTES", "202")
    monkeypatch.setenv("MNEMO_SERVER_MAX_DELIVERY_ASSETS", "3")
    monkeypatch.setenv("MNEMO_SERVER_MAX_DELIVERY_RESPONSE_BYTES", "404")
    monkeypatch.setenv("MNEMO_SERVER_DELIVERY_CURSOR_SECRET", "abcdefghijklmnop")
    config = ServerConfig.from_env()
    assert config.max_delivery_document_bytes == 101
    assert config.max_delivery_asset_bytes == 202
    assert config.max_delivery_assets == 3
    assert config.max_delivery_response_bytes == 404
    assert config.delivery_cursor_secret == "abcdefghijklmnop"
    monkeypatch.setenv("MNEMO_SERVER_MAX_DELIVERY_ASSETS", "invalid")
    with pytest.raises(ValueError, match="positive integer"):
        ServerConfig.from_env()
    monkeypatch.setenv("MNEMO_SERVER_MAX_DELIVERY_ASSETS", "0")
    with pytest.raises(ValueError, match="positive integer"):
        ServerConfig.from_env()


def test_wp04_cursor_configuration_rotation_and_production_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNEMO_SERVER_DELIVERY_CURSOR_SECRET", "n" * 32)
    monkeypatch.setenv("MNEMO_SERVER_DELIVERY_CURSOR_KEY_ID", "current-2026")
    monkeypatch.setenv("MNEMO_SERVER_DELIVERY_CURSOR_TTL_SECONDS", "60")
    monkeypatch.setenv(
        "MNEMO_SERVER_DELIVERY_CURSOR_ROTATION_KEYS",
        json.dumps({"previous-2026": "p" * 32}),
    )
    monkeypatch.setenv("MNEMO_SERVER_DELIVERY_CURSOR_LEGACY_V1_OVERLAP_SECONDS", "0")
    monkeypatch.setenv("MNEMO_SERVER_PRODUCTION_MODE", "true")
    config = ServerConfig.from_env()
    assert config.delivery_cursor_key_id == "current-2026"
    assert config.delivery_cursor_ttl_seconds == 60
    assert config.delivery_cursor_rotation_keys == (("previous-2026", "p" * 32),)
    assert config.delivery_cursor_legacy_v1_overlap_seconds == 0
    with pytest.raises(ValueError, match="cursor signing"):
        ServerConfig(production_mode=True)
    with pytest.raises(ValueError, match="cursor signing"):
        ServerConfig(auth_mode="api-key", api_key="configured")
    with pytest.raises(ValueError, match="unique"):
        ServerConfig(
            delivery_cursor_secret="n" * 32,
            delivery_cursor_key_id="same",
            delivery_cursor_rotation_keys=(("same", "p" * 32),),
        )


def test_transport_completeness_mapping_is_lossless() -> None:
    from mnemo_server.schemas.cursor import (
        TransportCompletenessV2,
        map_transport_coverage,
    )

    truncated = map_transport_coverage("complete", next_cursor="opaque")
    assert truncated.completeness is TransportCompletenessV2.TRUNCATED
    partial = map_transport_coverage(
        "complete", next_cursor=None, unavailable=("ocr",), omissions=("bounded",)
    )
    assert partial.completeness is TransportCompletenessV2.PARTIAL
    unknown = map_transport_coverage("new-domain-state", next_cursor=None)
    assert unknown.completeness is TransportCompletenessV2.UNKNOWN
