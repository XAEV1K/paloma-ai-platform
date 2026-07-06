"""No single agent can abort the pipeline: stage-resolution fallbacks."""

from __future__ import annotations

import pytest

from config.settings import Settings
from core.container import Container
from core.exceptions import AgentContractError
from models.business_case import BusinessCase
from models.enums import Severity


class _FakeCrewOutput:
    def __init__(self, raws: list[str]) -> None:
        self.tasks_output = [type("T", (), {"raw": raw})() for raw in raws]


@pytest.fixture()
def container() -> Container:
    return Container.build(Settings(_env_file=None))  # type: ignore[call-arg]


def _generate_offer(container: Container, restaurant_id: str):
    metrics = container.restaurant_service.get_metrics(restaurant_id)
    recommendations = container.pipeline._tools[
        "module_recommendations"
    ].recommendation_engine.recommend(metrics)
    container.offer_service.build_offer(metrics, recommendations, "s")
    return container.offer_service.get_latest_offer(restaurant_id)


def test_garbage_developer_narration_recovers_the_persisted_offer(
    container: Container,
) -> None:
    expected = _generate_offer(container, "R-001")
    crew_output = _FakeCrewOutput(["irrelevant", "I am sorry, I could not comply."])

    offer = container.pipeline._resolve_offer(crew_output, "R-001")

    assert offer.offer_id == expected.offer_id


def test_fabricated_offer_ref_recovers_the_real_offer(container: Container) -> None:
    expected = _generate_offer(container, "R-001")
    fake_ref = (
        '{"offer_id": "OF-FABRICATED", "restaurant_id": "R-001", '
        '"module_codes": ["DELIVERY"], "headline": "trust me"}'
    )
    crew_output = _FakeCrewOutput(["irrelevant", fake_ref])

    offer = container.pipeline._resolve_offer(crew_output, "R-001")

    assert offer.offer_id == expected.offer_id


def test_no_offer_at_all_is_a_clean_abort(container: Container) -> None:
    crew_output = _FakeCrewOutput(["irrelevant", "nothing useful"])
    with pytest.raises(AgentContractError, match="never generated an offer"):
        container.pipeline._resolve_offer(crew_output, "R-004")


def test_garbage_architect_narration_falls_back_to_rule_engine(
    container: Container,
) -> None:
    offer = _generate_offer(container, "R-001")
    metrics = container.restaurant_service.get_metrics("R-001")
    crew_output = _FakeCrewOutput(["I refuse to answer in JSON today.", "x"])

    case = container.pipeline._resolve_business_case(crew_output, metrics, offer)

    assert isinstance(case, BusinessCase)
    assert case.restaurant_id == "R-001"
    assert len(case.problems) == len(offer.recommendations)
    # Evidence comes from real metrics and thresholds, not placeholders.
    problem = next(p for p in case.problems if p.metric_name == "retention_rate")
    assert problem.metric_value == pytest.approx(0.18)
    assert problem.benchmark == pytest.approx(0.25)
    assert problem.severity in (Severity.HIGH, Severity.MEDIUM)


def test_valid_architect_narration_is_preferred_over_fallback(
    container: Container,
) -> None:
    offer = _generate_offer(container, "R-001")
    metrics = container.restaurant_service.get_metrics("R-001")
    narration = (
        '{"restaurant_id": "R-001", "headline": "LLM-authored headline.", '
        '"problems": [{"category": "low_retention", "severity": "high", '
        '"metric_name": "retention_rate", "metric_value": 0.18, '
        '"benchmark": 0.25, "summary": "s"}], '
        '"growth_opportunities": [], "priority_order": ["LOW_RETENTION"]}'
    )
    crew_output = _FakeCrewOutput([narration, "x"])

    case = container.pipeline._resolve_business_case(crew_output, metrics, offer)

    assert case.headline == "LLM-authored headline."
