"""ROI engine: conservative economics, exhaustively testable.

Reference math for the 'struggling' fixture + single DELIVERY module
(12% order growth) with default assumptions (30% margin, 60% attribution,
3-month ramp, 12-month horizon):

    monthly revenue      = 3000 * 2000            = 6,000,000
    incremental revenue  = 6,000,000 * 12%        =   720,000
    steady profit gain   = 720,000 * 0.30 * 0.60  =   129,600
    investment           = 90,000 + 25,000 * 12   =   390,000
    ramp factors sum     = 1/3 + 2/3 + 1 + 9      =        11
    horizon gain         = 129,600 * 11           = 1,425,600
    ROI                  = (1,425,600 - 390,000) / 390,000 = 265.5%
    payback              = 4 months + tiny fraction ≈ 4.0
"""

from __future__ import annotations

import pytest

from engines.roi_engine import ROIEngine
from models.enums import ModuleCode
from models.knowledge import ImpactAssumptions, KnowledgeBase, PalomaModule
from models.offer import RoiAssumptions
from models.restaurant import RestaurantMetrics


def test_projection_is_deterministic(
    struggling_restaurant: RestaurantMetrics, knowledge_base: KnowledgeBase
) -> None:
    engine = ROIEngine(horizon_months=12)
    modules = [knowledge_base.get_module(ModuleCode.DELIVERY)]
    prices = [knowledge_base.get_price(ModuleCode.DELIVERY)]

    assert engine.calculate(struggling_restaurant, modules, prices) == engine.calculate(
        struggling_restaurant, modules, prices
    )


def test_single_module_math(
    struggling_restaurant: RestaurantMetrics, knowledge_base: KnowledgeBase
) -> None:
    engine = ROIEngine(horizon_months=12)
    modules = [knowledge_base.get_module(ModuleCode.DELIVERY)]
    prices = [knowledge_base.get_price(ModuleCode.DELIVERY)]

    projection = engine.calculate(struggling_restaurant, modules, prices)

    assert projection.monthly_gain == pytest.approx(129_600)
    assert projection.total_investment == pytest.approx(390_000)
    assert projection.roi_pct == pytest.approx(265.54, abs=0.1)
    assert projection.payback_months == pytest.approx(4.0, abs=0.1)
    assert projection.assumptions == RoiAssumptions()  # defaults travel with the numbers


def test_roi_stays_in_credible_band(
    struggling_restaurant: RestaurantMetrics, knowledge_base: KnowledgeBase
) -> None:
    """The audit finding: naive math produced 4945% ROI. Never again."""
    engine = ROIEngine(horizon_months=12)
    modules = list(knowledge_base.modules.values())
    prices = list(knowledge_base.prices.values())

    projection = engine.calculate(struggling_restaurant, modules, prices)

    assert 0 < projection.roi_pct <= 500.0, "projection must pass the validator's ROI bounds"


def test_bundle_growth_is_capped(
    struggling_restaurant: RestaurantMetrics, knowledge_base: KnowledgeBase
) -> None:
    engine = ROIEngine(horizon_months=12)
    modules = list(knowledge_base.modules.values()) * 5  # absurd bundle
    prices = list(knowledge_base.prices.values()) * 5

    projection = engine.calculate(struggling_restaurant, modules, prices)

    assert projection.revenue_increase_pct <= 25.0


def test_custom_assumptions_are_applied(
    struggling_restaurant: RestaurantMetrics, knowledge_base: KnowledgeBase
) -> None:
    """No margin/attribution haircut, no ramp -> raw revenue math."""
    engine = ROIEngine(
        horizon_months=12,
        assumptions=RoiAssumptions(gross_margin_pct=1.0, attribution_pct=1.0, ramp_up_months=0),
    )
    modules = [knowledge_base.get_module(ModuleCode.DELIVERY)]
    prices = [knowledge_base.get_price(ModuleCode.DELIVERY)]

    projection = engine.calculate(struggling_restaurant, modules, prices)

    assert projection.monthly_gain == pytest.approx(720_000)
    assert projection.payback_months == pytest.approx(390_000 / 720_000, abs=0.06)


def test_zero_impact_bundle_has_no_payback(struggling_restaurant: RestaurantMetrics) -> None:
    dead_module = PalomaModule(
        code=ModuleCode.ANALYTICS_PRO,
        name="No-op",
        description="Zero uplift.",
        impact=ImpactAssumptions(),
    )
    from models.enums import Currency
    from models.knowledge import ModulePrice

    price = ModulePrice(
        code=ModuleCode.ANALYTICS_PRO, setup_fee=0, monthly_fee=22_000, currency=Currency.KZT
    )
    projection = ROIEngine().calculate(struggling_restaurant, [dead_module], [price])

    assert projection.payback_months is None
    assert projection.roi_pct < 0


def test_empty_bundle_is_rejected(struggling_restaurant: RestaurantMetrics) -> None:
    with pytest.raises(ValueError):
        ROIEngine().calculate(struggling_restaurant, [], [])


def test_invalid_horizon_is_rejected() -> None:
    with pytest.raises(ValueError):
        ROIEngine(horizon_months=0)
