"""Architect-stage contract.

The AI Architect's *entire* output is a :class:`BusinessCase` —
structured data, no prose walls, no timestamps (audit finding: given a
``created_at`` field, the model copied a date from the engagement
history; time is Python's job, so the contract has no time fields).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from models.enums import ProblemCategory, Severity


class BusinessProblem(BaseModel):
    """A single diagnosed problem, backed by a concrete metric."""

    model_config = ConfigDict(frozen=True)

    category: ProblemCategory
    severity: Severity
    metric_name: str = Field(description="The RestaurantMetrics field that triggered this.")
    metric_value: float = Field(description="Observed value from the analytics tool.")
    benchmark: float = Field(
        description="Official benchmark from the analytics tool's 'benchmarks' block."
    )
    summary: str = Field(max_length=300, description="One-sentence, evidence-based statement.")


class BusinessCase(BaseModel):
    """Structured diagnosis of a restaurant produced by the AI Architect."""

    restaurant_id: str
    headline: str = Field(max_length=200, description="One-line executive framing.")
    problems: list[BusinessProblem] = Field(min_length=1, max_length=5)
    growth_opportunities: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Short bullet points, each tied to a diagnosed problem.",
    )
    priority_order: list[ProblemCategory] = Field(
        description="Problem categories ordered by business impact, highest first."
    )
