"""Source-local parent candidate promotion for Phase 6 Module 6.4."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

from mnemo.interfaces import (
    IntegrityError,
    ParentPromotionCapabilities,
    StorageInterfaceV1,
)
from mnemo.models import Chunk, FrozenMetadata, ScoredChunk


@dataclass(frozen=True, slots=True)
class _Family:
    """One fully validated canonical child family."""

    parent: Chunk
    member_ids: frozenset[str]


class ParentRetriever:
    """Promote qualifying source-local child families without executing retrieval."""

    def __init__(self, storage: StorageInterfaceV1) -> None:
        """Bind the backend-neutral canonical storage facade."""
        if not isinstance(storage, StorageInterfaceV1):
            raise TypeError("storage must implement StorageInterfaceV1")
        self._storage = storage

    @property
    def promotion_mode(self) -> str:
        """Return the stable registry capability identifier."""
        return "parent"

    def capabilities(self) -> ParentPromotionCapabilities:
        """Describe the ADR-0040 behavior implemented by this promoter."""
        return ParentPromotionCapabilities(
            source_local=True,
            single_pass=True,
            preserves_raw_scores=True,
            validates_exact_version=True,
        )

    async def promote(
        self,
        candidates: tuple[ScoredChunk, ...],
    ) -> tuple[ScoredChunk, ...]:
        """Promote qualifying families once while preserving source-local evidence."""
        _validate_candidates(candidates)
        if not candidates:
            return ()

        referenced_ids = _referenced_relationship_ids(candidates)
        loaded = await self._load_chunks(referenced_ids)
        families = _validate_families(candidates, loaded)
        qualifying = _qualifying_families(candidates, families)

        emitted: list[ScoredChunk] = []
        emitted_ids: set[str] = set()
        emitted_families: set[tuple[str, frozenset[str]]] = set()
        for candidate in candidates:
            family = families.get(candidate.chunk.id)
            family_key = (family.parent.id, family.member_ids) if family is not None else None
            if family_key is not None and family_key in qualifying:
                assert family is not None
                if family_key in emitted_families:
                    continue
                emitted_families.add(family_key)
                output = ScoredChunk(
                    chunk=replace(
                        family.parent,
                        metadata=FrozenMetadata(
                            {**dict(family.parent.metadata), **dict(candidate.chunk.metadata)}
                        ),
                    ),
                    score=candidate.score,
                    source=candidate.source,
                    rank=1,
                )
            else:
                output = candidate

            if output.chunk.id in emitted_ids:
                continue
            emitted_ids.add(output.chunk.id)
            emitted.append(output)

        return tuple(
            ScoredChunk(
                chunk=result.chunk,
                score=result.score,
                source=result.source,
                rank=rank,
            )
            for rank, result in enumerate(emitted, start=1)
        )

    async def _load_chunks(self, chunk_ids: tuple[str, ...]) -> dict[str, Chunk]:
        results = await asyncio.gather(
            *(self._storage.get_chunk(chunk_id) for chunk_id in chunk_ids)
        )
        loaded: dict[str, Chunk] = {}
        for requested_id, chunk in zip(chunk_ids, results, strict=True):
            if chunk is None:
                raise IntegrityError(f"referenced chunk is missing: {requested_id}")
            if not isinstance(chunk, Chunk):
                raise IntegrityError("storage returned an invalid chunk")
            if chunk.id != requested_id:
                raise IntegrityError("loaded chunk identity does not match requested identity")
            loaded[requested_id] = chunk
        return loaded


def _validate_candidates(candidates: tuple[ScoredChunk, ...]) -> None:
    if not isinstance(candidates, tuple):
        raise TypeError("candidates must be a tuple")
    if any(not isinstance(candidate, ScoredChunk) for candidate in candidates):
        raise IntegrityError("candidates must contain only ScoredChunk values")
    if not candidates:
        return

    identities = tuple(candidate.chunk.id for candidate in candidates)
    if len(set(identities)) != len(identities):
        raise IntegrityError("candidate chunk identities must be unique")
    sources = {candidate.source for candidate in candidates}
    if len(sources) != 1 or not next(iter(sources)).strip():
        raise IntegrityError("candidates must belong to one source-local stream")
    if tuple(candidate.rank for candidate in candidates) != tuple(range(1, len(candidates) + 1)):
        raise IntegrityError("candidate ranks must be contiguous and match tuple order")
    expected = tuple(sorted(candidates, key=lambda item: (-item.score, item.chunk.id)))
    if candidates != expected:
        raise IntegrityError("candidates must use deterministic descending-score ordering")


def _referenced_relationship_ids(
    candidates: tuple[ScoredChunk, ...],
) -> tuple[str, ...]:
    referenced: set[str] = set()
    for candidate in candidates:
        chunk = candidate.chunk
        if chunk.parent_chunk_id is None:
            if chunk.sibling_ids:
                raise IntegrityError("root chunks cannot advertise siblings")
            continue
        referenced.add(chunk.parent_chunk_id)
        referenced.update(chunk.sibling_ids)
    return tuple(sorted(referenced))


def _validate_families(
    candidates: tuple[ScoredChunk, ...],
    loaded: dict[str, Chunk],
) -> dict[str, _Family]:
    families: dict[str, _Family] = {}
    for candidate in candidates:
        child = candidate.chunk
        parent_id = child.parent_chunk_id
        if parent_id is None:
            continue
        member_ids = frozenset((child.id, *child.sibling_ids))
        if parent_id in member_ids:
            raise IntegrityError("canonical parent cannot be one of its own children")
        parent = loaded[parent_id]
        _require_same_identity_domain(child, parent, "parent")
        if parent.parent_chunk_id is None and parent.sibling_ids:
            raise IntegrityError("root chunks cannot advertise siblings")

        for member_id in member_ids:
            member = child if member_id == child.id else loaded[member_id]
            _require_same_identity_domain(child, member, "sibling")
            if member.parent_chunk_id != parent_id:
                raise IntegrityError("family members must share one non-null parent")
            if frozenset(member.sibling_ids) != member_ids - {member.id}:
                raise IntegrityError("sibling relationships must be symmetric and complete")

        families[child.id] = _Family(parent=parent, member_ids=member_ids)
    return families


def _require_same_identity_domain(reference: Chunk, related: Chunk, role: str) -> None:
    if related.document_id != reference.document_id:
        raise IntegrityError(f"{role} belongs to another document")
    if related.version_id != reference.version_id:
        raise IntegrityError(f"{role} belongs to another document version")


def _qualifying_families(
    candidates: tuple[ScoredChunk, ...],
    families: dict[str, _Family],
) -> set[tuple[str, frozenset[str]]]:
    represented_ids = {candidate.chunk.id for candidate in candidates}
    qualifying: set[tuple[str, frozenset[str]]] = set()
    for family in families.values():
        represented_count = len(family.member_ids & represented_ids)
        if represented_count * 2 >= len(family.member_ids):
            qualifying.add((family.parent.id, family.member_ids))
    return qualifying
