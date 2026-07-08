"""In-process job scheduler with daily-time and interval schedules.

Deliberately not Celery/APScheduler: the platform needs a *heartbeat*,
not a distributed task queue. Jobs are plain callables returning a
detail string; schedules are ``daily@HH:MM`` or ``every:<N>h``. The
scheduler computes due-ness (`tick`) and next-run times for the status
board, and any cycle can be forced with ``run_all`` (the
``--maintenance`` command). Moving to a real queue later replaces this
one file — job definitions stay untouched.

Job faults are isolated: one failing job is reported, the cycle
continues (maintenance must degrade, never abort).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta
from typing import Callable

from core.logging import get_logger
from events.bus import EventBus
from events.events import MaintenanceRunCompleted

logger = get_logger("scheduler")

_DAILY_RE = re.compile(r"^daily@(\d{2}):(\d{2})$")
_INTERVAL_RE = re.compile(r"^every:(\d+)h$")


@dataclass
class Job:
    """One scheduled maintenance job."""

    name: str
    schedule: str  # 'daily@02:00' | 'every:6h'
    action: Callable[[], str]  # returns a human-readable result detail
    last_run: datetime | None = None

    def __post_init__(self) -> None:
        if not (_DAILY_RE.match(self.schedule) or _INTERVAL_RE.match(self.schedule)):
            raise ValueError(
                f"Job '{self.name}': schedule '{self.schedule}' "
                f"(expected 'daily@HH:MM' or 'every:<N>h')"
            )

    def next_run(self, now: datetime) -> datetime:
        daily = _DAILY_RE.match(self.schedule)
        if daily:
            at = dtime(int(daily.group(1)), int(daily.group(2)))
            candidate = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate
        hours = int(_INTERVAL_RE.match(self.schedule).group(1))  # type: ignore[union-attr]
        base = self.last_run or now
        return base + timedelta(hours=hours)

    def is_due(self, now: datetime) -> bool:
        if self.last_run is None:
            return True  # never ran: due on first tick
        daily = _DAILY_RE.match(self.schedule)
        if daily:
            at = dtime(int(daily.group(1)), int(daily.group(2)))
            todays = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
            return todays <= now and self.last_run < todays
        hours = int(_INTERVAL_RE.match(self.schedule).group(1))  # type: ignore[union-attr]
        return now - self.last_run >= timedelta(hours=hours)


@dataclass(frozen=True, slots=True)
class JobResult:
    name: str
    ok: bool
    detail: str
    duration_ms: float


@dataclass(frozen=True, slots=True)
class MaintenanceReport:
    trigger: str
    results: list[JobResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def ok(self) -> int:
        return sum(1 for result in self.results if result.ok)

    @property
    def failed(self) -> int:
        return sum(1 for result in self.results if not result.ok)


class Scheduler:
    """Registers jobs, evaluates due-ness, executes cycles with isolation."""

    def __init__(self, event_bus: EventBus) -> None:
        self._jobs: list[Job] = []
        self._event_bus = event_bus

    def register(self, job: Job) -> None:
        if any(existing.name == job.name for existing in self._jobs):
            raise ValueError(f"Duplicate job name: '{job.name}'")
        self._jobs.append(job)
        logger.debug("Job registered: %s (%s)", job.name, job.schedule)

    @property
    def jobs(self) -> list[Job]:
        return list(self._jobs)

    def tick(self, now: datetime | None = None) -> MaintenanceReport:
        """Run everything that is due right now (call from a heartbeat loop)."""
        moment = now or datetime.now()
        due = [job for job in self._jobs if job.is_due(moment)]
        return self._run(due, trigger="scheduled", now=moment)

    def run_all(self, now: datetime | None = None) -> MaintenanceReport:
        """Force a full maintenance cycle (the --maintenance command)."""
        return self._run(list(self._jobs), trigger="manual", now=now or datetime.now())

    # ------------------------------------------------------------------
    def _run(self, jobs: list[Job], trigger: str, now: datetime) -> MaintenanceReport:
        cycle_started = time.monotonic()
        results: list[JobResult] = []
        for job in jobs:
            started = time.monotonic()
            try:
                detail = job.action()
                ok = True
            except Exception as exc:  # noqa: BLE001 — job isolation is the contract
                detail = f"{type(exc).__name__}: {exc}"
                ok = False
                logger.exception("Job '%s' failed", job.name)
            job.last_run = now
            duration = round((time.monotonic() - started) * 1000, 1)
            results.append(JobResult(name=job.name, ok=ok, detail=detail, duration_ms=duration))
            logger.info("Job %s: %s (%.0fms) — %s", job.name, "ok" if ok else "FAILED",
                        duration, detail[:120])
        report = MaintenanceReport(
            trigger=trigger,
            results=results,
            duration_ms=round((time.monotonic() - cycle_started) * 1000, 1),
        )
        if results:
            self._event_bus.publish(
                MaintenanceRunCompleted(
                    request_id="scheduler",
                    trigger=trigger,
                    jobs_ok=report.ok,
                    jobs_failed=report.failed,
                    duration_ms=report.duration_ms,
                )
            )
        return report
