"""Agent factory: builds the three specialised CrewAI agents.

Agents are deliberately dumb executors of a strict protocol: they read
tool output, decide, and emit typed contracts. Two things are injected
rather than owned:

- the **LLM handle** comes from the provider abstraction (``llm/``), so
  the factory is vendor-agnostic;
- the **backstories** come from the versioned :class:`PromptRepository`,
  so prompt iteration never touches Python code.
"""

from __future__ import annotations

from crewai import LLM, Agent

from crewai.tools import BaseTool

from config.settings import Settings
from core.logging import get_logger
from crew.prompts import PromptRepository

logger = get_logger("crew.agents")


class AgentFactory:
    """Creates configured agents; tools are injected by the composition root."""

    def __init__(self, settings: Settings, llm: LLM, prompts: PromptRepository) -> None:
        self._settings = settings
        self._llm = llm
        self._prompts = prompts
        logger.info("Agent factory ready (prompts %s)", prompts.version)

    def architect(self, tools: list[BaseTool]) -> Agent:
        """The diagnostician: data in, structured BusinessCase out."""
        return self._build(
            role="Restaurant Business Architect",
            goal=(
                "Diagnose the restaurant's business problems strictly from tool data "
                "and produce a structured BusinessCase."
            ),
            agent_name="architect",
            tools=tools,
        )

    def developer(self, tools: list[BaseTool]) -> Agent:
        """The solution engineer: BusinessCase in, persisted Offer out."""
        return self._build(
            role="Paloma365 Solution Developer",
            goal=(
                "Turn the BusinessCase into a minimal, ROI-backed Paloma365 module "
                "bundle and generate the commercial offer via tools."
            ),
            agent_name="developer",
            tools=tools,
        )

    def validator(self, tools: list[BaseTool]) -> Agent:
        """The quality gate: Offer in, machine-made ValidationReport out."""
        return self._build(
            role="Offer Quality Validator",
            goal=(
                "Run deterministic validation on the generated offer and relay the "
                "machine-made verdict without altering it."
            ),
            agent_name="validator",
            tools=tools,
        )

    def _build(self, role: str, goal: str, agent_name: str, tools: list[BaseTool]) -> Agent:
        logger.debug("Building agent '%s' with %d tool(s)", role, len(tools))
        return Agent(
            role=role,
            goal=goal,
            backstory=self._prompts.load(agent_name),
            tools=tools,
            llm=self._llm,
            allow_delegation=False,  # the pipeline is linear by design
            verbose=self._settings.agent_verbose,
            max_iter=self._settings.agent_max_iterations,
        )
