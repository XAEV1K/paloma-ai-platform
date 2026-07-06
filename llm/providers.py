"""Credential/endpoint resolvers for LLM vendors.

A provider answers three questions about a model id:
1. Is this model mine? (``model_prefix`` match)
2. Which credential / base URL does it need?
3. Is the configuration usable right now? (``validate`` — fail fast)

Providers do NOT construct LLM handles — that is the router's job
(:mod:`llm.routing`), and it happens lazily so that commands which never
call a model (``--list-restaurants``, tests) never require a key.

Resolution policy (explicit over clever):
- A model id carrying a known prefix (``openrouter/``, ``anthropic/``,
  ``gemini/``, ``ollama/``) is routed to that vendor as-is.
- An unprefixed id is qualified by the *default* provider
  (``LLM_PROVIDER``). With ``LLM_PROVIDER=openrouter`` always write full
  catalog paths (``openrouter/openai/gpt-4o-mini``) — the platform will
  not guess a vendor segment for you.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from config.settings import Settings
from core.exceptions import ConfigurationError


class BaseLLMProvider(ABC):
    """Vendor integration: prefix routing + credentials + fail-fast checks."""

    #: Registry key used in ``LLM_PROVIDER``.
    name: ClassVar[str]
    #: LiteLLM route prefix, e.g. ``anthropic/``. Empty for the default route.
    model_prefix: ClassVar[str] = ""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # --- hooks -----------------------------------------------------------
    @abstractmethod
    def api_key(self) -> str | None:
        """The credential this vendor requires (``None`` for keyless backends)."""

    def base_url(self) -> str | None:
        """Override for self-hosted/gateway backends (Ollama, OpenRouter)."""
        return None

    def requires_api_key(self) -> bool:
        return True

    # --- template ---------------------------------------------------------
    def qualify(self, model_id: str) -> str:
        """Return the fully-qualified LiteLLM model id for this vendor."""
        if self.model_prefix and not model_id.startswith(self.model_prefix):
            return f"{self.model_prefix}{model_id}"
        return model_id

    def validate(self) -> None:
        """Fail fast, before any agent runs, if the provider is unusable."""
        if self.requires_api_key() and not self.api_key():
            raise ConfigurationError(
                f"LLM provider '{self.name}' requires an API key. "
                f"Set the appropriate variable in .env (see .env.example)."
            )


class OpenAIProvider(BaseLLMProvider):
    name = "openai"
    model_prefix = ""

    def api_key(self) -> str | None:
        return self._settings.openai_api_key


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"
    model_prefix = "anthropic/"

    def api_key(self) -> str | None:
        return self._settings.anthropic_api_key


class GeminiProvider(BaseLLMProvider):
    name = "gemini"
    model_prefix = "gemini/"

    def api_key(self) -> str | None:
        return self._settings.gemini_api_key


class OpenRouterProvider(BaseLLMProvider):
    """One credential, every frontier model — ideal for per-role routing."""

    name = "openrouter"
    model_prefix = "openrouter/"

    def api_key(self) -> str | None:
        return self._settings.openrouter_api_key

    def base_url(self) -> str | None:
        return "https://openrouter.ai/api/v1"


class OllamaProvider(BaseLLMProvider):
    """Local models: zero marginal cost, full data privacy."""

    name = "ollama"
    model_prefix = "ollama/"

    def api_key(self) -> str | None:
        return None

    def requires_api_key(self) -> bool:
        return False

    def base_url(self) -> str | None:
        return self._settings.ollama_base_url


_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    provider.name: provider
    for provider in (
        OpenAIProvider,
        AnthropicProvider,
        GeminiProvider,
        OpenRouterProvider,
        OllamaProvider,
    )
}


def create_provider(settings: Settings, name: str | None = None) -> BaseLLMProvider:
    """Resolve a provider by name (defaults to ``LLM_PROVIDER``)."""
    key = (name or settings.llm_provider).lower()
    provider_cls = _PROVIDERS.get(key)
    if provider_cls is None:
        raise ConfigurationError(
            f"Unknown LLM provider '{key}'. Valid options: {', '.join(sorted(_PROVIDERS))}."
        )
    return provider_cls(settings)


def provider_for_model(model_id: str, settings: Settings) -> BaseLLMProvider:
    """Route a model id to its vendor by prefix, else to the default provider."""
    for provider_cls in _PROVIDERS.values():
        if provider_cls.model_prefix and model_id.startswith(provider_cls.model_prefix):
            return provider_cls(settings)
    return create_provider(settings)
