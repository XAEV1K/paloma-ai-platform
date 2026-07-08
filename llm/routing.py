"""Role-based multi-model routing.

Different pipeline roles have different model requirements, and pinning
all agents to one model wastes either money or quality:

- **Architect** does the real reasoning (diagnosis, prioritisation) —
  it deserves the strongest model in the budget.
- **Developer** is a tool-calling loop over structured data — a fast,
  cheap, reliable function-caller is optimal.
- **Validator** relays one deterministic tool result — the cheapest,
  fastest model available (temperature 0: it must not be creative).

The router resolves each role to a model (``MODEL_<ROLE>`` env vars,
falling back to ``LLM_MODEL``), picks the vendor by prefix, and builds
CrewAI LLM handles **lazily** — commands that never call a model never
need a credential. ``validate()`` checks every distinct credential
up-front so a missing key fails before the first agent runs, not in the
middle of a demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Final

from crewai import LLM

from config.settings import Settings
from core.logging import get_logger
from llm.providers import BaseLLMProvider, provider_for_model

logger = get_logger("llm.routing")


@unique
class AgentRole(str, Enum):
    """Platform roles that can be routed to different models.

    Decision-pipeline roles (architect/developer/validator) and
    conversational roles (support/sales/technical) share one router:
    every model assignment in the platform lives in one table.
    """

    ARCHITECT = "architect"    # Business Analyst: the diagnosis is the product
    DEVELOPER = "developer"    # Report Generator: structured tool-calling
    VALIDATOR = "validator"    # QA relay: fully deterministic
    SUPPORT = "support"        # Support Agent: grounded, empathetic, fast
    SALES = "sales"            # Sales Agent: persuasive but grounded
    TECHNICAL = "technical"    # Technical Expert: precise, terse


#: Per-role temperature policy. Overridable globally via LLM_TEMPERATURE.
_ROLE_TEMPERATURES: Final[dict[AgentRole, float]] = {
    AgentRole.ARCHITECT: 0.2,  # reasoning benefits from a little breadth
    AgentRole.DEVELOPER: 0.1,  # structured tool calls: near-deterministic
    AgentRole.VALIDATOR: 0.0,  # relay a machine verdict: fully deterministic
    AgentRole.SUPPORT: 0.4,    # natural conversation, still grounded
    AgentRole.SALES: 0.5,      # a little persuasion latitude
    AgentRole.TECHNICAL: 0.2,  # precision over style
}


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    """The routing decision for one role, ready for logging and LLM build."""

    role: AgentRole
    model_id: str
    provider_name: str
    temperature: float


class LLMRouter:
    """Resolves roles to (model, provider, temperature) and builds LLMs lazily."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm_cache: dict[AgentRole, LLM] = {}

    # ------------------------------------------------------------------
    # resolution
    # ------------------------------------------------------------------
    def resolve(self, role: AgentRole) -> ResolvedModel:
        """Pure routing decision — no LLM constructed, no key required."""
        raw_model = self._configured_model(role)
        provider = self._provider_for(raw_model)
        return ResolvedModel(
            role=role,
            model_id=provider.qualify(raw_model),
            provider_name=provider.name,
            temperature=self._temperature_for(role),
        )

    def describe(self) -> dict[str, str]:
        """Human-readable routing table (logged at startup, shown in demos)."""
        return {
            resolved.role.value: (
                f"{resolved.model_id} "
                f"(provider={resolved.provider_name}, T={resolved.temperature})"
            )
            for resolved in (self.resolve(role) for role in AgentRole)
        }

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def validate(self) -> None:
        """Fail fast: check credentials for every distinct provider in use."""
        checked: set[str] = set()
        for role in AgentRole:
            provider = self._provider_for(self._configured_model(role))
            if provider.name not in checked:
                provider.validate()
                checked.add(provider.name)

    def llm_for(self, role: AgentRole) -> LLM:
        """Build (once) and return the CrewAI LLM handle for a role."""
        cached = self._llm_cache.get(role)
        if cached is not None:
            return cached

        resolved = self.resolve(role)
        provider = self._provider_for(self._configured_model(role))
        provider.validate()  # never construct a handle with a broken config
        logger.info(
            "LLM routed: %s -> %s (provider=%s, T=%s)",
            role.value,
            resolved.model_id,
            resolved.provider_name,
            resolved.temperature,
        )
        llm = LLM(
            model=resolved.model_id,
            temperature=resolved.temperature,
            api_key=provider.api_key(),
            base_url=provider.base_url(),
        )
        self._llm_cache[role] = llm
        return llm

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _configured_model(self, role: AgentRole) -> str:
        per_role: dict[AgentRole, str | None] = {
            AgentRole.ARCHITECT: self._settings.model_architect,
            AgentRole.DEVELOPER: self._settings.model_developer,
            AgentRole.VALIDATOR: self._settings.model_validator,
            AgentRole.SUPPORT: self._settings.model_support,
            AgentRole.SALES: self._settings.model_sales,
            AgentRole.TECHNICAL: self._settings.model_technical,
        }
        return per_role[role] or self._settings.llm_model

    def _provider_for(self, model_id: str) -> BaseLLMProvider:
        return provider_for_model(model_id, self._settings)

    def _temperature_for(self, role: AgentRole) -> float:
        if self._settings.llm_temperature is not None:
            return self._settings.llm_temperature
        return _ROLE_TEMPERATURES[role]
