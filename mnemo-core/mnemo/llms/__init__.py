"""Built-in provider-neutral language-model adapters."""

from .ollama import OllamaLLM, OllamaLLMPlugin

__all__ = ["OllamaLLM", "OllamaLLMPlugin"]
