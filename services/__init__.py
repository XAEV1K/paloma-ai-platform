"""Application services: data access, catalog, offers, CRM, memory, reporting.

Services own all I/O. They depend on ``models`` and ``engines`` and are
consumed by ``tools`` (the CrewAI boundary) — never the other way around.
"""

from services.crm_service import CrmService
from services.knowledge_service import KnowledgeService
from services.memory_service import (
    BusinessMemoryService,
    JsonMemoryRepository,
    MemoryRepository,
)
from services.offer_service import InMemoryOfferRepository, OfferRepository, OfferService
from services.report_service import ReportService
from services.restaurant_service import (
    CachedMetricsRepository,
    CsvMetricsRepository,
    MetricsRepository,
    RestaurantService,
    SqliteMetricsRepository,
)

__all__ = [
    "BusinessMemoryService",
    "CachedMetricsRepository",
    "CrmService",
    "CsvMetricsRepository",
    "InMemoryOfferRepository",
    "JsonMemoryRepository",
    "KnowledgeService",
    "MemoryRepository",
    "MetricsRepository",
    "OfferRepository",
    "OfferService",
    "ReportService",
    "RestaurantService",
    "SqliteMetricsRepository",
]
