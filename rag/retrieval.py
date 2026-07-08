"""Retrieval engine: hybrid search + deterministic reranking.

Pipeline: embed query → vector top-N + keyword top-N → Reciprocal Rank
Fusion → rerank → top-K.

Why RRF for hybrid fusion: vector and keyword scores live on different
scales; RRF fuses *ranks*, not scores, which is robust, parameter-light
and the industry-standard baseline (used by Elasticsearch and most RAG
stacks). Why a deterministic reranker instead of a cross-encoder model:
same latency class as the search itself, zero cost, reproducible — and
the ``RerankerService`` seam is exactly where a cross-encoder plugs in
later without touching callers.
"""

from __future__ import annotations

import re
import time
from typing import Sequence

from core.logging import get_logger
from rag.embeddings import EmbeddingPort
from rag.models import Chunk, RetrievalMetrics, RetrievedChunk
from rag.vector_store import VectorStorePort

logger = get_logger("rag.retrieval")

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]{2,}")
_RRF_K = 60  # standard damping constant


class RerankerService:
    """Blends fusion rank with lexical query coverage.

    Final score = 0.6 * fused-rank score + 0.4 * fraction of query terms
    present in the chunk. Cheap, deterministic, and measurably reduces
    the classic RRF failure mode (high-rank chunk that ignores half the
    query).
    """

    def rerank(
        self, query: str, candidates: list[tuple[Chunk, float, list[str]]]
    ) -> list[tuple[Chunk, float, list[str]]]:
        query_tokens = {t.lower() for t in _TOKEN_RE.findall(query)}
        if not candidates:
            return []
        max_fused = max(score for _, score, _ in candidates) or 1.0

        def final_score(item: tuple[Chunk, float, list[str]]) -> float:
            chunk, fused, _ = item
            coverage = 0.0
            if query_tokens:
                chunk_tokens = {t.lower() for t in _TOKEN_RE.findall(chunk.text)}
                coverage = len(query_tokens & chunk_tokens) / len(query_tokens)
            return 0.6 * (fused / max_fused) + 0.4 * coverage

        return sorted(candidates, key=final_score, reverse=True)


class RetrievalService:
    """The subsystem's query-side entry point (store/embedder-agnostic)."""

    def __init__(
        self,
        embedder: EmbeddingPort,
        store: VectorStorePort,
        reranker: RerankerService,
        top_k: int = 5,
        candidate_pool: int = 20,
        hybrid: bool = True,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._reranker = reranker
        self._top_k = top_k
        self._candidate_pool = candidate_pool
        self._hybrid = hybrid

    def retrieve(self, query: str) -> tuple[list[RetrievedChunk], RetrievalMetrics]:
        """Return the top-K most relevant chunks with full timing metrics."""
        started = time.monotonic()
        query_vector = self._embedder.embed([query])[0]
        embedding_ms = (time.monotonic() - started) * 1000

        started = time.monotonic()
        vector_hits = self._store.vector_search(query_vector, self._candidate_pool)
        keyword_hits = (
            self._store.keyword_search(query, self._candidate_pool) if self._hybrid else []
        )
        fused = self._fuse(vector_hits, keyword_hits)
        search_ms = (time.monotonic() - started) * 1000

        started = time.monotonic()
        reranked = self._reranker.rerank(query, fused)[: self._top_k]
        rerank_ms = (time.monotonic() - started) * 1000

        results = [
            RetrievedChunk(chunk=chunk, score=round(score, 4), channels=channels)
            for chunk, score, channels in reranked
        ]
        metrics = RetrievalMetrics(
            embedding_ms=round(embedding_ms, 1),
            search_ms=round(search_ms, 1),
            rerank_ms=round(rerank_ms, 1),
            candidates=len(fused),
            returned=len(results),
        )
        logger.info(
            "Retrieval: %d/%d chunk(s) in %.0fms (embed %.0f / search %.0f / rerank %.0f)",
            metrics.returned,
            metrics.candidates,
            metrics.total_ms,
            metrics.embedding_ms,
            metrics.search_ms,
            metrics.rerank_ms,
        )
        return results, metrics

    @staticmethod
    def _fuse(
        vector_hits: Sequence[tuple[Chunk, float]],
        keyword_hits: Sequence[tuple[Chunk, float]],
    ) -> list[tuple[Chunk, float, list[str]]]:
        """Reciprocal Rank Fusion across the two channels."""
        fused: dict[str, tuple[Chunk, float, list[str]]] = {}
        for channel, hits in (("vector", vector_hits), ("keyword", keyword_hits)):
            for rank, (chunk, _) in enumerate(hits):
                contribution = 1.0 / (_RRF_K + rank + 1)
                if chunk.chunk_id in fused:
                    existing_chunk, score, channels = fused[chunk.chunk_id]
                    fused[chunk.chunk_id] = (
                        existing_chunk,
                        score + contribution,
                        channels + [channel],
                    )
                else:
                    fused[chunk.chunk_id] = (chunk, contribution, [channel])
        return sorted(fused.values(), key=lambda item: item[1], reverse=True)
