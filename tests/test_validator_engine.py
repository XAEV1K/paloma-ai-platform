"""Validator engine: the anti-hallucination firewall must actually fire."""

from __future__ import annotations

from engines.validator_engine import ValidatorEngine
from models.enums import Currency, ModuleCode, ProblemCategory, ValidationStatus
from models.knowledge import KnowledgeBase
from models.offer import (
    ModuleRecommendation,
    Offer,
    OfferLineItem,
    RoiProjection,
)


def _offer(
    knowledge_base: KnowledgeBase,
    *,
    roi_pct: float = 120.0,
    payback_months: float | None = 4.0,
    setup_fee: float = 90000,
    monthly_fee: float = 25000,
) -> Offer:
    return Offer(
        offer_id="OF-TEST0001",
        restaurant_id="T-001",
        executive_summary="Test summary.",
        recommendations=[
            ModuleRecommendation(
                module_code=ModuleCode.DELIVERY,
                addresses=ProblemCategory.LOW_DELIVERY_SHARE,
                priority=1,
                rationale="Delivery share below benchmark.",
            )
        ],
        line_items=[
            OfferLineItem(
                module_code=ModuleCode.DELIVERY,
                module_name="Delivery",
                setup_fee=setup_fee,
                monthly_fee=monthly_fee,
                currency=Currency.KZT,
            )
        ],
        roi=RoiProjection(
            horizon_months=12,
            total_investment=390000,
            monthly_gain=720000,
            revenue_increase_pct=12.0,
            roi_pct=roi_pct,
            payback_months=payback_months,
        ),
    )


def test_valid_offer_passes(knowledge_base: KnowledgeBase) -> None:
    report = ValidatorEngine().validate(_offer(knowledge_base), knowledge_base)

    assert report.status is ValidationStatus.PASSED
    assert report.is_approved
    assert report.issues == []


def test_absurd_roi_fails(knowledge_base: KnowledgeBase) -> None:
    offer = _offer(knowledge_base, roi_pct=900.0)
    report = ValidatorEngine().validate(offer, knowledge_base)

    assert report.status is ValidationStatus.FAILED
    assert any(issue.rule_id == "ROI_BOUNDS" for issue in report.issues)


def test_missing_payback_fails(knowledge_base: KnowledgeBase) -> None:
    offer = _offer(knowledge_base, payback_months=None)
    report = ValidatorEngine().validate(offer, knowledge_base)

    assert report.status is ValidationStatus.FAILED
    assert any(issue.rule_id == "PAYBACK" for issue in report.issues)


def test_price_tampering_fails(knowledge_base: KnowledgeBase) -> None:
    offer = _offer(knowledge_base, setup_fee=1.0)  # not the catalog price
    report = ValidatorEngine().validate(offer, knowledge_base)

    assert report.status is ValidationStatus.FAILED
    assert any(issue.rule_id == "PRICE_CONSISTENCY" for issue in report.issues)


def test_long_payback_is_warning_not_failure(knowledge_base: KnowledgeBase) -> None:
    offer = _offer(knowledge_base, payback_months=18.0)
    report = ValidatorEngine().validate(offer, knowledge_base)

    assert report.status is ValidationStatus.PASSED_WITH_WARNINGS
    assert report.is_approved
