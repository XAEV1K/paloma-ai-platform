"""Instrumented tool base + registration decorator.

Every platform tool derives from :class:`InstrumentedTool`, which gives
it observability for free: each invocation is timed, recorded into the
current :class:`ExecutionContext` (metrics + trace span) and error-logged
— without a line of boilerplate in the tool itself.

Tools self-register into the plugin registry via :func:`register_tool`,
so adding a capability to the platform is: drop a file into ``tools/``,
decorate the class, add its name to an agent's tool belt. Nothing else.
"""

from __future__ import annotations

import time
from abc import abstractmethod
from typing import Any

from pydantic import ConfigDict

from crewai.tools import BaseTool

from core.context import current_context
from core.logging import get_logger

logger = get_logger("tools.base")

#: Plugin metadata populated at import time by @register_tool.
#: Import-time class registration is process-wide metadata (like the import
#: system itself), not mutable application state — the DI rule still holds:
#: instances are created only by the composition root.
_REGISTERED_TOOLS: dict[str, type["InstrumentedTool"]] = {}


def register_tool(cls: type["InstrumentedTool"]) -> type["InstrumentedTool"]:
    """Class decorator: publish a tool class into the plugin registry."""
    tool_name = cls.model_fields["name"].default
    if not isinstance(tool_name, str) or not tool_name:
        raise TypeError(f"{cls.__name__} must declare a non-empty 'name' field default")
    if tool_name in _REGISTERED_TOOLS:
        raise ValueError(f"Duplicate tool name '{tool_name}' ({cls.__name__})")
    _REGISTERED_TOOLS[tool_name] = cls
    return cls


def registered_tools() -> dict[str, type["InstrumentedTool"]]:
    """Snapshot of everything registered so far (registry reads this)."""
    return dict(_REGISTERED_TOOLS)


class InstrumentedTool(BaseTool):
    """Base for all platform tools: validation, timing, tracing, metrics.

    Subclasses implement :meth:`_execute` (the actual behaviour);
    ``_run`` is final and owns two cross-cutting concerns:

    1. **Input validation.** CrewAI passes LLM-supplied arguments as raw
       parsed JSON — nested objects arrive as ``dict``s, not as the
       ``args_schema`` models. We re-validate the kwargs through the
       schema here, so every ``_execute`` receives fully typed Pydantic
       instances (audit finding: an offer tool crashed three times on
       ``'dict' object has no attribute 'module_code'`` without this).
    2. **Instrumentation.** Each invocation is timed and recorded into
       the current :class:`ExecutionContext` (metrics + trace span).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, *args: Any, **kwargs: Any) -> str:
        context = current_context()
        start_offset = context.tracer.now_offset() if context else 0.0
        started = time.monotonic()
        ok = False
        try:
            if kwargs and self.args_schema is not None:
                validated = self.args_schema.model_validate(kwargs)
                kwargs = {
                    field: getattr(validated, field)
                    for field in type(validated).model_fields
                }
            result = self._execute(*args, **kwargs)
            ok = True
            return result
        finally:
            duration = time.monotonic() - started
            if context is not None:
                context.metrics.record_tool_call(self.name, duration, ok)
                context.tracer.record_tool(self.name, start_offset, duration)
            if not ok:
                logger.warning("Tool '%s' failed after %.2fs", self.name, duration)

    @abstractmethod
    def _execute(self, *args: Any, **kwargs: Any) -> str:
        """The tool's actual behaviour. Return compact JSON for the LLM."""
