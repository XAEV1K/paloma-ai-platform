"""Lightweight execution tracer (LangSmith-style, console-native).

Collects timestamped spans — pipeline stages and tool calls — relative to
a single run's start, so the CLI can render an execution timeline.

TODO: emit spans to OpenTelemetry when a collector is available; the
span model here maps 1:1 onto OTel spans by design.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, unique


@unique
class SpanKind(str, Enum):
    STAGE = "STAGE"  # one agent's slice of the pipeline
    TOOL = "TOOL"    # one tool invocation inside a stage


@dataclass(frozen=True, slots=True)
class Span:
    kind: SpanKind
    name: str
    start_offset_s: float  # relative to the run start
    duration_s: float


@dataclass(slots=True)
class Tracer:
    """Accumulates spans for one run. Not thread-safe by design (one run = one tracer)."""

    _t0: float = field(default_factory=time.monotonic)
    _spans: list[Span] = field(default_factory=list)
    _last_stage_mark: float = 0.0

    def now_offset(self) -> float:
        return time.monotonic() - self._t0

    def record_tool(self, name: str, start_offset_s: float, duration_s: float) -> None:
        self._spans.append(Span(SpanKind.TOOL, name, start_offset_s, duration_s))

    def mark_stage_end(self, stage_name: str) -> None:
        """Close a pipeline stage: spans from the previous mark until now.

        Stages run back-to-back in a sequential crew, so the previous
        stage's end is exactly this stage's start.
        """
        now = self.now_offset()
        self._spans.append(
            Span(SpanKind.STAGE, stage_name, self._last_stage_mark, now - self._last_stage_mark)
        )
        self._last_stage_mark = now

    @property
    def spans(self) -> tuple[Span, ...]:
        return tuple(sorted(self._spans, key=lambda s: (s.start_offset_s, s.kind is SpanKind.TOOL)))
