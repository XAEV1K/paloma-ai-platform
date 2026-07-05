"""Module recommendation tool: deterministic expert system, exposed to agents."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from core.logging import get_logger
from engines.recommendation_engine import RecommendationEngine
from services.restaurant_service import RestaurantService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.recommendation")


class RecommendationInput(BaseModel):
    restaurant_id: str = Field(description="Restaurant identifier, e.g. 'R-001'.")


@register_tool
class RecommendationTool(InstrumentedTool):
    """Runs the rule-based engine and returns prioritised module suggestions."""

    name: str = "module_recommendations"
    description: str = (
        "Get rule-based Paloma365 module recommendations for a restaurant. "
        "Each recommendation includes the module code, the problem it addresses, "
        "a priority and a data-backed rationale. Recommendations are computed by "
        "a deterministic rule engine — do not invent modules yourself."
    )
    args_schema: type[BaseModel] = RecommendationInput

    restaurant_service: RestaurantService
    recommendation_engine: RecommendationEngine

    def _execute(self, restaurant_id: str) -> str:
        logger.info("Recommendation tool invoked for %s", restaurant_id)
        metrics = self.restaurant_service.get_metrics(restaurant_id)
        recommendations = self.recommendation_engine.recommend(metrics)
        return json.dumps(
            [rec.model_dump(mode="json") for rec in recommendations],
            indent=2,
        )
