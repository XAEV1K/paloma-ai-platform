"""Console decision funnel: the whole pipeline story in one screen.

Rendered by the CLI after a successful run — the audience sees the
product's value chain, not framework internals::

    Restaurant -> Analysis -> Problems -> Modules -> ROI -> Validation -> Report
"""

from __future__ import annotations

from pathlib import Path

from models.enums import ValidationStatus
from presentation import ReportContext

_WIDTH = 74
_ARROW = " " * 8 + "│\n" + " " * 8 + "▼"

_STATUS_ICONS = {
    ValidationStatus.PASSED: "✅",
    ValidationStatus.PASSED_WITH_WARNINGS: "⚠️",
    ValidationStatus.FAILED: "❌",
}


def render_flow(
    context: ReportContext,
    request_id: str,
    markdown_path: Path,
    html_path: Path,
) -> str:
    """Render the end-to-end decision funnel for one restaurant."""
    metrics = context.metrics
    case = context.business_case
    offer = context.offer
    validation = context.validation
    currency = offer.line_items[0].currency.value if offer.line_items else ""

    problems = "\n".join(
        f"    [{p.severity.value:<8}] {p.category.value:<20} "
        f"{p.metric_value:g} vs benchmark {p.benchmark:g}"
        for p in case.problems
    )
    modules = "\n".join(
        f"    {rec.priority}. {item.module_name:<28} — addresses {rec.addresses.value}"
        for rec, item in zip(offer.recommendations, offer.line_items, strict=False)
    )
    payback = (
        f"{offer.roi.payback_months:.1f} mo" if offer.roi.payback_months is not None else "n/a"
    )
    assumptions = offer.roi.assumptions

    sections = [
        "═" * _WIDTH,
        f"  PALOMA AI DECISION PIPELINE · {metrics.restaurant_id} · request {request_id}",
        "═" * _WIDTH,
        "",
        "  RESTAURANT",
        f"    {metrics.name} — {metrics.city}",
        f"    Revenue {metrics.monthly_revenue:,.0f} {currency}/mo · "
        f"{metrics.orders_per_month:,} orders · avg ticket {metrics.avg_ticket:,.0f}",
        _ARROW,
        "  BUSINESS ANALYSIS",
        f'    "{case.headline}"',
        _ARROW,
        f"  PROBLEMS DIAGNOSED ({len(case.problems)})",
        problems,
        _ARROW,
        f"  RECOMMENDED MODULES ({len(offer.line_items)})",
        modules,
        _ARROW,
        f"  PROJECTED ROI ({offer.roi.horizon_months} months)",
        f"    ROI {offer.roi.roi_pct:.1f}% · payback {payback} · "
        f"+{offer.roi.monthly_gain:,.0f} {currency} profit/mo (steady state)",
        f"    Investment {offer.roi.total_investment:,.0f} {currency} · assumptions: "
        f"margin {assumptions.gross_margin_pct:.0%}, "
        f"attribution {assumptions.attribution_pct:.0%}, "
        f"ramp {assumptions.ramp_up_months}m",
        _ARROW,
        f"  VALIDATION: {_STATUS_ICONS[validation.status]} {validation.status.value} "
        f"({validation.rules_checked} rules, {len(validation.issues)} issue(s))",
        _ARROW,
        "  REPORTS",
        f"    markdown : {markdown_path}",
        f"    html     : {html_path}",
        "",
        "═" * _WIDTH,
    ]
    return "\n".join(sections)
