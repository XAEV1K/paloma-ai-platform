"""Caching port + in-memory TTL implementation.

Used to guarantee that when the Architect has already pulled a
restaurant's metrics, the Developer's tool call is served from cache
instead of re-reading the data source. The :class:`Cache` protocol is
the seam for Redis/Memcached in production.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from core.logging import get_logger

logger = get_logger("core.cache")


class Cache(Protocol):
    """Minimal cache port: get-or-None and set-with-TTL."""

    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None: ...


class InMemoryTTLCache:
    """Process-local TTL cache. Single-threaded pipeline -> no locking needed.

    TODO: swap for Redis behind the same protocol when the platform runs
    multiple worker processes.
    """

    def __init__(self, default_ttl_seconds: float = 300.0) -> None:
        self._default_ttl = default_ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._store[key] = (time.monotonic() + ttl, value)
