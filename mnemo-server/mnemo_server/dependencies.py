"""FastAPI dependencies for mnemo-server."""

from __future__ import annotations

from fastapi import Request
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError


def get_engine(request: Request) -> KnowledgeEngine:
    """Obtain the initialized and ready KnowledgeEngine from the application state.

    Raises:
        DependencyUnavailableError: If the engine is missing or not in READY state.
    """
    engine: KnowledgeEngine | None = getattr(request.app.state, "engine", None)
    if engine is None or engine.state is not EngineState.READY:
        raise DependencyUnavailableError("KnowledgeEngine is not ready", retryable=True)
    return engine
