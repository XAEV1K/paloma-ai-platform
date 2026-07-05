"""Restaurant analytics tool: real numbers in, zero hallucinations out."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.logging import get_logger
from services.restaurant_service import RestaurantService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.analytics")


class AnalyticsInput(BaseModel):
    """LLM-facing argument schema."""

    restaurant_id: str = Field(description="Restaurant identifier, e.g. 'R-001'.")


@register_tool
class RestaurantAnalyticsTool(InstrumentedTool):
    """Returns the validated performance snapshot of one restaurant."""

    name: str = "restaurant_analytics"
    description: str = (
        "Fetch real performance metrics for a restaurant by id: average ticket, "
        "orders per month, kitchen/delivery times, retention, LTV, channel mix "
        "and kitchen load. Always use this instead of guessing numbers."
    )
    args_schema: type[BaseModel] = AnalyticsInput

    restaurant_service: RestaurantService

    def _execute(self, restaurant_id: str) -> str:
        logger.info("Analytics tool invoked for %s", restaurant_id)
        metrics = self.restaurant_service.get_metrics(restaurant_id)
        return metrics.model_dump_json(indent=2)
