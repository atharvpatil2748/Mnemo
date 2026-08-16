"""Unit tests for tokenizer provisioning off-thread safety during lifespan."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.config import MnemoConfig
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo_server.app import create_app


@pytest.mark.anyio
async def test_tokenizer_provisioning_runs_off_event_loop(tmp_path: Path) -> None:
    """Verify that provision_tokenizer is called in a separate thread via asyncio.to_thread."""
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.UNINITIALIZED
    mock_engine.version = "0.22.0"

    storage_mock = MagicMock()
    storage_mock.health_check = AsyncMock(return_value=())
    mock_engine.storage = storage_mock

    emb_mock = MagicMock()
    emb_mock.health_check = AsyncMock(
        return_value=MagicMock(
            component="emb", healthy=True, checked_at=datetime.now(UTC), detail=None
        )
    )
    mock_engine.embedding_provider = emb_mock

    llm_mock = MagicMock()
    llm_mock.health_check = AsyncMock(
        return_value=MagicMock(
            component="llm", healthy=True, checked_at=datetime.now(UTC), detail=None
        )
    )
    mock_engine.llm = MagicMock(return_value=llm_mock)

    async def mock_initialize() -> None:
        mock_engine.state = EngineState.READY

    async def mock_shutdown() -> None:
        mock_engine.state = EngineState.STOPPED

    mock_engine.initialize = AsyncMock(side_effect=mock_initialize)
    mock_engine.shutdown = AsyncMock(side_effect=mock_shutdown)

    to_thread_calls: list[Any] = []

    async def mock_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        to_thread_calls.append(func)
        return tmp_path / "dummy_tokenizer.tiktoken"

    with (
        patch("mnemo_server.app.asyncio.to_thread", side_effect=mock_to_thread),
        patch("mnemo_server.app.O200KBaseTokenCounter") as mock_counter_cls,
        patch("mnemo_server.app.KnowledgeEngine", return_value=mock_engine),
    ):
        mock_counter_cls.return_value = MagicMock()
        mock_config = MagicMock(spec=MnemoConfig)
        app = create_app(
            mnemo_config=mock_config,
            provision_tokenizer_on_startup=True,
        )

        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            resp = await client.get("/health")
            assert resp.status_code == 200

        # Assert asyncio.to_thread was invoked with provision_tokenizer
        assert len(to_thread_calls) == 1
        assert to_thread_calls[0].__name__ == "provision_tokenizer"
