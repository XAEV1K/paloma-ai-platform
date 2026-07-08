"""RAG data contracts.

Frozen Pydantic models shared by every stage of the pipeline. The
``ContextPackage`` is the subsystem's only public artifact: agents and
the conversation runtime consume it as rendered text + citations,
never raw vectors or store rows.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class Document(BaseModel):
    """A source document registered in the knowledge base."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    source: str = Field(description="Origin path/URL — the citation target.")
    title: str
    media_type: str = Field(description="markdown | text | html | pdf | docx")
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, str] = Field(default_factory=dict)

    @staticmethod
    def make_id(source: str) -> str:
        """Stable id from the source path — re-ingestion replaces, not duplicates."""
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


class Chunk(BaseModel):
    """One retrievable unit of knowledge."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    doc_id: str
    source: str
    title: str
    index: int = Field(ge=0, description="Position within the document.")
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    """A chunk with its relevance evidence."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float = Field(description="Final (reranked) relevance score, higher = better.")
    channels: list[str] = Field(
        default_factory=list,
        description="Which searches surfaced it: 'vector' and/or 'keyword'.",
    )


class RetrievalMetrics(BaseModel):
    """Observability for one retrieval pass — shown after every run."""

    model_config = ConfigDict(frozen=True)

    embedding_ms: float = Field(ge=0)
    search_ms: float = Field(ge=0)
    rerank_ms: float = Field(ge=0)
    candidates: int = Field(ge=0)
    returned: int = Field(ge=0)

    @property
    def total_ms(self) -> float:
        return self.embedding_ms + self.search_ms + self.rerank_ms


class ContextPackage(BaseModel):
    """The RAG subsystem's deliverable: ready-to-inject grounded context."""

    query: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    text: str = Field(description="Rendered context block with source markers.")
    sources: list[str] = Field(default_factory=list, description="Unique citation sources.")
    char_count: int = Field(ge=0)
    metrics: RetrievalMetrics

    @property
    def is_empty(self) -> bool:
        return not self.chunks
