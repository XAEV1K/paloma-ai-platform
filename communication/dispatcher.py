"""Message dispatcher: the one path every channel's message travels.

Per message::

    InboundMessage ──► session (address → conversation, restaurant)
        ──► Conversation Runtime (intent → memory → RAG → capabilities → LLM)
             ──► ResponseBuilder ──► transport.send ──► MessageReport

Guarantees:
- **No message is ever ghosted**: a failed turn produces a polite
  fallback reply; a failed delivery is reported, never raised into the
  listener loop.
- **Every message is observable**: the dispatcher opens an
  ExecutionContext per message and emits a one-line runtime timeline
  (received → intent → retrieval → LLM → response → delivered) with
  latencies, plus token/cost via the standard run metrics.
"""

from __future__ import annotations

import time
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from core.context import ExecutionContext, execution_scope
from core.exceptions import RestaurantNotFoundError
from core.logging import get_logger
from conversation.runtime import ConversationRuntime
from communication.response_builder import ResponseBuilder
from communication.router import ChannelRouter
from communication.session import CommunicationSession, SessionManager
from communication.transport import InboundMessage, OutboundMessage
from services.restaurant_service import RestaurantService

logger = get_logger("communication.dispatcher")

_HELP_TEXT = (
    "Команды платформы:\n"
    "/restaurant R-001 — привязать ресторан к этому чату\n"
    "/restaurant — показать текущую привязку\n"
    "/reset — начать разговор заново\n"
    "/help — эта справка\n\n"
    "Просто напишите вопрос — о продуктах Paloma365, поддержке или "
    "показателях вашего ресторана."
)


class MessageReport(BaseModel):
    """The runtime timeline of one processed message."""

    model_config = ConfigDict(frozen=True)

    channel: str
    sender: str
    intent: str = ""
    agent: str = ""
    restaurant_id: str | None = None
    retrieval_ms: float = 0.0
    retrieval_chunks: int = 0
    llm_ms: float = 0.0
    reply_chars: int = 0
    delivery_ms: float = 0.0
    delivery_id: str = ""
    total_ms: float = 0.0
    ok: bool = True
    error: str = ""

    def timeline(self) -> str:
        """The observability line the operator sees per message."""
        received = datetime.now().strftime("%H:%M:%S")
        if not self.ok:
            return (
                f"{received}  {self.channel} message received → FAILED ({self.error[:80]}) "
                f"→ fallback delivered ({self.delivery_id or 'undelivered'})"
            )
        retrieval = (
            f"retrieval {self.retrieval_ms:.0f}ms · {self.retrieval_chunks} chunks"
            if self.retrieval_chunks
            else "retrieval skipped"
        )
        return (
            f"{received}  {self.channel} message received → intent {self.intent} "
            f"({self.agent}) → {retrieval} → LLM {self.llm_ms:.0f}ms → "
            f"response {self.reply_chars} chars → delivered {self.delivery_ms:.0f}ms "
            f"(id {self.delivery_id or 'n/a'}) → total {self.total_ms:.0f}ms"
        )


class MessageDispatcher:
    """Routes normalized inbound messages through the platform."""

    def __init__(
        self,
        sessions: SessionManager,
        runtime: ConversationRuntime,
        response_builder: ResponseBuilder,
        router: ChannelRouter,
        restaurant_service: RestaurantService,
    ) -> None:
        self._sessions = sessions
        self._runtime = runtime
        self._response_builder = response_builder
        self._router = router
        self._restaurant_service = restaurant_service

    def dispatch(self, inbound: InboundMessage) -> MessageReport:
        """Process one message end to end; never raises into the transport loop."""
        started = time.monotonic()
        transport = self._router.resolve(inbound.channel)
        session = self._sessions.resolve(inbound.channel, inbound.sender_address)

        # Platform commands are channel-agnostic and never reach the LLM:
        # deterministic, instant, free — and they work identically in
        # WhatsApp, web chat and any future channel.
        command_reply = self._handle_command(inbound, session)
        if command_reply is not None:
            delivery_id, delivery_ms = self._deliver_safe(
                transport,
                OutboundMessage(
                    channel=inbound.channel,
                    recipient_address=inbound.sender_address,
                    text=command_reply,
                    in_reply_to=inbound.message_id,
                ),
            )
            report = MessageReport(
                channel=inbound.channel,
                sender=inbound.sender_address,
                intent="COMMAND",
                agent="Platform",
                restaurant_id=session.restaurant_id,
                reply_chars=len(command_reply),
                delivery_ms=delivery_ms,
                delivery_id=delivery_id,
                total_ms=round((time.monotonic() - started) * 1000, 1),
                ok=bool(delivery_id),
            )
            logger.info("%s", report.timeline())
            return report

        context = ExecutionContext.new(session.restaurant_id or inbound.channel)

        try:
            with execution_scope(context):
                result = self._runtime.process_turn(
                    conversation_id=session.conversation_id,
                    user_text=inbound.text,
                    channel=inbound.channel,
                    restaurant_id=session.restaurant_id,
                )
        except Exception as exc:  # noqa: BLE001 — the customer must get a reply
            logger.exception(
                "Turn failed for %s:%s — sending fallback",
                inbound.channel,
                inbound.sender_address,
            )
            delivery_id, delivery_ms = self._deliver_safe(
                transport, self._response_builder.build_fallback(inbound)
            )
            report = MessageReport(
                channel=inbound.channel,
                sender=inbound.sender_address,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                delivery_id=delivery_id,
                delivery_ms=delivery_ms,
                total_ms=round((time.monotonic() - started) * 1000, 1),
            )
            logger.info("%s", report.timeline())
            return report

        # --- happy path ---------------------------------------------------
        outbound = self._response_builder.build(inbound, result)
        delivery_id, delivery_ms = self._deliver_safe(transport, outbound)
        self._sessions.record_turn(session, active_agent=result.agent_display_name)

        retrieval_ms = result.context.metrics.total_ms if result.context else 0.0
        report = MessageReport(
            channel=inbound.channel,
            sender=inbound.sender_address,
            intent=result.intent,
            agent=result.agent_display_name,
            restaurant_id=session.restaurant_id,
            retrieval_ms=retrieval_ms,
            retrieval_chunks=len(result.context.chunks) if result.context else 0,
            llm_ms=max(result.latency_ms - retrieval_ms, 0.0),
            reply_chars=len(outbound.text),
            delivery_ms=delivery_ms,
            delivery_id=delivery_id,
            total_ms=round((time.monotonic() - started) * 1000, 1),
            ok=bool(delivery_id),
            error="" if delivery_id else "delivery failed — see logs",
        )
        logger.info("%s", report.timeline())
        return report

    # ------------------------------------------------------------------
    def _handle_command(
        self, inbound: InboundMessage, session: CommunicationSession
    ) -> str | None:
        """Execute a platform command; None when the message is not one."""
        text = inbound.text.strip()
        if not text.startswith("/"):
            return None
        parts = text.split()
        command = parts[0].lower()

        if command == "/help":
            return _HELP_TEXT

        if command == "/reset":
            self._sessions.rotate_conversation(session)
            return "🔄 Контекст разговора очищен — начинаем с чистого листа."

        if command == "/restaurant":
            if len(parts) == 1:
                if session.restaurant_id:
                    name = self._restaurant_name(session.restaurant_id)
                    return f"Текущая привязка: {session.restaurant_id} — {name}."
                return (
                    "Ресторан не привязан. Отправьте: /restaurant R-001\n"
                    "Доступные: " + ", ".join(self._restaurant_service.list_restaurants())
                )
            restaurant_id = parts[1].upper()
            try:
                metrics = self._restaurant_service.get_metrics(restaurant_id)
            except RestaurantNotFoundError:
                return (
                    f"Ресторан '{parts[1]}' не найден. Доступные: "
                    + ", ".join(self._restaurant_service.list_restaurants())
                )
            self._sessions.bind_restaurant(session, restaurant_id)
            return (
                f"✅ Контекст привязан: {restaurant_id} — {metrics.name} ({metrics.city}). "
                f"Теперь вопросы о показателях будут отвечаться по этому ресторану."
            )

        return f"Неизвестная команда {command}. Отправьте /help для списка команд."

    def _restaurant_name(self, restaurant_id: str) -> str:
        try:
            return self._restaurant_service.get_metrics(restaurant_id).name
        except RestaurantNotFoundError:
            return "неизвестно"

    @staticmethod
    def _deliver_safe(transport, outbound) -> tuple[str, float]:
        """Send, timing the delivery; a transport fault becomes an empty id."""
        started = time.monotonic()
        try:
            delivery_id = transport.send(outbound)
        except Exception:  # noqa: BLE001 — delivery faults must not kill the loop
            logger.exception("Delivery via '%s' failed", transport.name)
            delivery_id = ""
        return delivery_id, round((time.monotonic() - started) * 1000, 1)
