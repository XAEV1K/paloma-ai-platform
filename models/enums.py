"""Closed vocabularies of the domain.

``str``-based enums serialise cleanly to JSON, which matters because these
values cross the LLM boundary: an agent can only reference a module or a
problem category that exists here — anything else fails Pydantic validation
long before it reaches a customer-facing report.
"""

from __future__ import annotations

from enum import Enum, unique


class NormalizedStrEnum(str, Enum):
    """Case/format-tolerant string enum.

    LLMs routinely emit ``"high"`` instead of ``"HIGH"`` or
    ``"kitchen-display"`` instead of ``"KITCHEN_DISPLAY"`` — a production
    run died on exactly this. Values are normalised (upper-case, spaces
    and hyphens to underscores) before membership lookup, so the domain
    vocabulary stays closed while its *spelling* is forgiving.
    """

    @classmethod
    def _missing_(cls, value: object) -> "NormalizedStrEnum | None":
        if isinstance(value, str):
            normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
            for member in cls:
                if member.value == normalized:
                    return member
        return None


@unique
class ModuleCode(NormalizedStrEnum):
    """Sellable Paloma365 product modules (mirror of ``data/modules.json``)."""

    DELIVERY = "DELIVERY"
    CRM_LOYALTY = "CRM_LOYALTY"
    KITCHEN_DISPLAY = "KITCHEN_DISPLAY"
    QR_MENU = "QR_MENU"
    INVENTORY = "INVENTORY"
    ANALYTICS_PRO = "ANALYTICS_PRO"


@unique
class ProblemCategory(NormalizedStrEnum):
    """Business problems the Architect is allowed to diagnose."""

    LOW_DELIVERY_SHARE = "LOW_DELIVERY_SHARE"
    LOW_RETENTION = "LOW_RETENTION"
    SLOW_KITCHEN = "SLOW_KITCHEN"
    SLOW_DELIVERY = "SLOW_DELIVERY"
    LOW_AVG_TICKET = "LOW_AVG_TICKET"
    KITCHEN_OVERLOAD = "KITCHEN_OVERLOAD"
    STOCK_LOSSES = "STOCK_LOSSES"


@unique
class Severity(NormalizedStrEnum):
    """Severity scale shared by problems and validation issues."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@unique
class ValidationStatus(NormalizedStrEnum):
    """Terminal state of an offer validation run."""

    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"


@unique
class OfferOutcome(NormalizedStrEnum):
    """What ultimately happened to an offer — the business memory's currency."""

    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@unique
class Currency(NormalizedStrEnum):
    """ISO-4217 currencies supported by the pricing catalog."""

    KZT = "KZT"
    USD = "USD"
