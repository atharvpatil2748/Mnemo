"""Focused centralized authorization and transport security invariants for WP-14."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mnemo.interfaces import NotFoundError, PrincipalContextV1
from mnemo_server.schemas.retrieval_v2 import EvidenceSearchRequest
from mnemo_server.services.authorization import (
    AuthorizationOperationV1,
    CentralAuthorizationServiceV1,
    principal_from_claims,
)


def test_server_owned_principal_is_deterministic_and_not_client_controlled() -> None:
    authenticated = principal_from_claims({"sub": "server-subject", "principal_id": "victim"})
    repeated = principal_from_claims({"sub": "server-subject"})
    forged_only = principal_from_claims({"principal_id": "victim", "actor_id": str(uuid4())})
    assert authenticated == repeated
    assert authenticated.authenticated is True
    assert forged_only.authenticated is False
    assert forged_only.actor_id != authenticated.actor_id


@pytest.mark.anyio
async def test_central_notebook_authorization_is_non_enumerating() -> None:
    notebook_id = uuid4()
    engine = MagicMock()
    engine.storage.get_notebook = AsyncMock(return_value=None)
    service = CentralAuthorizationServiceV1(engine)
    with pytest.raises(NotFoundError) as error:
        await service.authorize_notebook(
            PrincipalContextV1(uuid4(), True),
            notebook_id,
            AuthorizationOperationV1.RETRIEVE,
        )
    assert str(notebook_id) not in str(error.value)
    assert "authorized resource" in str(error.value)


def test_retrieval_security_scope_changes_canonical_cursor_fingerprint() -> None:
    notebook_id = uuid4()
    body = EvidenceSearchRequest.model_validate(
        {
            "query": "bounded evidence",
            "scope": {"notebook_id": str(notebook_id)},
            "mode": "ranked",
            "representations": ["canonical_text"],
            "candidate_budget": 5,
            "evidence_budget": 5,
        }
    )
    limits = {
        "max_candidate_budget": 10,
        "max_evidence_budget": 10,
        "max_response_bytes": 100_000,
        "max_content_characters": 10_000,
    }
    first = body.to_plan(**limits, security_scope_identity=str(uuid4()))
    second = body.to_plan(**limits, security_scope_identity=str(uuid4()))
    assert first.fingerprint != second.fingerprint
