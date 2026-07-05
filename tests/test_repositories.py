"""Data layer: CSV repository, knowledge service and offer round-trip."""

from __future__ import annotations

import pytest

from config.settings import Settings
from core.exceptions import OfferNotFoundError, RestaurantNotFoundError
from engines.recommendation_engine import RecommendationEngine
from engines.roi_engine import ROIEngine
from services.knowledge_service import KnowledgeService
from services.offer_service import InMemoryOfferRepository, OfferService
from services.restaurant_service import CsvMetricsRepository


def test_csv_repository_loads_demo_data(settings: Settings) -> None:
    repository = CsvMetricsRepository(settings.restaurants_csv)

    ids = repository.list_ids()
    assert "R-001" in ids

    metrics = repository.get_by_id("R-001")
    assert metrics.name == "Dastarkhan Lounge"
    assert metrics.monthly_revenue == pytest.approx(4200 * 3100)


def test_unknown_restaurant_raises(settings: Settings) -> None:
    repository = CsvMetricsRepository(settings.restaurants_csv)
    with pytest.raises(RestaurantNotFoundError):
        repository.get_by_id("R-999")


def test_knowledge_service_loads_catalog(settings: Settings) -> None:
    service = KnowledgeService(settings.modules_json, settings.prices_json)
    knowledge = service.knowledge_base

    assert set(knowledge.modules) == set(knowledge.prices), "every module must be priced"
    assert len(knowledge.modules) >= 6


def test_offer_round_trip_without_llm(settings: Settings) -> None:
    """Full deterministic slice: metrics -> rules -> ROI -> offer -> fetch."""
    metrics = CsvMetricsRepository(settings.restaurants_csv).get_by_id("R-001")
    knowledge = KnowledgeService(settings.modules_json, settings.prices_json)
    offer_service = OfferService(knowledge, ROIEngine(), InMemoryOfferRepository())

    recommendations = RecommendationEngine().recommend(metrics)
    assert recommendations, "R-001 is designed to trigger rules"

    ref = offer_service.build_offer(metrics, recommendations, "Deterministic test summary.")
    offer = offer_service.get_offer(ref.offer_id)

    assert offer.restaurant_id == "R-001"
    assert offer.module_codes == ref.module_codes
    assert offer.roi.total_investment > 0


def test_missing_offer_raises() -> None:
    with pytest.raises(OfferNotFoundError):
        InMemoryOfferRepository().get("OF-NOPE")
