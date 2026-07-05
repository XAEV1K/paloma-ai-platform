"""Metrics collector: counts what a pipeline run actually cost.

Collects tool calls, LLM token usage and wall-clock time, then freezes
into an immutable :class:`RunMetrics` snapshot for rendering/telemetry.

Cost is an *estimate* and only computed when the operator configures the
model's prices in ``.env`` (``LLM_PRICE_INPUT_PER_1M`` /
``LLM_PRICE_OUTPUT_PER_1M``). Prices change too often to hardcode.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.logging import get_logger

logger = get_logger("metrics.collector")


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """One completed tool invocation."""

    tool_name: str
    duration_s: float
    ok: bool


@dataclass(frozen=True, slots=True)
class RunMetrics:
    """Immutable end-of-run snapshot."""

    duration_s: float
    tool_calls: tuple[ToolCallRecord, ...]
    llm_requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None  # None when prices are not configured

    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)


@dataclass(slots=True)
class MetricsCollector:
    """Mutable accumulator scoped to a single pipeline run."""

    price_input_per_1m: float | None = None
    price_output_per_1m: float | None = None

    _started_at: float = field(default_factory=time.monotonic)
    _tool_calls: list[ToolCallRecord] = field(default_factory=list)
    _llm_requests: int = 0
    _prompt_tokens: int = 0
    _completion_tokens: int = 0
    _total_tokens: int = 0

    def record_tool_call(self, tool_name: str, duration_s: float, ok: bool) -> None:
        self._tool_calls.append(ToolCallRecord(tool_name, duration_s, ok))

    def record_llm_usage(self, usage: object) -> None:
        """Absorb CrewAI's usage metrics object (attribute names vary by version)."""
        self._llm_requests += int(getattr(usage, "successful_requests", 0) or 0)
        self._prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        self._completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        self._total_tokens += int(getattr(usage, "total_tokens", 0) or 0)

    def snapshot(self) -> RunMetrics:
        metrics = RunMetrics(
            duration_s=time.monotonic() - self._started_at,
            tool_calls=tuple(self._tool_calls),
            llm_requests=self._llm_requests,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            total_tokens=self._total_tokens,
            estimated_cost_usd=self._estimate_cost(),
        )
        logger.debug(
            "Run metrics: %.2fs, %d tool call(s), %d token(s)",
            metrics.duration_s,
            metrics.tool_call_count,
            metrics.total_tokens,
        )
        return metrics

    def _estimate_cost(self) -> float | None:
        if self.price_input_per_1m is None or self.price_output_per_1m is None:
            return None
        return (
            self._prompt_tokens / 1_000_000 * self.price_input_per_1m
            + self._completion_tokens / 1_000_000 * self.price_output_per_1m
        )
