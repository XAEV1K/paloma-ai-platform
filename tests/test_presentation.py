"""Presentation layer: all three renderers over one shared context."""

from __future__ import annotations

from pathlib import Path

import pytest

from models.business_case import BusinessCase, BusinessProblem
from models.enums import (
    Currency,
    ModuleCode,
    ProblemCategory,
    Severity,
    ValidationStatus,
)
from models.offer import (
    ModuleRecommendation,
    Offer,
    OfferLineItem,
    RoiProjection,
)
from models.restaurant import RestaurantMetrics
from models.validation import ValidationReport
from presentation import ReportContext
from presentation.console import render_flow
from presentation.html_report import render_html
from presentation.markdown_report import render_markdown
from services.report_service import ReportService


@pytest.fixture()
def report_context(healthy_restaurant: RestaurantMetrics) -> ReportContext:
    business_case = BusinessCase(
        restaurant_id=healthy_restaurant.restaurant_id,
        headline="Delivery under-penetration limits growth.",
        problems=[
            BusinessProblem(
                category=ProblemCategory.LOW_DELIVERY_SHARE,
                severity=Severity.HIGH,
                metric_name="delivery_share",
                metric_value=0.08,
                benchmark=0.15,
                summary="Delivery share is roughly half the official benchmark.",
            )
        ],
        growth_opportunities=["Launch own delivery with courier dispatch."],
        priority_order=[ProblemCategory.LOW_DELIVERY_SHARE],
    )
    offer = Offer(
        offer_id="OF-DEMO0001",
        restaurant_id=healthy_restaurant.restaurant_id,
        executive_summary="Delivery module closes the largest revenue gap. <script>alert(1)</script>",
        recommendations=[
            ModuleRecommendation(
                module_code=ModuleCode.DELIVERY,
                addresses=ProblemCategory.LOW_DELIVERY_SHARE,
                priority=1,
                rationale="Delivery share 8% is below the 15% benchmark.",
            )
        ],
        line_items=[
            OfferLineItem(
                module_code=ModuleCode.DELIVERY,
                module_name="Paloma365 Delivery",
                setup_fee=90_000,
                monthly_fee=25_000,
                currency=Currency.KZT,
            )
        ],
        roi=RoiProjection(
            horizon_months=12,
            total_investment=390_000,
            monthly_gain=129_600,
            revenue_increase_pct=12.0,
            roi_pct=265.5,
            payback_months=4.0,
        ),
    )
    validation = ValidationReport(
        offer_id=offer.offer_id,
        status=ValidationStatus.PASSED,
        issues=[],
        rules_checked=5,
    )
    return ReportContext(
        business_case=business_case,
        offer=offer,
        validation=validation,
        metrics=healthy_restaurant,
    )


def test_markdown_report_contains_every_section(report_context: ReportContext) -> None:
    document = render_markdown(report_context)
    for marker in (
        "# Business Proposal",
        "## Business Health Score",
        "85/100",
        "## Restaurant Profile",
        "## Diagnosis",
        "## Recommended Paloma365 Modules",
        "## Financial Projection",
        "## Validation — PASSED",
        "## Next Steps",
        "265.5%",
        "Paloma365 Delivery",
    ):
        assert marker in document, f"missing section: {marker}"


def test_html_report_is_selfcontained_and_escaped(report_context: ReportContext) -> None:
    document = render_html(report_context)
    assert document.startswith("<!DOCTYPE html>")
    assert "VALIDATED" in document and "Paloma365 Delivery" in document
    assert "Business Health Score" in document and "Implementation Timeline" in document
    assert "Paloma365 AI Decision Platform" in document
    assert "<script>alert(1)</script>" not in document, "LLM-authored text must be escaped"
    assert "&lt;script&gt;" in document
    assert "http://" not in document and "https://" not in document, "no external assets"


def test_console_flow_tells_the_whole_story(report_context: ReportContext) -> None:
    flow = render_flow(
        report_context, "req-demo", Path("reports/x.md"), Path("reports/x.html")
    )
    for stage in (
        "RESTAURANT",
        "BUSINESS ANALYSIS",
        "BUSINESS HEALTH",
        "PROBLEMS DIAGNOSED (1)",
        "GROWTH OPPORTUNITIES (1)",
        "RECOMMENDED MODULES (1)",
        "PROJECTED ROI",
        "VALIDATION",
        "COMMERCIAL PROPOSAL",
    ):
        assert stage in flow, f"missing funnel stage: {stage}"
    assert (
        flow.index("RESTAURANT")
        < flow.index("BUSINESS HEALTH")
        < flow.index("PROJECTED ROI")
        < flow.index("COMMERCIAL PROPOSAL")
    )
    assert "85/100" in flow, "one HIGH problem -> health score 85"


def test_report_service_writes_both_artifacts(
    report_context: ReportContext, tmp_path: Path
) -> None:
    service = ReportService(reports_dir=tmp_path)

    bundle = service.render(
        report_context.business_case,
        report_context.offer,
        report_context.validation,
        report_context.metrics,
    )

    assert bundle.markdown_path.is_file() and bundle.markdown_path.suffix == ".md"
    assert bundle.html_path.is_file() and bundle.html_path.suffix == ".html"
    assert bundle.markdown_path.stem == bundle.html_path.stem
