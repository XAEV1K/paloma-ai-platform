"""Business memory contracts: what the platform remembers about a client.

Not conversation memory — *business* memory: past diagnoses, past offers
and, crucially, their outcomes. This is what lets an agent say
"CRM_LOYALTY was offered six months ago and rejected — lead with the
new delivery data instead of repeating the same pitch."
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import ModuleCode, OfferOutcome, ProblemCategory


class PastAnalysis(BaseModel):
    """A previous Architect diagnosis, compressed to what matters later."""

    model_config = ConfigDict(frozen=True)

    analyzed_at: datetime
    headline: str
    problem_categories: list[ProblemCategory]


class PastOffer(BaseModel):
    """A previous commercial offer and how the client responded."""

    model_config = ConfigDict(frozen=True)

    offer_id: str
    offered_at: datetime
    module_codes: list[ModuleCode]
    roi_pct: float
    outcome: OfferOutcome = OfferOutcome.SENT
    rejected_modules: list[ModuleCode] = Field(
        default_factory=list,
        description="Modules the client explicitly declined (even in accepted offers).",
    )
    outcome_comment: str = Field(default="", max_length=300)


class RestaurantHistory(BaseModel):
    """Everything the platform knows about its past work with one restaurant."""

    restaurant_id: str
    analyses: list[PastAnalysis] = Field(default_factory=list)
    offers: list[PastOffer] = Field(default_factory=list)

    @property
    def previously_rejected_modules(self) -> set[ModuleCode]:
        """Modules this client has said 'no' to, across all history."""
        rejected: set[ModuleCode] = set()
        for offer in self.offers:
            rejected.update(offer.rejected_modules)
            if offer.outcome is OfferOutcome.REJECTED:
                rejected.update(offer.module_codes)
        return rejected

    @property
    def last_offer(self) -> PastOffer | None:
        if not self.offers:
            return None
        return max(self.offers, key=lambda offer: offer.offered_at)
