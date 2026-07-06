"""Restaurant analytics tool: real numbers in, zero hallucinations out.

Returns the metrics snapshot **plus the platform's own benchmarks** —
the same thresholds the rule engine uses. The Architect must quote these
benchmark values as evidence; without them it invents plausible-looking
targets (audit finding: 0.30/0.20 instead of the real 0.25/0.15).
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from core.logging import get_logger
from engines.recommendation_engine import RecommendationThresholds
from services.restaurant_service import RestaurantService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.analytics")


class AnalyticsInput(BaseModel):
    """LLM-facing argument schema."""

    restaurant_id: str = Field(description="Restaurant identifier, e.g. 'R-001'.")


@register_tool
class RestaurantAnalyticsTool(InstrumentedTool):
    """Returns the validated performance snapshot + official benchmarks."""

    name: str = "restaurant_analytics"
    description: str = (
        "Fetch real performance metrics for a restaurant by id: average ticket, "
        "orders per month, kitchen/delivery times, retention, LTV, channel mix "
        "and kitchen load. The response includes a 'benchmarks' block with the "
        "platform's official target values — use exactly these as benchmarks in "
        "your diagnosis, never invent your own."
    )
    args_schema: type[BaseModel] = AnalyticsInput

    restaurant_service: RestaurantService
    thresholds: RecommendationThresholds

    def _execute(self, restaurant_id: str) -> str:
        logger.info("Analytics tool invoked for %s", restaurant_id)
        metrics = self.restaurant_service.get_metrics(restaurant_id)
        payload = metrics.model_dump(mode="json")
        payload["benchmarks"] = {
            "delivery_share_min": self.thresholds.min_delivery_share,
            "retention_rate_min": self.thresholds.min_retention_rate,
            "avg_kitchen_time_max_min": self.thresholds.max_kitchen_time_min,
            "kitchen_load_max": self.thresholds.max_kitchen_load,
            "avg_ticket_min": self.thresholds.min_avg_ticket,
        }
        return json.dumps(payload, indent=2)
