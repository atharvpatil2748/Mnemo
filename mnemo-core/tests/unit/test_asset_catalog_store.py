"""SQLite Phase 8.5.1 catalog, lifecycle, isolation, and rollback tests."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict
from uuid import UUID, uuid4

import pytest
from mnemo.interfaces.errors import ConflictError, ContractValidationError, IntegrityError
from mnemo.models import (
    Asset,
    AssetContainerKind,
    AssetDerivation,
    AssetDerivationStatus,
    AssetExtractionProvenance,
    AssetLocator,
    AssetLocatorKind,
    AssetOccurrence,
    Document,
    DocumentBinaryAvailability,
    DocumentBinaryReference,
    DocumentBinaryRole,
    DocumentMetadata,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    FrozenMetadata,
    IndexGeneration,
    IndexGenerationState,
    Notebook,
    Source,
    asset_derivation_id,
    asset_occurrence_id,
)
from mnemo.phase85.projections import ProjectionBuildResult, ProjectionCoverage
from mnemo.storage.sqlite import SQLiteStore


class _IngestionCall(TypedDict):
    assets: tuple[Asset, ...]
    binary_reference: DocumentBinaryReference
    occurrences: tuple[AssetOccurrence, ...]


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _document(document_id: UUID, version_id: UUID, now: datetime) -> Document:
    metadata = DocumentMetadata(content_hash="a" * 64)
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        content_hash=metadata.content_hash,
        metadata=metadata,
        status=DocumentVersionStatus.CURRENT,
        created_at=now,
    )
    return Document(
        document_id=document_id,
        versions=(version,),
        current_version_id=version_id,
        current_hash=metadata.content_hash,
        status=DocumentStatus.INDEXED,
        created_at=now,
        updated_at=now,
    )


def _records(
    now: datetime,
) -> tuple[UUID, UUID, UUID, Asset, AssetOccurrence, DocumentBinaryReference]:
    document_id, version_id, notebook_id = uuid4(), uuid4(), uuid4()
    asset = Asset(
        asset_id=uuid4(),
        mime_type="image/png",
        content_hash="b" * 64,
        storage_uri="blob://opaque",
        metadata=FrozenMetadata({"safe": True}),
    )
    locator = AssetLocator(kind=AssetLocatorKind.PDF_PAGE, ordinal=0, page_number=1)
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
        authored_alt_text="Diagram",
        extraction_provenance=AssetExtractionProvenance(
            parser_id="mnemo.pdf", parser_version="v1", block_ordinal=0
        ),
        created_at=now,
    )
    reference = DocumentBinaryReference(
        document_id=document_id,
        version_id=version_id,
        asset_id=asset.asset_id,
        role=DocumentBinaryRole.ORIGINAL,
        media_type="image/png",
        byte_size=8,
        created_at=now,
    )
    return document_id, version_id, notebook_id, asset, occurrence, reference


def test_catalog_round_trip_idempotency_isolation_and_gc(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "catalog.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    document_id, version_id, notebook_id, asset, occurrence, reference = _records(now)
    _run(store.upsert_document(_document(document_id, version_id, now)))
    _run(
        store.upsert_notebook(
            Notebook(
                notebook_id=notebook_id,
                title="N",
                description=None,
                created_at=now,
                updated_at=now,
            )
        )
    )
    source = Source(
        source_id=uuid4(), notebook_id=notebook_id, document_id=document_id, created_at=now
    )
    _run(store.upsert_source(source))

    _run(
        store.register_asset_ingestion(
            assets=(asset,), binary_reference=reference, occurrences=(occurrence,)
        )
    )
    _run(
        store.register_asset_ingestion(
            assets=(asset,),
            binary_reference=replace(reference, created_at=datetime.now(UTC)),
            occurrences=(replace(occurrence, created_at=datetime.now(UTC)),),
        )
    )
    persisted_asset = _run(store.get_asset_record(asset.asset_id))
    assert persisted_asset is not None
    assert persisted_asset.content_hash == asset.content_hash
    assert _run(store.get_document_binary_reference(version_id)) == reference
    assert (
        _run(store.get_document_binary_availability(version_id))
        is DocumentBinaryAvailability.AVAILABLE
    )
    assert (
        _run(store.get_document_binary_availability(uuid4()))
        is DocumentBinaryAvailability.UNAVAILABLE
    )
    assert _run(store.list_asset_occurrences(version_id)) == (occurrence,)
    assert (
        _run(
            store.get_authorized_asset_occurrence(
                notebook_id=notebook_id, occurrence_id=occurrence.occurrence_id
            )
        )
        == occurrence
    )
    assert (
        _run(
            store.get_authorized_asset_occurrence(
                notebook_id=uuid4(), occurrence_id=occurrence.occurrence_id
            )
        )
        is None
    )
    _run(store.delete_source(source.source_id))
    assert (
        _run(
            store.get_authorized_asset_occurrence(
                notebook_id=notebook_id, occurrence_id=occurrence.occurrence_id
            )
        )
        is None
    )
    assert _run(store.is_asset_referenced(asset.asset_id)) is True
    with pytest.raises(ConflictError):
        _run(store.delete_asset_catalog_record(asset.asset_id))
    _run(store.add_asset_gc_reference(asset.asset_id, "job", "job-1"))
    _run(store.remove_asset_gc_reference(asset.asset_id, "job", "job-1"))
    _run(store.close())


def test_authorized_derivation_inventory_is_occurrence_scoped(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "derivation-inventory.db")
    _run(store.open())
    now = datetime(2026, 8, 27, tzinfo=UTC)
    document_id, version_id, notebook_id, asset, occurrence, reference = _records(now)
    _run(store.upsert_document(_document(document_id, version_id, now)))
    _run(
        store.upsert_notebook(
            Notebook(
                notebook_id=notebook_id,
                title="N",
                description=None,
                created_at=now,
                updated_at=now,
            )
        )
    )
    second_notebook_id = uuid4()
    _run(
        store.upsert_notebook(
            Notebook(
                notebook_id=second_notebook_id,
                title="Shared",
                description=None,
                created_at=now,
                updated_at=now,
            )
        )
    )
    for scoped_notebook_id in (notebook_id, second_notebook_id):
        _run(
            store.upsert_source(
                Source(
                    source_id=uuid4(),
                    notebook_id=scoped_notebook_id,
                    document_id=document_id,
                    created_at=now,
                )
            )
        )
    _run(
        store.register_asset_ingestion(
            assets=(asset,), binary_reference=reference, occurrences=(occurrence,)
        )
    )
    generation = _generation(now, "6" * 64)
    _run(store.create_index_generation(generation))
    _run(
        store.transition_index_generation(
            generation.generation_id,
            IndexGenerationState.BUILDING,
            IndexGenerationState.READY,
            item_count=1,
            checksum="7" * 64,
        )
    )
    derivation = AssetDerivation(
        derivation_id=uuid4(),
        occurrence_id=occurrence.occurrence_id,
        operation="ocr",
        provider_identity="local-ocr",
        model_identity="ocr-v1",
        configuration_digest="8" * 64,
        output_asset_id=None,
        output_payload=FrozenMetadata(),
        status=AssetDerivationStatus.PENDING,
        confidence=None,
        language=None,
        created_at=now,
        updated_at=now,
    )
    _run(store.create_asset_derivation(derivation))
    _run(
        store.transition_asset_derivation(
            derivation.derivation_id,
            AssetDerivationStatus.PENDING,
            AssetDerivationStatus.RUNNING,
        )
    )
    _run(
        store.transition_asset_derivation(
            derivation.derivation_id,
            AssetDerivationStatus.RUNNING,
            AssetDerivationStatus.SUCCEEDED,
            output_payload_json="{}",
            confidence=0.91,
            language="mr",
        )
    )
    db = store._require_open()
    _run(
        db.execute(
            """INSERT INTO ocr_results (
                   derivation_id,cache_key,document_id,version_id,occurrence_id,asset_id,
                   generation_id,provider_metadata,preprocessing_digest,completeness,
                   pages_submitted,pages_succeeded,content_hash,warnings,schema_version,created_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(derivation.derivation_id),
                "9" * 64,
                str(document_id),
                str(version_id),
                str(occurrence.occurrence_id),
                str(asset.asset_id),
                str(generation.generation_id),
                "{}",
                "a" * 64,
                "complete",
                1,
                1,
                "b" * 64,
                "[]",
                1,
                now.isoformat(),
            ),
        )
    )
    _run(db.commit())

    descriptors = _run(
        store.list_authorized_asset_derivations(
            notebook_id=notebook_id, occurrence_id=occurrence.occurrence_id
        )
    )
    assert len(descriptors) == 1
    assert descriptors[0].derivation_id == derivation.derivation_id
    assert descriptors[0].generation_state == "ready"
    assert descriptors[0].result_available is True
    assert descriptors[0].language == "mr"
    assert descriptors[0].ready is True
    assert (
        len(
            _run(
                store.list_authorized_asset_derivations(
                    notebook_id=second_notebook_id,
                    occurrence_id=occurrence.occurrence_id,
                )
            )
        )
        == 1
    )
    assert (
        _run(
            store.list_authorized_asset_derivations(
                notebook_id=uuid4(), occurrence_id=occurrence.occurrence_id
            )
        )
        == ()
    )
    _run(store.close())


def test_catalog_registration_rolls_back_and_rejects_identity_mutation(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "rollback.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    document_id, version_id, _, asset, occurrence, reference = _records(now)
    _run(store.upsert_document(_document(document_id, version_id, now)))
    missing_asset_occurrence = replace(occurrence, asset_id=uuid4())
    with pytest.raises(ContractValidationError):
        _run(
            store.register_asset_ingestion(
                assets=(asset,),
                binary_reference=reference,
                occurrences=(missing_asset_occurrence,),
            )
        )
    assert _run(store.get_asset_record(asset.asset_id)) is None
    _run(
        store.register_asset_ingestion(
            assets=(asset,), binary_reference=reference, occurrences=(occurrence,)
        )
    )
    changed = replace(asset, mime_type="image/jpeg")
    with pytest.raises(ConflictError):
        _run(
            store.register_asset_ingestion(
                assets=(changed,), binary_reference=reference, occurrences=(occurrence,)
            )
        )
    persisted_asset = _run(store.get_asset_record(asset.asset_id))
    assert persisted_asset is not None
    assert persisted_asset.mime_type == "image/png"
    assert _run(store.get_asset_occurrence(occurrence.occurrence_id)) == occurrence
    _run(store.close())


def test_derivation_and_generation_lifecycle(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "lifecycle.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    document_id, version_id, _, asset, occurrence, reference = _records(now)
    _run(store.upsert_document(_document(document_id, version_id, now)))
    _run(
        store.register_asset_ingestion(
            assets=(asset,), binary_reference=reference, occurrences=(occurrence,)
        )
    )
    derivation = AssetDerivation(
        derivation_id=asset_derivation_id(
            occurrence_id=occurrence.occurrence_id,
            operation="foundation-test",
            provider_identity="local",
            model_identity="none",
            configuration_digest="c" * 64,
        ),
        occurrence_id=occurrence.occurrence_id,
        operation="foundation-test",
        provider_identity="local",
        model_identity="none",
        configuration_digest="c" * 64,
        output_asset_id=None,
        output_payload=FrozenMetadata(),
        status=AssetDerivationStatus.PENDING,
        confidence=None,
        language=None,
        created_at=now,
        updated_at=now,
    )
    assert _run(store.create_asset_derivation(derivation)) is True
    assert _run(store.create_asset_derivation(derivation)) is False
    assert _run(
        store.transition_asset_derivation(
            derivation.derivation_id,
            AssetDerivationStatus.PENDING,
            AssetDerivationStatus.RUNNING,
        )
    )
    assert _run(
        store.transition_asset_derivation(
            derivation.derivation_id,
            AssetDerivationStatus.RUNNING,
            AssetDerivationStatus.SUCCEEDED,
            output_payload_json='{"result":"opaque"}',
            confidence=0.9,
            language="en",
        )
    )
    stored = _run(store.get_asset_derivation(derivation.derivation_id))
    assert stored is not None
    assert stored.status is AssetDerivationStatus.SUCCEEDED
    assert stored.output_payload["result"] == "opaque"

    first = _generation(now, "a" * 64)
    second = _generation(now, "b" * 64)
    for generation in (first, second):
        assert _run(store.create_index_generation(generation))
        assert _run(
            store.transition_index_generation(
                generation.generation_id,
                IndexGenerationState.BUILDING,
                IndexGenerationState.READY,
                item_count=5,
                checksum="d" * 64,
            )
        )
    assert _run(store.get_active_index_generation("asset_metadata", "baseline")) is None
    assert _run(store.promote_index_generation(first.generation_id))
    assert _run(store.promote_index_generation(second.generation_id))
    active = _run(store.get_active_index_generation("asset_metadata", "baseline"))
    superseded = _run(store.get_index_generation(first.generation_id))
    assert active is not None and active.generation_id == second.generation_id
    assert superseded is not None and superseded.state is IndexGenerationState.SUPERSEDED
    with pytest.raises(ContractValidationError):
        _run(
            store.transition_index_generation(
                second.generation_id,
                IndexGenerationState.READY,
                IndexGenerationState.BUILDING,
            )
        )
    with pytest.raises(ContractValidationError):
        _run(
            store.transition_asset_derivation(
                derivation.derivation_id,
                AssetDerivationStatus.SUCCEEDED,
                AssetDerivationStatus.RUNNING,
            )
        )
    with pytest.raises(ContractValidationError):
        _run(
            store.transition_asset_derivation(
                uuid4(),
                AssetDerivationStatus.RUNNING,
                AssetDerivationStatus.SUCCEEDED,
            )
        )
    _run(store.close())


def test_unreferenced_secondary_asset_can_be_collected(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "gc.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    document_id, version_id, _, asset, occurrence, reference = _records(now)
    secondary = replace(
        asset,
        asset_id=uuid4(),
        content_hash="e" * 64,
        storage_uri="blob://secondary",
    )
    _run(store.upsert_document(_document(document_id, version_id, now)))
    _run(
        store.register_asset_ingestion(
            assets=(asset, secondary),
            binary_reference=reference,
            occurrences=(occurrence,),
        )
    )
    assert _run(store.is_asset_referenced(secondary.asset_id)) is False
    assert _run(store.delete_asset_catalog_record(secondary.asset_id)) is True
    assert _run(store.get_asset_record(secondary.asset_id)) is None
    _run(store.close())


def test_catalog_rejects_invalid_batches_and_missing_references(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "invalid.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    document_id, version_id, _, asset, occurrence, reference = _records(now)
    _run(store.upsert_document(_document(document_id, version_id, now)))
    invalid_calls: tuple[_IngestionCall, ...] = (
        {"assets": (), "binary_reference": reference, "occurrences": ()},
        {
            "assets": (asset, asset),
            "binary_reference": reference,
            "occurrences": (occurrence,),
        },
        {
            "assets": (asset,),
            "binary_reference": reference,
            "occurrences": (replace(occurrence, document_id=uuid4()),),
        },
    )
    for call in invalid_calls:
        with pytest.raises(ContractValidationError):
            _run(store.register_asset_ingestion(**call))
    with pytest.raises(IntegrityError):
        _run(
            store.register_asset_ingestion(
                assets=(asset,),
                binary_reference=replace(reference, version_id=uuid4()),
                occurrences=(),
            )
        )
    assert _run(store.get_asset_occurrence(uuid4())) is None
    with pytest.raises(IntegrityError):
        _run(store.add_asset_gc_reference(uuid4(), "job", "missing"))
    with pytest.raises(ContractValidationError):
        _run(store.add_asset_gc_reference(asset.asset_id, "", "bad"))
    _run(store.close())


def test_derivation_validation_conflict_and_terminal_states(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "derivation-errors.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    document_id, version_id, _, asset, occurrence, reference = _records(now)
    _run(store.upsert_document(_document(document_id, version_id, now)))
    _run(
        store.register_asset_ingestion(
            assets=(asset,), binary_reference=reference, occurrences=(occurrence,)
        )
    )
    derivation = AssetDerivation(
        derivation_id=uuid4(),
        occurrence_id=occurrence.occurrence_id,
        operation="classify",
        provider_identity="local",
        model_identity="model",
        configuration_digest="9" * 64,
        output_asset_id=None,
        output_payload=FrozenMetadata(),
        status=AssetDerivationStatus.PENDING,
        confidence=None,
        language=None,
        created_at=now,
        updated_at=now,
    )
    assert _run(store.create_asset_derivation(derivation))
    with pytest.raises(ConflictError):
        _run(store.create_asset_derivation(replace(derivation, derivation_id=uuid4())))
    assert _run(
        store.transition_asset_derivation(
            derivation.derivation_id,
            AssetDerivationStatus.PENDING,
            AssetDerivationStatus.RUNNING,
        )
    )
    for payload in (None, "not-json", "[]"):
        with pytest.raises(ContractValidationError):
            _run(
                store.transition_asset_derivation(
                    derivation.derivation_id,
                    AssetDerivationStatus.RUNNING,
                    AssetDerivationStatus.SUCCEEDED,
                    output_payload_json=payload,
                )
            )
    assert _run(
        store.transition_asset_derivation(
            derivation.derivation_id,
            AssetDerivationStatus.RUNNING,
            AssetDerivationStatus.FAILED,
        )
    )
    assert _run(store.get_asset_derivation(uuid4())) is None
    _run(store.close())


def test_generation_fails_closed_and_promotes_idempotently(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "generation-errors.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    building = _generation(now, "7" * 64)
    assert _run(store.create_index_generation(building))
    assert _run(store.create_index_generation(building)) is False
    assert _run(store.promote_index_generation(building.generation_id)) is False
    with pytest.raises(ContractValidationError):
        _run(store.create_index_generation(replace(building, state=IndexGenerationState.READY)))
    with pytest.raises(ContractValidationError):
        _run(
            store.transition_index_generation(
                building.generation_id,
                IndexGenerationState.BUILDING,
                IndexGenerationState.READY,
            )
        )
    assert _run(
        store.transition_index_generation(
            building.generation_id,
            IndexGenerationState.BUILDING,
            IndexGenerationState.FAILED,
        )
    )
    assert _run(
        store.transition_index_generation(
            building.generation_id,
            IndexGenerationState.FAILED,
            IndexGenerationState.RETIRED,
        )
    )
    assert _run(store.get_index_generation(uuid4())) is None
    _run(store.close())


def _generation(now: datetime, digest: str) -> IndexGeneration:
    return IndexGeneration(
        generation_id=uuid4(),
        capability="asset_metadata",
        profile="baseline",
        schema_version=1,
        input_scope="all",
        provider_identity=None,
        model_identity=None,
        configuration_digest=digest,
        dimensions=None,
        state=IndexGenerationState.BUILDING,
        item_count=0,
        checksum=None,
        created_at=now,
        updated_at=now,
    )


def test_generation_set_requires_complete_coverage_and_unique_capabilities(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "atomic-generations.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    first = _generation(now, "a" * 64)
    second = _generation(now, "b" * 64)
    for generation in (first, second):
        assert _run(store.create_index_generation(generation))
        assert _run(
            store.transition_index_generation(
                generation.generation_id,
                IndexGenerationState.BUILDING,
                IndexGenerationState.READY,
                item_count=5,
                checksum="d" * 64,
            )
        )
    with pytest.raises(ValueError, match="nonempty and unique"):
        _run(store.promote_index_generation_set(()))
    with pytest.raises(ValueError, match="nonempty and unique"):
        _run(store.promote_index_generation_set((first.generation_id, first.generation_id)))
    assert not _run(store.promote_index_generation_set((first.generation_id,)))
    assert _run(store.get_active_index_generation("asset_metadata", "baseline")) is None
    _run(store.close())

    # The coverage writer requires BUILDING state; keep this fixture faithful to
    # the actual build lifecycle rather than inserting a fake READY manifest.
    store = SQLiteStore(tmp_path / "complete-generations.db")
    _run(store.open())
    ready = (
        _generation(now, "c" * 64),
        _generation(now, "e" * 64),
    )
    for generation in ready:
        assert _run(store.create_index_generation(generation))
        coverage = ProjectionCoverage.from_result(
            generation.generation_id,
            ProjectionBuildResult(
                expected_count=5,
                succeeded_count=5,
                failed_count=0,
                skipped_count=0,
                checksum="d" * 64,
            ),
            updated_at=now,
        )
        assert _run(store.put_index_generation_coverage(coverage))
        assert _run(
            store.transition_index_generation(
                generation.generation_id,
                IndexGenerationState.BUILDING,
                IndexGenerationState.READY,
                item_count=5,
                checksum="d" * 64,
            )
        )
    assert not _run(store.promote_index_generation_set(tuple(g.generation_id for g in ready)))
    assert _run(store.get_active_index_generation("asset_metadata", "baseline")) is None
    _run(store.close())


def test_generation_set_promotes_only_compatible_complete_ready_generations(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "compatible-generations.db")
    _run(store.open())
    now = datetime(2026, 8, 24, tzinfo=UTC)
    previous = _generation(now, "a" * 64)
    canonical = _generation(now, "b" * 64)
    ocr = replace(_generation(now, "c" * 64), capability="ocr")
    for generation in (previous, canonical, ocr):
        assert _run(store.create_index_generation(generation))
        assert _run(
            store.put_index_generation_coverage(
                ProjectionCoverage.from_result(
                    generation.generation_id,
                    ProjectionBuildResult(
                        expected_count=5,
                        succeeded_count=5,
                        failed_count=0,
                        skipped_count=0,
                        checksum="d" * 64,
                    ),
                    updated_at=now,
                )
            )
        )
        assert _run(
            store.transition_index_generation(
                generation.generation_id,
                IndexGenerationState.BUILDING,
                IndexGenerationState.READY,
                item_count=5,
                checksum="d" * 64,
            )
        )
    assert _run(store.promote_index_generation(previous.generation_id))
    assert _run(store.promote_index_generation_set((canonical.generation_id, ocr.generation_id)))
    active_canonical = _run(store.get_active_index_generation("asset_metadata", "baseline"))
    active_ocr = _run(store.get_active_index_generation("ocr", "baseline"))
    old = _run(store.get_index_generation(previous.generation_id))
    assert (
        active_canonical is not None and active_canonical.generation_id == canonical.generation_id
    )
    assert active_ocr is not None and active_ocr.generation_id == ocr.generation_id
    assert old is not None and old.state is IndexGenerationState.SUPERSEDED
    _run(store.close())
