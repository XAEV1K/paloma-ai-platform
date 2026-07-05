"""Caching: TTL semantics and the metrics-repository decorator."""

from __future__ import annotations

from core.cache import InMemoryTTLCache
from models.restaurant import RestaurantMetrics
from services.restaurant_service import CachedMetricsRepository


class CountingRepository:
    """Fake backend that counts how often it is actually hit."""

    def __init__(self, metrics: RestaurantMetrics) -> None:
        self._metrics = metrics
        self.calls = 0

    def get_by_id(self, restaurant_id: str) -> RestaurantMetrics:
        self.calls += 1
        return self._metrics

    def list_ids(self) -> list[str]:
        return [self._metrics.restaurant_id]


def test_ttl_cache_get_set() -> None:
    cache = InMemoryTTLCache(default_ttl_seconds=60)
    assert cache.get("k") is None
    cache.set("k", 42)
    assert cache.get("k") == 42


def test_ttl_expiry() -> None:
    cache = InMemoryTTLCache(default_ttl_seconds=60)
    cache.set("k", 42, ttl_seconds=-1)  # already expired
    assert cache.get("k") is None


def test_second_fetch_is_served_from_cache(healthy_restaurant: RestaurantMetrics) -> None:
    """The Architect fetched metrics -> the Developer's fetch is free."""
    backend = CountingRepository(healthy_restaurant)
    repository = CachedMetricsRepository(backend, InMemoryTTLCache())

    first = repository.get_by_id("T-002")
    second = repository.get_by_id("T-002")

    assert backend.calls == 1
    assert first == second
