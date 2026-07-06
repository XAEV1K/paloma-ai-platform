"""ROI engine: deterministic, *credible* financial projections.

Pure arithmetic over validated inputs — no LLM, no I/O, no randomness.

The economics are deliberately conservative (audit finding: naive
revenue-as-benefit math produced a 4945% ROI, which the validator
rightly rejects and no CTO would believe):

1. Per-module uplifts compose multiplicatively and are capped.
2. Only the **gross margin** share of incremental revenue counts as gain.
3. Only a fraction of that gain is **attributed** to the modules.
4. Effects **ramp up linearly** over the first months, not instantly.

All four levers ship inside the projection (:class:`RoiAssumptions`)
so every number in a customer offer is auditable.
"""

from __future__ import annotations

import math

from core.logging import get_logger
from models.knowledge import ModulePrice, PalomaModule
from models.offer import RoiAssumptions, RoiProjection
from models.restaurant import RestaurantMetrics

logger = get_logger("engines.roi")

# Compounding uplifts from many modules can overpromise; cap the combined
# monthly revenue growth to keep every projection defensible in a sales call.
_MAX_COMBINED_GROWTH_PCT: float = 25.0


class ROIEngine:
    """Computes ROI, payback and revenue projections for a module bundle."""

    def __init__(
        self,
        horizon_months: int = 12,
        assumptions: RoiAssumptions | None = None,
    ) -> None:
        if horizon_months < 1:
            raise ValueError("horizon_months must be >= 1")
        self._horizon_months = horizon_months
        self._assumptions = assumptions or RoiAssumptions()

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
        incremental_revenue = metrics.monthly_revenue * growth_pct / 100.0
        steady_gain = (
            incremental_revenue
            * self._assumptions.gross_margin_pct
            * self._assumptions.attribution_pct
        )

        total_investment = sum(
            price.setup_fee + price.monthly_fee * self._horizon_months for price in prices
        )
        ramp_factors = [self._ramp_factor(month) for month in range(1, self._horizon_months + 1)]
        horizon_gain = steady_gain * sum(ramp_factors)

        roi_pct = (
            (horizon_gain - total_investment) / total_investment * 100.0
            if total_investment > 0
            else 0.0
        )
        payback_months = self._payback_months(steady_gain, ramp_factors, total_investment)

        projection = RoiProjection(
            horizon_months=self._horizon_months,
            total_investment=round(total_investment, 2),
            monthly_gain=round(steady_gain, 2),
            revenue_increase_pct=round(growth_pct, 2),
            roi_pct=round(roi_pct, 2),
            payback_months=round(payback_months, 1) if payback_months is not None else None,
            assumptions=self._assumptions,
        )
        logger.info(
            "ROI computed for %s: roi=%.1f%%, payback=%s months "
            "(margin=%.0f%%, attribution=%.0f%%, ramp=%dm)",
            metrics.restaurant_id,
            projection.roi_pct,
            projection.payback_months,
            self._assumptions.gross_margin_pct * 100,
            self._assumptions.attribution_pct * 100,
            self._assumptions.ramp_up_months,
        )
        return projection

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
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

    def _ramp_factor(self, month: int) -> float:
        """Linear adoption ramp: 0 -> 1 over ``ramp_up_months``."""
        ramp = self._assumptions.ramp_up_months
        if ramp <= 0:
            return 1.0
        return min(month / ramp, 1.0)

    def _payback_months(
        self,
        steady_gain: float,
        ramp_factors: list[float],
        total_investment: float,
    ) -> float | None:
        """Month (fractional) when cumulative ramped gain covers the investment.

        Beyond the horizon the steady-state gain is extrapolated (the
        validator flags a payback longer than the horizon as a warning).
        Returns ``None`` only when the gain is non-positive.
        """
        if steady_gain <= 0:
            return None
        cumulative = 0.0
        for month, factor in enumerate(ramp_factors, start=1):
            month_gain = steady_gain * factor
            if cumulative + month_gain >= total_investment:
                remainder = total_investment - cumulative
                return (month - 1) + remainder / month_gain
            cumulative += month_gain
        # Not recovered within the horizon: extrapolate at steady state.
        return len(ramp_factors) + (total_investment - cumulative) / steady_gain
