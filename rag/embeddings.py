"""Embedding providers behind one port.

Two production-grade adapters:

- :class:`OpenAIEmbedder` — API embeddings (``text-embedding-3-small``
  by default), batched, for real deployments;
- :class:`HashingEmbedder` — the classic *hashing trick* (feature-hashed
  unigrams + bigrams, L2-normalised): fully deterministic, offline, zero
  cost. It is not a mock — it is a legitimate lexical embedding that
  makes semantic-ish search work in demos and keeps the entire RAG stack
  unit-testable without a network.

The rest of the platform sees only ``EmbeddingPort``: swap adapters in
the composition root via ``EMBEDDING_PROVIDER``.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Protocol, Sequence

from config.settings import Settings
from core.exceptions import ConfigurationError
from core.logging import get_logger

logger = get_logger("rag.embeddings")

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]{2,}")


class EmbeddingPort(Protocol):
    """Text -> vector. Implementations must be deterministic per input."""

    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Feature-hashing embedder (unigrams + bigrams, TF-weighted, L2-normalised)."""

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = [token.lower() for token in _TOKEN_RE.findall(text)]
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        for feature in features:
            digest = hashlib.md5(feature.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0  # signed hashing reduces collisions
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class OpenAIEmbedder:
    """OpenAI embeddings API adapter (batched, fail-fast on missing key)."""

    def __init__(self, settings: Settings, batch_size: int = 64) -> None:
        if not settings.openai_api_key:
            raise ConfigurationError(
                "EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY "
                "(embeddings are not routed through OpenRouter)."
            )
        from openai import OpenAI  # local import: optional at module level

        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.embedding_model
        self._batch_size = batch_size
        self.dimension = 1536  # text-embedding-3-small; overridden on first call

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        started = time.monotonic()
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            response = self._client.embeddings.create(model=self._model, input=batch)
            vectors.extend([item.embedding for item in response.data])
        if vectors:
            self.dimension = len(vectors[0])
        logger.debug(
            "Embedded %d text(s) in %.0fms via %s",
            len(texts),
            (time.monotonic() - started) * 1000,
            self._model,
        )
        return vectors
