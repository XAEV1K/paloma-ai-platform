"""LLM providers behind one abstract base.

The rest of the platform never mentions a vendor: ``AgentFactory``
receives a ready ``crewai.LLM`` built by whichever provider the operator
selected via ``LLM_PROVIDER`` in ``.env``. Switching Claude ↔ GPT ↔
Gemini ↔ OpenRouter ↔ local Ollama is a config change, zero code.

Each provider knows three things:
1. how to prefix the model id for LiteLLM routing,
2. which credential it needs,
3. how to fail fast (``validate``) when that credential is missing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from crewai import LLM

from config.settings import Settings
from core.exceptions import ConfigurationError
from core.logging import get_logger

logger = get_logger("llm.providers")


class BaseLLMProvider(ABC):
    """Template for a vendor integration (Template Method pattern)."""

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
    def model_id(self) -> str:
        """Fully-qualified LiteLLM model id."""
        model = self._settings.llm_model
        if self.model_prefix and not model.startswith(self.model_prefix):
            return f"{self.model_prefix}{model}"
        return model

    def validate(self) -> None:
        """Fail fast, before any agent runs, if the provider is unusable."""
        if self.requires_api_key() and not self.api_key():
            raise ConfigurationError(
                f"LLM provider '{self.name}' requires an API key. "
                f"Set the appropriate variable in .env (see .env.example)."
            )

    def build(self) -> LLM:
        """Construct the CrewAI LLM handle for this provider."""
        logger.info("LLM provider '%s' -> model '%s'", self.name, self.model_id())
        return LLM(
            model=self.model_id(),
            temperature=self._settings.llm_temperature,
            api_key=self.api_key(),
            base_url=self.base_url(),
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


def create_provider(settings: Settings) -> BaseLLMProvider:
    """Resolve the configured provider or fail with the list of valid options."""
    provider_cls = _PROVIDERS.get(settings.llm_provider.lower())
    if provider_cls is None:
        raise ConfigurationError(
            f"Unknown LLM provider '{settings.llm_provider}'. "
            f"Valid options: {', '.join(sorted(_PROVIDERS))}."
        )
    return provider_cls(settings)
