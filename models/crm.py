"""CRM contracts (mocked today, Paloma365 CRM API tomorrow)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CrmSnapshot(BaseModel):
    """Customer-relationship signals for a restaurant's guest base."""

    model_config = ConfigDict(frozen=True)

    restaurant_id: str
    nps: float = Field(ge=-100, le=100, description="Net Promoter Score.")
    complaints_last_month: int = Field(ge=0)
    top_complaint_topics: list[str] = Field(default_factory=list)
    repeat_guest_share: float = Field(ge=0, le=1)
    loyalty_program_active: bool
