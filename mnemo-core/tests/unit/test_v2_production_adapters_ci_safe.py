from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mnemo.models.advanced_retrieval import PositionalScopeV2, RetrievalScopeV2
from mnemo.models.v2_evidence_resolution import V2GenerationSetBindingV1
from mnemo.models.v2_retrieval_authorization import (
    V2ActiveRuntimeBindingV1,
    V2RetrievalAuthorizationDecisionV1,
)
from mnemo.phase85.v2_database_identity import GovernedV2DatabaseIdentityVerifier
from mnemo.phase85.v2_evaluation_runtime import V2RuntimeIdentityV1
from mnemo.phase85.v2_production_adapters import (
    AuthorizedV2EvidenceResolver,
    AuthorizedV2SourceStorageEnumerator,
    GovernedActiveV2GenerationInspector,
    GovernedV2CandidateProjector,
)
from mnemo.phase85.v2_readiness import V2GenerationCapability
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore

from tests.v2_test_fixtures import create_synthetic_v2_db

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = (
    WORKSPACE_ROOT
    / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
    / "V2_DATABASE_ARTIFACT_IDENTITY.json"
)


def _setup_synthetic_store(
    tmp_path: Path,
) -> tuple[SQLiteV2ReadOnlyRuntimeStore, Path, GovernedV2DatabaseIdentityVerifier]:
    db_path = tmp_path / "synthetic_v2.db"
    create_synthetic_v2_db(db_path, MANIFEST)
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=WORKSPACE_ROOT,
        identity_manifest=MANIFEST,
    )
    store = SQLiteV2ReadOnlyRuntimeStore(db_path)
    return store, db_path, verifier


def _runtime_identity(verifier: GovernedV2DatabaseIdentityVerifier) -> V2RuntimeIdentityV1:
    artifact = verifier.artifact
    return V2RuntimeIdentityV1(
        profile_id="full_multilingual_v2_local_prebuild",
        profile_fingerprint=artifact.profile_fingerprint,
        vector_space_identity=artifact.vector_space_identity,
        build_run_id=artifact.build_run_id,
        database_identity=artifact.database_identity,
        alias_set_digest="b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0",
        query_preprocessing_identity="query-preprocessing",
        document_preprocessing_identity="document-preprocessing",
        authorization_service_id="central-v1-plus-v2",
        provenance_validator_id="v2-provenance-validator/1",
        reranker_public_protocol_id="multilingual-reranker/3",
        provider_identity="sentence-transformers",
    )


@pytest.mark.anyio
async def test_synthetic_store_lifecycle_and_lookup_operations(tmp_path: Path) -> None:
    store, db_path, _verifier = _setup_synthetic_store(tmp_path)
    await store.open()
    try:
        alias = await store.resolve_active_multilingual_v2_alias_digest()
        assert alias == "b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0"

        active = await store.resolve_active_multilingual_v2_generation_set()
        assert active is not None
        assert len(active) == 4

        # Read-only verification: trying to write to the store fails closed
        with (
            pytest.raises(sqlite3.OperationalError),
            sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro&immutable=1", uri=True) as conn,
        ):
            conn.execute("INSERT INTO notebooks VALUES ('x','x','x','x','x','{}')")

        # inspect_active_v2_generations error on invalid count
        with pytest.raises(Exception, match="ACTIVE_GENERATION_INVALID"):
            await store.inspect_active_v2_generations(active[:3])

        # inspect_active_v2_generations success
        inspected = await store.inspect_active_v2_generations(active)
        assert len(inspected) == 4
    finally:
        await store.close()


@pytest.mark.anyio
async def test_synthetic_generation_inspector_and_enumerator(tmp_path: Path) -> None:
    store, _db_path, verifier = _setup_synthetic_store(tmp_path)
    identity = _runtime_identity(verifier)
    await store.open()
    try:
        active = await store.resolve_active_multilingual_v2_generation_set()
        assert active is not None
        inspector = GovernedActiveV2GenerationInspector(
            store=store,
            verifier=verifier,
            identity=identity,
        )
        evidence = await inspector.inspect_active_v2_generations(active)
        assert len(evidence) == 4

        # Error branch: active generation mismatch
        with pytest.raises(RuntimeError, match="ACTIVE_GENERATION_MISMATCH"):
            await inspector.inspect_active_v2_generations(tuple(reversed(active)))

        # Error branch: build run ID mismatch
        mismatched_inspector = GovernedActiveV2GenerationInspector(
            store=store,
            verifier=verifier,
            identity=replace(identity, build_run_id=uuid4()),
        )
        with pytest.raises(RuntimeError, match="ACTIVE_GENERATION_DEPENDENCY_MISMATCH"):
            await mismatched_inspector.inspect_active_v2_generations(active)

        by_capability = {item.capability: item for item in evidence}
        generations = V2GenerationSetBindingV1(
            representation_generation_id=by_capability[
                V2GenerationCapability.REPRESENTATION_DERIVATION
            ].generation_id,
            language_text_generation_id=by_capability[
                V2GenerationCapability.LANGUAGE_TEXT
            ].generation_id,
            embedding_generation_id=by_capability[
                V2GenerationCapability.MULTILINGUAL_EMBEDDING
            ].generation_id,
            vector_generation_id=by_capability[
                V2GenerationCapability.MULTILINGUAL_VECTOR
            ].generation_id,
        )

        decision = V2RetrievalAuthorizationDecisionV1(
            decision_id=uuid4(),
            principal_actor_id=uuid4(),
            operation="retrieve",
            retrieval_scope=RetrievalScopeV2(
                notebook_id=UUID("df9c20cf-85fe-529c-902e-2e9e68193fbe")
            ),
            positional_scope=PositionalScopeV2(),
            runtime_binding=V2ActiveRuntimeBindingV1(
                alias_set_digest=identity.alias_set_digest,
                generation_ids=generations.ordered_ids,
                profile_fingerprint=identity.profile_fingerprint,
                vector_space_identity=identity.vector_space_identity,
                database_identity=identity.database_identity,
                build_run_id=identity.build_run_id,
                admission_policy_identity="test-admission/1",
            ),
            authorization_policy_identity="central-v1-plus-v2/1",
            authorization_policy_revision="1",
            request_fingerprint="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            issued_at="2026-09-02T00:00:00Z",
            required_provenance_evidence=("exact-semantic-evidence",),
        )

        enumerator = AuthorizedV2SourceStorageEnumerator(
            store=store,
            generations=generations,
            identity=identity,
            model_identity="BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181",
        )

        # Enumerate authorized evidence
        handles = await enumerator.enumerate_authorized_v2_evidence(
            decision=decision,
            generations=generations,
            limit=5,
        )
        assert isinstance(handles, tuple)
        assert len(handles) == 1

        resolver = AuthorizedV2EvidenceResolver(store=store)
        resolution = await resolver.resolve_v2_evidence(
            decision=decision,
            handle=handles[0],
        )
        assert resolution.semantic_text is not None
        assert resolution.runtime_security is not None

        projector = GovernedV2CandidateProjector(
            enumerator=enumerator,
            resolver=resolver,
            store=store,
        )
        candidate = await projector.project_authorized_v2_evidence(
            resolution=resolution,
        )
        assert candidate.semantic_text == resolution.semantic_text
        assert candidate.runtime_security == resolution.runtime_security

        # Error branch: wrong retrieval paths for candidate projection
        for paths in ((), ("dense", "dense")):
            with pytest.raises(ValueError, match="CANDIDATE_INVALID"):
                await projector.project_authorized_v2_evidence(
                    resolution=resolution,
                    retrieval_paths=paths,
                )

        # Resolve reranker evidence
        reranker_evidence = await projector.resolve_reranker_evidence(
            source=handles[0].source_reference,
            decision=decision,
            retrieval_paths=("sparse",),
            fusion_rank=2,
        )
        assert reranker_evidence.provenance.fusion_rank == 2

        # Error branch: wrong generations
        wrong_generations = replace(generations, vector_generation_id=uuid4())
        with pytest.raises(PermissionError, match="GENERATION_MISMATCH"):
            await enumerator.enumerate_authorized_v2_evidence(
                decision=decision,
                generations=wrong_generations,
                limit=1,
            )

        # Error branch: decision runtime mismatch
        wrong_decision = replace(
            decision,
            runtime_binding=replace(
                decision.runtime_binding,
                generation_ids=wrong_generations.ordered_ids,
            ),
        )
        with pytest.raises(PermissionError, match="AUTHORIZATION_RUNTIME_MISMATCH"):
            await enumerator.enumerate_authorized_v2_evidence(
                decision=wrong_decision,
                generations=generations,
                limit=1,
            )
    finally:
        await store.close()
