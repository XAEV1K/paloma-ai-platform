"""Bitrix payload normalizer: vendor JSON → internal contracts.

Isolates every Bitrix-ism (SCREAMING field names, PHONE as a list of
typed values, stage ids like ``C1:NEW``) in one file. A Kommo/HubSpot
normalizer would be a sibling class mapping into the same
:class:`NormalizedCrmEvent` — nothing downstream changes.
"""

from __future__ import annotations

from core.exceptions import DataSourceError
from core.logging import get_logger
from crm_sync.models import CrmContact, CrmDeal, NormalizedCrmEvent

logger = get_logger("crm_sync.normalizer")

_CONTACT_EVENTS = {"ONCRMCONTACTADD": "created", "ONCRMCONTACTUPDATE": "updated"}
_DEAL_EVENTS = {"ONCRMDEALADD": "created", "ONCRMDEALUPDATE": "updated"}


class BitrixNormalizer:
    """Maps Bitrix24 webhook payloads into normalized CRM events."""

    def normalize(self, payload: dict) -> NormalizedCrmEvent:
        event_name = str(payload.get("event", "")).upper()
        fields = (payload.get("data") or {}).get("FIELDS") or {}
        if not fields:
            raise DataSourceError(f"Bitrix payload without FIELDS: {event_name or 'unknown'}")

        if event_name in _CONTACT_EVENTS:
            return NormalizedCrmEvent(
                kind="contact",
                action=_CONTACT_EVENTS[event_name],
                contact=self._contact(fields),
            )
        if event_name in _DEAL_EVENTS:
            return NormalizedCrmEvent(
                kind="deal",
                action=_DEAL_EVENTS[event_name],
                deal=self._deal(fields),
            )
        raise DataSourceError(f"Unsupported Bitrix event: '{event_name}'")

    # ------------------------------------------------------------------
    @staticmethod
    def _contact(fields: dict) -> CrmContact:
        phones = fields.get("PHONE") or []
        phone = ""
        if isinstance(phones, list) and phones:
            phone = str(phones[0].get("VALUE", "")) if isinstance(phones[0], dict) else str(phones[0])
        name = " ".join(
            part for part in (fields.get("NAME", ""), fields.get("LAST_NAME", "")) if part
        ).strip()
        return CrmContact(
            external_id=str(fields.get("ID", "")),
            name=name or "Unknown contact",
            phone=phone,
            email=str(fields.get("EMAIL", "") or ""),
            restaurant_id=fields.get("UF_RESTAURANT_ID"),
            tags=[tag for tag in str(fields.get("UF_TAGS", "") or "").split(",") if tag],
        )

    @staticmethod
    def _deal(fields: dict) -> CrmDeal:
        try:
            amount = float(fields.get("OPPORTUNITY") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        return CrmDeal(
            external_id=str(fields.get("ID", "")),
            title=str(fields.get("TITLE", "Untitled deal")),
            stage=str(fields.get("STAGE_ID", "UNKNOWN")).split(":")[-1],
            amount=amount,
            contact_external_id=(
                str(fields["CONTACT_ID"]) if fields.get("CONTACT_ID") else None
            ),
            restaurant_id=fields.get("UF_RESTAURANT_ID"),
        )
