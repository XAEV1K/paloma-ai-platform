"""Execution context: one object that identifies and instruments a run.

Propagated via :mod:`contextvars` instead of threading it through every
function signature — the same technique used for request ids in
production web services, and it is async-safe out of the box. Tools and
services call :func:`current_context` to record metrics/spans without
knowing anything about the pipeline that invoked them.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from metrics.collector import MetricsCollector
from metrics.tracer import Tracer


@dataclass(slots=True)
class ExecutionContext:
    """Identity + instrumentation for a single pipeline run."""

    request_id: str
    restaurant_id: str
    started_at: datetime
    metrics: MetricsCollector = field(default_factory=MetricsCollector)
    tracer: Tracer = field(default_factory=Tracer)

    @classmethod
    def new(
        cls,
        restaurant_id: str,
        price_input_per_1m: float | None = None,
        price_output_per_1m: float | None = None,
    ) -> "ExecutionContext":
        return cls(
            request_id=uuid.uuid4().hex[:12],
            restaurant_id=restaurant_id,
            started_at=datetime.now(timezone.utc),
            metrics=MetricsCollector(
                price_input_per_1m=price_input_per_1m,
                price_output_per_1m=price_output_per_1m,
            ),
        )


_current_context: ContextVar[ExecutionContext | None] = ContextVar(
    "paloma_execution_context", default=None
)


def current_context() -> ExecutionContext | None:
    """The context of the run we are inside of, if any.

    Returns ``None`` outside a pipeline run (e.g. unit tests calling a
    tool directly) — instrumentation must degrade gracefully, never fail.
    """
    return _current_context.get()


@contextmanager
def execution_scope(context: ExecutionContext) -> Iterator[ExecutionContext]:
    """Bind ``context`` as the current one for the duration of the block."""
    token = _current_context.set(context)
    try:
        yield context
    finally:
        _current_context.reset(token)
