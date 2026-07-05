"""Offer validation engine — the anti-hallucination firewall.

Every offer passes a deterministic rule set before it can reach a client:
ROI sanity bounds, catalog price consistency, module existence, numeric
validity. Rules follow the same strategy-object pattern as the
recommendation engine, so compliance can extend the rule set without
touching the engine.
"""

from __future__ import annotations

import math
import uuid
from typing import Protocol

from core.logging import get_logger
from models.enums import Severity, ValidationStatus
from models.knowledge import KnowledgeBase
from models.offer import Offer
from models.validation import ValidationIssue, ValidationReport

logger = get_logger("engines.validator")


class ValidationRule(Protocol):
    """Contract for a single deterministic validation rule."""

    rule_id: str

    def check(self, offer: Offer, knowledge: KnowledgeBase) -> list[ValidationIssue]:
        """Return zero or more issues found in the offer."""
        ...


class RoiBoundsRule:
    """ROI must be positive and believable (no '900% ROI' slideware)."""

    rule_id = "ROI_BOUNDS"
    _MAX_ROI_PCT = 500.0

    def check(self, offer: Offer, knowledge: KnowledgeBase) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        roi = offer.roi.roi_pct
        if roi > self._MAX_ROI_PCT:
            issues.append(
                ValidationIssue(
                    rule_id=self.rule_id,
                    severity=Severity.CRITICAL,
                    message=f"ROI {roi:.1f}% exceeds the {self._MAX_ROI_PCT:.0f}% credibility cap.",
                )
            )
        if roi < 0:
            issues.append(
                ValidationIssue(
                    rule_id=self.rule_id,
                    severity=Severity.HIGH,
                    message=f"ROI is negative ({roi:.1f}%): the bundle destroys value.",
                )
            )
        return issues


class PaybackRule:
    """Payback must exist and fit inside the projection horizon."""

    rule_id = "PAYBACK"

    def check(self, offer: Offer, knowledge: KnowledgeBase) -> list[ValidationIssue]:
        payback = offer.roi.payback_months
        if payback is None:
            return [
                ValidationIssue(
                    rule_id=self.rule_id,
                    severity=Severity.CRITICAL,
                    message="No payback: projected monthly gain is non-positive.",
                )
            ]
        if payback > offer.roi.horizon_months:
            return [
                ValidationIssue(
                    rule_id=self.rule_id,
                    severity=Severity.MEDIUM,
                    message=(
                        f"Payback of {payback:.1f} months exceeds the "
                        f"{offer.roi.horizon_months}-month horizon."
                    ),
                )
            ]
        return []


class ModuleExistsRule:
    """Every offered module must exist in the managed catalog."""

    rule_id = "MODULE_EXISTS"

    def check(self, offer: Offer, knowledge: KnowledgeBase) -> list[ValidationIssue]:
        return [
            ValidationIssue(
                rule_id=self.rule_id,
                severity=Severity.CRITICAL,
                message=f"Module '{item.module_code.value}' is not in the catalog.",
            )
            for item in offer.line_items
            if item.module_code not in knowledge.modules
        ]


class PriceConsistencyRule:
    """Offer prices must match the pricing catalog exactly (no invented discounts)."""

    rule_id = "PRICE_CONSISTENCY"

    def check(self, offer: Offer, knowledge: KnowledgeBase) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for item in offer.line_items:
            if item.module_code not in knowledge.prices:
                continue  # ModuleExistsRule already reports this
            catalog = knowledge.prices[item.module_code]
            if (
                not math.isclose(item.setup_fee, catalog.setup_fee, rel_tol=1e-9)
                or not math.isclose(item.monthly_fee, catalog.monthly_fee, rel_tol=1e-9)
                or item.currency is not catalog.currency
            ):
                issues.append(
                    ValidationIssue(
                        rule_id=self.rule_id,
                        severity=Severity.CRITICAL,
                        message=(
                            f"Price for '{item.module_code.value}' deviates from the catalog "
                            f"({item.setup_fee}/{item.monthly_fee} {item.currency.value} vs "
                            f"{catalog.setup_fee}/{catalog.monthly_fee} {catalog.currency.value})."
                        ),
                    )
                )
        return issues


class FiniteNumbersRule:
    """All projection numbers must be finite floats (NaN/inf firewall)."""

    rule_id = "FINITE_NUMBERS"

    def check(self, offer: Offer, knowledge: KnowledgeBase) -> list[ValidationIssue]:
        candidates: dict[str, float | None] = {
            "total_investment": offer.roi.total_investment,
            "monthly_gain": offer.roi.monthly_gain,
            "revenue_increase_pct": offer.roi.revenue_increase_pct,
            "roi_pct": offer.roi.roi_pct,
            "payback_months": offer.roi.payback_months,
        }
        return [
            ValidationIssue(
                rule_id=self.rule_id,
                severity=Severity.CRITICAL,
                message=f"Projection field '{field}' is not a finite number ({value}).",
            )
            for field, value in candidates.items()
            if value is not None and not math.isfinite(value)
        ]


#: Default production rule set.
DEFAULT_RULES: tuple[ValidationRule, ...] = (
    RoiBoundsRule(),
    PaybackRule(),
    ModuleExistsRule(),
    PriceConsistencyRule(),
    FiniteNumbersRule(),
)

#: Severities that flip a report to FAILED (anything below is a warning).
_BLOCKING_SEVERITIES: frozenset[Severity] = frozenset({Severity.HIGH, Severity.CRITICAL})


class ValidatorEngine:
    """Runs the full rule set against an offer and aggregates a report."""

    def __init__(self, rules: tuple[ValidationRule, ...] = DEFAULT_RULES) -> None:
        self._rules = rules

    def validate(self, offer: Offer, knowledge: KnowledgeBase) -> ValidationReport:
        """Check ``offer`` against every rule; never raises on findings."""
        issues: list[ValidationIssue] = []
        for rule in self._rules:
            issues.extend(rule.check(offer, knowledge))

        status = self._resolve_status(issues)
        report = ValidationReport(
            offer_id=offer.offer_id or str(uuid.uuid4()),
            status=status,
            issues=issues,
            rules_checked=len(self._rules),
        )
        logger.info(
            "Validation %s for offer %s (%d issue(s) across %d rule(s))",
            status.value,
            offer.offer_id,
            len(issues),
            len(self._rules),
        )
        return report

    @staticmethod
    def _resolve_status(issues: list[ValidationIssue]) -> ValidationStatus:
        if any(issue.severity in _BLOCKING_SEVERITIES for issue in issues):
            return ValidationStatus.FAILED
        if issues:
            return ValidationStatus.PASSED_WITH_WARNINGS
        return ValidationStatus.PASSED
