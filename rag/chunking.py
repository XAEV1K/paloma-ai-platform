"""Chunking service: structure-aware splitting with overlap.

Why not fixed-size windows: knowledge documents (manuals, FAQ) carry
their meaning in sections. The chunker is markdown-aware — it tracks the
current heading and prefixes every chunk with its section path, so a
retrieved chunk stays self-explanatory ("Delivery Module > Courier
dispatch: ...") even out of context. Paragraphs are packed greedily up
to ``max_chars`` with a sentence-boundary overlap carried into the next
chunk to preserve continuity across boundaries.
"""

from __future__ import annotations

import re
import uuid

from core.logging import get_logger
from rag.models import Chunk, Document

logger = get_logger("rag.chunking")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


class ChunkingService:
    """Splits document text into overlapping, heading-annotated chunks."""

    def __init__(self, max_chars: int = 900, overlap_chars: int = 150) -> None:
        if overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars

    def split(self, document: Document, text: str) -> list[Chunk]:
        """Produce chunks for one document. Deterministic for identical input."""
        blocks = self._blocks_with_headings(text)
        chunks: list[Chunk] = []
        buffer: list[str] = []
        buffer_len = 0
        current_heading = document.title

        def flush(heading: str) -> None:
            nonlocal buffer, buffer_len
            if not buffer:
                return
            body = "\n\n".join(buffer).strip()
            if not body:
                buffer, buffer_len = [], 0
                return
            chunks.append(self._make_chunk(document, len(chunks), heading, body))
            tail = self._overlap_tail(body)
            buffer = [tail] if tail else []
            buffer_len = len(tail)

        for heading, block in blocks:
            if heading != current_heading:
                flush(current_heading)
                buffer, buffer_len = [], 0  # no overlap across section boundaries
                current_heading = heading
            if buffer_len + len(block) > self._max_chars and buffer:
                flush(current_heading)
            # A single oversized paragraph is split hard on sentence boundaries.
            for piece in self._split_oversized(block):
                if buffer_len + len(piece) > self._max_chars and buffer:
                    flush(current_heading)
                buffer.append(piece)
                buffer_len += len(piece)
        flush(current_heading)

        logger.debug("Chunked '%s' into %d chunk(s)", document.title, len(chunks))
        return chunks

    # ------------------------------------------------------------------
    def _make_chunk(self, document: Document, index: int, heading: str, body: str) -> Chunk:
        prefix = f"{document.title} > {heading}" if heading != document.title else document.title
        return Chunk(
            chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{document.doc_id}:{index}").hex[:20],
            doc_id=document.doc_id,
            source=document.source,
            title=document.title,
            index=index,
            text=f"[{prefix}]\n{body}",
            metadata={"heading": heading},
        )

    @staticmethod
    def _blocks_with_headings(text: str) -> list[tuple[str, str]]:
        """(current heading, paragraph) pairs in document order."""
        result: list[tuple[str, str]] = []
        heading = ""
        for raw_block in re.split(r"\n\s*\n", text):
            block = raw_block.strip()
            if not block:
                continue
            match = _HEADING_RE.match(block.splitlines()[0])
            if match:
                heading = match.group(2).strip()
                remainder = "\n".join(block.splitlines()[1:]).strip()
                if remainder:
                    result.append((heading, remainder))
                continue
            result.append((heading, block))
        return result

    def _split_oversized(self, block: str) -> list[str]:
        if len(block) <= self._max_chars:
            return [block]
        pieces: list[str] = []
        current = ""
        for sentence in _SENTENCE_END_RE.split(block):
            if len(current) + len(sentence) + 1 > self._max_chars and current:
                pieces.append(current.strip())
                current = ""
            current += sentence + " "
        if current.strip():
            pieces.append(current.strip())
        return pieces

    def _overlap_tail(self, body: str) -> str:
        """The last sentences of a chunk, carried into the next one."""
        if self._overlap_chars <= 0:
            return ""
        tail = body[-self._overlap_chars :]
        # Start the overlap at a sentence boundary when possible.
        match = _SENTENCE_END_RE.search(tail)
        return tail[match.end() :].strip() if match else tail.strip()
