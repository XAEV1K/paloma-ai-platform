"""Example Plugin SDK capability: loyalty engagement insights.

A complete third-party-style plugin: it lives outside the platform
packages, declares its dependency (`memory_service`) as a field, and the
composition root injects it. Dropped into ``plugins/`` — discovered,
instrumented and capability-mapped automatically.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from core.logging import get_logger
from models.enums import ModuleCode, OfferOutcome
from services.memory_service import BusinessMemoryService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("plugins.loyalty_insights")


class LoyaltyInsightsInput(BaseModel):
    restaurant_id: str = Field(description="Restaurant identifier, e.g. 'R-001'.")


@register_tool
class LoyaltyInsightsTool(InstrumentedTool):
    """Summarises a venue's loyalty-module engagement from business memory."""

    name: str = "loyalty_insights"
    description: str = (
        "Analyse a restaurant's engagement history with the CRM & Loyalty "
        "module: past loyalty offers, their outcomes, rejection reasons and "
        "whether a re-pitch is currently advisable."
    )
    args_schema: type[BaseModel] = LoyaltyInsightsInput

    memory_service: BusinessMemoryService

    def _execute(self, restaurant_id: str) -> str:
        history = self.memory_service.get_history(restaurant_id)
        loyalty_offers = [
            offer for offer in history.offers if ModuleCode.CRM_LOYALTY in offer.module_codes
        ]
        rejected = [
            offer for offer in loyalty_offers
            if offer.outcome is OfferOutcome.REJECTED
            or ModuleCode.CRM_LOYALTY in offer.rejected_modules
        ]
        repitch_advisable = not rejected or len(loyalty_offers) > len(rejected)
        payload = {
            "restaurant_id": restaurant_id,
            "loyalty_offers_total": len(loyalty_offers),
            "loyalty_rejections": len(rejected),
            "last_rejection_comment": rejected[-1].outcome_comment if rejected else "",
            "repitch_advisable": repitch_advisable,
            "note": (
                "Client has previously declined loyalty — a re-pitch needs new evidence."
                if rejected
                else "No loyalty rejections on record."
            ),
        }
        logger.info(
            "Loyalty insights for %s: %d offer(s), %d rejection(s)",
            restaurant_id,
            len(loyalty_offers),
            len(rejected),
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)
