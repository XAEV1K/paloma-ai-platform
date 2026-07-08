"""Customer memory: who the platform's customers are (fed by CRM sync)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from core.exceptions import DataSourceError
from core.logging import get_logger
from crm_sync.models import CrmContact, CrmDeal

logger = get_logger("services.customer_memory")


class CustomerRecord(BaseModel):
    """One customer as the platform remembers them."""

    external_id: str
    name: str
    phone: str = ""
    email: str = ""
    restaurant_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    deals: list[CrmDeal] = Field(default_factory=list)
    last_synced: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CustomerMemoryService:
    """JSON-backed customer store (a PostgreSQL table behind the same API)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def upsert_contact(self, contact: CrmContact) -> None:
        records = self._read_all()
        existing = records.get(contact.external_id)
        deals = existing.deals if existing else []
        records[contact.external_id] = CustomerRecord(
            external_id=contact.external_id,
            name=contact.name,
            phone=contact.phone,
            email=contact.email,
            restaurant_id=contact.restaurant_id,
            tags=contact.tags,
            deals=deals,
        )
        self._write_all(records)
        logger.info("Customer %s (%s) synced", contact.external_id, contact.name)

    def attach_deal(self, deal: CrmDeal) -> None:
        records = self._read_all()
        owner_id = deal.contact_external_id or f"orphan-{deal.external_id}"
        owner = records.get(owner_id) or CustomerRecord(
            external_id=owner_id, name="Unknown contact", restaurant_id=deal.restaurant_id
        )
        owner.deals = [d for d in owner.deals if d.external_id != deal.external_id] + [deal]
        owner.last_synced = datetime.now(timezone.utc)
        records[owner_id] = owner
        self._write_all(records)
        logger.info("Deal %s (%s, %s) attached to customer %s",
                    deal.external_id, deal.title, deal.stage, owner_id)

    def get(self, external_id: str) -> CustomerRecord | None:
        return self._read_all().get(external_id)

    def count(self) -> int:
        return len(self._read_all())

    # ------------------------------------------------------------------
    def _read_all(self) -> dict[str, CustomerRecord]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return {key: CustomerRecord(**value) for key, value in raw.items()}
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise DataSourceError(f"Corrupt customer memory {self._path}: {exc}") from exc

    def _write_all(self, records: dict[str, CustomerRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: record.model_dump(mode="json") for key, record in records.items()}
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
