"""Metrics & tracing: collection, cost estimation, rendering."""

from __future__ import annotations

from dataclasses import dataclass

from metrics.collector import MetricsCollector
from metrics.report import render_summary, render_timeline
from metrics.tracer import SpanKind, Tracer


@dataclass
class FakeUsage:
    successful_requests: int = 3
    prompt_tokens: int = 1_000_000
    completion_tokens: int = 500_000
    total_tokens: int = 1_500_000


def test_collector_aggregates_usage() -> None:
    collector = MetricsCollector()
    collector.record_llm_usage(FakeUsage())
    collector.record_tool_call("roi_calculator", 0.02, ok=True)

    snapshot = collector.snapshot()

    assert snapshot.llm_requests == 3
    assert snapshot.total_tokens == 1_500_000
    assert snapshot.tool_call_count == 1
    assert snapshot.estimated_cost_usd is None, "no prices configured -> no estimate"


def test_cost_estimate_uses_configured_prices() -> None:
    collector = MetricsCollector(price_input_per_1m=1.0, price_output_per_1m=2.0)
    collector.record_llm_usage(FakeUsage())

    snapshot = collector.snapshot()

    # 1M in * $1/1M + 0.5M out * $2/1M = $2.00
    assert snapshot.estimated_cost_usd == 2.0


def test_tracer_builds_stage_and_tool_spans() -> None:
    tracer = Tracer()
    tracer.record_tool("restaurant_analytics", 0.1, 0.05)
    tracer.mark_stage_end("Architect stage")
    tracer.mark_stage_end("Developer stage")

    kinds = [span.kind for span in tracer.spans]

    assert kinds.count(SpanKind.STAGE) == 2
    assert kinds.count(SpanKind.TOOL) == 1


def test_rendering_smoke() -> None:
    collector = MetricsCollector()
    collector.record_llm_usage(FakeUsage())
    tracer = Tracer()
    tracer.record_tool("crm_insights", 0.0, 0.01)
    tracer.mark_stage_end("Architect stage")

    summary = render_summary("req-1", "R-001", collector.snapshot())
    timeline = render_timeline(tracer.spans)

    assert "Run finished" in summary and "R-001" in summary
    assert "Architect stage" in timeline and "crm_insights" in timeline
