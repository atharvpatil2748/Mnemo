"""Focused governance tests for Final-QA operational persistence separation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from mnemo.config import MnemoConfig
from mnemo.interfaces import FinalQAExecutionStoreV2, StorageInterfaceV1
from mnemo.models.final_qa_execution import FinalQAExecutionState
from mnemo.models.multimodal import FinalQAExecutionV2
from mnemo.storage import SQLiteFinalQAOperationalStore
from mnemo_server.config import ServerConfig
from mnemo_server.services.final_qa_operational import (
    open_production_final_qa_operational_store,
)


@pytest.mark.anyio
async def test_operational_store_is_typed_and_has_no_corpus_interface(tmp_path: Path) -> None:
    store = SQLiteFinalQAOperationalStore(tmp_path / "final-qa.db")
    await store.open()
    try:
        assert isinstance(store, FinalQAExecutionStoreV2)
        assert not isinstance(store, StorageInterfaceV1)
    finally:
        await store.close()


@pytest.mark.anyio
async def test_operational_execution_does_not_touch_corpus_store(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.db"
    corpus.write_bytes(b"immutable-corpus-marker")
    before = corpus.read_bytes()
    store = SQLiteFinalQAOperationalStore(tmp_path / "operational" / "final-qa.db")
    await store.open()
    now = datetime.now(UTC)
    execution = FinalQAExecutionV2(
        execution_id=uuid4(),
        assistant_turn_id=uuid4(),
        request_fingerprint="f" * 64,
        actor_id=uuid4(),
        notebook_id=uuid4(),
        session_id=uuid4(),
        user_turn_id=uuid4(),
        provider="test",
        model="test",
        provider_profile="final_qa_v2:test",
        state=FinalQAExecutionState.RUNNING,
        retry_count=0,
        failure_classification=None,
        created_at=now,
        updated_at=now,
    )
    try:
        assert await store.create_final_qa_v2_execution(execution)
        assert await store.get_final_qa_v2_execution(execution.assistant_turn_id) == execution
        assert corpus.read_bytes() == before
    finally:
        await store.close()


@pytest.mark.anyio
async def test_production_helper_rejects_corpus_path(tmp_path: Path) -> None:
    baseline = MnemoConfig.from_file(Path("mnemo.toml"))
    core = baseline.model_copy(
        update={
            "storage": baseline.storage.model_copy(
                update={
                    "sqlite": baseline.storage.sqlite.model_copy(
                        update={"path": tmp_path / "same.db"}
                    )
                }
            )
        }
    )
    server = ServerConfig(
        production_mode=True,
        auth_mode="api-key",
        api_key="test",
        delivery_cursor_secret="x" * 32,
        full_multilingual_v2_enabled=True,
        full_multilingual_v2_model_cache=tmp_path / "models",
        final_qa_operational_store_path=tmp_path / "same.db",
        mcp_stdio_principal_subject="stdio",
    )
    with pytest.raises(RuntimeError, match="MUST_DIFFER"):
        await open_production_final_qa_operational_store(
            workspace_root=tmp_path,
            mnemo_config=core,
            server_config=server,
        )
