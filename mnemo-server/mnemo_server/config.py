"""Server-level transport and process configuration for mnemo-server."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    max_delivery_document_bytes: int = Field(default=4_194_304, ge=1)
    max_delivery_asset_bytes: int = Field(default=8_388_608, ge=1)
    max_delivery_assets: int = Field(default=32, ge=1, le=1000)
    max_delivery_response_bytes: int = Field(default=8_388_608, ge=1)
    max_advanced_candidate_budget: int = Field(default=1000, ge=1, le=1000)
    production_rerank_candidate_limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Governed number of fused candidates entering production reranking.",
    )
    max_advanced_evidence_budget: int = Field(default=200, ge=1, le=200)
    max_advanced_response_bytes: int = Field(default=1_000_000, ge=256, le=10_000_000)
    max_advanced_content_characters: int = Field(default=200_000, ge=1, le=2_000_000)
    max_advanced_elapsed_milliseconds: int = Field(default=30_000, ge=1, le=60_000)
    max_structured_rows_scanned: int = Field(default=50_000, ge=1, le=99_999)
    max_structured_rows_returned: int = Field(default=1_000, ge=1, le=10_000)
    max_structured_groups: int = Field(default=1_000, ge=1, le=50_000)
    max_structured_fields: int = Field(default=64, ge=1, le=256)
    max_structured_evidence: int = Field(default=5_000, ge=1, le=100_000)
    max_structured_response_bytes: int = Field(default=2_000_000, ge=256, le=20_000_000)
    max_structured_elapsed_milliseconds: int = Field(default=5_000, ge=1, le=60_000)
    max_structured_page_size: int = Field(default=500, ge=1, le=1_000)
    delivery_cursor_secret: str = Field(default="mnemo-local-delivery-v1", min_length=16)
    delivery_cursor_key_id: str = Field(default="delivery-v2", min_length=1, max_length=64)
    delivery_cursor_ttl_seconds: int = Field(default=900, ge=1, le=86_400)
    delivery_cursor_rotation_keys: tuple[tuple[str, str], ...] = ()
    delivery_cursor_legacy_v1_overlap_seconds: int = Field(default=900, ge=0, le=86_400)
    delivery_cursor_legacy_v1_accept_until: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=15)
    )
    production_mode: bool = Field(
        default=False,
        description="Enable fail-closed production configuration validation.",
    )
    full_multilingual_v2_enabled: bool = False
    full_multilingual_v2_reranker_mode: Literal["PASS_THROUGH", "BGE_V2_M3"] = "PASS_THROUGH"
    full_multilingual_v2_model_cache: Path | None = None
    reranker_activation_state_path: Path | None = Field(
        default=None,
        description="Dedicated mutable state file for governed restart-safe reranker activation.",
    )
    reranker_activation_operator_subject: str | None = Field(
        default=None,
        description="Server-owned subject authorized to change durable reranker state.",
    )
    final_qa_operational_store_path: Path | None = None
    mcp_stdio_principal_subject: str | None = Field(
        default=None,
        description="Server-owned authenticated subject for the trusted local MCP stdio process.",
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

    @model_validator(mode="after")
    def _secure_cursor_configuration(self) -> ServerConfig:
        if (self.production_mode or self.auth_mode != "none") and (
            self.delivery_cursor_secret == "mnemo-local-delivery-v1"
            or len(self.delivery_cursor_secret.encode("utf-8")) < 32
        ):
            raise ValueError(
                "authenticated/production cursor signing secret must be unique "
                "and at least 32 bytes"
            )
        key_ids = [
            self.delivery_cursor_key_id,
            *(key for key, _ in self.delivery_cursor_rotation_keys),
        ]
        if len(key_ids) != len(set(key_ids)):
            raise ValueError("cursor signing key IDs must be unique")
        if any(
            len(secret.encode("utf-8")) < 32 for _, secret in self.delivery_cursor_rotation_keys
        ):
            raise ValueError("cursor rotation secrets must contain at least 32 bytes")
        if self.full_multilingual_v2_enabled:
            if not self.production_mode or self.auth_mode == "none":
                raise ValueError(
                    "Full Multilingual V2 exposure requires authenticated production mode"
                )
            if self.full_multilingual_v2_model_cache is None:
                raise ValueError("Full Multilingual V2 requires an explicit local model cache")
            if self.final_qa_operational_store_path is None:
                raise ValueError(
                    "Full Multilingual V2 requires a separate Final-QA operational store"
                )
            if not self.mcp_stdio_principal_subject or not self.mcp_stdio_principal_subject.strip():
                raise ValueError(
                    "Full Multilingual V2 requires an explicit MCP stdio principal subject"
                )
        if (
            self.full_multilingual_v2_reranker_mode == "BGE_V2_M3"
            and not self.full_multilingual_v2_enabled
        ):
            raise ValueError("BGE V2 reranker mode requires exposed Full Multilingual V2")
        durable_fields = (
            self.reranker_activation_state_path,
            self.reranker_activation_operator_subject,
        )
        if any(value is not None for value in durable_fields) and not all(
            value is not None for value in durable_fields
        ):
            raise ValueError(
                "durable reranker activation requires both a state path and operator subject"
            )
        if (
            self.reranker_activation_state_path is not None
            and not self.full_multilingual_v2_enabled
        ):
            raise ValueError("durable reranker activation requires exposed Full Multilingual V2")
        return self

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

        def _positive_env(name: str, default: int) -> int:
            raw = os.environ.get(name, str(default))
            try:
                value = int(raw)
            except ValueError as err:
                raise ValueError(f"{name} must be a positive integer, got: {raw!r}") from err
            if value < 1:
                raise ValueError(f"{name} must be a positive integer, got: {raw!r}")
            return value

        auth_mode_raw = os.environ.get("MNEMO_SERVER_AUTH_MODE", "none").lower()
        if auth_mode_raw not in _VALID_AUTH_MODES:
            valid_auth = sorted(_VALID_AUTH_MODES)
            raise ValueError(
                f"MNEMO_SERVER_AUTH_MODE must be one of {valid_auth}, got: {auth_mode_raw!r}"
            )

        api_key = os.environ.get("MNEMO_SERVER_API_KEY")
        jwt_secret = os.environ.get("MNEMO_SERVER_JWT_SECRET")

        rotation_raw = os.environ.get("MNEMO_SERVER_DELIVERY_CURSOR_ROTATION_KEYS", "{}")
        try:
            rotation_value = json.loads(rotation_raw)
        except json.JSONDecodeError as err:
            raise ValueError(
                "MNEMO_SERVER_DELIVERY_CURSOR_ROTATION_KEYS must be a JSON object"
            ) from err
        if not isinstance(rotation_value, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in rotation_value.items()
        ):
            raise ValueError("MNEMO_SERVER_DELIVERY_CURSOR_ROTATION_KEYS must be a JSON object")

        jwt_alg_raw = os.environ.get("MNEMO_SERVER_JWT_ALGORITHMS")
        if jwt_alg_raw is not None:
            jwt_algorithms = tuple(item.strip() for item in jwt_alg_raw.split(",") if item.strip())
        else:
            jwt_algorithms = ("HS256",)

        legacy_overlap = int(
            os.environ.get("MNEMO_SERVER_DELIVERY_CURSOR_LEGACY_V1_OVERLAP_SECONDS", "900")
        )
        if legacy_overlap < 0:
            raise ValueError(
                "MNEMO_SERVER_DELIVERY_CURSOR_LEGACY_V1_OVERLAP_SECONDS must be non-negative"
            )

        return cls(
            host=host,
            port=port,
            cors_origins=cors_origins,
            log_level=log_level_raw,  # type: ignore[arg-type]
            max_upload_bytes=max_upload_bytes,
            max_delivery_document_bytes=_positive_env(
                "MNEMO_SERVER_MAX_DELIVERY_DOCUMENT_BYTES", 4_194_304
            ),
            max_delivery_asset_bytes=_positive_env(
                "MNEMO_SERVER_MAX_DELIVERY_ASSET_BYTES", 8_388_608
            ),
            max_delivery_assets=_positive_env("MNEMO_SERVER_MAX_DELIVERY_ASSETS", 32),
            max_delivery_response_bytes=_positive_env(
                "MNEMO_SERVER_MAX_DELIVERY_RESPONSE_BYTES", 8_388_608
            ),
            max_advanced_candidate_budget=_positive_env(
                "MNEMO_SERVER_MAX_ADVANCED_CANDIDATE_BUDGET", 1000
            ),
            production_rerank_candidate_limit=_positive_env(
                "MNEMO_SERVER_PRODUCTION_RERANK_CANDIDATE_LIMIT", 50
            ),
            max_advanced_evidence_budget=_positive_env(
                "MNEMO_SERVER_MAX_ADVANCED_EVIDENCE_BUDGET", 200
            ),
            max_advanced_response_bytes=_positive_env(
                "MNEMO_SERVER_MAX_ADVANCED_RESPONSE_BYTES", 1_000_000
            ),
            max_advanced_content_characters=_positive_env(
                "MNEMO_SERVER_MAX_ADVANCED_CONTENT_CHARACTERS", 200_000
            ),
            max_advanced_elapsed_milliseconds=_positive_env(
                "MNEMO_SERVER_MAX_ADVANCED_ELAPSED_MILLISECONDS", 30_000
            ),
            max_structured_rows_scanned=_positive_env(
                "MNEMO_SERVER_MAX_STRUCTURED_ROWS_SCANNED", 50_000
            ),
            max_structured_rows_returned=_positive_env(
                "MNEMO_SERVER_MAX_STRUCTURED_ROWS_RETURNED", 1_000
            ),
            max_structured_groups=_positive_env("MNEMO_SERVER_MAX_STRUCTURED_GROUPS", 1_000),
            max_structured_fields=_positive_env("MNEMO_SERVER_MAX_STRUCTURED_FIELDS", 64),
            max_structured_evidence=_positive_env("MNEMO_SERVER_MAX_STRUCTURED_EVIDENCE", 5_000),
            max_structured_response_bytes=_positive_env(
                "MNEMO_SERVER_MAX_STRUCTURED_RESPONSE_BYTES", 2_000_000
            ),
            max_structured_elapsed_milliseconds=_positive_env(
                "MNEMO_SERVER_MAX_STRUCTURED_ELAPSED_MILLISECONDS", 5_000
            ),
            max_structured_page_size=_positive_env("MNEMO_SERVER_MAX_STRUCTURED_PAGE_SIZE", 500),
            delivery_cursor_secret=os.environ.get(
                "MNEMO_SERVER_DELIVERY_CURSOR_SECRET", "mnemo-local-delivery-v1"
            ),
            delivery_cursor_key_id=os.environ.get(
                "MNEMO_SERVER_DELIVERY_CURSOR_KEY_ID", "delivery-v2"
            ),
            delivery_cursor_ttl_seconds=_positive_env(
                "MNEMO_SERVER_DELIVERY_CURSOR_TTL_SECONDS", 900
            ),
            delivery_cursor_rotation_keys=tuple(rotation_value.items()),
            delivery_cursor_legacy_v1_overlap_seconds=legacy_overlap,
            delivery_cursor_legacy_v1_accept_until=datetime.now(UTC)
            + timedelta(seconds=legacy_overlap),
            production_mode=os.environ.get("MNEMO_SERVER_PRODUCTION_MODE", "false").lower()
            in {"1", "true", "yes"},
            full_multilingual_v2_enabled=os.environ.get(
                "MNEMO_SERVER_FULL_MULTILINGUAL_V2_ENABLED", "false"
            ).lower()
            in {"1", "true", "yes"},
            full_multilingual_v2_reranker_mode=os.environ.get(
                "MNEMO_SERVER_FULL_MULTILINGUAL_V2_RERANKER_MODE", "PASS_THROUGH"
            ),  # type: ignore[arg-type]
            full_multilingual_v2_model_cache=(
                Path(value)
                if (value := os.environ.get("MNEMO_SERVER_FULL_MULTILINGUAL_V2_MODEL_CACHE"))
                else None
            ),
            reranker_activation_state_path=(
                Path(value)
                if (value := os.environ.get("MNEMO_SERVER_RERANKER_ACTIVATION_STATE_PATH"))
                else None
            ),
            reranker_activation_operator_subject=os.environ.get(
                "MNEMO_SERVER_RERANKER_ACTIVATION_OPERATOR_SUBJECT"
            ),
            final_qa_operational_store_path=(
                Path(value)
                if (value := os.environ.get("MNEMO_SERVER_FINAL_QA_OPERATIONAL_STORE_PATH"))
                else None
            ),
            mcp_stdio_principal_subject=os.environ.get("MNEMO_SERVER_MCP_STDIO_PRINCIPAL_SUBJECT"),
            auth_mode=auth_mode_raw,  # type: ignore[arg-type]
            api_key=api_key,
            jwt_secret=jwt_secret,
            jwt_algorithms=jwt_algorithms,
        )
