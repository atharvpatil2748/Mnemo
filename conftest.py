"""Root test configuration and test isolation hooks."""

from __future__ import annotations

import os

import pytest

IS_CI = (
    os.environ.get("CI") == "true"
    or os.environ.get("GITHUB_ACTIONS") == "true"
    or os.environ.get("MNEMO_CI") == "1"
)

LOCAL_DB_SKIP_REASON = (
    "Local governed-database validation is intentionally excluded from GitHub CI; "
    "protected local database is unavailable by design."
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Explicitly skip local_database tests when executing in CI."""
    if IS_CI:
        skip_local_db = pytest.mark.skip(reason=LOCAL_DB_SKIP_REASON)
        for item in items:
            if "local_database" in item.keywords:
                item.add_marker(skip_local_db)
