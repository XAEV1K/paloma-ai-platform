"""CRM sync service: connector → normalizer → events → customer memory."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.exceptions import DataSourceError
from core.logging import get_logger
from crm_sync.connector import CrmConnectorPort
from crm_sync.normalizer import BitrixNormalizer
from events.bus import EventBus
from events.events import CrmRecordSynced
from services.customer_memory import CustomerMemoryService

logger = get_logger("crm_sync.service")


@dataclass(frozen=True, slots=True)
class CrmSyncReport:
    """Observability artifact for one sync run."""

    contacts: int
    deals: int
    failed: int
    duration_ms: float
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.contacts + self.deals


class CrmSyncService:
    """Pulls pending CRM changes and lands them in memory + events."""

    def __init__(
        self,
        connector: CrmConnectorPort,
        normalizer: BitrixNormalizer,
        customer_memory: CustomerMemoryService,
        event_bus: EventBus,
    ) -> None:
        self._connector = connector
        self._normalizer = normalizer
        self._customer_memory = customer_memory
        self._event_bus = event_bus

    def sync(self) -> CrmSyncReport:
        """Process every pending payload; per-record faults never abort the run."""
        started = time.monotonic()
        contacts = deals = failed = 0
        errors: list[str] = []
        for payload in self._connector.fetch_pending():
            try:
                event = self._normalizer.normalize(payload)
            except DataSourceError as exc:
                failed += 1
                errors.append(str(exc))
                logger.warning("CRM payload rejected: %s", exc)
                continue
            if event.kind == "contact" and event.contact is not None:
                self._customer_memory.upsert_contact(event.contact)
                contacts += 1
                record_id = event.contact.external_id
            elif event.deal is not None:
                self._customer_memory.attach_deal(event.deal)
                deals += 1
                record_id = event.deal.external_id
            else:  # pragma: no cover — normalizer guarantees one side is set
                continue
            self._event_bus.publish(
                CrmRecordSynced(
                    request_id="crm-sync",
                    kind=event.kind,
                    action=event.action,
                    record_id=record_id,
                )
            )
        report = CrmSyncReport(
            contacts=contacts,
            deals=deals,
            failed=failed,
            duration_ms=round((time.monotonic() - started) * 1000, 1),
            errors=errors,
        )
        logger.info(
            "CRM sync: %d contact(s), %d deal(s), %d failed in %.0fms",
            report.contacts,
            report.deals,
            report.failed,
            report.duration_ms,
        )
        return report

    def handshake(self) -> str:
        return f"{self._connector.name}: {self._connector.handshake()}"
