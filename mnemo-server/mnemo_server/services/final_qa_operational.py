"""Production ownership for mutable Final-QA execution persistence."""

from __future__ import annotations

from pathlib import Path

from mnemo.config import MnemoConfig
from mnemo.storage import SQLiteFinalQAOperationalStore

from ..config import ServerConfig


async def open_production_final_qa_operational_store(
    *,
    workspace_root: Path,
    mnemo_config: MnemoConfig,
    server_config: ServerConfig,
) -> SQLiteFinalQAOperationalStore:
    """Open the configured operational store after proving corpus-path separation."""
    configured = server_config.final_qa_operational_store_path
    if configured is None:
        raise RuntimeError("FINAL_QA_OPERATIONAL_STORE_CONFIGURATION_MISSING")
    root = workspace_root.resolve()
    path = configured if configured.is_absolute() else root / configured
    corpus_path = mnemo_config.storage.sqlite.path.resolve()
    if path.resolve() == corpus_path:
        raise RuntimeError("FINAL_QA_OPERATIONAL_STORE_MUST_DIFFER_FROM_CORPUS_STORE")
    store = SQLiteFinalQAOperationalStore(path)
    await store.open()
    return store
