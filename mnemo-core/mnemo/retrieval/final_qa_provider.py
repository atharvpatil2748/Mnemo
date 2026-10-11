"""Governed adapter from the configured LLM contract to Final-QA V2."""

from __future__ import annotations

import hashlib
import json
import re

from mnemo.interfaces import LLMInterfaceV1, Message, MessageRole
from mnemo.models import FrozenMetadata
from mnemo.models.multimodal import (
    EvidenceKindV2,
    MultimodalGenerationRequestV1,
    MultimodalGenerationResultV1,
    MultimodalProviderCapabilitiesV1,
    ProviderModalityState,
)


class LLMFinalQAV2Provider:
    """Use one explicitly configured LLM as the text Final-QA V2 generator."""

    def __init__(self, llm: LLMInterfaceV1) -> None:
        if not isinstance(llm, LLMInterfaceV1):
            raise TypeError("llm must implement LLMInterfaceV1")
        self._llm = llm

    def capabilities(self) -> MultimodalProviderCapabilitiesV1:
        llm_caps = self._llm.capabilities()
        visual_state = (
            ProviderModalityState.SUPPORTED
            if llm_caps.supports_vision
            else ProviderModalityState.UNSUPPORTED
        )
        states = {
            kind.value: ProviderModalityState.SUPPORTED.value
            for kind in EvidenceKindV2
            if kind not in {EvidenceKindV2.ASSET_OCCURRENCE, EvidenceKindV2.VISUAL_VECTOR_MATCH}
        }
        states[EvidenceKindV2.ASSET_OCCURRENCE.value] = visual_state.value
        states[EvidenceKindV2.VISUAL_VECTOR_MATCH.value] = visual_state.value
        digest = hashlib.sha256(
            json.dumps(
                {"provider": self._llm.provider, "model": self._llm.model},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return MultimodalProviderCapabilitiesV1(
            provider=self._llm.provider,
            model=self._llm.model,
            profile=f"final_qa_v2:{self._llm.model}",
            configuration_digest=digest,
            modality_states=FrozenMetadata(states),
            max_context_tokens=self._llm.max_context_tokens,
            max_output_tokens=4096,
        )

    async def complete(
        self, request: MultimodalGenerationRequestV1
    ) -> MultimodalGenerationResultV1:
        result = await self._llm.complete(
            request.system_prompt,
            (
                Message(
                    role=MessageRole.USER,
                    content=request.rendered_context + "\n\n" + request.query,
                ),
            ),
            max_tokens=request.max_output_tokens,
        )
        if result.text is None:
            raise ValueError("Final-QA provider requires a text completion")
        prompt_tokens = _metadata_count(result.metadata.get("prompt_eval_count"))
        answer_tokens = _metadata_count(result.metadata.get("eval_count")) or max(
            1, len(result.text.split())
        )
        raw_reason = result.metadata.get("done_reason")
        reason = (
            raw_reason
            if isinstance(raw_reason, str) and raw_reason in {"stop", "length"}
            else "unknown"
        )
        complete = reason != "length"
        if result.metadata.get("done") is False or (raw_reason is not None and reason == "unknown"):
            reason, complete = "interrupted", False
        elif reason == "unknown" and answer_tokens >= request.max_output_tokens:
            reason, complete = "length", False
        if complete and _incomplete_markdown(result.text):
            reason, complete = "incomplete_markdown", False
        return MultimodalGenerationResultV1(
            answer=result.text,
            provider=self._llm.provider,
            model=self._llm.model,
            prompt_tokens=prompt_tokens,
            answer_tokens=max(1, answer_tokens),
            termination_reason=reason,
            output_complete=complete,
        )


def _incomplete_markdown(answer: str) -> bool:
    """Reject obvious unclosed formatting, never guess missing prose or repair it."""
    if answer.count("```") % 2:
        return True
    prose = re.sub(r"```.*?```", "", answer, flags=re.S)
    prose = re.sub(r"\\.", "", prose)
    return prose.count("**") % 2 != 0 or prose.count("`") % 2 != 0


def _metadata_count(value: object) -> int:
    """Read optional provider token counters without trusting arbitrary metadata."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0
