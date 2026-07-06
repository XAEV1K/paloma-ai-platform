"""Strict data contracts shared by agents, tools, engines and services.

These models ARE the protocol of the platform: agents never exchange free
text, they exchange instances of these schemas. Keep this package free of
I/O and framework imports — pure Pydantic only.
"""

from models.business_case import BusinessCase, BusinessProblem
from models.crm import CrmSnapshot
from models.enums import (
    Currency,
    ModuleCode,
    OfferOutcome,
    ProblemCategory,
    Severity,
    ValidationStatus,
)
from models.knowledge import KnowledgeBase, ModulePrice, PalomaModule
from models.memory import PastAnalysis, PastOffer, RestaurantHistory
from models.offer import (
    ModuleRecommendation,
    Offer,
    OfferLineItem,
    OfferRef,
    RoiAssumptions,
    RoiProjection,
)
from models.restaurant import RestaurantMetrics
from models.validation import ValidationIssue, ValidationReport

__all__ = [
    "BusinessCase",
    "BusinessProblem",
    "CrmSnapshot",
    "Currency",
    "KnowledgeBase",
    "ModuleCode",
    "ModulePrice",
    "ModuleRecommendation",
    "Offer",
    "OfferLineItem",
    "OfferOutcome",
    "OfferRef",
    "PalomaModule",
    "PastAnalysis",
    "PastOffer",
    "ProblemCategory",
    "RestaurantHistory",
    "RestaurantMetrics",
    "RoiAssumptions",
    "RoiProjection",
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "ValidationStatus",
]
