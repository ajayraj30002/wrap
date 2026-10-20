from src.providers.anthropic import AnthropicAdapter
from src.providers.base import ProviderAdapter
from src.providers.gemini import GeminiAdapter
from src.providers.openai_compatible import (
    CerebrasAdapter,
    CohereAdapter,
    DeepSeekAdapter,
    FireworksAdapter,
    GroqAdapter,
    MistralAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
    PerplexityAdapter,
    SambaNovaAdapter,
    TogetherAdapter,
    XAIAdapter,
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        self._adapters.pop(name, None)

    def get(self, name: str) -> ProviderAdapter:
        return self._adapters[name]

    def all(self) -> list[ProviderAdapter]:
        return list(self._adapters.values())

    def names(self) -> list[str]:
        return list(self._adapters)


registry = ProviderRegistry()
# Big Frontier & Foundation Labs
registry.register(OpenAIAdapter())
registry.register(AnthropicAdapter())
registry.register(GeminiAdapter())

# Fast Inference & LPUs
registry.register(GroqAdapter())
registry.register(CerebrasAdapter())
registry.register(SambaNovaAdapter())

# Open Source / Open Weights Ecosystem
registry.register(DeepSeekAdapter())
registry.register(MistralAdapter())
registry.register(TogetherAdapter())
registry.register(FireworksAdapter())

# Search, Aggregation & Frontier Specialized
registry.register(OpenRouterAdapter())
registry.register(PerplexityAdapter())
registry.register(XAIAdapter())
registry.register(CohereAdapter())

