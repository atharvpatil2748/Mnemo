"""Ingestion orchestration service coordinating frozen core primitives."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from mnemo.chunkers import ChunkerDispatcher
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.embeddings import EmbedderModule
from mnemo.engine import KnowledgeEngine
from mnemo.ingestion import DocumentCanonicalizer, IngestionPipeline
from mnemo.interfaces import (
    ChunkingContext,
    ChunkingOptions,
    ConflictError,
    MnemoInterfaceError,
    NotFoundError,
    TokenCounterInterfaceV1,
)
from mnemo.models import (
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    Source,
)
from mnemo.parsers import ParserRouter

from mnemo_server.schemas.common import PageResponse
from mnemo_server.schemas.sources import SourceResponse, SourceStatusResponse


class IngestionService:
    """Coordinates parsing, chunking, embedding, indexing, and source association."""

    def __init__(
        self,
        engine: KnowledgeEngine,
        token_counter: TokenCounterInterfaceV1,
    ) -> None:
        self._engine = engine
        self._token_counter = token_counter

    async def ingest_source(
        self,
        *,
        notebook_id: UUID,
        filename: str,
        data: bytes,
    ) -> SourceResponse:
        """Ingest raw file bytes into a notebook, reusing existing documents when possible.

        Args:
            notebook_id: Owning notebook UUID.
            filename: Original filename.
            data: Raw file byte content.

        Returns:
            SourceResponse containing the linked source metadata.

        Raises:
            NotFoundError: If the notebook does not exist.
            ConflictError: If the document is already linked to this notebook.
            UnsupportedError: If the file format cannot be parsed.
            StorageError: If a database or vector write fails.
            DependencyUnavailableError: If the embedding model is offline.
        """
        # 1. Validate notebook existence
        notebook = await self._engine.storage.get_notebook(notebook_id)
        if notebook is None:
            raise NotFoundError(f"Notebook {notebook_id} was not found")

        # 2. Content hash calculation
        content_hash = hashlib.sha256(data).hexdigest()

        # 3. Document-level deduplication check
        existing_doc = await self._engine.storage.get_document_by_content_hash(content_hash)
        if existing_doc is not None:
            # Check for intra-notebook duplicate
            existing_source = await self._find_source_in_notebook(
                notebook_id, existing_doc.document_id
            )
            if existing_source is not None:
                raise ConflictError(
                    f"Document with hash {content_hash} is already associated with "
                    f"notebook {notebook_id}"
                )

            # Cross-notebook deduplication: reuse document and chunks, create new Source
            source_id = uuid4()
            now = datetime.now(UTC)
            source = Source(
                source_id=source_id,
                notebook_id=notebook_id,
                document_id=existing_doc.document_id,
                created_at=now,
            )
            await self._engine.storage.upsert_source(source)

            parsed_doc = await self._engine.storage.get_parsed_document(
                existing_doc.current_version_id
            )
            doc_type = parsed_doc.doc_type.value if parsed_doc is not None else "generic"
            guessed_mime, _ = mimetypes.guess_type(filename)
            mime_type = guessed_mime or "application/octet-stream"
            metadata: dict[str, Any] = (
                dict(parsed_doc.metadata.metadata) if parsed_doc is not None else {}
            )

            return SourceResponse(
                source_id=source.source_id,
                notebook_id=source.notebook_id,
                document_id=source.document_id,
                filename=filename,
                content_hash=content_hash,
                mime_type=mime_type,
                size_bytes=len(data),
                doc_type=doc_type,
                status=existing_doc.status.value,
                deduplicated=True,
                created_at=source.created_at,
                metadata=metadata,
            )

        # 4. New document ingestion path
        document_id = uuid5(NAMESPACE_URL, f"mnemo-document:{content_hash}")
        version_id = uuid5(NAMESPACE_URL, f"mnemo-version:{content_hash}")
        now = datetime.now(UTC)

        router = ParserRouter(self._engine.registry, self._engine.storage)
        cleaner = DocumentCleaner()
        classifier = DocumentClassifier()
        canonicalizer = DocumentCanonicalizer()
        pipeline = IngestionPipeline(
            router=router,
            storage=self._engine.storage,
            cleaner=cleaner,
            classifier=classifier,
            canonicalizer=canonicalizer,
        )

        parsed_doc = await pipeline.ingest(data, filename, version_id)

        # Create initial Document record in INDEXING state
        doc_version = DocumentVersion(
            version_id=version_id,
            document_id=document_id,
            content_hash=content_hash,
            metadata=parsed_doc.metadata,
            status=DocumentVersionStatus.CURRENT,
            created_at=now,
        )
        doc = Document(
            document_id=document_id,
            versions=(doc_version,),
            current_version_id=version_id,
            current_hash=content_hash,
            status=DocumentStatus.INDEXING,
            created_at=now,
            updated_at=now,
        )
        await self._engine.storage.upsert_document(doc)

        try:
            # Chunking
            chunking_context = ChunkingContext(
                document_version=doc_version,
                options=ChunkingOptions(target_tokens=512, max_tokens=1024, overlap_tokens=64),
            )
            dispatcher = ChunkerDispatcher(self._engine.registry, self._token_counter)
            chunks = dispatcher.dispatch(parsed_doc, chunking_context)

            # Embedding
            embedder = EmbedderModule(self._engine.embedding_provider)
            embedded_chunks = await embedder.embed_chunks(chunks)

            # Index chunks in SQLite and Qdrant
            await self._engine.storage.upsert_chunks(embedded_chunks)

            # Update Document status to INDEXED
            indexed_doc = replace(doc, status=DocumentStatus.INDEXED, updated_at=datetime.now(UTC))
            await self._engine.storage.upsert_document(indexed_doc)

            # Create Source association
            source_id = uuid4()
            source = Source(
                source_id=source_id,
                notebook_id=notebook_id,
                document_id=document_id,
                created_at=datetime.now(UTC),
            )
            await self._engine.storage.upsert_source(source)

            metadata = dict(parsed_doc.metadata.metadata)
            guessed_mime, _ = mimetypes.guess_type(filename)
            mime_type = guessed_mime or "application/octet-stream"

            return SourceResponse(
                source_id=source.source_id,
                notebook_id=source.notebook_id,
                document_id=source.document_id,
                filename=filename,
                content_hash=content_hash,
                mime_type=mime_type,
                size_bytes=len(data),
                doc_type=parsed_doc.doc_type.value,
                status=DocumentStatus.INDEXED.value,
                deduplicated=False,
                created_at=source.created_at,
                metadata=metadata,
            )
        except BaseExceptionGroup as eg:
            # Transition document status to FAILED on indexing failure
            try:
                failed_doc = replace(
                    doc, status=DocumentStatus.FAILED, updated_at=datetime.now(UTC)
                )
                await self._engine.storage.upsert_document(failed_doc)
            except Exception:
                pass
            for sub_exc in eg.exceptions:
                if isinstance(sub_exc, MnemoInterfaceError):
                    raise sub_exc from eg
            raise
        except Exception:
            # Transition document status to FAILED on indexing failure
            try:
                failed_doc = replace(
                    doc, status=DocumentStatus.FAILED, updated_at=datetime.now(UTC)
                )
                await self._engine.storage.upsert_document(failed_doc)
            except Exception:
                pass
            raise

    async def list_sources(
        self,
        *,
        notebook_id: UUID,
        limit: int = 50,
        cursor: str | None = None,
    ) -> PageResponse[SourceResponse]:
        """List all sources in a notebook using keyset cursor pagination."""
        notebook = await self._engine.storage.get_notebook(notebook_id)
        if notebook is None:
            raise NotFoundError(f"Notebook {notebook_id} was not found")

        page = await self._engine.storage.list_sources(
            notebook_id=notebook_id,
            limit=limit,
            cursor=cursor,
        )

        items: list[SourceResponse] = []
        for source in page.items:
            doc = await self._engine.storage.get_document(source.document_id)
            parsed_doc = (
                await self._engine.storage.get_parsed_document(doc.current_version_id)
                if doc
                else None
            )

            content_hash = doc.current_hash if doc else ""
            doc_type = parsed_doc.doc_type.value if parsed_doc else "generic"
            metadata: dict[str, Any] = dict(parsed_doc.metadata.metadata) if parsed_doc else {}
            filename = str(metadata.get("filename", "source_file"))
            guessed_mime, _ = mimetypes.guess_type(filename)
            mime_type = guessed_mime or "application/octet-stream"
            status = doc.status.value if doc else DocumentStatus.INDEXED.value
            size_bytes = int(metadata.get("size_bytes", 0))

            items.append(
                SourceResponse(
                    source_id=source.source_id,
                    notebook_id=source.notebook_id,
                    document_id=source.document_id,
                    filename=filename,
                    content_hash=content_hash,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    doc_type=doc_type,
                    status=status,
                    deduplicated=False,
                    created_at=source.created_at,
                    metadata=metadata,
                )
            )

        return PageResponse[SourceResponse](
            items=items,
            next_cursor=page.next_cursor,
            limit=limit,
        )

    async def get_source(
        self,
        *,
        notebook_id: UUID,
        source_id: UUID,
    ) -> SourceResponse:
        """Retrieve source details and linked document metadata."""
        notebook = await self._engine.storage.get_notebook(notebook_id)
        if notebook is None:
            raise NotFoundError(f"Notebook {notebook_id} was not found")

        source = await self._engine.storage.get_source(source_id)
        if source is None or source.notebook_id != notebook_id:
            raise NotFoundError(f"Source {source_id} was not found in notebook {notebook_id}")

        doc = await self._engine.storage.get_document(source.document_id)
        if doc is None:
            raise NotFoundError(f"Document for source {source_id} was not found")

        parsed_doc = await self._engine.storage.get_parsed_document(doc.current_version_id)
        content_hash = doc.current_hash
        doc_type = parsed_doc.doc_type.value if parsed_doc else "generic"
        status = doc.status.value
        metadata: dict[str, Any] = dict(parsed_doc.metadata.metadata) if parsed_doc else {}
        filename = str(metadata.get("filename", "source_file"))
        guessed_mime, _ = mimetypes.guess_type(filename)
        mime_type = guessed_mime or "application/octet-stream"
        size_bytes = int(metadata.get("size_bytes", 0))

        return SourceResponse(
            source_id=source.source_id,
            notebook_id=source.notebook_id,
            document_id=source.document_id,
            filename=filename,
            content_hash=content_hash,
            mime_type=mime_type,
            size_bytes=size_bytes,
            doc_type=doc_type,
            status=status,
            deduplicated=False,
            created_at=source.created_at,
            metadata=metadata,
        )

    async def delete_source(
        self,
        *,
        notebook_id: UUID,
        source_id: UUID,
    ) -> None:
        """Delete a source association and refresh vector memberships."""
        notebook = await self._engine.storage.get_notebook(notebook_id)
        if notebook is None:
            raise NotFoundError(f"Notebook {notebook_id} was not found")

        source = await self._engine.storage.get_source(source_id)
        if source is None or source.notebook_id != notebook_id:
            raise NotFoundError(f"Source {source_id} was not found in notebook {notebook_id}")

        deleted = await self._engine.storage.delete_source(source_id)
        if not deleted:
            raise NotFoundError(f"Source {source_id} was not found in notebook {notebook_id}")

    async def get_source_status(
        self,
        *,
        notebook_id: UUID,
        source_id: UUID,
    ) -> SourceStatusResponse:
        """Retrieve persisted document status for a source."""
        notebook = await self._engine.storage.get_notebook(notebook_id)
        if notebook is None:
            raise NotFoundError(f"Notebook {notebook_id} was not found")

        source = await self._engine.storage.get_source(source_id)
        if source is None or source.notebook_id != notebook_id:
            raise NotFoundError(f"Source {source_id} was not found in notebook {notebook_id}")

        doc = await self._engine.storage.get_document(source.document_id)
        if doc is None:
            raise NotFoundError(f"Document for source {source_id} was not found")

        error_message = (
            "Ingestion processing failed" if doc.status == DocumentStatus.FAILED else None
        )

        return SourceStatusResponse(
            source_id=source.source_id,
            notebook_id=source.notebook_id,
            document_id=source.document_id,
            status=doc.status.value,
            created_at=source.created_at,
            updated_at=doc.updated_at,
            error_message=error_message,
        )

    async def _find_source_in_notebook(self, notebook_id: UUID, document_id: UUID) -> Source | None:
        """Find if a document is already linked to a specific notebook."""
        cursor: str | None = None
        while True:
            page = await self._engine.storage.list_sources(
                notebook_id=notebook_id, limit=100, cursor=cursor
            )
            for s in page.items:
                if s.document_id == document_id:
                    return s
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        return None
