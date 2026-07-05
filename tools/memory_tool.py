"""Business memory tool: what have we already tried with this client?

Turns the platform from a one-shot report generator into a copilot that
remembers: previously rejected modules, past diagnoses, prior ROI claims.
Agents consult it before recommending anything.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from core.logging import get_logger
from services.memory_service import BusinessMemoryService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.memory")


class MemoryInput(BaseModel):
    restaurant_id: str = Field(description="Restaurant identifier, e.g. 'R-001'.")


@register_tool
class BusinessMemoryTool(InstrumentedTool):
    """Returns the engagement history: past analyses, offers and outcomes."""

    name: str = "business_memory"
    description: str = (
        "Fetch the engagement history for a restaurant: previous analyses, "
        "previous offers, their outcomes, and modules the client already "
        "rejected. ALWAYS check this before recommending modules — do not "
        "re-pitch a rejected module without new evidence, and acknowledge "
        "prior interactions in your reasoning."
    )
    args_schema: type[BaseModel] = MemoryInput

    memory_service: BusinessMemoryService

    def _execute(self, restaurant_id: str) -> str:
        logger.info("Memory tool invoked for %s", restaurant_id)
        history = self.memory_service.get_history(restaurant_id)
        payload = history.model_dump(mode="json")
        # Pre-computed so the LLM doesn't have to derive it from raw history.
        payload["previously_rejected_modules"] = sorted(
            code.value for code in history.previously_rejected_modules
        )
        return json.dumps(payload, indent=2)
