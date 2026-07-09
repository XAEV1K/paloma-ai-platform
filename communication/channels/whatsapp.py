"""WhatsApp channel adapter over Green API — transport only.

Two responsibilities and nothing more:
1. normalize Green API notifications (polling or webhook payloads — the
   body shape is identical) into :class:`InboundMessage`;
2. deliver :class:`OutboundMessage` via the Green API client.

Business logic, memory, RAG, agents — all live behind the dispatcher.
"""

from __future__ import annotations

import re
from typing import Any

from core.logging import get_logger
from communication.green_api import GreenApiClient
from communication.transport import InboundMessage, OutboundMessage

logger = get_logger("communication.whatsapp")

_NON_DIGITS_RE = re.compile(r"\D")


class WhatsAppTransport:
    """TransportPort implementation for WhatsApp via Green API."""

    name = "whatsapp"

    def __init__(self, client: GreenApiClient) -> None:
        self._client = client

    # --- TransportPort ------------------------------------------------------
    def send(self, message: OutboundMessage) -> str:
        chat_id = self._to_chat_id(message.recipient_address)
        return self._client.send_message(chat_id, message.text)

    def verify(self) -> str:
        state = self._client.get_state_instance()
        if state != "authorized":
            raise RuntimeError(f"instance state '{state}' (expected 'authorized')")
        return "instance authorized · notification queue listening"

    # --- inbound normalization -------------------------------------------------
    def parse_notification(self, body: dict[str, Any]) -> InboundMessage | None:
        """Normalize one Green API notification body.

        Returns ``None`` for anything that is not an inbound text message
        (status updates, outgoing echoes, media we do not handle yet) —
        the dispatcher simply skips those.
        """
        if body.get("typeWebhook") != "incomingMessageReceived":
            return None
        message_data = body.get("messageData") or {}
        text = self._extract_text(message_data)
        if not text:
            logger.debug(
                "Skipping non-text WhatsApp message (%s)",
                message_data.get("typeMessage", "unknown"),
            )
            return None
        sender_data = body.get("senderData") or {}
        chat_id = str(sender_data.get("chatId", ""))
        return InboundMessage(
            channel=self.name,
            sender_address=chat_id,
            sender_name=str(sender_data.get("senderName", "") or ""),
            text=text,
            message_id=str(body.get("idMessage", "")),
            metadata={"instance": str((body.get("instanceData") or {}).get("idInstance", ""))},
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_text(message_data: dict[str, Any]) -> str:
        type_message = message_data.get("typeMessage")
        if type_message == "textMessage":
            return str((message_data.get("textMessageData") or {}).get("textMessage", "")).strip()
        if type_message == "extendedTextMessage":
            return str(
                (message_data.get("extendedTextMessageData") or {}).get("text", "")
            ).strip()
        return ""

    @staticmethod
    def _to_chat_id(address: str) -> str:
        """Accept both raw phone numbers and native chat ids."""
        if address.endswith("@c.us") or address.endswith("@g.us"):
            return address
        return f"{_NON_DIGITS_RE.sub('', address)}@c.us"
