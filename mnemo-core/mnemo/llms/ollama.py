"""Local Ollama implementation of the frozen language-model contract."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import cast

import httpx

from mnemo._version import __version__
from mnemo.config import LLMRoleConfig
from mnemo.interfaces import (
    CompletionResult,
    HealthStatus,
    IntegrityError,
    LLMCapabilities,
    Message,
)
from mnemo.models import FrozenMetadata, JSONValue
from mnemo.registry import PluginRegistry

_DEFAULT_API_BASE = "http://127.0.0.1:11434"


class OllamaLLM:
    """Execute text and schema-constrained completions through Ollama chat."""

    def __init__(self, config: LLMRoleConfig, *, api_base: str = _DEFAULT_API_BASE) -> None:
        if not isinstance(config, LLMRoleConfig):
            raise TypeError("config must be LLMRoleConfig")
        if not isinstance(api_base, str) or not api_base.strip():
            raise ValueError("api_base must be non-empty")
        self._model = config.model
        self._max_context_tokens = config.max_context_tokens
        self._client = httpx.AsyncClient(
            base_url=api_base.rstrip("/"), timeout=httpx.Timeout(300.0)
        )

    @property
    def provider(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_context_tokens(self) -> int:
        return self._max_context_tokens

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_streaming=True,
            supports_json=True,
            supports_vision=False,
            supports_reasoning=False,
        )

    async def complete(
        self,
        system: str,
        messages: tuple[Message, ...],
        structured_output: JSONValue = None,
        max_tokens: int = 1000,
    ) -> CompletionResult:
        payload = _payload(
            self._model,
            system,
            messages,
            max_tokens,
            structured_output=structured_output,
            stream=False,
            max_context_tokens=self._max_context_tokens,
        )
        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        content = _content(data)
        metadata = FrozenMetadata(
            {
                "done_reason": data.get("done_reason"),
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
            }
        )
        if structured_output is None:
            return CompletionResult(model=self._model, text=content, metadata=metadata)
        try:
            structured = cast(JSONValue, json.loads(content))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise IntegrityError("Ollama returned malformed structured JSON") from error
        return CompletionResult(model=self._model, structured=structured, metadata=metadata)

    async def stream(
        self,
        system: str,
        messages: tuple[Message, ...],
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        payload = _payload(
            self._model,
            system,
            messages,
            max_tokens,
            stream=True,
            max_context_tokens=self._max_context_tokens,
        )
        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    fragment = _content(json.loads(line), allow_empty=True)
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    raise IntegrityError("Ollama returned malformed streaming JSON") from error
                if fragment:
                    yield fragment

    async def health_check(self) -> HealthStatus:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            models = response.json().get("models", ())
            available = any(
                isinstance(item, dict)
                and (item.get("name") == self._model or item.get("model") == self._model)
                for item in models
            )
            return HealthStatus(
                healthy=available,
                component="OllamaLLM",
                checked_at=datetime.now(UTC),
                detail=None if available else f"Model {self._model} not found in Ollama",
            )
        except Exception as error:
            return HealthStatus(
                healthy=False,
                component="OllamaLLM",
                checked_at=datetime.now(UTC),
                detail=str(error),
            )

    async def initialize(self) -> None:
        status = await self.health_check()
        if not status.healthy:
            raise RuntimeError(f"Ollama LLM initialization failed: {status.detail}")

    async def close(self) -> None:
        await self._client.aclose()


class OllamaLLMPlugin:
    """Register configured Ollama role providers using the existing LLM family."""

    name = "mnemo-ollama-llm"
    version = __version__
    core_version_range = ">=0.20.1"

    def __init__(self, providers: tuple[tuple[str, OllamaLLM], ...]) -> None:
        self.providers = providers

    def capabilities(self) -> tuple[str, ...]:
        return ("llm",)

    def register(self, registry: PluginRegistry) -> None:
        for role, provider in self.providers:
            registry.register_llm(role, provider, priority=0)
            registry.register_startup_hook(provider.initialize)
            registry.register_shutdown_hook(provider.close)


def _payload(
    model: str,
    system: str,
    messages: tuple[Message, ...],
    max_tokens: int,
    *,
    structured_output: JSONValue = None,
    stream: bool,
    max_context_tokens: int | None = None,
) -> dict[str, object]:
    if not isinstance(system, str) or not system.strip():
        raise ValueError("system must be non-empty")
    if not isinstance(messages, tuple) or any(not isinstance(item, Message) for item in messages):
        raise TypeError("messages must be a tuple of Message values")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
        raise ValueError("max_tokens must be positive")
    wire_messages = [{"role": "system", "content": system}]
    wire_messages.extend({"role": item.role.value, "content": item.content} for item in messages)
    options: dict[str, object] = {"num_predict": max_tokens}
    if max_context_tokens is not None:
        options["num_ctx"] = max_context_tokens
    payload: dict[str, object] = {
        "model": model,
        "messages": wire_messages,
        "stream": stream,
        "options": options,
    }
    if structured_output is not None:
        payload["format"] = _wire_json(structured_output)
    return payload


def _wire_json(value: JSONValue) -> object:
    if isinstance(value, Mapping):
        return {key: _wire_json(nested) for key, nested in value.items()}
    if isinstance(value, tuple):
        return [_wire_json(nested) for nested in value]
    return value


def _content(data: object, *, allow_empty: bool = False) -> str:
    if not isinstance(data, dict):
        raise IntegrityError("Ollama response must be an object")
    message = data.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise IntegrityError("Ollama response is missing message content")
    content = cast(str, message["content"])
    if not allow_empty and not content.strip():
        raise IntegrityError("Ollama returned empty content")
    return content
