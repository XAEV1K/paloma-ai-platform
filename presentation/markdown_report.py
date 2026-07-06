"""Markdown report renderer — the analyst-facing document.

Diffable, versionable, readable in any repo viewer. The client-facing
artifact is the HTML twin (:mod:`presentation.html_report`); both render
from the same :class:`ReportContext`, so they can never disagree.
"""

from __future__ import annotations

from presentation import ReportContext
from presentation.scoring import health_grade, health_score


def render_markdown(context: ReportContext) -> str:
    """Render the full business proposal as Markdown."""
    case = context.business_case
    offer = context.offer
    validation = context.validation
    metrics = context.metrics
    currency = offer.line_items[0].currency.value if offer.line_items else ""

    problems = "\n".join(
        f"| {p.category.value} | {p.severity.value} | `{p.metric_name}` "
        f"| {p.metric_value:g} | {p.benchmark:g} | {p.summary} |"
        for p in case.problems
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
    opportunities = "\n".join(f"- {item}" for item in case.growth_opportunities) or "- —"
    issues = (
        "\n".join(f"- `{i.rule_id}` [{i.severity.value}] {i.message}" for i in validation.issues)
        or "- No issues found."
    )
    payback = (
        f"{offer.roi.payback_months:.1f} months"
        if offer.roi.payback_months is not None
        else "n/a"
    )
    assumptions = offer.roi.assumptions

    score = health_score(case)

    return f"""# Business Proposal — {metrics.name} ({offer.restaurant_id})

**Prepared by:** Paloma365 AI Decision Platform
**Offer:** `{offer.offer_id}` · **Date:** {offer.created_at:%d %B %Y}

> {case.headline}

## Business Health Score

**{score}/100 — {health_grade(score)}**
(deterministic: 100 minus severity-weighted penalties per diagnosed problem)

## Restaurant Profile

| Metric | Value |
|---|---|
| Location | {metrics.city} |
| Monthly revenue | {metrics.monthly_revenue:,.0f} {currency} |
| Orders / month | {metrics.orders_per_month:,} |
| Average ticket | {metrics.avg_ticket:,.0f} {currency} |
| Retention rate | {metrics.retention_rate:.0%} |
| Delivery share | {metrics.delivery_share:.0%} |

## Diagnosis

| Problem | Severity | Metric | Value | Benchmark | Summary |
|---|---|---|---|---|---|
{problems}

## Growth Opportunities

{opportunities}

## Recommended Paloma365 Modules

{recommendations}

## Pricing

| Module | Setup fee | Monthly fee | Currency |
|---|---|---|---|
{lines}

## Financial Projection ({offer.roi.horizon_months} months)

- **Projected revenue growth:** {offer.roi.revenue_increase_pct:.1f}% / month
- **Projected monthly profit gain (steady state):** {offer.roi.monthly_gain:,.0f} {currency}
- **Total investment:** {offer.roi.total_investment:,.0f} {currency}
- **ROI:** {offer.roi.roi_pct:.1f}%
- **Payback:** {payback}
- **Assumptions:** {assumptions.gross_margin_pct:.0%} gross margin, \
{assumptions.attribution_pct:.0%} attribution, \
{assumptions.ramp_up_months}-month adoption ramp

## Executive Summary

{offer.executive_summary}

## Validation — {validation.status.value}

Checked against {validation.rules_checked} deterministic rules.

{issues}

## Next Steps

1. Review this proposal with the restaurant owner.
2. Confirm the module bundle and installation window.
3. Paloma365 onboarding team schedules setup (typical: 1–2 weeks).

---
*Offer `{offer.offer_id}` · generated {offer.created_at:%Y-%m-%d %H:%M UTC} · Paloma AI Platform*
"""
