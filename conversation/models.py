"""Conversation contracts: turns, state and per-turn results."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rag.models import ContextPackage


class ConversationTurn(BaseModel):
    """One utterance in a conversation, by either side."""

    role: Literal["user", "assistant"]
    content: str
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_role: str | None = Field(
        default=None, description="Which platform agent produced an assistant turn."
    )
    interrupted: bool = Field(
        default=False,
        description="True when the user barged in and only part of this reply was delivered.",
    )


class ConversationState(BaseModel):
    """The persistent state of one conversation across any channel."""

    conversation_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    channel: str = Field(default="api")
    restaurant_id: str | None = Field(
        default=None, description="Business context the conversation is about, if known."
    )
    turns: list[ConversationTurn] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def window(self, max_turns: int = 8) -> list[ConversationTurn]:
        """The recent history injected into the model."""
        return self.turns[-max_turns:]


class TurnResult(BaseModel):
    """Everything one processed turn produced — the runtime's deliverable."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    reply: str
    intent: str
    agent_role: str
    agent_display_name: str
    latency_ms: float = Field(ge=0)
    context: ContextPackage | None = Field(
        default=None, description="RAG grounding used for this reply, when applicable."
    )
