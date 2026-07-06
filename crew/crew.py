"""Pipeline orchestrator: wires agents + tasks into a sequential crew.

``PalomaPipeline`` is the platform's single entry point for a full run.
It owns no business logic; it:

- opens an :class:`ExecutionContext` (request id, metrics, trace),
- runs the crew and publishes a domain event at every stage boundary,
- honours feature flags (the Validator *agent* is optional — the
  deterministic ``ValidatorEngine`` firewall is not),
- records the run into business memory,
- renders the report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pydantic import ValidationError

from crewai import Crew, Process, Task

from crewai.tools import BaseTool

from config.settings import Settings
from core.context import ExecutionContext, execution_scope
from core.exceptions import AgentContractError, ConfigurationError, OfferNotFoundError
from core.logging import get_logger
from crew.agents import AgentFactory
from crew.tasks import TaskFactory
from engines.validator_engine import ValidatorEngine
from events.bus import EventBus
from events.events import (
    BusinessCaseCreated,
    OfferCreated,
    ReportGenerated,
    ValidationCompleted,
)
from models.business_case import BusinessCase
from models.offer import Offer, OfferRef
from models.validation import ValidationReport
from services.knowledge_service import KnowledgeService
from services.memory_service import BusinessMemoryService
from services.offer_service import OfferService
from services.report_service import ReportService

logger = get_logger("crew.pipeline")

#: Tool belts per agent role (least privilege). Names refer to registry keys —
#: adding a tool to an agent is one string here, not an import.
ARCHITECT_TOOLS: tuple[str, ...] = ("restaurant_analytics", "crm_insights")
DEVELOPER_TOOLS: tuple[str, ...] = (
    "module_recommendations",
    "paloma365_knowledge",
    "roi_calculator",
    "offer_generator",
)
VALIDATOR_TOOLS: tuple[str, ...] = ("offer_validation",)
#: Added to Architect + Developer belts when USE_BUSINESS_MEMORY is on.
MEMORY_TOOL: str = "business_memory"


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Everything a single pipeline run produced, fully typed."""

    business_case: BusinessCase
    offer: Offer
    validation: ValidationReport
    report_path: Path
    execution: ExecutionContext


class PalomaPipeline:
    """Builds and runs the agent crew for one restaurant."""

    def __init__(
        self,
        settings: Settings,
        agent_factory: AgentFactory,
        task_factory: TaskFactory,
        tools: Mapping[str, BaseTool],
        offer_service: OfferService,
        report_service: ReportService,
        knowledge_service: KnowledgeService,
        validator_engine: ValidatorEngine,
        memory_service: BusinessMemoryService | None,
        event_bus: EventBus,
    ) -> None:
        self._settings = settings
        self._agent_factory = agent_factory
        self._task_factory = task_factory
        self._tools = tools
        self._offer_service = offer_service
        self._report_service = report_service
        self._knowledge_service = knowledge_service
        self._validator_engine = validator_engine
        self._memory_service = memory_service
        self._event_bus = event_bus

    def run(self, restaurant_id: str) -> PipelineResult:
        """Execute the full pipeline for one restaurant."""
        context = ExecutionContext.new(
            restaurant_id,
            price_input_per_1m=self._settings.llm_price_input_per_1m,
            price_output_per_1m=self._settings.llm_price_output_per_1m,
        )
        logger.info(
            "Pipeline started for restaurant %s (request %s)", restaurant_id, context.request_id
        )

        with execution_scope(context):
            crew = self._build_crew(context)
            try:
                crew_output = crew.kickoff(inputs={"restaurant_id": restaurant_id})
            except ValidationError as exc:
                # An agent's final answer did not parse into its contract
                # (e.g. an over-long field after a fabricated response).
                raise AgentContractError(
                    f"An agent's final answer violated its output contract "
                    f"({exc.error_count()} validation error(s) for {exc.title}). "
                    f"First error: {exc.errors()[0].get('msg', 'unknown')}"
                ) from exc

        context.metrics.record_llm_usage(getattr(crew_output, "token_usage", None))

        business_case = self._typed_output(crew_output.tasks_output[0], BusinessCase)
        offer_ref = self._typed_output(crew_output.tasks_output[1], OfferRef)

        # The full offer never travelled through the LLM — fetch it from Python.
        # This is also the anti-fabrication guard: an OfferRef pointing at an
        # offer that was never generated cannot pass this line.
        try:
            offer = self._offer_service.get_offer(offer_ref.offer_id)
        except OfferNotFoundError as exc:
            raise AgentContractError(
                f"Developer returned OfferRef '{offer_ref.offer_id}', but no such "
                f"offer exists in the repository — the reference was fabricated "
                f"instead of being produced by the offer_generator tool."
            ) from exc
        validation = self._resolve_validation(context, crew_output, offer)

        report_path = self._report_service.render(business_case, offer, validation)
        self._event_bus.publish(
            ReportGenerated(
                request_id=context.request_id,
                restaurant_id=restaurant_id,
                offer_id=offer.offer_id,
                report_path=str(report_path),
            )
        )

        if self._memory_service is not None:
            self._memory_service.record_run(business_case, offer)

        logger.info(
            "Pipeline finished for %s: validation=%s, report=%s",
            restaurant_id,
            validation.status.value,
            report_path.name,
        )
        return PipelineResult(
            business_case=business_case,
            offer=offer,
            validation=validation,
            report_path=report_path,
            execution=context,
        )

    # ------------------------------------------------------------------
    # crew assembly
    # ------------------------------------------------------------------
    def _build_crew(self, context: ExecutionContext) -> Crew:
        """Assemble agents with role-scoped tool belts and sequential tasks."""
        memory_extra = (
            (MEMORY_TOOL,)
            if self._settings.use_business_memory and MEMORY_TOOL in self._tools
            else ()
        )

        architect = self._agent_factory.architect(
            tools=self._belt(ARCHITECT_TOOLS + memory_extra)
        )
        developer = self._agent_factory.developer(
            tools=self._belt(DEVELOPER_TOOLS + memory_extra)
        )

        analysis = self._task_factory.analysis_task(
            architect, callback=self._on_analysis_done(context)
        )
        development = self._task_factory.development_task(
            developer, context=[analysis], callback=self._on_development_done(context)
        )

        agents = [architect, developer]
        tasks: list[Task] = [analysis, development]

        if self._settings.use_validator_agent:
            validator = self._agent_factory.validator(tools=self._belt(VALIDATOR_TOOLS))
            validation = self._task_factory.validation_task(
                validator, context=[development], callback=self._on_validation_done(context)
            )
            agents.append(validator)
            tasks.append(validation)
        else:
            logger.info("Validator agent disabled by flag; ValidatorEngine will run directly")

        return Crew(agents=agents, tasks=tasks, process=Process.sequential)

    def _belt(self, names: tuple[str, ...]) -> list[BaseTool]:
        """Resolve a tool belt from registry names, failing fast on typos."""
        missing = [name for name in names if name not in self._tools]
        if missing:
            raise ConfigurationError(f"Unknown tool(s) in agent belt: {missing}")
        return [self._tools[name] for name in names]

    # ------------------------------------------------------------------
    # stage callbacks: trace marks + event publishing
    # ------------------------------------------------------------------
    def _on_analysis_done(self, context: ExecutionContext):
        def callback(task_output: object) -> None:
            context.tracer.mark_stage_end("Architect stage")
            case = getattr(task_output, "pydantic", None)
            if isinstance(case, BusinessCase):
                self._event_bus.publish(
                    BusinessCaseCreated(
                        request_id=context.request_id,
                        restaurant_id=case.restaurant_id,
                        headline=case.headline,
                        problem_count=len(case.problems),
                    )
                )

        return callback

    def _on_development_done(self, context: ExecutionContext):
        def callback(task_output: object) -> None:
            context.tracer.mark_stage_end("Developer stage")
            ref = getattr(task_output, "pydantic", None)
            if isinstance(ref, OfferRef):
                offer = self._offer_service.get_offer(ref.offer_id)
                self._event_bus.publish(
                    OfferCreated(
                        request_id=context.request_id,
                        restaurant_id=ref.restaurant_id,
                        offer_id=ref.offer_id,
                        module_codes=list(ref.module_codes),
                        roi_pct=offer.roi.roi_pct,
                    )
                )

        return callback

    def _on_validation_done(self, context: ExecutionContext):
        def callback(task_output: object) -> None:
            context.tracer.mark_stage_end("Validator stage")
            report = getattr(task_output, "pydantic", None)
            if isinstance(report, ValidationReport):
                self._publish_validation(context, report)

        return callback

    def _publish_validation(self, context: ExecutionContext, report: ValidationReport) -> None:
        self._event_bus.publish(
            ValidationCompleted(
                request_id=context.request_id,
                offer_id=report.offer_id,
                status=report.status,
                issue_count=len(report.issues),
            )
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _resolve_validation(
        self, context: ExecutionContext, crew_output: object, offer: Offer
    ) -> ValidationReport:
        """Take the Validator agent's report, or run the engine directly.

        The deterministic firewall always runs: disabling the agent only
        removes the LLM narration around it, never the check itself.
        """
        if self._settings.use_validator_agent:
            tasks_output = crew_output.tasks_output  # type: ignore[attr-defined]
            return self._typed_output(tasks_output[2], ValidationReport)

        report = self._validator_engine.validate(offer, self._knowledge_service.knowledge_base)
        context.tracer.mark_stage_end("Validation (engine only)")
        self._publish_validation(context, report)
        return report

    @staticmethod
    def _typed_output[T](task_output: object, model: type[T]) -> T:
        """Extract the contract model from a CrewAI task output, fail loudly."""
        pydantic_payload = getattr(task_output, "pydantic", None)
        if not isinstance(pydantic_payload, model):
            raise AgentContractError(
                f"Pipeline contract violation: expected {model.__name__}, "
                f"got {type(pydantic_payload).__name__}"
            )
        return pydantic_payload
