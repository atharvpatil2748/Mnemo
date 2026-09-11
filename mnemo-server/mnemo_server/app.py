"""FastAPI application factory and ASGI lifespan for mnemo-server."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mnemo import __version__
from mnemo.config import MnemoConfig
from mnemo.engine import EngineState, FinalQAComponents, KnowledgeEngine
from mnemo.tokenizers import O200KBaseTokenCounter

from .auth import AuthMiddleware
from .config import ServerConfig
from .errors import register_error_handlers
from .routers import (
    capabilities_v2_router,
    delivery_router,
    final_qa_router,
    final_qa_v2_router,
    insights_router,
    notebooks_router,
    notes_router,
    query_router,
    retrieval_v2_router,
    search_router,
    sessions_router,
    sources_router,
    streaming_router,
    structured_v2_router,
    system_router,
)
from .runtime_config import resolve_mnemo_runtime_config
from .services import JobService
from .services.retrieval_v2 import build_retrieval_cursor_codec
from .tokenizer_provisioning import provision_tokenizer

_LOGGER = logging.getLogger(__name__)


def create_app(
    server_config: ServerConfig | None = None,
    mnemo_config: MnemoConfig | None = None,
    *,
    engine: KnowledgeEngine | None = None,
    final_qa_components: FinalQAComponents | None = None,
    reranker_activation_evidence: object | None = None,
    provision_tokenizer_on_startup: bool = True,
) -> FastAPI:
    """Create and configure the FastAPI application for mnemo-server."""
    resolved_server_config = server_config or ServerConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage KnowledgeEngine lifecycle across application startup and shutdown."""
        active_engine = engine
        resolved_components = final_qa_components
        operational_store = None

        if active_engine is None:
            resolved_mnemo_config = resolve_mnemo_runtime_config(mnemo_config)

            if resolved_server_config.full_multilingual_v2_enabled:
                from .services.final_qa_operational import (
                    open_production_final_qa_operational_store,
                )

                operational_store = await open_production_final_qa_operational_store(
                    workspace_root=Path.cwd(),
                    mnemo_config=resolved_mnemo_config,
                    server_config=resolved_server_config,
                )

            if resolved_components is None and provision_tokenizer_on_startup:
                try:
                    # Tokenizer provisioning involves file/network I/O; run outside the event loop
                    asset_path = await asyncio.to_thread(provision_tokenizer)
                    token_counter = O200KBaseTokenCounter(asset_path)
                    resolved_components = FinalQAComponents(
                        token_counter=token_counter,
                        clock=lambda: datetime.now(UTC),
                        operational_store_v2=operational_store,
                    )
                except Exception as err:
                    _LOGGER.warning(
                        "Tokenizer provisioning skipped or failed during startup: %s", err
                    )
                    resolved_components = None

            active_engine = KnowledgeEngine(
                resolved_mnemo_config,
                final_qa_components=resolved_components,
                advanced_retrieval_cursor_codec=build_retrieval_cursor_codec(
                    resolved_server_config
                ),
            )

        # Initialize the engine atomically
        await active_engine.initialize()

        if active_engine.state is not EngineState.READY:
            state_val = active_engine.state.value
            raise RuntimeError(
                f"KnowledgeEngine failed to reach READY state (current: {state_val})"
            )

        installed_v2 = None
        if resolved_server_config.full_multilingual_v2_enabled:
            from .services.full_multilingual_v2_startup import (
                IDENTITY_MANIFEST,
                install_production_full_multilingual_v2,
            )
            from .services.production_store_readiness import (
                ProductionV2ReadinessEvidenceBuilderV1,
            )

            root = Path.cwd().resolve()
            model_cache = resolved_server_config.full_multilingual_v2_model_cache
            if model_cache is None:
                raise RuntimeError("Full Multilingual V2 model cache is missing")
            readiness_evidence, readiness = await ProductionV2ReadinessEvidenceBuilderV1(
                workspace_root=root,
                mnemo_config=active_engine.config,
                server_config=resolved_server_config,
                identity_manifest=root / IDENTITY_MANIFEST,
            ).build()
            if (
                resolved_server_config.reranker_activation_state_path is not None
                and reranker_activation_evidence is not None
            ):
                raise RuntimeError("COMPETING_RERANKER_ACTIVATION_AUTHORITIES")
            installed_v2 = await install_production_full_multilingual_v2(
                engine=active_engine,
                workspace_root=root,
                model_cache=model_cache,
                readiness=readiness,
            )
            from .services.durable_reranker_activation import (
                restore_production_reranker_activation,
            )

            durable_activation = await restore_production_reranker_activation(
                installed=installed_v2,
                config=resolved_server_config,
                workspace_root=root,
                production_store_path=active_engine.config.storage.sqlite.path,
            )
            if reranker_activation_evidence is not None:
                from .services.v2_reranker_lifecycle import RerankerActivationEvidenceV1

                if not isinstance(reranker_activation_evidence, RerankerActivationEvidenceV1):
                    raise TypeError("reranker activation evidence has the wrong governed type")
                await installed_v2.reranker_activation.activate(reranker_activation_evidence)
            app.state.full_multilingual_v2_runtime = installed_v2
            app.state.full_multilingual_v2_readiness = readiness_evidence
            app.state.full_multilingual_v2_exposure = installed_v2.exposure_snapshot
            app.state.reranker_activation_authority = durable_activation

        # Publish the ready engine and server configuration to app.state
        app.state.engine = active_engine
        app.state.server_config = resolved_server_config
        app.state.job_service = JobService()
        if resolved_components is not None:
            app.state.token_counter = resolved_components.token_counter

        yield

        # Clean shutdown of the engine
        if hasattr(app.state, "engine") and app.state.engine is not None:
            try:
                if installed_v2 is not None:
                    await installed_v2.close()
                await app.state.engine.shutdown()
                if operational_store is not None:
                    await operational_store.close()
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

    # Attach Authentication middleware
    app.add_middleware(
        AuthMiddleware,
        config=resolved_server_config,
    )

    # Register ADR-0049 standardized error handlers
    register_error_handlers(app)

    # Register API routers
    app.include_router(system_router)
    app.include_router(streaming_router)
    app.include_router(notebooks_router, prefix="/v1")
    app.include_router(sources_router, prefix="/v1")
    app.include_router(sessions_router, prefix="/v1")
    app.include_router(notes_router, prefix="/v1")
    app.include_router(insights_router, prefix="/v1")
    app.include_router(final_qa_router, prefix="/v1")
    app.include_router(final_qa_v2_router, prefix="/v2")
    app.include_router(capabilities_v2_router, prefix="/v2")
    app.include_router(query_router, prefix="/v1")
    app.include_router(search_router, prefix="/v1")
    app.include_router(delivery_router, prefix="/v2")
    app.include_router(retrieval_v2_router, prefix="/v2")
    app.include_router(structured_v2_router, prefix="/v2")

    return app
