"""Status board + boot narrative rendering (the 'AI Platform Status' view)."""

from __future__ import annotations

from core.health import HealthCheckResult, HealthMonitor, HealthStatus
from services.memory_fabric import MemoryDomainStatus

_STATUS_ICONS = {
    HealthStatus.OK: "✓",
    HealthStatus.DEGRADED: "◐",
    HealthStatus.FAIL: "✗",
}


def render_status_board(
    results: list[HealthCheckResult],
    memory_domains: list[MemoryDomainStatus],
    capabilities: dict[str, list[str]],
    scheduler_lines: list[str],
) -> str:
    overall = HealthMonitor.overall(results)
    lines = [
        "═" * 66,
        f"  PALOMA AI PLATFORM STATUS · {overall.value}",
        "═" * 66,
        "",
        "  SUBSYSTEMS",
    ]
    for result in results:
        icon = _STATUS_ICONS[result.status]
        lines.append(
            f"    {icon} {result.name:<22} {result.status.value:<9} "
            f"{result.latency_ms:6.0f}ms  {result.detail}"
        )
    lines += ["", "  MEMORY FABRIC"]
    for domain in memory_domains:
        lines.append(f"    · {domain.domain:<14} {domain.detail}")
    lines += ["", f"  CAPABILITIES ({len(capabilities)})"]
    lines.append("    " + " · ".join(sorted(capabilities)))
    lines += ["", "  SCHEDULER"]
    for line in scheduler_lines:
        lines.append(f"    {line}")
    lines += ["", "═" * 66]
    return "\n".join(lines)


def render_boot(steps: list[tuple[str, str]], boot_ms: float) -> str:
    lines = ["⏻ Paloma AI Runtime · booting", ""]
    for step, detail in steps:
        lines.append(f"  ✓ {step:<28} {detail}")
    lines.append("")
    lines.append(f"  Platform ready in {boot_ms / 1000:.2f}s")
    return "\n".join(lines)
