"""FastAPI application factory and ASGI lifespan for mnemo-server."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mnemo import __version__
from mnemo.config import MnemoConfig
from mnemo.engine import EngineState, FinalQAComponents, KnowledgeEngine
from mnemo.tokenizers import O200KBaseTokenCounter

from .config import ServerConfig
from .errors import register_error_handlers
from .routers import (
    insights_router,
    notebooks_router,
    notes_router,
    query_router,
    search_router,
    sessions_router,
    sources_router,
)
from .tokenizer_provisioning import provision_tokenizer

_LOGGER = logging.getLogger(__name__)


def create_app(
    server_config: ServerConfig | None = None,
    mnemo_config: MnemoConfig | None = None,
    *,
    engine: KnowledgeEngine | None = None,
    final_qa_components: FinalQAComponents | None = None,
    provision_tokenizer_on_startup: bool = True,
) -> FastAPI:
    """Create and configure the FastAPI application for mnemo-server."""
    resolved_server_config = server_config or ServerConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage KnowledgeEngine lifecycle across application startup and shutdown."""
        active_engine = engine
        resolved_components = final_qa_components

        if active_engine is None:
            resolved_mnemo_config = mnemo_config or MnemoConfig.from_env()

            if resolved_components is None and provision_tokenizer_on_startup:
                try:
                    # Tokenizer provisioning involves file/network I/O; run outside the event loop
                    asset_path = await asyncio.to_thread(provision_tokenizer)
                    token_counter = O200KBaseTokenCounter(asset_path)
                    resolved_components = FinalQAComponents(
                        token_counter=token_counter,
                        clock=lambda: datetime.now(UTC),
                    )
                except Exception as err:
                    _LOGGER.warning(
                        "Tokenizer provisioning skipped or failed during startup: %s", err
                    )
                    resolved_components = None

            active_engine = KnowledgeEngine(
                resolved_mnemo_config,
                final_qa_components=resolved_components,
            )

        # Initialize the engine atomically
        await active_engine.initialize()

        if active_engine.state is not EngineState.READY:
            state_val = active_engine.state.value
            raise RuntimeError(
                f"KnowledgeEngine failed to reach READY state (current: {state_val})"
            )

        # Publish the ready engine and server configuration to app.state
        app.state.engine = active_engine
        app.state.server_config = resolved_server_config
        if resolved_components is not None:
            app.state.token_counter = resolved_components.token_counter

        yield

        # Clean shutdown of the engine
        if hasattr(app.state, "engine") and app.state.engine is not None:
            try:
                await app.state.engine.shutdown()
            except Exception as err:
                _LOGGER.error("Error shutting down KnowledgeEngine: %s", err)
            finally:
                app.state.engine = None

    app = FastAPI(
        title="Mnemo Server",
        version=__version__,
        description="Transport adapter API for the Mnemo Local Knowledge Engine.",
        lifespan=lifespan,
    )

    # Attach CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_server_config.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register ADR-0049 standardized error handlers
    register_error_handlers(app)

    # Register API routers
    app.include_router(notebooks_router, prefix="/v1")
    app.include_router(sources_router, prefix="/v1")
    app.include_router(sessions_router, prefix="/v1")
    app.include_router(notes_router, prefix="/v1")
    app.include_router(insights_router, prefix="/v1")
    app.include_router(query_router, prefix="/v1")
    app.include_router(search_router, prefix="/v1")

    @app.get("/health", tags=["system"])
    @app.get("/v1/health", tags=["system"])
    async def health_check() -> dict[str, Any]:
        """Basic health check endpoint returning server status and engine readiness."""
        eng = getattr(app.state, "engine", None)
        is_ready = eng is not None and eng.state is EngineState.READY
        return {
            "status": "ok" if is_ready else "degraded",
            "version": __version__,
            "engine_state": eng.state.value if eng is not None else "unavailable",
        }

    return app
