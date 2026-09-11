"""Transport-owned authenticated principal binding for MCP sessions."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from mnemo_server.config import ServerConfig
from mnemo_server.services.authorization import (
    ServerPrincipalV1,
    principal_from_claims,
)

MCPPrincipalProviderV1 = Callable[[], ServerPrincipalV1]

_SESSION_PRINCIPAL: ContextVar[ServerPrincipalV1 | None] = ContextVar(
    "mnemo_mcp_session_principal", default=None
)


def require_authenticated_principal(principal: ServerPrincipalV1 | None) -> ServerPrincipalV1:
    """Reject missing or anonymous transport principals."""
    if principal is None or not principal.authenticated:
        raise PermissionError("authenticated MCP server principal is required")
    return principal


def stdio_principal(config: ServerConfig) -> ServerPrincipalV1:
    """Create the governed local stdio principal from server-only configuration."""
    subject = config.mcp_stdio_principal_subject
    if not isinstance(subject, str) or not subject.strip():
        raise PermissionError("MCP stdio principal subject is not configured")
    return require_authenticated_principal(principal_from_claims({"sub": subject.strip()}))


def sse_principal_from_scope(scope: dict[str, Any]) -> ServerPrincipalV1:
    """Map claims already validated by AuthMiddleware into the common principal type."""
    state = scope.get("state")
    claims = state.get("auth") if isinstance(state, dict) else None
    if not isinstance(claims, dict):
        raise PermissionError("authenticated MCP SSE session claims are required")
    return require_authenticated_principal(principal_from_claims(claims))


@contextmanager
def bind_session_principal(principal: ServerPrincipalV1) -> Iterator[None]:
    """Bind one validated principal to the current MCP transport session."""
    token = _SESSION_PRINCIPAL.set(require_authenticated_principal(principal))
    try:
        yield
    finally:
        _SESSION_PRINCIPAL.reset(token)


def session_principal() -> ServerPrincipalV1:
    """Return the authenticated principal bound to the current MCP session."""
    return require_authenticated_principal(_SESSION_PRINCIPAL.get())
