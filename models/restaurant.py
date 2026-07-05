"""Restaurant analytics contract.

Produced exclusively by ``RestaurantAnalyticsTool`` from real data sources
(CSV today, SQLite/Paloma365 API tomorrow). The LLM only *reads* these
numbers — it never computes them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RestaurantMetrics(BaseModel):
    """A validated monthly snapshot of a single restaurant's performance."""

    model_config = ConfigDict(frozen=True)

    restaurant_id: str = Field(description="Stable identifier, e.g. 'R-001'.")
    name: str
    city: str

    avg_ticket: float = Field(gt=0, description="Average ticket, KZT.")
    orders_per_month: int = Field(ge=0)
    avg_kitchen_time_min: float = Field(ge=0, description="Mean ticket-to-pass time.")
    avg_delivery_time_min: float = Field(ge=0, description="Mean courier delivery time.")

    retention_rate: float = Field(ge=0, le=1, description="Share of returning guests.")
    ltv: float = Field(ge=0, description="Customer lifetime value, KZT.")

    delivery_share: float = Field(ge=0, le=1)
    takeaway_share: float = Field(ge=0, le=1)
    dine_in_share: float = Field(ge=0, le=1)

    kitchen_load: float = Field(ge=0, le=1, description="Peak-hour capacity utilisation.")

    @property
    def monthly_revenue(self) -> float:
        """Deterministic derived metric — never asked of the LLM."""
        return self.avg_ticket * self.orders_per_month

    @model_validator(mode="after")
    def _channel_shares_sum_to_one(self) -> "RestaurantMetrics":
        """Data-quality gate: channel mix must be a proper distribution."""
        total = self.delivery_share + self.takeaway_share + self.dine_in_share
        if abs(total - 1.0) > 0.02:  # tolerate rounding noise in source data
            raise ValueError(
                f"Channel shares must sum to 1.0, got {total:.3f} "
                f"for restaurant '{self.restaurant_id}'"
            )
        return self
