"""Shared fixtures: everything below the LLM boundary is testable offline."""

from __future__ import annotations

import pytest

from config.settings import Settings
from models.enums import Currency, ModuleCode
from models.knowledge import (
    ImpactAssumptions,
    KnowledgeBase,
    ModulePrice,
    PalomaModule,
)
from models.restaurant import RestaurantMetrics


@pytest.fixture()
def settings() -> Settings:
    return Settings(openai_api_key=None)


@pytest.fixture()
def struggling_restaurant() -> RestaurantMetrics:
    """A restaurant that should trigger most recommendation rules."""
    return RestaurantMetrics(
        restaurant_id="T-001",
        name="Test Bistro",
        city="Almaty",
        avg_ticket=3000.0,
        orders_per_month=2000,
        avg_kitchen_time_min=26.0,
        avg_delivery_time_min=50.0,
        retention_rate=0.15,
        ltv=25000.0,
        delivery_share=0.05,
        takeaway_share=0.15,
        dine_in_share=0.80,
        kitchen_load=0.92,
    )


@pytest.fixture()
def healthy_restaurant() -> RestaurantMetrics:
    """A restaurant that should trigger no recommendation rules."""
    return RestaurantMetrics(
        restaurant_id="T-002",
        name="Healthy Grill",
        city="Astana",
        avg_ticket=5000.0,
        orders_per_month=4000,
        avg_kitchen_time_min=12.0,
        avg_delivery_time_min=28.0,
        retention_rate=0.40,
        ltv=60000.0,
        delivery_share=0.30,
        takeaway_share=0.20,
        dine_in_share=0.50,
        kitchen_load=0.60,
    )


@pytest.fixture()
def knowledge_base() -> KnowledgeBase:
    """Minimal two-module catalog for engine tests."""
    delivery = PalomaModule(
        code=ModuleCode.DELIVERY,
        name="Delivery",
        description="Delivery management.",
        impact=ImpactAssumptions(order_growth_pct=12.0),
    )
    crm = PalomaModule(
        code=ModuleCode.CRM_LOYALTY,
        name="CRM & Loyalty",
        description="Guest retention.",
        impact=ImpactAssumptions(order_growth_pct=6.0, avg_ticket_growth_pct=3.0),
    )
    return KnowledgeBase(
        modules={m.code: m for m in (delivery, crm)},
        prices={
            ModuleCode.DELIVERY: ModulePrice(
                code=ModuleCode.DELIVERY, setup_fee=90000, monthly_fee=25000,
                currency=Currency.KZT,
            ),
            ModuleCode.CRM_LOYALTY: ModulePrice(
                code=ModuleCode.CRM_LOYALTY, setup_fee=60000, monthly_fee=20000,
                currency=Currency.KZT,
            ),
        },
    )
