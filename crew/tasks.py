"""Task factory: the pipeline stages and their output contracts.

Contracts are enforced by the platform's own deterministic extractor
(:mod:`core.structured_output`), NOT by CrewAI's ``output_pydantic``
converter. The converter re-calls the LLM with a provider-specific JSON
schema when parsing gets hard — which failed in production (Anthropic
rejects ``maxItems``), burned retries and crashed the run. Tasks
therefore return raw text; the pipeline extracts and validates the
typed contract in pure Python.

Tasks accept an optional ``callback`` (invoked with the TaskOutput when
the stage completes): the pipeline uses it for trace marks and domain
events without coupling tasks to those concerns.
"""

from __future__ import annotations

from typing import Any, Callable

from crewai import Agent, Task

from core.logging import get_logger

logger = get_logger("crew.tasks")

#: Invoked by CrewAI with the completed TaskOutput.
TaskCallback = Callable[[Any], None]


class TaskFactory:
    """Creates the three pipeline tasks with strict, prompt-level contracts."""

    def analysis_task(self, agent: Agent, callback: TaskCallback | None = None) -> Task:
        """Architect stage: metrics -> BusinessCase JSON."""
        return Task(
            description=(
                "Analyse restaurant '{restaurant_id}'. Use your tools to gather "
                "evidence (metrics + official benchmarks, CRM signals, engagement "
                "history), then diagnose the business problems and rank them by "
                "impact. Benchmarks MUST be the values from the 'benchmarks' block "
                "of restaurant_analytics — never invented."
            ),
            expected_output=(
                "Raw JSON only (no markdown fences, no prose): "
                '{"restaurant_id": str, "headline": str (max 200 chars), '
                '"problems": [1-5 items: {"category", "severity", "metric_name", '
                '"metric_value", "benchmark", "summary" (max 300 chars)}], '
                '"growth_opportunities": [max 3 short strings], '
                '"priority_order": [problem categories, highest impact first]}. '
                "category MUST be one of: LOW_DELIVERY_SHARE, LOW_RETENTION, "
                "SLOW_KITCHEN, SLOW_DELIVERY, LOW_AVG_TICKET, KITCHEN_OVERLOAD, "
                "STOCK_LOSSES — no other category values exist. "
                "severity MUST be one of: LOW, MEDIUM, HIGH, CRITICAL. "
                "A finding that fits no category goes into growth_opportunities "
                "as text, never into problems."
            ),
            agent=agent,
            callback=callback,
        )

    def development_task(
        self, agent: Agent, context: list[Task], callback: TaskCallback | None = None
    ) -> Task:
        """Developer stage: BusinessCase -> persisted Offer (returned as OfferRef JSON)."""
        return Task(
            description=(
                "Using the BusinessCase from the previous task for restaurant "
                "'{restaurant_id}': check the engagement history, get rule-based "
                "module recommendations, verify each candidate in the knowledge "
                "base, compute the bundle's ROI, then create the offer with the "
                "offer_generator tool. Return only the OfferRef the tool gives you."
            ),
            expected_output=(
                "Raw JSON only (no markdown fences, no prose): the EXACT OfferRef "
                'returned by the offer_generator tool: {"offer_id": str, '
                '"restaurant_id": str, "module_codes": [codes], '
                '"headline": str (max 200 chars)}. Never fabricate an offer_id — '
                "if offer_generator failed, fix the input and call it again."
            ),
            agent=agent,
            context=context,
            callback=callback,
        )

    def validation_task(
        self, agent: Agent, context: list[Task], callback: TaskCallback | None = None
    ) -> Task:
        """Validator stage: OfferRef -> validation narration.

        The authoritative ValidationReport is recomputed deterministically
        by the pipeline (``ValidatorEngine``); the agent's relay is
        presentation only and can never abort the run.
        """
        return Task(
            description=(
                "Validate the offer referenced by the previous task's OfferRef using "
                "the offer_validation tool. Relay the machine-generated report "
                "verbatim as your final answer."
            ),
            expected_output=(
                "The exact JSON returned by the offer_validation tool, verbatim "
                "(no markdown fences, no wrapping keys, nothing added)."
            ),
            agent=agent,
            context=context,
            callback=callback,
        )
