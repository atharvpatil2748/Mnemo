"""Explicit installation-layer provisioning for the canonical tokenizer asset."""

import json
import os
import shutil
import sys
import tempfile
import urllib.request
from hashlib import sha256
from pathlib import Path

from mnemo.tokenizers import (
    O200K_BASE_ASSET_NAME,
    O200K_BASE_ASSET_SHA256,
    O200K_BASE_ASSET_SIZE,
    O200K_BASE_TOKENIZER_ID,
    O200K_BASE_UPSTREAM_URL,
)


def tokenizer_data_root() -> Path:
    """Return the deterministic per-user Mnemo tokenizer data root."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Mnemo" / "tokenizers"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Mnemo" / "tokenizers"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mnemo" / "tokenizers"


def provisioned_tokenizer_path(data_root: Path | None = None) -> Path:
    """Return the content-addressed canonical asset destination."""
    root = tokenizer_data_root() if data_root is None else Path(data_root)
    return root / "o200k_base" / O200K_BASE_ASSET_SHA256 / O200K_BASE_ASSET_NAME


def provision_tokenizer(*, source: Path | None = None, data_root: Path | None = None) -> Path:
    """Explicitly download or import, verify, and atomically install the asset."""
    destination = provisioned_tokenizer_path(data_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source is None and _asset_is_valid(destination):
        _write_manifest(destination)
        return destination
    temporary_path: Path | None = None
    try:
        if source is None:
            descriptor, raw_name = tempfile.mkstemp(
                prefix="mnemo-tokenizer-", suffix=".tmp", dir=destination.parent
            )
            os.close(descriptor)
            temporary_path = Path(raw_name)
            urllib.request.urlretrieve(O200K_BASE_UPSTREAM_URL, temporary_path)
            candidate = temporary_path
        else:
            candidate = Path(source)
        payload = candidate.read_bytes()
        if len(payload) != O200K_BASE_ASSET_SIZE:
            raise ValueError("tokenizer asset has an unexpected byte size")
        if sha256(payload).hexdigest() != O200K_BASE_ASSET_SHA256:
            raise ValueError("tokenizer asset SHA-256 does not match the frozen contract")
        install_path = temporary_path
        if install_path is None:
            descriptor, raw_name = tempfile.mkstemp(
                prefix="mnemo-tokenizer-", suffix=".tmp", dir=destination.parent
            )
            os.close(descriptor)
            install_path = Path(raw_name)
            shutil.copyfile(candidate, install_path)
        os.replace(install_path, destination)
        temporary_path = None
        _write_manifest(destination)
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _asset_is_valid(path: Path) -> bool:
    try:
        payload = path.read_bytes()
    except OSError:
        return False
    return len(payload) == O200K_BASE_ASSET_SIZE and (
        sha256(payload).hexdigest() == O200K_BASE_ASSET_SHA256
    )


def _write_manifest(destination: Path) -> None:
    manifest = {
        "adapter_version": "v1",
        "asset_sha256": O200K_BASE_ASSET_SHA256,
        "engine_version": "tiktoken-0.13.0",
        "tokenizer_id": O200K_BASE_TOKENIZER_ID,
    }
    destination.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
