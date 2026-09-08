"""Selects an LLMProvider based on the LLM_PROVIDER env var."""

from janet import config
from janet.agents.base import LLMProvider
from janet.agents.providers import GeminiProvider, GroqProvider, OllamaProvider

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "ollama": OllamaProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    key = (name or config.LLM_PROVIDER).lower()
    if key not in _PROVIDERS:
        raise ValueError(f"Unknown LLM_PROVIDER {key!r}. Valid options: {', '.join(_PROVIDERS)}")
    return _PROVIDERS[key]()
