"""Health Monitor: liveness of every platform subsystem, with latency.

Each check is a named probe returning a detail string; the monitor times
it and classifies OK / DEGRADED / FAIL (probes signal degradation by
raising ``DegradedError``, hard faults by raising anything else). Checks
never take the platform down — a failing probe is a red row on the
status board, not an exception.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, unique
from typing import Callable

from core.logging import get_logger

logger = get_logger("core.health")


class DegradedError(RuntimeError):
    """Raised inside a probe to report a working-but-impaired subsystem."""


@unique
class HealthStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    name: str
    status: HealthStatus
    detail: str
    latency_ms: float


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    probe: Callable[[], str]  # returns detail; raises on problems


class HealthMonitor:
    """Runs registered probes and aggregates the platform status."""

    def __init__(self) -> None:
        self._checks: list[HealthCheck] = []

    def register(self, name: str, probe: Callable[[], str]) -> None:
        self._checks.append(HealthCheck(name=name, probe=probe))

    def run(self) -> list[HealthCheckResult]:
        results: list[HealthCheckResult] = []
        for check in self._checks:
            started = time.monotonic()
            try:
                detail = check.probe()
                status = HealthStatus.OK
            except DegradedError as exc:
                detail, status = str(exc), HealthStatus.DEGRADED
            except Exception as exc:  # noqa: BLE001 — a probe fault is a red row
                detail, status = f"{type(exc).__name__}: {exc}", HealthStatus.FAIL
                logger.warning("Health check '%s' failed: %s", check.name, detail)
            results.append(
                HealthCheckResult(
                    name=check.name,
                    status=status,
                    detail=detail,
                    latency_ms=round((time.monotonic() - started) * 1000, 1),
                )
            )
        return results

    @staticmethod
    def overall(results: list[HealthCheckResult]) -> HealthStatus:
        if any(result.status is HealthStatus.FAIL for result in results):
            return HealthStatus.FAIL
        if any(result.status is HealthStatus.DEGRADED for result in results):
            return HealthStatus.DEGRADED
        return HealthStatus.OK
