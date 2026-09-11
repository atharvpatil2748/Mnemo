from __future__ import annotations

from types import SimpleNamespace

import pytest
from mnemo.interfaces import CompletionResult, LLMCapabilities
from mnemo.models import FrozenMetadata
from mnemo.models.multimodal import MultimodalGenerationRequestV1, ProviderModalityState
from mnemo.retrieval.final_qa_provider import LLMFinalQAV2Provider, _metadata_count


class LLM:
    provider = "test-provider"
    model = "test-model"
    max_context_tokens = 8192

    def __init__(self, result: CompletionResult) -> None:
        self.result = result
        self.call: object | None = None

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_streaming=False,
            supports_json=True,
            supports_vision=True,
            supports_reasoning=False,
        )

    async def complete(self, system, messages, **kwargs):  # type: ignore[no-untyped-def]
        self.call = (system, messages, kwargs)
        return self.result

    def stream(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def health_check(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(healthy=True)


def _request() -> MultimodalGenerationRequestV1:
    return MultimodalGenerationRequestV1(
        system_prompt="grounded only",
        query="What happened?",
        rendered_context="[source:1] Exact evidence",
        resource_handles=(),
        context_snapshot_identity="a" * 64,
        max_output_tokens=123,
    )


@pytest.mark.anyio
async def test_final_qa_provider_maps_capabilities_prompt_and_token_metadata() -> None:
    llm = LLM(
        CompletionResult(
            model="test-model",
            text="Grounded answer",
            metadata=FrozenMetadata({"prompt_eval_count": "12", "eval_count": 3.9}),
        )
    )
    provider = LLMFinalQAV2Provider(llm)
    capabilities = provider.capabilities()
    assert capabilities.provider == "test-provider"
    assert capabilities.modality_states["asset_occurrence"] == ProviderModalityState.SUPPORTED

    result = await provider.complete(_request())
    assert result.answer == "Grounded answer"
    assert result.prompt_tokens == 12
    assert result.answer_tokens == 3
    system, messages, options = llm.call  # type: ignore[misc]
    assert system == "grounded only"
    assert messages[0].content.endswith("What happened?")
    assert options["max_tokens"] == 123


@pytest.mark.anyio
async def test_final_qa_provider_fails_closed_without_text_and_counts_fallback_words() -> None:
    llm = LLM(CompletionResult(model="test-model", structured=FrozenMetadata({"ok": True})))
    provider = LLMFinalQAV2Provider(llm)
    with pytest.raises(ValueError, match="requires a text completion"):
        await provider.complete(_request())

    llm.result = CompletionResult(model="test-model", text="three word answer")
    result = await provider.complete(_request())
    assert result.prompt_tokens == 0
    assert result.answer_tokens == 3


@pytest.mark.parametrize(
    ("value", "expected"),
    ((True, 0), (-3, 0), (2, 2), (-2.9, 0), ("7", 7), ("bad", 0), (None, 0)),
)
def test_provider_token_metadata_is_untrusted(value: object, expected: int) -> None:
    assert _metadata_count(value) == expected


def test_final_qa_provider_requires_llm_protocol() -> None:
    with pytest.raises(TypeError, match="LLMInterfaceV1"):
        LLMFinalQAV2Provider(object())  # type: ignore[arg-type]
