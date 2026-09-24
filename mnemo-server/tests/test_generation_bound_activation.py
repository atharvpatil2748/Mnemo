"""Generation-bound activation never rewrites the historical signed state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from mnemo.interfaces import PrincipalContextV1
from mnemo_server.config import ServerConfig
from mnemo_server.services.durable_reranker_activation import (
    _activation_generation_for_restore,
)
from mnemo_server.services.v2_reranker_lifecycle import (
    DurableRerankerActivationStoreV1,
    V2RerankerMode,
)


def test_new_generation_is_separate_and_rejects_wrong_generation(tmp_path: Path) -> None:
    old_path = tmp_path / "historical" / "activation.json"
    old_store = DurableRerankerActivationStoreV1(
        path=old_path, signing_key=b"o" * 32, prohibited_paths=()
    )
    principal = PrincipalContextV1(actor_id=uuid4(), authenticated=True)
    old_store.commit(desired_mode=V2RerankerMode.PASS_THROUGH, principal=principal, evidence=None)
    old_bytes = old_path.read_bytes()
    old_sha = hashlib.sha256(old_bytes).hexdigest()

    new_id = uuid4()
    activation_id = uuid4()
    new_path = tmp_path / "new" / "activation.json"
    new_store = DurableRerankerActivationStoreV1(
        path=new_path,
        signing_key=b"n" * 32,
        prohibited_paths=(old_path,),
        credential_generation_id=new_id,
        activation_generation_id=activation_id,
    )
    new_store.commit(desired_mode=V2RerankerMode.PASS_THROUGH, principal=principal, evidence=None)
    assert new_store.load().credential_generation_id == new_id
    assert new_store.load().activation_generation_id == activation_id
    assert json.loads(new_path.read_text(encoding="utf-8"))["credential_generation_id"] == str(
        new_id
    )
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == old_sha
    assert old_path.read_bytes() == old_bytes

    assert (
        _activation_generation_for_restore(ServerConfig(credential_generation_id=new_id), new_path)
        == activation_id
    )
    assert _activation_generation_for_restore(ServerConfig(), new_path) is None
    with pytest.raises(RuntimeError, match="GENERATION_UNAVAILABLE"):
        _activation_generation_for_restore(ServerConfig(credential_generation_id=uuid4()), new_path)
    with pytest.raises(RuntimeError, match="GENERATION_UNAVAILABLE"):
        _activation_generation_for_restore(
            ServerConfig(credential_generation_id=new_id), tmp_path / "missing.json"
        )

    wrong_store = DurableRerankerActivationStoreV1(
        path=new_path,
        signing_key=b"n" * 32,
        prohibited_paths=(old_path,),
        credential_generation_id=uuid4(),
        activation_generation_id=activation_id,
    )
    with pytest.raises(RuntimeError, match="GENERATION_MISMATCH"):
        wrong_store.load()
    wrong_activation = DurableRerankerActivationStoreV1(
        path=new_path,
        signing_key=b"n" * 32,
        prohibited_paths=(),
        credential_generation_id=new_id,
        activation_generation_id=uuid4(),
    )
    with pytest.raises(RuntimeError, match="ACTIVATION_GENERATION_MISMATCH"):
        wrong_activation.load()
    with pytest.raises(RuntimeError, match="MALFORMED"):
        old_store_on_new_path = DurableRerankerActivationStoreV1(
            path=new_path, signing_key=b"n" * 32, prohibited_paths=()
        )
        old_store_on_new_path.load()
