"""Ingestion orchestration service coordinating frozen core primitives."""

from __future__ import annotations

import hashlib
import mimetypes
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, replace
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
    DependencyUnavailableError,
    MnemoInterfaceError,
    NotFoundError,
    PrincipalContextV1,
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
from mnemo.storage.composite import CompositeStorage
from mnemo.storage.sqlite import SQLiteStore

from mnemo_server.schemas.common import PageResponse
from mnemo_server.schemas.sources import SourceResponse, SourceStatusResponse
from mnemo_server.services.authorized_scope import (
    AuthorizedNotebookPageCursor,
    AuthorizedNotebookScope,
    AuthorizedNotebookScopeResolver,
)
from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority


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


@dataclass(frozen=True, slots=True)
class _SourceIngestionIntent:
    authority: SQLiteNotebookScopeAuthority
    actor_id: UUID
    notebook_id: UUID
    content_hash: str
    token: UUID
    revision: int
    process_lease: object


class IngestionService:
    """Coordinates parsing, chunking, embedding, indexing, and source association."""

    def __init__(
        self,
        engine: KnowledgeEngine,
        token_counter: TokenCounterInterfaceV1,
        *,
        max_asset_bytes: int = 100 * 1024 * 1024,
        principal: PrincipalContextV1 | None = None,
        page_cursor: AuthorizedNotebookPageCursor | None = None,
    ) -> None:
        self._engine = engine
        self._token_counter = token_counter
        self._max_asset_bytes = max_asset_bytes
        self._principal = principal
        self._page_cursor = page_cursor

    async def _read_scope(self, notebook_id: UUID) -> AuthorizedNotebookScope | None:
        authority = getattr(self._engine, "server_scope_authority", None)
        if authority is None:
            return None
        if not isinstance(authority, SQLiteNotebookScopeAuthority) or self._principal is None:
            raise PermissionError("trusted membership authority is unavailable")
        return (
            await AuthorizedNotebookScopeResolver(self._engine.storage, authority).resolve(
                self._principal, (notebook_id,)
            )
        )[0]

    async def _revalidate(self, scope: AuthorizedNotebookScope | None) -> None:
        if scope is None:
            return
        authority = getattr(self._engine, "server_scope_authority", None)
        if not isinstance(authority, SQLiteNotebookScopeAuthority) or self._principal is None:
            raise PermissionError("trusted membership authority is unavailable")
        await AuthorizedNotebookScopeResolver(self._engine.storage, authority).revalidate(
            self._principal, (scope,)
        )

    def _deletion_lease(self, notebook_id: UUID) -> AbstractContextManager[int | None]:
        authority = getattr(self._engine, "server_scope_authority", None)
        if authority is None:
            return nullcontext(None)
        if not isinstance(authority, SQLiteNotebookScopeAuthority) or self._principal is None:
            raise PermissionError("trusted membership authority is unavailable")
        if not isinstance(self._engine.storage, SQLiteStore):
            raise DependencyUnavailableError("governed source write store is unavailable")
        if not self._principal.authenticated:
            raise PermissionError("authenticated principal is required")
        return authority.owner_write_lease(
            actor_id=self._principal.actor_id, notebook_id=notebook_id
        )

    async def ingest_source(
        self,
        *,
        notebook_id: UUID,
        filename: str,
        data: bytes,
    ) -> SourceResponse:
        """Reserve an ACL quarantine before the first multi-store artifact write."""
        authority = getattr(self._engine, "server_scope_authority", None)
        if authority is None:
            return await self._ingest_source_artifacts(
                notebook_id=notebook_id, filename=filename, data=data, intent=None
            )
        if (
            not isinstance(authority, SQLiteNotebookScopeAuthority)
            or self._principal is None
            or not self._principal.authenticated
            or not isinstance(self._engine.storage, CompositeStorage)
        ):
            raise DependencyUnavailableError("governed source ingestion is unavailable")
        scope = await self._read_scope(notebook_id)
        if scope is None or not authority.permits(
            self._principal.actor_id, notebook_id, operation="write"
        ):
            raise NotFoundError("authorized resource was not found")
        with authority.source_ingestion_process_lock() as process_lease:
            return await self._governed_ingest_with_lease(
                authority=authority,
                notebook_id=notebook_id,
                filename=filename,
                data=data,
                process_lease=process_lease,
            )

    async def _governed_ingest_with_lease(
        self,
        *,
        authority: SQLiteNotebookScopeAuthority,
        notebook_id: UUID,
        filename: str,
        data: bytes,
        process_lease: object,
    ) -> SourceResponse:
        if self._principal is None:
            raise PermissionError("trusted membership identity is unavailable")
        content_hash = hashlib.sha256(data).hexdigest()
        existing_doc = await self._engine.storage.get_document_by_content_hash(content_hash)
        if (
            existing_doc is not None
            and await self._find_source_in_notebook(notebook_id, existing_doc.document_id)
            is not None
        ):
            raise ConflictError("document is already associated with this notebook")
        token = uuid4()
        revision = authority.reserve_source_ingestion(
            actor_id=self._principal.actor_id,
            notebook_id=notebook_id,
            content_hash=content_hash,
            token=token,
            document_preexisted=existing_doc is not None,
            process_lease=process_lease,
        )
        intent = _SourceIngestionIntent(
            authority=authority,
            actor_id=self._principal.actor_id,
            notebook_id=notebook_id,
            content_hash=content_hash,
            token=token,
            revision=revision,
            process_lease=process_lease,
        )
        try:
            return await self._ingest_source_artifacts(
                notebook_id=notebook_id, filename=filename, data=data, intent=intent
            )
        except BaseException:
            authority.mark_source_ingestion_failed(
                notebook_id=notebook_id, content_hash=content_hash, token=token
            )
            raise

    async def _ingest_source_artifacts(
        self,
        *,
        notebook_id: UUID,
        filename: str,
        data: bytes,
        intent: _SourceIngestionIntent | None,
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
            # An interrupted multi-artifact write may have published a parsed
            # document but not its original, chunks, or projection. Never turn
            # that incomplete document into a visible notebook association.
            if existing_doc.status is not DocumentStatus.INDEXED:
                raise DependencyUnavailableError(
                    "document ingestion is incomplete and requires reconciliation",
                    retryable=False,
                )
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
            await AssetFoundationService(
                storage=self._engine.storage,
                catalog=self._engine.asset_catalog,
                asset_records=self._engine.asset_records,
                max_asset_bytes=self._max_asset_bytes,
            ).validate_retained_version(
                data=data,
                filename=filename,
                declared_media_type=_retention_media_type(router, data, filename),
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
            doc_type = parsed_doc.doc_type.value
            guessed_mime, _ = mimetypes.guess_type(filename)
            mime_type = guessed_mime or "application/octet-stream"
            metadata: dict[str, Any] = thaw_metadata(parsed_doc.metadata.metadata)

            response = SourceResponse(
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
            await self._publish_source(source, intent)
            return response

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
            before_asset_write=(
                None
                if intent is None
                else lambda blob, mime: self._record_asset_candidate(intent, blob, mime)
            ),
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
                intent=intent,
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
            metadata = thaw_metadata(parsed_doc.metadata.metadata)
            guessed_mime, _ = mimetypes.guess_type(filename)
            mime_type = guessed_mime or "application/octet-stream"

            response = SourceResponse(
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
            await self._publish_source(source, intent)
            return response
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

    async def _publish_source(self, source: Source, intent: _SourceIngestionIntent | None) -> None:
        if intent is None:
            await self._engine.storage.upsert_source(source)
            return
        with intent.authority.source_ingestion_write_lease(
            actor_id=intent.actor_id,
            notebook_id=intent.notebook_id,
            content_hash=intent.content_hash,
            token=intent.token,
            reserved_revision=intent.revision,
            process_lease=intent.process_lease,
        ) as record_source:
            await self._engine.storage.upsert_source(source)
            record_source(source.source_id)

    async def reconcile_failed_source_ingestion(
        self, *, notebook_id: UUID, content_hash: str
    ) -> None:
        """Roll back an observed failed association while the ACL blocks serving.

        This never deletes shared documents or assets. The separate SQLite
        process lock proves that a protocol-v1 incomplete writer has exited
        before its canonical source association is reconciled.
        """
        authority = getattr(self._engine, "server_scope_authority", None)
        storage = self._engine.storage
        if (
            not isinstance(authority, SQLiteNotebookScopeAuthority)
            or self._principal is None
            or not self._principal.authenticated
            or not isinstance(storage, CompositeStorage)
        ):
            raise DependencyUnavailableError("governed source recovery is unavailable")
        if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
            raise ValueError("source content hash must be lowercase SHA-256")
        with (
            authority.source_ingestion_process_lock() as process_lease,
            authority.source_ingestion_recovery_lease(
                actor_id=self._principal.actor_id,
                notebook_id=notebook_id,
                content_hash=content_hash,
                process_lease=process_lease,
            ) as (needs_reconciliation, record_reconciled),
        ):
            if not needs_reconciliation:
                return
            document_preexisted = authority.source_ingestion_document_preexisted(
                actor_id=self._principal.actor_id,
                notebook_id=notebook_id,
                content_hash=content_hash,
            )
            document = await storage.get_document_by_content_hash(content_hash)
            if document is not None:
                sources = await storage.list_sources_for_document(document.document_id)
                for source in sources:
                    if source.notebook_id == notebook_id:
                        await storage.delete_source(source.source_id)
                remaining = await storage.list_sources_for_document(document.document_id)
                if any(source.notebook_id == notebook_id for source in remaining):
                    raise DependencyUnavailableError("source association recovery is incomplete")
                await storage.reconcile_document_membership(document.document_id)
                if not remaining and not document_preexisted:
                    await storage.reconcile_unpublished_document(
                        document_id=document.document_id,
                        version_id=document.current_version_id,
                        content_hash=content_hash,
                    )
            elif not document_preexisted:
                # A prior recovery may have committed the SQL cascade before
                # losing its filesystem/vector cleanup or ACL completion.
                await storage.reconcile_unpublished_document(
                    document_id=uuid5(NAMESPACE_URL, f"mnemo-document:{content_hash}"),
                    version_id=uuid5(NAMESPACE_URL, f"mnemo-version:{content_hash}"),
                    content_hash=content_hash,
                )
            candidates = authority.source_ingestion_asset_candidates(
                actor_id=self._principal.actor_id,
                notebook_id=notebook_id,
                content_hash=content_hash,
            )
            grouped: dict[str, set[str]] = {}
            preexisting_hashes: set[str] = set()
            for asset_hash, mime_type, preexisting in candidates:
                grouped.setdefault(asset_hash, set()).add(mime_type)
                if preexisting:
                    preexisting_hashes.add(asset_hash)
            for asset_hash, mime_types in grouped.items():
                if asset_hash not in preexisting_hashes:
                    await storage.reconcile_orphan_asset_candidate(
                        asset_hash, tuple(sorted(mime_types))
                    )
            record_reconciled()

    async def _record_asset_candidate(
        self, intent: _SourceIngestionIntent, data: bytes, mime_type: str
    ) -> None:
        storage = self._engine.storage
        if not isinstance(storage, CompositeStorage):
            raise DependencyUnavailableError("governed asset recovery is unavailable")
        asset_hash = hashlib.sha256(data).hexdigest()
        preexisting = await storage.contains_hash(asset_hash)
        intent.authority.record_source_ingestion_asset_candidate(
            actor_id=intent.actor_id,
            notebook_id=intent.notebook_id,
            source_content_hash=intent.content_hash,
            token=intent.token,
            asset_hash=asset_hash,
            mime_type=mime_type,
            preexisting=preexisting,
            process_lease=intent.process_lease,
        )

    async def _retain_original(
        self,
        *,
        data: bytes,
        filename: str,
        media_type: str,
        document: Document,
        parsed_document: ParsedDocument,
        ingestion_result: IngestionResultV2 | None = None,
        intent: _SourceIngestionIntent | None = None,
    ) -> None:
        service = AssetFoundationService(
            storage=self._engine.storage,
            catalog=self._engine.asset_catalog,
            asset_records=self._engine.asset_records,
            max_asset_bytes=self._max_asset_bytes,
            before_asset_write=(
                None
                if intent is None
                else lambda blob, mime: self._record_asset_candidate(intent, blob, mime)
            ),
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
        scope = await self._read_scope(notebook_id)
        if scope is not None:
            if self._principal is None or self._page_cursor is None:
                raise PermissionError("trusted continuation authority is unavailable")
            if cursor is not None:
                cursor = self._page_cursor.decode(
                    cursor,
                    domain="mnemo-source-list/v1",
                    principal=self._principal,
                    scope=scope,
                    limit=limit,
                )
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
            if scope is not None and source.notebook_id != notebook_id:
                raise NotFoundError("authorized resource was not found")
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

        await self._revalidate(scope)
        next_cursor = page.next_cursor
        if scope is not None and next_cursor is not None:
            if self._principal is None or self._page_cursor is None:
                raise PermissionError("trusted continuation authority is unavailable")
            next_cursor = self._page_cursor.encode(
                next_cursor,
                domain="mnemo-source-list/v1",
                principal=self._principal,
                scope=scope,
                limit=limit,
            )
        response = PageResponse[SourceResponse](items=items, next_cursor=next_cursor, limit=limit)
        return response

    async def get_source(
        self,
        *,
        notebook_id: UUID,
        source_id: UUID,
    ) -> SourceResponse:
        """Retrieve source details and linked document metadata."""
        scope = await self._read_scope(notebook_id)
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

        response = SourceResponse(
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
        await self._revalidate(scope)
        return response

    async def delete_source(
        self,
        *,
        notebook_id: UUID,
        source_id: UUID,
    ) -> None:
        """Delete a source association and refresh vector memberships."""
        authority = getattr(self._engine, "server_scope_authority", None)
        if authority is not None and isinstance(self._engine.storage, CompositeStorage):
            storage = self._engine.storage
            if (
                not isinstance(authority, SQLiteNotebookScopeAuthority)
                or self._principal is None
                or not self._principal.authenticated
            ):
                raise DependencyUnavailableError("governed source deletion is unavailable")
            scope = await self._read_scope(notebook_id)
            if scope is None or not authority.permits(
                self._principal.actor_id, notebook_id, operation="write"
            ):
                raise NotFoundError("authorized resource was not found")
            with authority.source_ingestion_process_lock() as process_lease:
                source = await storage.get_source(source_id)
                if source is None or source.notebook_id != notebook_id:
                    raise NotFoundError("authorized resource was not found")
                authority.reserve_source_deletion(
                    actor_id=self._principal.actor_id,
                    notebook_id=notebook_id,
                    source_id=source_id,
                    document_id=source.document_id,
                    token=uuid4(),
                    process_lease=process_lease,
                )
                await self._finish_source_deletion(
                    authority=authority,
                    storage=storage,
                    notebook_id=notebook_id,
                    source_id=source_id,
                    process_lease=process_lease,
                )
            return
        if authority is not None and not isinstance(self._engine.storage, SQLiteStore):
            raise DependencyUnavailableError("governed source deletion is unavailable")
        with self._deletion_lease(notebook_id):
            notebook = await self._engine.storage.get_notebook(notebook_id)
            if notebook is None:
                raise NotFoundError(f"Notebook {notebook_id} was not found")

            source = await self._engine.storage.get_source(source_id)
            if source is None or source.notebook_id != notebook_id:
                raise NotFoundError(f"Source {source_id} was not found in notebook {notebook_id}")

            deleted = await self._engine.storage.delete_source(source_id)
            if not deleted:
                raise NotFoundError(f"Source {source_id} was not found in notebook {notebook_id}")

    async def reconcile_failed_source_deletion(self, *, notebook_id: UUID, source_id: UUID) -> None:
        """Retry a quarantined delete; no ACL scope is disclosed before recovery."""
        authority = getattr(self._engine, "server_scope_authority", None)
        storage = self._engine.storage
        if (
            not isinstance(authority, SQLiteNotebookScopeAuthority)
            or self._principal is None
            or not self._principal.authenticated
            or not isinstance(storage, CompositeStorage)
        ):
            raise DependencyUnavailableError("governed source deletion recovery is unavailable")
        with authority.source_ingestion_process_lock() as process_lease:
            await self._finish_source_deletion(
                authority=authority,
                storage=storage,
                notebook_id=notebook_id,
                source_id=source_id,
                process_lease=process_lease,
            )

    async def _finish_source_deletion(
        self,
        *,
        authority: SQLiteNotebookScopeAuthority,
        storage: CompositeStorage,
        notebook_id: UUID,
        source_id: UUID,
        process_lease: object,
    ) -> None:
        if self._principal is None:
            raise PermissionError("trusted membership identity is unavailable")
        with authority.source_deletion_completion_lease(
            actor_id=self._principal.actor_id,
            notebook_id=notebook_id,
            source_id=source_id,
            process_lease=process_lease,
        ) as (document_id, needs_reconciliation):
            if not needs_reconciliation:
                return
            source = await storage.get_source(source_id)
            if source is not None:
                if source.notebook_id != notebook_id or source.document_id != document_id:
                    raise DependencyUnavailableError("source deletion state is inconsistent")
                await storage.delete_source(source_id)
            if await storage.get_source(source_id) is not None:
                raise DependencyUnavailableError("source deletion was not persisted")
            await storage.reconcile_document_membership(document_id)

    async def get_source_status(
        self,
        *,
        notebook_id: UUID,
        source_id: UUID,
    ) -> SourceStatusResponse:
        """Retrieve persisted document status for a source."""
        scope = await self._read_scope(notebook_id)
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

        response = SourceStatusResponse(
            source_id=source.source_id,
            notebook_id=source.notebook_id,
            document_id=source.document_id,
            status=doc.status.value,
            created_at=source.created_at,
            updated_at=doc.updated_at,
            error_message=error_message,
        )
        await self._revalidate(scope)
        return response

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
