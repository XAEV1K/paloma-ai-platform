"""Multi-model routing: prefix resolution, role mapping, fail-fast validation."""

from __future__ import annotations

import pytest

from config.settings import Settings
from core.exceptions import ConfigurationError
from llm.providers import create_provider, provider_for_model
from llm.routing import AgentRole, LLMRouter


def _settings(**overrides: object) -> Settings:
    """Isolated settings.

    ``_env_file=None`` skips the developer's .env, but third-party libs
    (litellm) call ``load_dotenv()`` at import time and leak it into
    ``os.environ`` — so routing-relevant fields are pinned explicitly
    (init kwargs always win over environment values).
    """
    params: dict[str, object] = {
        "model_architect": None,
        "model_developer": None,
        "model_validator": None,
        "llm_temperature": None,
    }
    params.update(overrides)
    return Settings(_env_file=None, **params)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# provider resolution
# ---------------------------------------------------------------------------
def test_known_prefix_routes_to_its_vendor() -> None:
    settings = _settings(llm_provider="openai")
    assert provider_for_model("openrouter/openai/gpt-4o-mini", settings).name == "openrouter"
    assert provider_for_model("anthropic/claude-sonnet-5", settings).name == "anthropic"
    assert provider_for_model("ollama/llama3", settings).name == "ollama"


def test_unprefixed_model_falls_back_to_default_provider() -> None:
    settings = _settings(llm_provider="openrouter")
    provider = provider_for_model("openai/gpt-4o-mini", settings)  # no known prefix
    assert provider.name == "openrouter"
    assert provider.qualify("openai/gpt-4o-mini") == "openrouter/openai/gpt-4o-mini"


def test_unknown_default_provider_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Unknown LLM provider"):
        create_provider(_settings(llm_provider="skynet"))


# ---------------------------------------------------------------------------
# role routing
# ---------------------------------------------------------------------------
def test_roles_fall_back_to_default_model() -> None:
    router = LLMRouter(_settings(llm_provider="openai", llm_model="gpt-4o-mini"))
    for role in AgentRole:
        assert router.resolve(role).model_id == "gpt-4o-mini"


def test_per_role_models_win_over_fallback() -> None:
    router = LLMRouter(
        _settings(
            llm_provider="openrouter",
            llm_model="openrouter/openai/gpt-4o-mini",
            model_architect="openrouter/anthropic/claude-sonnet-5",
            model_validator="openrouter/google/gemini-2.5-flash",
        )
    )
    assert router.resolve(AgentRole.ARCHITECT).model_id == "openrouter/anthropic/claude-sonnet-5"
    assert router.resolve(AgentRole.DEVELOPER).model_id == "openrouter/openai/gpt-4o-mini"
    assert router.resolve(AgentRole.VALIDATOR).model_id == "openrouter/google/gemini-2.5-flash"


def test_role_temperature_policy() -> None:
    router = LLMRouter(_settings())
    assert router.resolve(AgentRole.ARCHITECT).temperature == 0.2
    assert router.resolve(AgentRole.DEVELOPER).temperature == 0.1
    assert router.resolve(AgentRole.VALIDATOR).temperature == 0.0


def test_global_temperature_override() -> None:
    router = LLMRouter(_settings(llm_temperature=0.5))
    assert all(router.resolve(role).temperature == 0.5 for role in AgentRole)


def test_describe_covers_every_role() -> None:
    table = LLMRouter(_settings()).describe()
    assert set(table) == {role.value for role in AgentRole}


# ---------------------------------------------------------------------------
# validation & lifecycle
# ---------------------------------------------------------------------------
def test_validate_fails_fast_on_missing_key() -> None:
    router = LLMRouter(_settings(llm_provider="openrouter", openrouter_api_key=None))
    with pytest.raises(ConfigurationError, match="openrouter"):
        router.validate()


def test_validate_checks_every_provider_in_the_table() -> None:
    router = LLMRouter(
        _settings(
            llm_provider="openai",
            openai_api_key="sk-test",
            model_validator="anthropic/claude-haiku-4-5",  # second vendor, no key
        )
    )
    with pytest.raises(ConfigurationError, match="anthropic"):
        router.validate()


def test_keyless_ollama_validates() -> None:
    LLMRouter(_settings(llm_model="ollama/llama3")).validate()  # must not raise


def test_llm_handles_are_cached_per_role() -> None:
    router = LLMRouter(
        _settings(llm_provider="openai", llm_model="gpt-4o-mini", openai_api_key="sk-test")
    )
    assert router.llm_for(AgentRole.DEVELOPER) is router.llm_for(AgentRole.DEVELOPER)
