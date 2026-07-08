"""Conversation memory: persistence port + JSON adapter.

Part of the platform's global memory family: business memory remembers
*outcomes* (offers, rejections), conversation memory remembers
*dialogue*. Both live behind repository ports, so the JSON files become
PostgreSQL tables without touching the runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from core.exceptions import DataSourceError
from core.logging import get_logger
from conversation.models import ConversationState

logger = get_logger("conversation.memory")


@runtime_checkable  # used as a Pydantic field type in the tool layer
class ConversationStorePort(Protocol):
    """Persistence port for conversation state."""

    def load(self, conversation_id: str) -> ConversationState | None: ...

    def save(self, state: ConversationState) -> None: ...


class JsonConversationStore:
    """File-backed store: ``{conversation_id: ConversationState}``."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self, conversation_id: str) -> ConversationState | None:
        raw = self._read_all().get(conversation_id)
        if raw is None:
            return None
        try:
            return ConversationState(**raw)
        except ValidationError as exc:
            raise DataSourceError(
                f"Corrupt conversation record '{conversation_id}': {exc}"
            ) from exc

    def save(self, state: ConversationState) -> None:
        data = self._read_all()
        data[state.conversation_id] = state.model_dump(mode="json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug(
            "Conversation %s persisted (%d turn(s))",
            state.conversation_id,
            len(state.turns),
        )

    def _read_all(self) -> dict[str, dict]:
        if not self._path.is_file():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"Cannot read conversation store {self._path}: {exc}") from exc


class InMemoryConversationStore:
    """Ephemeral store for tests and short-lived sessions."""

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}

    def load(self, conversation_id: str) -> ConversationState | None:
        return self._states.get(conversation_id)

    def save(self, state: ConversationState) -> None:
        self._states[state.conversation_id] = state
