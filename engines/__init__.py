"""Deterministic computation engines.

'LLM thinks. Python works.' — every number in the platform is produced
here: ROI math, rule-based recommendations and offer validation. Engines
are pure (no I/O, no framework imports) and therefore trivially unit-testable.
"""

from engines.recommendation_engine import RecommendationEngine, RecommendationThresholds
from engines.roi_engine import ROIEngine
from engines.validator_engine import ValidatorEngine

__all__ = [
    "ROIEngine",
    "RecommendationEngine",
    "RecommendationThresholds",
    "ValidatorEngine",
]
