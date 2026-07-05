"""ROI calculator tool: all financial math happens in Python."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.logging import get_logger
from engines.roi_engine import ROIEngine
from models.enums import ModuleCode
from services.knowledge_service import KnowledgeService
from services.restaurant_service import RestaurantService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.roi")


class RoiInput(BaseModel):
    restaurant_id: str = Field(description="Restaurant identifier, e.g. 'R-001'.")
    module_codes: list[ModuleCode] = Field(
        min_length=1,
        description="Paloma365 module codes to evaluate as one bundle, e.g. ['DELIVERY'].",
    )


@register_tool
class RoiCalculatorTool(InstrumentedTool):
    """Computes ROI / payback / revenue projections for a module bundle."""

    name: str = "roi_calculator"
    description: str = (
        "Compute the deterministic financial projection (ROI %, payback months, "
        "monthly gain, revenue growth %) for installing a bundle of Paloma365 "
        "modules at a restaurant. NEVER estimate ROI yourself — always call this."
    )
    args_schema: type[BaseModel] = RoiInput

    restaurant_service: RestaurantService
    knowledge_service: KnowledgeService
    roi_engine: ROIEngine

    def _execute(self, restaurant_id: str, module_codes: list[ModuleCode]) -> str:
        logger.info("ROI tool invoked for %s, bundle=%s", restaurant_id, module_codes)
        metrics = self.restaurant_service.get_metrics(restaurant_id)
        modules = [self.knowledge_service.get_module(code) for code in module_codes]
        prices = [self.knowledge_service.get_price(code) for code in module_codes]
        projection = self.roi_engine.calculate(metrics, modules, prices)
        return projection.model_dump_json(indent=2)
