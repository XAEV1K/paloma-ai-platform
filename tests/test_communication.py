"""Communication Platform: Green API client, adapters, sessions, dispatcher."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import httpx
import pytest

from config.settings import Settings
from conversation.intents import RuleBasedIntentClassifier
from conversation.memory import InMemoryConversationStore
from conversation.router import AgentRouter
from conversation.runtime import ConversationRuntime
from communication.channels.webchat import WebChatTransport
from communication.channels.whatsapp import WhatsAppTransport
from communication.dispatcher import MessageDispatcher
from communication.green_api import GreenApiClient, GreenApiError
from communication.response_builder import ResponseBuilder
from communication.router import ChannelRouter
from communication.session import SessionManager
from communication.transport import InboundMessage
from crew.prompts import PromptRepository
from crm_sync.models import CrmContact
from events.bus import InMemoryEventBus
from llm.routing import AgentRole
from services.customer_memory import CustomerMemoryService
from services.restaurant_service import CsvMetricsRepository, RestaurantService

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

_WEBHOOK_BODY = {
    "typeWebhook": "incomingMessageReceived",
    "idMessage": "MSG-001",
    "instanceData": {"idInstance": 1101},
    "senderData": {"chatId": "77015550101@c.us", "senderName": "Aigerim"},
    "messageData": {
        "typeMessage": "textMessage",
        "textMessageData": {"textMessage": "Почему у меня не печатаются чеки?"},
    },
}


class FakeLLM:
    def __init__(self, reply: str = "Проверьте подключение принтера [S1].") -> None:
        self.reply = reply
        self.calls: list[tuple[AgentRole, list[dict]]] = []
        self.fail = False

    def stream(self, role: AgentRole, messages: list[dict]) -> Iterator[str]:
        if self.fail:
            raise RuntimeError("provider down")
        self.calls.append((role, messages))
        yield self.reply


def _green_settings(**overrides: object) -> Settings:
    params: dict[str, object] = {
        "green_api_instance_id": "1101",
        "green_api_token": "token-secret",
    }
    params.update(overrides)
    return Settings(_env_file=None, **params)  # type: ignore[call-arg]


@pytest.fixture()
def customer_memory(tmp_path: Path) -> CustomerMemoryService:
    memory = CustomerMemoryService(tmp_path / "customers.json")
    memory.upsert_contact(
        CrmContact(
            external_id="501",
            name="Aigerim Bekova",
            phone="+7 701 555 0101",
            restaurant_id="R-001",
        )
    )
    return memory


@pytest.fixture()
def dispatcher_parts(settings: Settings, tmp_path: Path, customer_memory):
    llm = FakeLLM()
    runtime = ConversationRuntime(
        store=InMemoryConversationStore(),
        classifier=RuleBasedIntentClassifier(),
        router=AgentRouter(),
        llm=llm,
        prompts=PromptRepository(settings.prompts_dir, "v1"),
        context_builder=None,
        restaurant_service=RestaurantService(CsvMetricsRepository(settings.restaurants_csv)),
        event_bus=InMemoryEventBus(),
    )
    sessions = SessionManager(
        store_path=tmp_path / "sessions.json",
        customer_memory=customer_memory,
        idle_minutes=240,
    )
    router = ChannelRouter()
    webchat = WebChatTransport(sink=lambda message: None)
    router.register(webchat)
    dispatcher = MessageDispatcher(
        sessions=sessions,
        runtime=runtime,
        response_builder=ResponseBuilder(),
        router=router,
        restaurant_service=RestaurantService(CsvMetricsRepository(settings.restaurants_csv)),
    )
    return dispatcher, webchat, sessions, llm


def _inbound(text: str, channel: str = "webchat", sender: str = "77015550101@c.us"):
    return InboundMessage(
        channel=channel, sender_address=sender, text=text, message_id="MSG-1"
    )


# ---------------------------------------------------------------------------
# Green API client: retry, timeout classes, permanent faults
# ---------------------------------------------------------------------------
def test_green_client_sends_and_parses_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"idMessage": "3EB0"})

    client = GreenApiClient(_green_settings(), transport=httpx.MockTransport(handler))
    message_id = client.send_message("77015550101@c.us", "hello")

    assert message_id == "3EB0"
    url = str(seen[0].url)
    assert "/waInstance1101/sendMessage/token-secret" in url
    assert json.loads(seen[0].content) == {"chatId": "77015550101@c.us", "message": "hello"}


def test_green_client_retries_transient_faults(monkeypatch) -> None:
    monkeypatch.setattr("communication.green_api.time.sleep", lambda _s: None)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(502)
        return httpx.Response(200, json={"idMessage": "OK-AFTER-RETRY"})

    client = GreenApiClient(_green_settings(), transport=httpx.MockTransport(handler))
    assert client.send_message("7@c.us", "x") == "OK-AFTER-RETRY"
    assert attempts["count"] == 3


def test_green_client_fails_fast_on_permanent_4xx(monkeypatch) -> None:
    monkeypatch.setattr("communication.green_api.time.sleep", lambda _s: None)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(401, text="bad token")

    client = GreenApiClient(_green_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(GreenApiError, match="401"):
        client.send_message("7@c.us", "x")
    assert attempts["count"] == 1, "4xx must not be retried"


def test_green_client_empty_queue_returns_none_and_long_polls() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="null")

    client = GreenApiClient(_green_settings(), transport=httpx.MockTransport(handler))
    assert client.receive_notification() is None
    assert seen[0].url.params.get("receiveTimeout") == "20", "server-side long-poll enabled"


def test_ensure_polling_mode_clears_preset_webhook() -> None:
    """Production incident: a preset webhookUrl makes receiveNotification 404."""
    calls: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url), request.content))
        if "getSettings" in str(request.url):
            return httpx.Response(
                200, json={"webhookUrl": "https://old.example/hook", "incomingWebhook": "no"}
            )
        return httpx.Response(200, json={"saveSettings": True})

    client = GreenApiClient(_green_settings(), transport=httpx.MockTransport(handler))
    detail = client.ensure_polling_mode()

    assert "settings updated" in detail
    method, url, content = calls[-1]
    assert method == "POST" and "setSettings" in url
    payload = json.loads(content)
    assert payload["webhookUrl"] == "" and payload["incomingWebhook"] == "yes"


def test_ensure_polling_mode_noop_when_already_correct() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"webhookUrl": "", "incomingWebhook": "yes"})

    client = GreenApiClient(_green_settings(), transport=httpx.MockTransport(handler))
    detail = client.ensure_polling_mode()

    assert "queue active" in detail
    assert all("setSettings" not in url for url in calls), "no write when already correct"


# ---------------------------------------------------------------------------
# WhatsApp adapter: pure transport
# ---------------------------------------------------------------------------
def test_webhook_text_message_is_normalized() -> None:
    adapter = WhatsAppTransport.__new__(WhatsAppTransport)  # parse needs no client
    inbound = adapter.parse_notification(_WEBHOOK_BODY)

    assert inbound is not None
    assert inbound.channel == "whatsapp"
    assert inbound.sender_address == "77015550101@c.us"
    assert "чеки" in inbound.text
    assert inbound.message_id == "MSG-001"


def test_non_text_and_foreign_webhooks_are_skipped() -> None:
    adapter = WhatsAppTransport.__new__(WhatsAppTransport)
    assert adapter.parse_notification({"typeWebhook": "outgoingMessageStatus"}) is None
    media = {
        "typeWebhook": "incomingMessageReceived",
        "idMessage": "M2",
        "senderData": {"chatId": "7@c.us"},
        "messageData": {"typeMessage": "imageMessage"},
    }
    assert adapter.parse_notification(media) is None


def test_phone_number_becomes_chat_id() -> None:
    assert WhatsAppTransport._to_chat_id("+7 701 555-01-01") == "77015550101@c.us"
    assert WhatsAppTransport._to_chat_id("77015550101@c.us") == "77015550101@c.us"


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------
def test_session_binds_known_phone_to_restaurant(dispatcher_parts) -> None:
    _, _, sessions, _ = dispatcher_parts
    session = sessions.resolve("whatsapp", "77015550101@c.us")
    assert session.restaurant_id == "R-001", "CRM-known number auto-binds to its venue"

    stranger = sessions.resolve("whatsapp", "79990000000@c.us")
    assert stranger.restaurant_id is None


def test_sessions_are_independent_and_persistent(dispatcher_parts) -> None:
    _, _, sessions, _ = dispatcher_parts
    first = sessions.resolve("webchat", "user-a")
    second = sessions.resolve("webchat", "user-b")
    assert first.conversation_id != second.conversation_id
    assert sessions.resolve("webchat", "user-a").session_id == first.session_id


def test_idle_session_rotates_conversation(dispatcher_parts) -> None:
    _, _, sessions, _ = dispatcher_parts
    session = sessions.resolve("webchat", "user-idle")
    old_conversation = session.conversation_id
    session.last_activity = datetime.now(timezone.utc) - timedelta(hours=10)
    sessions._write_all({f"webchat:user-idle": session})

    rotated = sessions.resolve("webchat", "user-idle")
    assert rotated.session_id == session.session_id, "same customer identity"
    assert rotated.conversation_id != old_conversation, "fresh conversation context"


# ---------------------------------------------------------------------------
# dispatcher: the full message path
# ---------------------------------------------------------------------------
def test_message_flows_end_to_end_with_timeline(dispatcher_parts) -> None:
    dispatcher, webchat, sessions, llm = dispatcher_parts

    report = dispatcher.dispatch(_inbound("Почему не печатаются чеки? Помогите!"))

    assert report.ok is True
    assert report.intent == "SUPPORT" and report.agent == "Support Agent"
    assert report.restaurant_id == "R-001"
    assert webchat.delivered and "принтера" in webchat.delivered[0].text
    assert report.delivery_id.startswith("wc-")
    line = report.timeline()
    for marker in ("message received", "intent SUPPORT", "LLM", "delivered"):
        assert marker in line

    session = sessions.resolve("webchat", "77015550101@c.us")
    assert session.active_agent == "Support Agent" and session.messages == 1


def test_business_memory_reaches_the_model(dispatcher_parts) -> None:
    """A CRM-known customer asking analytics gets venue data injected."""
    dispatcher, _, _, llm = dispatcher_parts
    dispatcher.dispatch(_inbound("Какой средний чек моего ресторана?"))

    _, messages = llm.calls[-1]
    joined = " ".join(m["content"] for m in messages)
    assert "Dastarkhan Lounge" in joined, "restaurant metrics injected via session binding"


def test_failed_turn_sends_fallback_never_ghosts(dispatcher_parts) -> None:
    dispatcher, webchat, _, llm = dispatcher_parts
    llm.fail = True

    report = dispatcher.dispatch(_inbound("help me"))

    assert report.ok is False and "provider down" in report.error
    assert webchat.delivered, "customer still received a reply"
    assert "заминка" in webchat.delivered[-1].text
    assert "FAILED" in report.timeline()


def test_unknown_channel_is_a_config_error(dispatcher_parts) -> None:
    dispatcher, _, _, _ = dispatcher_parts
    from core.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError, match="No transport"):
        dispatcher.dispatch(_inbound("hi", channel="telegram"))


# ---------------------------------------------------------------------------
# platform commands (channel-agnostic, never reach the LLM)
# ---------------------------------------------------------------------------
def test_restaurant_command_binds_session(dispatcher_parts) -> None:
    """Production log: '/restaurant r-001' went to the LLM as plain text."""
    dispatcher, webchat, sessions, llm = dispatcher_parts

    report = dispatcher.dispatch(_inbound("/restaurant r-001", sender="79990000000@c.us"))

    assert report.intent == "COMMAND" and report.agent == "Platform"
    assert not llm.calls, "commands must never reach the LLM"
    assert "Dastarkhan Lounge" in webchat.delivered[-1].text
    session = sessions.resolve("webchat", "79990000000@c.us")
    assert session.restaurant_id == "R-001", "lowercase id normalised and bound"

    # The very next analytics question now gets business data.
    dispatcher.dispatch(_inbound("какой средний чек моего ресторана?", sender="79990000000@c.us"))
    _, messages = llm.calls[-1]
    assert any("Dastarkhan Lounge" in m["content"] for m in messages)


def test_unknown_restaurant_command_lists_options(dispatcher_parts) -> None:
    dispatcher, webchat, _, llm = dispatcher_parts
    dispatcher.dispatch(_inbound("/restaurant R-999"))
    assert "не найден" in webchat.delivered[-1].text
    assert "R-001" in webchat.delivered[-1].text
    assert not llm.calls


def test_reset_command_rotates_conversation(dispatcher_parts) -> None:
    dispatcher, _, sessions, _ = dispatcher_parts
    session_before = sessions.resolve("webchat", "77015550101@c.us")
    old_conversation = session_before.conversation_id

    dispatcher.dispatch(_inbound("/reset"))

    session_after = sessions.resolve("webchat", "77015550101@c.us")
    assert session_after.conversation_id != old_conversation


def test_help_command(dispatcher_parts) -> None:
    dispatcher, webchat, _, _ = dispatcher_parts
    dispatcher.dispatch(_inbound("/help"))
    assert "/restaurant" in webchat.delivered[-1].text


def test_green_client_treats_404_queue_as_empty() -> None:
    """Production log: this instance answers an empty queue with HTTP 404."""
    client = GreenApiClient(
        _green_settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
    )
    assert client.receive_notification() is None  # not an error, not a retry storm


# ---------------------------------------------------------------------------
# response builder
# ---------------------------------------------------------------------------
def test_sources_only_when_reply_cites_them(dispatcher_parts) -> None:
    """Production log: small-talk got a noisy document footer."""
    from conversation.models import TurnResult
    from rag.models import ContextPackage, RetrievalMetrics

    builder = ResponseBuilder()
    metrics = RetrievalMetrics(
        embedding_ms=1, search_ms=1, rerank_ms=0, candidates=5, returned=2
    )
    context = ContextPackage(
        query="q", chunks=[], text="ctx", sources=["faq.md"], char_count=3, metrics=metrics
    )

    def result_with(reply: str) -> TurnResult:
        return TurnResult(
            conversation_id="c", reply=reply, intent="SUPPORT", agent_role="support",
            agent_display_name="Support Agent", latency_ms=1.0, context=context,
        )

    ungrounded = builder.build(_inbound("тест1"), result_with("Не понял вопрос, уточните."))
    assert "📄" not in ungrounded.text

    grounded = builder.build(_inbound("q"), result_with("Проверьте токен [S1]."))
    assert "📄" in grounded.text and "faq.md" in grounded.text
def test_response_builder_caps_whatsapp_length() -> None:
    from conversation.models import TurnResult

    builder = ResponseBuilder()
    long_reply = ("Очень длинное предложение о модулях. " * 300).strip()
    result = TurnResult(
        conversation_id="c", reply=long_reply, intent="SUPPORT",
        agent_role="support", agent_display_name="Support Agent", latency_ms=1.0,
    )
    outbound = builder.build(_inbound("q", channel="whatsapp"), result)
    assert len(outbound.text) <= 3800
    assert outbound.channel == "whatsapp"
