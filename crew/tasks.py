"""Task factory: the pipeline stages and their output contracts.

Every task declares ``output_pydantic`` — CrewAI enforces that the agent's
final answer parses into the contract model, which is what makes the
agent-to-agent protocol *structural* rather than conversational.

Tasks also accept an optional ``callback`` (invoked with the TaskOutput
when the stage completes): the pipeline uses it for trace marks and
domain-event publishing without coupling tasks to those concerns.
"""

from __future__ import annotations

from typing import Any, Callable

from crewai import Agent, Task

from core.logging import get_logger
from models.business_case import BusinessCase
from models.offer import OfferRef
from models.validation import ValidationReport

logger = get_logger("crew.tasks")

#: Invoked by CrewAI with the completed TaskOutput.
TaskCallback = Callable[[Any], None]


class TaskFactory:
    """Creates the three pipeline tasks with strict typed outputs."""

    def analysis_task(self, agent: Agent, callback: TaskCallback | None = None) -> Task:
        """Architect stage: metrics -> BusinessCase."""
        return Task(
            description=(
                "Analyse restaurant '{restaurant_id}'. Use your tools to gather "
                "evidence (metrics + official benchmarks, CRM signals, engagement "
                "history), then diagnose the business problems and rank them by "
                "impact. Benchmarks MUST be the values from the 'benchmarks' block "
                "of restaurant_analytics — never invented."
            ),
            expected_output=(
                "Raw JSON only (no markdown fences): "
                '{"restaurant_id": str, "headline": str (max 200 chars), '
                '"problems": [1-5 items: {"category", "severity", "metric_name", '
                '"metric_value", "benchmark", "summary" (max 300 chars)}], '
                '"growth_opportunities": [max 3 short strings], '
                '"priority_order": [problem categories, highest impact first]}'
            ),
            agent=agent,
            output_pydantic=BusinessCase,
            callback=callback,
        )

    def development_task(
        self, agent: Agent, context: list[Task], callback: TaskCallback | None = None
    ) -> Task:
        """Developer stage: BusinessCase -> persisted Offer (returned as OfferRef)."""
        return Task(
            description=(
                "Using the BusinessCase from the previous task for restaurant "
                "'{restaurant_id}': check the engagement history, get rule-based "
                "module recommendations, verify each candidate in the knowledge "
                "base, compute the bundle's ROI, then create the offer with the "
                "offer_generator tool. Return only the OfferRef the tool gives you."
            ),
            expected_output=(
                "Raw JSON only (no markdown fences): the EXACT OfferRef returned by "
                'the offer_generator tool: {"offer_id": str, "restaurant_id": str, '
                '"module_codes": [codes], "headline": str (max 200 chars)}. '
                "Never fabricate an offer_id — if offer_generator failed, fix the "
                "input and call it again."
            ),
            agent=agent,
            context=context,
            output_pydantic=OfferRef,
            callback=callback,
        )

    def validation_task(
        self, agent: Agent, context: list[Task], callback: TaskCallback | None = None
    ) -> Task:
        """Validator stage: OfferRef -> ValidationReport."""
        return Task(
            description=(
                "Validate the offer referenced by the previous task's OfferRef using "
                "the offer_validation tool. Relay the machine-generated report "
                "verbatim as your final answer."
            ),
            expected_output=(
                "Raw JSON only (no markdown fences): the EXACT ValidationReport "
                "returned by the offer_validation tool, verbatim and unmodified."
            ),
            agent=agent,
            context=context,
            output_pydantic=ValidationReport,
            callback=callback,
        )
