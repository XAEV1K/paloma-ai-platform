"""Platform maintenance jobs: the nightly cycle, defined as data.

The classic 02:00 sequence — sync CRM, reindex knowledge (which refreshes
embeddings), generate daily analytics, snapshot health. Each job is a
plain callable over existing services; the scheduler owns timing and
fault isolation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.health import HealthMonitor
from core.logging import get_logger
from crm_sync.service import CrmSyncService
from rag.ingestion import IngestionService
from scheduler.scheduler import Job
from services.memory_fabric import MemoryFabric

logger = get_logger("scheduler.jobs")


def build_platform_jobs(
    crm_sync: CrmSyncService,
    ingestion: IngestionService,
    knowledge_dir: Path,
    memory_fabric: MemoryFabric,
    health_monitor: HealthMonitor,
    reports_dir: Path,
) -> list[Job]:
    """The platform's standard maintenance cycle."""

    def sync_crm() -> str:
        report = crm_sync.sync()
        return f"{report.contacts} contact(s), {report.deals} deal(s), {report.failed} failed"

    def reindex_knowledge() -> str:
        report = ingestion.ingest_directory(knowledge_dir)
        return (
            f"{report.files} file(s) -> {report.chunks} chunk(s), "
            f"embeddings refreshed in {report.duration_ms:.0f}ms"
        )

    def daily_analytics() -> str:
        path = _write_daily_summary(memory_fabric, reports_dir)
        return f"daily summary -> {path.name}"

    def health_snapshot() -> str:
        results = health_monitor.run()
        overall = HealthMonitor.overall(results)
        return f"platform {overall.value} ({len(results)} checks)"

    return [
        Job(name="crm-sync", schedule="every:6h", action=sync_crm),
        Job(name="knowledge-reindex", schedule="daily@02:00", action=reindex_knowledge),
        Job(name="daily-analytics", schedule="daily@03:00", action=daily_analytics),
        Job(name="health-snapshot", schedule="every:1h", action=health_snapshot),
    ]


def _write_daily_summary(memory_fabric: MemoryFabric, reports_dir: Path) -> Path:
    """Render the memory-fabric headline numbers into a dated report."""
    now = datetime.now(timezone.utc)
    lines = [
        f"# Platform Daily Summary — {now:%Y-%m-%d}",
        "",
        f"Generated {now:%Y-%m-%d %H:%M UTC} by the maintenance scheduler.",
        "",
        "## Memory Fabric",
        "",
    ]
    for domain in memory_fabric.describe():
        lines.append(f"- **{domain.domain} Memory** — {domain.detail}")
    lines += [
        "",
        "---",
        "*Paloma365 AI Operations Platform · automated maintenance report*",
        "",
    ]
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"daily-summary-{now:%Y%m%d}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Daily summary written -> %s", path.name)
    return path
