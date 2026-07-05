"""Recommendation engine: the rule set is the product's sales expertise."""

from __future__ import annotations

from engines.recommendation_engine import RecommendationEngine
from models.enums import ModuleCode
from models.restaurant import RestaurantMetrics


def test_struggling_restaurant_gets_recommendations(
    struggling_restaurant: RestaurantMetrics,
) -> None:
    recommendations = RecommendationEngine().recommend(struggling_restaurant)
    codes = {r.module_code for r in recommendations}

    assert ModuleCode.DELIVERY in codes  # delivery_share 5% < 15%
    assert ModuleCode.CRM_LOYALTY in codes  # retention 15% < 25%
    assert ModuleCode.KITCHEN_DISPLAY in codes  # kitchen 26 min > 20 min
    assert ModuleCode.QR_MENU in codes  # ticket 3000 < 3500


def test_healthy_restaurant_gets_nothing(healthy_restaurant: RestaurantMetrics) -> None:
    assert RecommendationEngine().recommend(healthy_restaurant) == []


def test_recommendations_are_deduplicated_and_sorted(
    struggling_restaurant: RestaurantMetrics,
) -> None:
    recommendations = RecommendationEngine().recommend(struggling_restaurant)

    codes = [r.module_code for r in recommendations]
    assert len(codes) == len(set(codes)), "one recommendation per module"
    priorities = [r.priority for r in recommendations]
    assert priorities == sorted(priorities), "highest priority first"


def test_every_recommendation_carries_evidence(
    struggling_restaurant: RestaurantMetrics,
) -> None:
    for recommendation in RecommendationEngine().recommend(struggling_restaurant):
        assert recommendation.rationale, "rules must explain themselves"
