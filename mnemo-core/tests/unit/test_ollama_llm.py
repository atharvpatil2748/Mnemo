"""Focused contract tests for the built-in Ollama LLM adapter."""

from __future__ import annotations

import json

import httpx
import pytest
from mnemo.config import LLMRoleConfig
from mnemo.interfaces import IntegrityError, LLMInterfaceV1, Message, MessageRole
from mnemo.llms import OllamaLLM
from mnemo.models import FrozenMetadata

pytestmark = pytest.mark.anyio


def _provider(handler: httpx.MockTransport) -> OllamaLLM:
    provider = OllamaLLM(
        LLMRoleConfig(provider="ollama", model="gemma4:e4b", max_context_tokens=8192)
    )
    provider._client = httpx.AsyncClient(transport=handler, base_url="http://ollama.test")
    return provider


async def test_text_and_structured_completion_use_exact_ollama_contract() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = '{"answer":"duty"}' if "format" in payload else "Duty [source:1]"
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": content},
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 4,
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    assert isinstance(provider, LLMInterfaceV1)
    message = Message(role=MessageRole.USER, content="Question")
    text = await provider.complete("System", (message,), max_tokens=50)
    structured = await provider.complete(
        "System",
        (message,),
        structured_output=FrozenMetadata({"type": "object", "required": ("answer",)}),
        max_tokens=20,
    )
    assert text.text == "Duty [source:1]" and text.model == "gemma4:e4b"
    assert structured.structured == {"answer": "duty"}
    assert requests[0]["messages"] == [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Question"},
    ]
    assert requests[0]["options"] == {"num_predict": 50, "num_ctx": 8192}
    assert requests[1]["format"] == {"required": ["answer"], "type": "object"}
    await provider.close()


async def test_health_initialization_and_streaming() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "gemma4:e4b"}]})
        body = (
            json.dumps({"message": {"content": "first"}})
            + "\n"
            + json.dumps({"message": {"content": ""}, "done": True})
            + "\n"
        )
        return httpx.Response(200, text=body)

    provider = _provider(httpx.MockTransport(handler))
    await provider.initialize()
    fragments = tuple([item async for item in provider.stream("System", (), max_tokens=5)])
    assert fragments == ("first",)
    await provider.close()


async def test_malformed_structured_output_is_integrity_failure() -> None:
    provider = _provider(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"message": {"content": "not json"}})
        )
    )
    with pytest.raises(IntegrityError, match="structured JSON"):
        await provider.complete("System", (), structured_output={"type": "object"})
    await provider.close()


async def test_ollama_properties_and_plugin() -> None:
    from mnemo.llms.ollama import OllamaLLMPlugin
    from mnemo.registry import PluginRegistry

    provider = _provider(
        httpx.MockTransport(lambda request: httpx.Response(200, json={"models": []}))
    )
    assert provider.provider == "ollama"
    assert provider.model == "gemma4:e4b"
    assert provider.max_context_tokens == 8192
    caps = provider.capabilities()
    assert caps.supports_streaming and caps.supports_json and not caps.supports_vision

    plugin = OllamaLLMPlugin((("synthesizer", provider),))
    assert plugin.capabilities() == ("llm",)
    registry = PluginRegistry(core_version="0.20.1")
    registry.load_plugin(plugin)
    assert registry.resolve_llm("synthesizer") is provider

    status = await provider.health_check()
    assert not status.healthy
    with pytest.raises(RuntimeError, match="initialization failed"):
        await provider.initialize()
    await provider.close()


def test_ollama_payload_validation() -> None:
    from mnemo.llms.ollama import _content, _payload

    with pytest.raises(TypeError):
        OllamaLLM("not config")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        OllamaLLM(LLMRoleConfig(provider="ollama", model="m", max_context_tokens=100), api_base="")
    with pytest.raises(ValueError):
        _payload("m", "", (), 10, stream=False)
    with pytest.raises(TypeError):
        _payload("m", "s", "not tuple", 10, stream=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _payload("m", "s", (), 0, stream=False)
    with pytest.raises(IntegrityError):
        _content("not dict")
    with pytest.raises(IntegrityError):
        _content({"message": "not dict"})
    with pytest.raises(IntegrityError):
        _content({"message": {"content": ""}})
