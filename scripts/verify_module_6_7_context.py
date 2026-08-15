"""Validate ADR-0043 against the real Module 6.6 golden handoff."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast

from mnemo import __version__
from mnemo.config import RerankerConfig
from mnemo.interfaces import CompletionResult, HealthStatus, LLMCapabilities, Message
from mnemo.models import FrozenMetadata, RetrievalRerankResult
from mnemo.registry import PluginRegistry
from mnemo.retrieval import ContextBuilder
from mnemo.retrieval.context import _render, _serialize_fixed_input
from mnemo.retrieval.reranker import (
    MODEL_ID,
    MODEL_REVISION,
    CrossEncoderReranker,
    CrossEncoderRerankerPlugin,
    RerankingModule,
)
from mnemo.tokenizers import O200KBaseTokenCounter
from verify_module_6_4_parent import _tokenizer_asset
from verify_module_6_5_fusion import EXPECTED_SHA256, ROOT
from verify_module_6_6_reranking import DATASET, M65_EVIDENCE, _real_fusion


class _ControlledExtractor:
    provider = "mnemo-acceptance"
    model = "controlled-extractor-v1"
    max_context_tokens = 131_072

    def __init__(self, counter: O200KBaseTokenCounter) -> None:
        self.counter = counter
        self.calls = 0

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
        messages: tuple[Message, ...],
        structured_output: object = None,
        max_tokens: int = 1000,
    ) -> CompletionResult:
        del system, structured_output, max_tokens
        self.calls += 1
        payload = cast(dict[str, str], json.loads(messages[0].content))
        words = payload["text"].split()
        summary = " ".join(words[:50])
        while self.counter.count(summary) > 100:
            words.pop()
            summary = " ".join(words)
        return CompletionResult(
            model=self.model,
            structured=FrozenMetadata({"summary": summary}),
        )

    def stream(
        self, system: str, messages: tuple[Message, ...], max_tokens: int = 1000
    ) -> AsyncIterator[str]:
        del system, messages, max_tokens
        return self._stream()

    async def _stream(self) -> AsyncIterator[str]:
        yield "unused"

    async def health_check(self) -> HealthStatus:
        raise NotImplementedError


class _ExtractorPlugin:
    name = "mnemo-module-6-7-controlled-extractor"
    version = __version__
    core_version_range = ">=0.20.1"

    def __init__(self, provider: _ControlledExtractor) -> None:
        self.provider = provider

    def capabilities(self) -> tuple[str, ...]:
        return ("llm",)

    def register(self, registry: PluginRegistry) -> None:
        registry.register_llm("extractor", self.provider, priority=0)


async def _run() -> dict[str, object]:
    digest = sha256(DATASET.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise AssertionError(f"golden corpus hash mismatch: {digest}")
    m65 = cast(dict[str, object], json.loads(M65_EVIDENCE.read_text(encoding="utf-8")))
    started = time.perf_counter()
    fusion, storage, ollama, builtins = await _real_fusion(m65)
    reranker = CrossEncoderReranker(
        RerankerConfig(provider="sentence-transformers", model=MODEL_ID)
    )
    rerank_registry = PluginRegistry(core_version=__version__)
    rerank_registry.load_plugin(CrossEncoderRerankerPlugin(reranker))
    counter = O200KBaseTokenCounter(_tokenizer_asset())
    extractor = _ControlledExtractor(counter)
    context_registry = PluginRegistry(core_version=__version__)
    context_registry.load_plugin(_ExtractorPlugin(extractor))
    context_registry.freeze()
    try:
        await rerank_registry.execute_startup_hooks()
        rerank_registry.freeze()
        rerank_result = await RerankingModule(rerank_registry).execute(
            cast(str, m65["query"]), fusion
        )
        if not isinstance(rerank_result, RetrievalRerankResult):
            raise AssertionError("real Module 6.6 handoff is unavailable")
        original_chunks = tuple(item.fused_result.chunk for item in rerank_result.results)
        system_prompt = "Answer only from the attributed context."
        fixed = counter.count(_serialize_fixed_input(system_prompt, rerank_result, ()))
        mandatory_rendered = "\n\n".join(
            _render(index, item, item.fused_result.chunk.text, {})
            for index, item in enumerate(rerank_result.results[:3], 1)
        )
        sample_words = rerank_result.results[3].fused_result.chunk.text.split()[:50]
        sample = " ".join(sample_words)
        while counter.count(sample) > 100:
            sample_words.pop()
            sample = " ".join(sample_words)
        compressed_fourth = _render(4, rerank_result.results[3], sample, {})
        available = counter.count(mandatory_rendered + "\n\n" + compressed_fourth)
        budget = fixed + available
        builder = ContextBuilder(context_registry, counter)
        first_started = time.perf_counter()
        first = await builder.build(
            rerank_result,
            context_budget=budget,
            system_prompt=system_prompt,
        )
        first_seconds = time.perf_counter() - first_started
        calls_after_first = extractor.calls
        second_started = time.perf_counter()
        second = await builder.build(
            rerank_result,
            context_budget=budget,
            system_prompt=system_prompt,
        )
        second_seconds = time.perf_counter() - second_started
        if first != second:
            raise AssertionError("controlled context construction repeat changed")
        if first.rerank_result is not rerank_result:
            raise AssertionError("top-level rerank provenance was replaced")
        selected = tuple(item.reranked_result for item in first.items)
        if any(item is not rerank_result.results[item.reranked_rank - 1] for item in selected):
            raise AssertionError("selected reranking evidence was replaced")
        if {id(item) for item in selected + first.omitted_results} != {
            id(item) for item in rerank_result.results
        }:
            raise AssertionError("selected/omitted candidates do not partition the handoff")
        if first.context_tokens > first.available_context_tokens:
            raise AssertionError("context exceeded the accepted token budget")
        if not any(item.kind.value == "compressed" for item in first.items):
            raise AssertionError("controlled acceptance did not exercise compression")
        if tuple(item.fused_result.chunk for item in rerank_result.results) != original_chunks:
            raise AssertionError("canonical chunk evidence was mutated")
        return {
            "verdict": "PASS",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": digest,
            "module_6_6_evidence": "docs/milestone-evidence/module-6.6-reranking.json",
            "query": rerank_result.query,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "input_candidates": len(rerank_result.results),
            "selected_items": len(first.items),
            "omitted_items": len(first.omitted_results),
            "verbatim_items": sum(item.kind.value == "verbatim" for item in first.items),
            "compressed_items": sum(item.kind.value == "compressed" for item in first.items),
            "context_budget": first.context_budget,
            "fixed_overhead_tokens": first.fixed_overhead_tokens,
            "available_context_tokens": first.available_context_tokens,
            "context_tokens": first.context_tokens,
            "tokenizer_id": first.tokenizer_id,
            "selected_chunk_ids": [
                item.reranked_result.fused_result.chunk.id for item in first.items
            ],
            "omitted_chunk_ids": [item.fused_result.chunk.id for item in first.omitted_results],
            "extractor_calls_first": calls_after_first,
            "extractor_calls_second": extractor.calls - calls_after_first,
            "first_build_seconds": first_seconds,
            "second_build_seconds": second_seconds,
            "total_acceptance_seconds": time.perf_counter() - started,
            "deterministic_repeat": True,
            "provenance_preserved": True,
            "partition_verified": True,
            "canonical_chunks_unchanged": True,
            "retrieval_reranking_or_storage_access_by_module_6_7": False,
        }
    finally:
        await rerank_registry.execute_shutdown_hooks()
        await ollama._client.aclose()
        await storage.close()
        del builtins


def main() -> int:
    print(json.dumps(asyncio.run(_run()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
