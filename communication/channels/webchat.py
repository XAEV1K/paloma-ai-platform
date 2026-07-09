"""Web-chat channel adapter: the in-process transport.

The second live transport — proof that the core is channel-agnostic and
the delivery seam for an embedded website widget (a future WebSocket
handler calls exactly these two methods). Outbound messages are handed
to a sink callback (the CLI prints them; tests capture them) and receive
a delivery id like any external channel.
"""

from __future__ import annotations

import uuid
from typing import Callable

from core.logging import get_logger
from communication.transport import OutboundMessage

logger = get_logger("communication.webchat")

#: Delivery sink: receives the outbound message (print, websocket push, test capture).
DeliverySink = Callable[[OutboundMessage], None]


class WebChatTransport:
    """TransportPort implementation for the embedded web chat."""

    name = "webchat"

    def __init__(self, sink: DeliverySink | None = None) -> None:
        self._sink = sink or (lambda message: print(f"[webchat → {message.recipient_address}] {message.text}"))
        self.delivered: list[OutboundMessage] = []

    def send(self, message: OutboundMessage) -> str:
        self._sink(message)
        self.delivered.append(message)
        delivery_id = f"wc-{uuid.uuid4().hex[:10]}"
        logger.debug("WebChat delivery %s to %s", delivery_id, message.recipient_address)
        return delivery_id

    def verify(self) -> str:
        return "in-process transport online"
