"""Integration, contract, deduplication, and error tests for source endpoints."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mnemo import __version__
from mnemo.config import (
    EmbeddingConfig,
    LLMConfig,
    LLMRoleConfig,
    MnemoConfig,
    PluginConfig,
    RerankerConfig,
    StorageConfig,
)
from mnemo.engine import EngineState, KnowledgeEngine, _builtin_plugins
from mnemo.interfaces import (
    DependencyUnavailableError,
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingProviderV1,
    Page,
    StorageCapabilities,
    StorageError,
    TokenCounterInterfaceV1,
)
from mnemo.models import (
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
)
from mnemo.registry import PluginRegistry
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig


class MockTokenCounter(TokenCounterInterfaceV1):
    """Deterministic token counter mock for test execution."""

    @property
    def tokenizer_id(self) -> str:
        return "mock-tokenizer"

    def count(self, text: str) -> int:
        return len(text.split())


def _make_test_document(
    doc_id: UUID | None = None,
    version_id: UUID | None = None,
    content_hash: str = "a" * 64,
    status: DocumentStatus = DocumentStatus.INDEXED,
) -> Document:
    """Helper to construct a valid Document domain model for tests."""
    doc_id = doc_id or uuid4()
    version_id = version_id or uuid4()
    now = datetime.now(UTC)
    doc_version = DocumentVersion(
        version_id=version_id,
        document_id=doc_id,
        content_hash=content_hash,
        metadata=DocumentMetadata(content_hash=content_hash),
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    return Document(
        document_id=doc_id,
        versions=(doc_version,),
        current_version_id=version_id,
        current_hash=content_hash,
        status=status,
        created_at=now,
        updated_at=now,
    )


def _make_config() -> MnemoConfig:
    role = LLMRoleConfig(provider="test", model="model", max_context_tokens=128)
    return MnemoConfig(
        storage=StorageConfig(),
        llm=LLMConfig(
            planner=role,
            synthesizer=role,
            extractor=role,
            classifier=role,
        ),
        embedding=EmbeddingConfig(provider="test", model="embedding", dimensions=4),
        reranker=RerankerConfig(provider="test", model="reranker"),
        plugins=PluginConfig(directory=Path("./plugins")),
    )


def _make_mock_engine() -> MagicMock:
    """Create a mock KnowledgeEngine with real registry and mock storage/embedding."""
    mock_engine = MagicMock(spec=KnowledgeEngine)
    mock_engine.state = EngineState.READY
    mock_engine.initialize = AsyncMock()
    mock_engine.shutdown = AsyncMock()

    # Real registry with built-in parsers and chunkers
    registry = PluginRegistry(core_version=__version__)
    registry.load_plugins(_builtin_plugins(_make_config()))
    mock_engine.registry = registry

    # Embedding provider mock
    embedding_mock = MagicMock(spec=EmbeddingProviderV1)
    embedding_mock.capabilities.return_value = EmbeddingCapabilities(
        dimensions=4,
        supports_batch=True,
        max_batch=32,
        multilingual=False,
        supports_normalization=True,
    )
    embedding_mock.embed_batch = AsyncMock(
        side_effect=lambda texts: EmbeddingBatch(
            vectors=tuple((0.1, 0.2, 0.3, 0.4) for _ in texts),
            usage=MagicMock(),
        )
    )
    mock_engine.embedding_provider = embedding_mock

    # Storage mock
    storage_mock = MagicMock()
    storage_mock.capabilities.return_value = StorageCapabilities(
        supports_blobs=True,
        supports_dense_search=True,
        supports_sparse_search=True,
        supports_metadata=True,
        supports_graph=False,
        supports_transactions=True,
        supports_health_checks=True,
    )
    storage_mock.get_notebook = AsyncMock()
    storage_mock.get_document = AsyncMock()
    storage_mock.get_document_by_content_hash = AsyncMock()
    storage_mock.get_parsed_document = AsyncMock()
    storage_mock.put_asset = AsyncMock()
    storage_mock.put_parsed_document = AsyncMock()
    storage_mock.upsert_document = AsyncMock()
    storage_mock.upsert_chunks = AsyncMock()
    storage_mock.upsert_source = AsyncMock()
    storage_mock.get_source = AsyncMock()
    storage_mock.delete_source = AsyncMock()
    storage_mock.list_sources = AsyncMock()
    mock_engine.storage = storage_mock
    return mock_engine


@pytest.fixture
def mock_engine() -> MagicMock:
    return _make_mock_engine()


@pytest.fixture
def mock_token_counter() -> TokenCounterInterfaceV1:
    return MockTokenCounter()


@pytest.fixture
def test_notebook() -> Notebook:
    now = datetime.now(UTC)
    return Notebook(
        notebook_id=uuid4(),
        title="Research Notebook",
        description="A test workspace",
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({"tag": "test"}),
    )


@pytest.fixture
async def client(
    mock_engine: MagicMock,
    mock_token_counter: TokenCounterInterfaceV1,
) -> AsyncClient:
    """Create test client with injected mock engine and token counter."""
    server_config = ServerConfig(max_upload_bytes=1024 * 1024)  # 1MB limit for testing
    app = create_app(
        server_config=server_config,
        engine=mock_engine,
        provision_tokenizer_on_startup=False,
    )
    app.state.engine = mock_engine
    app.state.server_config = server_config
    app.state.token_counter = mock_token_counter
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# =============================================================================
# 1. Ingestion Endpoint Tests (POST /v1/notebooks/{id}/sources)
# =============================================================================


@pytest.mark.anyio
async def test_ingest_markdown_source_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Successfully ingest a new Markdown source file."""
    mock_engine.storage.get_notebook.return_value = test_notebook
    mock_engine.storage.get_document_by_content_hash.return_value = None
    mock_engine.storage.put_asset.return_value = MagicMock()
    mock_engine.storage.put_parsed_document = AsyncMock()
    mock_engine.storage.upsert_document = AsyncMock()
    mock_engine.storage.upsert_chunks = AsyncMock()
    mock_engine.storage.upsert_source = AsyncMock()

    md_content = b"# Document Title\n\nThis is a sample paragraph with valuable research data."
    files = {"file": ("research.md", md_content, "text/markdown")}

    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 201
    body = resp.json()
    assert body["notebook_id"] == str(test_notebook.notebook_id)
    assert body["filename"] == "research.md"
    assert body["mime_type"] == "text/markdown"
    assert body["status"] == "indexed"
    assert body["deduplicated"] is False
    assert "source_id" in body
    assert "document_id" in body

    # Verify storage calls
    mock_engine.storage.get_notebook.assert_awaited_once_with(test_notebook.notebook_id)
    assert mock_engine.storage.upsert_document.await_count == 2  # INDEXING, then INDEXED
    assert mock_engine.storage.upsert_chunks.await_count == 1
    assert mock_engine.storage.upsert_source.await_count == 1


@pytest.mark.anyio
async def test_ingest_plaintext_source_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Successfully ingest a plain text file."""
    mock_engine.storage.get_notebook.return_value = test_notebook
    mock_engine.storage.get_document_by_content_hash.return_value = None
    mock_engine.storage.put_asset.return_value = MagicMock()
    mock_engine.storage.put_parsed_document = AsyncMock()
    mock_engine.storage.upsert_document = AsyncMock()
    mock_engine.storage.upsert_chunks = AsyncMock()
    mock_engine.storage.upsert_source = AsyncMock()

    txt_content = b"Simple plain text notes for integration verification."
    files = {"file": ("notes.txt", txt_content, "text/plain")}

    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "notes.txt"
    assert body["status"] == "indexed"
    assert body["deduplicated"] is False


@pytest.mark.anyio
async def test_ingest_csv_source_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Successfully ingest a CSV data file."""
    mock_engine.storage.get_notebook.return_value = test_notebook
    mock_engine.storage.get_document_by_content_hash.return_value = None
    mock_engine.storage.put_asset.return_value = MagicMock()
    mock_engine.storage.put_parsed_document = AsyncMock()
    mock_engine.storage.upsert_document = AsyncMock()
    mock_engine.storage.upsert_chunks = AsyncMock()
    mock_engine.storage.upsert_source = AsyncMock()

    csv_content = b"name,role,department\nAlice,Engineer,Platform\nBob,Designer,Product\n"
    files = {"file": ("data.csv", csv_content, "text/csv")}

    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "data.csv"
    assert body["status"] == "indexed"


# =============================================================================
# 2. Validation & Security Tests
# =============================================================================


@pytest.mark.anyio
async def test_ingest_missing_notebook_returns_404(
    client: AsyncClient,
    mock_engine: MagicMock,
) -> None:
    """Ingestion fails with 404 when notebook does not exist."""
    missing_id = uuid4()
    mock_engine.storage.get_notebook.return_value = None

    files = {"file": ("doc.txt", b"Hello", "text/plain")}
    resp = await client.post(f"/v1/notebooks/{missing_id}/sources", files=files)

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_ingest_malformed_notebook_id_returns_422(
    client: AsyncClient,
) -> None:
    """Ingestion fails with 422 when notebook UUID is malformed."""
    files = {"file": ("doc.txt", b"Hello", "text/plain")}
    resp = await client.post("/v1/notebooks/not-a-uuid/sources", files=files)

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "http.validation"


@pytest.mark.anyio
async def test_ingest_empty_file_returns_422(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Empty 0-byte file returns 422 Unprocessable Entity."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    files = {"file": ("empty.txt", b"", "text/plain")}
    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "http.422"


@pytest.mark.anyio
async def test_ingest_oversized_upload_returns_413(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """File upload exceeding max_upload_bytes returns 413 Payload Too Large."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    # Server config in test fixture set max_upload_bytes to 1MB
    large_content = b"x" * (1024 * 1024 + 100)
    files = {"file": ("large.txt", large_content, "text/plain")}

    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 413
    body = resp.json()
    assert body["error"]["code"] == "http.413"
    assert body["error"]["retryable"] is False


@pytest.mark.anyio
async def test_ingest_unsupported_file_extension_returns_400(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Unsupported binary format returns 400 with contract.unsupported."""
    mock_engine.storage.get_notebook.return_value = test_notebook
    mock_engine.storage.get_document_by_content_hash.return_value = None

    files = {"file": ("program.exe", b"MZ\x90\x00BinaryData", "application/octet-stream")}
    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "contract.unsupported"


# =============================================================================
# 3. Deduplication Tests (Cases A, B, C)
# =============================================================================


@pytest.mark.anyio
async def test_deduplication_cross_notebook_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Case B: Existing document in another notebook reuses chunks with deduplicated=True."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    doc_id = uuid4()
    version_id = uuid4()
    content = b"Shared document content across workspaces."
    content_hash = hashlib.sha256(content).hexdigest()

    existing_doc = _make_test_document(
        doc_id=doc_id, version_id=version_id, content_hash=content_hash
    )
    mock_engine.storage.get_document_by_content_hash.return_value = existing_doc
    mock_engine.storage.list_sources.return_value = Page(items=(), next_cursor=None)

    parsed_doc = ParsedDocument(
        doc_type=DocType.GENERIC,
        blocks=(),
        metadata=DocumentMetadata(
            content_hash=content_hash,
            metadata=FrozenMetadata({"filename": "shared.txt", "size_bytes": len(content)}),
        ),
        language="en",
    )
    mock_engine.storage.get_parsed_document.return_value = parsed_doc
    mock_engine.storage.upsert_source = AsyncMock()

    files = {"file": ("shared.txt", content, "text/plain")}
    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 201
    body = resp.json()
    assert body["document_id"] == str(doc_id)
    assert body["deduplicated"] is True
    assert body["status"] == "indexed"

    # Chunking and embedding must NOT be called on deduplication hit
    assert mock_engine.storage.upsert_chunks.await_count == 0
    assert mock_engine.storage.upsert_source.await_count == 1


@pytest.mark.anyio
async def test_deduplication_intra_notebook_conflict_returns_409(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Case C: Re-uploading identical file to the same notebook returns 409 Conflict."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    doc_id = uuid4()
    version_id = uuid4()
    content = b"Duplicate file content in same notebook."
    content_hash = hashlib.sha256(content).hexdigest()

    existing_doc = _make_test_document(
        doc_id=doc_id, version_id=version_id, content_hash=content_hash
    )
    mock_engine.storage.get_document_by_content_hash.return_value = existing_doc

    existing_source = Source(
        source_id=uuid4(),
        notebook_id=test_notebook.notebook_id,
        document_id=doc_id,
        created_at=datetime.now(UTC),
    )
    mock_engine.storage.list_sources.return_value = Page(items=(existing_source,), next_cursor=None)

    files = {"file": ("duplicate.txt", content, "text/plain")}
    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "contract.conflict"


# =============================================================================
# 4. Source CRUD & Pagination Tests
# =============================================================================


@pytest.mark.anyio
async def test_list_sources_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """List sources returns paginated PageResponse[SourceResponse]."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    source_1 = Source(
        source_id=uuid4(),
        notebook_id=test_notebook.notebook_id,
        document_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    source_2 = Source(
        source_id=uuid4(),
        notebook_id=test_notebook.notebook_id,
        document_id=uuid4(),
        created_at=datetime.now(UTC),
    )

    mock_engine.storage.list_sources.return_value = Page(
        items=(source_1, source_2),
        next_cursor=str(source_2.source_id),
    )
    mock_engine.storage.get_document.return_value = _make_test_document(
        doc_id=source_1.document_id,
        content_hash="b" * 64,
    )
    mock_engine.storage.get_parsed_document.return_value = None

    resp = await client.get(f"/v1/notebooks/{test_notebook.notebook_id}/sources?limit=2")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["next_cursor"] == str(source_2.source_id)


@pytest.mark.anyio
async def test_get_source_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Retrieve single source details."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    source_id = uuid4()
    doc_id = uuid4()
    version_id = uuid4()
    source = Source(
        source_id=source_id,
        notebook_id=test_notebook.notebook_id,
        document_id=doc_id,
        created_at=datetime.now(UTC),
    )
    mock_engine.storage.get_source.return_value = source

    doc = _make_test_document(doc_id=doc_id, version_id=version_id, content_hash="c" * 64)
    mock_engine.storage.get_document.return_value = doc

    parsed_doc = ParsedDocument(
        doc_type=DocType.MARKDOWN,
        blocks=(),
        metadata=DocumentMetadata(
            content_hash="c" * 64,
            metadata=FrozenMetadata({"filename": "report.md", "size_bytes": 1024}),
        ),
        language="en",
    )
    mock_engine.storage.get_parsed_document.return_value = parsed_doc

    resp = await client.get(f"/v1/notebooks/{test_notebook.notebook_id}/sources/{source_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["source_id"] == str(source_id)
    assert body["filename"] == "report.md"
    assert body["doc_type"] == "markdown"
    assert body["size_bytes"] == 1024


@pytest.mark.anyio
async def test_delete_source_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Deleting a source returns 204 No Content."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    source_id = uuid4()
    source = Source(
        source_id=source_id,
        notebook_id=test_notebook.notebook_id,
        document_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    mock_engine.storage.get_source.return_value = source
    mock_engine.storage.delete_source.return_value = True

    resp = await client.delete(f"/v1/notebooks/{test_notebook.notebook_id}/sources/{source_id}")

    assert resp.status_code == 204
    mock_engine.storage.delete_source.assert_awaited_once_with(source_id)


@pytest.mark.anyio
async def test_get_source_status_success(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Get status polling endpoint returns persisted DocumentStatus."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    source_id = uuid4()
    doc_id = uuid4()
    source = Source(
        source_id=source_id,
        notebook_id=test_notebook.notebook_id,
        document_id=doc_id,
        created_at=datetime.now(UTC),
    )
    mock_engine.storage.get_source.return_value = source

    doc = _make_test_document(doc_id=doc_id, content_hash="d" * 64)
    mock_engine.storage.get_document.return_value = doc

    resp = await client.get(f"/v1/notebooks/{test_notebook.notebook_id}/sources/{source_id}/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["source_id"] == str(source_id)
    assert body["status"] == "indexed"
    assert body["error_message"] is None


# =============================================================================
# 5. Security & IDOR Isolation Tests
# =============================================================================


@pytest.mark.anyio
async def test_get_source_wrong_notebook_returns_404(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Attempting to access a source belonging to a different notebook returns 404."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    other_notebook_id = uuid4()
    source_id = uuid4()
    source = Source(
        source_id=source_id,
        notebook_id=other_notebook_id,  # Belonging to different notebook
        document_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    mock_engine.storage.get_source.return_value = source

    resp = await client.get(f"/v1/notebooks/{test_notebook.notebook_id}/sources/{source_id}")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "contract.not_found"


@pytest.mark.anyio
async def test_delete_source_wrong_notebook_returns_404(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Attempting to delete a source belonging to a different notebook returns 404."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    other_notebook_id = uuid4()
    source_id = uuid4()
    source = Source(
        source_id=source_id,
        notebook_id=other_notebook_id,
        document_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    mock_engine.storage.get_source.return_value = source

    resp = await client.delete(f"/v1/notebooks/{test_notebook.notebook_id}/sources/{source_id}")

    assert resp.status_code == 404
    assert mock_engine.storage.delete_source.await_count == 0


@pytest.mark.anyio
async def test_get_status_wrong_notebook_returns_404(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """Status polling returns 404 when notebook ID does not match source."""
    mock_engine.storage.get_notebook.return_value = test_notebook

    other_notebook_id = uuid4()
    source_id = uuid4()
    source = Source(
        source_id=source_id,
        notebook_id=other_notebook_id,
        document_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    mock_engine.storage.get_source.return_value = source

    resp = await client.get(f"/v1/notebooks/{test_notebook.notebook_id}/sources/{source_id}/status")

    assert resp.status_code == 404


# =============================================================================
# 6. Failure & Resilience Tests
# =============================================================================


@pytest.mark.anyio
async def test_ingest_embedding_failure_returns_503_and_sets_failed_status(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """When embedding fails, returns retryable 503 and transitions document to FAILED."""
    mock_engine.storage.get_notebook.return_value = test_notebook
    mock_engine.storage.get_document_by_content_hash.return_value = None
    mock_engine.storage.put_asset.return_value = MagicMock()
    mock_engine.storage.put_parsed_document = AsyncMock()
    mock_engine.storage.upsert_document = AsyncMock()

    # Make embedding provider fail
    mock_engine.embedding_provider.embed_batch.side_effect = DependencyUnavailableError(
        "Ollama service unavailable", retryable=True
    )

    files = {
        "file": (
            "test.md",
            (
                b"# Heading\n\nThis is a sufficiently long paragraph designed to exceed "
                b"the fifteen token threshold so that chunk filtering retains the generated leaf "
                b"chunk during dispatcher materialization."
            ),
            "text/markdown",
        )
    }
    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "contract.dependency_unavailable"
    assert body["error"]["retryable"] is True

    # Check that document was updated to FAILED state
    assert mock_engine.storage.upsert_document.await_count >= 2
    last_call_doc = mock_engine.storage.upsert_document.call_args_list[-1][0][0]
    assert last_call_doc.status == DocumentStatus.FAILED


@pytest.mark.anyio
async def test_ingest_storage_failure_returns_503(
    client: AsyncClient,
    mock_engine: MagicMock,
    test_notebook: Notebook,
) -> None:
    """When storage writes fail, returns retryable 503."""
    mock_engine.storage.get_notebook.return_value = test_notebook
    mock_engine.storage.get_document_by_content_hash.return_value = None
    mock_engine.storage.upsert_chunks.side_effect = StorageError("Disk I/O error", retryable=True)

    files = {"file": ("test.md", b"# Test", "text/markdown")}
    resp = await client.post(f"/v1/notebooks/{test_notebook.notebook_id}/sources", files=files)

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "contract.storage"
    assert body["error"]["retryable"] is True
