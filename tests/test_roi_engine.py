"""ROI engine: pure math, exhaustively testable."""

from __future__ import annotations

import pytest

from engines.roi_engine import ROIEngine
from models.enums import ModuleCode
from models.knowledge import KnowledgeBase
from models.restaurant import RestaurantMetrics


def test_projection_is_deterministic(
    struggling_restaurant: RestaurantMetrics, knowledge_base: KnowledgeBase
) -> None:
    engine = ROIEngine(horizon_months=12)
    modules = [knowledge_base.get_module(ModuleCode.DELIVERY)]
    prices = [knowledge_base.get_price(ModuleCode.DELIVERY)]

    first = engine.calculate(struggling_restaurant, modules, prices)
    second = engine.calculate(struggling_restaurant, modules, prices)

    assert first == second


def test_single_module_math(
    struggling_restaurant: RestaurantMetrics, knowledge_base: KnowledgeBase
) -> None:
    engine = ROIEngine(horizon_months=12)
    modules = [knowledge_base.get_module(ModuleCode.DELIVERY)]
    prices = [knowledge_base.get_price(ModuleCode.DELIVERY)]

    projection = engine.calculate(struggling_restaurant, modules, prices)

    # revenue = 3000 * 2000 = 6_000_000; +12% -> 720_000/month
    assert projection.monthly_gain == pytest.approx(720_000)
    # investment = 90_000 + 25_000 * 12 = 390_000
    assert projection.total_investment == pytest.approx(390_000)
    assert projection.payback_months == pytest.approx(0.5, abs=0.05)
    assert projection.roi_pct > 0


def test_bundle_growth_is_capped(
    struggling_restaurant: RestaurantMetrics, knowledge_base: KnowledgeBase
) -> None:
    engine = ROIEngine(horizon_months=12)
    modules = list(knowledge_base.modules.values()) * 5  # absurd bundle
    prices = list(knowledge_base.prices.values()) * 5

    projection = engine.calculate(struggling_restaurant, modules, prices)

    assert projection.revenue_increase_pct <= 40.0


def test_empty_bundle_is_rejected(struggling_restaurant: RestaurantMetrics) -> None:
    with pytest.raises(ValueError):
        ROIEngine().calculate(struggling_restaurant, [], [])


def test_invalid_horizon_is_rejected() -> None:
    with pytest.raises(ValueError):
        ROIEngine(horizon_months=0)
