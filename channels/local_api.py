"""Local API channel: the programmatic transport.

The in-process equivalent of a REST endpoint — used by tests, by the
voice pipeline (voice is "just another channel") and by any embedding
application. A future FastAPI surface wraps exactly this adapter.
"""

from __future__ import annotations

from core.logging import get_logger
from conversation.models import TurnResult
from conversation.runtime import ConversationRuntime, TokenCallback

logger = get_logger("channels.api")


class LocalApiChannel:
    """Synchronous programmatic access to the Conversation Runtime."""

    name = "api"

    def __init__(self, runtime: ConversationRuntime, restaurant_id: str | None = None) -> None:
        self._runtime = runtime
        self._restaurant_id = restaurant_id

    def respond(
        self,
        conversation_id: str,
        text: str,
        on_token: TokenCallback | None = None,
    ) -> TurnResult:
        return self._runtime.process_turn(
            conversation_id=conversation_id,
            user_text=text,
            channel=self.name,
            restaurant_id=self._restaurant_id,
            on_token=on_token,
        )
