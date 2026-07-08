"""Normalized CRM contracts — the internal shape all CRMs map into."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CrmContact(BaseModel):
    """A customer contact, normalized from any CRM vendor."""

    model_config = ConfigDict(frozen=True)

    external_id: str
    name: str
    phone: str = ""
    email: str = ""
    restaurant_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class CrmDeal(BaseModel):
    """A sales deal, normalized from any CRM vendor."""

    model_config = ConfigDict(frozen=True)

    external_id: str
    title: str
    stage: str
    amount: float = Field(ge=0, default=0.0)
    contact_external_id: str | None = None
    restaurant_id: str | None = None


class NormalizedCrmEvent(BaseModel):
    """One CRM change, ready for the event bus and memory."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["contact", "deal"]
    action: Literal["created", "updated"]
    contact: CrmContact | None = None
    deal: CrmDeal | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
