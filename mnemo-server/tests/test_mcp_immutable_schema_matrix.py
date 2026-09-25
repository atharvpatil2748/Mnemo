"""Public MCP protocol matrix over disposable old/new immutable chunk schemas."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import anyio
import pytest
from mcp.client.session import ClientSession
from mnemo.config import (
    EmbeddingConfig,
    LLMConfig,
    LLMRoleConfig,
    MnemoConfig,
    PluginConfig,
    RerankerConfig,
    StorageConfig,
)
from mnemo.engine import EngineState, KnowledgeEngine, _ResolvedProviders
from mnemo.interfaces import EmbeddingCapabilities, HealthStatus, PrincipalContextV1
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DocType,
    Document,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    Notebook,
    ParsedDocument,
    Source,
    TextBlock,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import (
    AdvancedRetrievalService,
    CanonicalTextAdvancedSource,
    ParentRetriever,
    RetrievalCursorCodec,
    SparseRetriever,
)
from mnemo.storage.sqlite import SQLiteStore
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore
from mnemo_server.config import ServerConfig
from mnemo_server.mcp.server import create_mcp_server


class _ParsedReadStore(SQLiteV2ReadOnlyRuntimeStore):
    """Only the parsed-block fixture is in memory; chunk/FTS reads are real SQLite."""

    parsed: dict[UUID, ParsedDocument]

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        return self.parsed.get(version_id)


class _Embedding:
    model_name = "fixture-embedding"
    dimensions = 2
    max_tokens = 512

    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(
            dimensions=2,
            supports_batch=True,
            max_batch=2,
            multilingual=False,
            supports_normalization=False,
        )

    async def embed(self, text: str) -> tuple[float, float]:
        return (float(len(text)), 1.0)

    async def embed_batch(self, texts: tuple[str, ...]):  # type: ignore[no-untyped-def]
        raise AssertionError("dense embedding is outside this sparse schema matrix")

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, component="fixture", checked_at=datetime.now(UTC))


class _EmptyDense:
    retrieval_mode = "dense"

    def capabilities(self):  # type: ignore[no-untyped-def]
        from mnemo.interfaces import RetrieverCapabilities

        return RetrieverCapabilities(
            supports_hybrid=False,
            supports_metadata_filters=True,
            supports_parent_child=False,
            supports_reranking=False,
        )

    async def retrieve(self, query, query_embedding, filters, top_k):  # type: ignore[no-untyped-def]
        return ()


class _FixturePlugin:
    name = "schema-matrix-retrieval"
    version = "1.0.0"
    core_version_range = ">=0.0.0"

    def __init__(self, store: SQLiteV2ReadOnlyRuntimeStore) -> None:
        self.store = store

    def capabilities(self) -> tuple[str, ...]:
        return ("retriever", "parent_promotion")

    def register(self, registry: PluginRegistry) -> None:
        registry.register_retriever("dense", _EmptyDense(), priority=0)
        registry.register_retriever("sparse", SparseRetriever(self.store), priority=0)
        registry.register_parent_promoter("default", ParentRetriever(self.store), priority=0)


async def _fixture(tmp_path: Path, *, legacy: bool):  # type: ignore[no-untyped-def]
    path = tmp_path / "matrix.db"
    writer = SQLiteStore(path)
    await writer.open()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    identities = []
    parsed: dict[UUID, ParsedDocument] = {}
    for index in range(2):
        notebook_id, document_id, version_id, source_id = (
            UUID(int=index * 10 + offset) for offset in range(1, 5)
        )
        text = f"schema evidence {index}"
        metadata = DocumentMetadata(content_hash=f"{index + 1:064x}", page_count=5)
        version = DocumentVersion(
            version_id=version_id,
            document_id=document_id,
            content_hash=metadata.content_hash,
            metadata=metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=now,
        )
        document = Document(
            document_id=document_id,
            versions=(version,),
            current_version_id=version_id,
            current_hash=metadata.content_hash,
            status=DocumentStatus.INDEXED,
            created_at=now,
            updated_at=now,
        )
        chunk = Chunk(
            id=f"{index + 1:064x}",
            document_id=document_id,
            version_id=version_id,
            text=text,
            chunk_type=ChunkType.PASSAGE,
            position=ChunkPosition(
                section_index=0,
                chunk_index_in_section=0,
                page_number=3,
                page_start=None if legacy else 3,
                page_end=None if legacy else 5,
            ),
            source_span=BlockSpan(start_ordinal=0, end_ordinal=0),
            heading_path=(),
            metadata=FrozenMetadata(),
        )
        await writer.upsert_notebook(
            Notebook(
                notebook_id=notebook_id, title=f"Fixture {index}", created_at=now, updated_at=now
            )
        )
        await writer.upsert_document(document)
        await writer.upsert_source(
            Source(
                source_id=source_id,
                notebook_id=notebook_id,
                document_id=document_id,
                created_at=now,
            )
        )
        await writer.upsert_chunks((chunk,))
        parsed[version_id] = ParsedDocument(
            blocks=(TextBlock(ordinal=0, text=text, page_number=3),),
            metadata=metadata,
            language="en",
            doc_type=DocType.GENERIC,
        )
        identities.append((notebook_id, document_id, version_id, source_id, chunk))
    await writer.close()
    if legacy:
        with sqlite3.connect(path) as db:
            db.execute("ALTER TABLE chunks DROP COLUMN position_page_start")
            db.execute("ALTER TABLE chunks DROP COLUMN position_page_end")
            db.commit()
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("PRAGMA journal_mode=DELETE")
    reader = _ParsedReadStore(path)
    reader.parsed = parsed
    await reader.open()
    role = LLMRoleConfig(provider="test", model="local", max_context_tokens=128)
    engine = KnowledgeEngine(
        MnemoConfig(
            storage=StorageConfig(),
            llm=LLMConfig(planner=role, synthesizer=role, extractor=role, classifier=role),
            embedding=EmbeddingConfig(provider="test", model="fixture", dimensions=2),
            reranker=RerankerConfig(provider="test", model="fixture"),
            plugins=PluginConfig(directory=tmp_path / "plugins"),
        ),
        certified_read_only=True,
    )
    registry = PluginRegistry(core_version=engine.version)
    registry.load_plugin(_FixturePlugin(reader))
    registry.freeze()
    engine._registry = registry
    engine._providers = _ResolvedProviders(
        storage=reader,
        embedding=_Embedding(),
        reranker=MagicMock(),
        planner=MagicMock(),
        synthesizer=MagicMock(),
        extractor=MagicMock(),
        classifier=MagicMock(),
        capabilities={},
    )
    engine._state = EngineState.READY
    engine._advanced_retrieval = AdvancedRetrievalService(
        sources=(
            CanonicalTextAdvancedSource(store=reader, ranked_retriever=SparseRetriever(reader)),
        ),
        cursor_codec=RetrievalCursorCodec(b"disposable-schema-matrix-cursor-secret"),
    )
    config = ServerConfig.model_validate(
        {
            "production_mode": True,
            "full_multilingual_v2_enabled": True,
            "full_multilingual_v2_model_cache": str(tmp_path),
            "final_qa_operational_store_path": str(tmp_path / "operational.db"),
            "mcp_stdio_principal_subject": "schema-matrix-operator",
            "auth_mode": "api-key",
            "api_key": "fixture-only-not-production",
            "delivery_cursor_secret": "disposable-schema-matrix-delivery-secret",
        }
    )
    return engine, reader, config, identities


def _body(result):  # type: ignore[no-untyped-def]
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_mcp_chunk_reader_matrix(tmp_path: Path, legacy: bool) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, source_id, chunk = identities[0]
    other_notebook, other_document, _, _, other_chunk = identities[1]
    server = create_mcp_server(
        engine,
        config=config,
        principal_provider=lambda: PrincipalContextV1(uuid4(), True),
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                listed = await client.list_tools()
                assert {tool.name for tool in listed.tools}.issuperset(
                    {
                        "query_notebook",
                        "search_all_notebooks",
                        "search_evidence",
                        "get_document",
                        "get_document_chunk",
                    }
                )
                search = _body(
                    await client.call_tool(
                        "search_all_notebooks",
                        {
                            "query": "schema",
                            "top_k": 2,
                            "notebook_id": str(notebook_id),
                        },
                    )
                )
                assert [hit["chunk_id"] for hit in search["results"]] == [chunk.id]
                hit = search["results"][0]
                assert (hit["document_id"], hit["version_id"], hit["notebook_id"]) == (
                    str(document_id),
                    str(version_id),
                    str(notebook_id),
                )
                assert hit["page_number"] == 3
                assert hit["page_start"] == (None if legacy else 3)
                assert hit["page_end"] == (None if legacy else 5)
                assert other_chunk.text not in json.dumps(search)
                global_search = _body(
                    await client.call_tool(
                        "search_all_notebooks",
                        {
                            "query": "schema",
                            "top_k": 2,
                        },
                    )
                )
                assert {hit["chunk_id"] for hit in global_search["results"]} == {
                    chunk.id,
                    other_chunk.id,
                }
                query = _body(
                    await client.call_tool(
                        "query_notebook",
                        {
                            "notebook_id": str(notebook_id),
                            "question": "schema",
                            "top_k": 2,
                            "synthesize": False,
                        },
                    )
                )
                assert {item["chunk_id"] for item in query["citations"]} == {chunk.id}
                assert query["citations"][0]["page"] == 3
                evidence = _body(
                    await client.call_tool(
                        "search_evidence",
                        {
                            "query": "schema",
                            "mode": "exhaustive",
                            "scope": {
                                "notebook_id": str(notebook_id),
                                "document_ids": [str(document_id)],
                            },
                            "representations": ["canonical_text"],
                            "evidence_budget": 2,
                        },
                    )
                )
                assert evidence["items"][0]["document_id"] == str(document_id)
                assert evidence["items"][0]["version_id"] == str(version_id)
                assert evidence["items"][0]["chunk_id"] == chunk.id
                locator = evidence["items"][0]["locator"]
                assert locator.get("page_start") == (None if legacy else 3)
                assert locator.get("page_end") == (None if legacy else 5)
                assert other_chunk.text not in json.dumps(evidence)
                ranked = _body(
                    await client.call_tool(
                        "search_evidence",
                        {
                            "query": "schema",
                            "mode": "ranked",
                            "scope": {"notebook_id": str(notebook_id)},
                            "representations": ["canonical_text"],
                            "evidence_budget": 2,
                        },
                    )
                )
                assert [item["chunk_id"] for item in ranked["items"]] == [chunk.id]
                assert other_chunk.text not in json.dumps(ranked)
                constrained = await client.call_tool(
                    "search_evidence",
                    {
                        "query": "schema",
                        "mode": "exhaustive",
                        "scope": {"notebook_id": str(notebook_id)},
                        "representations": ["canonical_text"],
                        "positional_scope": {"page_start": 3, "page_end": 5},
                        "evidence_budget": 2,
                    },
                )
                if legacy:
                    unavailable = _body(constrained)
                    assert unavailable["completeness"] == "partial"
                    assert unavailable["items"] == []
                    assert unavailable["omissions"] == [
                        "canonical_text:source_failure:UnsupportedError"
                    ]
                else:
                    assert _body(constrained)["items"][0]["chunk_id"] == chunk.id
                exact = _body(
                    await client.call_tool(
                        "get_document_chunk",
                        {
                            "notebook_id": str(notebook_id),
                            "document_id": str(document_id),
                            "version_id": str(version_id),
                            "chunk_id": chunk.id,
                        },
                    )
                )
                assert exact["items"][0]["payload"]["id"] == chunk.id
                assert exact["items"][0]["attribution"]["source_id"] == str(source_id)
                assert exact["items"][0]["payload"]["position"]["page_start"] == (
                    None if legacy else 3
                )
                document = _body(
                    await client.call_tool(
                        "get_document",
                        {
                            "notebook_id": str(notebook_id),
                            "document_id": str(document_id),
                            "version_id": str(version_id),
                            "mode": "blocks",
                            "selector": {"kind": "block_range", "start": 0, "end": 0},
                            "max_items": 1,
                        },
                    )
                )
                assert document["items"][0]["attribution"]["document_id"] == str(document_id)
                assert document["items"][0]["payload"]["text"] == chunk.text
                assert document["items"][0]["payload"]["exact_position"][
                    "overlapping_chunk_ids"
                ] == [chunk.id]
                bad = await client.call_tool(
                    "get_document_chunk",
                    {
                        "notebook_id": str(notebook_id),
                        "document_id": str(other_document),
                        "version_id": str(version_id),
                        "chunk_id": chunk.id,
                    },
                )
                assert bad.isError
                assert chunk.text not in str(bad.content)
                missing = await client.call_tool(
                    "get_document_chunk",
                    {
                        "notebook_id": str(notebook_id),
                        "document_id": str(document_id),
                        "version_id": str(version_id),
                        "chunk_id": "f" * 64,
                    },
                )
                assert missing.isError
                assert chunk.text not in str(missing.content)
                denied = await client.call_tool(
                    "search_all_notebooks",
                    {
                        "query": "schema",
                        "notebook_id": str(uuid4()),
                    },
                )
                assert denied.isError
                assert other_chunk.text not in str(denied.content)
                assert other_notebook != notebook_id
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()
