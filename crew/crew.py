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

from crewai import Crew, Process, Task

from crewai.tools import BaseTool

from config.settings import Settings
from core.context import ExecutionContext, execution_scope
from core.exceptions import (
    AgentContractError,
    ConfigurationError,
    OfferNotFoundError,
    PalomaError,
    PipelineExecutionError,
)
from core.logging import get_logger
from core.structured_output import extract_contract
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
from models.restaurant import RestaurantMetrics
from models.validation import ValidationReport
from services.knowledge_service import KnowledgeService
from services.memory_service import BusinessMemoryService
from services.offer_service import OfferService
from services.report_service import ReportService
from services.restaurant_service import RestaurantService

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
    metrics: RestaurantMetrics
    report_path: Path
    html_report_path: Path | None  # None when the optional HTML artifact failed
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
        restaurant_service: RestaurantService,
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
        self._restaurant_service = restaurant_service
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
            except PalomaError:
                raise
            except Exception as exc:  # noqa: BLE001 — framework/provider boundary
                # CrewAI/providers raise arbitrary exception types (HTTP 4xx,
                # timeouts, framework faults). The CLI must show a clean
                # domain failure, never a third-party traceback.
                raise PipelineExecutionError(
                    f"Agent crew execution failed ({type(exc).__name__}): "
                    f"{str(exc)[:300]}"
                ) from exc

        context.metrics.record_llm_usage(getattr(crew_output, "token_usage", None))

        # Typed contracts are extracted by OUR deterministic parser — no
        # CrewAI converter, no schema round-trips to the provider.
        business_case = extract_contract(self._stage_raw(crew_output, 0, "Architect"), BusinessCase)
        offer_ref = extract_contract(self._stage_raw(crew_output, 1, "Developer"), OfferRef)

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

        # Served from cache (the agents already read it) — powers the report's
        # restaurant profile section without another data-source round trip.
        metrics = self._restaurant_service.get_metrics(restaurant_id)

        bundle = self._report_service.render(business_case, offer, validation, metrics)
        self._event_bus.publish(
            ReportGenerated(
                request_id=context.request_id,
                restaurant_id=restaurant_id,
                offer_id=offer.offer_id,
                report_path=str(bundle.markdown_path),
            )
        )

        if self._memory_service is not None:
            try:
                self._memory_service.record_run(business_case, offer)
            except Exception:  # noqa: BLE001 — memory is enrichment, not critical path
                logger.exception(
                    "Business memory update failed — continuing (history will miss this run)"
                )

        logger.info(
            "Pipeline finished for %s: validation=%s, report=%s",
            restaurant_id,
            validation.status.value,
            bundle.markdown_path.name,
        )
        return PipelineResult(
            business_case=business_case,
            offer=offer,
            validation=validation,
            metrics=metrics,
            report_path=bundle.markdown_path,
            html_report_path=bundle.html_path,
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
            try:
                case = extract_contract(str(getattr(task_output, "raw", "") or ""), BusinessCase)
            except AgentContractError:
                return  # the pipeline will surface the full error after kickoff
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
            try:
                ref = extract_contract(str(getattr(task_output, "raw", "") or ""), OfferRef)
                offer = self._offer_service.get_offer(ref.offer_id)
            except PalomaError:
                return  # fabricated/broken refs are handled after kickoff
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

        return callback

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _resolve_validation(
        self, context: ExecutionContext, crew_output: object, offer: Offer
    ) -> ValidationReport:
        """Produce the authoritative validation verdict.

        The verdict is ALWAYS the deterministic engine's output — an LLM
        relay must never be load-bearing (audit finding: a cost-tier model
        wrapped the report JSON in an extra key and aborted the run at the
        step with zero degrees of freedom). When the Validator agent ran,
        its narration is only checked for consistency and logged.
        """
        report = self._validator_engine.validate(offer, self._knowledge_service.knowledge_base)

        if self._settings.use_validator_agent:
            narration = self._validator_narration(crew_output)
            if report.status.value in narration and report.offer_id in narration:
                logger.info(
                    "Validator narration consistent with machine verdict (%s)",
                    report.status.value,
                )
            else:
                logger.warning(
                    "Validator narration diverged from the machine verdict — "
                    "using the engine report (this is why the relay is not load-bearing)"
                )
        else:
            context.tracer.mark_stage_end("Validation (engine only)")

        self._event_bus.publish(
            ValidationCompleted(
                request_id=context.request_id,
                offer_id=report.offer_id,
                status=report.status,
                issue_count=len(report.issues),
            )
        )
        return report

    @staticmethod
    def _stage_raw(crew_output: object, index: int, stage: str) -> str:
        """The raw final answer of a pipeline stage, or a clean contract error."""
        outputs = getattr(crew_output, "tasks_output", None) or []
        if len(outputs) <= index:
            raise AgentContractError(
                f"{stage} stage produced no output (crew returned "
                f"{len(outputs)} task output(s))."
            )
        return str(getattr(outputs[index], "raw", "") or "")

    def _validator_narration(self, crew_output: object) -> str:
        """The Validator agent's raw final answer, if the stage ran."""
        outputs = getattr(crew_output, "tasks_output", None) or []
        if len(outputs) >= 3:
            return str(getattr(outputs[2], "raw", "") or "")
        return ""
