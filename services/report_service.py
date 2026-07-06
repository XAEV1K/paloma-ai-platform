"""Business report persistence.

Rendering lives in the ``presentation`` package (pure functions over
:class:`ReportContext`); this service owns only the I/O: file naming,
directory management, writing both artifacts.

- ``<id>-<ts>.md``   — analyst-facing Markdown (diffable, repo-friendly)
- ``<id>-<ts>.html`` — client-facing proposal (self-contained, styled)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.logging import get_logger
from models.business_case import BusinessCase
from models.offer import Offer
from models.restaurant import RestaurantMetrics
from models.validation import ValidationReport
from presentation import ReportContext
from presentation.html_report import render_html
from presentation.markdown_report import render_markdown

logger = get_logger("services.report")


@dataclass(frozen=True, slots=True)
class ReportBundle:
    """Paths of every artifact produced for one pipeline run."""

    markdown_path: Path
    html_path: Path


class ReportService:
    """Renders and persists the final business report in both formats."""

    def __init__(self, reports_dir: Path) -> None:
        self._reports_dir = reports_dir

    def render(
        self,
        business_case: BusinessCase,
        offer: Offer,
        validation: ValidationReport,
        metrics: RestaurantMetrics,
    ) -> ReportBundle:
        """Write the Markdown + HTML reports and return their paths."""
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        context = ReportContext(
            business_case=business_case,
            offer=offer,
            validation=validation,
            metrics=metrics,
        )
        stem = f"{offer.restaurant_id}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"

        markdown_path = self._reports_dir / f"{stem}.md"
        markdown_path.write_text(render_markdown(context), encoding="utf-8")

        html_path = self._reports_dir / f"{stem}.html"
        html_path.write_text(render_html(context), encoding="utf-8")

        logger.info("Report generated -> %s (+ %s)", markdown_path, html_path.name)
        return ReportBundle(markdown_path=markdown_path, html_path=html_path)
