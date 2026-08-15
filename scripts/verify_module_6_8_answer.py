"""Validate ADR-0044 against the real Module 6.7 golden handoff."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast

from mnemo import __version__
from mnemo.config import RerankerConfig
from mnemo.interfaces import CompletionResult, HealthStatus, LLMCapabilities, Message
from mnemo.models import GroundedAnswerStatus, RetrievalRerankResult
from mnemo.registry import PluginRegistry
from mnemo.retrieval import ContextBuilder, GroundedAnswerGenerator
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
from verify_module_6_7_context import _ControlledExtractor, _ExtractorPlugin

EVIDENCE = ROOT / "docs" / "milestone-evidence" / "module-6.8-grounded-answer.json"


class _ControlledSynthesizer:
    provider = "mnemo-acceptance"
    model = "controlled-synthesizer-v1"
    max_context_tokens = 131_072

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Message, ...], object, int]] = []

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_streaming=False,
            supports_json=False,
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
        self.calls.append((system, messages, structured_output, max_tokens))
        return CompletionResult(
            model=self.model,
            text=(
                "The available passage describes duty as grounded guidance in the Bhagavad "
                "Gita [source:1]."
            ),
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


class _SynthesizerPlugin:
    name = "mnemo-module-6-8-controlled-synthesizer"
    version = __version__
    core_version_range = ">=0.20.1"

    def __init__(self, provider: _ControlledSynthesizer) -> None:
        self.provider = provider

    def capabilities(self) -> tuple[str, ...]:
        return ("llm",)

    def register(self, registry: PluginRegistry) -> None:
        registry.register_llm("synthesizer", self.provider, priority=0)


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
    synthesizer = _ControlledSynthesizer()
    answer_registry = PluginRegistry(core_version=__version__)
    answer_registry.load_plugin(_SynthesizerPlugin(synthesizer))
    answer_registry.freeze()
    try:
        await rerank_registry.execute_startup_hooks()
        rerank_registry.freeze()
        rerank_result = await RerankingModule(rerank_registry).execute(
            cast(str, m65["query"]), fusion
        )
        if not isinstance(rerank_result, RetrievalRerankResult):
            raise AssertionError("real Module 6.6 handoff is unavailable")

        system_prompt = "Answer only from the attributed context."
        fixed = counter.count(_serialize_fixed_input(system_prompt, rerank_result, ()))
        mandatory = "\n\n".join(
            _render(index, item, item.fused_result.chunk.text, {})
            for index, item in enumerate(rerank_result.results[:3], 1)
        )
        sample_words = rerank_result.results[3].fused_result.chunk.text.split()[:50]
        sample = " ".join(sample_words)
        while counter.count(sample) > 100:
            sample_words.pop()
            sample = " ".join(sample_words)
        budget = fixed + counter.count(
            mandatory + "\n\n" + _render(4, rerank_result.results[3], sample, {})
        )
        context_result = await ContextBuilder(context_registry, counter).build(
            rerank_result,
            context_budget=budget,
            system_prompt=system_prompt,
        )
        if not context_result.items:
            raise AssertionError("real Module 6.7 handoff is empty")
        original_chunks = tuple(
            item.reranked_result.fused_result.chunk for item in context_result.items
        )

        generator = GroundedAnswerGenerator(answer_registry, counter)
        first_started = time.perf_counter()
        first = await generator.generate(context_result, max_output_tokens=256)
        first_seconds = time.perf_counter() - first_started
        second = await generator.generate(context_result, max_output_tokens=256)
        if first != second:
            raise AssertionError("identical validated synthesizer output changed the result")
        if first.status is not GroundedAnswerStatus.GENERATED or first.answer is None:
            raise AssertionError("grounded answer was not generated")
        markers = tuple(int(item) for item in re.findall(r"\[source:(\d+)\]", first.answer))
        if not markers or any(number > len(context_result.items) for number in markers):
            raise AssertionError("controlled answer did not contain an available source marker")
        if first.context_result is not context_result or first.query != rerank_result.query:
            raise AssertionError("Module 6.7 provenance or original query was replaced")
        evidence = first.generation_evidence
        if evidence is None or evidence.tokenizer_id != context_result.tokenizer_id:
            raise AssertionError("generation token evidence is unavailable")
        if evidence.answer_token_count != counter.count(first.answer):
            raise AssertionError("answer token accounting changed")
        if (
            tuple(item.reranked_result.fused_result.chunk for item in context_result.items)
            != original_chunks
        ):
            raise AssertionError("prior-stage canonical evidence was mutated")
        return {
            "verdict": "PASS",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
            "dataset_sha256": digest,
            "module_6_7_handoff": "real Module 6.6 reranking plus ADR-0043 context build",
            "query": first.query,
            "input_context_items": len(context_result.items),
            "omitted_context_items": len(context_result.omitted_results),
            "context_tokens": context_result.context_tokens,
            "available_context_tokens": context_result.available_context_tokens,
            "tokenizer_id": context_result.tokenizer_id,
            "provider": evidence.provider,
            "model": evidence.model,
            "prompt_token_count": evidence.prompt_token_count,
            "max_output_tokens": evidence.max_output_tokens,
            "answer_token_count": evidence.answer_token_count,
            "answer": first.answer,
            "source_markers": list(markers),
            "provider_calls": len(synthesizer.calls),
            "first_generation_seconds": first_seconds,
            "total_acceptance_seconds": time.perf_counter() - started,
            "deterministic_result_construction": True,
            "query_preserved": True,
            "provenance_preserved": True,
            "canonical_chunks_unchanged": True,
            "storage_access_by_module_6_8": False,
            "citations_created_by_module_6_8": False,
            "reranker_model_id": MODEL_ID,
            "reranker_model_revision": MODEL_REVISION,
        }
    finally:
        await rerank_registry.execute_shutdown_hooks()
        await ollama._client.aclose()
        await storage.close()
        del builtins


def main() -> int:
    evidence = asyncio.run(_run())
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
