"""HTML report renderer — the client-facing proposal.

Self-contained (inline CSS, zero external assets): the file can be
attached to an e-mail, opened offline, or dropped into a CRM. All
dynamic text is HTML-escaped; the only LLM-authored field (executive
summary) gets the same treatment as everything else.
"""

from __future__ import annotations

import html

from models.enums import Severity, ValidationStatus
from presentation import ReportContext
from presentation.scoring import health_grade, health_score

_SEVERITY_COLORS: dict[Severity, str] = {
    Severity.INFO: "#64748b",
    Severity.LOW: "#0ea5e9",
    Severity.MEDIUM: "#f59e0b",
    Severity.HIGH: "#ef4444",
    Severity.CRITICAL: "#b91c1c",
}

_STATUS_STYLES: dict[ValidationStatus, tuple[str, str]] = {
    ValidationStatus.PASSED: ("#16a34a", "VALIDATED ✓"),
    ValidationStatus.PASSED_WITH_WARNINGS: ("#f59e0b", "VALIDATED WITH WARNINGS"),
    ValidationStatus.FAILED: ("#dc2626", "VALIDATION FAILED"),
}


def _esc(value: object) -> str:
    return html.escape(str(value))


def render_html(context: ReportContext) -> str:
    """Render the full business proposal as a standalone HTML document."""
    case = context.business_case
    offer = context.offer
    validation = context.validation
    metrics = context.metrics
    currency = offer.line_items[0].currency.value if offer.line_items else ""
    status_color, status_label = _STATUS_STYLES[validation.status]
    assumptions = offer.roi.assumptions
    payback = (
        f"{offer.roi.payback_months:.1f} mo" if offer.roi.payback_months is not None else "n/a"
    )

    problem_rows = "\n".join(
        f"""      <tr>
        <td><span class="badge" style="background:{_SEVERITY_COLORS[p.severity]}">{_esc(p.severity.value)}</span></td>
        <td><code>{_esc(p.category.value)}</code></td>
        <td>{_esc(f"{p.metric_value:g}")} <span class="muted">vs {_esc(f"{p.benchmark:g}")}</span></td>
        <td>{_esc(p.summary)}</td>
      </tr>"""
        for p in case.problems
    )
    module_cards = "\n".join(
        f"""      <div class="module">
        <div class="module-head">
          <strong>{_esc(item.module_name)}</strong>
          <span class="muted">addresses {_esc(rec.addresses.value)}</span>
        </div>
        <p>{_esc(rec.rationale)}</p>
        <p class="price">Setup {item.setup_fee:,.0f} {_esc(item.currency.value)}
           · Monthly {item.monthly_fee:,.0f} {_esc(item.currency.value)}</p>
      </div>"""
        for rec, item in zip(offer.recommendations, offer.line_items, strict=False)
    )
    issue_items = (
        "\n".join(
            f"      <li><code>{_esc(i.rule_id)}</code> [{_esc(i.severity.value)}] {_esc(i.message)}</li>"
            for i in validation.issues
        )
        or "      <li>No issues found — all deterministic checks passed.</li>"
    )
    opportunity_items = (
        "\n".join(f"      <li>{_esc(item)}</li>" for item in case.growth_opportunities)
        or "      <li>—</li>"
    )

    score = health_score(case)
    grade = health_grade(score)
    score_color = "#16a34a" if score >= 65 else ("#f59e0b" if score >= 40 else "#dc2626")

    ramp = assumptions.ramp_up_months
    payback_label = (
        f"Month {offer.roi.payback_months:.0f}: investment recovered"
        if offer.roi.payback_months is not None
        else "Payback: n/a for this bundle"
    )
    timeline_steps = [
        ("Weeks 1–2", "Module installation, staff onboarding and data setup by Paloma365."),
        (
            f"Months 1–{ramp}" if ramp > 0 else "Month 1",
            "Adoption ramp: delivery zones, loyalty mechanics and kitchen flows tuned in production.",
        ),
        (payback_label.split(":")[0], payback_label.split(": ", 1)[-1]),
        (
            f"Month {offer.roi.horizon_months}",
            f"Projected outcome: {offer.roi.roi_pct:.0f}% ROI, "
            f"+{offer.roi.monthly_gain:,.0f} {currency} profit per month at steady state.",
        ),
    ]
    timeline_rows = "\n".join(
        f"""      <div class="tl-step">
        <div class="tl-when">{_esc(when)}</div>
        <div class="tl-what">{_esc(what)}</div>
      </div>"""
        for when, what in timeline_steps
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Paloma365 Proposal — {_esc(metrics.name)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; background: #f1f5f9; color: #0f172a; }}
  .page {{ max-width: 880px; margin: 32px auto; background: #fff; border-radius: 12px;
           box-shadow: 0 4px 24px rgba(15,23,42,.08); overflow: hidden; }}
  header {{ background: #0f172a; color: #f8fafc; padding: 28px 40px; }}
  header .brand {{ font-size: 13px; letter-spacing: 2px; color: #94a3b8; text-transform: uppercase; }}
  header h1 {{ margin: 6px 0 2px; font-size: 26px; }}
  header .sub {{ color: #cbd5e1; font-size: 14px; }}
  section {{ padding: 24px 40px; border-top: 1px solid #e2e8f0; }}
  h2 {{ font-size: 15px; letter-spacing: 1px; text-transform: uppercase; color: #475569; margin: 0 0 14px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  td, th {{ padding: 8px 10px; text-align: left; vertical-align: top; border-bottom: 1px solid #e2e8f0; }}
  .kpis {{ display: flex; gap: 14px; flex-wrap: wrap; }}
  .kpi {{ flex: 1 1 150px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }}
  .kpi .value {{ font-size: 22px; font-weight: 700; }}
  .kpi .label {{ font-size: 12px; color: #64748b; margin-top: 2px; }}
  .badge {{ color: #fff; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 999px; }}
  .muted {{ color: #64748b; font-size: 12px; }}
  .module {{ border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }}
  .module-head {{ display: flex; justify-content: space-between; gap: 12px; }}
  .module p {{ margin: 8px 0 0; font-size: 14px; }}
  .price {{ color: #334155; font-weight: 600; }}
  .verdict {{ display: inline-block; color: #fff; font-weight: 700; padding: 8px 18px;
              border-radius: 8px; background: {status_color}; }}
  .assumptions {{ font-size: 12px; color: #64748b; margin-top: 10px; }}
  .logo {{ display: inline-flex; align-items: center; gap: 10px; }}
  .logo-mark {{ width: 34px; height: 34px; border-radius: 9px; background: #38bdf8;
                color: #0f172a; font-weight: 800; font-size: 15px;
                display: flex; align-items: center; justify-content: center; }}
  .score-wrap {{ display: flex; align-items: center; gap: 18px; }}
  .score-num {{ font-size: 40px; font-weight: 800; color: {score_color}; }}
  .score-bar {{ flex: 1; height: 10px; background: #e2e8f0; border-radius: 999px; overflow: hidden; }}
  .score-fill {{ height: 100%; width: {score}%; background: {score_color}; }}
  .score-grade {{ font-weight: 700; color: {score_color}; }}
  .tl-step {{ display: flex; gap: 16px; padding: 10px 0; border-bottom: 1px dashed #e2e8f0; }}
  .tl-when {{ flex: 0 0 120px; font-weight: 700; color: #334155; font-size: 13px; }}
  .tl-what {{ font-size: 14px; }}
  footer {{ padding: 18px 40px; background: #f8fafc; color: #64748b; font-size: 12px; }}
  code {{ background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 12px; }}
</style>
</head>
<body>
<div class="page">
  <header>
    <div class="logo">
      <div class="logo-mark">P365</div>
      <div class="brand">Paloma365 · AI Decision Platform</div>
    </div>
    <h1>Business Proposal — {_esc(metrics.name)}</h1>
    <div class="sub">{_esc(metrics.city)} · {_esc(metrics.restaurant_id)} ·
      offer {_esc(offer.offer_id)} · {offer.created_at:%d %b %Y}</div>
  </header>

  <section>
    <h2>Business Health Score</h2>
    <div class="score-wrap">
      <div class="score-num">{score}</div>
      <div class="score-bar"><div class="score-fill"></div></div>
      <div class="score-grade">{_esc(grade)}</div>
    </div>
    <p class="muted">Deterministic score: 100 minus severity-weighted penalties
      for each diagnosed problem.</p>
  </section>

  <section>
    <h2>Restaurant Snapshot</h2>
    <div class="kpis">
      <div class="kpi"><div class="value">{metrics.monthly_revenue:,.0f}</div>
        <div class="label">Monthly revenue, {_esc(currency)}</div></div>
      <div class="kpi"><div class="value">{metrics.orders_per_month:,}</div>
        <div class="label">Orders / month</div></div>
      <div class="kpi"><div class="value">{metrics.avg_ticket:,.0f}</div>
        <div class="label">Average ticket, {_esc(currency)}</div></div>
      <div class="kpi"><div class="value">{metrics.retention_rate:.0%}</div>
        <div class="label">Guest retention</div></div>
    </div>
  </section>

  <section>
    <h2>Diagnosis</h2>
    <p><em>{_esc(case.headline)}</em></p>
    <table>
      <tr><th>Severity</th><th>Problem</th><th>Observed vs benchmark</th><th>Evidence</th></tr>
{problem_rows}
    </table>
  </section>

  <section>
    <h2>Growth Opportunities</h2>
    <ul>
{opportunity_items}
    </ul>
  </section>

  <section>
    <h2>Recommended Modules</h2>
{module_cards}
  </section>

  <section>
    <h2>Financial Projection · {offer.roi.horizon_months} months</h2>
    <div class="kpis">
      <div class="kpi"><div class="value">{offer.roi.roi_pct:.0f}%</div><div class="label">ROI</div></div>
      <div class="kpi"><div class="value">{payback}</div><div class="label">Payback</div></div>
      <div class="kpi"><div class="value">+{offer.roi.monthly_gain:,.0f}</div>
        <div class="label">Monthly profit gain, {_esc(currency)} (steady state)</div></div>
      <div class="kpi"><div class="value">{offer.roi.total_investment:,.0f}</div>
        <div class="label">Total investment, {_esc(currency)}</div></div>
    </div>
    <p class="assumptions">Conservative assumptions applied: {assumptions.gross_margin_pct:.0%} gross margin ·
      {assumptions.attribution_pct:.0%} uplift attribution · {assumptions.ramp_up_months}-month adoption ramp.
      Revenue growth projection: {offer.roi.revenue_increase_pct:.1f}% / month.</p>
  </section>

  <section>
    <h2>Implementation Timeline</h2>
{timeline_rows}
  </section>

  <section>
    <h2>Executive Summary</h2>
    <p>{_esc(offer.executive_summary)}</p>
  </section>

  <section>
    <h2>Quality Assurance</h2>
    <p><span class="verdict">{_esc(status_label)}</span></p>
    <p class="muted">Checked against {validation.rules_checked} deterministic business rules:</p>
    <ul>
{issue_items}
    </ul>
  </section>

  <footer>
    Generated by <strong>Paloma365 AI Decision Platform</strong> · offer {_esc(offer.offer_id)} ·
    {offer.created_at:%Y-%m-%d %H:%M UTC} · all figures computed deterministically — no model-generated numbers
  </footer>
</div>
</body>
</html>
"""
