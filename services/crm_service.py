"""CRM integration service.

Serves guest-relationship signals (:class:`CrmSnapshot`) that enrich the
Architect's diagnosis. Currently backed by deterministic mock data so the
demo runs offline; the public contract is final and production-ready.

TODO: replace the mock with the real Paloma365 CRM REST API client
(httpx + retry/backoff + auth from Settings) behind the same interface.
"""

from __future__ import annotations

import hashlib

from core.logging import get_logger
from models.crm import CrmSnapshot

logger = get_logger("services.crm")

_COMPLAINT_TOPICS: tuple[str, ...] = (
    "delivery delays",
    "cold food",
    "order mix-ups",
    "long waiting time",
    "app usability",
)


class CrmService:
    """Read-side facade over the (future) Paloma365 CRM API."""

    def get_snapshot(self, restaurant_id: str) -> CrmSnapshot:
        """Return CRM signals for a restaurant.

        Mock implementation: derives stable pseudo-data from the id hash so
        repeated demo runs are reproducible (same id -> same snapshot).
        """
        seed = int(hashlib.sha256(restaurant_id.encode()).hexdigest(), 16)
        snapshot = CrmSnapshot(
            restaurant_id=restaurant_id,
            nps=float(seed % 71 - 10),  # -10..60
            complaints_last_month=seed % 25,
            top_complaint_topics=list(_COMPLAINT_TOPICS[: seed % 3 + 1]),
            repeat_guest_share=round((seed % 40 + 10) / 100, 2),  # 0.10..0.49
            loyalty_program_active=bool(seed % 2),
        )
        logger.info("CRM snapshot served for %s (mock backend)", restaurant_id)
        return snapshot
