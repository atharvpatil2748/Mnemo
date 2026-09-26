"""Independent, disposable adversarial checks for the Stage 6 combined audit."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo.interfaces import ContractValidationError, PrincipalContextV1
from mnemo.interfaces.advanced_retrieval import AdvancedSourcePage
from mnemo.interfaces.errors import NotFoundError
from mnemo.models import FrozenMetadata
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    EvidenceRepresentation,
    RetrievalPathEvidenceV2,
    advanced_candidate_id,
)
from mnemo.retrieval import (
    AdvancedRetrievalService,
    PartitionedRetrievalServiceV1,
    RetrievalCursorCodec,
)
from mnemo_server.app import create_app
from mnemo_server.mcp.tools import execute_mcp_tool
from test_mcp_immutable_schema_matrix import _fixture


class _PrincipalOnlySource:
    """Model the governed ranked multilingual source's principal requirement."""

    representation = EvidenceRepresentation.MULTILINGUAL_TEXT

    def __init__(self, candidate: AdvancedRetrievalCandidate | None = None) -> None:
        self.authorized_calls = 0
        self.unauthorized_calls = 0
        self.candidate = candidate

    async def retrieve(self, plan, *, offset, limit):  # type: ignore[no-untyped-def]
        self.unauthorized_calls += 1
        raise PermissionError("governed source requires a trusted principal")

    async def retrieve_authorized(  # type: ignore[no-untyped-def]
        self, *, principal, plan, offset, limit
    ):
        assert principal.authenticated
        self.authorized_calls += 1
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity="a" * 64,
            candidates=() if self.candidate is None else (self.candidate,),
            examined=0 if self.candidate is None else 1,
            next_offset=None,
            exhausted=True,
        )

    async def expand(self, plan, seeds, *, limit):  # type: ignore[no-untyped-def]
        return ()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["older", "newer"])
async def test_partitioned_ranked_v2_keeps_principal_at_public_mcp_boundary(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, source_id, chunk = identities[0]
    candidate = AdvancedRetrievalCandidate(
        candidate_id=advanced_candidate_id(
            representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
            document_id=document_id,
            version_id=version_id,
            chunk_id=chunk.id,
            occurrence_id=None,
            derivation_id=None,
        ),
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        representation=EvidenceRepresentation.MULTILINGUAL_TEXT,
        chunk=chunk,
        occurrence_id=None,
        derivation_id=None,
        locator=FrozenMetadata(),
        document_title="Authorized fixture document",
        content=chunk.text,
        paths=(
            RetrievalPathEvidenceV2(
                path="fixture-governed-multilingual",
                source_rank=1,
                source_score=1.0,
            ),
        ),
    )
    source = _PrincipalOnlySource(candidate)
    retrieval = AdvancedRetrievalService(
        sources=(source,), cursor_codec=RetrievalCursorCodec(b"disposable-audit-cursor-secret-1234")
    )
    engine._advanced_retrieval = retrieval
    engine._partitioned_retrieval = PartitionedRetrievalServiceV1(retrieval)
    principal = PrincipalContextV1(uuid4(), True)
    try:
        common = {
            "query": "schema",
            "mode": "ranked",
            "scope": {"notebook_id": str(notebook_id)},
            "representations": ["multilingual_text"],
            "evidence_budget": 1,
        }
        normal = await execute_mcp_tool(
            engine, "search_evidence", common, server_config=config, principal=principal
        )
        normal_body = json.loads(normal[0].text)
        assert normal_body["coverage"]["representations"][0]["status"] == "searched"
        partitioned = await execute_mcp_tool(
            engine,
            "search_evidence",
            {**common, "partition_document_ids": [str(document_id)]},
            server_config=config,
            principal=principal,
        )
        body = json.loads(partitioned[0].text)
        assert body["partitions"][0]["coverage"]["representations"][0]["status"] == ("searched")
        assert body["items"][0]["document_id"] == str(document_id)
        assert body["items"][0]["representation"] == "multilingual_text"
        assert (
            body["partitions"][0]["items"][0]["source_metadata"]
            == (body["items"][0]["source_metadata"])
        )
        app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
        app.state.engine = engine
        app.state.server_config = config
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fixture",
            headers={"X-API-Key": "fixture-only-not-production"},
        ) as client:
            http = await client.post(
                "/v2/retrieval/evidence",
                json={**common, "partition_document_ids": [str(document_id)]},
            )
        assert http.status_code == 200, http.text
        assert http.json()["items"][0]["document_id"] == str(document_id)
        assert (
            http.json()["partitions"][0]["items"][0]["source_metadata"]
            == (body["items"][0]["source_metadata"])
        )
        assert source.unauthorized_calls == 0
        assert source.authorized_calls == 3
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["older", "newer"])
async def test_cross_notebook_partition_never_discloses_other_canonical_evidence(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id = identities[0][0]
    other_document_id = identities[1][1]
    other_chunk = identities[1][4]
    engine._partitioned_retrieval = PartitionedRetrievalServiceV1(engine.advanced_retrieval)
    try:
        with pytest.raises(NotFoundError) as failure:
            await execute_mcp_tool(
                engine,
                "search_evidence",
                {
                    "query": "schema",
                    "mode": "exhaustive",
                    "scope": {"notebook_id": str(notebook_id)},
                    "representations": ["canonical_text"],
                    "evidence_budget": 1,
                    "partition_document_ids": [str(other_document_id)],
                },
                server_config=config,
                principal=PrincipalContextV1(uuid4(), True),
            )
        assert str(failure.value) == "authorized resource was not found"
        assert other_chunk.text not in str(failure.value)
        assert other_chunk.id not in str(failure.value)
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["older", "newer"])
async def test_partitioned_evidence_enriches_both_public_item_views(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, source_id, chunk = identities[0]
    engine._partitioned_retrieval = PartitionedRetrievalServiceV1(engine.advanced_retrieval)
    try:
        result = await execute_mcp_tool(
            engine,
            "search_evidence",
            {
                "query": "schema",
                "mode": "ranked",
                "scope": {"notebook_id": str(notebook_id)},
                "representations": ["canonical_text"],
                "evidence_budget": 1,
                "partition_document_ids": [str(document_id)],
            },
            server_config=config,
            principal=PrincipalContextV1(uuid4(), True),
        )
        body = json.loads(result[0].text)
        item = body["items"][0]
        child = body["partitions"][0]["items"][0]
        assert (item["document_id"], item["version_id"], item["chunk_id"]) == (
            str(document_id),
            str(version_id),
            chunk.id,
        )
        assert item["source_metadata"]["source_id"] == str(source_id)
        assert child["source_metadata"] == item["source_metadata"]
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["older", "newer"])
async def test_explicit_partitions_fail_closed_before_governed_retrieval(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    source = _PrincipalOnlySource()
    retrieval = AdvancedRetrievalService(
        sources=(source,), cursor_codec=RetrievalCursorCodec(b"disposable-audit-cursor-secret-1234")
    )
    engine._advanced_retrieval = retrieval
    engine._partitioned_retrieval = PartitionedRetrievalServiceV1(retrieval)
    notebook_id, document_id, version_id, _, _ = identities[0]
    foreign_document_id = identities[1][1]
    common = {
        "query": "schema",
        "mode": "ranked",
        "scope": {"notebook_id": str(notebook_id)},
        "representations": ["multilingual_text"],
        "evidence_budget": 1,
    }

    async def request(ids: list[str], *, version: str | None = None) -> None:
        scope = {**common["scope"]}
        if version is not None:
            scope["version_ids"] = [version]
        await execute_mcp_tool(
            engine,
            "search_evidence",
            {**common, "scope": scope, "partition_document_ids": ids},
            server_config=config,
            principal=PrincipalContextV1(uuid4(), True),
        )

    try:
        for ids in (
            [str(foreign_document_id)],
            [str(uuid4())],
            [str(document_id), str(foreign_document_id)],
        ):
            with pytest.raises(NotFoundError) as failure:
                await request(ids)
            assert str(failure.value) == "authorized resource was not found"
        with pytest.raises(NotFoundError) as failure:
            await request([str(document_id)], version=str(uuid4()))
        assert str(failure.value) == "authorized resource was not found"
        with pytest.raises(NotFoundError) as failure:
            await execute_mcp_tool(
                engine,
                "search_evidence",
                {
                    **common,
                    "scope": {
                        "notebook_id": str(notebook_id),
                        "version_ids": [str(version_id), str(uuid4())],
                    },
                    "partition_document_ids": [str(document_id)],
                },
                server_config=config,
                principal=PrincipalContextV1(uuid4(), True),
            )
        assert str(failure.value) == "authorized resource was not found"
        with pytest.raises(ContractValidationError):
            await request([str(document_id), str(document_id)])
        assert source.authorized_calls == 0
        assert source.unauthorized_calls == 0
        await request([str(document_id)], version=str(version_id))
        assert source.authorized_calls == 1
        assert source.unauthorized_calls == 0
    finally:
        await reader.close()
