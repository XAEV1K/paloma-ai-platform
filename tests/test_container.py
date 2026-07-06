"""Composition root: flags and calibration flow into the object graph."""

from __future__ import annotations

from config.settings import Settings
from core.container import Container


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_container_builds_offline_without_credentials() -> None:
    """No LLM handle is constructed at assembly time (lazy routing)."""
    container = Container.build(_settings())
    assert container.restaurant_service.list_restaurants()
    assert len(container.knowledge_service.list_modules()) >= 6


def test_roi_calibration_flows_from_settings() -> None:
    container = Container.build(
        _settings(roi_gross_margin_pct=0.5, roi_attribution_pct=0.8, roi_ramp_up_months=1)
    )
    metrics = container.restaurant_service.get_metrics("R-001")
    module = container.knowledge_service.list_modules()[0]
    price = container.knowledge_service.get_price(module.code)

    projection = container.pipeline._tools["roi_calculator"].roi_engine.calculate(
        metrics, [module], [price]
    )

    assert projection.assumptions.gross_margin_pct == 0.5
    assert projection.assumptions.attribution_pct == 0.8
    assert projection.assumptions.ramp_up_months == 1


def test_memory_flag_removes_tool_and_service() -> None:
    container = Container.build(_settings(use_business_memory=False))
    assert container.memory_service is None
    assert "business_memory" not in container.pipeline._tools
