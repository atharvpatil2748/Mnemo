"""Authentication middleware and JWT/API-key validation for mnemo-server."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from mnemo_server.config import ServerConfig

_LOGGER = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/v1/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

_ALG_HASH_MAP = {
    "HS256": hashlib.sha256,
    "HS384": hashlib.sha384,
    "HS512": hashlib.sha512,
}


class AuthError(Exception):
    """Raised when authentication fails."""

    def __init__(self, message: str, code: str = "auth.unauthorized") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _base64url_decode(input_str: str) -> bytes:
    """Decode a base64url-encoded string adding padding if necessary."""
    rem = len(input_str) % 4
    if rem > 0:
        input_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(input_str)


def validate_jwt(
    token: str,
    secret: str,
    allowed_algorithms: tuple[str, ...] = ("HS256",),
    tolerance_seconds: int = 10,
) -> dict[str, Any]:
    """Validate a standard RFC 7519 JWT token using HMAC-SHA secret verification."""
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise AuthError("Invalid JWT token format")

    header_b64, payload_b64, sig_b64 = parts

    try:
        header_bytes = _base64url_decode(header_b64)
        header = json.loads(header_bytes.decode("utf-8"))
    except Exception as err:
        raise AuthError(f"Malformed JWT header: {err}") from err

    if not isinstance(header, dict):
        raise AuthError("JWT header must be a JSON object")

    alg = header.get("alg")
    if not alg or alg not in allowed_algorithms:
        raise AuthError(f"Unsupported or disallowed JWT algorithm: {alg!r}")

    hash_func = _ALG_HASH_MAP.get(alg)
    if hash_func is None:
        raise AuthError(f"Unsupported HMAC algorithm: {alg}")

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hash_func).digest()

    try:
        actual_sig = _base64url_decode(sig_b64)
    except Exception as err:
        raise AuthError(f"Malformed JWT signature: {err}") from err

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise AuthError("JWT signature verification failed")

    try:
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as err:
        raise AuthError(f"Malformed JWT payload: {err}") from err

    if not isinstance(payload, dict):
        raise AuthError("JWT payload must be a JSON object")

    now = int(time.time())

    # Expiration check
    exp = payload.get("exp")
    if exp is not None:
        if not isinstance(exp, int | float):
            raise AuthError("JWT 'exp' claim must be a number")
        if now > (exp + tolerance_seconds):
            raise AuthError("JWT token has expired")

    # Not Before check
    nbf = payload.get("nbf")
    if nbf is not None:
        if not isinstance(nbf, int | float):
            raise AuthError("JWT 'nbf' claim must be a number")
        if now < (nbf - tolerance_seconds):
            raise AuthError("JWT token is not yet valid")

    return payload


class AuthMiddleware(BaseHTTPMiddleware):
    """ASGI middleware enforcing authentication policy based on ServerConfig."""

    def __init__(self, app: ASGIApp, config: ServerConfig | None = None) -> None:
        super().__init__(app)
        self._config = config or ServerConfig()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Evaluate request against the active authentication strategy."""
        path = request.url.path
        if path in EXEMPT_PATHS or path.rstrip("/") in EXEMPT_PATHS:
            return await call_next(request)

        # Use request application state config if dynamically updated
        config: ServerConfig = getattr(request.app.state, "server_config", self._config)

        if config.auth_mode == "none":
            return await call_next(request)

        if config.auth_mode == "api-key":
            if not config.api_key:
                _LOGGER.error("auth_mode is 'api-key' but no API key is configured")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "code": "internal.configuration",
                            "message": "Server authentication is misconfigured",
                            "details": {},
                            "retryable": False,
                        }
                    },
                )

            provided_key = None
            auth_header = request.headers.get("Authorization")
            if auth_header:
                parts = auth_header.strip().split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    provided_key = parts[1]
                elif len(parts) == 1:
                    provided_key = parts[0]

            if not provided_key:
                provided_key = request.headers.get("X-API-Key")

            if not provided_key or not hmac.compare_digest(
                provided_key.strip(), config.api_key.strip()
            ):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "auth.unauthorized",
                            "message": "Invalid or missing API key",
                            "details": {},
                            "retryable": False,
                        }
                    },
                )

            return await call_next(request)

        if config.auth_mode == "jwt":
            if not config.jwt_secret:
                _LOGGER.error("auth_mode is 'jwt' but no JWT secret is configured")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "code": "internal.configuration",
                            "message": "Server authentication is misconfigured",
                            "details": {},
                            "retryable": False,
                        }
                    },
                )

            token = None
            auth_header = request.headers.get("Authorization")
            if auth_header:
                parts = auth_header.strip().split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    token = parts[1]

            if not token:
                token = request.query_params.get("token")

            if not token:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "auth.unauthorized",
                            "message": "Missing Bearer token",
                            "details": {},
                            "retryable": False,
                        }
                    },
                )

            try:
                claims = validate_jwt(
                    token=token,
                    secret=config.jwt_secret,
                    allowed_algorithms=config.jwt_algorithms,
                )
                request.state.auth = claims
            except AuthError as err:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": err.code,
                            "message": err.message,
                            "details": {},
                            "retryable": False,
                        }
                    },
                )

            return await call_next(request)

        return await call_next(request)
