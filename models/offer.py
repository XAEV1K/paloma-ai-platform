"""Developer-stage contracts: recommendations, ROI and the commercial offer.

The full :class:`Offer` is produced and persisted by Python
(``OfferService``); agents pass around the lightweight :class:`OfferRef`
so large payloads never travel through the LLM context window.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from models.enums import Currency, ModuleCode, ProblemCategory


class ModuleRecommendation(BaseModel):
    """One rule-engine recommendation: which module and why."""

    model_config = ConfigDict(frozen=True)

    module_code: ModuleCode
    addresses: ProblemCategory
    priority: int = Field(ge=1, description="1 = highest priority.")
    rationale: str = Field(max_length=300, description="Deterministic rule explanation.")


class RoiProjection(BaseModel):
    """Deterministic financial projection computed by ``ROIEngine``.

    Every number here is Python-computed. The LLM may quote these values
    verbatim but can never alter them (the Validator re-derives them).
    """

    model_config = ConfigDict(frozen=True)

    horizon_months: int = Field(ge=1)
    total_investment: float = Field(ge=0, description="Setup + subscription over horizon.")
    monthly_gain: float = Field(description="Projected incremental revenue per month.")
    revenue_increase_pct: float = Field(description="Projected monthly revenue growth, %.")
    roi_pct: float = Field(description="((gain - investment) / investment) * 100 over horizon.")
    payback_months: float | None = Field(
        default=None,
        description="None when monthly gain is non-positive (no payback).",
    )


class OfferLineItem(BaseModel):
    """A priced module line inside the offer (prices come from the catalog)."""

    model_config = ConfigDict(frozen=True)

    module_code: ModuleCode
    module_name: str
    setup_fee: float = Field(ge=0)
    monthly_fee: float = Field(ge=0)
    currency: Currency


class Offer(BaseModel):
    """The complete commercial offer — the platform's main artifact."""

    offer_id: str
    restaurant_id: str
    executive_summary: str = Field(
        max_length=1500,
        description="The only LLM-authored field: business narrative for the client.",
    )
    recommendations: list[ModuleRecommendation] = Field(min_length=1)
    line_items: list[OfferLineItem] = Field(min_length=1)
    roi: RoiProjection
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def module_codes(self) -> list[ModuleCode]:
        return [item.module_code for item in self.line_items]


class OfferRef(BaseModel):
    """Token-cheap handle to a persisted offer.

    Agents exchange this reference instead of the full offer: the payload
    stays in the ``OfferRepository`` (Python side), the LLM only carries
    the id — this is the 'LLM thinks, Python works' rule applied to I/O.
    """

    model_config = ConfigDict(frozen=True)

    offer_id: str
    restaurant_id: str
    module_codes: list[ModuleCode] = Field(min_length=1)
    headline: str = Field(max_length=200)
