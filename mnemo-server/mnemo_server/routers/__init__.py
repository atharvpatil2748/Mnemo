"""API routers for mnemo-server endpoints."""

from __future__ import annotations

from .capabilities_v2 import router as capabilities_v2_router
from .delivery import router as delivery_router
from .final_qa import router as final_qa_router
from .final_qa_v2 import router as final_qa_v2_router
from .insights import router as insights_router
from .notebooks import router as notebooks_router
from .notes import router as notes_router
from .query import router as query_router
from .retrieval_v2 import router as retrieval_v2_router
from .search import router as search_router
from .sessions import router as sessions_router
from .sources import router as sources_router
from .streaming import router as streaming_router
from .structured_v2 import router as structured_v2_router
from .system import system_router

__all__ = [
    "capabilities_v2_router",
    "delivery_router",
    "final_qa_router",
    "final_qa_v2_router",
    "insights_router",
    "notebooks_router",
    "notes_router",
    "query_router",
    "retrieval_v2_router",
    "search_router",
    "sessions_router",
    "sources_router",
    "streaming_router",
    "structured_v2_router",
    "system_router",
]
