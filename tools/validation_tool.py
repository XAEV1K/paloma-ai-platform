"""Validation tool: the deterministic gate before anything ships."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.logging import get_logger
from engines.validator_engine import ValidatorEngine
from services.knowledge_service import KnowledgeService
from services.offer_service import OfferService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.validation")


class ValidationInput(BaseModel):
    offer_id: str = Field(description="Offer id returned by the offer_generator tool.")


@register_tool
class ValidationTool(InstrumentedTool):
    """Runs every validation rule against a persisted offer."""

    name: str = "offer_validation"
    description: str = (
        "Validate a generated offer by id: ROI bounds, payback sanity, module "
        "existence, catalog price consistency and numeric validity. Returns the "
        "machine-generated validation report. You must call this exactly once "
        "and report its verdict truthfully — never override it."
    )
    args_schema: type[BaseModel] = ValidationInput

    offer_service: OfferService
    knowledge_service: KnowledgeService
    validator_engine: ValidatorEngine

    def _execute(self, offer_id: str) -> str:
        logger.info("Validation tool invoked for offer %s", offer_id)
        offer = self.offer_service.get_offer(offer_id)
        report = self.validator_engine.validate(offer, self.knowledge_service.knowledge_base)
        return report.model_dump_json(indent=2)
