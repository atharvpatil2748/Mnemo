"""Focused tests for ADR-0040 source-local parent candidate promotion."""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, cast
from unittest.mock import AsyncMock, create_autospec
from uuid import UUID

import mnemo.retrieval.parent as parent_module
import pytest
from mnemo import (
    CapabilityKind,
    PluginRegistry,
    RegistrationConflictError,
    RegistryFrozenError,
)
from mnemo.interfaces import (
    IntegrityError,
    ParentPromotionInterfaceV1,
    StorageError,
    StorageInterfaceV1,
)
from mnemo.models import (
    BlockSpan,
    Chunk,
    ChunkPosition,
    ChunkType,
    FrozenMetadata,
    ScoredChunk,
)
from mnemo.retrieval import ParentRetriever

DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000001")
VERSION_ID = UUID("00000000-0000-4000-8000-000000000002")


def _chunk(
    index: int,
    *,
    document_id: UUID = DOCUMENT_ID,
    version_id: UUID = VERSION_ID,
    parent_id: str | None = None,
    sibling_ids: tuple[str, ...] = (),
) -> Chunk:
    return Chunk(
        id=f"{index:064x}",
        text=f"Canonical chunk {index}",
        document_id=document_id,
        version_id=version_id,
        chunk_type=ChunkType.PASSAGE,
        position=ChunkPosition(section_index=0, chunk_index_in_section=index),
        source_span=BlockSpan(start_ordinal=index, end_ordinal=index),
        heading_path=("Chapter",),
        parent_chunk_id=parent_id,
        sibling_ids=sibling_ids,
        metadata=FrozenMetadata({"test.index": index}),
    )


def _family(
    parent_index: int,
    child_indices: tuple[int, ...],
    *,
    document_id: UUID = DOCUMENT_ID,
    version_id: UUID = VERSION_ID,
) -> tuple[Chunk, tuple[Chunk, ...]]:
    parent = _chunk(parent_index, document_id=document_id, version_id=version_id)
    child_ids = tuple(f"{index:064x}" for index in child_indices)
    children = tuple(
        _chunk(
            index,
            document_id=document_id,
            version_id=version_id,
            parent_id=parent.id,
            sibling_ids=tuple(item for item in child_ids if item != f"{index:064x}"),
        )
        for index in child_indices
    )
    return parent, children


def _stream(
    chunks: tuple[Chunk, ...],
    *,
    scores: tuple[float, ...] | None = None,
    source: str = "dense",
) -> tuple[ScoredChunk, ...]:
    values = scores or tuple(float(len(chunks) - index) for index in range(len(chunks)))
    return tuple(
        ScoredChunk(chunk=chunk, score=score, source=source, rank=rank)
        for rank, (chunk, score) in enumerate(zip(chunks, values, strict=True), start=1)
    )


def _storage(chunks: tuple[Chunk, ...]) -> tuple[StorageInterfaceV1, AsyncMock]:
    by_id = {chunk.id: chunk for chunk in chunks}
    storage = create_autospec(StorageInterfaceV1, instance=True)
    get_chunk = cast(AsyncMock, storage.get_chunk)
    get_chunk.side_effect = lambda chunk_id: by_id.get(chunk_id)
    return cast(StorageInterfaceV1, storage), get_chunk


@pytest.mark.anyio
async def test_empty_input_returns_without_storage_access() -> None:
    storage, get_chunk = _storage(())
    assert await ParentRetriever(storage).promote(()) == ()
    get_chunk.assert_not_awaited()


@pytest.mark.anyio
async def test_roots_and_unrelated_candidates_remain_in_order() -> None:
    roots = (_chunk(1), _chunk(2))
    storage, get_chunk = _storage(roots)
    candidates = _stream(roots, scores=(0.9, 0.8))

    result = await ParentRetriever(storage).promote(candidates)

    assert tuple(item.chunk for item in result) == roots
    assert tuple(item.rank for item in result) == (1, 2)
    get_chunk.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("represented", "promotes"),
    ((1, False), (2, True), (3, True), (4, True)),
)
async def test_four_child_threshold_is_exact(represented: int, promotes: bool) -> None:
    parent, children = _family(100, (1, 2, 3, 4))
    storage, _ = _storage((parent, *children))
    candidates = _stream(children[:represented])

    result = await ParentRetriever(storage).promote(candidates)

    if promotes:
        assert tuple(item.chunk.id for item in result) == (parent.id,)
    else:
        assert result == candidates


@pytest.mark.anyio
async def test_sole_child_promotes_at_one_of_one() -> None:
    parent, children = _family(100, (1,))
    storage, _ = _storage((parent, *children))

    result = await ParentRetriever(storage).promote(_stream(children, scores=(0.931,)))

    assert result[0].chunk is parent
    assert result[0].score == 0.931
    assert result[0].source == "dense"
    assert result[0].rank == 1


@pytest.mark.anyio
async def test_mixed_families_preserve_replacement_position_score_source_and_ranks() -> None:
    parent_a, children_a = _family(100, (1, 2, 3, 4))
    parent_b, children_b = _family(200, (5, 6, 7, 8))
    unrelated = _chunk(50)
    storage, _ = _storage((parent_a, *children_a, parent_b, *children_b, unrelated))
    candidates = _stream(
        (children_a[1], unrelated, children_b[0], children_a[0]),
        scores=(0.95, 0.9, 0.85, 0.8),
        source="sparse",
    )

    result = await ParentRetriever(storage).promote(candidates)

    assert tuple(item.chunk.id for item in result) == (
        parent_a.id,
        unrelated.id,
        children_b[0].id,
    )
    assert tuple(item.score for item in result) == (0.95, 0.9, 0.85)
    assert tuple(item.source for item in result) == ("sparse", "sparse", "sparse")
    assert tuple(item.rank for item in result) == (1, 2, 3)


@pytest.mark.anyio
async def test_two_qualifying_families_promote_independently() -> None:
    parent_a, children_a = _family(100, (1, 2))
    parent_b, children_b = _family(200, (3, 4))
    storage, _ = _storage((parent_a, *children_a, parent_b, *children_b))
    candidates = _stream((children_b[0], children_a[0], children_b[1], children_a[1]))

    result = await ParentRetriever(storage).promote(candidates)

    assert tuple(item.chunk.id for item in result) == (parent_b.id, parent_a.id)
    assert tuple(item.rank for item in result) == (1, 2)


@pytest.mark.anyio
async def test_direct_parent_duplicate_uses_earliest_surviving_occurrence() -> None:
    parent, children = _family(100, (1, 2))
    storage, _ = _storage((parent, *children))
    candidates = _stream((parent, children[0], children[1]), scores=(0.99, 0.9, 0.8))

    result = await ParentRetriever(storage).promote(candidates)

    assert tuple(item.chunk.id for item in result) == (parent.id,)
    assert result[0].score == 0.99

    candidates = _stream((children[0], children[1], parent), scores=(0.99, 0.9, 0.8))
    result = await ParentRetriever(storage).promote(candidates)
    assert tuple(item.chunk.id for item in result) == (parent.id,)
    assert result[0].score == 0.99


@pytest.mark.anyio
async def test_promotion_is_single_pass_across_adjacent_hierarchy_levels() -> None:
    grandparent, parent_family = _family(300, (100, 101))
    parent = parent_family[0]
    _, child_family = _family(100, (1, 2))
    child_family = tuple(
        replace(child, document_id=parent.document_id, version_id=parent.version_id)
        for child in child_family
    )
    storage, _ = _storage((grandparent, *parent_family, *child_family))
    candidates = _stream((child_family[0], child_family[1]), scores=(0.9, 0.8))

    result = await ParentRetriever(storage).promote(candidates)

    assert tuple(item.chunk.id for item in result) == (parent.id,)
    assert result[0].chunk.id != grandparent.id


@pytest.mark.anyio
async def test_original_parent_can_independently_participate_in_its_family() -> None:
    grandparent, parent_family = _family(300, (100, 101))
    parent = parent_family[0]
    _, children = _family(100, (1, 2))
    storage, _ = _storage((grandparent, *parent_family, *children))
    candidates = _stream((children[0], parent, parent_family[1], children[1]))

    result = await ParentRetriever(storage).promote(candidates)

    assert tuple(item.chunk.id for item in result) == (parent.id, grandparent.id)


@pytest.mark.anyio
async def test_lookup_ids_are_deduplicated_and_bounded() -> None:
    parent, children = _family(100, (1, 2, 3, 4))
    storage, get_chunk = _storage((parent, *children))

    await ParentRetriever(storage).promote(_stream(children))

    requested = tuple(call.args[0] for call in get_chunk.await_args_list)
    assert len(requested) == len(set(requested)) == 5
    assert set(requested) == {parent.id, *(child.id for child in children)}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutate",
    (
        lambda parent, children: replace(parent, document_id=UUID(int=9)),
        lambda parent, children: replace(parent, version_id=UUID(int=9)),
        lambda parent, children: replace(children[1], parent_chunk_id=f"{999:064x}"),
        lambda parent, children: replace(children[1], document_id=UUID(int=9)),
        lambda parent, children: replace(children[1], version_id=UUID(int=9)),
        lambda parent, children: replace(children[1], sibling_ids=()),
    ),
)
async def test_invalid_family_relationships_raise_integrity_error(mutate: Any) -> None:
    parent, children = _family(100, (1, 2))
    corrupted = mutate(parent, children)
    stored = tuple(corrupted if item.id == corrupted.id else item for item in (parent, *children))
    storage, _ = _storage(stored)

    with pytest.raises(IntegrityError):
        await ParentRetriever(storage).promote(_stream((children[0],)))


@pytest.mark.anyio
async def test_missing_parent_and_missing_sibling_raise_integrity_error() -> None:
    parent, children = _family(100, (1, 2))
    for stored in ((children[0], children[1]), (parent, children[0])):
        storage, _ = _storage(stored)
        with pytest.raises(IntegrityError, match="missing"):
            await ParentRetriever(storage).promote(_stream((children[0],)))


@pytest.mark.anyio
async def test_root_with_siblings_and_self_referential_sibling_are_rejected() -> None:
    root = _chunk(1, sibling_ids=(f"{2:064x}",))
    storage, get_chunk = _storage(())
    with pytest.raises(IntegrityError, match="root"):
        await ParentRetriever(storage).promote(_stream((root,)))
    get_chunk.assert_not_awaited()

    parent, children = _family(100, (1, 2))
    object.__setattr__(children[0], "sibling_ids", (children[0].id,))
    storage, _ = _storage((parent, *children))
    with pytest.raises(IntegrityError):
        await ParentRetriever(storage).promote(_stream((children[0],)))

    parent, children = _family(100, (1,))
    object.__setattr__(parent, "sibling_ids", (f"{200:064x}",))
    storage, _ = _storage((parent, *children))
    with pytest.raises(IntegrityError, match="root"):
        await ParentRetriever(storage).promote(_stream(children))


@pytest.mark.anyio
async def test_wrong_loaded_identity_is_rejected() -> None:
    parent, children = _family(100, (1,))
    storage, get_chunk = _storage((parent, *children))
    get_chunk.side_effect = lambda _: replace(parent, id=f"{999:064x}")

    with pytest.raises(IntegrityError, match="identity"):
        await ParentRetriever(storage).promote(_stream(children))


@pytest.mark.anyio
async def test_invalid_loaded_value_and_parent_inside_family_are_rejected() -> None:
    parent, children = _family(100, (1, 2))
    storage, get_chunk = _storage((parent, *children))
    get_chunk.side_effect = lambda _: object()
    with pytest.raises(IntegrityError, match="invalid chunk"):
        await ParentRetriever(storage).promote(_stream((children[0],)))

    child = replace(children[0], sibling_ids=(parent.id,))
    storage, _ = _storage((parent, child))
    with pytest.raises(IntegrityError, match="own children"):
        await ParentRetriever(storage).promote(_stream((child,)))


@pytest.mark.anyio
async def test_storage_failure_propagates_without_partial_result() -> None:
    parent, children = _family(100, (1, 2))
    storage, get_chunk = _storage((parent, *children))
    failure = StorageError("canonical storage unavailable")
    get_chunk.side_effect = failure

    with pytest.raises(StorageError, match="unavailable") as raised:
        await ParentRetriever(storage).promote(_stream(children))
    assert raised.value is failure


@pytest.mark.anyio
@pytest.mark.parametrize(
    "candidates",
    (
        cast(Any, []),
        cast(Any, (object(),)),
        _stream((_chunk(1), _chunk(1))),
        (
            ScoredChunk(chunk=_chunk(1), score=0.9, source="dense", rank=1),
            ScoredChunk(chunk=_chunk(2), score=0.8, source="sparse", rank=2),
        ),
        (ScoredChunk(chunk=_chunk(1), score=0.9, source="dense", rank=2),),
        _stream((_chunk(1), _chunk(2)), scores=(0.8, 0.9)),
    ),
)
async def test_invalid_candidate_streams_are_rejected(candidates: object) -> None:
    storage, get_chunk = _storage(())
    with pytest.raises((TypeError, IntegrityError)):
        await ParentRetriever(storage).promote(cast(Any, candidates))
    get_chunk.assert_not_awaited()


@pytest.mark.anyio
async def test_empty_source_is_rejected_even_if_model_was_corrupted() -> None:
    candidate = _stream((_chunk(1),))[0]
    object.__setattr__(candidate, "source", "")
    storage, get_chunk = _storage(())
    with pytest.raises(IntegrityError):
        await ParentRetriever(storage).promote((candidate,))
    get_chunk.assert_not_awaited()


def test_capabilities_protocol_and_backend_boundary() -> None:
    storage, _ = _storage(())
    promoter = ParentRetriever(storage)

    assert isinstance(promoter, ParentPromotionInterfaceV1)
    assert promoter.promotion_mode == "parent"
    assert promoter.capabilities().source_local
    assert promoter.capabilities().single_pass
    assert promoter.capabilities().preserves_raw_scores
    assert promoter.capabilities().validates_exact_version

    source = inspect.getsource(parent_module).casefold()
    forbidden = ("qdrant", "sqlite", "surreal", "search_dense", "search_sparse", "top_k")
    assert not any(name in source for name in forbidden)


def test_parent_promoter_registry_priority_descriptor_conflict_and_freeze() -> None:
    storage, _ = _storage(())
    low = ParentRetriever(storage)
    high = ParentRetriever(storage)
    registry = PluginRegistry(core_version="0.20.1")

    class Plugin:
        version = "0.20.1"
        core_version_range = ">=0.20.1"

        def __init__(self, name: str, promoter: ParentRetriever, priority: int) -> None:
            self.name = name
            self.promoter = promoter
            self.priority = priority

        def capabilities(self) -> tuple[str, ...]:
            return ("parent_promotion",)

        def register(self, target: PluginRegistry) -> None:
            target.register_parent_promoter("default", self.promoter, priority=self.priority)

    registry.load_plugin(Plugin("low-parent", low, 1))
    registry.load_plugin(Plugin("high-parent", high, 10))
    assert registry.resolve_parent_promoter("default") is high
    descriptors = registry.list_registrations(CapabilityKind.PARENT_PROMOTION)
    assert [(item.priority, item.active) for item in descriptors] == [(10, True), (1, False)]
    assert all(item.interface_version == "v1" for item in descriptors)

    with pytest.raises(Exception) as raised:
        registry.load_plugin(Plugin("conflict-parent", ParentRetriever(storage), 10))
    assert isinstance(raised.value.__cause__, RegistrationConflictError)

    registry.freeze()
    with pytest.raises(RegistryFrozenError):
        registry.register_parent_promoter("late", low, priority=1)


def test_parent_retriever_rejects_non_storage_dependency() -> None:
    with pytest.raises(TypeError, match="StorageInterfaceV1"):
        ParentRetriever(object())  # type: ignore[arg-type]
