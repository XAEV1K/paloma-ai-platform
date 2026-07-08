"""Conversation Runtime: the channel-agnostic heart of the platform.

The runtime owns everything a conversational turn needs — history,
memory, intent-based agent routing, RAG grounding, streaming and
tracing — while knowing nothing about transports. Web chat, voice, API
and future WhatsApp/Telegram channels are thin adapters that feed text
in and stream tokens out; adding a channel never touches this package.
"""

from conversation.intents import Intent, RuleBasedIntentClassifier
from conversation.llm import ConversationLLMPort, StreamingConversationLLM
from conversation.memory import ConversationStorePort, JsonConversationStore
from conversation.models import ConversationState, ConversationTurn, TurnResult
from conversation.router import AgentRouter, AgentSpec
from conversation.runtime import ConversationRuntime

__all__ = [
    "AgentRouter",
    "AgentSpec",
    "ConversationLLMPort",
    "ConversationRuntime",
    "ConversationState",
    "ConversationStorePort",
    "ConversationTurn",
    "Intent",
    "JsonConversationStore",
    "RuleBasedIntentClassifier",
    "StreamingConversationLLM",
    "TurnResult",
]
