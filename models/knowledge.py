"""Knowledge-base contracts: the Paloma365 product catalog.

Everything the LLM "knows" about Paloma365 modules comes from these
models, hydrated from ``data/modules.json`` and ``data/prices.json``.
The model does not invent features, limitations or prices — it reads them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.exceptions import UnknownModuleError
from models.enums import Currency, ModuleCode


class ImpactAssumptions(BaseModel):
    """Deterministic uplift assumptions used by the ROI engine.

    These are conservative, catalog-managed numbers — NOT model output.
    """

    model_config = ConfigDict(frozen=True)

    order_growth_pct: float = Field(ge=0, le=100, default=0)
    avg_ticket_growth_pct: float = Field(ge=0, le=100, default=0)
    retention_uplift_pct: float = Field(ge=0, le=100, default=0)


class PalomaModule(BaseModel):
    """Catalog entry for a sellable Paloma365 module."""

    model_config = ConfigDict(frozen=True)

    code: ModuleCode
    name: str
    description: str
    features: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    impact: ImpactAssumptions


class ModulePrice(BaseModel):
    """Catalog price for a module (single source of pricing truth)."""

    model_config = ConfigDict(frozen=True)

    code: ModuleCode
    setup_fee: float = Field(ge=0)
    monthly_fee: float = Field(ge=0)
    currency: Currency = Currency.KZT


class KnowledgeBase(BaseModel):
    """Immutable aggregate of the whole product catalog."""

    model_config = ConfigDict(frozen=True)

    modules: dict[ModuleCode, PalomaModule]
    prices: dict[ModuleCode, ModulePrice]

    def get_module(self, code: ModuleCode) -> PalomaModule:
        try:
            return self.modules[code]
        except KeyError as exc:
            raise UnknownModuleError(str(code)) from exc

    def get_price(self, code: ModuleCode) -> ModulePrice:
        try:
            return self.prices[code]
        except KeyError as exc:
            raise UnknownModuleError(str(code)) from exc
