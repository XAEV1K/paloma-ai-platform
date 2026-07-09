"""AI Runtime as a product: CRM sync, memory fabric, scheduler, health, boot."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from config.settings import Settings
from core.capabilities import Capability, CapabilityRegistry
from core.container import Container
from core.exceptions import ConfigurationError
from core.health import HealthStatus
from crm_sync.normalizer import BitrixNormalizer
from events.bus import InMemoryEventBus
from events.events import CrmRecordSynced, MaintenanceRunCompleted, PlatformReady
from scheduler.scheduler import Job, Scheduler


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.fixture()
def container(tmp_path: Path, monkeypatch) -> Container:
    # Redirect writable stores into tmp so tests never touch demo data.
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    monkeypatch.setattr(
        type(settings), "customers_path", property(lambda self: tmp_path / "customers.json")
    )
    monkeypatch.setattr(
        type(settings),
        "conversations_path",
        property(lambda self: tmp_path / "conversations.json"),
    )
    return Container.build(settings)


# --- CRM sync -----------------------------------------------------------------
def test_bitrix_contact_and_deal_are_normalized() -> None:
    normalizer = BitrixNormalizer()
    contact_event = normalizer.normalize(
        {
            "event": "ONCRMCONTACTADD",
            "data": {
                "FIELDS": {
                    "ID": "501",
                    "NAME": "Aigerim",
                    "LAST_NAME": "Bekova",
                    "PHONE": [{"VALUE": "+7 701 555 0101"}],
                    "UF_RESTAURANT_ID": "R-001",
                    "UF_TAGS": "owner,decision-maker",
                }
            },
        }
    )
    assert contact_event.kind == "contact" and contact_event.action == "created"
    assert contact_event.contact.name == "Aigerim Bekova"
    assert contact_event.contact.phone == "+7 701 555 0101"
    assert contact_event.contact.tags == ["owner", "decision-maker"]

    deal_event = normalizer.normalize(
        {
            "event": "ONCRMDEALUPDATE",
            "data": {
                "FIELDS": {
                    "ID": "9002",
                    "TITLE": "Bundle",
                    "STAGE_ID": "C1:PROPOSAL_SENT",
                    "OPPORTUNITY": "726000",
                    "CONTACT_ID": "501",
                }
            },
        }
    )
    assert deal_event.deal.stage == "PROPOSAL_SENT"
    assert deal_event.deal.amount == 726000.0
    assert deal_event.deal.contact_external_id == "501"


def test_crm_sync_lands_in_customer_memory_and_events(container: Container) -> None:
    events: list = []
    container.event_bus.subscribe(CrmRecordSynced, events.append)

    report = container.crm_sync_service.sync()

    assert report.contacts == 2 and report.deals == 2 and report.failed == 0
    assert len(events) == 4
    customer = container.customer_memory.get("501")
    assert customer is not None and customer.restaurant_id == "R-001"
    assert any(deal.stage == "PROPOSAL_SENT" for deal in customer.deals)


# --- memory fabric ---------------------------------------------------------------
def test_memory_fabric_describes_five_domains(container: Container) -> None:
    domains = {status.domain for status in container.memory_fabric.describe()}
    assert domains == {"Knowledge", "Conversation", "Business", "Restaurant", "Customer"}


# --- capabilities ------------------------------------------------------------------
def test_capabilities_resolve_to_tools(container: Container) -> None:
    registry = container.capabilities
    tools = registry.resolve((Capability.RESTAURANT_METRICS, Capability.KNOWLEDGE_SEARCH))
    assert [tool.name for tool in tools] == ["restaurant_analytics", "knowledge_search"]


def test_missing_capability_provider_fails_fast() -> None:
    registry = CapabilityRegistry(tools={})
    with pytest.raises(ConfigurationError, match="KNOWLEDGE_SEARCH"):
        registry.resolve((Capability.KNOWLEDGE_SEARCH,))


def test_plugin_tool_is_discovered_and_capability_mapped(container: Container) -> None:
    """The Plugin SDK example must be live on the platform."""
    assert "loyalty_insights" in container.capabilities.available()["LOYALTY_ANALYTICS"]
    result = container.capabilities.resolve((Capability.LOYALTY_ANALYTICS,))[0].run(
        restaurant_id="R-001"
    )
    assert '"repitch_advisable"' in result


# --- scheduler ------------------------------------------------------------------------
def test_job_schedules_and_dueness() -> None:
    ran: list[str] = []
    job = Job(name="t", schedule="every:6h", action=lambda: ran.append("x") or "ok")
    now = datetime(2026, 7, 7, 12, 0)

    assert job.is_due(now) is True  # never ran
    job.last_run = datetime(2026, 7, 7, 7, 0)
    assert job.is_due(now) is False
    job.last_run = datetime(2026, 7, 7, 5, 0)
    assert job.is_due(now) is True

    daily = Job(name="d", schedule="daily@02:00", action=lambda: "ok")
    daily.last_run = datetime(2026, 7, 6, 2, 0)
    assert daily.is_due(datetime(2026, 7, 7, 2, 30)) is True
    assert daily.next_run(datetime(2026, 7, 7, 3, 0)) == datetime(2026, 7, 8, 2, 0)


def test_invalid_schedule_is_rejected() -> None:
    with pytest.raises(ValueError, match="schedule"):
        Job(name="bad", schedule="sometimes", action=lambda: "ok")


def test_cycle_isolates_failing_jobs() -> None:
    bus = InMemoryEventBus()
    completed: list = []
    bus.subscribe(MaintenanceRunCompleted, completed.append)
    scheduler = Scheduler(bus)
    scheduler.register(Job(name="ok-job", schedule="every:1h", action=lambda: "fine"))

    def explode() -> str:
        raise RuntimeError("boom")

    scheduler.register(Job(name="bad-job", schedule="every:1h", action=explode))

    report = scheduler.run_all()

    assert report.ok == 1 and report.failed == 1
    assert completed and completed[0].jobs_failed == 1


def test_full_maintenance_cycle_runs_green(container: Container) -> None:
    report = container.scheduler.run_all()
    assert report.failed == 0
    assert {result.name for result in report.results} == {
        "crm-sync", "knowledge-reindex", "daily-analytics", "health-snapshot",
    }


# --- health & boot -------------------------------------------------------------------
def test_health_board_is_green_offline_except_llm(container: Container) -> None:
    results = {result.name: result for result in container.health_monitor.run()}
    assert results["Knowledge Index"].status is HealthStatus.OK
    assert results["Embedding Service"].status is HealthStatus.OK
    assert results["Retrieval Engine"].status is HealthStatus.OK
    assert results["CRM Connector"].status is HealthStatus.OK
    # No credentials in isolated settings -> LLM degraded, never FAIL.
    assert results["LLM Routing"].status in (HealthStatus.OK, HealthStatus.DEGRADED)


def test_boot_narrative_covers_every_subsystem(container: Container) -> None:
    ready: list = []
    container.event_bus.subscribe(PlatformReady, ready.append)

    boot = container.platform_runtime.boot()

    step_names = [step for step, _ in boot.steps]
    assert step_names == [
        "Restaurant data connected",
        "Knowledge synced",
        "CRM sync ready",
        "Memory fabric online",
        "AI services registered",
        "Voice ready",
        "Channels online",
        "Scheduler armed",
    ]
    channels_detail = dict(boot.steps)["Channels online"]
    assert "webchat" in channels_detail and "voice" in channels_detail
    assert ready and ready[0].services == ["support", "sales", "analyst", "technical"]
