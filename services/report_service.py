"""Business report rendering.

Turns the pipeline's typed artifacts (BusinessCase + Offer +
ValidationReport) into a human-readable Markdown document. Rendering is
plain Python string templating — deterministic, testable, and free.

TODO: add a PDF renderer (weasyprint) behind the same interface for
customer-facing delivery.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.logging import get_logger
from models.business_case import BusinessCase
from models.offer import Offer
from models.validation import ValidationReport

logger = get_logger("services.report")


class ReportService:
    """Renders and persists the final business report."""

    def __init__(self, reports_dir: Path) -> None:
        self._reports_dir = reports_dir

    def render(
        self,
        business_case: BusinessCase,
        offer: Offer,
        validation: ValidationReport,
    ) -> Path:
        """Write the full Markdown report and return its path."""
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = self._reports_dir / f"{offer.restaurant_id}-{timestamp}.md"
        path.write_text(self._to_markdown(business_case, offer, validation), encoding="utf-8")
        logger.info("Report generated -> %s", path)
        return path

    @staticmethod
    def _to_markdown(
        business_case: BusinessCase,
        offer: Offer,
        validation: ValidationReport,
    ) -> str:
        problems = "\n".join(
            f"| {p.category.value} | {p.severity.value} | {p.metric_name} "
            f"| {p.metric_value:g} | {p.benchmark:g} | {p.summary} |"
            for p in business_case.problems
        )
        lines = "\n".join(
            f"| {item.module_name} | {item.setup_fee:,.0f} | {item.monthly_fee:,.0f} "
            f"| {item.currency.value} |"
            for item in offer.line_items
        )
        recommendations = "\n".join(
            f"{rec.priority}. **{rec.module_code.value}** — {rec.rationale}"
            for rec in offer.recommendations
        )
        issues = (
            "\n".join(f"- `{i.rule_id}` [{i.severity.value}] {i.message}" for i in validation.issues)
            or "- No issues found."
        )
        payback = (
            f"{offer.roi.payback_months:.1f} months"
            if offer.roi.payback_months is not None
            else "n/a"
        )
        return f"""# Business Proposal — {offer.restaurant_id}

> {business_case.headline}

## Diagnosis

| Problem | Severity | Metric | Value | Benchmark | Summary |
|---|---|---|---|---|---|
{problems}

## Recommended Paloma365 Modules

{recommendations}

## Pricing

| Module | Setup fee | Monthly fee | Currency |
|---|---|---|---|
{lines}

## Financial Projection ({offer.roi.horizon_months} months)

- **Projected revenue growth:** {offer.roi.revenue_increase_pct:.1f}% / month
- **Projected monthly profit gain (steady state):** {offer.roi.monthly_gain:,.0f}
- **Total investment:** {offer.roi.total_investment:,.0f}
- **ROI:** {offer.roi.roi_pct:.1f}%
- **Payback:** {payback}
- **Assumptions:** {offer.roi.assumptions.gross_margin_pct:.0%} gross margin, \
{offer.roi.assumptions.attribution_pct:.0%} attribution, \
{offer.roi.assumptions.ramp_up_months}-month adoption ramp

## Executive Summary

{offer.executive_summary}

## Validation — {validation.status.value}

{issues}

---
*Offer `{offer.offer_id}` · generated {offer.created_at:%Y-%m-%d %H:%M UTC} · Paloma AI Platform*
"""
