"""LLM provider abstraction: routing, validation, registry."""

from __future__ import annotations

import pytest

from config.settings import Settings
from core.exceptions import ConfigurationError
from llm.providers import create_provider


def test_openai_model_id_is_unprefixed() -> None:
    provider = create_provider(Settings(llm_provider="openai", llm_model="gpt-4o-mini"))
    assert provider.model_id() == "gpt-4o-mini"


def test_anthropic_model_id_gets_route_prefix() -> None:
    provider = create_provider(
        Settings(llm_provider="anthropic", llm_model="claude-sonnet-5")
    )
    assert provider.model_id() == "anthropic/claude-sonnet-5"


def test_prefix_is_not_duplicated() -> None:
    provider = create_provider(
        Settings(llm_provider="anthropic", llm_model="anthropic/claude-sonnet-5")
    )
    assert provider.model_id() == "anthropic/claude-sonnet-5"


def test_ollama_needs_no_key() -> None:
    provider = create_provider(Settings(llm_provider="ollama", llm_model="llama3"))
    provider.validate()  # must not raise
    assert provider.base_url() == "http://localhost:11434"


def test_missing_key_fails_fast() -> None:
    provider = create_provider(Settings(llm_provider="anthropic", anthropic_api_key=None))
    with pytest.raises(ConfigurationError, match="anthropic"):
        provider.validate()


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Unknown LLM provider"):
        create_provider(Settings(llm_provider="skynet"))
