"""Rule-based module recommendation engine (an expert system, not an LLM).

Each rule is a small, independently testable strategy object implementing
:class:`RecommendationRule`. Adding a new business rule = adding one class
and registering it — the engine itself never changes (Open/Closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.logging import get_logger
from models.enums import ModuleCode, ProblemCategory
from models.offer import ModuleRecommendation
from models.restaurant import RestaurantMetrics

logger = get_logger("engines.recommendation")


@dataclass(frozen=True, slots=True)
class RecommendationThresholds:
    """Tunable business thresholds. Frozen: rules never mutate config.

    TODO: load per-market overrides (e.g. city-specific benchmarks) from
    the knowledge base once real Paloma365 benchmark data is available.
    """

    min_delivery_share: float = 0.15
    min_retention_rate: float = 0.25
    max_kitchen_time_min: float = 20.0
    max_kitchen_load: float = 0.85
    min_avg_ticket: float = 3500.0  # KZT


class RecommendationRule(Protocol):
    """Contract for a single deterministic recommendation rule."""

    def evaluate(
        self, metrics: RestaurantMetrics, thresholds: RecommendationThresholds
    ) -> ModuleRecommendation | None:
        """Return a recommendation if the rule fires, else ``None``."""
        ...


class LowDeliveryShareRule:
    """Delivery under-penetration -> DELIVERY module."""

    def evaluate(
        self, metrics: RestaurantMetrics, thresholds: RecommendationThresholds
    ) -> ModuleRecommendation | None:
        if metrics.delivery_share >= thresholds.min_delivery_share:
            return None
        return ModuleRecommendation(
            module_code=ModuleCode.DELIVERY,
            addresses=ProblemCategory.LOW_DELIVERY_SHARE,
            priority=1,
            rationale=(
                f"Delivery share {metrics.delivery_share:.0%} is below the "
                f"{thresholds.min_delivery_share:.0%} benchmark."
            ),
        )


class LowRetentionRule:
    """Weak guest retention -> CRM & Loyalty module."""

    def evaluate(
        self, metrics: RestaurantMetrics, thresholds: RecommendationThresholds
    ) -> ModuleRecommendation | None:
        if metrics.retention_rate >= thresholds.min_retention_rate:
            return None
        return ModuleRecommendation(
            module_code=ModuleCode.CRM_LOYALTY,
            addresses=ProblemCategory.LOW_RETENTION,
            priority=1,
            rationale=(
                f"Retention {metrics.retention_rate:.0%} is below the "
                f"{thresholds.min_retention_rate:.0%} benchmark."
            ),
        )


class SlowKitchenRule:
    """Slow ticket times -> Kitchen Display System."""

    def evaluate(
        self, metrics: RestaurantMetrics, thresholds: RecommendationThresholds
    ) -> ModuleRecommendation | None:
        if metrics.avg_kitchen_time_min <= thresholds.max_kitchen_time_min:
            return None
        return ModuleRecommendation(
            module_code=ModuleCode.KITCHEN_DISPLAY,
            addresses=ProblemCategory.SLOW_KITCHEN,
            priority=2,
            rationale=(
                f"Average kitchen time {metrics.avg_kitchen_time_min:.0f} min exceeds "
                f"the {thresholds.max_kitchen_time_min:.0f} min target."
            ),
        )


class KitchenOverloadRule:
    """Saturated kitchen -> Kitchen Display System (throughput)."""

    def evaluate(
        self, metrics: RestaurantMetrics, thresholds: RecommendationThresholds
    ) -> ModuleRecommendation | None:
        if metrics.kitchen_load <= thresholds.max_kitchen_load:
            return None
        return ModuleRecommendation(
            module_code=ModuleCode.KITCHEN_DISPLAY,
            addresses=ProblemCategory.KITCHEN_OVERLOAD,
            priority=2,
            rationale=(
                f"Peak kitchen load {metrics.kitchen_load:.0%} exceeds the safe "
                f"{thresholds.max_kitchen_load:.0%} utilisation ceiling."
            ),
        )


class LowAvgTicketRule:
    """Low average ticket -> QR Menu (upsell & photos drive ticket size)."""

    def evaluate(
        self, metrics: RestaurantMetrics, thresholds: RecommendationThresholds
    ) -> ModuleRecommendation | None:
        if metrics.avg_ticket >= thresholds.min_avg_ticket:
            return None
        return ModuleRecommendation(
            module_code=ModuleCode.QR_MENU,
            addresses=ProblemCategory.LOW_AVG_TICKET,
            priority=3,
            rationale=(
                f"Average ticket {metrics.avg_ticket:,.0f} KZT is below the "
                f"{thresholds.min_avg_ticket:,.0f} KZT benchmark."
            ),
        )


#: Default production rule set; order is irrelevant (priorities decide).
DEFAULT_RULES: tuple[RecommendationRule, ...] = (
    LowDeliveryShareRule(),
    LowRetentionRule(),
    SlowKitchenRule(),
    KitchenOverloadRule(),
    LowAvgTicketRule(),
)


class RecommendationEngine:
    """Runs every registered rule and aggregates unique recommendations."""

    def __init__(
        self,
        rules: tuple[RecommendationRule, ...] = DEFAULT_RULES,
        thresholds: RecommendationThresholds | None = None,
    ) -> None:
        self._rules = rules
        self._thresholds = thresholds or RecommendationThresholds()

    def recommend(self, metrics: RestaurantMetrics) -> list[ModuleRecommendation]:
        """Evaluate all rules; deduplicate by module keeping the best priority."""
        best_by_module: dict[ModuleCode, ModuleRecommendation] = {}
        for rule in self._rules:
            recommendation = rule.evaluate(metrics, self._thresholds)
            if recommendation is None:
                continue
            current = best_by_module.get(recommendation.module_code)
            if current is None or recommendation.priority < current.priority:
                best_by_module[recommendation.module_code] = recommendation

        recommendations = sorted(best_by_module.values(), key=lambda r: r.priority)
        logger.info(
            "Recommendation engine fired %d rule(s) for %s: %s",
            len(recommendations),
            metrics.restaurant_id,
            [r.module_code.value for r in recommendations],
        )
        return recommendations
