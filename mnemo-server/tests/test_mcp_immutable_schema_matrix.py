"""Public MCP protocol matrix over disposable old/new immutable chunk schemas."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import anyio
import pytest
from httpx import ASGITransport, AsyncClient
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
from mnemo.engine import EngineState, FinalQAComponents, KnowledgeEngine, _ResolvedProviders
from mnemo.interfaces import (
    CompletionResult,
    EmbeddingCapabilities,
    HealthStatus,
    LLMCapabilities,
    PluginError,
    PrincipalContextV1,
    StorageError,
)
from mnemo.interfaces.advanced_retrieval import AdvancedSourcePage
from mnemo.models import (
    Asset,
    AssetContainerKind,
    AssetDerivation,
    AssetDerivationStatus,
    AssetExtractionProvenance,
    AssetLocator,
    AssetLocatorKind,
    AssetOccurrence,
    BinaryDelivery,
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    DeliveryAttribution,
    DeliveryCompleteness,
    DeliveryResourceKind,
    DocType,
    Document,
    DocumentBinaryReference,
    DocumentBinaryRole,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    IndexGeneration,
    IndexGenerationState,
    Insight,
    InsightType,
    Notebook,
    OCRCapability,
    OCRCompleteness,
    OCRConfidence,
    OCRConfidenceBand,
    OCRProviderMetadata,
    OCRRegion,
    OCRResult,
    ParsedDocument,
    Source,
    TableBlock,
    TextBlock,
    VisionCapability,
    VisionCaption,
    VisionCompleteness,
    VisionConfidence,
    VisionProviderMetadata,
    VisionResult,
    asset_derivation_id,
    asset_occurrence_id,
    ocr_region_id,
    ocr_result_content_hash,
    vision_result_content_hash,
)
from mnemo.models.advanced_retrieval import (
    AdvancedRetrievalCandidate,
    EvidenceRepresentation,
    PositionalScopeV2,
    RetrievalPathEvidenceV2,
    RetrievalScopeV2,
    advanced_candidate_id,
)
from mnemo.registry import PluginRegistry
from mnemo.retrieval import (
    AdvancedRetrievalService,
    CanonicalTextAdvancedSource,
    FinalQAV2Orchestrator,
    MultimodalContextBuilder,
    ParentRetriever,
    PartitionedRetrievalServiceV1,
    RetrievalCursorCodec,
    SparseRetriever,
    StructuredDatasetRuntimeService,
)
from mnemo.storage import SQLiteFinalQAOperationalStore
from mnemo.storage.sqlite import SQLiteStore
from mnemo.storage.v2_runtime import SQLiteV2ReadOnlyRuntimeStore
from mnemo_server.app import create_app
from mnemo_server.config import ServerConfig
from mnemo_server.mcp import server as mcp_server_module
from mnemo_server.mcp import tools as mcp_tools
from mnemo_server.mcp.server import create_mcp_server
from mnemo_server.routers import delivery as delivery_router


class _ParsedReadStore(SQLiteV2ReadOnlyRuntimeStore):
    """Only parsed blocks and source bytes are in memory; indexed reads are SQLite."""

    parsed: dict[UUID, ParsedDocument]
    assets: dict[UUID, bytes]
    analysis_ids: dict[str, UUID]
    qa_store: SQLiteFinalQAOperationalStore | None = None

    async def close(self) -> None:
        await super().close()
        if self.qa_store is not None:
            await self.qa_store.close()

    async def get_parsed_document(self, version_id: UUID) -> ParsedDocument | None:
        return self.parsed.get(version_id)

    async def get_asset(self, asset_id: UUID) -> bytes | None:
        return self.assets.get(asset_id)


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
        registry.register_llm("synthesizer", _FixtureSynthesizer(), priority=0)


class _FixtureSynthesizer:
    provider = "disposable-test"
    model = "deterministic-grounded"
    max_context_tokens = 100_000

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_streaming=False,
            supports_json=True,
            supports_vision=False,
            supports_reasoning=False,
        )

    async def complete(
        self,
        system: str,
        messages: object,
        structured_output: object = None,
        max_tokens: int = 1000,
    ) -> CompletionResult:
        del system, messages, structured_output, max_tokens
        return CompletionResult(model=self.model, text="Grounded [source:1]")

    def stream(self, system: str, messages: object, max_tokens: int = 1000) -> AsyncIterator[str]:
        del system, messages, max_tokens
        return self._stream()

    async def _stream(self) -> AsyncIterator[str]:
        yield "Grounded [source:1]"

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            healthy=True, component="fixture-synthesizer", checked_at=datetime.now(UTC)
        )


async def _persist_analysis(
    writer: SQLiteStore,
    *,
    notebook_id: UUID,
    document_id: UUID,
    version_id: UUID,
    occurrence: AssetOccurrence,
    now: datetime,
) -> dict[str, UUID]:
    """Publish real, disposable derived records through the storage lifecycle."""
    ids: dict[str, UUID] = {"occurrence": occurrence.occurrence_id}
    for modality in ("ocr", "vision"):
        generation_id = UUID(int=90 if modality == "ocr" else 91)
        profile = f"fixture-{modality}"
        assert await writer.create_index_generation(
            IndexGeneration(
                generation_id=generation_id,
                capability=f"{modality}_text",
                profile=profile,
                schema_version=1,
                input_scope=str(notebook_id),
                provider_identity="fixture-provider",
                model_identity="fixture-model@r1",
                configuration_digest="a" * 64,
                dimensions=None,
                state=IndexGenerationState.BUILDING,
                item_count=0,
                checksum=None,
                created_at=now,
                updated_at=now,
            )
        )
        assert await writer.transition_index_generation(
            generation_id,
            IndexGenerationState.BUILDING,
            IndexGenerationState.READY,
            item_count=1,
            checksum="b" * 64,
        )
        ids[f"{modality}_generation"] = generation_id
        for ordinal in range(2 if modality == "ocr" else 1):
            created = now + timedelta(seconds=ordinal)
            digest = f"{ordinal + (1 if modality == 'ocr' else 4):064x}"
            operation = "ocr" if modality == "ocr" else "vision_analysis"
            derivation_id = asset_derivation_id(
                occurrence_id=occurrence.occurrence_id,
                operation=operation,
                provider_identity="fixture-provider",
                model_identity="fixture-model@r1",
                configuration_digest=digest,
            )
            assert await writer.create_asset_derivation(
                AssetDerivation(
                    derivation_id=derivation_id,
                    occurrence_id=occurrence.occurrence_id,
                    operation=operation,
                    provider_identity="fixture-provider",
                    model_identity="fixture-model@r1",
                    configuration_digest=digest,
                    output_asset_id=None,
                    output_payload=FrozenMetadata(),
                    status=AssetDerivationStatus.RUNNING,
                    confidence=None,
                    language=None,
                    created_at=created,
                    updated_at=created,
                )
            )
            ids[f"{modality}_{ordinal}"] = derivation_id
            if modality == "ocr":
                content = f"Persisted OCR observation {ordinal}"
                region = OCRRegion(
                    region_id=ocr_region_id(
                        derivation_id=derivation_id,
                        page_number=3,
                        order_index=0,
                        text=content,
                        bounding_box=None,
                    ),
                    page_number=3,
                    order_index=0,
                    text=content,
                    bounding_box=None,
                    confidence=OCRConfidence(value=0.9, band=OCRConfidenceBand.HIGH),
                    language=None,
                )
                assert await writer.put_ocr_result(
                    OCRResult(
                        derivation_id=derivation_id,
                        cache_key=digest,
                        document_id=document_id,
                        version_id=version_id,
                        occurrence_id=occurrence.occurrence_id,
                        asset_id=occurrence.asset_id,
                        generation_id=generation_id,
                        provider=OCRProviderMetadata(
                            provider_identity="fixture-provider",
                            model_identity="fixture-model",
                            model_revision="r1",
                            profile_id=profile,
                            capability=OCRCapability(
                                supported_media_types=("image/png",),
                                supported_languages=("en",),
                                supported_scripts=("Latn",),
                                max_pages=5,
                                max_pixels=1000,
                                geometry=False,
                                confidence=True,
                                cancellation=True,
                            ),
                        ),
                        preprocessing_digest="a" * 64,
                        completeness=OCRCompleteness.COMPLETE,
                        regions=(region,),
                        languages=(),
                        failures=(),
                        pages_submitted=1,
                        pages_succeeded=1,
                        content_hash=ocr_result_content_hash((region,)),
                        created_at=created,
                    )
                )
            else:
                caption = VisionCaption(
                    text="Persisted fixture diagram",
                    confidence=VisionConfidence(value=0.9),
                    language=None,
                )
                assert await writer.put_vision_result(
                    VisionResult(
                        derivation_id=derivation_id,
                        cache_key=digest,
                        document_id=document_id,
                        version_id=version_id,
                        occurrence_id=occurrence.occurrence_id,
                        asset_id=occurrence.asset_id,
                        generation_id=generation_id,
                        provider=VisionProviderMetadata(
                            provider_identity="fixture-provider",
                            model_identity="fixture-model",
                            model_revision="r1",
                            profile_id=profile,
                            capability=VisionCapability(
                                supported_media_types=("image/png",),
                                supported_languages=("en",),
                                max_width=1000,
                                max_height=1000,
                                max_pixels=1000000,
                                max_response_bytes=10000,
                                max_captions=2,
                                max_entities=2,
                                max_regions=2,
                                max_relations=2,
                                geometry=False,
                                confidence=True,
                                cancellation=True,
                            ),
                        ),
                        preprocessing_digest="a" * 64,
                        completeness=VisionCompleteness.COMPLETE,
                        captions=(caption,),
                        observations=(),
                        regions=(),
                        entities=(),
                        relations=(),
                        languages=(),
                        failures=(),
                        inputs_submitted=1,
                        inputs_succeeded=1,
                        content_hash=vision_result_content_hash(
                            completeness=VisionCompleteness.COMPLETE,
                            captions=(caption,),
                            observations=(),
                            regions=(),
                            entities=(),
                            relations=(),
                            languages=(),
                            failures=(),
                        ),
                        created_at=created,
                    )
                )
    pending_id = asset_derivation_id(
        occurrence_id=occurrence.occurrence_id,
        operation="ocr",
        provider_identity="fixture-provider",
        model_identity="fixture-model@r1",
        configuration_digest="e" * 64,
    )
    assert await writer.create_asset_derivation(
        AssetDerivation(
            derivation_id=pending_id,
            occurrence_id=occurrence.occurrence_id,
            operation="ocr",
            provider_identity="fixture-provider",
            model_identity="fixture-model@r1",
            configuration_digest="e" * 64,
            output_asset_id=None,
            output_payload=FrozenMetadata(),
            status=AssetDerivationStatus.PENDING,
            confidence=None,
            language=None,
            created_at=now,
            updated_at=now,
        )
    )
    ids["pending"] = pending_id
    return ids


class _GovernedFixtureSource:
    """Disposable principal-only representation over one persisted fixture chunk."""

    representation = EvidenceRepresentation.MULTILINGUAL_TEXT

    def __init__(self, candidate: AdvancedRetrievalCandidate) -> None:
        self._candidate = candidate

    async def retrieve(self, plan, *, offset, limit):  # type: ignore[no-untyped-def]
        raise PermissionError("governed fixture requires a trusted principal")

    async def retrieve_authorized(  # type: ignore[no-untyped-def]
        self, *, principal, plan, offset, limit
    ):
        assert principal.authenticated
        candidate = self._candidate
        in_scope = (
            plan.scope.notebook_id == candidate.notebook_id
            and (not plan.scope.document_ids or candidate.document_id in plan.scope.document_ids)
            and (not plan.scope.version_ids or candidate.version_id in plan.scope.version_ids)
        )
        selected = (candidate,) if in_scope and offset == 0 and limit > 0 else ()
        return AdvancedSourcePage(
            representation=self.representation,
            snapshot_identity="a" * 64,
            candidates=selected,
            examined=len(selected),
            next_offset=None,
            exhausted=True,
        )

    async def expand(self, plan, seeds, *, limit):  # type: ignore[no-untyped-def]
        return ()


async def _fixture(
    tmp_path: Path,
    *,
    legacy: bool,
    analysis: bool = False,
    empty_notebook: bool = False,
    capability_ready: bool = False,
    structured_ready: bool = False,
    final_qa_ready: bool = False,
    governed_multilingual: bool = False,
    cursor_ready: bool = False,
    inventory_empty: bool = False,
    asset_empty: bool = False,
):  # type: ignore[no-untyped-def]
    path = tmp_path / "matrix.db"
    writer = SQLiteStore(path)
    await writer.open()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    identities = []
    parsed: dict[UUID, ParsedDocument] = {}
    assets: dict[UUID, bytes] = {}
    analysis_ids: dict[str, UUID] = {}
    for index in range(0 if inventory_empty else 2):
        notebook_id, document_id, version_id, source_id = (
            UUID(int=index * 10 + offset) for offset in range(1, 5)
        )
        text = f"schema evidence {index}"
        metadata = DocumentMetadata(
            content_hash=f"{index + 1:064x}",
            title="Shared display title",
            page_count=5,
            metadata=FrozenMetadata(
                {
                    "original_filename": "same-name.csv",
                    "mime_type": "text/csv",
                }
            ),
        )
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
            source_span=BlockSpan(
                start_ordinal=0, end_ordinal=1 if index == 0 and structured_ready else 0
            ),
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
        if index == 0 and cursor_ready:
            second_chunk = replace(
                chunk,
                id="3" * 64,
                text="schema second persisted evidence",
                position=ChunkPosition(
                    section_index=0,
                    chunk_index_in_section=1,
                    page_number=4,
                    page_start=None if legacy else 4,
                    page_end=None if legacy else 4,
                ),
            )
            await writer.upsert_chunks((second_chunk,))
        asset_bytes = b"\x89PNG\r\n\x1a\nfixture-image" + bytes([index])
        asset_hash = hashlib.sha256(asset_bytes).hexdigest()
        asset = Asset(
            asset_id=UUID(int=50 + index),
            mime_type="image/png",
            content_hash=asset_hash,
            storage_uri="blob://fixture",
            metadata=FrozenMetadata(),
        )
        locator = AssetLocator(kind=AssetLocatorKind.PDF_PAGE, ordinal=0, page_number=3)
        occurrence = AssetOccurrence(
            occurrence_id=asset_occurrence_id(
                document_id=document_id,
                version_id=version_id,
                asset_id=asset.asset_id,
                locator=locator,
            ),
            asset_id=asset.asset_id,
            document_id=document_id,
            version_id=version_id,
            container_kind=AssetContainerKind.PDF,
            locator=locator,
            authored_alt_text="Fixture diagram",
            extraction_provenance=AssetExtractionProvenance(
                parser_id="fixture", parser_version="1", block_ordinal=0
            ),
            created_at=now,
        )
        if not (asset_empty and index == 1):
            await writer.register_asset_ingestion(
                assets=(asset,),
                binary_reference=DocumentBinaryReference(
                    document_id=document_id,
                    version_id=version_id,
                    asset_id=asset.asset_id,
                    role=DocumentBinaryRole.ORIGINAL,
                    media_type="image/png",
                    byte_size=len(asset_bytes),
                    created_at=now,
                ),
                occurrences=(occurrence,),
            )
            assets[asset.asset_id] = asset_bytes
        if index == 0 and analysis:
            analysis_ids = await _persist_analysis(
                writer,
                notebook_id=notebook_id,
                document_id=document_id,
                version_id=version_id,
                occurrence=occurrence,
                now=now,
            )
        if index == 0:
            await writer.upsert_insight(
                Insight(
                    insight_id=UUID(int=5),
                    notebook_id=notebook_id,
                    source_id=source_id,
                    type=InsightType.KEY_FACT,
                    content="Fixture schema evidence remains scoped",
                    confidence=0.99,
                    created_at=now,
                    metadata=FrozenMetadata(),
                )
            )
        blocks = (TextBlock(ordinal=0, text=text, page_number=3),)
        if index == 0 and structured_ready:
            blocks += (
                TableBlock(
                    ordinal=1,
                    rows=(("Name", "CPI"), ("Atharv", "9.20"), ("Asha", "8.95")),
                    header_row_count=1,
                    page_number=3,
                ),
            )
        parsed[version_id] = ParsedDocument(
            blocks=blocks,
            metadata=metadata,
            language="en",
            doc_type=DocType.GENERIC,
        )
        if index == 0 and structured_ready:
            assert await writer.project_structured_document(version_id, parsed[version_id])
        identities.append((notebook_id, document_id, version_id, source_id, chunk))
    if empty_notebook:
        await writer.upsert_notebook(
            Notebook(
                notebook_id=UUID(int=1000),
                title="Empty fixture",
                created_at=now,
                updated_at=now,
            )
        )
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
    reader.assets = assets
    reader.analysis_ids = analysis_ids
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
    if structured_ready:
        engine._structured_retrieval = StructuredDatasetRuntimeService(reader)
    if capability_ready:
        from test_capabilities_v2 import _engine as capability_engine

        engine._phase85 = (await capability_engine(tmp_path)).phase85
    sources = [CanonicalTextAdvancedSource(store=reader, ranked_retriever=SparseRetriever(reader))]
    if governed_multilingual and identities:
        notebook_id, document_id, version_id, source_id, chunk = identities[0]
        sources.append(
            _GovernedFixtureSource(
                AdvancedRetrievalCandidate(
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
            )
        )
    engine._advanced_retrieval = AdvancedRetrievalService(
        sources=tuple(sources),
        cursor_codec=RetrievalCursorCodec(b"disposable-schema-matrix-cursor-secret"),
    )
    engine._partitioned_retrieval = PartitionedRetrievalServiceV1(engine._advanced_retrieval)
    if final_qa_ready:
        from test_final_qa_v2_transport import Counter, Provider

        class FixtureAuthorizer:
            async def authorize_evidence(
                self, actor_id: UUID, notebook_id: UUID, candidate: object
            ) -> bool:
                del actor_id, candidate
                return notebook_id == UUID(int=1)

            async def generation_is_active(self, candidate: object) -> bool:
                del candidate
                return True

        operational = SQLiteFinalQAOperationalStore(tmp_path / "qa-operational.db")
        await operational.open()
        reader.qa_store = operational
        authorizer = FixtureAuthorizer()
        counter = Counter()
        engine._final_qa_components = FinalQAComponents(
            token_counter=counter, clock=lambda: now, operational_store_v2=operational
        )
        engine._final_qa_v2 = FinalQAV2Orchestrator(
            operational,
            Provider(["Grounded [source:1]"]),
            MultimodalContextBuilder(authorizer, counter),
            counter,
            authorizer,
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
async def test_public_persisted_ocr_vision_analysis_matrix(tmp_path: Path, legacy: bool) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy, analysis=True)
    notebook_id, document_id, version_id, source_id, _ = identities[0]
    other_notebook = identities[1][0]
    ids = reader.analysis_ids
    descriptors = await reader.list_authorized_asset_derivations(
        notebook_id=notebook_id, occurrence_id=ids["occurrence"]
    )
    assert {item.derivation_id for item in descriptors if item.ready} == {
        ids["ocr_0"],
        ids["ocr_1"],
        ids["vision_0"],
    }
    assert {item.generation_profile for item in descriptors if item.ready} == {
        "fixture-ocr",
        "fixture-vision",
    }
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                scope = {
                    "notebook_id": str(notebook_id),
                    "occurrence_id": str(ids["occurrence"]),
                }
                for modality, key in (("ocr", "ocr_0"), ("vision", "vision_0")):
                    arg = f"{modality}_derivation_id"
                    result = _body(
                        await client.call_tool("get_image_analysis", {**scope, arg: str(ids[key])})
                    )
                    item = result["items"][0]
                    assert item["attribution"]["notebook_id"] == str(notebook_id)
                    assert item["attribution"]["document_id"] == str(document_id)
                    assert item["attribution"]["version_id"] == str(version_id)
                    assert item["attribution"]["source_id"] == str(source_id)
                    assert item["attribution"]["derivation_id"] == str(ids[key])
                    assert item["attribution"]["generation_id"] == str(
                        ids[f"{modality}_generation"]
                    )
                    assert item["source_metadata"]["source_id"] == str(source_id)
                    assert item["kind"] == f"derived_{modality}"
                latest = _body(
                    await client.call_tool(
                        "get_image_analysis",
                        {**scope, "selection": "latest_ready", "modalities": ["ocr", "vision"]},
                    )
                )
                assert {item["attribution"]["derivation_id"] for item in latest["items"]} == {
                    str(ids["ocr_1"]),
                    str(ids["vision_0"]),
                }
                all_results = _body(
                    await client.call_tool(
                        "get_image_analysis",
                        {**scope, "selection": "all", "modalities": ["ocr", "vision"]},
                    )
                )
                assert {item["attribution"]["derivation_id"] for item in all_results["items"]} == {
                    str(ids["ocr_0"]),
                    str(ids["ocr_1"]),
                    str(ids["vision_0"]),
                }
                profiled = _body(
                    await client.call_tool(
                        "get_image_analysis",
                        {
                            **scope,
                            "selection": "all",
                            "modalities": ["ocr", "vision"],
                            "profile": "fixture-vision",
                        },
                    )
                )
                assert [item["attribution"]["derivation_id"] for item in profiled["items"]] == [
                    str(ids["vision_0"])
                ]
                for wrong_scope in (
                    {**scope, "notebook_id": str(other_notebook)},
                    {**scope, "occurrence_id": str(uuid4())},
                ):
                    denied = await client.call_tool(
                        "get_image_analysis",
                        {**wrong_scope, "ocr_derivation_id": str(ids["ocr_0"])},
                    )
                    assert denied.isError
                    error = json.loads(denied.content[0].text)["error"]
                    assert error["category"] == "not_found"
                    assert UUID(error["correlation_id"])
                    assert str(ids["ocr_0"]) not in str(denied.content)
                    assert "Persisted OCR" not in str(denied.content)
                unknown = await client.call_tool(
                    "get_image_analysis",
                    {
                        **scope,
                        "selection": "explicit",
                        "modalities": ["ocr"],
                        "ocr_derivation_id": str(uuid4()),
                    },
                )
                assert unknown.isError
                assert json.loads(unknown.content[0].text)["error"]["category"] == "not_found"
                pending = _body(
                    await client.call_tool(
                        "get_image_analysis",
                        {
                            **scope,
                            "selection": "explicit",
                            "modalities": ["ocr"],
                            "ocr_derivation_id": str(ids["pending"]),
                        },
                    )
                )
                assert pending["completeness"] == "unavailable"
                assert pending["items"] == []
                for invalid in (
                    {**scope, "selection": "bad", "modalities": ["ocr"]},
                    {**scope, "selection": "all", "modalities": ["bad"]},
                    {**scope, "selection": "all", "modalities": ["ocr"], "profile": ""},
                ):
                    rejected = await client.call_tool("get_image_analysis", invalid)
                    assert rejected.isError
                    assert (
                        json.loads(rejected.content[0].text)["error"]["category"] == "invalid_input"
                    )
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_mcp_chunk_reader_matrix(
    tmp_path: Path, legacy: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
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
                notebooks = _body(await client.call_tool("list_notebooks", {"limit": 2}))
                assert notebooks["total"] == 2
                invalid_limit = await client.call_tool("list_notebooks", {"limit": True})
                assert invalid_limit.isError
                assert json.loads(invalid_limit.content[0].text)["error"]["category"] == (
                    "invalid_input"
                )
                assert {item["notebook_id"] for item in notebooks["notebooks"]} == {
                    str(notebook_id),
                    str(other_notebook),
                }
                capabilities = await client.call_tool("get_capabilities", {})
                assert capabilities.isError
                capability_error = json.loads(capabilities.content[0].text)["error"]
                assert capability_error["category"] == "capability_unavailable"
                assert UUID(capability_error["correlation_id"])
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
                assert hit["source_metadata"]["source_id"] == str(source_id)
                assert hit["source_metadata"]["original_filename"] == "same-name.csv"
                assert hit["source_metadata"]["document_title"] == "Shared display title"
                assert hit["source_metadata"]["mime_type"] == "text/csv"
                assert hit["source_metadata"]["content_hash"] == f"{1:064x}"
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
                assert (
                    len({hit["source_metadata"]["source_id"] for hit in global_search["results"]})
                    == 2
                )
                assert {
                    hit["source_metadata"]["original_filename"] for hit in global_search["results"]
                } == {"same-name.csv"}
                summary = _body(
                    await client.call_tool(
                        "get_notebook_summary", {"notebook_id": str(notebook_id)}
                    )
                )
                assert summary["sources"][0]["source_metadata"]["source_id"] == str(source_id)
                insights = _body(
                    await client.call_tool(
                        "get_source_insights", {"source_id": str(source_id), "limit": 1}
                    )
                )
                assert insights["source_metadata"]["original_filename"] == "same-name.csv"
                assert insights["total"] == 1
                assert insights["insights"][0]["content"] == (
                    "Fixture schema evidence remains scoped"
                )
                bad_insight_limit = await client.call_tool(
                    "get_source_insights", {"source_id": str(source_id), "limit": True}
                )
                assert bad_insight_limit.isError
                assert json.loads(bad_insight_limit.content[0].text)["error"]["category"] == (
                    "invalid_input"
                )
                timeline = _body(
                    await client.call_tool(
                        "get_timeline", {"notebook_id": str(notebook_id), "limit": 1}
                    )
                )
                assert timeline["events"][0]["source_metadata"]["source_id"] == str(source_id)
                bad_timeline_limit = await client.call_tool(
                    "get_timeline", {"notebook_id": str(notebook_id), "limit": True}
                )
                assert bad_timeline_limit.isError
                assert json.loads(bad_timeline_limit.content[0].text)["error"]["category"] == (
                    "invalid_input"
                )
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
                assert query["citations"][0]["source_metadata"]["source_id"] == str(source_id)
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
                assert evidence["items"][0]["source_metadata"]["source_id"] == str(source_id)
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
                        "canonical_text:source_failure:contract.unsupported:PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA"
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
                assert exact["source_metadata"]["source_id"] == str(source_id)
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
                assert document["items"][0]["source_metadata"]["source_id"] == str(source_id)
                assert document["items"][0]["payload"]["text"] == chunk.text
                assert document["items"][0]["payload"]["exact_position"][
                    "overlapping_chunk_ids"
                ] == [chunk.id]
                occurrences = await reader.list_asset_occurrences(version_id)
                assert len(occurrences) == 1
                occurrence = occurrences[0]
                inventory = _body(
                    await client.call_tool(
                        "get_asset",
                        {
                            "notebook_id": str(notebook_id),
                            "document_id": str(document_id),
                            "version_id": str(version_id),
                            "limit": 1,
                        },
                    )
                )
                assert inventory["items"][0]["attribution"]["occurrence_id"] == str(
                    occurrence.occurrence_id
                )
                original_asset = await client.call_tool(
                    "get_asset",
                    {
                        "notebook_id": str(notebook_id),
                        "occurrence_id": str(occurrence.occurrence_id),
                    },
                )
                assert not original_asset.isError
                assert original_asset.content[0].meta["assetId"] == str(occurrence.asset_id)
                assert original_asset.content[0].meta["sourceId"] == str(source_id)
                assert (
                    original_asset.content[0].meta["contentHash"]
                    == hashlib.sha256(reader.assets[occurrence.asset_id]).hexdigest()
                )
                original_document = await client.call_tool(
                    "get_document",
                    {
                        "notebook_id": str(notebook_id),
                        "document_id": str(document_id),
                        "version_id": str(version_id),
                        "mode": "original",
                    },
                )
                assert not original_document.isError
                assert original_document.content[0].resource.meta["sourceMetadata"][
                    "version_id"
                ] == str(version_id)
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
                bad_error = json.loads(bad.content[0].text)["error"]
                assert bad_error["category"] == "not_found"
                assert bad_error["code"] == "contract.not_found"
                assert UUID(bad_error["correlation_id"])
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
                missing_error = json.loads(missing.content[0].text)["error"]
                assert missing_error["category"] == bad_error["category"]
                assert missing_error["code"] == bad_error["code"]
                assert missing_error["correlation_id"] != bad_error["correlation_id"]
                denied = await client.call_tool(
                    "search_all_notebooks",
                    {
                        "query": "schema",
                        "notebook_id": str(uuid4()),
                    },
                )
                assert denied.isError
                assert other_chunk.text not in str(denied.content)
                denied_error = json.loads(denied.content[0].text)["error"]
                assert denied_error["category"] == bad_error["category"]
                assert denied_error["message"] == bad_error["message"]

                async def failed_retrieval(*_args: object) -> None:
                    try:
                        raise StorageError("PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA")
                    except StorageError as origin:
                        raise PluginError("sq-2:sparse") from origin

                monkeypatch.setattr(mcp_server_module, "execute_mcp_tool", failed_retrieval)
                typed_failure = await client.call_tool("search_evidence", {"query": "schema"})
                assert typed_failure.isError
                failure = json.loads(typed_failure.content[0].text)["error"]
                assert failure["category"] == "schema_compatibility"
                assert failure["origin_code"] == "contract.storage"
                assert failure["reason"] == "PAGE_RANGE_UNAVAILABLE_FOR_CHUNK_SCHEMA"
                assert "sq-2:sparse" not in str(typed_failure.content)
                assert other_notebook != notebook_id
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_every_public_tool_rejects_client_owned_storage_selection(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, _ = await _fixture(tmp_path, legacy=legacy)
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                assert len((await client.list_tools()).tools) == 14
                for tool in mcp_tools.get_mcp_tools():
                    response = await client.call_tool(tool.name, {"db_path": "DUMMY_DO_NOT_USE"})
                    assert response.isError, tool.name
                    error = json.loads(response.content[0].text)["error"]
                    assert error["category"] == "invalid_input", tool.name
                    assert UUID(error["correlation_id"])
                    assert "DUMMY_DO_NOT_USE" not in str(response.content)
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_empty_notebook_and_asset_inventories(tmp_path: Path, legacy: bool) -> None:
    for label, options in (
        ("inventory", {"inventory_empty": True}),
        ("assets", {"asset_empty": True}),
    ):
        root = tmp_path / label
        root.mkdir()
        engine, reader, config, identities = await _fixture(root, legacy=legacy, **options)
        server = create_mcp_server(
            engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
        )
        c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
        s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
        try:
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(
                    server.run, c2s_recv, s2c_send, server.create_initialization_options()
                )
                async with ClientSession(s2c_recv, c2s_send) as client:
                    await client.initialize()
                    if label == "inventory":
                        listed = _body(await client.call_tool("list_notebooks", {"limit": 1}))
                        assert listed["notebooks"] == []
                        assert listed["total"] == 0
                    else:
                        notebook_id, document_id, version_id, _, _ = identities[1]
                        result = _body(
                            await client.call_tool(
                                "get_asset",
                                {
                                    "notebook_id": str(notebook_id),
                                    "document_id": str(document_id),
                                    "version_id": str(version_id),
                                    "limit": 1,
                                },
                            )
                        )
                        assert result["items"] == []
                        assert result["completeness"] == "complete"
                    tasks.cancel_scope.cancel()
        finally:
            await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_exhaustive_cursor_traverses_persisted_chunks(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy, cursor_ready=True)
    notebook_id, document_id, version_id, source_id, first_chunk = identities[0]
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    request = {
        "query": "schema",
        "mode": "exhaustive",
        "scope": {"notebook_id": str(notebook_id), "document_ids": [str(document_id)]},
        "representations": ["canonical_text"],
        "evidence_budget": 1,
    }
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                seen: list[str] = []
                for _ in range(3):
                    result = _body(await client.call_tool("search_evidence", request))
                    assert result["items"]
                    assert len(result["items"]) == 1
                    item = result["items"][0]
                    assert item["document_id"] == str(document_id)
                    assert item["version_id"] == str(version_id)
                    assert item["source_metadata"]["source_id"] == str(source_id)
                    assert item["locator"].get("page_start") == (
                        None if legacy else (3 if item["chunk_id"] == first_chunk.id else 4)
                    )
                    seen.append(item["chunk_id"])
                    cursor = result["next_cursor"]
                    if cursor is None:
                        assert result["completeness"] == "complete"
                        break
                    assert result["completeness"] == "truncated"
                    request = {**request, "cursor": cursor}
                assert set(seen) == {first_chunk.id, "3" * 64}
                assert len(seen) == 2
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_fourteen_tool_invalid_input_matrix(tmp_path: Path, legacy: bool) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, source_id, _ = identities[0]
    invalid = {
        "list_notebooks": {"limit": True},
        "get_notebook_summary": {"notebook_id": "malformed"},
        "get_timeline": {"notebook_id": str(notebook_id), "limit": True},
        "get_source_insights": {"source_id": str(source_id), "limit": True},
        "search_all_notebooks": {"query": ""},
        "query_notebook": {"notebook_id": str(notebook_id), "question": ""},
        "search_evidence": {"query": "schema", "mode": "invalid"},
        "get_capabilities": {"capability_ids": ["INVALID_CAPABILITY"]},
        "query_structured": {"operation": "invalid", "scope": {"notebook_id": str(notebook_id)}},
        "get_document": {
            "document_id": str(document_id),
            "version_id": str(version_id),
            "max_items": 0,
        },
        "get_document_chunk": {
            "notebook_id": str(notebook_id),
            "document_id": str(document_id),
            "version_id": str(version_id),
            "chunk_id": "malformed",
        },
        "get_asset": {"notebook_id": str(notebook_id), "limit": True},
        "get_image_analysis": {"notebook_id": str(notebook_id), "occurrence_id": "malformed"},
        "run_final_qa_v2": {"notebook_id": str(notebook_id)},
    }
    assert set(invalid) == {tool.name for tool in mcp_tools.get_mcp_tools()}
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                for name, args in invalid.items():
                    response = await client.call_tool(name, args)
                    assert response.isError, name
                    error = json.loads(response.content[0].text)["error"]
                    assert error["category"] == "invalid_input", (name, error)
                    assert UUID(error["correlation_id"])
                    assert "malformed" not in str(response.content)
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_invalid_cursors_and_excessive_budgets(tmp_path: Path, legacy: bool) -> None:
    engine, reader, config, identities = await _fixture(
        tmp_path, legacy=legacy, structured_ready=True
    )
    notebook_id, document_id, version_id, _, _ = identities[0]
    scope = {"notebook_id": str(notebook_id), "document_ids": [str(document_id)]}
    cases = (
        ("search_all_notebooks", {"query": "schema", "top_k": 101}),
        ("query_notebook", {"notebook_id": str(notebook_id), "question": "schema", "top_k": -1}),
        (
            "search_evidence",
            {
                "query": "schema",
                "mode": "exhaustive",
                "scope": scope,
                "representations": ["canonical_text"],
                "cursor": "not-a-signed-cursor",
            },
        ),
        (
            "search_evidence",
            {
                "query": "schema",
                "mode": "ranked",
                "scope": scope,
                "representations": ["canonical_text"],
                "evidence_budget": -1,
            },
        ),
        (
            "query_structured",
            {
                "operation": "describe",
                "scope": {"notebook_id": str(notebook_id), "version_ids": [str(version_id)]},
                "cursor": "not-a-signed-cursor",
            },
        ),
        (
            "get_document",
            {
                "notebook_id": str(notebook_id),
                "document_id": str(document_id),
                "version_id": str(version_id),
                "mode": "blocks",
                "cursor": "not-a-signed-cursor",
            },
        ),
        (
            "get_asset",
            {
                "notebook_id": str(notebook_id),
                "document_id": str(document_id),
                "version_id": str(version_id),
                "cursor": "not-a-signed-cursor",
            },
        ),
    )
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                for tool, arguments in cases:
                    response = await client.call_tool(tool, arguments)
                    assert response.isError, (tool, arguments)
                    error = json.loads(response.content[0].text)["error"]
                    assert error["category"] == "invalid_input", (tool, error)
                    assert UUID(error["correlation_id"])
                    assert "not-a-signed-cursor" not in response.content[0].text
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_resource_scope_nondisclosure_matrix(tmp_path: Path, legacy: bool) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy, analysis=True)
    _, document_id, version_id, source_id, chunk = identities[0]
    other_notebook, other_document, _, other_source, _ = identities[1]
    occurrence_id = reader.analysis_ids["occurrence"]
    unknown_notebook = str(UUID(int=999))
    cases = (
        ("get_notebook_summary", {"notebook_id": unknown_notebook}),
        ("get_timeline", {"notebook_id": unknown_notebook}),
        ("get_source_insights", {"source_id": str(UUID(int=999))}),
        ("search_all_notebooks", {"query": "schema", "notebook_id": unknown_notebook}),
        (
            "query_notebook",
            {"notebook_id": unknown_notebook, "question": "schema", "synthesize": False},
        ),
        (
            "search_evidence",
            {
                "query": "schema",
                "mode": "ranked",
                "scope": {"notebook_id": unknown_notebook},
                "representations": ["canonical_text"],
            },
        ),
        ("get_capabilities", {"notebook_id": unknown_notebook}),
        (
            "query_structured",
            {
                "operation": "describe",
                "scope": {"notebook_id": unknown_notebook, "version_ids": [str(version_id)]},
            },
        ),
        (
            "get_document",
            {
                "notebook_id": str(other_notebook),
                "document_id": str(document_id),
                "version_id": str(version_id),
                "mode": "blocks",
            },
        ),
        (
            "get_document_chunk",
            {
                "notebook_id": str(other_notebook),
                "document_id": str(document_id),
                "version_id": str(version_id),
                "chunk_id": chunk.id,
            },
        ),
        (
            "get_asset",
            {
                "notebook_id": str(other_notebook),
                "occurrence_id": str(occurrence_id),
            },
        ),
        (
            "get_image_analysis",
            {
                "notebook_id": str(other_notebook),
                "occurrence_id": str(occurrence_id),
                "ocr_derivation_id": str(reader.analysis_ids["ocr_0"]),
            },
        ),
    )
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                for tool, args in cases:
                    response = await client.call_tool(tool, args)
                    assert response.isError, tool
                    error = json.loads(response.content[0].text)["error"]
                    assert error["category"] == "not_found", (tool, error)
                    assert UUID(error["correlation_id"])
                    assert str(document_id) not in response.content[0].text
                    assert str(source_id) not in response.content[0].text
                    assert chunk.text not in response.content[0].text
                    assert str(other_document) not in response.content[0].text
                    assert str(other_source) not in response.content[0].text
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_valid_empty_and_scope_unavailable_matrix(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(
        tmp_path, legacy=legacy, empty_notebook=True
    )
    empty_id = str(UUID(int=1000))
    source_without_insights = str(identities[1][3])
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                inventory = _body(await client.call_tool("list_notebooks", {"limit": 10}))
                assert inventory["total"] == 3
                summary = _body(
                    await client.call_tool("get_notebook_summary", {"notebook_id": empty_id})
                )
                assert summary["status"] == "empty"
                assert summary["sources"] == []
                timeline = _body(await client.call_tool("get_timeline", {"notebook_id": empty_id}))
                assert timeline["events"] == []
                insights = _body(
                    await client.call_tool(
                        "get_source_insights", {"source_id": source_without_insights}
                    )
                )
                assert insights["insights"] == []
                search = _body(
                    await client.call_tool(
                        "search_all_notebooks", {"query": "unmatchedzzzz", "notebook_id": empty_id}
                    )
                )
                assert search["results"] == []
                query = _body(
                    await client.call_tool(
                        "query_notebook",
                        {"notebook_id": empty_id, "question": "unmatchedzzzz", "synthesize": False},
                    )
                )
                assert query["citations"] == []
                evidence = _body(
                    await client.call_tool(
                        "search_evidence",
                        {
                            "query": "unmatchedzzzz",
                            "mode": "ranked",
                            "scope": {"notebook_id": empty_id},
                            "representations": ["canonical_text"],
                        },
                    )
                )
                assert evidence["items"] == []
                assert evidence["completeness"] == "empty"
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_exact_chunk_reader_sql_failure_is_typed_and_sanitized(
    tmp_path: Path, legacy: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, _, chunk = identities[0]
    assert reader._db is not None
    original_execute = reader._db.execute
    secret = "C:/private/token.db SELECT * FROM secrets bearer_private_token"

    def fail_chunk_read(sql: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if "FROM chunks WHERE id = ?" in sql:
            raise sqlite3.OperationalError(secret)
        return original_execute(sql, *args, **kwargs)

    monkeypatch.setattr(reader._db, "execute", fail_chunk_read)
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                result = await client.call_tool(
                    "get_document_chunk",
                    {
                        "notebook_id": str(notebook_id),
                        "document_id": str(document_id),
                        "version_id": str(version_id),
                        "chunk_id": chunk.id,
                    },
                )
                assert result.isError
                error = json.loads(result.content[0].text)["error"]
                assert error["category"] == "retrieval_failure"
                assert error["code"] == "contract.storage"
                assert error["origin_code"] == "contract.storage"
                assert error["reason"] == "CHUNK_READ_FAILURE"
                assert error["layer"] == "storage"
                assert UUID(error["correlation_id"])
                assert secret not in str(result.content)
                tasks.cancel_scope.cancel()
        app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
        app.state.engine = engine
        app.state.server_config = config
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fixture",
            headers={"X-API-Key": "fixture-only-not-production"},
        ) as client:
            response = await client.get(
                f"/v2/notebooks/{notebook_id}/documents/{document_id}/"
                f"versions/{version_id}/chunks/{chunk.id}"
            )
        assert response.status_code == 503
        http_error = response.json()["error"]
        assert http_error["category"] == "retrieval_failure"
        assert http_error["origin_code"] == "contract.storage"
        assert http_error["reason"] == "CHUNK_READ_FAILURE"
        assert response.headers["X-Mnemo-Correlation-ID"] == http_error["correlation_id"]
        assert secret not in response.text
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_sparse_reader_failure_keeps_safe_origin(
    tmp_path: Path, legacy: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id = identities[0][0]
    assert reader._db is not None
    original_execute = reader._db.execute
    secret = "C:/private/token.db SELECT * FROM secrets bearer_private_token"

    def fail_sparse(sql: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if "WITH sparse_candidates" in sql:
            raise sqlite3.OperationalError(secret)
        return original_execute(sql, *args, **kwargs)

    monkeypatch.setattr(reader._db, "execute", fail_sparse)
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                search = await client.call_tool(
                    "search_all_notebooks",
                    {"query": "schema", "top_k": 2, "notebook_id": str(notebook_id)},
                )
                assert search.isError
                error = json.loads(search.content[0].text)["error"]
                assert error["category"] == "retrieval_failure"
                assert error["reason"] == "CHUNK_READ_FAILURE"
                assert error["origin_code"] == "contract.storage"
                assert error["layer"] == "storage"
                assert UUID(error["correlation_id"])
                assert secret not in str(search.content)
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_advanced_reader_partial_result_has_safe_reason(
    tmp_path: Path, legacy: bool, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id = identities[0][0]
    assert reader._db is not None
    original_execute = reader._db.execute
    secret = "C:/private/token.db SELECT * FROM secrets bearer_private_token"

    def fail_canonical(sql: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if "SELECT c.id,MIN(s.source_id),dv.metadata" in sql:
            raise sqlite3.OperationalError(secret)
        return original_execute(sql, *args, **kwargs)

    monkeypatch.setattr(reader._db, "execute", fail_canonical)
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with ClientSession(s2c_recv, c2s_send) as client:
                await client.initialize()
                result = _body(
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
                assert result["completeness"] == "unknown"
                assert result["items"] == []
                assert result["omissions"] == [
                    "canonical_text:source_failure:contract.storage:CHUNK_READ_FAILURE"
                ]
                assert secret not in json.dumps(result)
                assert secret not in caplog.text
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
@pytest.mark.parametrize("operation", ["exact_list", "snapshot", "rows", "adjacent"])
async def test_compatible_reader_sql_boundaries_preserve_typed_failure(
    tmp_path: Path, legacy: bool, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, reader, _, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, _, chunk = identities[0]
    scope = RetrievalScopeV2(notebook_id=notebook_id)
    assert reader._db is not None
    original_execute = reader._db.execute
    patterns = {
        "exact_list": "WHERE document_id = ? AND version_id = ?",
        "snapshot": "SELECT c.id,MIN(s.source_id),dv.metadata",
        "rows": "SELECT c.id,c.document_id",
        "adjacent": "SELECT id FROM chunks WHERE document_id=? AND version_id=?",
    }

    def fail_read(sql: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if patterns[operation] in sql:
            raise sqlite3.OperationalError("C:/private/token.db SELECT * FROM secrets")
        return original_execute(sql, *args, **kwargs)

    monkeypatch.setattr(reader._db, "execute", fail_read)
    try:
        with pytest.raises(StorageError, match=r"^CHUNK_READ_FAILURE$"):
            if operation == "exact_list":
                await reader.list_exact_document_chunks(
                    document_id=document_id, version_id=version_id
                )
            elif operation == "snapshot":
                await reader.advanced_canonical_snapshot(
                    scope=scope, position=PositionalScopeV2(), query="schema"
                )
            elif operation == "rows":
                await reader.enumerate_advanced_canonical(
                    scope=scope, position=PositionalScopeV2(), query="schema", offset=0, limit=2
                )
            else:
                await reader.expand_advanced_canonical(
                    scope=scope, seed_chunk_ids=(chunk.id,), include_parents=False, limit=2
                )
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_http_metadata_envelope_matches_public_mcp_schema(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, source_id, chunk = identities[0]
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fixture",
            headers={"X-API-Key": "fixture-only-not-production"},
        ) as client:
            delivery = await client.get(
                f"/v2/notebooks/{notebook_id}/documents/{document_id}/"
                f"versions/{version_id}/chunks/{chunk.id}"
            )
            assert delivery.status_code == 200, delivery.text
            item = delivery.json()["items"][0]
            assert item["source_metadata"]["source_id"] == str(source_id)
            assert item["source_metadata"]["original_filename"] == "same-name.csv"
            evidence = await client.post(
                "/v2/retrieval/evidence",
                json={
                    "query": "schema",
                    "mode": "exhaustive",
                    "scope": {"notebook_id": str(notebook_id)},
                    "representations": ["canonical_text"],
                    "evidence_budget": 2,
                },
            )
            assert evidence.status_code == 200, evidence.text
            assert evidence.json()["items"][0]["source_metadata"]["source_id"] == str(source_id)

            unknown = await client.get(
                f"/v2/notebooks/{uuid4()}/documents/{document_id}/"
                f"versions/{version_id}/chunks/{chunk.id}"
            )
            mismatched = await client.get(
                f"/v2/notebooks/{notebook_id}/documents/{identities[1][1]}/"
                f"versions/{version_id}/chunks/{chunk.id}"
            )
            missing_chunk = await client.get(
                f"/v2/notebooks/{notebook_id}/documents/{document_id}/"
                f"versions/{version_id}/chunks/{'f' * 64}"
            )
            for denied in (unknown, mismatched, missing_chunk):
                assert denied.status_code in {400, 404}
                assert "source_metadata" not in denied.text
                assert "same-name.csv" not in denied.text
                assert chunk.text not in denied.text
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_http_and_mcp_exact_reader_provenance_and_scope_agree(
    tmp_path: Path, legacy: bool
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, source_id, chunk = identities[0]
    server = create_mcp_server(
        engine, config=config, principal_provider=lambda: PrincipalContextV1(uuid4(), True)
    )
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    c2s_send, c2s_recv = anyio.create_memory_object_stream(20)
    s2c_send, s2c_recv = anyio.create_memory_object_stream(20)
    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, c2s_recv, s2c_send, server.create_initialization_options())
            async with (
                ClientSession(s2c_recv, c2s_send) as mcp,
                AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://fixture",
                    headers={"X-API-Key": "fixture-only-not-production"},
                ) as http,
            ):
                await mcp.initialize()
                arguments = {
                    "notebook_id": str(notebook_id),
                    "document_id": str(document_id),
                    "version_id": str(version_id),
                    "chunk_id": chunk.id,
                }
                mcp_chunk = _body(await mcp.call_tool("get_document_chunk", arguments))
                http_chunk = await http.get(
                    f"/v2/notebooks/{notebook_id}/documents/{document_id}/"
                    f"versions/{version_id}/chunks/{chunk.id}"
                )
                assert http_chunk.status_code == 200
                http_chunk_body = http_chunk.json()
                for body in (mcp_chunk, http_chunk_body):
                    item = body["items"][0]
                    assert item["payload"]["id"] == chunk.id
                    assert item["attribution"]["source_id"] == str(source_id)
                    assert item["attribution"]["document_id"] == str(document_id)
                    assert item["attribution"]["version_id"] == str(version_id)
                    assert item["source_metadata"]["original_filename"] == "same-name.csv"
                    assert item["payload"]["position"]["page_start"] == (None if legacy else 3)
                request = {
                    "query": "schema",
                    "mode": "exhaustive",
                    "scope": {"notebook_id": str(notebook_id)},
                    "representations": ["canonical_text"],
                    "evidence_budget": 2,
                }
                mcp_evidence = _body(await mcp.call_tool("search_evidence", request))
                http_evidence = await http.post("/v2/retrieval/evidence", json=request)
                assert http_evidence.status_code == 200
                for body in (mcp_evidence, http_evidence.json()):
                    assert body["items"][0]["chunk_id"] == chunk.id
                    assert body["items"][0]["source_metadata"]["source_id"] == str(source_id)
                    assert body["items"][0]["representation"] == "canonical_text"
                    assert body["completeness"] == mcp_evidence["completeness"]
                unknown = str(uuid4())
                mcp_denied = await mcp.call_tool(
                    "get_document_chunk", {**arguments, "notebook_id": unknown}
                )
                http_denied = await http.get(
                    f"/v2/notebooks/{unknown}/documents/{document_id}/"
                    f"versions/{version_id}/chunks/{chunk.id}"
                )
                assert mcp_denied.isError
                assert http_denied.status_code == 404
                mcp_error = json.loads(mcp_denied.content[0].text)["error"]
                http_error = http_denied.json()["error"]
                assert mcp_error["category"] == http_error["category"] == "not_found"
                assert UUID(mcp_error["correlation_id"])
                assert UUID(http_error["correlation_id"])
                assert chunk.text not in str(mcp_denied.content)
                assert chunk.text not in http_denied.text
                tasks.cancel_scope.cancel()
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_public_mcp_binary_asset_and_document_metadata(
    tmp_path: Path, legacy: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, source_id, _ = identities[0]
    principal = PrincipalContextV1(uuid4(), True)
    content = b"\x89PNG\r\n\x1a\nfixture"
    attribution = DeliveryAttribution(
        notebook_id=notebook_id,
        source_id=source_id,
        document_id=document_id,
        version_id=version_id,
        asset_id=uuid4(),
        occurrence_id=uuid4(),
        modality="image",
    )

    def binary(kind: DeliveryResourceKind) -> BinaryDelivery:
        return BinaryDelivery(
            resource_kind=kind,
            attribution=attribution,
            snapshot_identity="d" * 64,
            content=content,
            media_type="image/png",
            content_hash=hashlib.sha256(content).hexdigest(),
            total_byte_size=len(content),
            range_start=0,
            completeness=DeliveryCompleteness.COMPLETE,
        )

    service = MagicMock()
    service.get_asset = AsyncMock(return_value=binary(DeliveryResourceKind.ASSET))
    service.get_original_document = AsyncMock(return_value=binary(DeliveryResourceKind.DOCUMENT))
    monkeypatch.setattr(mcp_tools, "_delivery_service", lambda *_: service)
    try:
        asset = await mcp_tools.execute_mcp_tool(
            engine,
            "get_asset",
            {"notebook_id": str(notebook_id), "occurrence_id": str(attribution.occurrence_id)},
            config,
            principal,
        )
        assert asset[0].type == "image"
        assert asset[0].meta["sourceMetadata"]["source_id"] == str(source_id)
        document = await mcp_tools.execute_mcp_tool(
            engine,
            "get_document",
            {
                "notebook_id": str(notebook_id),
                "document_id": str(document_id),
                "version_id": str(version_id),
                "mode": "original",
            },
            config,
            principal,
        )
        assert document[0].type == "resource"
        assert document[0].resource.meta["sourceMetadata"]["version_id"] == str(version_id)
    finally:
        await reader.close()


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [True, False], ids=["certified-older", "newer"])
async def test_http_original_binary_contract_does_not_claim_json_metadata(
    tmp_path: Path, legacy: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, reader, config, identities = await _fixture(tmp_path, legacy=legacy)
    notebook_id, document_id, version_id, source_id, _ = identities[0]
    content = b"disposable original bytes"
    result = BinaryDelivery(
        resource_kind=DeliveryResourceKind.DOCUMENT,
        attribution=DeliveryAttribution(
            notebook_id=notebook_id,
            source_id=source_id,
            document_id=document_id,
            version_id=version_id,
            modality="text",
        ),
        snapshot_identity="d" * 64,
        content=content,
        media_type="text/plain",
        content_hash=hashlib.sha256(content).hexdigest(),
        total_byte_size=len(content),
        range_start=0,
        completeness=DeliveryCompleteness.COMPLETE,
    )
    service = MagicMock()
    service.get_original_document = AsyncMock(return_value=result)
    monkeypatch.setattr(delivery_router, "build_delivery_service", lambda *_: service)
    app = create_app(server_config=config, engine=engine, provision_tokenizer_on_startup=False)
    app.state.engine = engine
    app.state.server_config = config
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fixture",
            headers={"X-API-Key": "fixture-only-not-production"},
        ) as client:
            response = await client.get(
                f"/v2/notebooks/{notebook_id}/documents/{document_id}/"
                f"versions/{version_id}/original"
            )
            assert response.status_code == 200
            assert response.content == content
            assert response.headers["x-mnemo-source-id"] == str(source_id)
            assert response.headers["x-mnemo-content-sha256"] == result.content_hash
            assert response.headers["content-disposition"] == (
                f'attachment; filename="document-{document_id}"'
            )
            assert "source_metadata" not in response.headers
    finally:
        await reader.close()
