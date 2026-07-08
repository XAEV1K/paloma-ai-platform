"""Conversation Runtime: process one turn, channel-agnostically.

Turn lifecycle::

    text in ──► intent ──► agent spec ──► grounding (RAG / business data)
            ──► streamed LLM reply ──► memory ──► events ──► TurnResult

Design decisions:
- **Deterministic pre-fetch instead of LLM tool-calls.** The intent
  decides what grounding a turn needs (knowledge chunks, restaurant
  metrics); Python fetches it before the model runs. Predictable
  latency, predictable cost, no tool-loop failure modes. Agentic
  tool-calling remains available in the decision pipeline where it earns
  its complexity.
- **Streaming first.** Tokens flow to the channel via a callback, so a
  chat cursor and a TTS engine consume the same runtime.
- **Interruption is a memory operation.** When voice barge-in cuts a
  reply, the runtime rewrites the last assistant turn to exactly what
  was spoken — the model never believes it said words the user never
  heard.
"""

from __future__ import annotations

import time
from typing import Callable

from core.context import current_context
from core.exceptions import PalomaError
from core.logging import get_logger
from conversation.intents import IntentClassifierPort
from conversation.llm import ConversationLLMPort, Message
from conversation.memory import ConversationStorePort
from conversation.models import ConversationState, ConversationTurn, TurnResult
from conversation.router import AgentRouter
from crew.prompts import PromptRepository
from events.bus import EventBus
from events.events import ConversationTurnCompleted
from rag.context_builder import ContextBuilder
from rag.models import ContextPackage
from services.restaurant_service import RestaurantService

logger = get_logger("conversation.runtime")

#: Streaming sink: called once per generated token.
TokenCallback = Callable[[str], None]

_PLATFORM_PREAMBLE = (
    "You are part of the Paloma365 AI Operations Platform serving restaurant "
    "businesses in Kazakhstan. Answer in the user's language. Be concise and "
    "concrete. When context passages [S1], [S2], ... are provided, ground every "
    "factual claim in them and cite the marker; if the context does not cover "
    "the question, say so plainly instead of guessing."
)


class ConversationRuntime:
    """Channel-agnostic turn processor."""

    def __init__(
        self,
        store: ConversationStorePort,
        classifier: IntentClassifierPort,
        router: AgentRouter,
        llm: ConversationLLMPort,
        prompts: PromptRepository,
        context_builder: ContextBuilder | None,
        restaurant_service: RestaurantService,
        event_bus: EventBus,
        history_window: int = 8,
    ) -> None:
        self._store = store
        self._classifier = classifier
        self._router = router
        self._llm = llm
        self._prompts = prompts
        self._context_builder = context_builder
        self._restaurant_service = restaurant_service
        self._event_bus = event_bus
        self._history_window = history_window

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def process_turn(
        self,
        conversation_id: str,
        user_text: str,
        channel: str = "api",
        restaurant_id: str | None = None,
        on_token: TokenCallback | None = None,
    ) -> TurnResult:
        """Process one user utterance and return the completed turn."""
        started = time.monotonic()
        state = self._store.load(conversation_id) or ConversationState(
            conversation_id=conversation_id, channel=channel, restaurant_id=restaurant_id
        )
        if restaurant_id and not state.restaurant_id:
            state.restaurant_id = restaurant_id

        intent = self._classifier.classify(user_text)
        spec = self._router.route(intent)
        context_package = self._grounding(spec.use_rag, user_text)
        messages = self._build_messages(state, spec, user_text, context_package)

        reply = self._stream_reply(spec.role, messages, on_token)

        state.turns.append(ConversationTurn(role="user", content=user_text))
        state.turns.append(
            ConversationTurn(role="assistant", content=reply, agent_role=spec.role.value)
        )
        self._safe_save(state)

        latency_ms = round((time.monotonic() - started) * 1000, 1)
        self._publish(state, intent.value, spec.role.value, latency_ms)
        self._record_metrics(spec.display_name, started)

        logger.info(
            "Turn done: conversation=%s intent=%s agent=%s %.0fms (%d ctx chunk(s))",
            conversation_id,
            intent.value,
            spec.display_name,
            latency_ms,
            len(context_package.chunks) if context_package else 0,
        )
        return TurnResult(
            conversation_id=conversation_id,
            reply=reply,
            intent=intent.value,
            agent_role=spec.role.value,
            agent_display_name=spec.display_name,
            latency_ms=latency_ms,
            context=context_package,
        )

    def register_interruption(self, conversation_id: str, spoken_text: str) -> None:
        """Voice barge-in: shrink the last assistant turn to what was heard."""
        state = self._store.load(conversation_id)
        if state is None or not state.turns or state.turns[-1].role != "assistant":
            return
        last = state.turns[-1]
        state.turns[-1] = ConversationTurn(
            role="assistant",
            content=spoken_text,
            at=last.at,
            agent_role=last.agent_role,
            interrupted=True,
        )
        self._safe_save(state)
        logger.info(
            "Interruption registered: conversation=%s, reply truncated to %d char(s)",
            conversation_id,
            len(spoken_text),
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _grounding(self, use_rag: bool, query: str) -> ContextPackage | None:
        if not use_rag or self._context_builder is None:
            return None
        try:
            package = self._context_builder.build(query)
            return None if package.is_empty else package
        except PalomaError as exc:
            logger.warning("RAG grounding unavailable (%s) — answering ungrounded", exc)
            return None

    def _build_messages(
        self,
        state: ConversationState,
        spec,
        user_text: str,
        context_package: ContextPackage | None,
    ) -> list[Message]:
        system = _PLATFORM_PREAMBLE + "\n\n" + self._prompts.load(spec.prompt_name)
        if spec.use_business_data and state.restaurant_id:
            system += "\n\n" + self._business_block(state.restaurant_id)
        messages: list[Message] = [{"role": "system", "content": system}]
        for turn in state.window(self._history_window):
            messages.append({"role": turn.role, "content": turn.content})
        if context_package is not None:
            messages.append(
                {
                    "role": "system",
                    "content": "Knowledge base context:\n\n" + context_package.text,
                }
            )
        messages.append({"role": "user", "content": user_text})
        return messages

    def _business_block(self, restaurant_id: str) -> str:
        try:
            metrics = self._restaurant_service.get_metrics(restaurant_id)
        except PalomaError:
            return ""
        return (
            "Business context (deterministic data — quote, never recompute): "
            + metrics.model_dump_json()
        )

    def _stream_reply(
        self, role, messages: list[Message], on_token: TokenCallback | None
    ) -> str:
        tokens: list[str] = []
        for token in self._llm.stream(role, messages):
            tokens.append(token)
            if on_token is not None:
                on_token(token)
        return "".join(tokens).strip()

    def _safe_save(self, state: ConversationState) -> None:
        try:
            self._store.save(state)
        except Exception:  # noqa: BLE001 — memory loss must not kill the turn
            logger.exception("Conversation persistence failed — turn continues unrecorded")

    def _publish(self, state: ConversationState, intent: str, role: str, latency: float) -> None:
        context = current_context()
        self._event_bus.publish(
            ConversationTurnCompleted(
                request_id=context.request_id if context else "conversation",
                conversation_id=state.conversation_id,
                channel=state.channel,
                intent=intent,
                agent_role=role,
                latency_ms=latency,
            )
        )

    @staticmethod
    def _record_metrics(stage_name: str, started: float) -> None:
        context = current_context()
        if context is None:
            return
        duration = time.monotonic() - started
        context.metrics.record_tool_call(f"turn:{stage_name}", duration, ok=True)
        context.tracer.record_tool(f"turn:{stage_name}", context.tracer.now_offset() - duration, duration)
