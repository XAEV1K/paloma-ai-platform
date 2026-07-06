"""Console decision funnel: the whole pipeline story in one screen.

Rendered by the CLI after a successful run — the audience sees the
product's value chain, not framework internals::

    Restaurant -> Analysis -> Health -> Problems -> Modules -> ROI
               -> Validation -> Reports

Colors are ANSI (VT mode is enabled by ``core.bootstrap``) and degrade
to plain text automatically when stdout is not a terminal (piped/CI) or
``NO_COLOR`` is set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from models.enums import ValidationStatus
from presentation import ReportContext
from presentation.scoring import health_grade, health_score

_WIDTH = 74

# --- ANSI helpers ----------------------------------------------------------
_BOLD, _DIM, _CYAN, _GREEN, _YELLOW, _RED = "1", "2", "36", "32", "33", "31"


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _paint(text: str, code: str) -> str:
    if not _color_enabled():
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


_ARROW = " " * 8 + _paint("│", _DIM) + "\n" + " " * 8 + _paint("▼", _DIM)

_STATUS_STYLE: dict[ValidationStatus, tuple[str, str]] = {
    ValidationStatus.PASSED: ("✅", _GREEN),
    ValidationStatus.PASSED_WITH_WARNINGS: ("⚠️", _YELLOW),
    ValidationStatus.FAILED: ("❌", _RED),
}

_SEVERITY_STYLE: dict[str, str] = {
    "CRITICAL": _RED,
    "HIGH": _RED,
    "MEDIUM": _YELLOW,
    "LOW": _CYAN,
    "INFO": _DIM,
}


def _stage(title: str) -> str:
    return _paint(f"  {title}", _BOLD)


def render_flow(
    context: ReportContext,
    request_id: str,
    markdown_path: Path,
    html_path: Path | None,
) -> str:
    """Render the end-to-end decision funnel for one restaurant."""
    metrics = context.metrics
    case = context.business_case
    offer = context.offer
    validation = context.validation
    currency = offer.line_items[0].currency.value if offer.line_items else ""
    score = health_score(case)
    score_color = _GREEN if score >= 65 else (_YELLOW if score >= 40 else _RED)

    problems = "\n".join(
        "    "
        + _paint(f"[{p.severity.value:<8}]", _SEVERITY_STYLE.get(p.severity.value, _DIM))
        + f" {p.category.value:<20} {p.metric_value:g} vs benchmark {p.benchmark:g}"
        for p in case.problems
    )
    opportunities = "\n".join(f"    • {item}" for item in case.growth_opportunities) or "    • —"
    modules = "\n".join(
        f"    {rec.priority}. {item.module_name:<28} — addresses {rec.addresses.value}"
        for rec, item in zip(offer.recommendations, offer.line_items, strict=False)
    )
    payback = (
        f"{offer.roi.payback_months:.1f} mo" if offer.roi.payback_months is not None else "n/a"
    )
    assumptions = offer.roi.assumptions
    status_icon, status_color = _STATUS_STYLE[validation.status]
    html_line = (
        f"    html     : {html_path}"
        if html_path is not None
        else "    html     : (rendering failed — see logs, Markdown is available)"
    )

    sections = [
        _paint("═" * _WIDTH, _CYAN),
        _paint(
            f"  PALOMA AI DECISION PIPELINE · {metrics.restaurant_id} · request {request_id}",
            _BOLD,
        ),
        _paint("═" * _WIDTH, _CYAN),
        "",
        _stage("RESTAURANT"),
        f"    {metrics.name} — {metrics.city}",
        f"    Revenue {metrics.monthly_revenue:,.0f} {currency}/mo · "
        f"{metrics.orders_per_month:,} orders · avg ticket {metrics.avg_ticket:,.0f}",
        _ARROW,
        _stage("BUSINESS ANALYSIS"),
        f'    "{case.headline}"',
        _ARROW,
        _stage("BUSINESS HEALTH"),
        "    " + _paint(f"{score}/100 — {health_grade(score)}", score_color),
        _ARROW,
        _stage(f"PROBLEMS DIAGNOSED ({len(case.problems)})"),
        problems,
        _ARROW,
        _stage(f"GROWTH OPPORTUNITIES ({len(case.growth_opportunities)})"),
        opportunities,
        _ARROW,
        _stage(f"RECOMMENDED MODULES ({len(offer.line_items)})"),
        modules,
        _ARROW,
        _stage(f"PROJECTED ROI ({offer.roi.horizon_months} months)"),
        f"    ROI {offer.roi.roi_pct:.1f}% · payback {payback} · "
        f"+{offer.roi.monthly_gain:,.0f} {currency} profit/mo (steady state)",
        f"    Investment {offer.roi.total_investment:,.0f} {currency} · assumptions: "
        f"margin {assumptions.gross_margin_pct:.0%}, "
        f"attribution {assumptions.attribution_pct:.0%}, "
        f"ramp {assumptions.ramp_up_months}m",
        _ARROW,
        _stage("VALIDATION")
        + ": "
        + _paint(
            f"{status_icon} {validation.status.value} "
            f"({validation.rules_checked} rules, {len(validation.issues)} issue(s))",
            status_color,
        ),
        _ARROW,
        _stage("COMMERCIAL PROPOSAL"),
        f"    Offer {offer.offer_id} · {len(offer.line_items)} module(s)",
        f"    markdown : {markdown_path}",
        html_line,
        "",
        _paint("═" * _WIDTH, _CYAN),
    ]
    return "\n".join(sections)
