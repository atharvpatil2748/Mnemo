"""API routers for mnemo-server endpoints."""

from __future__ import annotations

from .notebooks import router as notebooks_router
from .query import router as query_router
from .search import router as search_router
from .sources import router as sources_router

__all__ = ["notebooks_router", "query_router", "search_router", "sources_router"]
