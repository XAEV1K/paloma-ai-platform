"""Streaming LLM port for conversations.

Why not CrewAI here: crews are the right tool for the multi-stage
decision pipeline, but a conversational turn is one call that must
stream tokens to the channel (chat cursor, TTS). This adapter talks to
the provider's OpenAI-compatible endpoint directly, reusing the same
``LLMRouter`` routing table — one place still decides which model serves
which role.
"""

from __future__ import annotations

from typing import Iterator, Protocol

from config.settings import Settings
from core.logging import get_logger
from llm.providers import provider_for_model
from llm.routing import AgentRole, LLMRouter

logger = get_logger("conversation.llm")

#: Chat messages in the OpenAI wire format.
Message = dict[str, str]


class ConversationLLMPort(Protocol):
    """Streamed completion for one conversational turn."""

    def stream(self, role: AgentRole, messages: list[Message]) -> Iterator[str]: ...


class StreamingConversationLLM:
    """OpenAI-SDK streaming adapter over the platform's model routing."""

    def __init__(self, settings: Settings, router: LLMRouter) -> None:
        self._settings = settings
        self._router = router
        self._clients: dict[str, object] = {}

    def stream(self, role: AgentRole, messages: list[Message]) -> Iterator[str]:
        resolved = self._router.resolve(role)
        provider = provider_for_model(self._router.resolve(role).model_id, self._settings)
        provider.validate()
        client = self._client_for(provider)
        # The provider prefix routes inside LiteLLM; the raw API expects
        # the catalog slug without it (e.g. 'anthropic/claude-sonnet-5').
        api_model = resolved.model_id.removeprefix(provider.model_prefix)

        logger.debug("Streaming turn via %s (role=%s)", resolved.model_id, role.value)
        stream = client.chat.completions.create(  # type: ignore[attr-defined]
            model=api_model,
            messages=messages,
            temperature=resolved.temperature,
            stream=True,
        )
        for event in stream:
            choices = getattr(event, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            token = getattr(delta, "content", None) if delta else None
            if token:
                yield token

    def _client_for(self, provider: object) -> object:
        key = getattr(provider, "name", "default")
        if key not in self._clients:
            from openai import OpenAI  # local import: keep module import light

            self._clients[key] = OpenAI(
                api_key=provider.api_key(),  # type: ignore[attr-defined]
                base_url=provider.base_url(),  # type: ignore[attr-defined]
            )
        return self._clients[key]
