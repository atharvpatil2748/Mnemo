"""API routers for mnemo-server endpoints."""

from __future__ import annotations

from .notebooks import router as notebooks_router

__all__ = ["notebooks_router"]
