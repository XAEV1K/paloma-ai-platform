"""Business Health Score: deterministic, explainable, bounded."""

from __future__ import annotations

from models.business_case import BusinessCase, BusinessProblem
from models.enums import ProblemCategory, Severity
from presentation.scoring import health_grade, health_score


def _case(*severities: Severity) -> BusinessCase:
    return BusinessCase(
        restaurant_id="T-001",
        headline="h",
        problems=[
            BusinessProblem(
                category=ProblemCategory.LOW_RETENTION,
                severity=severity,
                metric_name="retention_rate",
                metric_value=0.1,
                benchmark=0.25,
                summary="s",
            )
            for severity in severities
        ],
        priority_order=[ProblemCategory.LOW_RETENTION],
    )


def test_penalties_are_severity_weighted() -> None:
    assert health_score(_case(Severity.HIGH)) == 85
    assert health_score(_case(Severity.HIGH, Severity.MEDIUM)) == 77
    assert health_score(_case(Severity.CRITICAL, Severity.CRITICAL)) == 50


def test_score_is_clamped_to_zero() -> None:
    assert health_score(_case(*[Severity.CRITICAL] * 5)) == 0


def test_grades_cover_the_scale() -> None:
    assert health_grade(90) == "Excellent"
    assert health_grade(70) == "Good"
    assert health_grade(50) == "At Risk"
    assert health_grade(10) == "Critical"
