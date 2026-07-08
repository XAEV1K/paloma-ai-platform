"""Capability Registry: what the platform can do, independent of how.

A *capability* is a product-level ability (Knowledge Search, CRM,
Notifications); a *tool* is one implementation of it. AI services are
granted capabilities, and the registry resolves them to whatever tools
currently provide them — so swapping or adding an implementation never
touches a service definition, and the platform can answer the product
question "what can this AI do?" without enumerating plumbing.
"""

from __future__ import annotations

from enum import Enum, unique
from typing import Mapping

from core.exceptions import ConfigurationError
from core.logging import get_logger

logger = get_logger("core.capabilities")


@unique
class Capability(str, Enum):
    RESTAURANT_METRICS = "RESTAURANT_METRICS"
    CRM_INSIGHTS = "CRM_INSIGHTS"
    BUSINESS_MEMORY = "BUSINESS_MEMORY"
    MODULE_CATALOG = "MODULE_CATALOG"
    RECOMMENDATIONS = "RECOMMENDATIONS"
    ROI_PROJECTION = "ROI_PROJECTION"
    OFFER_GENERATION = "OFFER_GENERATION"
    OFFER_VALIDATION = "OFFER_VALIDATION"
    KNOWLEDGE_SEARCH = "KNOWLEDGE_SEARCH"
    CONVERSATION_HISTORY = "CONVERSATION_HISTORY"
    NOTIFICATIONS = "NOTIFICATIONS"
    LOYALTY_ANALYTICS = "LOYALTY_ANALYTICS"


#: Capability -> tool names that provide it (plugins may extend a capability).
_PROVIDERS: dict[Capability, tuple[str, ...]] = {
    Capability.RESTAURANT_METRICS: ("restaurant_analytics",),
    Capability.CRM_INSIGHTS: ("crm_insights",),
    Capability.BUSINESS_MEMORY: ("business_memory",),
    Capability.MODULE_CATALOG: ("paloma365_knowledge",),
    Capability.RECOMMENDATIONS: ("module_recommendations",),
    Capability.ROI_PROJECTION: ("roi_calculator",),
    Capability.OFFER_GENERATION: ("offer_generator",),
    Capability.OFFER_VALIDATION: ("offer_validation",),
    Capability.KNOWLEDGE_SEARCH: ("knowledge_search",),
    Capability.CONVERSATION_HISTORY: ("conversation_history",),
    Capability.NOTIFICATIONS: ("send_notification",),
    Capability.LOYALTY_ANALYTICS: ("loyalty_insights",),
}


class CapabilityRegistry:
    """Resolves granted capabilities to available tool instances."""

    def __init__(self, tools: Mapping[str, object]) -> None:
        self._tools = tools

    def resolve(self, capabilities: tuple[Capability, ...]) -> list[object]:
        """Tool instances for a capability grant, in grant order.

        A capability with *no* available provider raises (a service was
        promised an ability the platform cannot deliver); a capability
        with some providers missing degrades to the available ones.
        """
        resolved: list[object] = []
        for capability in capabilities:
            providers = [
                self._tools[name]
                for name in _PROVIDERS.get(capability, ())
                if name in self._tools
            ]
            if not providers:
                raise ConfigurationError(
                    f"No tool provides capability {capability.value} "
                    f"(expected one of: {_PROVIDERS.get(capability, ())})"
                )
            resolved.extend(providers)
        return resolved

    def available(self) -> dict[str, list[str]]:
        """Capability -> provider tool names actually present (for /status)."""
        return {
            capability.value: [name for name in providers if name in self._tools]
            for capability, providers in _PROVIDERS.items()
            if any(name in self._tools for name in providers)
        }
