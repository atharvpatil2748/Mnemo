"""ADR-0043 deterministic provenance-preserving context construction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from mnemo.interfaces import ContractValidationError, IntegrityError, LLMInterfaceV1, Message
from mnemo.interfaces.tokenizer import TokenCounterInterfaceV1
from mnemo.interfaces.types import MessageRole
from mnemo.models import FrozenMetadata, RerankedChunkResult, RetrievalRerankResult
from mnemo.models.context import (
    CompressionEvidence,
    ContextBuildResult,
    ContextEmptyReason,
    ContextItem,
    ContextItemKind,
    DocumentContextLabel,
)
from mnemo.registry import PluginRegistry, RegistryState

MAX_CONTEXT_BUDGET = 1_000_000
COMPRESSION_TARGET_TOKENS = 100
COMPRESSION_HARD_MAX_TOKENS = 120
EXTRACTOR_SLOT = "extractor"
EXTRACTOR_SYSTEM_PROMPT = (
    "Compress one retrieved passage for grounded question answering. Preserve only claims "
    "supported by the passage, retain names, dates, quantities, qualifications, and "
    "negation, and do not add facts. Return JSON matching the supplied schema. The summary "
    "must be self-contained and at most 100 o200k_base tokens."
)
SUMMARY_SCHEMA = FrozenMetadata(
    {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ("summary",),
        "additionalProperties": False,
    }
)


class ContextBuilder:
    """Build bounded attributed context without accessing retrieval or storage."""

    __slots__ = ("_registry", "_token_counter")

    def __init__(
        self,
        registry: PluginRegistry,
        token_counter: TokenCounterInterfaceV1,
    ) -> None:
        if not isinstance(registry, PluginRegistry):
            raise TypeError("registry must be PluginRegistry")
        if registry.state is not RegistryState.FROZEN:
            raise ContractValidationError("ContextBuilder requires a frozen registry")
        if not isinstance(token_counter, TokenCounterInterfaceV1):
            raise TypeError("token_counter must implement TokenCounterInterfaceV1")
        self._registry = registry
        self._token_counter = token_counter

    async def build(
        self,
        rerank_result: RetrievalRerankResult,
        *,
        context_budget: int,
        system_prompt: str,
        session_history: tuple[Message, ...] = (),
        document_labels: tuple[DocumentContextLabel, ...] = (),
    ) -> ContextBuildResult:
        """Build one immutable context result using ADR-0043 selection semantics."""
        _validate_inputs(
            rerank_result,
            context_budget=context_budget,
            system_prompt=system_prompt,
            session_history=session_history,
            document_labels=document_labels,
        )
        extractor = self._registry.resolve_llm(EXTRACTOR_SLOT)
        compression_available = extractor is not None
        labels = {(label.document_id, label.version_id): label for label in document_labels}
        fixed_overhead_tokens = self._token_counter.count(
            _serialize_fixed_input(system_prompt, rerank_result, session_history)
        )
        available = max(0, context_budget - fixed_overhead_tokens)
        ordered = rerank_result.results
        if not ordered:
            return self._empty(
                rerank_result,
                context_budget,
                fixed_overhead_tokens,
                available,
                compression_available,
                ContextEmptyReason.NO_CANDIDATES,
            )
        if fixed_overhead_tokens >= context_budget:
            return self._empty(
                rerank_result,
                context_budget,
                fixed_overhead_tokens,
                available,
                compression_available,
                ContextEmptyReason.FIXED_OVERHEAD_EXHAUSTED,
            )

        selected: list[
            tuple[RerankedChunkResult, ContextItemKind, str, CompressionEvidence | None]
        ] = []
        mandatory = ordered[: min(3, len(ordered))]
        for item in mandatory:
            selected.append((item, ContextItemKind.VERBATIM, item.fused_result.chunk.text, None))
        if self._count_rendered(selected, labels) > available:
            return self._empty(
                rerank_result,
                context_budget,
                fixed_overhead_tokens,
                available,
                compression_available,
                ContextEmptyReason.VERBATIM_PREFIX_DOES_NOT_FIT,
            )

        for candidate in ordered[len(mandatory) :]:
            verbatim = (
                candidate,
                ContextItemKind.VERBATIM,
                candidate.fused_result.chunk.text,
                None,
            )
            if self._count_rendered([*selected, verbatim], labels) <= available:
                selected.append(verbatim)
                continue
            if extractor is None:
                continue
            content, evidence = await self._compress(rerank_result.query, candidate, extractor)
            compressed = (candidate, ContextItemKind.COMPRESSED, content, evidence)
            if self._count_rendered([*selected, compressed], labels) <= available:
                selected.append(compressed)

        if not selected:
            return self._empty(
                rerank_result,
                context_budget,
                fixed_overhead_tokens,
                available,
                compression_available,
                ContextEmptyReason.NO_ITEM_FITS,
            )
        items = self._materialize(selected, labels)
        selected_ids = {id(item.reranked_result) for item in items}
        omitted = tuple(item for item in ordered if id(item) not in selected_ids)
        rendered = "\n\n".join(item.rendered_text for item in items)
        return ContextBuildResult(
            rerank_result=rerank_result,
            tokenizer_id=self._token_counter.tokenizer_id,
            context_budget=context_budget,
            fixed_overhead_tokens=fixed_overhead_tokens,
            available_context_tokens=available,
            context_tokens=self._token_counter.count(rendered),
            rendered_context=rendered,
            items=items,
            omitted_results=omitted,
            compression_available=compression_available,
        )

    async def _compress(
        self,
        query: str,
        candidate: RerankedChunkResult,
        extractor: LLMInterfaceV1,
    ) -> tuple[str, CompressionEvidence]:
        chunk = candidate.fused_result.chunk
        user_content = json.dumps(
            {
                "chunk_id": chunk.id,
                "document_id": str(chunk.document_id),
                "query": query,
                "text": chunk.text,
                "version_id": str(chunk.version_id),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        message = Message(role=MessageRole.USER, content=user_content)
        prompt_tokens = self._token_counter.count(
            EXTRACTOR_SYSTEM_PROMPT
        ) + self._token_counter.count(user_content)
        if prompt_tokens + COMPRESSION_HARD_MAX_TOKENS > extractor.max_context_tokens:
            raise ContractValidationError("Extractor input and output exceed its context window")
        completion = await extractor.complete(
            EXTRACTOR_SYSTEM_PROMPT,
            (message,),
            structured_output=SUMMARY_SCHEMA,
            max_tokens=COMPRESSION_HARD_MAX_TOKENS,
        )
        if completion.model != extractor.model:
            raise IntegrityError("Extractor completion model does not match the provider")
        structured = completion.structured
        if not isinstance(structured, Mapping) or set(structured) != {"summary"}:
            raise IntegrityError("Extractor output must contain exactly summary")
        summary = structured["summary"]
        if not isinstance(summary, str):
            raise IntegrityError("Extractor summary must be a string")
        normalized = " ".join(summary.split())
        if not normalized:
            raise IntegrityError("Extractor summary must not be empty")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in normalized):
            raise IntegrityError("Extractor summary contains an unpaired Unicode surrogate")
        token_count = self._token_counter.count(normalized)
        if not 1 <= token_count <= COMPRESSION_HARD_MAX_TOKENS:
            raise IntegrityError("Extractor summary must contain from 1 through 120 tokens")
        return normalized, CompressionEvidence(
            extractor_provider=extractor.provider,
            extractor_model=extractor.model,
            compressed_token_count=token_count,
        )

    def _count_rendered(
        self,
        selected: list[
            tuple[RerankedChunkResult, ContextItemKind, str, CompressionEvidence | None]
        ],
        labels: dict[tuple[UUID, UUID], DocumentContextLabel],
    ) -> int:
        rendered = "\n\n".join(
            _render(number, item, content, labels)
            for number, (item, _, content, _) in enumerate(selected, start=1)
        )
        return self._token_counter.count(rendered)

    def _materialize(
        self,
        selected: list[
            tuple[RerankedChunkResult, ContextItemKind, str, CompressionEvidence | None]
        ],
        labels: dict[tuple[UUID, UUID], DocumentContextLabel],
    ) -> tuple[ContextItem, ...]:
        items: list[ContextItem] = []
        for number, (result, kind, content, evidence) in enumerate(selected, start=1):
            rendered = _render(number, result, content, labels)
            items.append(
                ContextItem(
                    source_number=number,
                    reranked_result=result,
                    kind=kind,
                    content=content,
                    content_token_count=self._token_counter.count(content),
                    rendered_text=rendered,
                    rendered_token_count=self._token_counter.count(rendered),
                    compression_evidence=evidence,
                )
            )
        return tuple(items)

    def _empty(
        self,
        rerank_result: RetrievalRerankResult,
        context_budget: int,
        fixed_overhead_tokens: int,
        available: int,
        compression_available: bool,
        reason: ContextEmptyReason,
    ) -> ContextBuildResult:
        return ContextBuildResult(
            rerank_result=rerank_result,
            tokenizer_id=self._token_counter.tokenizer_id,
            context_budget=context_budget,
            fixed_overhead_tokens=fixed_overhead_tokens,
            available_context_tokens=available,
            context_tokens=0,
            rendered_context="",
            items=(),
            omitted_results=rerank_result.results,
            compression_available=compression_available,
            empty_reason=reason,
        )


def _validate_inputs(
    rerank_result: RetrievalRerankResult,
    *,
    context_budget: int,
    system_prompt: str,
    session_history: tuple[Message, ...],
    document_labels: tuple[DocumentContextLabel, ...],
) -> None:
    if not isinstance(rerank_result, RetrievalRerankResult):
        raise TypeError("rerank_result must be RetrievalRerankResult")
    if isinstance(context_budget, bool) or not isinstance(context_budget, int):
        raise TypeError("context_budget must be an integer")
    if not 1 <= context_budget <= MAX_CONTEXT_BUDGET:
        raise ContractValidationError("context_budget must be from 1 through 1000000")
    if not isinstance(system_prompt, str):
        raise TypeError("system_prompt must be a string")
    if not isinstance(session_history, tuple) or any(
        not isinstance(message, Message) for message in session_history
    ):
        raise TypeError("session_history must be a tuple of Message values")
    if not isinstance(document_labels, tuple) or any(
        not isinstance(label, DocumentContextLabel) for label in document_labels
    ):
        raise TypeError("document_labels must contain DocumentContextLabel values")
    keys = tuple((label.document_id, label.version_id) for label in document_labels)
    if len(set(keys)) != len(keys):
        raise ContractValidationError("document labels must have unique exact-version keys")
    expected_ranks = tuple(range(1, len(rerank_result.results) + 1))
    if tuple(item.reranked_rank for item in rerank_result.results) != expected_ranks:
        raise IntegrityError("reranked results must be in contiguous reranked-rank order")


def _serialize_fixed_input(
    system_prompt: str,
    rerank_result: RetrievalRerankResult,
    session_history: tuple[Message, ...],
) -> str:
    history = "".join(f"{message.role.value}\n{message.content}\n" for message in session_history)
    return f"SYSTEM\n{system_prompt}\nQUESTION\n{rerank_result.query}\nHISTORY\n{history}"


def _render(
    source_number: int,
    result: RerankedChunkResult,
    content: str,
    labels: dict[tuple[UUID, UUID], DocumentContextLabel],
) -> str:
    chunk = result.fused_result.chunk
    fields = [
        f"=== Source [{source_number}]",
        f"document_id={chunk.document_id}",
        f"version_id={chunk.version_id}",
    ]
    label = labels.get((chunk.document_id, chunk.version_id))
    if label is not None:
        fields.append(f"title={json.dumps(label.title, ensure_ascii=False, separators=(',', ':'))}")
    if chunk.heading_path:
        heading = " > ".join(chunk.heading_path)
        fields.append(f"heading={json.dumps(heading, ensure_ascii=False, separators=(',', ':'))}")
    if chunk.position.page_number is not None:
        fields.append(f"page={chunk.position.page_number}")
    return " | ".join(fields) + " ===\n" + content
