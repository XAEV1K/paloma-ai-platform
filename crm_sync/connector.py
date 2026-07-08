"""CRM connector port + the simulated Bitrix inbox.

The simulation replays realistic webhook payloads from
``data/crm_inbox.json`` — the agreed stand-in for a live CRM (no Docker,
no external infrastructure). A production receiver (FastAPI webhook
endpoint or a polling client) implements the same two methods; the sync
service, normalizer, events and memory never notice the swap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from core.exceptions import DataSourceError
from core.logging import get_logger

logger = get_logger("crm_sync.connector")


class CrmConnectorPort(Protocol):
    """Transport port for CRM change feeds."""

    name: str

    def handshake(self) -> str:
        """Cheap connectivity probe; returns a human-readable status detail."""
        ...

    def fetch_pending(self) -> list[dict]:
        """Raw vendor payloads accumulated since the last sync."""
        ...


class SimulatedBitrixConnector:
    """Replays Bitrix webhook payloads from a local inbox file."""

    name = "bitrix (simulated)"

    def __init__(self, inbox_path: Path) -> None:
        self._inbox_path = inbox_path

    def handshake(self) -> str:
        if not self._inbox_path.is_file():
            return "inbox empty (no pending webhooks)"
        return f"{len(self.fetch_pending())} webhook(s) pending"

    def fetch_pending(self) -> list[dict]:
        if not self._inbox_path.is_file():
            return []
        try:
            payloads = json.loads(self._inbox_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"Cannot read CRM inbox {self._inbox_path}: {exc}") from exc
        if not isinstance(payloads, list):
            raise DataSourceError(f"CRM inbox must be a JSON list: {self._inbox_path}")
        logger.debug("CRM inbox: %d pending payload(s)", len(payloads))
        return payloads
