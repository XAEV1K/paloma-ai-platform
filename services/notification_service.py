"""Notification service: transactional outbox for outbound messages.

Messages are appended to a durable JSONL outbox instead of being sent
inline — the outbox pattern: the pipeline's success never depends on a
third-party messaging API, and a delivery worker (or the event bus's
Slack handler) drains the file asynchronously. Swapping the outbox for a
queue table in PostgreSQL is a repository-level change.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.logging import get_logger

logger = get_logger("services.notification")


class NotificationService:
    """Queues outbound notifications durably (JSONL outbox)."""

    def __init__(self, outbox_path: Path) -> None:
        self._outbox_path = outbox_path

    def queue(self, channel: str, recipient: str, message: str) -> str:
        """Persist one notification; returns its id."""
        notification_id = f"NT-{uuid.uuid4().hex[:8].upper()}"
        record = {
            "notification_id": notification_id,
            "channel": channel,
            "recipient": recipient,
            "message": message,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "status": "QUEUED",
        }
        self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
        with self._outbox_path.open("a", encoding="utf-8") as outbox:
            outbox.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("Notification %s queued for %s via %s", notification_id, recipient, channel)
        return notification_id

    def pending(self) -> list[dict]:
        """All queued notifications (consumed by a delivery worker)."""
        if not self._outbox_path.is_file():
            return []
        records = []
        for line in self._outbox_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records
