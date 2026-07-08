"""Conversation memory tool: dialogue history for pipeline agents."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from core.logging import get_logger
from conversation.memory import ConversationStorePort
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.conversation")


class ConversationHistoryInput(BaseModel):
    conversation_id: str = Field(description="Conversation identifier, e.g. 'chat-1a2b3c4d'.")
    max_turns: int = Field(default=10, ge=1, le=50)


@register_tool
class ConversationHistoryTool(InstrumentedTool):
    """Returns the recent turns of a stored conversation."""

    name: str = "conversation_history"
    description: str = (
        "Fetch the recent history of a customer conversation by id: who said "
        "what, which agent answered, and whether replies were interrupted. "
        "Use it to understand prior interactions before making recommendations."
    )
    args_schema: type[BaseModel] = ConversationHistoryInput

    conversation_store: ConversationStorePort

    def _execute(self, conversation_id: str, max_turns: int = 10) -> str:
        logger.info("Conversation history requested: %s", conversation_id)
        state = self.conversation_store.load(conversation_id)
        if state is None:
            return json.dumps({"conversation_id": conversation_id, "turns": []})
        turns = [
            {
                "role": turn.role,
                "content": turn.content,
                "agent_role": turn.agent_role,
                "interrupted": turn.interrupted,
            }
            for turn in state.window(max_turns)
        ]
        return json.dumps(
            {"conversation_id": conversation_id, "channel": state.channel, "turns": turns},
            ensure_ascii=False,
            indent=2,
        )
