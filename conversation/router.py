"""Agent router: intent → agent specification.

The routing table is data, not code branches: each spec names the model
role, the versioned prompt, a display name and its grounding strategy
(RAG and/or business data). Adding a new conversational agent is one
table row + one prompt file.
"""

from __future__ import annotations

from dataclasses import dataclass

from conversation.intents import Intent
from llm.routing import AgentRole


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Everything the runtime needs to embody one agent for a turn."""

    role: AgentRole
    display_name: str
    prompt_name: str  # resolved through the versioned PromptRepository
    use_rag: bool  # ground the reply in the knowledge base
    use_business_data: bool  # inject restaurant metrics when context is known


_ROUTING_TABLE: dict[Intent, AgentSpec] = {
    Intent.SUPPORT: AgentSpec(
        role=AgentRole.SUPPORT,
        display_name="Support Agent",
        prompt_name="support",
        use_rag=True,
        use_business_data=False,
    ),
    Intent.SALES: AgentSpec(
        role=AgentRole.SALES,
        display_name="Sales Agent",
        prompt_name="sales",
        use_rag=True,
        use_business_data=True,
    ),
    Intent.ANALYTICS: AgentSpec(
        role=AgentRole.ARCHITECT,  # the Business Analyst reuses the strongest model
        display_name="Business Analyst",
        prompt_name="analyst_chat",
        use_rag=False,
        use_business_data=True,
    ),
    Intent.TECHNICAL: AgentSpec(
        role=AgentRole.TECHNICAL,
        display_name="Technical Expert",
        prompt_name="technical",
        use_rag=True,
        use_business_data=False,
    ),
    Intent.GENERAL: AgentSpec(
        role=AgentRole.SUPPORT,
        display_name="Support Agent",
        prompt_name="support",
        use_rag=True,
        use_business_data=False,
    ),
}


class AgentRouter:
    """Resolves the owning agent for an intent."""

    def route(self, intent: Intent) -> AgentSpec:
        return _ROUTING_TABLE[intent]
