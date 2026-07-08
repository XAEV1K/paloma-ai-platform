"""Channel port: the only contract a transport must satisfy."""

from __future__ import annotations

from typing import Protocol

from conversation.models import TurnResult


class ChannelAdapter(Protocol):
    """A transport binding for the Conversation Runtime.

    ``respond`` is the synchronous request/response shape every channel
    can be reduced to; streaming channels additionally pass an
    ``on_token`` sink straight through to the runtime.
    """

    name: str

    def respond(self, conversation_id: str, text: str) -> TurnResult: ...
