"""Restaurant metrics access: repository abstraction + service facade.

The service depends on the :class:`MetricsRepository` *protocol*, not on a
concrete backend, so swapping CSV -> SQLite -> Paloma365 production API is
a one-line change in the composition root (``core/container.py``) with
zero impact on agents, tools or engines (Dependency Inversion).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd
from pydantic import ValidationError

from core.cache import Cache
from core.exceptions import DataSourceError, RestaurantNotFoundError
from core.logging import get_logger
from models.restaurant import RestaurantMetrics

logger = get_logger("services.restaurant")


class MetricsRepository(Protocol):
    """Read-side port for restaurant performance snapshots."""

    def get_by_id(self, restaurant_id: str) -> RestaurantMetrics:
        """Return metrics for one restaurant or raise ``RestaurantNotFoundError``."""
        ...

    def list_ids(self) -> list[str]:
        """Return every known restaurant id."""
        ...


class CsvMetricsRepository:
    """CSV-backed repository (demo data source).

    Deliberately does NOT cache: caching is a cross-cutting concern owned
    by :class:`CachedMetricsRepository`, toggled with the ``USE_CACHE``
    feature flag. Every row is validated through Pydantic at read time —
    bad source data fails fast with a precise message.
    """

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path

    def get_by_id(self, restaurant_id: str) -> RestaurantMetrics:
        metrics = self._load().get(restaurant_id)
        if metrics is None:
            raise RestaurantNotFoundError(restaurant_id)
        logger.info("Loaded metrics for %s from %s", restaurant_id, self._csv_path.name)
        return metrics

    def list_ids(self) -> list[str]:
        return sorted(self._load().keys())

    def _load(self) -> dict[str, RestaurantMetrics]:
        if not self._csv_path.is_file():
            raise DataSourceError(f"Restaurant CSV not found: {self._csv_path}")
        try:
            frame = pd.read_csv(self._csv_path)
            return {
                str(row["restaurant_id"]): RestaurantMetrics(**row)
                for row in frame.to_dict(orient="records")
            }
        except (ValidationError, KeyError, ValueError) as exc:
            raise DataSourceError(f"Malformed restaurant data in {self._csv_path}: {exc}") from exc


class CachedMetricsRepository:
    """Caching decorator over any :class:`MetricsRepository` (GoF Decorator).

    Guarantees that when the Architect already fetched a restaurant's
    metrics, the Developer's identical request is served from cache —
    one data-source read per restaurant per TTL window, whatever the
    backend costs.
    """

    def __init__(self, inner: MetricsRepository, cache: Cache) -> None:
        self._inner = inner
        self._cache = cache

    def get_by_id(self, restaurant_id: str) -> RestaurantMetrics:
        key = f"metrics:{restaurant_id}"
        cached = self._cache.get(key)
        if cached is not None:
            logger.info("Cache hit: metrics for %s", restaurant_id)
            return cached
        metrics = self._inner.get_by_id(restaurant_id)
        self._cache.set(key, metrics)
        return metrics

    def list_ids(self) -> list[str]:
        return self._inner.list_ids()


class SqliteMetricsRepository:
    """SQLite-backed repository — extension point for the next iteration.

    TODO: implement over ``sqlite3``/SQLAlchemy once analytics snapshots
    move out of flat files. The protocol guarantees a drop-in swap.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def get_by_id(self, restaurant_id: str) -> RestaurantMetrics:
        raise NotImplementedError("SQLite metrics backend is not implemented yet")

    def list_ids(self) -> list[str]:
        raise NotImplementedError("SQLite metrics backend is not implemented yet")


class RestaurantService:
    """Facade the rest of the platform talks to for restaurant analytics."""

    def __init__(self, repository: MetricsRepository) -> None:
        self._repository = repository

    def get_metrics(self, restaurant_id: str) -> RestaurantMetrics:
        """Fetch the validated performance snapshot for one restaurant."""
        return self._repository.get_by_id(restaurant_id)

    def list_restaurants(self) -> list[str]:
        """List all restaurant ids available for analysis."""
        return self._repository.list_ids()
