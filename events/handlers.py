"""Built-in event subscribers.

These are the reference implementations of the extension pattern: a new
integration (Slack agent, analytics sink, e-mail follow-up, CRM sync) is
one handler class + one ``subscribe`` line in the composition root.
"""

from __future__ import annotations

from core.logging import get_logger
from events.events import DomainEvent, ValidationCompleted

logger = get_logger("events.handlers")


class AuditLogHandler:
    """Wildcard subscriber: writes every domain event to the audit log.

    Subscribed to ``DomainEvent`` — it sees everything, which is exactly
    what an audit trail (and tomorrow, an analytics pipeline) needs.
    """

    __name__ = "AuditLogHandler"

    def __call__(self, event: DomainEvent) -> None:
        payload = event.model_dump_json(exclude={"event_id", "occurred_at"})
        logger.info("AUDIT %s %s", type(event).__name__, payload)


class SlackNotificationHandler:
    """Extension point: notify a sales channel when validation completes.

    Not subscribed by default. TODO: implement via Slack webhook (httpx),
    with the webhook URL coming from ``Settings``.
    """

    __name__ = "SlackNotificationHandler"

    def __call__(self, event: DomainEvent) -> None:
        if not isinstance(event, ValidationCompleted):
            return
        raise NotImplementedError("Slack integration is a roadmap item")
