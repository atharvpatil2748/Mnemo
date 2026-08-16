"""FastAPI dependencies for mnemo-server."""

from __future__ import annotations

from fastapi import Request
from mnemo.engine import EngineState, KnowledgeEngine
from mnemo.interfaces import DependencyUnavailableError, TokenCounterInterfaceV1
from mnemo.tokenizers import O200KBaseTokenCounter

from mnemo_server.config import ServerConfig
from mnemo_server.services.streaming import StreamingQueryService
from mnemo_server.services.system import JobService, SystemService
from mnemo_server.tokenizer_provisioning import provision_tokenizer


def get_engine(request: Request) -> KnowledgeEngine:
    """Obtain the initialized and ready KnowledgeEngine from the application state.

    Raises:
        DependencyUnavailableError: If the engine is missing or not in READY state.
    """
    engine: KnowledgeEngine | None = getattr(request.app.state, "engine", None)
    if engine is None or engine.state is not EngineState.READY:
        raise DependencyUnavailableError("KnowledgeEngine is not ready", retryable=True)
    return engine


def get_token_counter(request: Request) -> TokenCounterInterfaceV1:
    """Obtain or lazily provision the canonical token counter from application state."""
    token_counter: TokenCounterInterfaceV1 | None = getattr(
        request.app.state, "token_counter", None
    )
    if token_counter is None:
        asset_path = provision_tokenizer()
        token_counter = O200KBaseTokenCounter(asset_path)
        request.app.state.token_counter = token_counter
    return token_counter


def get_server_config(request: Request) -> ServerConfig:
    """Obtain the server configuration from application state."""
    server_config: ServerConfig | None = getattr(request.app.state, "server_config", None)
    if server_config is None:
        return ServerConfig()
    return server_config


def get_system_service(request: Request) -> SystemService:
    """Obtain SystemService with engine and token counter from application state."""
    engine: KnowledgeEngine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        raise DependencyUnavailableError("KnowledgeEngine is not ready", retryable=True)
    token_counter: TokenCounterInterfaceV1 | None = getattr(
        request.app.state, "token_counter", None
    )
    return SystemService(engine=engine, token_counter=token_counter)


def get_job_service(request: Request) -> JobService:
    """Obtain the singleton JobService from application state."""
    job_service: JobService | None = getattr(request.app.state, "job_service", None)
    if job_service is None:
        job_service = JobService()
        request.app.state.job_service = job_service
    return job_service


def get_streaming_query_service(request: Request) -> StreamingQueryService:
    """Obtain StreamingQueryService from ready KnowledgeEngine and TokenCounter."""
    engine = get_engine(request)
    token_counter = get_token_counter(request)
    return StreamingQueryService(engine=engine, token_counter=token_counter)
