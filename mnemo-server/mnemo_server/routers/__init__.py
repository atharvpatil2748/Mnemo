"""API routers for mnemo-server endpoints."""

from __future__ import annotations

from .final_qa import router as final_qa_router
from .insights import router as insights_router
from .notebooks import router as notebooks_router
from .notes import router as notes_router
from .query import router as query_router
from .search import router as search_router
from .sessions import router as sessions_router
from .sources import router as sources_router
from .streaming import router as streaming_router
from .system import system_router

__all__ = [
    "final_qa_router",
    "insights_router",
    "notebooks_router",
    "notes_router",
    "query_router",
    "search_router",
    "sessions_router",
    "sources_router",
    "streaming_router",
    "system_router",
]
