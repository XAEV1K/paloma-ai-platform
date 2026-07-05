"""ROI engine: deterministic financial projections.

Pure arithmetic over validated inputs — no LLM, no I/O, no randomness.
The uplift assumptions come from the managed catalog
(``ImpactAssumptions``), which keeps projections conservative, auditable
and reproducible: same inputs, same offer, every time.
"""

from __future__ import annotations

import math

from core.logging import get_logger
from models.knowledge import ModulePrice, PalomaModule
from models.offer import RoiProjection
from models.restaurant import RestaurantMetrics

logger = get_logger("engines.roi")

# Compounding uplifts from many modules can overpromise; cap the combined
# monthly revenue growth to keep every projection defensible in a sales call.
_MAX_COMBINED_GROWTH_PCT: float = 40.0


class ROIEngine:
    """Computes ROI, payback and revenue projections for a module bundle."""

    def __init__(self, horizon_months: int = 12) -> None:
        if horizon_months < 1:
            raise ValueError("horizon_months must be >= 1")
        self._horizon_months = horizon_months

    def calculate(
        self,
        metrics: RestaurantMetrics,
        modules: list[PalomaModule],
        prices: list[ModulePrice],
    ) -> RoiProjection:
        """Project the financial effect of installing ``modules``.

        Args:
            metrics: Current validated performance snapshot.
            modules: Catalog entries for the proposed bundle.
            prices: Matching catalog prices (same order not required).

        Returns:
            A frozen, fully deterministic :class:`RoiProjection`.
        """
        if not modules:
            raise ValueError("Cannot compute ROI for an empty module bundle")

        growth_pct = self._combined_growth_pct(modules)
        monthly_gain = metrics.monthly_revenue * growth_pct / 100.0

        total_investment = sum(
            price.setup_fee + price.monthly_fee * self._horizon_months for price in prices
        )
        horizon_gain = monthly_gain * self._horizon_months

        roi_pct = (
            (horizon_gain - total_investment) / total_investment * 100.0
            if total_investment > 0
            else 0.0
        )
        payback_months = total_investment / monthly_gain if monthly_gain > 0 else None

        projection = RoiProjection(
            horizon_months=self._horizon_months,
            total_investment=round(total_investment, 2),
            monthly_gain=round(monthly_gain, 2),
            revenue_increase_pct=round(growth_pct, 2),
            roi_pct=round(roi_pct, 2),
            payback_months=round(payback_months, 1) if payback_months is not None else None,
        )
        logger.info(
            "ROI computed for %s: roi=%.1f%%, payback=%s months",
            metrics.restaurant_id,
            projection.roi_pct,
            projection.payback_months,
        )
        return projection

    @staticmethod
    def _combined_growth_pct(modules: list[PalomaModule]) -> float:
        """Combine per-module uplifts multiplicatively, then apply a hard cap.

        Multiplicative composition avoids double counting: two modules each
        promising +10% yield +21%, not +20% naive... and never above the cap.
        """
        factor = math.prod(
            (1 + m.impact.order_growth_pct / 100.0) * (1 + m.impact.avg_ticket_growth_pct / 100.0)
            for m in modules
        )
        combined_pct = (factor - 1.0) * 100.0
        return min(combined_pct, _MAX_COMBINED_GROWTH_PCT)
