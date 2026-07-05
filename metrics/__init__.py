"""Run-level observability: token usage, cost, latency and tracing.

This package is deliberately framework-free (no CrewAI imports): it can
instrument anything. The pipeline feeds it, the CLI renders it.
"""

from metrics.collector import MetricsCollector, RunMetrics, ToolCallRecord
from metrics.report import render_summary, render_timeline
from metrics.tracer import Span, SpanKind, Tracer

__all__ = [
    "MetricsCollector",
    "RunMetrics",
    "Span",
    "SpanKind",
    "ToolCallRecord",
    "Tracer",
    "render_summary",
    "render_timeline",
]
