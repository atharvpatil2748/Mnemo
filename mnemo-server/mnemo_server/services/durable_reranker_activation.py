"""Production-owned durable BGE activation composition."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from mnemo_server.config import ServerConfig
from mnemo_server.services.authorization import principal_from_claims
from mnemo_server.services.full_multilingual_v2_startup import (
    InstalledFullMultilingualV2RuntimeV1,
)
from mnemo_server.services.v2_reranker_lifecycle import (
    DurableRerankerActivationAuthorityV1,
    DurableRerankerActivationStoreV1,
)


def _signing_key(config: ServerConfig) -> bytes:
    """Domain-separate the existing production server secret without persisting it."""
    return hmac.new(
        config.delivery_cursor_secret.encode("utf-8"),
        b"mnemo.v2-reranker-activation-state/1",
        hashlib.sha256,
    ).digest()


async def restore_production_reranker_activation(
    *,
    installed: InstalledFullMultilingualV2RuntimeV1,
    config: ServerConfig,
    workspace_root: Path,
    production_store_path: Path,
) -> DurableRerankerActivationAuthorityV1 | None:
    """Restore configured signed state after V2 exposure and before serving requests."""
    configured_path = config.reranker_activation_state_path
    operator_subject = config.reranker_activation_operator_subject
    if configured_path is None and operator_subject is None:
        return None
    if configured_path is None or operator_subject is None:
        raise RuntimeError("DURABLE_BGE_ACTIVATION_CONFIGURATION_INCOMPLETE")
    state_path = (
        configured_path.resolve()
        if configured_path.is_absolute()
        else (workspace_root / configured_path).resolve()
    )
    operator = principal_from_claims({"sub": operator_subject})
    if not operator.authenticated:
        raise PermissionError("durable reranker activation operator is not authenticated")
    store = DurableRerankerActivationStoreV1(
        path=state_path,
        signing_key=_signing_key(config),
        prohibited_paths=(
            production_store_path,
            *(
                (config.final_qa_operational_store_path,)
                if config.final_qa_operational_store_path is not None
                else ()
            ),
        ),
    )
    authority = DurableRerankerActivationAuthorityV1(
        runtime_authority=installed.reranker_activation,
        router=installed.reranker,
        store=store,
        authorized_operator_actor_id=operator.actor_id,
    )
    await authority.restore()
    installed.durable_reranker_activation = authority
    return authority
