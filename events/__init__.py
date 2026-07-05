"""Domain events: the platform's extension backbone.

The pipeline publishes typed events at every stage boundary; anything —
a Slack notifier, an analytics sink, a CRM sync agent — extends the
platform by *subscribing*, never by editing pipeline code.
"""

from events.bus import EventBus, EventHandler, InMemoryEventBus
from events.events import (
    BusinessCaseCreated,
    DomainEvent,
    OfferCreated,
    ReportGenerated,
    ValidationCompleted,
)
from events.handlers import AuditLogHandler, SlackNotificationHandler

__all__ = [
    "AuditLogHandler",
    "BusinessCaseCreated",
    "DomainEvent",
    "EventBus",
    "EventHandler",
    "InMemoryEventBus",
    "OfferCreated",
    "ReportGenerated",
    "SlackNotificationHandler",
    "ValidationCompleted",
]
