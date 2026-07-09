"""Transport contracts: the only interface a channel must satisfy.

A transport moves bytes; it never reasons. Inbound payloads are
normalized into :class:`InboundMessage` by the channel adapter, replies
arrive as :class:`OutboundMessage` — everything in between belongs to
the dispatcher and the Conversation Runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class InboundMessage(BaseModel):
    """A user message normalized from any channel's wire format."""

    model_config = ConfigDict(frozen=True)

    channel: str = Field(description="Transport name, e.g. 'whatsapp'.")
    sender_address: str = Field(
        description="Channel-native sender id (phone, chat id, email)."
    )
    sender_name: str = ""
    text: str
    message_id: str = Field(description="Channel-native message id (for dedup/tracing).")
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, str] = Field(default_factory=dict)


class OutboundMessage(BaseModel):
    """A reply ready for one specific channel."""

    model_config = ConfigDict(frozen=True)

    channel: str
    recipient_address: str
    text: str
    in_reply_to: str = Field(default="", description="Inbound message id being answered.")


@runtime_checkable
class TransportPort(Protocol):
    """What every channel adapter implements. Transport only — no business."""

    name: str

    def send(self, message: OutboundMessage) -> str:
        """Deliver the message; returns the channel-native delivery id."""
        ...

    def verify(self) -> str:
        """Cheap connectivity probe for the Health Monitor; returns a detail
        string or raises."""
        ...
