"""Product knowledge service: the only source of Paloma365 facts.

Hydrates the immutable :class:`KnowledgeBase` from versioned JSON files.
Agents query it through ``KnowledgeTool`` — the LLM reads the catalog,
it never invents features or prices.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from core.exceptions import DataSourceError
from core.logging import get_logger
from models.enums import ModuleCode
from models.knowledge import KnowledgeBase, ModulePrice, PalomaModule

logger = get_logger("services.knowledge")


class KnowledgeService:
    """Loads and serves the Paloma365 module catalog and price list.

    The catalog is loaded **eagerly** at construction time: it is small,
    it must be valid for the platform to run at all (fail fast), and
    CrewAI executes tool calls in parallel threads — lazy initialisation
    here caused a triple concurrent load in production logs.
    """

    def __init__(self, modules_path: Path, prices_path: Path) -> None:
        self._modules_path = modules_path
        self._prices_path = prices_path
        self._knowledge: KnowledgeBase = self._load()

    @property
    def knowledge_base(self) -> KnowledgeBase:
        """The validated, immutable catalog aggregate."""
        return self._knowledge

    def get_module(self, code: ModuleCode) -> PalomaModule:
        return self.knowledge_base.get_module(code)

    def get_price(self, code: ModuleCode) -> ModulePrice:
        return self.knowledge_base.get_price(code)

    def list_modules(self) -> list[PalomaModule]:
        return list(self.knowledge_base.modules.values())

    def _load(self) -> KnowledgeBase:
        logger.info(
            "Loading knowledge base (%s, %s)", self._modules_path.name, self._prices_path.name
        )
        try:
            modules_raw = json.loads(self._modules_path.read_text(encoding="utf-8"))
            prices_raw = json.loads(self._prices_path.read_text(encoding="utf-8"))
            modules = [PalomaModule(**entry) for entry in modules_raw["modules"]]
            prices = [ModulePrice(**entry) for entry in prices_raw["prices"]]
        except (OSError, json.JSONDecodeError, KeyError, ValidationError) as exc:
            raise DataSourceError(f"Cannot load knowledge base: {exc}") from exc

        knowledge = KnowledgeBase(
            modules={m.code: m for m in modules},
            prices={p.code: p for p in prices},
        )
        logger.info("Knowledge base ready: %d module(s)", len(knowledge.modules))
        return knowledge
