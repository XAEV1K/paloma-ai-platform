"""Business Health Score: one deterministic number for the whole diagnosis.

A weighted severity penalty over the diagnosed problems, clamped to
0–100. Pure function of the BusinessCase — no model output, same inputs,
same score, fully explainable in front of a client.
"""

from __future__ import annotations

from typing import Final

from models.business_case import BusinessCase
from models.enums import Severity

_PENALTIES: Final[dict[Severity, int]] = {
    Severity.CRITICAL: 25,
    Severity.HIGH: 15,
    Severity.MEDIUM: 8,
    Severity.LOW: 4,
    Severity.INFO: 1,
}


def health_score(case: BusinessCase) -> int:
    """0–100 score: 100 = no diagnosed problems."""
    penalty = sum(_PENALTIES[problem.severity] for problem in case.problems)
    return max(0, 100 - penalty)


def health_grade(score: int) -> str:
    """Human label for a score band (shown next to the number)."""
    if score >= 85:
        return "Excellent"
    if score >= 65:
        return "Good"
    if score >= 40:
        return "At Risk"
    return "Critical"
