"""CrewAI tool layer — the only bridge between agents and the Python core.

Each tool is a thin, single-responsibility plugin: it derives from
:class:`InstrumentedTool` (observability for free), self-registers via
``@register_tool``, validates LLM input through an ``args_schema``,
delegates to a service/engine, and returns compact JSON. No business
logic lives here (and none ever should).

Tools are discovered and instantiated by :class:`ToolRegistry` — the
composition root never imports individual tool classes.
"""

from tools.base import InstrumentedTool, register_tool
from tools.registry import ToolRegistry

__all__ = ["InstrumentedTool", "ToolRegistry", "register_tool"]
