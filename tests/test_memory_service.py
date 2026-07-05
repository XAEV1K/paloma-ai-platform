"""Business memory: persistence round-trip and rejection aggregation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from models.business_case import BusinessCase, BusinessProblem
from models.enums import (
    ModuleCode,
    OfferOutcome,
    ProblemCategory,
    Severity,
)
from models.memory import PastOffer, RestaurantHistory
from models.offer import (
    ModuleRecommendation,
    Offer,
    OfferLineItem,
    RoiProjection,
)
from models.enums import Currency
from services.memory_service import BusinessMemoryService, JsonMemoryRepository


def _history_with_rejection() -> RestaurantHistory:
    return RestaurantHistory(
        restaurant_id="T-001",
        offers=[
            PastOffer(
                offer_id="OF-OLD",
                offered_at=datetime(2026, 1, 14, tzinfo=timezone.utc),
                module_codes=[ModuleCode.CRM_LOYALTY],
                roi_pct=96.0,
                outcome=OfferOutcome.REJECTED,
                rejected_modules=[ModuleCode.CRM_LOYALTY],
            )
        ],
    )


def test_first_contact_returns_empty_history(tmp_path: Path) -> None:
    service = BusinessMemoryService(JsonMemoryRepository(tmp_path / "memory.json"))
    history = service.get_history("T-404")
    assert history.analyses == [] and history.offers == []


def test_round_trip(tmp_path: Path) -> None:
    repository = JsonMemoryRepository(tmp_path / "memory.json")
    repository.save(_history_with_rejection())

    loaded = repository.load("T-001")

    assert loaded is not None
    assert loaded.previously_rejected_modules == {ModuleCode.CRM_LOYALTY}
    assert loaded.last_offer is not None and loaded.last_offer.offer_id == "OF-OLD"


def test_record_run_appends_history(tmp_path: Path) -> None:
    service = BusinessMemoryService(JsonMemoryRepository(tmp_path / "memory.json"))
    business_case = BusinessCase(
        restaurant_id="T-001",
        headline="Test case",
        problems=[
            BusinessProblem(
                category=ProblemCategory.LOW_DELIVERY_SHARE,
                severity=Severity.HIGH,
                metric_name="delivery_share",
                metric_value=0.05,
                benchmark=0.15,
                summary="Delivery share far below benchmark.",
            )
        ],
        priority_order=[ProblemCategory.LOW_DELIVERY_SHARE],
    )
    offer = Offer(
        offer_id="OF-NEW",
        restaurant_id="T-001",
        executive_summary="s",
        recommendations=[
            ModuleRecommendation(
                module_code=ModuleCode.DELIVERY,
                addresses=ProblemCategory.LOW_DELIVERY_SHARE,
                priority=1,
                rationale="r",
            )
        ],
        line_items=[
            OfferLineItem(
                module_code=ModuleCode.DELIVERY,
                module_name="Delivery",
                setup_fee=90000,
                monthly_fee=25000,
                currency=Currency.KZT,
            )
        ],
        roi=RoiProjection(
            horizon_months=12,
            total_investment=390000,
            monthly_gain=720000,
            revenue_increase_pct=12.0,
            roi_pct=120.0,
            payback_months=0.5,
        ),
    )

    service.record_run(business_case, offer)
    history = service.get_history("T-001")

    assert len(history.analyses) == 1
    assert len(history.offers) == 1
    assert history.offers[0].outcome is OfferOutcome.SENT
