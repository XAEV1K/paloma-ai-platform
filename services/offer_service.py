"""Offer assembly and persistence.

``OfferService`` is the deterministic 'offer factory': it takes the module
selection (decided by agents) and assembles a fully priced, ROI-annotated
:class:`Offer` from catalog data and engine output. The finished offer is
persisted in an :class:`OfferRepository`, and only a token-cheap
:class:`OfferRef` travels back through the LLM.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from core.exceptions import OfferNotFoundError
from core.logging import get_logger
from engines.roi_engine import ROIEngine
from models.enums import ModuleCode
from models.offer import ModuleRecommendation, Offer, OfferLineItem, OfferRef
from models.restaurant import RestaurantMetrics
from services.knowledge_service import KnowledgeService

logger = get_logger("services.offer")


class OfferRepository(Protocol):
    """Persistence port for assembled offers."""

    def save(self, offer: Offer) -> None: ...

    def get(self, offer_id: str) -> Offer:
        """Return the offer or raise ``OfferNotFoundError``."""
        ...

    def latest_for(self, restaurant_id: str) -> Offer | None:
        """The most recently saved offer for a restaurant, if any.

        Used by the pipeline's recovery path: the offer is persisted by
        Python regardless of what the agent's narration looks like.
        """
        ...


class InMemoryOfferRepository:
    """Process-local offer store — sufficient for a single pipeline run.

    TODO: replace with a database-backed repository (PostgreSQL) once
    offers must survive process restarts and feed a review UI.
    """

    def __init__(self) -> None:
        self._offers: dict[str, Offer] = {}  # insertion-ordered (dict semantics)

    def save(self, offer: Offer) -> None:
        self._offers[offer.offer_id] = offer
        logger.debug("Offer %s stored (%d total)", offer.offer_id, len(self._offers))

    def get(self, offer_id: str) -> Offer:
        offer = self._offers.get(offer_id)
        if offer is None:
            raise OfferNotFoundError(offer_id)
        return offer

    def latest_for(self, restaurant_id: str) -> Offer | None:
        for offer in reversed(self._offers.values()):
            if offer.restaurant_id == restaurant_id:
                return offer
        return None


class OfferService:
    """Assembles commercial offers from catalog data and engine outputs."""

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        roi_engine: ROIEngine,
        repository: OfferRepository,
    ) -> None:
        self._knowledge = knowledge_service
        self._roi_engine = roi_engine
        self._repository = repository

    def build_offer(
        self,
        metrics: RestaurantMetrics,
        recommendations: list[ModuleRecommendation],
        executive_summary: str,
    ) -> OfferRef:
        """Assemble, price, project and persist an offer; return its reference.

        All numbers (prices, ROI) are sourced from the catalog and the ROI
        engine — the caller (an LLM agent) contributes only the module
        selection and the executive summary narrative.
        """
        module_codes = [rec.module_code for rec in recommendations]
        modules = [self._knowledge.get_module(code) for code in module_codes]
        prices = [self._knowledge.get_price(code) for code in module_codes]

        line_items = [
            OfferLineItem(
                module_code=module.code,
                module_name=module.name,
                setup_fee=price.setup_fee,
                monthly_fee=price.monthly_fee,
                currency=price.currency,
            )
            for module, price in zip(modules, prices, strict=True)
        ]
        roi = self._roi_engine.calculate(metrics, modules, prices)

        offer = Offer(
            offer_id=f"OF-{uuid.uuid4().hex[:8].upper()}",
            restaurant_id=metrics.restaurant_id,
            executive_summary=executive_summary,
            recommendations=recommendations,
            line_items=line_items,
            roi=roi,
        )
        self._repository.save(offer)
        logger.info(
            "Offer %s generated for %s (%d module(s), ROI %.1f%%)",
            offer.offer_id,
            offer.restaurant_id,
            len(line_items),
            roi.roi_pct,
        )
        return OfferRef(
            offer_id=offer.offer_id,
            restaurant_id=offer.restaurant_id,
            module_codes=[ModuleCode(code) for code in offer.module_codes],
            headline=f"{len(line_items)} module(s), projected ROI {roi.roi_pct:.0f}%",
        )

    def get_offer(self, offer_id: str) -> Offer:
        """Fetch a previously assembled offer by id."""
        return self._repository.get(offer_id)

    def get_latest_offer(self, restaurant_id: str) -> Offer | None:
        """Fetch the most recent offer for a restaurant (recovery path)."""
        return self._repository.latest_for(restaurant_id)
