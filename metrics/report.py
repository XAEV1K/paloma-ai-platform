"""Console rendering of run metrics: summary box + execution timeline."""

from __future__ import annotations

from metrics.collector import RunMetrics
from metrics.tracer import Span, SpanKind


def render_summary(request_id: str, restaurant_id: str, metrics: RunMetrics) -> str:
    """The 'Run finished' box shown at the end of every pipeline run."""
    cost = f"${metrics.estimated_cost_usd:.4f}" if metrics.estimated_cost_usd is not None else "n/a (set LLM_PRICE_* to estimate)"
    rows = [
        ("Request", request_id),
        ("Restaurant", restaurant_id),
        ("Duration", f"{metrics.duration_s:.2f}s"),
        ("LLM requests", str(metrics.llm_requests)),
        ("Tokens", f"{metrics.total_tokens:,} ({metrics.prompt_tokens:,} in / {metrics.completion_tokens:,} out)"),
        ("Tool calls", str(metrics.tool_call_count)),
        ("Est. cost", cost),
    ]
    body = [f"  {key:<13}: {value}" for key, value in rows]
    width = max(len(line) for line in body) + 2
    lines = ["┌" + "─" * width + "┐"]
    lines.append("│" + "  Run finished".ljust(width) + "│")
    lines.append("├" + "─" * width + "┤")
    lines.extend("│" + line.ljust(width) + "│" for line in body)
    lines.append("└" + "─" * width + "┘")
    return "\n".join(lines)


def render_timeline(spans: tuple[Span, ...]) -> str:
    """ASCII execution timeline: stages with their tool calls indented."""
    if not spans:
        return "Execution Timeline: (no spans recorded)"
    lines = ["Execution Timeline"]
    for span in spans:
        if span.kind is SpanKind.STAGE:
            lines.append(f"{span.start_offset_s:7.2f}s ├─ {span.name:<32} {span.duration_s:6.2f}s")
        else:
            lines.append(f"{span.start_offset_s:7.2f}s │    • {span.name:<28} {span.duration_s:6.2f}s")
    return "\n".join(lines)
