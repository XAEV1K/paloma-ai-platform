"""Event bus: typed routing, wildcard subscription, handler isolation."""

from __future__ import annotations

from events.bus import InMemoryEventBus
from events.events import BusinessCaseCreated, DomainEvent, OfferCreated
from models.enums import ModuleCode


def _case_event() -> BusinessCaseCreated:
    return BusinessCaseCreated(
        request_id="req-1", restaurant_id="R-001", headline="h", problem_count=2
    )


def _offer_event() -> OfferCreated:
    return OfferCreated(
        request_id="req-1",
        restaurant_id="R-001",
        offer_id="OF-1",
        module_codes=[ModuleCode.DELIVERY],
        roi_pct=100.0,
    )


def test_exact_type_routing() -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []
    bus.subscribe(BusinessCaseCreated, received.append)

    bus.publish(_case_event())
    bus.publish(_offer_event())  # different type -> not delivered

    assert len(received) == 1
    assert isinstance(received[0], BusinessCaseCreated)


def test_wildcard_subscription_sees_everything() -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []
    bus.subscribe(DomainEvent, received.append)

    bus.publish(_case_event())
    bus.publish(_offer_event())

    assert len(received) == 2


def test_failing_handler_is_isolated() -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []

    def broken(_: DomainEvent) -> None:
        raise RuntimeError("subscriber bug")

    bus.subscribe(BusinessCaseCreated, broken)
    bus.subscribe(BusinessCaseCreated, received.append)

    bus.publish(_case_event())  # must not raise

    assert len(received) == 1, "healthy subscriber still gets the event"
