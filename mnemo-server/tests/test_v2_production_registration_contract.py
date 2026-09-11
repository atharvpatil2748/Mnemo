"""Server ownership contract for future Full Multilingual V2 adapter registration."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

from mnemo.engine import KnowledgeEngine
from mnemo.phase85.v2_evaluation_runtime import (
    V2RuntimeCompositionDependencies,
    V2RuntimeIdentityV1,
)
from mnemo_server.services.authorization import CentralAuthorizationServiceV1
from mnemo_server.services.full_multilingual_v2_registration import (
    FullMultilingualV2ServerDependencyAssemblerV1,
    ServerOwnedFullMultilingualV2RegistrationV1,
)

DIGEST = "a" * 64


class _DeferredAssembler:
    def assemble_v2_runtime_dependencies(
        self,
        *,
        engine: KnowledgeEngine,
        authorization: CentralAuthorizationServiceV1,
    ) -> V2RuntimeCompositionDependencies:
        raise RuntimeError("five production adapters are deliberately not implemented")


def _identity() -> V2RuntimeIdentityV1:
    return V2RuntimeIdentityV1(
        profile_id="full-multilingual-v2",
        profile_fingerprint=DIGEST,
        vector_space_identity=DIGEST,
        build_run_id=uuid4(),
        database_identity=DIGEST,
        alias_set_digest=DIGEST,
        query_preprocessing_identity="query-v1",
        document_preprocessing_identity="document-v1",
        authorization_service_id="central-authorization-v1-plus-v2/1",
        provenance_validator_id="v2-provenance/1",
        reranker_public_protocol_id="v2-reranker/1",
        provider_identity="configured-provider/1",
    )


def test_server_owns_registration_without_implementing_the_deferred_adapters() -> None:
    assembler = _DeferredAssembler()
    assert isinstance(assembler, FullMultilingualV2ServerDependencyAssemblerV1)
    registration = ServerOwnedFullMultilingualV2RegistrationV1(
        engine=cast(KnowledgeEngine, object()),
        identity=_identity(),
        assembler=assembler,
    )
    assert registration.registration_id == "mnemo.server.full-multilingual-v2-registration/1"


def test_registration_rejects_an_untyped_or_evaluator_owned_assembler() -> None:
    try:
        ServerOwnedFullMultilingualV2RegistrationV1(
            engine=cast(KnowledgeEngine, object()),
            identity=_identity(),
            assembler=cast(FullMultilingualV2ServerDependencyAssemblerV1, object()),
        )
    except TypeError as exc:
        assert "governed server V2 registration port" in str(exc)
    else:
        raise AssertionError("untyped registration dependency was accepted")
