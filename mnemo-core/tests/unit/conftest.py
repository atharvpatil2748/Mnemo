"""Shared fixtures for Module 1.1 domain model tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest


@pytest.fixture
def document_id() -> UUID:
    """Return a deterministic document UUID."""
    return UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture
def version_id() -> UUID:
    """Return a deterministic version UUID."""
    return UUID("00000000-0000-4000-8000-000000000002")


@pytest.fixture
def timestamp() -> datetime:
    """Return a deterministic UTC timestamp."""
    return datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


@pytest.fixture
def content_hash() -> str:
    """Return a valid deterministic SHA-256 digest."""
    return "a" * 64
