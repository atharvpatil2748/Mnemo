"""FastAPI application factory and ASGI lifespan for mnemo-server."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
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
    pre_certification_observation: bool = False,
) -> FastAPI:
    """Create and configure the FastAPI application for mnemo-server."""
    if pre_certification_observation and (engine is not None or final_qa_components is not None):
        raise RuntimeError("PRE_CERTIFICATION_INJECTED_RUNTIME_REJECTED")
    resolved_server_config = server_config or ServerConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage KnowledgeEngine lifecycle across application startup and shutdown."""
        active_engine = engine
        resolved_components = final_qa_components
        operational_store = None
        production_binding = None
        observation_authority = None
        if resolved_server_config.full_multilingual_v2_enabled:
            supplied_config = (
                mnemo_config if mnemo_config is not None else (engine.config if engine else None)
            )
            if pre_certification_observation:
                from .services.pre_certification_observation import (
                    resolve_pre_certification_observation,
                )

                certified_config, observation_identity, observation_authority = (
                    resolve_pre_certification_observation(
                        server_config=resolved_server_config, mnemo_config=supplied_config
                    )
                )
                app.state.pre_certification_identity = observation_identity
                app.state.pre_certification_authority = observation_authority
            else:
                from .services.production_runtime_binding import (
                    resolve_certified_production_binding,
                )

                certified_config, production_binding = resolve_certified_production_binding(
                    server_config=resolved_server_config,
                    mnemo_config=supplied_config,
                )
                app.state.certified_production_binding = production_binding
        elif pre_certification_observation:
            raise RuntimeError("PRE_CERTIFICATION_BINDING_REJECTED")
        else:
            certified_config = resolve_mnemo_runtime_config(
                mnemo_config if mnemo_config is not None else (engine.config if engine else None)
            )
            from .services.production_runtime_binding import reject_uncertified_corpus_startup

            reject_uncertified_corpus_startup(
                mnemo_config=certified_config, server_config=resolved_server_config
            )
        if production_binding is not None or observation_authority is not None:
            from .services.production_runtime_binding import repository_root

            application_root = repository_root()
        else:
            application_root = Path.cwd()
        runtime_config = certified_config
        storage_composition = None

        if resolved_server_config.production_mode:
            from .services.production_storage_composition import (
                preflight_production_storage,
            )

            storage_composition = preflight_production_storage(
                application_root=application_root,
                mnemo_config=certified_config,
                server_config=resolved_server_config,
            )
            app.state.mutable_workspace_decision = storage_composition.decision
            storage_composition = storage_composition.materialize()
            app.state.mutable_workspace_decision = storage_composition.decision
            runtime_config = storage_composition.engine_config

            if active_engine is not None:
                if storage_composition.certified_read_only:
                    if not active_engine.certified_read_only:
                        raise RuntimeError("UNSAFE_INJECTED_PRODUCTION_STORAGE")
                elif active_engine.config.storage != runtime_config.storage:
                    raise RuntimeError("INJECTED_WORKSPACE_STORAGE_MISMATCH")

        if active_engine is None:
            if (
                resolved_server_config.full_multilingual_v2_enabled
                and not pre_certification_observation
            ):
                from .services.final_qa_operational import (
                    open_production_final_qa_operational_store,
                )

                operational_store = await open_production_final_qa_operational_store(
                    workspace_root=application_root,
                    mnemo_config=certified_config,
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
                runtime_config,
                final_qa_components=resolved_components,
                advanced_retrieval_cursor_codec=build_retrieval_cursor_codec(
                    resolved_server_config
                ),
                certified_read_only=(
                    storage_composition.certified_read_only
                    if storage_composition is not None
                    else False
                ),
                embedding_cache_path=(
                    storage_composition.embedding_cache_path
                    if storage_composition is not None
                    else None
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

            root = application_root.resolve()
            model_cache = resolved_server_config.full_multilingual_v2_model_cache
            if model_cache is None:
                raise RuntimeError("Full Multilingual V2 model cache is missing")
            readiness_evidence, readiness = await ProductionV2ReadinessEvidenceBuilderV1(
                workspace_root=root,
                mnemo_config=certified_config,
                server_config=resolved_server_config,
                identity_manifest=root / IDENTITY_MANIFEST,
                pre_certification_observation=pre_certification_observation,
                certified_production_binding_verified=production_binding is not None,
            ).build()
            if (
                resolved_server_config.reranker_activation_state_path is not None
                and reranker_activation_evidence is not None
            ):
                raise RuntimeError("COMPETING_RERANKER_ACTIVATION_AUTHORITIES")
            installed_v2 = await install_production_full_multilingual_v2(
                engine=active_engine,
                production_config=certified_config,
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
                production_store_path=certified_config.storage.sqlite.path,
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

        if production_binding is not None:
            from .services.production_runtime_binding import record_certified_transport_startup

            record_certified_transport_startup(
                binding=production_binding,
                transport="http",
                server_config=resolved_server_config,
            )

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

    if pre_certification_observation:

        @app.get("/internal/pre-certification/observe")
        async def observe_pre_certification(request: Request) -> dict[str, object]:
            """Authenticated conformance only; no chat or mutation routes exist."""
            from dataclasses import asdict

            from mnemo.engine import EngineState

            from .services.v2_reranker_lifecycle import V2RerankerMode

            claims = getattr(request.state, "auth", None)
            engine_state = getattr(request.app.state, "engine", None)
            runtime = getattr(request.app.state, "full_multilingual_v2_runtime", None)
            identity = getattr(request.app.state, "pre_certification_identity", None)
            authority = getattr(request.app.state, "pre_certification_authority", None)
            if (
                not isinstance(claims, dict)
                or not isinstance(claims.get("sub"), str)
                or engine_state is None
                or engine_state.state is not EngineState.READY
                or runtime is None
                or runtime.reranker.mode is not V2RerankerMode.BGE_V2_M3
                or identity is None
                or authority is None
            ):
                raise HTTPException(status_code=503, detail="Observation unavailable")
            correlation_id = uuid4()
            await authority.observe(
                transport="http",
                identity=identity,
                principal_subject=claims["sub"],
                correlation_id=correlation_id,
                engine=engine_state,
                runtime=runtime,
            )
            return {
                "state": "PRE_CERTIFICATION_OBSERVATION",
                "correlation_id": str(correlation_id),
                "identity": asdict(identity),
            }

        return app

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
