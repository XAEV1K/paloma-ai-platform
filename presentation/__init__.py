"""Presentation layer: turns typed pipeline artifacts into human-facing output.

Three renderers over one immutable :class:`ReportContext`:

- ``markdown_report`` — the analyst-facing document (versionable, diffable);
- ``html_report``     — the client-facing proposal (self-contained, styled);
- ``console``         — the decision-funnel view shown at the end of a run.

This package depends only on ``models`` — pure rendering, trivially
testable, no I/O (persistence stays in ``services.report_service``).
"""

from dataclasses import dataclass

from models.business_case import BusinessCase
from models.offer import Offer
from models.restaurant import RestaurantMetrics
from models.validation import ValidationReport


@dataclass(frozen=True, slots=True)
class ReportContext:
    """Everything a renderer needs about one completed pipeline run."""

    business_case: BusinessCase
    offer: Offer
    validation: ValidationReport
    metrics: RestaurantMetrics


__all__ = ["ReportContext"]
