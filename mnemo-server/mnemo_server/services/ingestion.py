"""Ingestion orchestration service coordinating frozen core primitives."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from mnemo.asset_foundation import AssetFoundationService
from mnemo.chunkers import ChunkerDispatcher
from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.embeddings import EmbedderModule
from mnemo.engine import KnowledgeEngine
from mnemo.ingestion import DocumentCanonicalizer, IngestionPipeline, IngestionResultV2
from mnemo.interfaces import (
    ChunkingContext,
    ChunkingOptions,
    ConflictError,
    MnemoInterfaceError,
    NotFoundError,
    TokenCounterInterfaceV1,
)
from mnemo.interfaces.parser import ParserInterfaceV1
from mnemo.models import (
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    ParsedDocument,
    Source,
    thaw_metadata,
)
from mnemo.parsers import ParserRouter

from mnemo_server.schemas.common import PageResponse
from mnemo_server.schemas.sources import SourceResponse, SourceStatusResponse


class ServerParserRouter(ParserRouter):
    """Parser router with extension-aware resolution precedence.

    Ensures that structured text formats (such as .md, .csv, .json, .html)
    with specific file extensions are not hijacked by generic text/plain
    MIME detection from libmagic on Linux platforms.
    """

    def _resolve_parser(self, mime_type: str, extension: str) -> ParserInterfaceV1 | None:
        """Prefer specific extensions over generic text MIME observations."""
        parser = None
        if extension and extension not in (".txt", ".log"):
            parser = self.registry.resolve_parser(extension)
        if not parser:
            parser = self.registry.resolve_parser(mime_type)
        if not parser and extension:
            parser = self.registry.resolve_parser(extension)

        return parser


class IngestionService:
    """Coordinates parsing, chunking, embedding, indexing, and source association."""

    def __init__(
        self,
        engine: KnowledgeEngine,
        token_counter: TokenCounterInterfaceV1,
        *,
        max_asset_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self._engine = engine
        self._token_counter = token_counter
        self._max_asset_bytes = max_asset_bytes

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

            parsed_doc = await self._engine.storage.get_parsed_document(
                existing_doc.current_version_id
            )
            if parsed_doc is None:
                raise NotFoundError("Parsed representation for deduplicated document was not found")
            router = ServerParserRouter(self._engine.registry, self._engine.storage)
            await self._retain_original(
                data=data,
                filename=filename,
                media_type=_retention_media_type(router, data, filename),
                document=existing_doc,
                parsed_document=parsed_doc,
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

            doc_type = parsed_doc.doc_type.value
            guessed_mime, _ = mimetypes.guess_type(filename)
            mime_type = guessed_mime or "application/octet-stream"
            metadata: dict[str, Any] = thaw_metadata(parsed_doc.metadata.metadata)

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

        router = ServerParserRouter(self._engine.registry, self._engine.storage)
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

        ingestion_result = await pipeline.ingest_with_assets(data, filename, version_id)
        parsed_doc = ingestion_result.parsed_document

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
            await self._retain_original(
                data=data,
                filename=filename,
                media_type=_retention_media_type(router, data, filename),
                document=doc,
                parsed_document=parsed_doc,
                ingestion_result=ingestion_result,
            )
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

            metadata = thaw_metadata(parsed_doc.metadata.metadata)
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

    async def _retain_original(
        self,
        *,
        data: bytes,
        filename: str,
        media_type: str,
        document: Document,
        parsed_document: ParsedDocument,
        ingestion_result: IngestionResultV2 | None = None,
    ) -> None:
        service = AssetFoundationService(
            storage=self._engine.storage,
            catalog=self._engine.asset_catalog,
            asset_records=self._engine.asset_records,
            max_asset_bytes=self._max_asset_bytes,
        )
        await service.retain_ingested_version(
            data=data,
            filename=filename,
            declared_media_type=media_type,
            document=document,
            parsed_document=parsed_document,
            extraction=None if ingestion_result is None else ingestion_result.extraction,
            resolved_assets=(
                None if ingestion_result is None else ingestion_result.resolved_assets
            ),
        )

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
            metadata: dict[str, Any] = (
                thaw_metadata(parsed_doc.metadata.metadata) if parsed_doc else {}
            )
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
        metadata: dict[str, Any] = thaw_metadata(parsed_doc.metadata.metadata) if parsed_doc else {}
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


def _retention_media_type(router: ServerParserRouter, data: bytes, filename: str) -> str:
    """Preserve a specific safe extension type when sniffing is generic text/binary."""
    detected = router._detect_mime(data, filename)
    guessed, _ = mimetypes.guess_type(filename)
    if guessed and detected in {"text/plain", "application/octet-stream"}:
        return guessed
    return detected
