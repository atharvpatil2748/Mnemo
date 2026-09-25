"""Model Context Protocol (MCP) server core implementation for Mnemo."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import mcp.types as types
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mnemo import EngineState, KnowledgeEngine, MnemoConfig, __version__
from mnemo.engine import FinalQAComponents
from mnemo.tokenizers import O200KBaseTokenCounter
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from mnemo_server.auth import AuthMiddleware
from mnemo_server.config import ServerConfig
from mnemo_server.runtime_config import resolve_mnemo_runtime_config
from mnemo_server.schemas.capabilities_v2 import CapabilityDiscoveryRequest
from mnemo_server.services.retrieval_v2 import build_retrieval_cursor_codec
from mnemo_server.tokenizer_provisioning import provision_tokenizer

from .principal import (
    MCPPrincipalProviderV1,
    bind_session_principal,
    require_authenticated_principal,
    session_principal,
    sse_principal_from_scope,
    stdio_principal,
)
from .tools import execute_mcp_tool, get_mcp_tools, structured_content_for

logger = logging.getLogger("mnemo.mcp")


async def _install_v2_if_enabled(
    engine: KnowledgeEngine,
    config: ServerConfig,
    production_config: MnemoConfig,
    reranker_activation_evidence: object | None = None,
    pre_certification_observation: bool = False,
    certified_production_binding_verified: bool = False,
) -> Any | None:
    if not config.full_multilingual_v2_enabled:
        return None
    from mnemo_server.services.full_multilingual_v2_startup import (
        IDENTITY_MANIFEST,
        install_production_full_multilingual_v2,
    )
    from mnemo_server.services.production_store_readiness import (
        ProductionV2ReadinessEvidenceBuilderV1,
    )

    if config.production_mode:
        from mnemo_server.services.production_runtime_binding import repository_root

        root = repository_root()
    else:
        root = Path.cwd().resolve()
    cache = config.full_multilingual_v2_model_cache
    if cache is None:
        raise RuntimeError("Full Multilingual V2 model cache is missing")
    _, readiness = await ProductionV2ReadinessEvidenceBuilderV1(
        workspace_root=root,
        mnemo_config=production_config,
        server_config=config,
        identity_manifest=root / IDENTITY_MANIFEST,
        pre_certification_observation=pre_certification_observation,
        certified_production_binding_verified=certified_production_binding_verified,
    ).build()
    if (
        config.reranker_activation_state_path is not None
        and reranker_activation_evidence is not None
    ):
        raise RuntimeError("COMPETING_RERANKER_ACTIVATION_AUTHORITIES")
    installed = await install_production_full_multilingual_v2(
        engine=engine,
        production_config=production_config,
        workspace_root=root,
        model_cache=cache,
        readiness=readiness,
    )
    from mnemo_server.services.durable_reranker_activation import (
        restore_production_reranker_activation,
    )

    await restore_production_reranker_activation(
        installed=installed,
        config=config,
        workspace_root=root,
        production_store_path=production_config.storage.sqlite.path,
    )
    if reranker_activation_evidence is not None:
        from mnemo_server.services.v2_reranker_lifecycle import RerankerActivationEvidenceV1

        if not isinstance(reranker_activation_evidence, RerankerActivationEvidenceV1):
            await installed.close()
            raise TypeError("reranker activation evidence has the wrong governed type")
        await installed.reranker_activation.activate(reranker_activation_evidence)
    return installed


def configure_stderr_logging(level: str = "INFO") -> None:
    """Configure all root and mnemo loggers to emit exclusively to sys.stderr.

    This guarantees that standard I/O (stdout) remains reserved exclusively for
    framed JSON-RPC protocol packets in stdio mode.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    # Remove existing stdout/stderr handlers to prevent duplication
    root_logger.handlers = [handler]

    # Silence stdout leaks from ML libraries in stdio transport mode
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"


class MnemoServer(Server):
    """Subclass of MCP Server providing typed KnowledgeEngine association."""

    _engine: KnowledgeEngine | None = None
    _config: ServerConfig
    _workspace_decision: Any | None = None
    _certified_binding: Any | None = None
    _transport_label: str | None = None


def create_mcp_server(
    engine: KnowledgeEngine | None = None,
    config: ServerConfig | None = None,
    principal_provider: MCPPrincipalProviderV1 | None = None,
    workspace_decision: Any | None = None,
    certified_binding: Any | None = None,
    transport_label: str | None = None,
) -> Server:
    """Create and configure the canonical Mnemo MCP Server instance.

    Module 8.1 registered the server identity, capability negotiation, and baseline
    transport infrastructure. Module 8.2 delivers the six authoritative knowledge
    retrieval tools.
    """
    server: MnemoServer = MnemoServer(name="mnemo-mcp", version=__version__)
    server._engine = engine
    server._config = config or ServerConfig()
    server._workspace_decision = workspace_decision
    server._certified_binding = certified_binding
    server._transport_label = transport_label
    resolved_principal_provider = principal_provider

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        """List knowledge tools exposed by the Mnemo MCP server."""
        if server._config.full_multilingual_v2_enabled:
            require_authenticated_principal(
                resolved_principal_provider() if resolved_principal_provider else None
            )
        return get_mcp_tools()

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> tuple[
        list[types.TextContent | types.ImageContent | types.EmbeddedResource],
        dict[str, Any],
    ]:
        """Execute an authorized Mnemo MCP knowledge tool call."""
        resolved_arguments = arguments or {}
        principal = resolved_principal_provider() if resolved_principal_provider else None
        content = await execute_mcp_tool(
            server._engine,
            name,
            resolved_arguments,
            server._config,
            principal,
            server._workspace_decision,
            server._certified_binding,
            server._transport_label,
        )
        return content, structured_content_for(name, resolved_arguments, content)

    @server.list_prompts()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_prompts() -> list[types.Prompt]:
        """List prompts exposed by Mnemo."""
        return []

    @server.list_resources()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_resources() -> list[types.Resource]:
        """List resources exposed by Mnemo."""
        if server._config.full_multilingual_v2_enabled:
            require_authenticated_principal(
                resolved_principal_provider() if resolved_principal_provider else None
            )
        return [
            types.Resource(
                name="Mnemo Phase 8.5 runtime capabilities",
                uri=AnyUrl("mnemo://capabilities"),
                description=(
                    "Deterministic runtime-derived lifecycle, dependency, generation, "
                    "transport, bounds, and task-guidance metadata."
                ),
                mimeType="application/json",
            )
        ]

    @server.read_resource()  # type: ignore[no-untyped-call]
    async def read_resource(uri):  # type: ignore[no-untyped-def]
        if server._config.full_multilingual_v2_enabled:
            require_authenticated_principal(
                resolved_principal_provider() if resolved_principal_provider else None
            )
        if str(uri) != "mnemo://capabilities":
            raise ValueError("Unknown Mnemo resource")
        if server._engine is None or server._engine.state is not EngineState.READY:
            raise RuntimeError("KnowledgeEngine is not ready")
        from mnemo_server.services.capabilities_v2 import CapabilityDiscoveryService

        principal = resolved_principal_provider() if resolved_principal_provider else None
        service = CapabilityDiscoveryService(
            server._engine,
            server._config,
            server._workspace_decision,
            server._certified_binding,
            server._transport_label,
        )
        document = (
            await service.document_for_principal(
                CapabilityDiscoveryRequest(), require_authenticated_principal(principal)
            )
            if server._config.full_multilingual_v2_enabled
            else service.document()
        )
        return json.dumps(document.model_dump(mode="json"), sort_keys=True)

    return server


def create_pre_certification_mcp_server(
    *,
    principal_provider: MCPPrincipalProviderV1,
    runtime_provider: Callable[[], tuple[Any, Any, Any, Any]],
    transport: str,
) -> Server:
    """Expose exactly one authenticated, read-only observation tool."""
    from dataclasses import asdict

    from mnemo_server.services.v2_reranker_lifecycle import V2RerankerMode

    if transport not in {"stdio", "sse", "external_tunnel"}:
        raise RuntimeError("PRE_CERTIFICATION_TRANSPORT_REJECTED")
    server = MnemoServer(name="mnemo-pre-certification", version=__version__)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        require_authenticated_principal(principal_provider())
        return [
            types.Tool(
                name="observe_runtime",
                description="Read-only pre-certification runtime identity observation",
                inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
            )
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> tuple[list[types.TextContent], dict[str, Any]]:
        if name != "observe_runtime" or arguments:
            raise RuntimeError("PRE_CERTIFICATION_TOOL_UNAVAILABLE")
        principal = require_authenticated_principal(principal_provider())
        active_engine, runtime, identity, authority = runtime_provider()
        if (
            active_engine is None
            or active_engine.state is not EngineState.READY
            or runtime is None
            or runtime.reranker.mode is not V2RerankerMode.BGE_V2_M3
            or identity is None
            or authority is None
        ):
            raise RuntimeError("PRE_CERTIFICATION_OBSERVATION_UNAVAILABLE")
        correlation = uuid4()
        await authority.observe(
            transport=transport,
            identity=identity,
            principal_subject=str(principal.actor_id),
            correlation_id=correlation,
            engine=active_engine,
            runtime=runtime,
        )
        result = {
            "state": "PRE_CERTIFICATION_OBSERVATION",
            "correlation_id": str(correlation),
            "identity": asdict(identity),
        }
        return [types.TextContent(type="text", text=json.dumps(result))], result

    return server


async def run_stdio_server(
    *,
    config: ServerConfig | None = None,
    mnemo_config: MnemoConfig | None = None,
    engine: KnowledgeEngine | None = None,
    reranker_activation_evidence: object | None = None,
    runtime_observer: Callable[[Any], None] | None = None,
    transport_label: str = "mcp_stdio",
    pre_certification_observation: bool = False,
) -> None:
    """Run the Mnemo MCP server over standard I/O (stdio) transport.

    All diagnostic output is routed strictly to stderr to keep stdout 100% protocol-pure.
    """
    log_level = config.log_level if config else "INFO"
    configure_stderr_logging(log_level)

    logger.info("Starting Mnemo MCP stdio server (v%s)", __version__)

    owns_engine = engine is None
    active_engine = engine
    resolved_server_config = config or ServerConfig()
    production_binding = None
    observation_identity = None
    observation_authority = None
    if resolved_server_config.full_multilingual_v2_enabled:
        if pre_certification_observation:
            if engine is not None or reranker_activation_evidence is not None:
                raise RuntimeError("PRE_CERTIFICATION_INJECTED_RUNTIME_REJECTED")
            from mnemo_server.services.pre_certification_observation import (
                resolve_pre_certification_observation,
            )

            resolved_cfg, observation_identity, observation_authority = (
                resolve_pre_certification_observation(
                    server_config=resolved_server_config, mnemo_config=mnemo_config
                )
            )
        else:
            from mnemo_server.services.production_runtime_binding import (
                resolve_certified_production_binding,
            )

            resolved_cfg, production_binding = resolve_certified_production_binding(
                server_config=resolved_server_config, mnemo_config=mnemo_config
            )
            logger.info("Certified MCP stdio binding admitted: %s", production_binding.binding_id)
    elif pre_certification_observation:
        raise RuntimeError("PRE_CERTIFICATION_BINDING_REJECTED")
    else:
        resolved_cfg = resolve_mnemo_runtime_config(mnemo_config)
        from mnemo_server.services.production_runtime_binding import (
            reject_uncertified_corpus_startup,
        )

        reject_uncertified_corpus_startup(
            mnemo_config=resolved_cfg, server_config=resolved_server_config
        )
    if production_binding is not None or observation_authority is not None:
        from mnemo_server.services.production_runtime_binding import repository_root

        application_root = repository_root()
    else:
        application_root = Path.cwd()
    storage_composition = None
    runtime_cfg = resolved_cfg
    if resolved_server_config.production_mode:
        from mnemo_server.services.production_storage_composition import (
            preflight_production_storage,
        )

        storage_composition = preflight_production_storage(
            application_root=application_root,
            mnemo_config=resolved_cfg,
            server_config=resolved_server_config,
        ).materialize()
        runtime_cfg = storage_composition.engine_config
        if active_engine is not None:
            if storage_composition.certified_read_only:
                if not active_engine.certified_read_only:
                    raise RuntimeError("UNSAFE_INJECTED_PRODUCTION_STORAGE")
            elif active_engine.config.storage != runtime_cfg.storage:
                raise RuntimeError("INJECTED_WORKSPACE_STORAGE_MISMATCH")
    operational_store = None
    if active_engine is None:
        try:
            final_qa_components = None
            if (
                resolved_server_config.full_multilingual_v2_enabled
                and not pre_certification_observation
            ):
                from mnemo_server.services.final_qa_operational import (
                    open_production_final_qa_operational_store,
                )

                operational_store = await open_production_final_qa_operational_store(
                    workspace_root=application_root,
                    mnemo_config=resolved_cfg,
                    server_config=resolved_server_config,
                )
                tokenizer_path = await asyncio.to_thread(provision_tokenizer)
                final_qa_components = FinalQAComponents(
                    token_counter=O200KBaseTokenCounter(tokenizer_path),
                    clock=lambda: datetime.now(UTC),
                    operational_store_v2=operational_store,
                )
            active_engine = KnowledgeEngine(
                config=runtime_cfg,
                final_qa_components=final_qa_components,
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
        except Exception as err:
            if resolved_server_config.production_mode:
                raise RuntimeError("CERTIFIED_PRODUCTION_STARTUP_FAILED") from err
            logger.warning("KnowledgeEngine could not be loaded: %s", err)

    if active_engine is not None and active_engine.state != EngineState.READY:
        if owns_engine:
            try:
                await asyncio.to_thread(provision_tokenizer)
            except Exception as err:
                logger.warning("Tokenizer provisioning check skipped or failed: %s", err)
        try:
            await active_engine.initialize()
        except Exception as err:
            if resolved_server_config.production_mode:
                raise RuntimeError("CERTIFIED_PRODUCTION_STARTUP_FAILED") from err
            logger.warning("KnowledgeEngine initialization encountered error: %s", err)

    if resolved_server_config.production_mode and (
        active_engine is None or active_engine.state != EngineState.READY
    ):
        raise RuntimeError("CERTIFIED_PRODUCTION_STARTUP_FAILED")

    resolved_config = resolved_server_config
    installed_v2 = None
    if active_engine is not None and active_engine.state == EngineState.READY:
        installed_v2 = await _install_v2_if_enabled(
            active_engine,
            resolved_config,
            resolved_cfg,
            reranker_activation_evidence,
            pre_certification_observation,
            production_binding is not None,
        )
    principal = (
        stdio_principal(resolved_config) if resolved_config.full_multilingual_v2_enabled else None
    )
    if pre_certification_observation:
        if principal is None:
            raise RuntimeError("PRE_CERTIFICATION_PRINCIPAL_UNAVAILABLE")
        server = create_pre_certification_mcp_server(
            principal_provider=lambda: principal,
            runtime_provider=lambda: (
                active_engine,
                installed_v2,
                observation_identity,
                observation_authority,
            ),
            transport=("external_tunnel" if transport_label == "external_tunnel" else "stdio"),
        )
    else:
        server = create_mcp_server(
            engine=active_engine,
            config=resolved_config,
            principal_provider=(lambda: principal) if principal is not None else None,
            workspace_decision=(
                storage_composition.decision if storage_composition is not None else None
            ),
            certified_binding=production_binding,
            transport_label=transport_label,
        )
    init_options = server.create_initialization_options()

    try:
        async with stdio_server() as (read_stream, write_stream):
            if production_binding is not None:
                from mnemo_server.services.production_runtime_binding import (
                    record_certified_transport_startup,
                )

                record_certified_transport_startup(
                    binding=production_binding,
                    transport=transport_label,
                    server_config=resolved_server_config,
                )
            logger.info("Stdio transport stream connected; serving requests")
            await server.run(read_stream, write_stream, init_options)
    except asyncio.CancelledError:
        logger.info("Stdio server execution cancelled")
    finally:
        if installed_v2 is not None:
            if runtime_observer is not None:
                runtime_observer(installed_v2)
            await installed_v2.close()
        if owns_engine and active_engine is not None and active_engine.state == EngineState.READY:
            logger.info("Shutting down KnowledgeEngine")
            await active_engine.shutdown()
        if operational_store is not None:
            await operational_store.close()


def create_sse_app(
    *,
    server: Server | None = None,
    config: ServerConfig | None = None,
    mnemo_config: MnemoConfig | None = None,
    engine: KnowledgeEngine | None = None,
    reranker_activation_evidence: object | None = None,
    pre_certification_observation: bool = False,
) -> Starlette:
    """Create a Starlette ASGI application hosting the MCP SSE transport."""
    server_config = config or ServerConfig()
    owns_engine = engine is None
    active_engine = engine
    installed_v2: Any | None = None
    operational_store = None
    observation_identity = None
    observation_authority = None
    if pre_certification_observation and (
        server is not None or engine is not None or reranker_activation_evidence is not None
    ):
        raise RuntimeError("PRE_CERTIFICATION_INJECTED_RUNTIME_REJECTED")
    active_server = (
        create_pre_certification_mcp_server(
            principal_provider=session_principal,
            runtime_provider=lambda: (
                active_engine,
                installed_v2,
                observation_identity,
                observation_authority,
            ),
            transport="sse",
        )
        if pre_certification_observation
        else server
        or create_mcp_server(
            engine=active_engine,
            config=server_config,
            principal_provider=(
                session_principal if server_config.full_multilingual_v2_enabled else None
            ),
        )
    )
    if isinstance(active_server, MnemoServer):
        active_server._config = server_config
    sse_transport = SseServerTransport(endpoint="/messages")

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        nonlocal active_engine, installed_v2, operational_store
        nonlocal observation_identity, observation_authority
        production_binding = None
        if server_config.full_multilingual_v2_enabled:
            if pre_certification_observation:
                from mnemo_server.services.pre_certification_observation import (
                    resolve_pre_certification_observation,
                )

                resolved_core_config, observation_identity, observation_authority = (
                    resolve_pre_certification_observation(
                        server_config=server_config, mnemo_config=mnemo_config
                    )
                )
                app.state.pre_certification_identity = observation_identity
            else:
                from mnemo_server.services.production_runtime_binding import (
                    resolve_certified_production_binding,
                )

                resolved_core_config, production_binding = resolve_certified_production_binding(
                    server_config=server_config, mnemo_config=mnemo_config
                )
                app.state.certified_production_binding = production_binding
                if isinstance(active_server, MnemoServer):
                    active_server._certified_binding = production_binding
                    active_server._transport_label = "mcp_sse"
        elif pre_certification_observation:
            raise RuntimeError("PRE_CERTIFICATION_BINDING_REJECTED")
        else:
            resolved_core_config = resolve_mnemo_runtime_config(mnemo_config)
            from mnemo_server.services.production_runtime_binding import (
                reject_uncertified_corpus_startup,
            )

            reject_uncertified_corpus_startup(
                mnemo_config=resolved_core_config, server_config=server_config
            )
        if production_binding is not None or observation_authority is not None:
            from mnemo_server.services.production_runtime_binding import repository_root

            application_root = repository_root()
        else:
            application_root = Path.cwd()
        storage_composition = None
        runtime_config = resolved_core_config
        if server_config.production_mode:
            from mnemo_server.services.production_storage_composition import (
                preflight_production_storage,
            )

            storage_composition = preflight_production_storage(
                application_root=application_root,
                mnemo_config=resolved_core_config,
                server_config=server_config,
            ).materialize()
            if isinstance(active_server, MnemoServer):
                active_server._workspace_decision = storage_composition.decision
            runtime_config = storage_composition.engine_config
            if active_engine is not None:
                if storage_composition.certified_read_only:
                    if not active_engine.certified_read_only:
                        raise RuntimeError("UNSAFE_INJECTED_PRODUCTION_STORAGE")
                elif active_engine.config.storage != runtime_config.storage:
                    raise RuntimeError("INJECTED_WORKSPACE_STORAGE_MISMATCH")
        if active_engine is None:
            try:
                final_qa_components = None
                if server_config.full_multilingual_v2_enabled and not pre_certification_observation:
                    from mnemo_server.services.final_qa_operational import (
                        open_production_final_qa_operational_store,
                    )

                    operational_store = await open_production_final_qa_operational_store(
                        workspace_root=application_root,
                        mnemo_config=resolved_core_config,
                        server_config=server_config,
                    )
                    tokenizer_path = await asyncio.to_thread(provision_tokenizer)
                    final_qa_components = FinalQAComponents(
                        token_counter=O200KBaseTokenCounter(tokenizer_path),
                        clock=lambda: datetime.now(UTC),
                        operational_store_v2=operational_store,
                    )
                active_engine = KnowledgeEngine(
                    config=runtime_config,
                    final_qa_components=final_qa_components,
                    advanced_retrieval_cursor_codec=build_retrieval_cursor_codec(server_config),
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
            except Exception as err:
                if server_config.production_mode:
                    raise RuntimeError("CERTIFIED_PRODUCTION_STARTUP_FAILED") from err
                logger.warning("KnowledgeEngine could not be loaded: %s", err)
            app.state.engine = active_engine
            if isinstance(active_server, MnemoServer):
                active_server._engine = active_engine

        if active_engine is not None and active_engine.state != EngineState.READY:
            if owns_engine:
                try:
                    await asyncio.to_thread(provision_tokenizer)
                except Exception as err:
                    logger.warning("Tokenizer provisioning check skipped or failed: %s", err)
            try:
                await active_engine.initialize()
            except Exception as err:
                if server_config.production_mode:
                    raise RuntimeError("CERTIFIED_PRODUCTION_STARTUP_FAILED") from err
                logger.warning("KnowledgeEngine initialization encountered error: %s", err)

        if server_config.production_mode and (
            active_engine is None or active_engine.state != EngineState.READY
        ):
            raise RuntimeError("CERTIFIED_PRODUCTION_STARTUP_FAILED")
        else:
            app.state.engine = active_engine

        if active_engine is not None and active_engine.state == EngineState.READY:
            installed_v2 = await _install_v2_if_enabled(
                active_engine,
                server_config,
                resolved_core_config,
                reranker_activation_evidence,
                pre_certification_observation,
                production_binding is not None,
            )
            app.state.full_multilingual_v2_runtime = installed_v2

        if production_binding is not None:
            from mnemo_server.services.production_runtime_binding import (
                record_certified_transport_startup,
            )

            record_certified_transport_startup(
                binding=production_binding,
                transport="mcp_sse",
                server_config=server_config,
            )

        yield

        if installed_v2 is not None:
            await installed_v2.close()
        if owns_engine and active_engine is not None and active_engine.state == EngineState.READY:
            await active_engine.shutdown()
        if operational_store is not None:
            await operational_store.close()

    class _SseEndpoint:
        """Raw ASGI endpoint because the MCP transport owns the HTTP response."""

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            init_options = active_server.create_initialization_options()
            if server_config.full_multilingual_v2_enabled:
                principal = sse_principal_from_scope(scope)
                with bind_session_principal(principal):
                    async with sse_transport.connect_sse(scope, receive, send) as (
                        read_stream,
                        write_stream,
                    ):
                        await active_server.run(read_stream, write_stream, init_options)
            else:
                async with sse_transport.connect_sse(scope, receive, send) as (
                    read_stream,
                    write_stream,
                ):
                    await active_server.run(read_stream, write_stream, init_options)

    class _MessageEndpoint:
        """Raw ASGI endpoint preventing a second Starlette response write."""

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            await sse_transport.handle_post_message(scope, receive, send)

    async def handle_health(request: Request) -> Response:
        """Health check endpoint for MCP SSE service."""
        current_engine = getattr(request.app.state, "engine", active_engine)
        engine_state_str = (
            current_engine.state.value if current_engine else EngineState.UNINITIALIZED.value
        )
        return JSONResponse(
            {
                "status": "ok",
                "service": "mnemo-mcp",
                "version": __version__,
                "engine_state": engine_state_str,
            }
        )

    routes = [
        Route("/sse", endpoint=_SseEndpoint(), methods=["GET"]),
        Route("/messages", endpoint=_MessageEndpoint(), methods=["POST"]),
        Route("/health", endpoint=handle_health, methods=["GET"]),
    ]

    app = Starlette(routes=routes, lifespan=lifespan)
    if server_config.auth_mode in ("api-key", "jwt"):
        app.add_middleware(AuthMiddleware, config=server_config)

    return app


def run_sse_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8001,
    config: ServerConfig | None = None,
    engine: KnowledgeEngine | None = None,
    reranker_activation_evidence: object | None = None,
    pre_certification_observation: bool = False,
) -> None:
    """Run the MCP SSE HTTP transport using Uvicorn."""
    server_config = config or ServerConfig(host=host, port=port)
    app = create_sse_app(
        config=server_config,
        engine=engine,
        reranker_activation_evidence=reranker_activation_evidence,
        pre_certification_observation=pre_certification_observation,
    )
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=server_config.log_level,
    )
