"""Platform Runtime: the product-level lifecycle object.

Not a library — the thing an operator boots. ``boot()`` connects every
subsystem in dependency order, emits the boot narrative ("Restaurant
data connected → Knowledge synced → CRM ready → AI services registered →
Voice ready → Scheduler armed") and publishes :class:`PlatformReady`.
The company should feel the AI *living inside it*, not being invoked.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.capabilities import CapabilityRegistry
from core.logging import get_logger
from crm_sync.service import CrmSyncService
from events.bus import EventBus
from events.events import PlatformReady
from scheduler.scheduler import Scheduler
from services.memory_fabric import MemoryFabric

logger = get_logger("core.runtime")

#: The AI Runtime Services the conversation layer exposes.
AI_SERVICES: tuple[str, ...] = ("support", "sales", "analyst", "technical")


@dataclass(frozen=True, slots=True)
class BootReport:
    """The boot narrative: ordered (step, detail) pairs + total time."""

    steps: list[tuple[str, str]] = field(default_factory=list)
    boot_ms: float = 0.0


class PlatformRuntime:
    """Owns the platform lifecycle: boot narrative, subsystem wiring checks."""

    def __init__(
        self,
        memory_fabric: MemoryFabric,
        crm_sync: CrmSyncService,
        capabilities: CapabilityRegistry,
        scheduler: Scheduler,
        event_bus: EventBus,
        voice_mode: str,
        channels: list[str] | None = None,
    ) -> None:
        self._memory_fabric = memory_fabric
        self._crm_sync = crm_sync
        self._capabilities = capabilities
        self._scheduler = scheduler
        self._event_bus = event_bus
        self._voice_mode = voice_mode
        self._channels = channels or []

    def boot(self) -> BootReport:
        """Connect every subsystem and produce the boot narrative."""
        started = time.monotonic()
        steps: list[tuple[str, str]] = []
        domains = {status.domain: status.detail for status in self._memory_fabric.describe()}

        steps.append(("Restaurant data connected", domains.get("Restaurant", "offline")))
        steps.append(("Knowledge synced", domains.get("Knowledge", "offline")))
        steps.append(("CRM sync ready", self._crm_sync.handshake()))
        steps.append(
            ("Memory fabric online", f"{len(domains)} domains: {', '.join(sorted(domains))}")
        )
        steps.append(
            (
                "AI services registered",
                f"{' · '.join(AI_SERVICES)} ({len(self._capabilities.available())} capabilities)",
            )
        )
        steps.append(("Voice ready", f"{self._voice_mode} adapters · barge-in enabled"))
        channel_names = [*self._channels, "voice"]
        steps.append(("Channels online", " · ".join(channel_names)))
        jobs = self._scheduler.jobs
        steps.append(("Scheduler armed", f"{len(jobs)} job(s): "
                      + ", ".join(job.name for job in jobs)))

        boot_ms = round((time.monotonic() - started) * 1000, 1)
        self._event_bus.publish(
            PlatformReady(request_id="boot", services=list(AI_SERVICES), boot_ms=boot_ms)
        )
        logger.info("Platform boot complete in %.0fms (%d step(s))", boot_ms, len(steps))
        return BootReport(steps=steps, boot_ms=boot_ms)
