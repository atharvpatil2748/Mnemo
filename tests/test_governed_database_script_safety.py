"""Regression tests for writable operator-script database guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.governed_database_safety import (
    CURRENT_GOVERNED_DATABASES,
    reject_current_governed_database_write,
)


@pytest.mark.parametrize("database", CURRENT_GOVERNED_DATABASES)
def test_current_governed_database_is_rejected_as_a_script_write_target(database: Path) -> None:
    if not database.exists():
        pytest.skip(f"governed database is unavailable: {database}")

    with pytest.raises(RuntimeError, match="CURRENT_GOVERNED_DATABASE_IS_IMMUTABLE"):
        reject_current_governed_database_write(database)


def test_isolated_operator_database_is_accepted(tmp_path: Path) -> None:
    isolated = tmp_path / "isolated.db"
    isolated.write_bytes(b"synthetic")

    assert reject_current_governed_database_write(isolated) == isolated.resolve(strict=True)
