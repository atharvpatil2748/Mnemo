"""Async ingestion sequencing across the pure Phase 3 boundaries."""

from types import MappingProxyType
from uuid import UUID

from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.interfaces.parser_models import ParseResult, TransientAsset
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.models import Asset, Document, FrozenMetadata, ParsedDocument
from mnemo.parsers import ParserRouter

from .canonicalizer import DocumentCanonicalizer


class IngestionPipeline:
    """Own routing, pure transformations, asset persistence, and IR publication."""

    def __init__(
        self,
        *,
        router: ParserRouter,
        storage: StorageInterfaceV1,
        cleaner: DocumentCleaner,
        classifier: DocumentClassifier,
        canonicalizer: DocumentCanonicalizer,
    ) -> None:
        self._router = router
        self._storage = storage
        self._cleaner = cleaner
        self._classifier = classifier
        self._canonicalizer = canonicalizer

    async def ingest(self, data: bytes, filename: str, version_id: UUID) -> ParsedDocument:
        """Produce or retrieve the canonical ParsedDocument for one document version."""
        if not isinstance(version_id, UUID):
            raise ContractValidationError("version_id must be a UUID")

        routed = await self._router.route(data, filename)
        if isinstance(routed, Document):
            return await self._load_deduplicated(routed)

        cleaned = self._cleaner.clean(routed)
        classified = self._classifier.classify(cleaned, filename)
        assets = await self._persist_assets(classified)
        document = self._canonicalizer.canonicalize(classified, assets)
        await self._storage.put_parsed_document(version_id, document)
        return document

    async def _load_deduplicated(self, document: Document) -> ParsedDocument:
        parsed = await self._storage.get_parsed_document(document.current_version_id)
        if parsed is None:
            raise IntegrityError(
                "deduplicated document has no canonical ParsedDocument for its current version"
            )
        return parsed

    async def _persist_assets(self, result: ParseResult) -> MappingProxyType[str, Asset]:
        resolved: dict[str, Asset] = {}
        for transient in result.extracted_assets:
            resolved[transient.parser_local_id] = await self._persist_asset(transient)
        return MappingProxyType(resolved)

    async def _persist_asset(self, transient: TransientAsset) -> Asset:
        return await self._storage.put_asset(
            transient.raw_bytes,
            transient.mime_type,
            FrozenMetadata(),
        )
