"""Session manager: the bridge between a channel address and a conversation.

A session binds ``(channel, address)`` — a WhatsApp number, a web-chat
id — to a ``conversation_id`` in Conversation Memory, plus the business
context: which restaurant this customer is about, which AI service
answered last, when they were last active. Sessions are independent per
address; after ``idle_minutes`` of silence a session continues under a
*fresh* conversation id (stale context must not leak into a new topic —
the old dialogue stays retrievable in Conversation Memory).

Restaurant binding is automatic when possible: Customer Memory (fed by
CRM sync) knows customer phone numbers, so a known caller gets their
venue's business context without typing anything.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from core.exceptions import DataSourceError
from core.logging import get_logger
from services.customer_memory import CustomerMemoryService

logger = get_logger("communication.session")

_DIGITS_RE = re.compile(r"\d+")


class CommunicationSession(BaseModel):
    """One customer's live binding to the platform on one channel."""

    session_id: str = Field(default_factory=lambda: f"cs-{uuid.uuid4().hex[:10]}")
    channel: str
    address: str
    conversation_id: str = Field(default_factory=lambda: f"conv-{uuid.uuid4().hex[:10]}")
    restaurant_id: str | None = None
    active_agent: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    messages: int = 0


class SessionManager:
    """Creates, refreshes and persists communication sessions."""

    def __init__(
        self,
        store_path: Path,
        customer_memory: CustomerMemoryService,
        idle_minutes: int = 240,
    ) -> None:
        self._store_path = store_path
        self._customer_memory = customer_memory
        self._idle = timedelta(minutes=idle_minutes)

    def resolve(self, channel: str, address: str) -> CommunicationSession:
        """Return the live session for an address, rotating stale conversations."""
        sessions = self._read_all()
        key = f"{channel}:{address}"
        session = sessions.get(key)
        now = datetime.now(timezone.utc)

        if session is None:
            session = CommunicationSession(channel=channel, address=address)
            session.restaurant_id = self._restaurant_for(address)
            logger.info(
                "New session %s for %s (restaurant=%s)",
                session.session_id,
                key,
                session.restaurant_id or "unbound",
            )
        elif now - session.last_activity > self._idle:
            # Same customer, new topic: fresh conversation, same identity.
            session.conversation_id = f"conv-{uuid.uuid4().hex[:10]}"
            session.active_agent = None
            logger.info(
                "Session %s idle-rotated to conversation %s",
                session.session_id,
                session.conversation_id,
            )
        if session.restaurant_id is None:
            session.restaurant_id = self._restaurant_for(address)

        sessions[key] = session
        self._write_all(sessions)
        return session

    def bind_restaurant(self, session: CommunicationSession, restaurant_id: str) -> None:
        """Explicitly bind (or rebind) the session's business context."""
        sessions = self._read_all()
        session.restaurant_id = restaurant_id
        sessions[f"{session.channel}:{session.address}"] = session
        self._write_all(sessions)
        logger.info("Session %s bound to restaurant %s", session.session_id, restaurant_id)

    def rotate_conversation(self, session: CommunicationSession) -> None:
        """Start a fresh conversation for the same customer (context reset)."""
        sessions = self._read_all()
        session.conversation_id = f"conv-{uuid.uuid4().hex[:10]}"
        session.active_agent = None
        sessions[f"{session.channel}:{session.address}"] = session
        self._write_all(sessions)
        logger.info(
            "Session %s reset to conversation %s", session.session_id, session.conversation_id
        )

    def record_turn(self, session: CommunicationSession, active_agent: str) -> None:
        """Update activity/agent after a processed message."""
        sessions = self._read_all()
        session.last_activity = datetime.now(timezone.utc)
        session.active_agent = active_agent
        session.messages += 1
        sessions[f"{session.channel}:{session.address}"] = session
        self._write_all(sessions)

    def count(self) -> int:
        return len(self._read_all())

    # ------------------------------------------------------------------
    def _restaurant_for(self, address: str) -> str | None:
        """Bind a channel address to a venue via Customer Memory (CRM-fed)."""
        record = self._customer_memory.find_by_phone(address)
        if record is not None and record.restaurant_id:
            logger.info(
                "Address %s recognised as %s (%s)", address, record.name, record.restaurant_id
            )
            return record.restaurant_id
        return None

    def _read_all(self) -> dict[str, CommunicationSession]:
        if not self._store_path.is_file():
            return {}
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
            return {key: CommunicationSession(**value) for key, value in raw.items()}
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise DataSourceError(f"Corrupt session store {self._store_path}: {exc}") from exc

    def _write_all(self, sessions: dict[str, CommunicationSession]) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: session.model_dump(mode="json") for key, session in sessions.items()}
        self._store_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
