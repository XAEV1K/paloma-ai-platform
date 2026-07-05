"""Offer generator tool.

The Developer agent contributes exactly two things: the module selection
(verified through the recommendation tool) and the executive-summary
narrative. Pricing, ROI and assembly happen in ``OfferService``; only a
compact :class:`OfferRef` returns into the LLM context.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.logging import get_logger
from models.enums import ModuleCode, ProblemCategory
from models.offer import ModuleRecommendation
from services.offer_service import OfferService
from services.restaurant_service import RestaurantService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.offer")


class OfferModuleInput(BaseModel):
    """One selected module with the reasoning the agent attaches to it."""

    module_code: ModuleCode
    addresses: ProblemCategory = Field(description="The diagnosed problem this module solves.")
    priority: int = Field(ge=1, description="1 = highest priority.")
    rationale: str = Field(max_length=300, description="Data-backed one-sentence justification.")


class OfferInput(BaseModel):
    restaurant_id: str = Field(description="Restaurant identifier, e.g. 'R-001'.")
    modules: list[OfferModuleInput] = Field(min_length=1)
    executive_summary: str = Field(
        max_length=1500,
        description="Client-facing narrative. Quote only numbers returned by tools.",
    )


@register_tool
class OfferGeneratorTool(InstrumentedTool):
    """Assembles, prices and persists the commercial offer."""

    name: str = "offer_generator"
    description: str = (
        "Create the final commercial offer for a restaurant from the selected "
        "Paloma365 modules and your executive summary. Prices and ROI are filled "
        "in automatically from the catalog. Returns a compact offer reference "
        "(offer_id) — pass that id onward instead of re-typing offer contents."
    )
    args_schema: type[BaseModel] = OfferInput

    restaurant_service: RestaurantService
    offer_service: OfferService

    def _execute(
        self,
        restaurant_id: str,
        modules: list[OfferModuleInput],
        executive_summary: str,
    ) -> str:
        logger.info(
            "Offer generator invoked for %s with %d module(s)", restaurant_id, len(modules)
        )
        metrics = self.restaurant_service.get_metrics(restaurant_id)
        recommendations = [
            ModuleRecommendation(
                module_code=m.module_code,
                addresses=m.addresses,
                priority=m.priority,
                rationale=m.rationale,
            )
            for m in modules
        ]
        offer_ref = self.offer_service.build_offer(metrics, recommendations, executive_summary)
        return offer_ref.model_dump_json(indent=2)
