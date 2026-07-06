"""Composition root: the one place where the object graph is assembled.

Everything else in the codebase receives its dependencies through
constructors (pure DI, no service locator, no globals). Feature flags
are resolved here and only here — the rest of the system just receives
different collaborators:

- ``USE_SQLITE``          -> which MetricsRepository backend
- ``USE_CACHE``           -> whether the repository is wrapped in a TTL cache
- ``USE_BUSINESS_MEMORY`` -> whether memory service/tool exist at all
- ``USE_VALIDATOR_AGENT`` -> handled by the pipeline (engine always runs)
- ``LLM_PROVIDER``        -> which vendor builds the LLM handle
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings
from core.cache import InMemoryTTLCache
from core.logging import get_logger
from crew.agents import AgentFactory
from crew.crew import PalomaPipeline
from crew.prompts import PromptRepository
from crew.tasks import TaskFactory
from engines.recommendation_engine import RecommendationEngine, RecommendationThresholds
from engines.roi_engine import ROIEngine
from engines.validator_engine import ValidatorEngine
from events.bus import InMemoryEventBus
from events.events import DomainEvent
from events.handlers import AuditLogHandler
from llm.routing import LLMRouter
from models.offer import RoiAssumptions
from services.crm_service import CrmService
from services.knowledge_service import KnowledgeService
from services.memory_service import BusinessMemoryService, JsonMemoryRepository
from services.offer_service import InMemoryOfferRepository, OfferService
from services.report_service import ReportService
from services.restaurant_service import (
    CachedMetricsRepository,
    CsvMetricsRepository,
    MetricsRepository,
    RestaurantService,
    SqliteMetricsRepository,
)
from tools.registry import ToolRegistry

logger = get_logger("core.container")


@dataclass(frozen=True, slots=True)
class Container:
    """Fully wired application object graph."""

    settings: Settings
    llm_router: LLMRouter
    restaurant_service: RestaurantService
    knowledge_service: KnowledgeService
    offer_service: OfferService
    report_service: ReportService
    memory_service: BusinessMemoryService | None
    event_bus: InMemoryEventBus
    pipeline: PalomaPipeline

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        """Wire the whole platform bottom-up: data -> engines -> services -> tools -> crew."""
        logger.info("Assembling application container")

        # --- Data access (flag-driven backend + optional caching) --------
        repository: MetricsRepository
        if settings.use_sqlite:
            repository = SqliteMetricsRepository(settings.sqlite_db)
        else:
            repository = CsvMetricsRepository(settings.restaurants_csv)
        if settings.use_cache:
            repository = CachedMetricsRepository(
                repository, InMemoryTTLCache(settings.cache_ttl_seconds)
            )
        restaurant_service = RestaurantService(repository=repository)

        knowledge_service = KnowledgeService(
            modules_path=settings.modules_json,
            prices_path=settings.prices_json,
        )
        crm_service = CrmService()

        memory_service: BusinessMemoryService | None = None
        if settings.use_business_memory:
            memory_service = BusinessMemoryService(JsonMemoryRepository(settings.memory_json))

        # --- Deterministic engines ----------------------------------------
        # One thresholds instance shared by the rule engine AND the analytics
        # tool: the benchmarks agents quote are the thresholds rules fire on.
        thresholds = RecommendationThresholds()
        # ROI economics are operator-calibrated via .env (ROI_* variables).
        roi_engine = ROIEngine(
            horizon_months=settings.roi_horizon_months,
            assumptions=RoiAssumptions(
                gross_margin_pct=settings.roi_gross_margin_pct,
                attribution_pct=settings.roi_attribution_pct,
                ramp_up_months=settings.roi_ramp_up_months,
            ),
        )
        recommendation_engine = RecommendationEngine(thresholds=thresholds)
        validator_engine = ValidatorEngine()

        offer_service = OfferService(
            knowledge_service=knowledge_service,
            roi_engine=roi_engine,
            repository=InMemoryOfferRepository(),
        )
        report_service = ReportService(reports_dir=settings.reports_dir)

        # --- Events ---------------------------------------------------------
        event_bus = InMemoryEventBus()
        event_bus.subscribe(DomainEvent, AuditLogHandler())  # wildcard audit trail
        # Extension point: subscribe SlackNotificationHandler / analytics
        # sinks here — the pipeline never changes.

        # --- Tool plugins (discovered, then dependency-injected) -----------
        dependencies: dict[str, object] = {
            "restaurant_service": restaurant_service,
            "knowledge_service": knowledge_service,
            "crm_service": crm_service,
            "offer_service": offer_service,
            "roi_engine": roi_engine,
            "recommendation_engine": recommendation_engine,
            "validator_engine": validator_engine,
            "thresholds": thresholds,
        }
        if memory_service is not None:
            dependencies["memory_service"] = memory_service
        registry = ToolRegistry().discover()
        # business_memory is feature-flagged: skip it (not fail) when disabled.
        tools = registry.create_all(dependencies, optional=frozenset({"business_memory"}))

        # --- LLM & orchestration --------------------------------------------
        # The router resolves models per role and builds LLM handles lazily:
        # commands that never call a model never need a credential.
        llm_router = LLMRouter(settings)
        logger.info("LLM routing table: %s", llm_router.describe())
        prompts = PromptRepository(settings.prompts_dir, settings.prompt_version)
        pipeline = PalomaPipeline(
            settings=settings,
            agent_factory=AgentFactory(settings, router=llm_router, prompts=prompts),
            task_factory=TaskFactory(),
            tools=tools,
            offer_service=offer_service,
            report_service=report_service,
            knowledge_service=knowledge_service,
            restaurant_service=restaurant_service,
            validator_engine=validator_engine,
            thresholds=thresholds,
            memory_service=memory_service,
            event_bus=event_bus,
        )

        logger.info("Container ready")
        return cls(
            settings=settings,
            llm_router=llm_router,
            restaurant_service=restaurant_service,
            knowledge_service=knowledge_service,
            offer_service=offer_service,
            report_service=report_service,
            memory_service=memory_service,
            event_bus=event_bus,
            pipeline=pipeline,
        )
