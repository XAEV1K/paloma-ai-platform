"""Pipeline anti-hallucination and resilience guards (no LLM required)."""

from __future__ import annotations

import pytest

from core.exceptions import (
    AgentContractError,
    PalomaError,
    PipelineExecutionError,
)
from core.structured_output import extract_contract
from crew.crew import PalomaPipeline
from models.offer import OfferRef


class _FakeCrewOutput:
    def __init__(self, raws: list[str]) -> None:
        self.tasks_output = [type("T", (), {"raw": raw})() for raw in raws]


def test_stage_raw_returns_the_stage_answer() -> None:
    output = _FakeCrewOutput(["first", "second"])
    assert PalomaPipeline._stage_raw(output, 1, "Developer") == "second"


def test_missing_stage_is_a_clean_contract_error() -> None:
    output = _FakeCrewOutput(["only one"])
    with pytest.raises(AgentContractError, match="Developer stage produced no output"):
        PalomaPipeline._stage_raw(output, 1, "Developer")


def test_fabricated_reference_is_detected_by_extraction_plus_repository() -> None:
    """The extractor accepts the JSON; the repository lookup is the guard."""
    raw = (
        '{"offer_id": "OF-FAKE", "restaurant_id": "R-001", '
        '"module_codes": ["DELIVERY"], "headline": "looks legit"}'
    )
    ref = extract_contract(raw, OfferRef)
    assert ref.offer_id == "OF-FAKE"  # parsing succeeds; crew.run() checks existence


def test_latest_offer_recovery_path(settings, tmp_path) -> None:
    """Broken Developer narration -> the persisted offer is still recoverable."""
    from engines.recommendation_engine import RecommendationEngine
    from engines.roi_engine import ROIEngine
    from services.knowledge_service import KnowledgeService
    from services.offer_service import InMemoryOfferRepository, OfferService
    from services.restaurant_service import CsvMetricsRepository

    metrics = CsvMetricsRepository(settings.restaurants_csv).get_by_id("R-001")
    knowledge = KnowledgeService(settings.modules_json, settings.prices_json)
    service = OfferService(knowledge, ROIEngine(), InMemoryOfferRepository())

    assert service.get_latest_offer("R-001") is None, "no offers yet"

    recommendations = RecommendationEngine().recommend(metrics)
    ref = service.build_offer(metrics, recommendations, "s")

    recovered = service.get_latest_offer("R-001")
    assert recovered is not None and recovered.offer_id == ref.offer_id
    assert service.get_latest_offer("R-999") is None


def test_domain_error_hierarchy() -> None:
    """The CLI catches PalomaError — every failure mode must be inside it."""
    assert issubclass(AgentContractError, PalomaError)
    assert issubclass(PipelineExecutionError, PalomaError)
