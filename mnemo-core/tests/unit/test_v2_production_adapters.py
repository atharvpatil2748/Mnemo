"""Read-only production-adapter verification against the governed V2 artifact."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mnemo.models.advanced_retrieval import PositionalScopeV2, RetrievalScopeV2
from mnemo.models.v2_evidence_resolution import (
    V2GenerationSetBindingV1,
    V2RepresentationResolutionState,
)
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

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = (
    ROOT
    / "docs/governance/proposals/phase8_5_full_multilingual_architecture"
    / "V2_DATABASE_ARTIFACT_IDENTITY.json"
)
ALIAS_DIGEST = "b3479aeaf423630abc48436ea3d23c7d37a7fdee637e53b5df86d08b972fe7c0"


def _identity(verifier: GovernedV2DatabaseIdentityVerifier) -> V2RuntimeIdentityV1:
    artifact = verifier.artifact
    return V2RuntimeIdentityV1(
        profile_id="full_multilingual_v2_local_prebuild",
        profile_fingerprint=artifact.profile_fingerprint,
        vector_space_identity=artifact.vector_space_identity,
        build_run_id=artifact.build_run_id,
        database_identity=artifact.database_identity,
        alias_set_digest=ALIAS_DIGEST,
        query_preprocessing_identity="governed-query-preprocessing",
        document_preprocessing_identity="governed-document-preprocessing",
        authorization_service_id="central-v1-plus-v2",
        provenance_validator_id="v2-provenance-validator/1",
        reranker_public_protocol_id="multilingual-reranker/3",
        provider_identity="sentence-transformers",
    )


def _notebook_id(target: Path) -> UUID:
    connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        row = connection.execute(
            "SELECT notebook_id FROM language_text_projection_rows_v2 ORDER BY row_id LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return UUID(str(row[0]))


def _require_production_database() -> None:
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=ROOT,
        identity_manifest=MANIFEST,
    )
    target = ROOT / verifier.artifact.target_path
    if not target.exists():
        pytest.skip("Governed V2 production database not present in environment")


async def _exercise() -> None:
    _require_production_database()
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=ROOT,
        identity_manifest=MANIFEST,
    )
    identity = _identity(verifier)
    target = ROOT / verifier.artifact.target_path
    before = target.read_bytes()
    store = SQLiteV2ReadOnlyRuntimeStore(target)
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
        with pytest.raises(RuntimeError, match="ACTIVE_GENERATION_MISMATCH"):
            await inspector.inspect_active_v2_generations(tuple(reversed(active)))
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
            retrieval_scope=RetrievalScopeV2(notebook_id=_notebook_id(target)),
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
        handles = await enumerator.enumerate_authorized_v2_evidence(
            decision=decision,
            generations=generations,
            limit=1,
        )
        assert len(handles) == 1
        wrong_generations = replace(generations, vector_generation_id=uuid4())
        with pytest.raises(PermissionError, match="GENERATION_MISMATCH"):
            await enumerator.enumerate_authorized_v2_evidence(
                decision=decision,
                generations=wrong_generations,
                limit=1,
            )
        with pytest.raises(PermissionError, match="EVIDENCE_UNAUTHORIZED"):
            await enumerator.resolve_handle(
                decision=decision,
                source=replace(handles[0].source_reference, source_id=uuid4()),
            )
        resolver = AuthorizedV2EvidenceResolver(store=store)
        resolution = await resolver.resolve_v2_evidence(
            decision=decision,
            handle=handles[0],
        )
        assert resolution.semantic_text.strip()
        assert resolution.runtime_security.database_identity == verifier.artifact.database_identity
        assert resolution.to_contract_payload()["semantic_text"] == resolution.semantic_text
        security = handles[0].runtime_security
        for changes, message in (
            ({"profile_id": ""}, "profile_id"),
            ({"model_identity": ""}, "model_identity"),
        ):
            with pytest.raises(ValueError, match=message):
                replace(security, **changes)
        with pytest.raises(ValueError, match="distinct"):
            replace(
                generations,
                vector_generation_id=generations.embedding_generation_id,
            )
        with pytest.raises(PermissionError, match="generation set"):
            replace(
                security,
                generations=replace(generations, vector_generation_id=uuid4()),
            )

        handle = handles[0]
        with pytest.raises(ValueError, match="representation/source mismatch"):
            replace(
                handle,
                source_reference=replace(handle.source_reference, source_id=uuid4()),
            )
        with pytest.raises(ValueError, match="outside the authorized runtime"):
            replace(handle, semantic_generation_id=uuid4())
        with pytest.raises(ValueError, match="language observation"):
            replace(handle, language_observation_references=(object(),))
        with pytest.raises(ValueError, match="script observation"):
            replace(handle, script_observation_references=(object(),))

        record = resolution.record
        for changes, message in (
            ({"semantic_text": " "}, "must not be empty"),
            ({"semantic_text": "title: only"}, "title-only"),
            ({"semantic_text_content_hash": "f" * 64}, "content hash mismatch"),
            ({"representation_observation_reference": uuid4()}, "observation identity"),
            ({"title_metadata": ""}, "title_metadata"),
            ({"title_metadata": record.semantic_text}, "title-only"),
            (
                {
                    "representation_state": V2RepresentationResolutionState.DERIVED,
                    "transformation_lineage": None,
                },
                "requires transformation lineage",
            ),
            ({"transformation_lineage": object()}, "cannot claim transformation lineage"),
        ):
            with pytest.raises(ValueError, match=message):
                replace(record, **changes)
        with pytest.raises(ValueError, match="provenance digest mismatch"):
            replace(resolution, provenance_digest="f" * 64)
        with pytest.raises(PermissionError, match="AUTHORIZATION_SCOPE_MISMATCH"):
            await resolver.resolve_v2_evidence(
                decision=replace(decision, request_fingerprint="b" * 64),
                handle=handles[0],
            )
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
        assert candidate.title_metadata is None
        for paths in ((), ("dense", "dense")):
            with pytest.raises(ValueError, match="CANDIDATE_INVALID"):
                await projector.project_authorized_v2_evidence(
                    resolution=resolution,
                    retrieval_paths=paths,
                )
        reranker_evidence = await projector.resolve_reranker_evidence(
            source=handles[0].source_reference,
            decision=decision,
            retrieval_paths=("sparse",),
            fusion_rank=2,
        )
        assert reranker_evidence.provenance.fusion_rank == 2
        with pytest.raises(PermissionError, match="AUTHORIZATION_RUNTIME_MISMATCH"):
            await enumerator.enumerate_authorized_multilingual_sources(
                decision=replace(
                    decision,
                    runtime_binding=replace(
                        decision.runtime_binding,
                        database_identity="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    ),
                ),
                limit=1,
            )
    finally:
        await store.close()
    assert target.read_bytes() == before


def test_real_production_adapters_preserve_governed_identity_read_only() -> None:
    asyncio.run(_exercise())


def test_manifest_vector_generation_names_distinct_embedding_source() -> None:
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    generations = {item["capability"]: item for item in raw["generations"]}
    vector = generations["multilingual_vector_v2"]
    embedding = generations["multilingual_embedding_v2"]
    assert vector["generation_id"] != embedding["generation_id"]
    assert vector["source_generation_ids"] == [embedding["generation_id"]]


async def _exercise_limit_boundary() -> None:
    _require_production_database()
    verifier = GovernedV2DatabaseIdentityVerifier(
        workspace_root=ROOT,
        identity_manifest=MANIFEST,
    )
    identity = _identity(verifier)
    target = ROOT / verifier.artifact.target_path
    before = target.read_bytes()
    store = SQLiteV2ReadOnlyRuntimeStore(target)
    await store.open()
    try:
        active = await store.resolve_active_multilingual_v2_generation_set()
        assert active is not None
        alias_digest_before = await store.resolve_active_multilingual_v2_alias_digest()
        assert alias_digest_before == ALIAS_DIGEST

        inspector = GovernedActiveV2GenerationInspector(
            store=store,
            verifier=verifier,
            identity=identity,
        )
        evidence = await inspector.inspect_active_v2_generations(active)
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
            retrieval_scope=RetrievalScopeV2(notebook_id=_notebook_id(target)),
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

        # 1. limit=10,000 remains accepted as normal maximum retrieval bound
        rows_10k = await store.list_authorized_v2_semantic_rows(
            decision=decision,
            generation_id=generations.language_text_generation_id,
            limit=10_000,
        )
        assert len(rows_10k) > 0

        # 2. limit=10,001 is accepted ONLY as the explicit governed overflow-detection probe
        rows_probe = await store.list_authorized_v2_semantic_rows(
            decision=decision,
            generation_id=generations.language_text_generation_id,
            limit=10_001,
        )
        assert len(rows_probe) == len(rows_10k)

        sources_probe = await enumerator.enumerate_authorized_multilingual_sources(
            decision=decision,
            limit=10_001,
        )
        assert len(sources_probe) > 0

        # 3. limit=10,002 is rejected (arbitrary larger limits strictly illegal)
        with pytest.raises(ValueError, match="authorized V2 semantic enumeration limit is invalid"):
            await store.list_authorized_v2_semantic_rows(
                decision=decision,
                generation_id=generations.language_text_generation_id,
                limit=10_002,
            )

        with pytest.raises(ValueError, match="authorized V2 semantic enumeration limit is invalid"):
            await enumerator.enumerate_authorized_multilingual_sources(
                decision=decision,
                limit=10_002,
            )

        # 4. negative/zero/invalid limits retain existing rejection behavior
        for invalid in (0, -1, -100):
            with pytest.raises(
                ValueError, match="authorized V2 semantic enumeration limit is invalid"
            ):
                await store.list_authorized_v2_semantic_rows(
                    decision=decision,
                    generation_id=generations.language_text_generation_id,
                    limit=invalid,
                )

        # 5. authorization is unchanged (unauthorized binding fails closed)
        with pytest.raises(PermissionError, match="AUTHORIZATION_RUNTIME_MISMATCH"):
            await enumerator.enumerate_authorized_multilingual_sources(
                decision=replace(
                    decision,
                    runtime_binding=replace(
                        decision.runtime_binding,
                        database_identity="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    ),
                ),
                limit=10_001,
            )

        # 6. semantic text resolution is unchanged
        resolver = AuthorizedV2EvidenceResolver(store=store)
        handles = await enumerator.enumerate_authorized_v2_evidence(
            decision=decision,
            generations=generations,
            limit=1,
        )
        resolution = await resolver.resolve_v2_evidence(decision=decision, handle=handles[0])
        assert resolution.semantic_text.strip()
        assert resolution.runtime_security.database_identity == verifier.artifact.database_identity

        # 7. no alias mutation occurred
        alias_digest_after = await store.resolve_active_multilingual_v2_alias_digest()
        assert alias_digest_after == alias_digest_before
    finally:
        await store.close()
    # 8. database remains strictly read-only (bit-for-bit unchanged)
    assert target.read_bytes() == before


def test_authorized_v2_semantic_enumeration_limit_boundary() -> None:
    asyncio.run(_exercise_limit_boundary())
