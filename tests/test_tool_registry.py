"""Tool plugin system: discovery, DI instantiation, instrumentation."""

from __future__ import annotations

import pytest

from config.settings import Settings
from core.context import ExecutionContext, execution_scope
from core.exceptions import ConfigurationError
from engines.recommendation_engine import RecommendationEngine
from engines.roi_engine import ROIEngine
from engines.validator_engine import ValidatorEngine
from services.crm_service import CrmService
from services.knowledge_service import KnowledgeService
from services.memory_service import BusinessMemoryService, JsonMemoryRepository
from services.offer_service import InMemoryOfferRepository, OfferService
from services.restaurant_service import CsvMetricsRepository, RestaurantService
from tools.registry import ToolRegistry

EXPECTED_TOOLS = {
    "restaurant_analytics",
    "crm_insights",
    "module_recommendations",
    "paloma365_knowledge",
    "roi_calculator",
    "offer_generator",
    "offer_validation",
    "business_memory",
}


def _dependencies(settings: Settings, tmp_path) -> dict[str, object]:
    restaurant_service = RestaurantService(CsvMetricsRepository(settings.restaurants_csv))
    knowledge_service = KnowledgeService(settings.modules_json, settings.prices_json)
    roi_engine = ROIEngine()
    return {
        "restaurant_service": restaurant_service,
        "knowledge_service": knowledge_service,
        "crm_service": CrmService(),
        "offer_service": OfferService(knowledge_service, roi_engine, InMemoryOfferRepository()),
        "roi_engine": roi_engine,
        "recommendation_engine": RecommendationEngine(),
        "validator_engine": ValidatorEngine(),
        "memory_service": BusinessMemoryService(JsonMemoryRepository(tmp_path / "memory.json")),
    }


def test_discovery_finds_all_tools() -> None:
    registry = ToolRegistry().discover()
    assert EXPECTED_TOOLS <= registry.tool_names


def test_create_all_injects_dependencies(settings: Settings, tmp_path) -> None:
    tools = ToolRegistry().discover().create_all(_dependencies(settings, tmp_path))
    assert EXPECTED_TOOLS <= set(tools)

    result = tools["restaurant_analytics"].run(restaurant_id="R-001")
    assert '"restaurant_id": "R-001"' in result


def test_missing_dependency_fails_fast() -> None:
    with pytest.raises(ConfigurationError, match="restaurant_analytics"):
        ToolRegistry().discover().create_all({})


def test_optional_tool_is_skipped_when_deps_missing(settings: Settings, tmp_path) -> None:
    dependencies = _dependencies(settings, tmp_path)
    del dependencies["memory_service"]

    tools = ToolRegistry().discover().create_all(
        dependencies, optional=frozenset({"business_memory"})
    )

    assert "business_memory" not in tools
    assert "restaurant_analytics" in tools


def test_tool_calls_are_recorded_into_context(settings: Settings, tmp_path) -> None:
    tools = ToolRegistry().discover().create_all(_dependencies(settings, tmp_path))
    context = ExecutionContext.new("R-001")

    with execution_scope(context):
        tools["restaurant_analytics"].run(restaurant_id="R-001")
        tools["business_memory"].run(restaurant_id="R-001")

    snapshot = context.metrics.snapshot()
    assert snapshot.tool_call_count == 2
    assert {call.tool_name for call in snapshot.tool_calls} == {
        "restaurant_analytics",
        "business_memory",
    }
    assert len(context.tracer.spans) == 2
