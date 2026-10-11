"""Explicit pre-index production selection; never infer a historical index."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SELECTION_PATH = Path("config/production/runtime-selection.json")
SELECTION_SCHEMA = "mnemo.production-runtime-selection/1"


@dataclass(frozen=True, slots=True)
class ProductionRuntimeSelectionV1:
    deployment_key: str
    state: Literal["UNINDEXED"]


def resolve_production_runtime_selection(root: Path) -> ProductionRuntimeSelectionV1:
    """Fail closed if explicit deployment selection is missing or unsupported.

    The only admitted state before a new governed index is published is
    UNINDEXED. Historical certificates, aliases, and notebook IDs are never
    considered fallback candidates. A future indexed state needs a separate
    authenticated publication contract and explicit implementation.
    """
    base = root.resolve(strict=True)
    path = base / SELECTION_PATH
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("PRODUCTION_RUNTIME_SELECTION_UNAVAILABLE")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("PRODUCTION_RUNTIME_SELECTION_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "deployment_key", "state"}
        or payload.get("schema") != SELECTION_SCHEMA
        or payload.get("state") != "UNINDEXED"
        or not isinstance(payload.get("deployment_key"), str)
        or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", payload["deployment_key"]) is None
    ):
        raise RuntimeError("PRODUCTION_RUNTIME_SELECTION_INVALID")
    return ProductionRuntimeSelectionV1(payload["deployment_key"], "UNINDEXED")


def require_production_index(root: Path) -> None:
    """Block every production transport before it opens the retired index."""
    selection = resolve_production_runtime_selection(root)
    if selection.state == "UNINDEXED":
        raise RuntimeError("PRODUCTION_CORPUS_UNINDEXED")
