"""Deterministic, storage-free Phase 4 chunk dispatcher and finalizer."""

import json
from dataclasses import replace
from hashlib import sha256
from uuid import UUID

from mnemo.interfaces import (
    ChunkingContext,
    ContractValidationError,
    IntegrityError,
    TokenCounterInterfaceV1,
    UnsupportedError,
)
from mnemo.models import BlockSpan, Chunk, ChunkDraft, ParsedDocument
from mnemo.registry import PluginRegistry


def compute_chunk_id(version_id: UUID, source_span: BlockSpan, text: str) -> str:
    """Compute the frozen canonical chunk identity."""
    if not isinstance(version_id, UUID):
        raise TypeError("version_id must be UUID")
    if not isinstance(source_span, BlockSpan):
        raise TypeError("source_span must be BlockSpan")
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    serialized = json.dumps(
        [str(version_id).lower(), [source_span.start_ordinal, source_span.end_ordinal], text],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


class ChunkerDispatcher:
    """Select a V2 strategy and finalize its immutable draft forest."""

    __slots__ = ("_registry", "_token_counter")

    def __init__(self, registry: PluginRegistry, token_counter: TokenCounterInterfaceV1) -> None:
        """Bind a registry and the one canonical counter used per operation."""
        if not isinstance(registry, PluginRegistry):
            raise TypeError("registry must be PluginRegistry")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must satisfy TokenCounterInterfaceV1")
        self._registry = registry
        self._token_counter = token_counter

    def dispatch(self, document: ParsedDocument, context: ChunkingContext) -> tuple[Chunk, ...]:
        """Validate, invoke, and deterministically finalize one V2 strategy."""
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be ParsedDocument")
        if not isinstance(context, ChunkingContext):
            raise TypeError("context must be ChunkingContext")
        if document.metadata.content_hash != context.document_version.content_hash:
            raise ContractValidationError(
                "ParsedDocument content_hash does not match DocumentVersion"
            )
        strategy = self._registry.resolve_chunker_v2(document.doc_type)
        if strategy is None:
            raise UnsupportedError(f"no V2 chunker supports {document.doc_type.value}")
        capabilities = strategy.capabilities()
        if document.doc_type not in strategy.supported_doc_types or (
            document.doc_type not in capabilities.supported_doc_types
        ):
            raise UnsupportedError("resolved V2 chunker does not advertise the document type")
        drafts = strategy.chunk(document, context, self._token_counter)
        if not isinstance(drafts, tuple):
            raise ContractValidationError("V2 chunker output must be a tuple")
        self._validate_drafts(document, drafts)
        counts = tuple(self._token_counter.count(draft.text) for draft in drafts)
        if any(count > context.effective_max_tokens for count in counts):
            raise IntegrityError("V2 chunker emitted an oversized draft")
        retained = self._filter_short_leaves(drafts, counts)
        return self._materialize(context, retained)

    @staticmethod
    def _validate_drafts(document: ParsedDocument, drafts: tuple[ChunkDraft, ...]) -> None:
        block_count = len(document.blocks)
        for index, draft in enumerate(drafts):
            if not isinstance(draft, ChunkDraft):
                raise ContractValidationError("V2 output entries must be ChunkDraft")
            if draft.source_span.end_ordinal >= block_count:
                raise ContractValidationError("ChunkDraft source_span is outside the document")
            if draft.parent_index is not None and draft.parent_index >= index:
                raise ContractValidationError("parent_index must reference an earlier draft")

    @staticmethod
    def _filter_short_leaves(
        drafts: tuple[ChunkDraft, ...], counts: tuple[int, ...]
    ) -> tuple[ChunkDraft, ...]:
        parent_indexes = {draft.parent_index for draft in drafts if draft.parent_index is not None}
        short = {
            index
            for index, (draft, count) in enumerate(zip(drafts, counts, strict=True))
            if count < 15 and draft.metadata.get("chunker.preserve_short") is not True
        }
        if short & parent_indexes:
            raise IntegrityError("a short parent draft cannot be removed while it has children")
        survivors = tuple(index for index in range(len(drafts)) if index not in short)
        remap = {old: new for new, old in enumerate(survivors)}
        result: list[ChunkDraft] = []
        for old_index in survivors:
            draft = drafts[old_index]
            parent = None if draft.parent_index is None else remap[draft.parent_index]
            result.append(replace(draft, parent_index=parent))
        return tuple(result)

    @staticmethod
    def _materialize(context: ChunkingContext, drafts: tuple[ChunkDraft, ...]) -> tuple[Chunk, ...]:
        version = context.document_version
        identifiers = tuple(
            compute_chunk_id(version.version_id, draft.source_span, draft.text) for draft in drafts
        )
        if len(set(identifiers)) != len(identifiers):
            raise IntegrityError("V2 chunker emitted duplicate canonical identities")
        children: dict[int, list[int]] = {}
        for index, draft in enumerate(drafts):
            if draft.parent_index is not None:
                children.setdefault(draft.parent_index, []).append(index)
        chunks: list[Chunk] = []
        for index, draft in enumerate(drafts):
            parent_id = None if draft.parent_index is None else identifiers[draft.parent_index]
            siblings: tuple[str, ...] = ()
            if draft.parent_index is not None:
                siblings = tuple(
                    identifiers[sibling]
                    for sibling in children[draft.parent_index]
                    if sibling != index
                )
            chunks.append(
                Chunk(
                    id=identifiers[index],
                    text=draft.text,
                    document_id=version.document_id,
                    version_id=version.version_id,
                    chunk_type=draft.chunk_type,
                    position=draft.position,
                    source_span=draft.source_span,
                    heading_path=draft.heading_path,
                    parent_chunk_id=parent_id,
                    sibling_ids=siblings,
                    metadata=draft.metadata,
                )
            )
        return tuple(chunks)
