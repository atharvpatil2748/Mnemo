"""Server-level transport and process configuration for mnemo-server."""

from __future__ import annotations

import json
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_VALID_LOG_LEVELS = frozenset({"critical", "error", "warning", "info", "debug", "trace"})
_VALID_AUTH_MODES = frozenset({"none", "api-key", "jwt"})


class ServerConfig(BaseModel):
    """Transport and runtime process configuration for mnemo-server."""

    model_config = ConfigDict(frozen=True)

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: tuple[str, ...] = Field(
        default=("http://localhost:3000", "http://127.0.0.1:3000")
    )
    log_level: Literal["critical", "error", "warning", "info", "debug", "trace"] = Field(
        default="info"
    )
    max_upload_bytes: int = Field(
        default=52_428_800,
        ge=1,
        description="Maximum allowed size in bytes for uploaded source files (default: 50MB).",
    )
    auth_mode: Literal["none", "api-key", "jwt"] = Field(
        default="none",
        description="Authentication mode for protecting API endpoints (none, api-key, jwt).",
    )
    api_key: str | None = Field(
        default=None,
        description="Static API key required when auth_mode is api-key.",
    )
    jwt_secret: str | None = Field(
        default=None,
        description="Shared secret key for verifying HMAC-SHA JWT tokens when auth_mode is jwt.",
    )
    jwt_algorithms: tuple[str, ...] = Field(
        default=("HS256",),
        description="Allowed JWT signing algorithms.",
    )

    @classmethod
    def from_env(cls) -> ServerConfig:
        """Load server configuration from MNEMO_SERVER_* environment variables."""
        host = os.environ.get("MNEMO_SERVER_HOST", "127.0.0.1")
        port_raw = os.environ.get("MNEMO_SERVER_PORT", "8000")
        try:
            port = int(port_raw)
        except ValueError as err:
            raise ValueError(f"MNEMO_SERVER_PORT must be an integer, got: {port_raw!r}") from err

        cors_raw = os.environ.get("MNEMO_SERVER_CORS_ORIGINS")
        if cors_raw is None:
            cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
        else:
            stripped = cors_raw.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        cors_origins = tuple(
                            str(item).strip() for item in parsed if str(item).strip()
                        )
                    else:
                        cors_origins = tuple(
                            item.strip() for item in stripped.split(",") if item.strip()
                        )
                except json.JSONDecodeError:
                    cors_origins = tuple(
                        item.strip() for item in stripped.split(",") if item.strip()
                    )
            else:
                cors_origins = tuple(item.strip() for item in stripped.split(",") if item.strip())

        log_level_raw = os.environ.get("MNEMO_SERVER_LOG_LEVEL", "info").lower()
        if log_level_raw not in _VALID_LOG_LEVELS:
            valid_str = sorted(_VALID_LOG_LEVELS)
            raise ValueError(
                f"MNEMO_SERVER_LOG_LEVEL must be one of {valid_str}, got: {log_level_raw!r}"
            )

        max_upload_raw = os.environ.get("MNEMO_SERVER_MAX_UPLOAD_BYTES", "52428800")
        try:
            max_upload_bytes = int(max_upload_raw)
            if max_upload_bytes < 1:
                raise ValueError("must be positive")
        except ValueError as err:
            raise ValueError(
                f"MNEMO_SERVER_MAX_UPLOAD_BYTES must be a positive integer, got: {max_upload_raw!r}"
            ) from err

        auth_mode_raw = os.environ.get("MNEMO_SERVER_AUTH_MODE", "none").lower()
        if auth_mode_raw not in _VALID_AUTH_MODES:
            valid_auth = sorted(_VALID_AUTH_MODES)
            raise ValueError(
                f"MNEMO_SERVER_AUTH_MODE must be one of {valid_auth}, got: {auth_mode_raw!r}"
            )

        api_key = os.environ.get("MNEMO_SERVER_API_KEY")
        jwt_secret = os.environ.get("MNEMO_SERVER_JWT_SECRET")

        jwt_alg_raw = os.environ.get("MNEMO_SERVER_JWT_ALGORITHMS")
        if jwt_alg_raw is not None:
            jwt_algorithms = tuple(item.strip() for item in jwt_alg_raw.split(",") if item.strip())
        else:
            jwt_algorithms = ("HS256",)

        return cls(
            host=host,
            port=port,
            cors_origins=cors_origins,
            log_level=log_level_raw,  # type: ignore[arg-type]
            max_upload_bytes=max_upload_bytes,
            auth_mode=auth_mode_raw,  # type: ignore[arg-type]
            api_key=api_key,
            jwt_secret=jwt_secret,
            jwt_algorithms=jwt_algorithms,
        )
