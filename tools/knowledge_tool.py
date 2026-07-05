"""Knowledge tool: the catalog is read, never imagined."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from core.logging import get_logger
from models.enums import ModuleCode
from services.knowledge_service import KnowledgeService
from tools.base import InstrumentedTool, register_tool

logger = get_logger("tools.knowledge")


class KnowledgeInput(BaseModel):
    module_code: ModuleCode | None = Field(
        default=None,
        description="Specific module to look up; omit to list the whole catalog.",
    )


@register_tool
class KnowledgeTool(InstrumentedTool):
    """Serves verified Paloma365 module descriptions, features and prices."""

    name: str = "paloma365_knowledge"
    description: str = (
        "Look up verified facts about Paloma365 modules: description, features, "
        "limitations, impact assumptions and official prices. Use this as the "
        "single source of product truth — never describe a module from memory."
    )
    args_schema: type[BaseModel] = KnowledgeInput

    knowledge_service: KnowledgeService

    def _execute(self, module_code: ModuleCode | None = None) -> str:
        logger.info("Knowledge tool invoked (module=%s)", module_code)
        if module_code is not None:
            module = self.knowledge_service.get_module(module_code)
            price = self.knowledge_service.get_price(module_code)
            return json.dumps(
                {"module": module.model_dump(mode="json"), "price": price.model_dump(mode="json")},
                indent=2,
            )
        catalog = [
            {
                "code": module.code.value,
                "name": module.name,
                "description": module.description,
            }
            for module in self.knowledge_service.list_modules()
        ]
        return json.dumps(catalog, indent=2)
