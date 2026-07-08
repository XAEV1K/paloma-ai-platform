"""Conversation Runtime: intents, routing, memory, grounding, interruption."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from config.settings import Settings
from conversation.intents import Intent, RuleBasedIntentClassifier
from conversation.memory import InMemoryConversationStore, JsonConversationStore
from conversation.models import ConversationState, ConversationTurn
from conversation.router import AgentRouter
from conversation.runtime import ConversationRuntime
from crew.prompts import PromptRepository
from events.bus import InMemoryEventBus
from events.events import ConversationTurnCompleted
from llm.routing import AgentRole
from rag.chunking import ChunkingService
from rag.context_builder import ContextBuilder
from rag.embeddings import HashingEmbedder
from rag.models import Document
from rag.retrieval import RerankerService, RetrievalService
from rag.vector_store import InMemoryVectorStore
from services.restaurant_service import CsvMetricsRepository, RestaurantService


class FakeLLM:
    """Captures messages, streams a canned reply token by token."""

    def __init__(self, reply: str = "Canned grounded reply.") -> None:
        self.reply = reply
        self.calls: list[tuple[AgentRole, list[dict]]] = []

    def stream(self, role: AgentRole, messages: list[dict]) -> Iterator[str]:
        self.calls.append((role, messages))
        for index, token in enumerate(self.reply.split(" ")):
            yield (" " if index else "") + token


def _context_builder() -> ContextBuilder:
    embedder = HashingEmbedder()
    store = InMemoryVectorStore()
    chunker = ChunkingService()
    doc = Document(
        doc_id=Document.make_id("faq"), source="faq.md", title="FAQ", media_type="markdown"
    )
    chunks = chunker.split(
        doc, "# FAQ\n\n## Tokens\n\nExpired marketplace tokens need re-authorisation."
    )
    store.add(chunks, embedder.embed([c.text for c in chunks]))
    return ContextBuilder(
        RetrievalService(embedder, store, RerankerService(), top_k=3, candidate_pool=10)
    )


@pytest.fixture()
def runtime_parts(settings: Settings):
    llm = FakeLLM()
    bus = InMemoryEventBus()
    store = InMemoryConversationStore()
    runtime = ConversationRuntime(
        store=store,
        classifier=RuleBasedIntentClassifier(),
        router=AgentRouter(),
        llm=llm,
        prompts=PromptRepository(settings.prompts_dir, "v1"),
        context_builder=_context_builder(),
        restaurant_service=RestaurantService(CsvMetricsRepository(settings.restaurants_csv)),
        event_bus=bus,
    )
    return runtime, llm, store, bus


# --- intents ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Delivery orders are not working, help!", Intent.SUPPORT),
        ("Сколько стоит модуль доставки?", Intent.SALES),
        ("Show me our revenue metrics please", Intent.ANALYTICS),
        ("Does the API support webhooks?", Intent.TECHNICAL),
        ("Good morning!", Intent.GENERAL),
    ],
)
def test_intent_classification(text: str, expected: Intent) -> None:
    assert RuleBasedIntentClassifier().classify(text) == expected


# --- runtime ---------------------------------------------------------------------
def test_turn_routes_streams_and_persists(runtime_parts) -> None:
    runtime, llm, store, bus = runtime_parts
    received: list[str] = []
    events: list = []
    bus.subscribe(ConversationTurnCompleted, events.append)

    result = runtime.process_turn(
        "conv-1", "The marketplace token expired, how do I fix it?",
        channel="chat", on_token=received.append,
    )

    assert result.agent_display_name == "Support Agent"
    assert result.reply == llm.reply
    assert "".join(received).replace("Canned", "Canned") != ""  # streaming happened
    state = store.load("conv-1")
    assert state is not None and [t.role for t in state.turns] == ["user", "assistant"]
    assert len(events) == 1 and events[0].intent == "SUPPORT"


def test_support_turn_is_rag_grounded(runtime_parts) -> None:
    runtime, llm, _, _ = runtime_parts
    result = runtime.process_turn("conv-2", "token expired error, what do I do?")

    assert result.context is not None and not result.context.is_empty
    _, messages = llm.calls[-1]
    assert any("Knowledge base context" in m["content"] for m in messages)


def test_analytics_turn_injects_business_data_not_rag(runtime_parts) -> None:
    runtime, llm, _, _ = runtime_parts
    result = runtime.process_turn(
        "conv-3", "analyse our revenue performance", restaurant_id="R-001"
    )

    assert result.agent_display_name == "Business Analyst"
    assert result.context is None
    role, messages = llm.calls[-1]
    assert role is AgentRole.ARCHITECT
    assert any("Business context" in m["content"] for m in messages)
    assert any("Dastarkhan Lounge" in m["content"] for m in messages)


def test_history_window_flows_into_messages(runtime_parts) -> None:
    runtime, llm, _, _ = runtime_parts
    runtime.process_turn("conv-4", "hello there")
    runtime.process_turn("conv-4", "and one more question")

    _, messages = llm.calls[-1]
    contents = [m["content"] for m in messages]
    assert "hello there" in contents  # prior user turn present


def test_interruption_rewrites_last_assistant_turn(runtime_parts) -> None:
    runtime, _, store, _ = runtime_parts
    runtime.process_turn("conv-5", "help with something broken")

    runtime.register_interruption("conv-5", "Only these words were")

    state = store.load("conv-5")
    last = state.turns[-1]
    assert last.role == "assistant"
    assert last.content == "Only these words were"
    assert last.interrupted is True


# --- persistence --------------------------------------------------------------------
def test_json_store_roundtrip(tmp_path: Path) -> None:
    store = JsonConversationStore(tmp_path / "conversations.json")
    state = ConversationState(conversation_id="c-1", channel="chat")
    state.turns.append(ConversationTurn(role="user", content="hi"))
    store.save(state)

    loaded = store.load("c-1")
    assert loaded is not None
    assert loaded.turns[0].content == "hi"
    assert store.load("missing") is None
