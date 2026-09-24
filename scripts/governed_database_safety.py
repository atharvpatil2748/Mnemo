"""Fail-closed guards for scripts with writable SQLite dependencies."""

from __future__ import annotations

import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CURRENT_GOVERNED_DATABASES = (
    REPOSITORY_ROOT / "scratch/phase8_5_full_multilingual_v2/build-20260831-01/mnemo.db",
    REPOSITORY_ROOT / "scratch/phase8_5_wp16/eval-20260828-01/mnemo.db",
)


def reject_current_governed_database_write(database: Path) -> Path:
    """Return a canonical path unless it identifies a current governed database."""
    resolved = database.resolve(strict=True)
    key = os.path.normcase(os.path.normpath(os.fspath(resolved)))
    protected = {
        os.path.normcase(os.path.normpath(os.fspath(path.resolve(strict=True))))
        for path in CURRENT_GOVERNED_DATABASES
        if path.exists()
    }
    if key in protected:
        raise RuntimeError(
            "CURRENT_GOVERNED_DATABASE_IS_IMMUTABLE: use an isolated operator-owned copy"
        )
    return resolved
