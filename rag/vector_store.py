"""Vector store adapters behind one port.

- :class:`InMemoryVectorStore` — numpy cosine search + lexical keyword
  index, persisted to a JSON file. The demo/test backend, and an honest
  one: exact (non-approximate) search over thousands of chunks is
  perfectly production-adequate at this corpus size.
- :class:`PgVectorStore` — PostgreSQL + pgvector: one database next to
  the CRM, no extra infrastructure, HNSW/IVFFlat ANN indexes, hybrid
  search via ``tsvector``. Chosen over dedicated vector DBs precisely
  because operational cost matters more than benchmark deltas at this
  scale.

Re-ingestion contract: ``add`` replaces all chunks of the same
``doc_id`` — ingesting a file twice never duplicates knowledge.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

from core.exceptions import ConfigurationError, DataSourceError
from core.logging import get_logger
from rag.models import Chunk

logger = get_logger("rag.vector_store")

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]{2,}")


class VectorStorePort(Protocol):
    """Persistence + search port for embedded chunks."""

    def add(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None: ...

    def vector_search(self, vector: Sequence[float], k: int) -> list[tuple[Chunk, float]]: ...

    def keyword_search(self, query: str, k: int) -> list[tuple[Chunk, float]]: ...

    def count(self) -> int: ...


class InMemoryVectorStore:
    """Exact cosine search over a numpy matrix, JSON-persisted."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self._persist_path = persist_path
        self._chunks: list[Chunk] = []
        self._matrix: np.ndarray | None = None
        if persist_path is not None and persist_path.is_file():
            self._load(persist_path)

    # --- port -------------------------------------------------------------
    def add(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must be the same length")
        replaced_docs = {chunk.doc_id for chunk in chunks}
        kept = [
            (chunk, row)
            for chunk, row in zip(self._chunks, self._rows())
            if chunk.doc_id not in replaced_docs
        ]
        self._chunks = [chunk for chunk, _ in kept] + list(chunks)
        rows = [row for _, row in kept] + [np.asarray(v, dtype=np.float32) for v in vectors]
        self._matrix = np.vstack(rows) if rows else None
        if self._persist_path is not None:
            self._save(self._persist_path)
        logger.info("Vector store now holds %d chunk(s)", len(self._chunks))

    def vector_search(self, vector: Sequence[float], k: int) -> list[tuple[Chunk, float]]:
        if self._matrix is None or not self._chunks:
            return []
        query = np.asarray(vector, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        norms = np.linalg.norm(self._matrix, axis=1)
        norms[norms == 0] = 1e-9
        scores = (self._matrix @ query) / (norms * query_norm)
        order = np.argsort(scores)[::-1][:k]
        return [(self._chunks[i], float(scores[i])) for i in order]

    def keyword_search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        """IDF-weighted token overlap — the lexical half of hybrid search."""
        query_tokens = {t.lower() for t in _TOKEN_RE.findall(query)}
        if not query_tokens or not self._chunks:
            return []
        document_frequency: Counter[str] = Counter()
        chunk_tokens: list[set[str]] = []
        for chunk in self._chunks:
            tokens = {t.lower() for t in _TOKEN_RE.findall(chunk.text)}
            chunk_tokens.append(tokens)
            document_frequency.update(tokens & query_tokens)
        total = len(self._chunks)
        scored: list[tuple[Chunk, float]] = []
        for chunk, tokens in zip(self._chunks, chunk_tokens):
            hit = tokens & query_tokens
            if not hit:
                continue
            score = sum(np.log1p(total / document_frequency[token]) for token in hit)
            scored.append((chunk, float(score)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]

    def count(self) -> int:
        return len(self._chunks)

    # --- persistence --------------------------------------------------------
    def _rows(self) -> list[np.ndarray]:
        if self._matrix is None:
            return []
        return [self._matrix[i] for i in range(self._matrix.shape[0])]

    def _save(self, path: Path) -> None:
        payload = {
            "chunks": [chunk.model_dump(mode="json") for chunk in self._chunks],
            "vectors": [row.tolist() for row in self._rows()],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _load(self, path: Path) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._chunks = [Chunk(**raw) for raw in payload["chunks"]]
            vectors = payload["vectors"]
            self._matrix = np.asarray(vectors, dtype=np.float32) if vectors else None
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise DataSourceError(f"Corrupt vector index at {path}: {exc}") from exc
        logger.info("Vector index loaded: %d chunk(s) from %s", len(self._chunks), path.name)


class PgVectorStore:
    """PostgreSQL + pgvector adapter (cosine ANN + tsvector keyword search).

    Schema is owned by the adapter (``ensure_schema``): extension, table,
    ANN index (HNSW or IVFFlat) and a GIN index for the lexical channel.
    Requires ``psycopg`` and a reachable database — both are checked at
    construction time, never mid-request.
    """

    def __init__(self, dsn: str, dimension: int, index_kind: str = "hnsw") -> None:
        try:
            import psycopg  # noqa: F401 — optional heavy dependency
        except ImportError as exc:
            raise ConfigurationError(
                "RAG_BACKEND=pgvector requires the 'psycopg' package: "
                "pip install 'psycopg[binary]'"
            ) from exc
        self._psycopg = psycopg
        self._dsn = dsn
        self._dimension = dimension
        self._index_kind = index_kind
        self.ensure_schema()

    def ensure_schema(self) -> None:
        index_ddl = (
            "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON rag_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
            if self._index_kind == "hnsw"
            else "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON rag_chunks "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
        with self._psycopg.connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    chunk_id   TEXT PRIMARY KEY,
                    doc_id     TEXT NOT NULL,
                    source     TEXT NOT NULL,
                    title      TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text       TEXT NOT NULL,
                    metadata   JSONB NOT NULL DEFAULT '{{}}',
                    embedding  vector({self._dimension}) NOT NULL,
                    tsv        tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED
                )
                """
            )
            cursor.execute(index_ddl)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON rag_chunks USING gin (tsv)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON rag_chunks (doc_id)")
        logger.info("pgvector schema ready (%s index, dim=%d)", self._index_kind, self._dimension)

    def add(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        started = time.monotonic()
        with self._psycopg.connect(self._dsn) as connection, connection.cursor() as cursor:
            for doc_id in {chunk.doc_id for chunk in chunks}:
                cursor.execute("DELETE FROM rag_chunks WHERE doc_id = %s", (doc_id,))
            for chunk, vector in zip(chunks, vectors):
                cursor.execute(
                    """
                    INSERT INTO rag_chunks
                        (chunk_id, doc_id, source, title, chunk_index, text, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.doc_id,
                        chunk.source,
                        chunk.title,
                        chunk.index,
                        chunk.text,
                        json.dumps(chunk.metadata),
                        _to_pg_vector(vector),
                    ),
                )
        logger.info(
            "pgvector upsert: %d chunk(s) in %.0fms",
            len(chunks),
            (time.monotonic() - started) * 1000,
        )

    def vector_search(self, vector: Sequence[float], k: int) -> list[tuple[Chunk, float]]:
        with self._psycopg.connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id, doc_id, source, title, chunk_index, text, metadata,
                       1 - (embedding <=> %s::vector) AS score
                FROM rag_chunks ORDER BY embedding <=> %s::vector LIMIT %s
                """,
                (_to_pg_vector(vector), _to_pg_vector(vector), k),
            )
            return [_row_to_result(row) for row in cursor.fetchall()]

    def keyword_search(self, query: str, k: int) -> list[tuple[Chunk, float]]:
        with self._psycopg.connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id, doc_id, source, title, chunk_index, text, metadata,
                       ts_rank(tsv, plainto_tsquery('simple', %s)) AS score
                FROM rag_chunks
                WHERE tsv @@ plainto_tsquery('simple', %s)
                ORDER BY score DESC LIMIT %s
                """,
                (query, query, k),
            )
            return [_row_to_result(row) for row in cursor.fetchall()]

    def count(self) -> int:
        with self._psycopg.connect(self._dsn) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM rag_chunks")
            return int(cursor.fetchone()[0])


def _to_pg_vector(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.7f}" for value in vector) + "]"


def _row_to_result(row: tuple) -> tuple[Chunk, float]:
    chunk_id, doc_id, source, title, index, text, metadata, score = row
    chunk = Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        source=source,
        title=title,
        index=index,
        text=text,
        metadata=metadata if isinstance(metadata, dict) else json.loads(metadata or "{}"),
    )
    return chunk, float(score)
