"""Tests for the Phase 0 core package scaffold."""

import mnemo


def test_core_package_version() -> None:
    """The core package exposes its package version."""
    assert mnemo.__version__ == "0.23.0"
