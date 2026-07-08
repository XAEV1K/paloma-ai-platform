"""Interactive chat channel for the terminal (the "web chat" demo stand-in).

Streams tokens as they arrive, then prints a per-turn observability line
(agent, intent, latency, grounding). Commands: ``/restaurant <id>`` binds
a business context, ``/exit`` quits.
"""

from __future__ import annotations

import sys
import uuid

from core.logging import get_logger
from conversation.models import TurnResult
from conversation.runtime import ConversationRuntime

logger = get_logger("channels.chat")

_BANNER = """\
──────────────────────────────────────────────────────────────
  Paloma365 AI Operations Platform · chat channel
  Commands: /restaurant <id>  bind business context
            /exit             leave the chat
──────────────────────────────────────────────────────────────"""


class ChatCliChannel:
    """REPL chat over the Conversation Runtime."""

    name = "chat"

    def __init__(self, runtime: ConversationRuntime) -> None:
        self._runtime = runtime
        self._restaurant_id: str | None = None

    def respond(self, conversation_id: str, text: str) -> TurnResult:
        return self._runtime.process_turn(
            conversation_id=conversation_id,
            user_text=text,
            channel=self.name,
            restaurant_id=self._restaurant_id,
            on_token=lambda token: print(token, end="", flush=True),
        )

    def run(self) -> int:
        """Blocking chat loop; returns a process exit code."""
        conversation_id = f"chat-{uuid.uuid4().hex[:8]}"
        print(_BANNER)
        print(f"  conversation: {conversation_id}\n")
        while True:
            try:
                user_text = input("you > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye.")
                return 0
            if not user_text:
                continue
            if user_text.lower() in ("/exit", "/quit"):
                print("bye.")
                return 0
            if user_text.lower().startswith("/restaurant"):
                parts = user_text.split()
                self._restaurant_id = parts[1] if len(parts) > 1 else None
                print(f"business context: {self._restaurant_id or 'cleared'}\n")
                continue

            print("ai  > ", end="", flush=True)
            try:
                result = self.respond(conversation_id, user_text)
            except Exception as exc:  # noqa: BLE001 — a turn failure must not kill the session
                logger.error("Turn failed: %s: %s", type(exc).__name__, exc)
                print("\n(sorry — that turn failed; see the log. The session continues.)\n")
                continue
            print()  # newline after the streamed reply
            grounding = (
                f"{len(result.context.chunks)} chunk(s) from "
                f"{', '.join(result.context.sources)} "
                f"({result.context.metrics.total_ms:.0f}ms retrieval)"
                if result.context
                else "no retrieval"
            )
            print(
                f"      · {result.agent_display_name} · intent {result.intent} · "
                f"{result.latency_ms / 1000:.1f}s · {grounding}\n"
            )
            sys.stdout.flush()
