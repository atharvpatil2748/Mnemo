"""HTTP membership principal derived from verified deployment JWT settings."""

from __future__ import annotations

from fastapi import Request, WebSocket
from mnemo.engine import KnowledgeEngine
from mnemo.interfaces import PrincipalContextV1

from mnemo_server.auth import AuthError
from mnemo_server.config import ServerConfig

from .scope_authority import SQLiteNotebookScopeAuthority
from .trusted_actor import TrustedJWTActorMapper


def membership_http_principal(request: Request, engine: KnowledgeEngine) -> PrincipalContextV1:
    """Fail closed unless middleware and the membership mapper agree on JWT identity."""
    authority = getattr(engine, "server_scope_authority", None)
    mapper = getattr(engine, "server_actor_mapper", None)
    config = getattr(request.app.state, "server_config", None)
    if (
        not isinstance(authority, SQLiteNotebookScopeAuthority)
        or not isinstance(mapper, TrustedJWTActorMapper)
        or not isinstance(config, ServerConfig)
        or config.auth_mode != "jwt"
        or config.jwt_secret != mapper.signing_secret
        or tuple(config.jwt_algorithms) != mapper.allowed_algorithms
        or not isinstance(getattr(request.state, "auth", None), dict)
    ):
        raise PermissionError("trusted membership identity is unavailable")
    authorization = request.headers.get("Authorization", "").split()
    if len(authorization) != 2 or authorization[0].lower() != "bearer":
        raise PermissionError("trusted membership identity is unavailable")
    try:
        return mapper.from_token(authorization[1])
    except AuthError as error:
        raise PermissionError("trusted membership identity is unavailable") from error


def membership_websocket_principal(
    websocket: WebSocket, engine: KnowledgeEngine
) -> PrincipalContextV1:
    """Validate each WebSocket query from its signed bearer; HTTP middleware does not run here."""
    authority = getattr(engine, "server_scope_authority", None)
    mapper = getattr(engine, "server_actor_mapper", None)
    config = getattr(websocket.app.state, "server_config", None)
    if (
        not isinstance(authority, SQLiteNotebookScopeAuthority)
        or not isinstance(mapper, TrustedJWTActorMapper)
        or not isinstance(config, ServerConfig)
        or config.auth_mode != "jwt"
        or config.jwt_secret != mapper.signing_secret
        or tuple(config.jwt_algorithms) != mapper.allowed_algorithms
    ):
        raise PermissionError("trusted membership identity is unavailable")
    authorization = websocket.headers.get("Authorization", "").split()
    if len(authorization) != 2 or authorization[0].lower() != "bearer":
        raise PermissionError("trusted membership identity is unavailable")
    try:
        return mapper.from_token(authorization[1])
    except AuthError as error:
        raise PermissionError("trusted membership identity is unavailable") from error
