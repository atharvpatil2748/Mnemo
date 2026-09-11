"""Shared runtime configuration resolution for HTTP and MCP processes."""

from __future__ import annotations

from pathlib import Path

from mnemo.config import MnemoConfig

DEFAULT_MNEMO_CONFIG_PATH = Path("mnemo.toml")


def resolve_mnemo_runtime_config(
    explicit: MnemoConfig | None = None,
    *,
    config_path: Path = DEFAULT_MNEMO_CONFIG_PATH,
) -> MnemoConfig:
    """Resolve one core configuration policy for every production transport."""
    if explicit is not None:
        return explicit
    if config_path.is_file():
        return MnemoConfig.from_file(config_path)
    return MnemoConfig.from_env()
