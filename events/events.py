"""Typed domain events published by the pipeline.

Events carry compact, serialisable payloads (ids + key figures), not
whole aggregates — subscribers that need the full object fetch it from
the owning service by id. This keeps events cheap to fan out and safe to
ship over a broker later (Kafka/RabbitMQ) without schema surgery.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from models.enums import ModuleCode, ValidationStatus


class DomainEvent(BaseModel):
    """Base class for every event on the bus."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    request_id: str = Field(description="ExecutionContext.request_id of the producing run.")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BusinessCaseCreated(DomainEvent):
    """The Architect finished its diagnosis."""

    restaurant_id: str
    headline: str
    problem_count: int


class OfferCreated(DomainEvent):
    """The Developer produced a persisted commercial offer."""

    restaurant_id: str
    offer_id: str
    module_codes: list[ModuleCode]
    roi_pct: float


class ValidationCompleted(DomainEvent):
    """The deterministic validation verdict is in."""

    offer_id: str
    status: ValidationStatus
    issue_count: int


class ReportGenerated(DomainEvent):
    """The final business report has been rendered to disk."""

    restaurant_id: str
    offer_id: str
    report_path: str
