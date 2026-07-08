"""Context builder: retrieval results → one LLM-ready Context Package.

The last RAG stage and the only one visible to agents. Responsibilities:

- **budgeting** — hard character budget so retrieval can never blow up
  the prompt (chunks are cut at sentence boundaries, whole-chunk-first);
- **compression** — near-duplicate chunks (chunk overlap produces them
  by design) are dropped by token-set similarity;
- **grounding** — every chunk is rendered under a ``[S<n>]`` marker with
  its source, so answers can cite and reviewers can audit.
"""

from __future__ import annotations

import re

from core.logging import get_logger
from rag.models import ContextPackage, RetrievedChunk
from rag.retrieval import RetrievalService

logger = get_logger("rag.context")

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]{2,}")
_DUPLICATE_SIMILARITY = 0.85


class ContextBuilder:
    """Turns a query into a grounded, budgeted context block."""

    def __init__(self, retrieval: RetrievalService, char_budget: int = 4000) -> None:
        self._retrieval = retrieval
        self._char_budget = char_budget

    def build(self, query: str) -> ContextPackage:
        retrieved, metrics = self._retrieval.retrieve(query)
        selected = self._compress(retrieved)

        parts: list[str] = []
        used = 0
        kept: list[RetrievedChunk] = []
        for position, item in enumerate(selected, start=1):
            body = item.chunk.text.strip()
            remaining = self._char_budget - used
            if remaining <= 200:  # too small a window to be useful
                break
            if len(body) > remaining:
                body = self._cut_at_sentence(body, remaining)
            block = f"[S{position}] ({item.chunk.source})\n{body}"
            parts.append(block)
            used += len(block)
            kept.append(item)

        text = "\n\n".join(parts)
        sources = list(dict.fromkeys(item.chunk.source for item in kept))
        package = ContextPackage(
            query=query,
            chunks=kept,
            text=text,
            sources=sources,
            char_count=len(text),
            metrics=metrics,
        )
        logger.info(
            "Context package: %d chunk(s), %d chars, %d source(s)",
            len(kept),
            package.char_count,
            len(sources),
        )
        return package

    # ------------------------------------------------------------------
    @staticmethod
    def _compress(items: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Drop near-duplicates (overlapping chunks retrieve together)."""
        kept: list[RetrievedChunk] = []
        kept_tokens: list[set[str]] = []
        for item in items:
            tokens = {t.lower() for t in _TOKEN_RE.findall(item.chunk.text)}
            duplicate = any(
                len(tokens & existing) / max(len(tokens | existing), 1) > _DUPLICATE_SIMILARITY
                for existing in kept_tokens
            )
            if not duplicate:
                kept.append(item)
                kept_tokens.append(tokens)
        return kept

    @staticmethod
    def _cut_at_sentence(text: str, limit: int) -> str:
        cut = text[:limit]
        last_end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind(".\n"))
        if last_end > limit // 2:
            return cut[: last_end + 1]
        return cut
