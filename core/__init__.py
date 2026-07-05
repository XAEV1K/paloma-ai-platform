"""Core infrastructure: logging, exceptions and the composition root.

This package contains framework-agnostic building blocks. Nothing in here
may import from ``crew`` or ``tools`` — dependencies always point inwards.
"""

from core.exceptions import (
    ConfigurationError,
    DataSourceError,
    OfferNotFoundError,
    PalomaError,
    RestaurantNotFoundError,
    UnknownModuleError,
)
from core.logging import configure_logging, get_logger

__all__ = [
    "ConfigurationError",
    "DataSourceError",
    "OfferNotFoundError",
    "PalomaError",
    "RestaurantNotFoundError",
    "UnknownModuleError",
    "configure_logging",
    "get_logger",
]
