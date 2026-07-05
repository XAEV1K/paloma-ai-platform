"""Architect-stage contracts.

The AI Architect's *entire* output is a :class:`BusinessCase` — structured
data, no prose walls. The :class:`DeveloperTask` is the hand-off contract
between the Architect and the Developer.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from models.enums import ModuleCode, ProblemCategory, Severity


class BusinessProblem(BaseModel):
    """A single diagnosed problem, backed by a concrete metric."""

    model_config = ConfigDict(frozen=True)

    category: ProblemCategory
    severity: Severity
    metric_name: str = Field(description="The RestaurantMetrics field that triggered this.")
    metric_value: float = Field(description="Observed value from the analytics tool.")
    benchmark: float = Field(description="Industry/target benchmark it was compared against.")
    summary: str = Field(max_length=300, description="One-sentence, evidence-based statement.")


class BusinessCase(BaseModel):
    """Structured diagnosis of a restaurant produced by the AI Architect."""

    restaurant_id: str
    headline: str = Field(max_length=200, description="One-line executive framing.")
    problems: list[BusinessProblem] = Field(min_length=1)
    growth_opportunities: list[str] = Field(
        default_factory=list,
        description="Short bullet points, each tied to a diagnosed problem.",
    )
    priority_order: list[ProblemCategory] = Field(
        description="Problem categories ordered by business impact, highest first."
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeveloperTask(BaseModel):
    """Work order handed from the Architect to the Developer agent.

    Kept intentionally small: the Developer re-reads raw data through
    tools, so this contract carries *intent*, not data.
    """

    model_config = ConfigDict(frozen=True)

    restaurant_id: str
    focus_problems: list[ProblemCategory] = Field(min_length=1)
    candidate_modules: list[ModuleCode] = Field(
        default_factory=list,
        description="Optional hint; the Developer verifies via RecommendationTool.",
    )
    notes: str = Field(default="", max_length=500)
