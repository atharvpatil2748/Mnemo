"""Async ingestion sequencing across the pure Phase 3 boundaries."""

from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from mnemo.classifier import DocumentClassifier
from mnemo.cleaner import DocumentCleaner
from mnemo.interfaces.errors import ContractValidationError, IntegrityError
from mnemo.interfaces.parser_models import ParseResult, ParseResultV2, TransientAsset
from mnemo.interfaces.storage import StorageInterfaceV1
from mnemo.models import Asset, Document, FrozenMetadata, ParsedDocument
from mnemo.parsers import ParserRouter

from .canonicalizer import DocumentCanonicalizer


@dataclass(frozen=True, slots=True)
class IngestionResultV2:
    """Additive ingestion evidence used by the asset-catalog publication boundary."""

    parsed_document: ParsedDocument
    resolved_assets: MappingProxyType[str, Asset]
    extraction: ParseResultV2 | None


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

        document, _, _ = await self._publish(routed, filename, version_id)
        return document

    async def ingest_with_assets(
        self, data: bytes, filename: str, version_id: UUID
    ) -> IngestionResultV2:
        """Publish canonical V1 IR and retain typed transient extraction evidence."""
        if not isinstance(version_id, UUID):
            raise ContractValidationError("version_id must be a UUID")
        routed = await self._router.route_with_assets(data, filename)
        if isinstance(routed, Document):
            return IngestionResultV2(
                parsed_document=await self._load_deduplicated(routed),
                resolved_assets=MappingProxyType({}),
                extraction=None,
            )
        canonical_route = await self._router.route(data, filename)
        if isinstance(canonical_route, Document):
            return IngestionResultV2(
                parsed_document=await self._load_deduplicated(canonical_route),
                resolved_assets=MappingProxyType({}),
                extraction=None,
            )
        document, assets = await self._publish_with_assets(
            canonical_route, routed, filename, version_id
        )
        return IngestionResultV2(
            parsed_document=document,
            resolved_assets=assets,
            extraction=routed,
        )

    async def _publish_with_assets(
        self,
        canonical_route: ParseResult,
        extraction: ParseResultV2,
        filename: str,
        version_id: UUID,
    ) -> tuple[ParsedDocument, MappingProxyType[str, Asset]]:
        """Publish the frozen V1 IR while retaining additive V2 asset evidence."""
        cleaned = self._cleaner.clean(canonical_route)
        classified = self._classifier.classify(cleaned, filename)
        extracted_assets = dict(await self._persist_assets(extraction.parse_result))
        canonical_assets = dict(await self._persist_assets(classified))
        document = self._canonicalizer.canonicalize(classified, canonical_assets)
        await self._storage.put_parsed_document(version_id, document)
        return document, MappingProxyType(extracted_assets)

    async def _publish(
        self, routed: ParseResult, filename: str, version_id: UUID
    ) -> tuple[ParsedDocument, MappingProxyType[str, Asset], ParseResult]:
        """Run frozen cleaning/classification/canonicalization exactly once."""

        cleaned = self._cleaner.clean(routed)
        classified = self._classifier.classify(cleaned, filename)
        assets = await self._persist_assets(classified)
        document = self._canonicalizer.canonicalize(classified, assets)
        await self._storage.put_parsed_document(version_id, document)
        return document, assets, classified

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
