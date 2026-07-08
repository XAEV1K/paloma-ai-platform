"""Memory Fabric: five memory domains behind one facade.

The platform remembers different things at different lifetimes:

- **Knowledge Memory**     — what the company knows (vector index)
- **Conversation Memory**  — what was said, on every channel
- **Business Memory**      — what was analysed, offered and rejected
- **Restaurant Memory**    — the operational metrics of each venue
- **Customer Memory**      — who the customers are (fed by CRM sync)

Each domain keeps its own store and its own API; the fabric provides the
platform-level view (boot report, health checks, daily analytics) without
collapsing them into one schema — domains evolve independently.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.logging import get_logger
from conversation.memory import ConversationStorePort
from rag.vector_store import VectorStorePort
from services.customer_memory import CustomerMemoryService
from services.memory_service import BusinessMemoryService
from services.restaurant_service import RestaurantService

logger = get_logger("services.memory_fabric")


@dataclass(frozen=True, slots=True)
class MemoryDomainStatus:
    """One domain's headline numbers for status/boot views."""

    domain: str
    detail: str


class MemoryFabric:
    """Read-side facade over the platform's memory domains."""

    def __init__(
        self,
        vector_store: VectorStorePort,
        conversation_store: ConversationStorePort,
        business_memory: BusinessMemoryService | None,
        restaurant_service: RestaurantService,
        customer_memory: CustomerMemoryService,
    ) -> None:
        self._vector_store = vector_store
        self._conversation_store = conversation_store
        self._business_memory = business_memory
        self._restaurant_service = restaurant_service
        self._customer_memory = customer_memory

    def describe(self) -> list[MemoryDomainStatus]:
        """Headline numbers per domain (never raises — degrades to 'offline')."""
        domains: list[MemoryDomainStatus] = []

        def probe(domain: str, fn) -> None:
            try:
                domains.append(MemoryDomainStatus(domain=domain, detail=fn()))
            except Exception as exc:  # noqa: BLE001 — status view must not crash
                domains.append(MemoryDomainStatus(domain=domain, detail=f"offline ({exc})"))

        probe("Knowledge", lambda: f"{self._vector_store.count()} chunk(s) indexed")
        probe("Conversation", lambda: "persistent store online")
        probe(
            "Business",
            lambda: "engagement history online"
            if self._business_memory is not None
            else "disabled by flag",
        )
        probe(
            "Restaurant",
            lambda: f"{len(self._restaurant_service.list_restaurants())} venue(s) connected",
        )
        probe("Customer", lambda: f"{self._customer_memory.count()} customer record(s)")
        return domains
