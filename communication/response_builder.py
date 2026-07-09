"""Response builder: one reply, formatted per channel.

Channel constraints are presentation, not intelligence: WhatsApp gets a
hard length cap and a compact source line; web chat keeps full sources.
New channels add an entry to the policy table, not new logic upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from conversation.models import TurnResult
from communication.transport import InboundMessage, OutboundMessage


@dataclass(frozen=True, slots=True)
class ChannelPolicy:
    max_chars: int
    include_sources: bool


_POLICIES: dict[str, ChannelPolicy] = {
    "whatsapp": ChannelPolicy(max_chars=3800, include_sources=True),  # WA cap is 4096
    "webchat": ChannelPolicy(max_chars=8000, include_sources=True),
}
_DEFAULT_POLICY = ChannelPolicy(max_chars=4000, include_sources=True)


class ResponseBuilder:
    """Turns a runtime TurnResult into a channel-ready OutboundMessage."""

    def build(self, inbound: InboundMessage, result: TurnResult) -> OutboundMessage:
        policy = _POLICIES.get(inbound.channel, _DEFAULT_POLICY)
        text = result.reply.strip()

        if policy.include_sources and result.context and result.context.sources:
            text += "\n\n📄 " + " · ".join(result.context.sources[:3])

        if len(text) > policy.max_chars:
            cut = text[: policy.max_chars - 1]
            boundary = max(cut.rfind(". "), cut.rfind("\n"))
            text = (cut[: boundary + 1] if boundary > policy.max_chars // 2 else cut) + "…"

        return OutboundMessage(
            channel=inbound.channel,
            recipient_address=inbound.sender_address,
            text=text,
            in_reply_to=inbound.message_id,
        )

    def build_fallback(self, inbound: InboundMessage) -> OutboundMessage:
        """A safe reply when the turn failed — the customer is never ghosted."""
        return OutboundMessage(
            channel=inbound.channel,
            recipient_address=inbound.sender_address,
            text=(
                "Извините, возникла техническая заминка при обработке вашего "
                "сообщения. Мы уже разбираемся — напишите, пожалуйста, ещё раз "
                "через пару минут, либо позвоните на горячую линию поддержки."
            ),
            in_reply_to=inbound.message_id,
        )
