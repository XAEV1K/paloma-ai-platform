"""CRM tool: guest-relationship signals for the Architect's diagnosis."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.logging import get_logger
from services.crm_service import CrmService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.crm")


class CrmInput(BaseModel):
    restaurant_id: str = Field(description="Restaurant identifier, e.g. 'R-001'.")


@register_tool
class CrmTool(InstrumentedTool):
    """Returns NPS, complaints and loyalty signals for a restaurant."""

    name: str = "crm_insights"
    description: str = (
        "Fetch CRM signals for a restaurant: NPS, complaint volume and topics, "
        "repeat-guest share and loyalty program status. Use it to support the "
        "diagnosis with guest-relationship evidence."
    )
    args_schema: type[BaseModel] = CrmInput

    crm_service: CrmService

    def _execute(self, restaurant_id: str) -> str:
        logger.info("CRM tool invoked for %s", restaurant_id)
        return self.crm_service.get_snapshot(restaurant_id).model_dump_json(indent=2)
