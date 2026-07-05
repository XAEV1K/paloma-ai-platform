"""Event bus: synchronous in-process pub/sub with handler isolation.

The :class:`EventBus` protocol is the seam for a real broker later
(Kafka, RabbitMQ, Redis Streams) — publishers and subscribers only see
``publish``/``subscribe``, so the transport is swappable in the
composition root like every other backend.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Protocol, TypeVar

from core.logging import get_logger
from events.events import DomainEvent

logger = get_logger("events.bus")

E = TypeVar("E", bound=DomainEvent)

#: A handler is any callable taking one event. Handlers must be idempotent.
EventHandler = Callable[[DomainEvent], None]


class EventBus(Protocol):
    """Transport-agnostic pub/sub port."""

    def publish(self, event: DomainEvent) -> None: ...

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None: ...


class InMemoryEventBus:
    """Synchronous, in-process bus.

    Guarantees:
    - Handlers are isolated: one failing subscriber never breaks the
      pipeline or the other subscribers — the error is logged and swallowed.
    - Subscribing to ``DomainEvent`` receives *every* event (wildcard).
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)
        logger.debug(
            "Subscribed %s to %s", getattr(handler, "__name__", handler), event_type.__name__
        )

    def publish(self, event: DomainEvent) -> None:
        exact = self._handlers.get(type(event), [])
        wildcard = self._handlers.get(DomainEvent, []) if type(event) is not DomainEvent else []
        logger.debug(
            "Publishing %s to %d handler(s)", type(event).__name__, len(exact) + len(wildcard)
        )
        for handler in (*exact, *wildcard):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 — isolation is the contract here
                logger.exception(
                    "Event handler %s failed on %s (event dropped for this handler)",
                    getattr(handler, "__name__", handler),
                    type(event).__name__,
                )
