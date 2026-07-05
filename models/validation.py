"""Validator-stage contracts.

The :class:`ValidationReport` is the platform's safety net: no offer
reaches a customer without passing the deterministic rule set in
``ValidatorEngine``. The report is machine-generated; the Validator agent
only interprets and relays it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from models.enums import Severity, ValidationStatus


class ValidationIssue(BaseModel):
    """A single finding produced by one validation rule."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(description="Stable rule identifier, e.g. 'ROI_BOUNDS'.")
    severity: Severity
    message: str = Field(max_length=300)


class ValidationReport(BaseModel):
    """Aggregated result of running every validation rule against an offer."""

    offer_id: str
    status: ValidationStatus
    issues: list[ValidationIssue] = Field(default_factory=list)
    rules_checked: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_approved(self) -> bool:
        """An offer may ship unless validation explicitly failed."""
        return self.status is not ValidationStatus.FAILED
