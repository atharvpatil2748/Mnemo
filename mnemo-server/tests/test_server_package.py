"""Tests for the Phase 0 server package scaffold."""

import mnemo_server


def test_server_package_version() -> None:
    """The server package exposes its scaffold version."""
    assert mnemo_server.__version__ == "0.7.0"
