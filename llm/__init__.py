"""LLM layer: vendor resolution + role-based multi-model routing.

The platform is model-agnostic by contract: agents receive LLM handles
from :class:`LLMRouter`, which maps pipeline roles to models via config
(``MODEL_ARCHITECT`` / ``MODEL_DEVELOPER`` / ``MODEL_VALIDATOR``).
"""

from llm.providers import (
    AnthropicProvider,
    BaseLLMProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    create_provider,
    provider_for_model,
)
from llm.routing import AgentRole, LLMRouter, ResolvedModel

__all__ = [
    "AgentRole",
    "AnthropicProvider",
    "BaseLLMProvider",
    "GeminiProvider",
    "LLMRouter",
    "OllamaProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "ResolvedModel",
    "create_provider",
    "provider_for_model",
]
