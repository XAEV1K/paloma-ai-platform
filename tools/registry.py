"""Tool plugin registry: discovery + dependency-injected instantiation.

``discover()`` imports every module in the ``tools`` package, letting
``@register_tool`` decorators publish their classes. ``create_all()``
then instantiates each tool, injecting only the dependencies its
Pydantic fields declare — a tool asks for ``restaurant_service`` by
naming a field, the registry supplies it. New tools plug in with zero
container edits.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Mapping

from core.exceptions import ConfigurationError
from core.logging import get_logger
from tools.base import InstrumentedTool, registered_tools

logger = get_logger("tools.registry")

#: Fields owned by CrewAI's BaseTool itself — never treated as dependencies.
_NON_DEPENDENCY_FIELDS: frozenset[str] = frozenset(
    {"name", "description", "args_schema", "cache_function", "result_as_answer"}
)


class ToolRegistry:
    """Discovers tool plugins and builds them with injected dependencies."""

    def __init__(self, package: str = "tools") -> None:
        self._package = package
        self._classes: dict[str, type[InstrumentedTool]] = {}

    def discover(self) -> "ToolRegistry":
        """Import every module in the tools package to trigger registration."""
        package = importlib.import_module(self._package)
        for module_info in pkgutil.iter_modules(package.__path__):
            importlib.import_module(f"{self._package}.{module_info.name}")
        self._classes = registered_tools()
        logger.info(
            "Tool discovery complete: %d tool(s) registered (%s)",
            len(self._classes),
            ", ".join(sorted(self._classes)),
        )
        return self

    @property
    def tool_names(self) -> frozenset[str]:
        """Names of all discovered tool plugins."""
        return frozenset(self._classes)

    def create_all(
        self,
        dependencies: Mapping[str, object],
        optional: frozenset[str] = frozenset(),
    ) -> dict[str, InstrumentedTool]:
        """Instantiate every discovered tool, injecting declared dependencies.

        Args:
            dependencies: Name -> instance map provided by the composition
                root (e.g. ``{"restaurant_service": ..., "roi_engine": ...}``).
            optional: Tool names that may be skipped when their dependencies
                are absent (feature-flagged capabilities). Any other tool
                with missing dependencies is a wiring bug and raises.

        Raises:
            ConfigurationError: If a non-optional tool declares a dependency
                the composition root does not provide.
        """
        instances: dict[str, InstrumentedTool] = {}
        for tool_name, tool_cls in self._classes.items():
            required = [
                field
                for field, info in tool_cls.model_fields.items()
                if field not in _NON_DEPENDENCY_FIELDS and info.is_required()
            ]
            missing = [field for field in required if field not in dependencies]
            if missing and tool_name in optional:
                logger.info(
                    "Skipping optional tool '%s' (feature disabled, missing: %s)",
                    tool_name,
                    missing,
                )
                continue
            if missing:
                raise ConfigurationError(
                    f"Tool '{tool_name}' requires unprovided dependencies: {missing}"
                )
            kwargs = {field: dependencies[field] for field in required}
            instances[tool_name] = tool_cls(**kwargs)
        return instances
