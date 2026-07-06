"""Business memory service: the platform's long-term client knowledge.

Backed by a JSON file today (perfectly adequate for hundreds of
restaurants); the :class:`MemoryRepository` protocol is the seam for a
real database when history becomes multi-tenant.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from core.exceptions import DataSourceError
from core.logging import get_logger
from models.business_case import BusinessCase
from models.enums import OfferOutcome
from models.memory import PastAnalysis, PastOffer, RestaurantHistory
from models.offer import Offer

logger = get_logger("services.memory")


class MemoryRepository(Protocol):
    """Persistence port for restaurant histories."""

    def load(self, restaurant_id: str) -> RestaurantHistory | None: ...

    def save(self, history: RestaurantHistory) -> None: ...


class JsonMemoryRepository:
    """File-backed store: ``{restaurant_id: RestaurantHistory}`` in one JSON.

    TODO: move to PostgreSQL (one table per aggregate) when concurrent
    writers appear; the protocol keeps that swap local to the container.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self, restaurant_id: str) -> RestaurantHistory | None:
        data = self._read_all()
        raw = data.get(restaurant_id)
        if raw is None:
            return None
        try:
            return RestaurantHistory(**raw)
        except ValidationError as exc:
            raise DataSourceError(f"Corrupt memory record for '{restaurant_id}': {exc}") from exc

    def save(self, history: RestaurantHistory) -> None:
        data = self._read_all()
        data[history.restaurant_id] = history.model_dump(mode="json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug("Memory persisted for %s", history.restaurant_id)

    def _read_all(self) -> dict[str, dict]:
        if not self._path.is_file():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"Cannot read memory store {self._path}: {exc}") from exc


class BusinessMemoryService:
    """Read/write facade over the client history store."""

    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    def get_history(self, restaurant_id: str) -> RestaurantHistory:
        """Return the restaurant's history (empty history if first contact)."""
        history = self._repository.load(restaurant_id)
        if history is None:
            logger.info("No prior history for %s (first engagement)", restaurant_id)
            return RestaurantHistory(restaurant_id=restaurant_id)
        logger.info(
            "History loaded for %s: %d analysis(es), %d offer(s)",
            restaurant_id,
            len(history.analyses),
            len(history.offers),
        )
        return history

    def record_run(self, business_case: BusinessCase, offer: Offer) -> None:
        """Append this pipeline run's diagnosis and offer to the history.

        The offer starts as ``SENT``; its final outcome (accepted /
        rejected) is recorded later via :meth:`record_outcome` when the
        sales team hears back.
        """
        history = self.get_history(offer.restaurant_id)
        history.analyses.append(
            PastAnalysis(
                analyzed_at=datetime.now(timezone.utc),  # time is Python's job, not the LLM's
                headline=business_case.headline,
                problem_categories=[p.category for p in business_case.problems],
            )
        )
        history.offers.append(
            PastOffer(
                offer_id=offer.offer_id,
                offered_at=offer.created_at,
                module_codes=list(offer.module_codes),
                roi_pct=offer.roi.roi_pct,
                outcome=OfferOutcome.SENT,
            )
        )
        self._repository.save(history)
        logger.info("Run recorded to business memory for %s", offer.restaurant_id)

    def record_outcome(self, restaurant_id: str, offer_id: str, outcome: OfferOutcome) -> None:
        """Update an offer's outcome once the client responds.

        TODO: expose through the future CRM webhook / review UI. Frozen
        models mean replace-not-mutate.
        """
        raise NotImplementedError("Outcome feedback loop is a roadmap item")
